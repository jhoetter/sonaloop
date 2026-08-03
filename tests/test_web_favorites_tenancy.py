"""Favorites are browser-local, but their bucket must follow the server data boundary."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.testclient import TestClient

from sonaloop import config
from sonaloop.web._components import _layout


def _enable_row_tenancy(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://favorites-test.invalid/sonaloop")
    monkeypatch.setenv("SONALOOP_PG_TENANT", "1")


def _render_for_workspace(store, workspace_id: str) -> str:
    token = config.set_request_tenant_scope([workspace_id], workspace_id)
    try:
        return _layout("Favorites", "<p>body</p>", store)
    finally:
        config.reset_request_tenant_scope(token)


def test_row_tenancy_renders_a_distinct_favorites_key_per_active_workspace(
        store, monkeypatch):
    _enable_row_tenancy(monkeypatch)

    personal = _render_for_workspace(store, "ws_personal.1")
    customer = _render_for_workspace(store, "ws_customer-2")

    assert 'var SK="pc-stars:ws_personal.1"' in personal
    assert 'var SK="pc-stars:ws_customer-2"' in customer
    assert 'var SK="pc-stars:ws_customer-2"' not in personal
    assert 'var SK="pc-stars:ws_personal.1"' not in customer
    # A tenant render must never read or seed itself from the legacy bucket.
    assert 'var SK="pc-stars",' not in personal
    assert 'var SK="pc-stars",' not in customer


def test_async_middleware_scope_reaches_a_sync_page_renderer(store, monkeypatch):
    """Starlette copies request context into its sync-endpoint worker thread.

    This guards the production middleware shape, rather than only calling the
    renderer directly: a valid active scope must survive ``call_next`` and the
    async-to-sync boundary intact.
    """
    _enable_row_tenancy(monkeypatch)
    app = FastAPI()

    @app.middleware("http")
    async def bind_workspace(_request, call_next):
        token = config.set_request_tenant_scope(["ws_threaded"], "ws_threaded")
        try:
            return await call_next(_request)
        finally:
            config.reset_request_tenant_scope(token)

    @app.get("/")
    def sync_page():
        return HTMLResponse(_layout("Favorites", "<p>body</p>", store))

    response = TestClient(app).get("/")

    assert response.status_code == 200
    assert 'var SK="pc-stars:ws_threaded"' in response.text


def test_row_tenant_without_a_workspace_disables_favorites(store, monkeypatch):
    """A valid unaffiliated session is empty data scope, not a server error."""
    _enable_row_tenancy(monkeypatch)
    token = config.set_request_tenant_scope([], "")
    try:
        page = _layout("Favorites", "<p>body</p>", store)
    finally:
        config.reset_request_tenant_scope(token)

    assert "var SK=null" in page
    assert "function readStars(){ if(!SK) return {};" in page
    assert "localStorage.getItem(null)" not in page


def test_local_sqlite_mode_preserves_the_legacy_favorites_key(store):
    # Even an incidental request scope is ignored outside shared-Postgres mode.
    token = config.set_request_tenant_scope(["ws_ignored"], "ws_ignored")
    try:
        page = _layout("Favorites", "<p>body</p>", store)
    finally:
        config.reset_request_tenant_scope(token)

    assert 'var SK="pc-stars"' in page
    assert "pc-stars:ws_ignored" not in page


@pytest.mark.parametrize(
    ("accessible", "active", "error"),
    [
        (["ws_allowed"], "ws_other", PermissionError),
        (["ws_allowed"], "", PermissionError),
        ([], "ws_other", PermissionError),
        (["ws_bad</script>"], "ws_bad</script>", ValueError),
    ],
)
def test_row_tenant_favorites_key_fails_closed_for_unvalidated_scope(
        store, monkeypatch, accessible, active, error):
    _enable_row_tenancy(monkeypatch)
    token = config.set_request_tenant_scope(accessible, active)
    try:
        with pytest.raises(error):
            _layout("Favorites", "<p>body</p>", store)
    finally:
        config.reset_request_tenant_scope(token)


def test_row_tenant_favorites_key_fails_closed_without_request_scope(store, monkeypatch):
    _enable_row_tenancy(monkeypatch)

    with pytest.raises(RuntimeError, match="request tenant scope"):
        _layout("Favorites", "<p>body</p>", store)
