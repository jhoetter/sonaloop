"""The public façade sonaloop-cloud / sonaloop-research consume must stay stable.

These products are out-of-tree, so a rename of a re-exported name would only surface
as a runtime ImportError in the paying surfaces. This test pins the contract here, in
the core suite, so a breaking change fails loudly where it is made (audit cleanup #5).
"""

from __future__ import annotations

import importlib


def test_design_facade_exposes_the_vendored_assets():
    design = importlib.import_module("sonaloop.design")
    for name in (
        "icon", "hifi", "figure", "names", "hifi_names", "figure_names",
        "TOKENS_CSS", "COMPONENTS_CSS", "PIXEL_FONT_CSS", "STANDALONE_CSS",
    ):
        assert hasattr(design, name), f"sonaloop.design lost public name: {name}"
    # STANDALONE_CSS is the concatenation a standalone page needs.
    assert design.STANDALONE_CSS == design.PIXEL_FONT_CSS + design.TOKENS_CSS + design.COMPONENTS_CSS
    assert callable(design.icon) and "<svg" in design.icon("sonaloop")


def test_sessions_facade_round_trips(monkeypatch):
    monkeypatch.setenv("SONALOOP_CLOUD_SECRET", "test-secret-please-ignore")
    sessions = importlib.import_module("sonaloop.sessions")
    token = sessions.sign_session({"sub": "u1", "email": "a@b.c"}, ttl_s=60)
    payload = sessions.verify_session(token)
    assert payload is not None and payload["sub"] == "u1" and payload["email"] == "a@b.c"
    # tamper / garbage / empty all verify to None (anonymous), never raise.
    assert sessions.verify_session(token + "x") is None
    assert sessions.verify_session("not-a-token") is None
    assert sessions.verify_session("") is None


def test_sessions_expiry(monkeypatch):
    monkeypatch.setenv("SONALOOP_CLOUD_SECRET", "test-secret-please-ignore")
    sessions = importlib.import_module("sonaloop.sessions")
    assert sessions.verify_session(sessions.sign_session({"sub": "u1"}, ttl_s=-1)) is None


def test_platform_facades_are_importable():
    # mcp tool envelope + catalogue, storage backend seam, deck preview — the exact
    # public names sonaloop-cloud / sonaloop-research import.
    mcp = importlib.import_module("sonaloop.mcp_server")
    assert callable(mcp.tool_response) and callable(mcp.catalogue_data)
    assert isinstance(mcp.SERVER_VERSION, str)
    storage = importlib.import_module("sonaloop.storage")
    assert callable(storage.port_sqlite_schema_to_postgres) and hasattr(storage, "PgConnection")
    services = importlib.import_module("sonaloop.services")
    assert callable(services.set_request_catalog_token)
    assert callable(services.reset_request_catalog_token)
    presentation = importlib.import_module("sonaloop.presentation")
    assert callable(presentation.render_first_slide)
