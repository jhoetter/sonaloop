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
import base64
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from threading import Barrier, Event

import pytest
from PIL import Image

# Postgres-only suite: psycopg ships with the `postgres` extra, which open-core CI does not
# install. importorskip skips the whole module cleanly when it's absent rather than erroring
# at collection time (the SONALOOP_TEST_PG_DSN gate below skips it when there's no DB).
psycopg = pytest.importorskip("psycopg")

from sonaloop import config, services
from sonaloop import plan as P
from sonaloop.storage import Store
from sonaloop.storage._backend import PostgresBackend, _tenant_tables
from sonaloop._project_locks import workspace_project_creation_lock

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


def test_project_operation_id_is_scoped_per_workspace(pg):
    """The deterministic operation id may repeat across tenants: composite PK/RLS scope owns it."""
    operation_id = "connector-session:create-1"
    pa = _scoped(["wsA"], "wsA", lambda: services.start_project(
        "Same intent", "g", operation_id=operation_id, store=Store()))
    pb = _scoped(["wsB"], "wsB", lambda: services.start_project(
        "Same intent", "g", operation_id=operation_id, store=Store()))
    replay_a = _scoped(["wsA"], "wsA", lambda: services.start_project(
        "Same intent", "g", operation_id=operation_id, store=Store()))

    assert pa["id"] == pb["id"] == replay_a["id"]
    assert replay_a["idempotent_replay"] is True
    assert _titles(["wsA"], "wsA") == ["Same intent"]
    assert _titles(["wsB"], "wsB") == ["Same intent"]


def test_run_operation_id_is_scoped_per_workspace(pg):
    operation_id = "connector-session:run-create-1"
    pa = _scoped(["wsA"], "wsA", lambda: services.start_project("A", "g", store=Store()))
    pb = _scoped(["wsB"], "wsB", lambda: services.start_project("B", "g", store=Store()))
    ra = _scoped(["wsA"], "wsA", lambda: services.start_run(
        pa["id"], operation_id=operation_id, store=Store()))
    rb = _scoped(["wsB"], "wsB", lambda: services.start_run(
        pb["id"], operation_id=operation_id, store=Store()))
    replay_a = _scoped(["wsA"], "wsA", lambda: services.start_run(
        pa["id"], operation_id=operation_id, store=Store()))

    assert ra["run_id"] == rb["run_id"] == replay_a["run_id"]
    assert replay_a["idempotent_replay"] is True


def test_claim_release_targets_only_the_active_workspace_under_multi_read_scope(pg):
    project_operation = "same-project-across-workspaces"
    run_operation = "same-run-across-workspaces"
    pa = _scoped(["wsA"], "wsA", lambda: services.start_project(
        "Same", "g", operation_id=project_operation, store=Store()))
    pb = _scoped(["wsB"], "wsB", lambda: services.start_project(
        "Same", "g", operation_id=project_operation, store=Store()))
    ra = _scoped(["wsA"], "wsA", lambda: services.start_run(
        pa["id"], operation_id=run_operation, store=Store()))
    rb = _scoped(["wsB"], "wsB", lambda: services.start_run(
        pb["id"], operation_id=run_operation, store=Store()))
    assert pa["id"] == pb["id"] and ra["run_id"] == rb["run_id"]

    _scoped(["wsA", "wsB"], "wsA", lambda: services.finish_run(
        ra["run_id"], "stopped", store=Store()))

    def claim_count(workspace_id):
        with Store() as scoped:
            return scoped.conn.execute(
                "SELECT COUNT(*) AS n FROM active_run_claims WHERE project_id=?",
                (pa["id"],),
            ).fetchone()["n"]

    assert _scoped(["wsA"], "wsA", lambda: claim_count("wsA")) == 0
    assert _scoped(["wsB"], "wsB", lambda: claim_count("wsB")) == 1


