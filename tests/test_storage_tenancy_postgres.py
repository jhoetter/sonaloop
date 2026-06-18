"""Row-level tenancy + RLS on the Postgres backend (Phase 2 of cloud-data-model).

Proves the isolation is REAL — enforced by Postgres RLS, not app-level WHEREs — by running
as a NON-superuser app role (a superuser bypasses RLS, even FORCE). Open-core (SQLite) is
untouched: none of this exists there.

Skipped unless `SONALOOP_TEST_PG_DSN` (an admin/superuser DSN used only to create the app
role + drop schemas) is set, e.g. postgresql://postgres:test@localhost:55432/sonaloop.
"""
from __future__ import annotations

import os
import uuid

import pytest

# Postgres-only suite: psycopg ships with the `postgres` extra, which open-core CI does not
# install. importorskip skips the whole module cleanly when it's absent rather than erroring
# at collection time (the SONALOOP_TEST_PG_DSN gate below skips it when there's no DB).
psycopg = pytest.importorskip("psycopg")

from sonaloop import config, services
from sonaloop.storage import Store
from sonaloop.storage._backend import _tenant_tables

_ADMIN = os.getenv("SONALOOP_TEST_PG_DSN")
pytestmark = pytest.mark.skipif(not _ADMIN, reason="set SONALOOP_TEST_PG_DSN to run Postgres tenancy")

_APP_PW = "app"


def _app_dsn() -> str:
    # swap the admin DSN's credentials for the app role's
    rest = _ADMIN.split("://", 1)[1].split("@", 1)[1]
    return f"postgresql://sonaloop_app:{_APP_PW}@{rest}"


@pytest.fixture(scope="session", autouse=True)
def _app_role():
    a = psycopg.connect(_ADMIN, autocommit=True)
    a.execute("DO $$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='sonaloop_app') "
              f"THEN CREATE ROLE sonaloop_app LOGIN PASSWORD '{_APP_PW}' NOSUPERUSER NOBYPASSRLS; "
              "END IF; END $$;")
    a.execute(f"GRANT CREATE ON DATABASE {_ADMIN.rsplit('/', 1)[1]} TO sonaloop_app")
    a.close()


@pytest.fixture
def pg(monkeypatch):
    """A fresh per-test schema owned by the non-superuser app role, tenancy ON."""
    schema = "ten_" + uuid.uuid4().hex[:10]
    monkeypatch.setenv("DATABASE_URL", _app_dsn())
    monkeypatch.setenv("SONALOOP_PG_SCHEMA", schema)
    monkeypatch.setenv("SONALOOP_PG_TENANT", "1")
    monkeypatch.setenv("SONALOOP_PUBLIC_BASE_URL", "https://app.sonaloop.test")
    yield schema
    admin = psycopg.connect(_ADMIN, autocommit=True)
    admin.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
    admin.close()


def _scoped(accessible, active, fn):
    tok = config.set_request_tenant_scope(accessible, active)
    try:
        return fn()
    finally:
        config.reset_request_tenant_scope(tok)


def _titles(scope_ids, active):
    return _scoped(scope_ids, active,
                  lambda: sorted(p["title"] for p in services.list_research_projects(store=Store())))


def test_rls_isolates_reads_across_workspaces(pg):
    pa = _scoped(["wsA"], "wsA", lambda: services.start_project("Alpha", "a", store=Store()))
    _scoped(["wsB"], "wsB", lambda: services.start_project("Beta", "b", store=Store()))
    assert _titles(["wsA"], "wsA") == ["Alpha"]
    assert _titles(["wsB"], "wsB") == ["Beta"]
    assert _titles(["wsA", "wsB"], "wsA") == ["Alpha", "Beta"]
    # the row really is stamped with the active workspace
    assert pa["url"].endswith(pa["id"])


