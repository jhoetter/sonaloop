"""The storage backend seam (Phase 1 of the cloud-data-model redesign).

Pins that the Store opens through a pluggable backend, that open-core stays SQLite with
unchanged behaviour, and that a postgresql:// URL fails LOUDLY rather than silently
falling back to SQLite (a silent fallback once served the cloud app off the wrong store)."""
from __future__ import annotations

import sqlite3
import sys
import types

import pytest

from sonaloop.storage import Store
from sonaloop.storage._backend import (
    PostgresBackend, SqliteBackend, StorageBackend, _PgConnection, _pg_json_extract,
    _pg_params, make_backend, schema_statements_postgres,
)


def test_store_opens_through_the_sqlite_backend(store):
    assert isinstance(store.backend, SqliteBackend)
    assert store.backend.dialect == "sqlite"
    assert store.path is not None and store.path.suffix == ".db"
    # the connection is the real sqlite3 one, schema applied, version stamped
    assert isinstance(store.conn, sqlite3.Connection)
    assert store.schema_version() >= 1


def test_current_schema_stamp_is_not_rewritten_on_each_store_open(tmp_path):
    """Read-only Store construction must not update+commit the global meta row.

    A missing/stale version still takes the idempotent upsert path, preserving
    cold-start and migration correctness.
    """
    class TrackingSqliteBackend(SqliteBackend):
        def __init__(self, path):
            super().__init__(path)
            self.statements: list[str] = []

        def connect(self):
            conn = super().connect()
            conn.set_trace_callback(self.statements.append)
            return conn

    backend = TrackingSqliteBackend(tmp_path / "schema-stamp.db")
    with Store(backend=backend) as first:
        expected = first.schema_version()
    assert any(sql.lstrip().upper().startswith("INSERT INTO META")
               for sql in backend.statements)

    backend.statements.clear()
    with Store(backend=backend) as second:
        assert second.schema_version() == expected
    assert not any(sql.lstrip().upper().startswith("INSERT INTO META")
                   for sql in backend.statements)

    # Simulate a process opening a DB stamped by an older application version.
    with sqlite3.connect(backend.path) as raw:
        raw.execute("UPDATE meta SET value='0' WHERE key='schema_version'")
    backend.statements.clear()
    with Store(backend=backend) as upgraded:
        assert upgraded.schema_version() == expected
    assert any(sql.lstrip().upper().startswith("INSERT INTO META")
               for sql in backend.statements)


def test_make_backend_defaults_to_sqlite_at_database_path():
    b = make_backend()
    assert isinstance(b, SqliteBackend) and b.path is not None


def test_postgres_url_selects_the_postgres_backend(monkeypatch):
    for url in ("postgresql://user@host/db", "postgres://user@host/db"):
        monkeypatch.setenv("DATABASE_URL", url)
        b = make_backend()
        assert isinstance(b, PostgresBackend) and b.path is None and b.dsn == url


class _FakePgRaw:
    """Small psycopg stand-in for testing tenant GUC lifecycle without a PG service."""

    def __init__(self):
        self.calls = []
        self.commits = 0
        self.row_factory = None

    def execute(self, sql, params=()):
        self.calls.append((sql, params))
        return self

    def commit(self):
        self.commits += 1


def _scope_values(raw):
    return [params[0] for sql, params in raw.calls if "set_config('app." in sql]


def test_tenant_checkout_explicitly_clears_an_absent_request_scope():
    """Regression: an unscoped checkout must not inherit a prior pooled request's GUCs."""
    from sonaloop import config

    backend = PostgresBackend("postgresql://unused/test", tenant=True)
    raw = _FakePgRaw()
    token = config.set_request_tenant_scope(["ws-a", "ws-b"], "ws-a")
    try:
        backend._bind_scope(raw)
    finally:
        config.reset_request_tenant_scope(token)
    assert _scope_values(raw) == ['{"ws-a","ws-b"}', "ws-a"]

    raw.calls.clear()
    backend._bind_scope(raw)
    assert _scope_values(raw) == ["{}", ""]
    assert raw.commits == 2


def test_tenant_pool_configure_and_return_reset_are_fail_closed(monkeypatch):
    """The physical connection is neutral both on creation and after pool return."""
    made = []

    class FakePool:
        def __init__(self, **kwargs):
            self.configure = kwargs["configure"]
            self.reset = kwargs["reset"]
            made.append(self)

        def open(self, *, wait):
            assert wait is True

    pool_module = types.ModuleType("psycopg_pool")
    pool_module.ConnectionPool = FakePool
    rows_module = types.ModuleType("psycopg.rows")
    rows_module.dict_row = object()
    psycopg_module = types.ModuleType("psycopg")
    psycopg_module.rows = rows_module
    monkeypatch.setitem(sys.modules, "psycopg_pool", pool_module)
    monkeypatch.setitem(sys.modules, "psycopg", psycopg_module)
    monkeypatch.setitem(sys.modules, "psycopg.rows", rows_module)

    backend = PostgresBackend("postgresql://unused/pool-reset", tenant=True)
    try:
        pool = backend._get_pool()
        raw = _FakePgRaw()
        pool.configure(raw)
        assert raw.row_factory is rows_module.dict_row
        assert _scope_values(raw) == ["{}", ""]

        raw.calls.clear()
        pool.reset(raw)
        assert _scope_values(raw) == ["{}", ""]
        assert raw.commits == 2
    finally:
        PostgresBackend._pools.pop(backend._key(), None)
    assert made == [pool]