def test_postgres_concurrent_distinct_starts_claim_one_workspace_run(pg):
    project = _scoped(["ws_run_race"], "ws_run_race", lambda: services.start_project(
        "Postgres one active run", "g", store=Store()))
    barrier = Barrier(2)

    def create(operation_id: str):
        def _inside():
            with Store() as st:
                barrier.wait(timeout=10)
                try:
                    return services.start_run(
                        project["id"], operation_id=operation_id, store=st)
                except P.PlanError as exc:
                    return exc
        return _scoped(["ws_run_race"], "ws_run_race", _inside)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [future.result() for future in [
            pool.submit(create, "pg:run:left"), pool.submit(create, "pg:run:right")]]

    runs = [row for row in results if isinstance(row, dict)]
    errors = [row for row in results if isinstance(row, P.PlanError)]
    assert len(runs) == 1 and len(errors) == 1
    assert errors[0].code == "ACTIVE_RUN_EXISTS"
    assert runs[0]["run_id"] in errors[0].message
    persisted = _scoped(["ws_run_race"], "ws_run_race", lambda: Store().list_runs(project["id"]))
    assert len(persisted) == 1 and persisted[0]["status"] == "active"


def test_workspace_project_creation_waits_for_shared_maintenance_lock(pg):
    """An exhaustive workspace operation cannot race a new project insert."""
    workspace_id = "ws_project_creation_lock"
    attempted = Event()
    completed = Event()

    def create_while_locked():
        attempted.set()
        try:
            return _scoped([workspace_id], workspace_id, lambda: services.start_project(
                "Created after maintenance", "g",
                operation_id="pg:workspace-lock:create", store=Store(),
            ))
        finally:
            completed.set()

    token = config.set_request_tenant_scope([workspace_id], workspace_id)
    try:
        with Store() as maintenance, ThreadPoolExecutor(max_workers=1) as pool:
            with workspace_project_creation_lock(maintenance):
                future = pool.submit(create_while_locked)
                assert attempted.wait(timeout=5)
                assert not completed.wait(timeout=0.25)
                maintenance.conn.commit()
            created = future.result(timeout=10)
    finally:
        config.reset_request_tenant_scope(token)

    assert completed.is_set()
    assert created["title"] == "Created after maintenance"
    assert _titles([workspace_id], workspace_id) == ["Created after maintenance"]


def test_postgres_project_with_run_history_requires_archive(pg):
    workspace_id = "ws_delete_run_history"
    project = _scoped([workspace_id], workspace_id, lambda: services.start_project(
        "Preserve governed history", "g", store=Store()))
    run = _scoped([workspace_id], workspace_id, lambda: services.start_run(
        project["id"], operation_id="pg:durable:run", store=Store()))
    _scoped([workspace_id], workspace_id, lambda: services.finish_run(
        run["run_id"], "stopped", store=Store()))

    def blocked_delete():
        with pytest.raises(ValueError, match="PROJECT_DELETE_RUN_HISTORY_BLOCKED"):
            services.delete_research_project(project["id"], store=Store())
    _scoped([workspace_id], workspace_id, blocked_delete)

    archived = _scoped([workspace_id], workspace_id, lambda: services.archive_project(
        project["id"], "pg:durable:archive", "Preserve history", store=Store()))
    assert archived["status"] == "archived"