def test_rls_with_check_blocks_writing_into_another_workspace(pg):
    with pytest.raises(Exception):
        def _bad():
            st = Store()
            st.conn.execute(
                "INSERT INTO research_projects (id, workspace_id, slug, title, data, created_at, "
                "updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("x", "wsB", "s", "t", "{}", "2026", "2026"))   # active is wsA → WITH CHECK fails
            st.conn.commit()
        _scoped(["wsA", "wsB"], "wsA", _bad)


def test_unscoped_access_is_fail_closed(pg):
    _scoped(["wsA"], "wsA", lambda: services.start_project("Alpha", "a", store=Store()))
    # no scope bound → RLS sees no rows, and a write can't resolve a workspace_id (NOT NULL)
    assert services.list_research_projects(store=Store()) == []
    with pytest.raises(Exception):
        services.start_project("Orphan", "x", store=Store())


def test_same_slug_allowed_in_different_workspaces(pg):
    from conftest import create_persona
    a = _scoped(["wsA"], "wsA", lambda: create_persona(Store(), "Dr. Reuter"))
    b = _scoped(["wsB"], "wsB", lambda: create_persona(Store(), "Dr. Reuter"))
    assert a and b                              # the shared slug did NOT collide across workspaces


def test_importer_folds_a_sqlite_partition_into_a_workspace(pg, tmp_path):
    """The cutover tool: a single-tenant SQLite partition's rows land in Postgres under the
    target workspace, ids preserved, visible only to that workspace's scope."""
    from sonaloop.storage._backend import SqliteBackend, import_sqlite_to_postgres

    # build a source partition on plain SQLite (no scope, single-tenant)
    src_db = tmp_path / "partition.db"
    src = Store(backend=SqliteBackend(src_db))
    proj = services.start_project("Imported study", "from a partition", store=src)
    services.record_council(proj["id"], "Q?", [], [{"persona_id": "x", "text": "t"}], store=src, key="ic")
    src.close()

    counts = import_sqlite_to_postgres(src_db, "wsZ")
    assert counts["research_projects"] >= 1 and counts["council_sessions"] >= 1

    seen = _scoped(["wsZ"], "wsZ", lambda: services.list_research_projects(store=Store()))
    assert [p["title"] for p in seen] == ["Imported study"]
    assert seen[0]["id"] == proj["id"]                 # id preserved
    # and another workspace cannot see the imported rows
    assert _scoped(["wsA"], "wsA", lambda: services.list_research_projects(store=Store())) == []


def test_import_resyncs_identity_sequences_so_auto_id_inserts_dont_collide(pg, tmp_path):
    """Regression: imported rows preserve their ids, but `GENERATED BY DEFAULT AS IDENTITY` left
    the column's sequence at its start — so the first audit()/events insert after a cutover
    reused id=1 and tripped `audit_log_pkey` ('duplicate key value violates unique constraint').
    The importer now advances the sequences past the imported rows."""
    from sonaloop.storage._backend import SqliteBackend, import_sqlite_to_postgres

    src_db = tmp_path / "partition.db"
    src = Store(backend=SqliteBackend(src_db))
    for i in range(1, 4):                        # a lived-in partition: audit_log ids 1..3
        src.conn.execute(
            "INSERT INTO audit_log (id, entity_type, entity_id, action, reason, created_at, data) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (i, "persona", f"p{i}", "upsert", None, "2026-01-01T00:00:00Z", "{}"))
    src.conn.commit()
    src.close()

    assert import_sqlite_to_postgres(src_db, "wsZ")["audit_log"] == 3

    def _audit_then_max():
        st = Store()
        st.audit("persona", "p4", "upsert", None)   # auto-id insert: must NOT reuse 1..3
        st.conn.commit()
        mx = st.conn._raw.execute("SELECT MAX(id) AS m FROM audit_log").fetchone()["m"]
        st.close()
        return mx

    assert _scoped(["wsZ"], "wsZ", _audit_then_max) == 4   # sequence resumed past 1..3


def test_every_tenant_table_has_workspace_id_and_a_policy(pg):
    # the "can't forget a new table" gate: each tenant table must carry workspace_id AND an
    # RLS policy, or isolation has a hole.
    Store().close()                             # triggers schema + tenancy apply
    conn = psycopg.connect(_app_dsn())
    conn.execute(f'SET search_path TO "{pg}"')
    missing_col, missing_policy = [], []
    for t in _tenant_tables():
        col = conn.execute("SELECT 1 FROM information_schema.columns WHERE table_schema=%s "
                           "AND table_name=%s AND column_name='workspace_id'", (pg, t)).fetchone()
        pol = conn.execute("SELECT 1 FROM pg_policies WHERE schemaname=%s AND tablename=%s "
                           "AND policyname='tenant_isolation'", (pg, t)).fetchone()
        if not col:
            missing_col.append(t)
        if not pol:
            missing_policy.append(t)
    conn.close()
    assert not missing_col, f"tenant tables without workspace_id: {missing_col}"
    assert not missing_policy, f"tenant tables without an RLS policy: {missing_policy}"