# --- pure dialect translation (no Postgres server needed) -----------------------------

def test_schema_ports_to_postgres_dialect():
    stmts = schema_statements_postgres()
    joined = "\n".join(stmts)
    assert not any(s.upper().startswith("PRAGMA") for s in stmts)         # WAL pragma dropped
    assert "AUTOINCREMENT" not in joined                                  # → IDENTITY
    assert "GENERATED BY DEFAULT AS IDENTITY" in joined
    assert "BLOB" not in joined and "BYTEA" in joined                     # vector column
    assert '"end"' in joined                                             # reserved word stays quoted
    assert "-- " not in joined                                           # comments stripped (had ';')
    assert any("calendar_events" in s for s in stmts)


def test_param_translation_is_safe():
    assert _pg_params("SELECT * FROM t WHERE id=? AND x=?") == "SELECT * FROM t WHERE id=%s AND x=%s"
    # a literal % (none in the Store today) is escaped so psycopg won't read it as a placeholder
    assert _pg_params("WHERE x LIKE '%a%' AND id=?") == "WHERE x LIKE '%%a%%' AND id=%s"


def test_json_extract_translation_to_postgres():
    # SQLite json_extract(...) → PG (...::jsonb #>> '{...}'); the one dialect function the
    # mixins use (delete_research_project's council_sessions/syntheses deletes). Without this
    # Postgres errors: function json_extract(text, unknown) does not exist.
    assert (_pg_json_extract("DELETE FROM council_sessions WHERE json_extract(data, '$.project_id')=?")
            == "DELETE FROM council_sessions WHERE (data::jsonb #>> '{project_id}')=?")
    # nested path → array key list
    assert _pg_json_extract("json_extract(data, '$.a.b')") == "(data::jsonb #>> '{a,b}')"
    # untouched when there is no json_extract
    assert _pg_json_extract("SELECT 1 WHERE id=?") == "SELECT 1 WHERE id=?"
    # end to end through the translator (no upsert, non-tenant) also flips the placeholder
    conn = _PgConnection.__new__(_PgConnection)
    conn._tenant = False
    out = conn._translate("DELETE FROM syntheses WHERE json_extract(data, '$.project_id')=?")
    assert out == "DELETE FROM syntheses WHERE (data::jsonb #>> '{project_id}')=%s"


def test_insert_or_replace_translation_via_pk_lookup():
    # _PgConnection rewrites INSERT OR REPLACE → ON CONFLICT using the table's PK; stub the
    # PK lookup so this stays a pure unit test (no server).
    conn = _PgConnection.__new__(_PgConnection)
    conn._pk = {"runs": ["run_id"], "event_entities": ["event_id", "entity_id"]}
    out = conn._translate(
        "INSERT OR REPLACE INTO runs (run_id, project_id, data) VALUES (?, ?, ?)")
    assert out == ('INSERT INTO runs (run_id, project_id, data) VALUES (%s, %s, %s) '
                   'ON CONFLICT ("run_id") DO UPDATE SET "project_id" = EXCLUDED."project_id", '
                   '"data" = EXCLUDED."data"')
    # composite PK + a row that is ALL key columns → DO NOTHING (nothing to update)
    out2 = conn._translate("INSERT OR IGNORE INTO event_entities (event_id, entity_id) VALUES (?, ?)")
    assert out2.endswith('ON CONFLICT ("event_id", "entity_id") DO NOTHING')


def test_store_accepts_an_explicit_backend(tmp_path):
    """The seam is injectable — the Postgres backend will arrive this way without
    touching StoreBase."""
    backend = SqliteBackend(tmp_path / "explicit.db")
    s = Store(backend=backend)
    assert s.backend is backend and (tmp_path / "explicit.db").exists()
    s.close()


def test_open_core_never_imports_psycopg():
    """Hard guarantee: psycopg is a cloud-only OPTIONAL dependency. Importing the storage +
    services layer and opening a SQLite Store must NOT pull psycopg in (lazy import inside
    PostgresBackend only). Checked in a clean subprocess so a sibling test that already
    imported psycopg can't mask a regression."""
    import subprocess
    import sys

    code = ("import sys; import sonaloop.storage, sonaloop.services; "
            "from sonaloop.storage import Store; Store().close(); "
            "sys.exit(1 if 'psycopg' in sys.modules else 0)")
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert r.returncode == 0, f"open-core imported psycopg (must stay lazy): {r.stderr}"


def test_backend_interface_is_abstract():
    b = StorageBackend()
    with pytest.raises(NotImplementedError):
        b.connect()
    with pytest.raises(NotImplementedError):
        b.apply_schema(None)


def test_store_is_a_context_manager_with_idempotent_close():
    """A Store releases its connection deterministically (ticket store-connection-lifecycle):
    `with`, an explicit close(), and the __del__ backstop must all be safe and release exactly
    once — cloud's Postgres connections leak otherwise."""
    with Store() as s:
        assert s._closed is False
        assert s.schema_version() >= 0
    assert s._closed is True                       # __exit__ closed it

    s2 = Store()
    s2.close()
    assert s2._closed is True
    s2.close()                                     # idempotent — no double-release, no error

    # __del__ backstop: an unreferenced Store must close without raising (the ~60 unclosed
    # web-route sites rely on this; a function-local Store is refcount-collected at return).
    s3 = Store()
    s3.__del__()                                   # explicit, deterministic invocation
    assert s3._closed is True
    s3.__del__()                                   # still safe after already closed