def test_delete_guard_and_cascade_use_only_the_active_workspace(pg):
    operation_id = "pg:same-project-delete-scope"
    run_operation = "pg:same-run-delete-scope"
    pa = _scoped(["wsA"], "wsA", lambda: services.start_project(
        "Same tenant identity", "g", operation_id=operation_id, store=Store()))
    pb = _scoped(["wsB"], "wsB", lambda: services.start_project(
        "Same tenant identity", "g", operation_id=operation_id, store=Store()))
    rb = _scoped(["wsB"], "wsB", lambda: services.start_run(
        pb["id"], operation_id=run_operation, store=Store()))
    assert pa["id"] == pb["id"]

    # B's readable run history must neither block nor be cascaded by deleting A.
    deleted = _scoped(["wsA", "wsB"], "wsA", lambda: services.delete_research_project(
        pa["id"], store=Store()))
    assert deleted["deleted"]["research_projects"] == 1

    assert _scoped(["wsA"], "wsA", lambda: Store().list_runs(pa["id"])) == []
    assert _scoped(["wsA"], "wsA", lambda: Store().get_research_project(pa["id"])) is None
    persisted_b = _scoped(["wsB"], "wsB", lambda: Store().list_runs(pb["id"]))
    assert _scoped(["wsB"], "wsB", lambda: Store().get_research_project(pb["id"])) is not None
    assert [(row["run_id"], row["status"]) for row in persisted_b] == [
        (rb["run_id"], "active"),
    ]


def test_product_understanding_and_dispatch_tokens_are_tenant_scoped(pg):
    """PU history stays in its RLS row; a token from wsA cannot mutate wsB."""
    def _seed(workspace_id: str, suffix: str):
        def _inside():
            st = Store()
            project = services.start_project(
                f"Reaction {suffix}", "Understand the real screen",
                methodology="Reaction Test", operation_id=f"pg:{suffix}:project", store=st)
            run = services.start_run(
                project["id"], operation_id=f"pg:{suffix}:run", store=st)
            dispatch = services.run_step(run["run_id"], store=st)
            asset = services.attach_asset(
                project["id"],
                content_base64=base64.b64encode(f"screen-{suffix}".encode()).decode(),
                filename=f"{suffix}.png", kind="screenshot",
                dispatch_token=dispatch["dispatch_token"], store=st)
            ref = {"kind": "asset", "id": asset["id"]}
            pu = services.record_product_understanding(
                project["id"], {"name": f"App {suffix}"}, f"rev-{suffix}",
                routes=[{"path": "/", "evidence_refs": [ref]}], flows=[], states=[],
                capabilities=[{"claim": f"Capability {suffix}", "status": "observed_present",
                               "evidence_refs": [ref]}],
                evidence_refs=[ref], observed_at="2026-08-08T10:00:00Z",
                dispatch_token=dispatch["dispatch_token"], store=st)
            return project["id"], dispatch["dispatch_token"], pu["id"]
        return _scoped([workspace_id], workspace_id, _inside)

    pa, token_a, pu_a = _seed("ws_A", "a")
    pb, _token_b, pu_b = _seed("ws_B", "b")
    assert pa != pb and pu_a != pu_b

    def _wrong_scope_write():
        # Expected exception tracebacks can outlive the assertion.  Explicitly close the
        # Store so a retained traceback cannot keep a Postgres connection checked out and
        # block this test's DROP SCHEMA teardown.
        with Store() as st:
            before = len((st.get_research_project(pb) or {}).get("assets") or [])
            with pytest.raises(P.PlanError) as exc:
                services.attach_asset(
                    pb, content_base64=base64.b64encode(b"cross-tenant").decode(),
                    filename="cross.png", dispatch_token=token_a, store=st)
            after = len((st.get_research_project(pb) or {}).get("assets") or [])
            return exc.value.code, before, after,

    code, before, after = _scoped(["ws_B"], "ws_B", _wrong_scope_write)
    assert code in {"UNKNOWN_DISPATCH_TOKEN", "DISPATCH_SCOPE_MISMATCH"}
    assert before == after == 1
    assert _scoped(["ws_A"], "ws_A", lambda: services.get_product_understanding(pa, store=Store()))["id"] == pu_a
    assert _scoped(["ws_B"], "ws_B", lambda: services.get_product_understanding(pb, store=Store()))["id"] == pu_b


