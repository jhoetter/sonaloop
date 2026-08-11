"""Workspace isolation for runtime files that live beside the RLS database rows."""
from __future__ import annotations

import base64
import copy
import json
from contextlib import contextmanager
from pathlib import Path

import pytest

from sonaloop import avatar, browser, config, prototypes, services
from sonaloop.services import _personas, _snapshots
from sonaloop.web import _components, _ext
from sonaloop.web.pages import sessions as session_pages


@contextmanager
def _tenant(workspace_id: str):
    token = config.set_request_tenant_scope([workspace_id], workspace_id)
    try:
        yield
    finally:
        config.reset_request_tenant_scope(token)


def _enable_row_tenancy(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://not-connected/runtime-file-test")
    monkeypatch.setenv("SONALOOP_PG_TENANT", "1")


def test_partition_dir_is_local_by_default_and_workspace_scoped_in_pg(tmp_path, monkeypatch):
    assert config.partition_dir() == config.DATA_DIR
    assert services.persona_dir({"slug": "same-persona"}) == config.DATA_DIR / "personas" / "same-persona"

    _enable_row_tenancy(monkeypatch)
    assert config.partition_dir() == config.DATA_DIR / "workspaces" / ".unbound"
    with _tenant("ws_alpha"):
        assert config.partition_dir() == config.DATA_DIR / "workspaces" / "ws_alpha"

    for unsafe in ("../ws_other", "ws_a/b", "ws_a\\b", "not-a-workspace", "ws_"):
        with _tenant(unsafe), pytest.raises(ValueError, match="unsafe active workspace id"):
            config.partition_dir()

    explicit = tmp_path / "legacy-partition"
    part_token = config.set_request_partition(explicit)
    tenant_token = config.set_request_tenant_scope(["../invalid"], "../invalid")
    try:
        assert config.partition_dir() == explicit  # explicit legacy partition always wins
    finally:
        config.reset_request_tenant_scope(tenant_token)
        config.reset_request_partition(part_token)


def test_identical_persona_slug_and_settings_do_not_collide(monkeypatch):
    _enable_row_tenancy(monkeypatch)
    persona = {"slug": "shared-persona"}

    with _tenant("ws_alpha"):
        alpha_dir = services.persona_dir(persona)
        alpha_dir.mkdir(parents=True)
        (alpha_dir / "SOUL.md").write_text("alpha soul", encoding="utf-8")
        (alpha_dir / "MEMORY.md").write_text("alpha memory", encoding="utf-8")
        config.set_setting("partition_marker", "alpha")

    with _tenant("ws_beta"):
        beta_dir = services.persona_dir(persona)
        beta_dir.mkdir(parents=True)
        (beta_dir / "SOUL.md").write_text("beta soul", encoding="utf-8")
        (beta_dir / "MEMORY.md").write_text("beta memory", encoding="utf-8")
        config.set_setting("partition_marker", "beta")

    assert alpha_dir != beta_dir
    with _tenant("ws_alpha"):
        assert services.soul_path(persona).read_text(encoding="utf-8") == "alpha soul"
        assert services.memory_path(persona).read_text(encoding="utf-8") == "alpha memory"
        assert config.get_setting("partition_marker") == "alpha"
    with _tenant("ws_beta"):
        assert services.soul_path(persona).read_text(encoding="utf-8") == "beta soul"
        assert services.memory_path(persona).read_text(encoding="utf-8") == "beta memory"
        assert config.get_setting("partition_marker") == "beta"


class _PersonaStore:
    def __init__(self, persona: dict):
        self.persona = copy.deepcopy(persona)

    def get_persona(self, _persona_id):
        return copy.deepcopy(self.persona)

    def upsert_persona(self, persona, reason=""):
        self.persona = copy.deepcopy(persona)


def _minimal_persona() -> dict:
    return {
        "id": "persona_shared",
        "slug": "shared-persona",
        "display_name": "Shared Persona",
        "source_description": "A grounded customer profile",
        "identity_traits": {"avatar_profile": {}},
        "role": {"title": "Customer"},
        "company_context": {"industry": "Banking", "size": "100", "operating_model": "team"},
        "personality": {"working_style": "pragmatic", "communication_style": "direct",
                        "risk_tolerance": "medium"},
        "tools": ["Email"],
        "tool_ids": ["e_mail"],
        "relationships": [],
        "success_criteria": ["clarity"],
        "pain_points": ["waiting"],
        "goals": ["finish the task"],
    }


def test_stale_soul_ref_cannot_read_another_workspace(monkeypatch):
    _enable_row_tenancy(monkeypatch)
    persona = _minimal_persona()
    persona["soul"] = {
        "path": "data/workspaces/ws_beta/personas/shared-persona/SOUL.md",
        "updated_at": "old",
    }
    beta_secret = config.DATA_DIR / "workspaces" / "ws_beta" / "personas" / "shared-persona" / "SOUL.md"
    beta_secret.parent.mkdir(parents=True)
    beta_secret.write_text("beta secret", encoding="utf-8")
    store = _PersonaStore(persona)
    monkeypatch.setattr(_personas, "render_soul", lambda *_args, **_kwargs: "alpha canonical")

    with _tenant("ws_alpha"):
        result = services.get_persona_soul(persona["id"], store=store)
        canonical = services.soul_path(persona)

    assert result["content"] == "alpha canonical"
    assert canonical.read_text(encoding="utf-8") == "alpha canonical"
    assert beta_secret.read_text(encoding="utf-8") == "beta secret"
    assert "workspaces/ws_alpha/" in result["path"]


def test_identical_avatar_ref_resolves_to_each_workspace(monkeypatch):
    _enable_row_tenancy(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.delenv("AVATAR_OUTPUT_DIR", raising=False)
    payloads = [b"alpha avatar", b"beta avatar"]

    def _image(*_args, **_kwargs):
        return {"data": [{"b64_json": base64.b64encode(payloads.pop(0)).decode("ascii")}]}

    monkeypatch.setattr(avatar, "_post_json", _image)
    alpha_store = _PersonaStore(_minimal_persona())
    beta_store = _PersonaStore(_minimal_persona())

    with _tenant("ws_alpha"):
        alpha = avatar.generate_persona_avatar("persona_shared", store=alpha_store)
        alpha_path = _snapshots._avatar_disk_path(alpha["path"])
    with _tenant("ws_beta"):
        beta = avatar.generate_persona_avatar("persona_shared", store=beta_store)
        beta_path = _snapshots._avatar_disk_path(beta["path"])

    assert alpha["path"] == beta["path"]  # virtual record is portable and tenant-neutral
    assert alpha_path != beta_path
    assert alpha_path.read_bytes() == b"alpha avatar"
    assert beta_path.read_bytes() == b"beta avatar"


def test_avatar_content_reads_only_the_active_workspace(monkeypatch):
    _enable_row_tenancy(monkeypatch)
    persona = _minimal_persona()
    persona["avatar"] = {"path": "data/avatars/shared.png"}
    store = _PersonaStore(persona)
    payloads = {
        "ws_alpha": b"\x89PNG\r\n\x1a\nalpha",
        "ws_beta": b"\x89PNG\r\n\x1a\nbeta",
    }
    for workspace_id, payload in payloads.items():
        with _tenant(workspace_id):
            target = config.partition_dir() / "avatars" / "shared.png"
            target.parent.mkdir(parents=True)
            target.write_bytes(payload)

    for workspace_id, payload in payloads.items():
        with _tenant(workspace_id):
            data, record = avatar.get_persona_avatar_content(persona["id"], store=store)
            assert data == payload
            assert record["id"] == persona["id"]

    store.persona["avatar"] = {"path": "data/avatars/../shared.png"}
    with _tenant("ws_alpha"), pytest.raises(ValueError, match="unsafe tenant avatar path"):
        avatar.get_persona_avatar_content(persona["id"], store=store)


class _PrototypeStore:
    def __init__(self):
        self.rows: dict[str, dict] = {}

    def get_prototype(self, key):
        row = next((p for p in self.rows.values() if key in (p["id"], p["slug"])), None)
        return copy.deepcopy(row) if row else None

    def upsert_prototype(self, record):
        self.rows[record["id"]] = copy.deepcopy(record)


def test_identical_prototype_slug_isolated_and_cross_path_rejected(monkeypatch):
    _enable_row_tenancy(monkeypatch)
    # Production imports the editable research checkout (pyproject present); row
    # tenancy must still outrank the local developer ROOT/prototypes convention.
    monkeypatch.setattr(config, "_is_source_checkout", lambda: True)
    monkeypatch.setattr(prototypes, "_render_spa", lambda _name, concept, _template: concept["summary"])

    def _concept(marker: str) -> dict:
        return {"title": "Shared", "summary": marker,
                "screens": [{"id": "start", "elements": [
                    {"id": "copy", "kind": "text", "text": marker}]}]}

    with _tenant("ws_alpha"):
        alpha = prototypes.scaffold_prototype(
            "shared-prototype", "Shared", _concept("alpha"), store=_PrototypeStore())
        alpha_dir = prototypes._prototype_app_dir(alpha)
    with _tenant("ws_beta"):
        beta = prototypes.scaffold_prototype(
            "shared-prototype", "Shared", _concept("beta"), store=_PrototypeStore())
        beta_dir = prototypes._prototype_app_dir(beta)
        with pytest.raises(prototypes.PrototypeError) as exc:
            prototypes._prototype_app_dir(alpha)
        assert exc.value.code == "BAD_PATH"

    assert alpha_dir != beta_dir
    assert (alpha_dir / "index.html").read_text(encoding="utf-8") == "alpha"
    assert (beta_dir / "index.html").read_text(encoding="utf-8") == "beta"


def test_tenant_prototype_runner_is_static_only_and_legacy_rows_cannot_execute(monkeypatch):
    _enable_row_tenancy(monkeypatch)
    monkeypatch.setattr(config, "_is_source_checkout", lambda: True)
    store = _PrototypeStore()
    popen_calls = []

    class _Proc:
        pid = 4242

        def terminate(self):
            return None

        def wait(self, timeout=None):
            return None

        def kill(self):
            return None

    monkeypatch.setattr(prototypes.subprocess, "Popen",
                        lambda *args, **kwargs: popen_calls.append((args, kwargs)) or _Proc())

    with _tenant("ws_alpha"):
        app_dir = config.prototypes_dir() / "safe-static"
        app_dir.mkdir(parents=True)
        (app_dir / "index.html").write_text("<h1>safe</h1>", encoding="utf-8")
        with pytest.raises(prototypes.PrototypeError) as exc:
            prototypes.register_prototype(
                "unsafe-server", "Unsafe", str(app_dir), run="server",
                run_cmd="python app.py", store=store)
        assert exc.value.code == "UNSAFE_RUNNER"
        with pytest.raises(prototypes.PrototypeError) as exc:
            prototypes.register_prototype(
                "unsafe-command", "Unsafe", str(app_dir), run="static",
                run_cmd="touch /tmp/no", store=store)
        assert exc.value.code == "UNSAFE_RUNNER"

        normal = prototypes.register_prototype(
            "safe-static", "Safe", str(app_dir), run="static", store=store)
        try:
            result = prototypes.run_prototype(normal["id"], store=store)
            assert result["pid"] == 4242
            assert len(popen_calls) == 1
            assert popen_calls[0][1].get("shell") is None
        finally:
            prototypes.stop_prototype(normal["id"], store=store)

        legacy = dict(normal, id="proto_legacy_exec", slug="legacy-exec",
                      run="server", run_cmd="touch /tmp/no")
        store.rows[legacy["id"]] = legacy
        calls_before = len(popen_calls)
        with pytest.raises(prototypes.PrototypeError) as exc:
            prototypes.run_prototype(legacy["id"], store=store)
        assert exc.value.code == "UNSAFE_RUNNER"
        assert len(popen_calls) == calls_before


class _SnapshotStore:
    def __init__(self, marker: str):
        self.marker = marker

    def list_personas(self):
        return []

    def list_world_context(self):
        return [{"marker": self.marker}]

    def list_council_sessions(self):
        return []

    def list_syntheses(self):
        return []

    def list_research_projects(self):
        return []

    def schema_version(self):
        return 1

    def embedding_models(self):
        return []

    def commit(self):
        return None


def test_default_snapshots_and_purge_are_workspace_scoped(monkeypatch):
    _enable_row_tenancy(monkeypatch)
    with _tenant("ws_alpha"):
        alpha_out = services.export_snapshot(store=_SnapshotStore("alpha"))
        alpha_manifest = config.partition_dir() / "export" / "world_context.json"
        (config.partition_dir() / "personas" / "same").mkdir(parents=True)
        (config.partition_dir() / "personas" / "same" / "SOUL.md").write_text("alpha")
        (config.partition_dir() / "avatars").mkdir()
        (config.partition_dir() / "avatars" / "same.png").write_bytes(b"alpha")
    with _tenant("ws_beta"):
        beta_out = services.export_snapshot(store=_SnapshotStore("beta"))
        beta_manifest = config.partition_dir() / "export" / "world_context.json"
        (config.partition_dir() / "personas" / "same").mkdir(parents=True)
        beta_soul = config.partition_dir() / "personas" / "same" / "SOUL.md"
        beta_soul.write_text("beta")

    assert alpha_out["out_dir"] != beta_out["out_dir"]
    assert json.loads(alpha_manifest.read_text())[0]["marker"] == "alpha"
    assert json.loads(beta_manifest.read_text())[0]["marker"] == "beta"

    class _PurgeStore:
        def purge_runtime_state(self):
            return {"rows": 0}

    with _tenant("ws_alpha"):
        services.purge_runtime_data(store=_PurgeStore())
    assert not (config.DATA_DIR / "workspaces" / "ws_alpha" / "personas").exists()
    assert beta_soul.read_text() == "beta"


def test_runtime_slugs_and_tenant_export_paths_fail_closed(tmp_path, monkeypatch):
    with pytest.raises(ValueError, match="unsafe persona slug"):
        services.persona_dir({"slug": "../escape"})

    _enable_row_tenancy(monkeypatch)
    with _tenant("ws_alpha"):
        with pytest.raises(prototypes.PrototypeError) as exc:
            prototypes.register_prototype("../escape", "Bad", ".", store=_PrototypeStore())
        assert exc.value.code == "BAD_SLUG"
        with pytest.raises(ValueError, match="escapes the active workspace partition"):
            services.write_export("secret", tmp_path / "outside.md")
        outside = tmp_path / "another-workspace.txt"
        outside.write_text("private material long enough to become a corpus chunk")
        with pytest.raises(ValueError, match="corpus file path must stay inside"):
            services.ingest_corpus(str(outside), "interview", store=object())

        class _AssetStore:
            def get_research_project(self, _project_id):
                return {"id": "project_a", "assets": []}

        with pytest.raises(ValueError, match="asset path must stay inside"):
            services.attach_asset("project_a", path=str(outside), store=_AssetStore())


def test_browser_live_and_retained_state_is_workspace_scoped(monkeypatch):
    _enable_row_tenancy(monkeypatch)
    monkeypatch.setattr(browser, "_SESSIONS", {})
    monkeypatch.setattr(browser, "_RETAINED_LOGS", {})

    class _Live:
        def __init__(self, namespace: str, marker: str):
            self.runtime_namespace = namespace
            self.session_id = "shared-session"
            self.url = f"https://{marker}.example.test"
            self.prototype_id = "shared-prototype"
            self.persona_id = "shared-persona"
            self.log = [{"marker": marker}]
            self.marker = marker

        def send(self, _command, _payload=None):
            return {"marker": self.marker}

    with _tenant("ws_alpha"):
        alpha_ns = browser._runtime_namespace()
        alpha = _Live(alpha_ns, "alpha")
        browser._SESSIONS[browser._session_key(alpha.session_id, alpha_ns)] = alpha
        browser._retain_log("closed-session", [{"marker": "alpha"}], alpha_ns)
    with _tenant("ws_beta"):
        beta_ns = browser._runtime_namespace()
        beta = _Live(beta_ns, "beta")
        browser._SESSIONS[browser._session_key(beta.session_id, beta_ns)] = beta
        browser._retain_log("closed-session", [{"marker": "beta"}], beta_ns)

    with _tenant("ws_alpha"):
        assert [s["url"] for s in browser.list_sessions()] == ["https://alpha.example.test"]
        assert browser.read("shared-session")["snapshot"]["marker"] == "alpha"
        assert browser.session_log("closed-session") == [{"marker": "alpha"}]
    with _tenant("ws_beta"):
        assert [s["url"] for s in browser.list_sessions()] == ["https://beta.example.test"]
        assert browser.read("shared-session")["snapshot"]["marker"] == "beta"
        assert browser.session_log("closed-session") == [{"marker": "beta"}]
    with _tenant("ws_gamma"):
        assert browser.list_sessions() == []
        assert browser.session_log("closed-session") is None
        with pytest.raises(browser.HarnessError) as exc:
            browser.read("shared-session")
        assert exc.value.code == "SESSION_NOT_FOUND"


def test_browser_worker_uses_captured_workspace_screenshot_root(monkeypatch):
    _enable_row_tenancy(monkeypatch)

    class _Page:
        def __init__(self, payload: bytes):
            self.payload = payload

        def screenshot(self, path: str):
            Path(path).write_bytes(self.payload)

    sessions = []
    for workspace_id, marker in (("ws_alpha", b"alpha"), ("ws_beta", b"beta")):
        with _tenant(workspace_id):
            root = config.sessions_dir()
            session = browser._Session(
                "same-session", "http://127.0.0.1", None, None,
                runtime_namespace=browser._runtime_namespace(), screenshots_root=root)
            session._page = _Page(marker)
            assert session._screenshot() == "same-session/step-0.png"
            sessions.append((root, marker))

    assert sessions[0][0] != sessions[1][0]
    for root, marker in sessions:
        assert (root / "same-session" / "step-0.png").read_bytes() == marker


def test_browser_dictionary_keys_stay_flat_in_sqlite(monkeypatch):
    monkeypatch.setattr(browser, "_RETAINED_LOGS", {})
    browser._retain_log("local-session", [{"marker": "local"}])
    assert browser._RETAINED_LOGS == {"local-session": [{"marker": "local"}]}
    assert browser.session_log("local-session") == [{"marker": "local"}]


def test_shared_web_renderers_do_not_probe_or_reference_runtime_files(monkeypatch):
    _enable_row_tenancy(monkeypatch)
    global_shot = config.DATA_DIR / "sessions" / "foreign" / "step-0.png"
    global_logo = config.DATA_DIR / "brand" / "foreign.png"
    global_shot.parent.mkdir(parents=True, exist_ok=True)
    global_logo.parent.mkdir(parents=True, exist_ok=True)
    global_shot.write_bytes(b"foreign screenshot")
    global_logo.write_bytes(b"foreign logo")

    with _tenant("ws_alpha"):
        assert session_pages._screenshot_url("foreign", str(global_shot)) is None
        token = _ext.set_runtime_brand("Alpha", str(global_logo))
        try:
            assert _components._brand_logo_img("Alpha") == ""
        finally:
            _ext.reset_runtime_brand(token)

        token = _ext.set_runtime_brand("Alpha", "data:image/png;base64,YWxwaGE=")
        try:
            assert "data:image/png;base64,YWxwaGE=" in _components._brand_logo_img("Alpha")
        finally:
            _ext.reset_runtime_brand(token)

        token = _ext.set_runtime_brand(
            "Alpha",
            "data:image/png;base64,bGlnaHQ=",
            "data:image/png;base64,ZGFyaw==",
        )
        try:
            lockup = str(_components._brand_logo_img("Alpha"))
            assert "sl-logo__img--light" in lockup
            assert "sl-logo__img--dark" in lockup
            assert "data:image/png;base64,bGlnaHQ=" in lockup
            assert "data:image/png;base64,ZGFyaw==" in lockup
        finally:
            _ext.reset_runtime_brand(token)
