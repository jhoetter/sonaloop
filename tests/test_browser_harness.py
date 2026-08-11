"""M3 — Playwright harness: a persona-agent drives the REAL running app.

Live when chromium is installed; otherwise asserts graceful PLAYWRIGHT_UNAVAILABLE
(per spec: harness tests skip the live path when chromium is absent).
"""
from __future__ import annotations

import pytest

from sonaloop import browser, prototypes, services


_CONCEPT = {
    "title": "Übergabe-Check", "summary": "Was hat sich geändert?", "start": "home",
    "screens": [
        {"id": "home", "title": "Start", "elements": [
            {"kind": "button", "id": "go", "label": "Vergleichen", "goto": "result"}]},
        {"id": "result", "title": "Ergebnis", "elements": [
            {"kind": "text", "id": "t2", "label": "W-12 (tragende Wand) entfernt."}]},
    ],
}


def _proto(store, tmp_path, monkeypatch, slug):
    monkeypatch.setattr(prototypes, "prototypes_dir", lambda: tmp_path)
    # every snapshot now writes a per-step screenshot under DATA_DIR/sessions — keep it hermetic
    from sonaloop import config
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    return prototypes.scaffold_prototype(slug, "Übergabe-Check", _CONCEPT, store=store)


def test_unavailable_is_graceful(store, tmp_path, monkeypatch):
    if browser.available():
        pytest.skip("playwright present; covered by the live test")
    with pytest.raises(browser.HarnessError) as e:
        browser.open_session("http://127.0.0.1:1/x")
    assert e.value.code == "PLAYWRIGHT_UNAVAILABLE"


@pytest.mark.skipif(not browser.available(), reason="chromium not installed")
def test_agent_drives_real_app(store, tmp_path, monkeypatch):
    _proto(store, tmp_path, monkeypatch, "harness-live")
    info = prototypes.run_prototype("harness-live", store=store)
    try:
        opened = browser.open_session(info["url"], prototype_id="harness-live")
        sid = opened["session_id"]
        # the start screen exposes the "Vergleichen" button with a ref
        refs = _refs(opened["snapshot"])
        go = next(r for r, spec in refs.items() if "Vergleichen" in spec["name"])
        out = browser.act(sid, {"type": "click", "ref": go})
        # clicking navigated to the result screen -> real observed state change
        assert "W-12" in out["snapshot"]["text"]
        # a stale/fabricated ref is rejected
        with pytest.raises(browser.HarnessError) as e:
            browser.act(sid, {"type": "click", "ref": "e999"})
        assert e.value.code == "STALE_REF"
        # groundedness: a reaction citing a real observed state is accepted...
        res = services.record_prototype_session(
            "pX", "harness-live", sid, "2026-06-03",
            {"summary": "tried it", "liked": ["catches W-12"], "observed_state_refs": ["W-12"]}, store=store)
        assert res["grounded_verified"] is True
        # ...one citing a never-seen state is rejected
        with pytest.raises(ValueError):
            services.record_prototype_session(
                "pX", "harness-live", sid, "2026-06-03",
                {"summary": "x", "observed_state_refs": ["NONEXISTENT-STATE-XYZ"]}, store=store)
    finally:
        try:
            browser.close(opened["session_id"])
        except Exception:
            pass
        prototypes.stop_prototype("harness-live", store=store)


def _refs(snapshot):
    tree = snapshot["tree"]
    nodes = tree if isinstance(tree, list) else [tree]
    return {n["ref"]: {"role": n["role"], "name": n["name"]} for n in nodes if n.get("ref")}


@pytest.mark.skipif(not browser.available(), reason="chromium not installed")
def test_proto_drive_one_process_grounded(store, tmp_path, monkeypatch):
    """proto_drive: the whole proband session (open → actions → read → close → record) in one
    call — the CLI-safe path, since sessions + retained logs are process-memory only."""
    _proto(store, tmp_path, monkeypatch, "harness-drive")
    try:
        out = services.proto_drive(
            "harness-drive", persona_id="pX",
            actions=[],                                   # open already shows the start screen
            reaction={"summary": "saw the start screen", "liked": ["Vergleichen button"],
                      "observed_state_refs": ["Vergleichen"]},
            date_value="2026-06-10", store=store)
        assert out["session_id"].startswith("psession_")
        assert out["final"] and out["recorded"]["grounded_verified"] is True
        # the session is closed (no live sessions remain)
        assert services.list_proto_sessions() == []
    finally:
        prototypes.stop_prototype("harness-drive", store=store)


@pytest.mark.skipif(not browser.available(), reason="chromium not installed")
def test_proto_drive_forwards_governed_dispatch_token(store, tmp_path, monkeypatch):
    """The CLI-safe one-process path must also be usable inside dispatch_v1 runs."""
    from sonaloop import plan as plan_mod

    proto = _proto(store, tmp_path, monkeypatch, "harness-drive-governed")
    project = services.start_project("Governed", "hmw?", None, persona_ids=["pX"],
                                     operation_id="governed-drive-project", store=store)
    project["governance_contract"] = "dispatch_v1"
    store.upsert_research_project(project)
    proto["project_id"] = project["id"]
    store.upsert_prototype(proto)
    task = {"id": "act__test", "bucket": "act", "capability": "test", "title": "Test",
            "status": "ready", "consumes": [], "produces": [], "requires": {"min_inputs": 0}}
    plan_mod.save_plan({"project_id": project["id"], "goal": "hmw?", "tasks": [task]}, store=store)
    run = services.start_run(project["id"], operation_id="governed-drive-run", store=store)
    dispatch = services.run_step(run["run_id"], store=store)
    try:
        out = services.proto_drive(
            proto["id"], persona_id="pX", actions=[],
            reaction={"summary": "saw the start screen", "observed_state_refs": ["Vergleichen"]},
            date_value="2026-06-10", dispatch_token=dispatch["dispatch_token"], store=store,
        )
        assert out["recorded"]["grounded_verified"] is True
        saved = store.get_prototype_session(out["recorded"]["id"])
        assert saved["dispatch_provenance"]["dispatch_token"] == dispatch["dispatch_token"]
    finally:
        prototypes.stop_prototype("harness-drive-governed", store=store)


def test_proto_drive_unavailable_is_graceful(store, tmp_path, monkeypatch):
    if browser.available():
        pytest.skip("playwright present; covered by the live test")
    _proto(store, tmp_path, monkeypatch, "harness-drive-na")
    with pytest.raises(browser.HarnessError):
        services.proto_drive("harness-drive-na", actions=[], store=store)