def test_remote_same_bytes_have_workspace_isolated_admission_ids(pg, monkeypatch):
    """Physical content may deduplicate, but authorization identities never cross tenants."""
    monkeypatch.setenv("SONALOOP_REMOTE_ASSET_EXTERNAL_SCAN_REQUIRED", "0")
    image = BytesIO()
    Image.new("RGB", (8, 8), (15, 80, 140)).save(image, format="PNG")
    encoded = base64.b64encode(image.getvalue()).decode("ascii")

    def _seed(workspace_id: str):
        def _inside():
            st = Store()
            project = services.start_project(
                "Same remote intent", "Inspect exact pixels", methodology="Reaction Test",
                operation_id="same:project", store=st,
            )
            run = services.start_run(project["id"], operation_id="same:run", store=st)
            dispatch = services.run_step(run["run_id"], store=st)
            asset = services.admit_remote_screenshot(
                project["id"], run["run_id"], "same:upload", encoded,
                "screen.png", "image/png", "2026-08-08T10:00:00Z", "deploy:one",
                dispatch_token=dispatch["dispatch_token"], store=st,
            )
            return project["id"], asset
        return _scoped([workspace_id], workspace_id, _inside)

    project_a, asset_a = _seed("ws_asset_A")
    project_b, asset_b = _seed("ws_asset_B")
    assert project_a == project_b  # deterministic intent ids may match across RLS partitions
    assert asset_a["content_digest"] == asset_b["content_digest"]
    assert asset_a["id"] != asset_b["id"]
    assert asset_a["admission"]["workspace_id"] == "ws_asset_A"
    assert asset_b["admission"]["workspace_id"] == "ws_asset_B"

    def _read_cross_tenant_asset():
        with Store() as st:
            return services.get_asset(project_a, asset_b["id"], store=st)

    with pytest.raises(KeyError):
        _scoped(["ws_asset_A"], "ws_asset_A", _read_cross_tenant_asset)


def test_rls_with_check_blocks_writing_into_another_workspace(pg):
    with pytest.raises(Exception):
        def _bad():
            with Store() as st:
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

    def _write_unscoped():
        with Store() as st:
            return services.start_project("Orphan", "x", store=st)

    with pytest.raises(Exception):
        _write_unscoped()


