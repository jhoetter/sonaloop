"""Runtime-file isolation at the shared-Postgres web boundary.

SQLite is a single-user filesystem product and retains its local static-file behaviour. Shared
Postgres is row-tenanted: RLS protects database rows, not process-global files, so those routes
must fail closed until a workspace-authorized blob/download implementation replaces them.
"""
from __future__ import annotations

from starlette.testclient import TestClient

from sonaloop import config, web


def _write_runtime_fixtures(tmp_path, monkeypatch):
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    monkeypatch.setattr(config, "DATA_DIR", runtime)
    monkeypatch.setattr(web, "DATA_DIR", runtime)

    files = {
        "sonaloop.db": "private database",
        "settings.json": '{"ui_language":"de"}',
        "assets/ws-a-secret.txt": "asset a",
        "assets/ws-b-secret.txt": "asset b",
        "exports/ws-a-report.txt": "report a",
        "prototypes/shared-slug/index.html": "<h1>prototype</h1>",
        "sessions/shared-session/step-0.png": "not really a png",
    }
    for relative, content in files.items():
        target = runtime / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    return runtime


def test_sqlite_runtime_file_serving_stays_unchanged(tmp_path, monkeypatch):
    _write_runtime_fixtures(tmp_path, monkeypatch)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'local.db'}")
    # A stray tenant flag alone must not alter the open-core SQLite product.
    monkeypatch.setenv("SONALOOP_PG_TENANT", "1")

    client = TestClient(web.create_app())
    registered = {getattr(route, "path", "") for route in client.app.routes}
    assert "/data" in registered
    assert "/proto-files" in registered
    assert "/sessions-files/{path:path}" in registered
    assert client.get("/data/assets/ws-a-secret.txt").text == "asset a"
    assert client.get("/proto-files/shared-slug/index.html").status_code == 200
    assert client.get("/sessions-files/shared-session/step-0.png").status_code == 200


def test_two_postgres_workspaces_cannot_fetch_global_runtime_files(tmp_path, monkeypatch):
    _write_runtime_fixtures(tmp_path, monkeypatch)
    monkeypatch.setenv("DATABASE_URL", "postgresql://unused/tenant-test")
    monkeypatch.setenv("SONALOOP_PG_TENANT", "1")
    client = TestClient(web.create_app())
    registered = {getattr(route, "path", "") for route in client.app.routes}
    assert "/data" not in registered
    assert not any(path.startswith("/proto-files") for path in registered)
    assert not any(path.startswith("/sessions-files") for path in registered)
    private_paths = (
        "/data/sonaloop.db",
        "/data/settings.json",
        "/data/assets/ws-a-secret.txt",
        "/data/assets/ws-b-secret.txt",
        "/data/exports/ws-a-report.txt",
        "/proto-files/shared-slug/index.html",
        "/sessions-files/shared-session/step-0.png",
    )

    for workspace_id in ("ws_a", "ws_b"):
        token = config.set_request_tenant_scope([workspace_id], workspace_id)
        try:
            for path in private_paths:
                response = client.get(path)
                assert response.status_code == 404, (workspace_id, path, response.text)
                assert response.headers["Cache-Control"] == "no-store"
        finally:
            config.reset_request_tenant_scope(token)