def test_pool_return_clears_session_scope_before_connection_reuse(pg):
    """Security regression: session GUCs must not survive a pool return.

    Force a one-connection pool so this proves the exact physical connection that served wsA
    is neutral before reuse, then prove the normal unscoped checkout remains fail-closed.
    """
    backend = PostgresBackend(_app_dsn(), schema=pg, tenant=True)
    pool = backend._get_pool()
    assert pool is not None
    pool.resize(1, 1)

    token = config.set_request_tenant_scope(["wsA"], "wsA")
    try:
        scoped_store = Store(backend=backend)
        backend_pid = scoped_store.conn._raw.info.backend_pid
        scoped_store.conn.execute(
            "INSERT INTO research_projects (id, workspace_id, slug, title, data, created_at, "
            "updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("pool-a", "wsA", "alpha", "Alpha", "{}", "2026", "2026"))
        scoped_store.conn.commit()
        scoped_store.close()
    finally:
        config.reset_request_tenant_scope(token)

    # Bypass PostgresBackend.connect() once to inspect the pool-reset state itself. With
    # max_size=1 this is the same physical connection, not a freshly configured replacement.
    raw = pool.getconn()
    try:
        assert raw.info.backend_pid == backend_pid
        values = raw.execute(
            "SELECT current_setting('app.workspace_ids', true) AS ids, "
            "current_setting('app.active_workspace', true) AS active"
        ).fetchone()
        assert values == {"ids": "{}", "active": ""}
    finally:
        pool.putconn(raw)

    with Store(backend=backend) as unscoped_store:
        assert services.list_research_projects(store=unscoped_store) == []
        with pytest.raises(Exception):
            unscoped_store.conn.execute(
                "INSERT INTO research_projects (id, workspace_id, slug, title, data, created_at, "
                "updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("pool-orphan", "wsA", "orphan", "Orphan", "{}", "2026", "2026"))


def test_same_slug_allowed_in_different_workspaces(pg):
    from conftest import create_persona
    # Persona creation writes SOUL.md as well as a row; use production-shaped
    # workspace ids so the filesystem-partition validation is exercised too.
    a = _scoped(["ws_alpha"], "ws_alpha", lambda: create_persona(Store(), "Dr. Reuter"))
    b = _scoped(["ws_beta"], "ws_beta", lambda: create_persona(Store(), "Dr. Reuter"))
    assert a and b                              # the shared slug did NOT collide across workspaces


def test_project_delete_cascade_is_scoped_to_the_active_workspace(pg):
    """A copied project id may exist in two tenants; deleting one must not touch the other."""
    project_id = "rproject_shared_delete"

    def _seed(workspace_id: str, title: str):
        def _write():
            with Store() as st:
                st.upsert_research_project({
                    "id": project_id, "slug": "shared-delete", "title": title,
                    "goal": "tenant-safe deletion", "study_ids": [], "edges": [],
                    "created_at": "2026-06-16T12:00:00+00:00",
                    "updated_at": "2026-06-16T12:00:00+00:00",
                })
                st.insert_prediction_outcome({
                    "id": "pbout-shared-delete", "project_id": project_id,
                    "created_at": "2026-06-16T12:01:00+00:00", "observed": 1.0,
                })
                st.append_event(
                    "2026-06-16T12:02:00+00:00", "project.updated", "project",
                    project_id, project_id, {"url": f"/jobs/{project_id}"})

        _scoped([workspace_id], workspace_id, _write)

    def _state(workspace_id: str) -> dict:
        def _read():
            with Store() as st:
                return {
                    "project": st.get_research_project(project_id) is not None,
                    "outcomes": len(st.list_prediction_outcomes(project_id)),
                    "events": len([e for e in st.list_events_after(0)
                                   if e.get("project_id") == project_id]),
                }

        return _scoped([workspace_id], workspace_id, _read)

    _seed("ws_alpha", "Alpha copy")
    _seed("ws_beta", "Beta copy")

    def _delete_alpha():
        with Store() as st:
            return services.delete_research_project(project_id, store=st)

    deleted = _scoped(["ws_alpha", "ws_beta"], "ws_alpha", _delete_alpha)
    assert deleted["deleted"]["prediction_outcomes"] == 1
    assert deleted["deleted"]["events"] == 1
    assert _state("ws_alpha") == {"project": False, "outcomes": 0, "events": 0}
    assert _state("ws_beta") == {"project": True, "outcomes": 1, "events": 1}


def test_postgres_store_project_cascade_batch_commits_or_rolls_back_together(pg):
    def _exercise():
        with Store() as st:
            rollback_projects = [
                services.start_project(
                    f"Rollback {suffix}", "q",
                    operation_id=f"pg-atomic-rollback:{suffix}", store=st,
                )
                for suffix in ("a", "b")
            ]
            rollback_ids = [project["id"] for project in rollback_projects]
            for project_id in rollback_ids:
                assert st.get_research_plan(project_id) is not None
                st.delete_research_project(project_id, commit=False)
            assert all(st.get_research_project(project_id) is None for project_id in rollback_ids)
            st.conn.rollback()
            assert all(st.get_research_project(project_id) is not None for project_id in rollback_ids)
            assert all(st.get_research_plan(project_id) is not None for project_id in rollback_ids)

            commit_projects = [
                services.start_project(
                    f"Commit {suffix}", "q",
                    operation_id=f"pg-atomic-commit:{suffix}", store=st,
                )
                for suffix in ("a", "b")
            ]
            commit_ids = [project["id"] for project in commit_projects]
            for project_id in commit_ids:
                st.delete_research_project(project_id, commit=False)
            st.conn.commit()
            assert all(st.get_research_project(project_id) is None for project_id in commit_ids)
            assert all(st.get_research_plan(project_id) is None for project_id in commit_ids)

    _scoped(["ws_atomic"], "ws_atomic", _exercise)


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
