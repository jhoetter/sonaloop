"""M2 — prototype generation + local runner."""
from __future__ import annotations

import time
import urllib.request

from sonaloop import prototypes
from sonaloop.theming import (
    SPEC_VERSION,
    reset_runtime_design_system_context,
    runtime_design_system_context,
    set_runtime_design_system_context,
)


_CONCEPT = {
    "title": "Übergabe-Check",
    "summary": "Was hat sich geändert?",
    "start": "home",
    "screens": [
        {"id": "home", "title": "Start", "elements": [
            {"kind": "text", "id": "t1", "label": "Lade zwei Stände und vergleiche."},
            {"kind": "button", "id": "go", "label": "Vergleichen", "goto": "result"}]},
        {"id": "result", "title": "Ergebnis", "elements": [
            {"kind": "text", "id": "t2", "label": "W-12 (tragende Wand) entfernt."},
            {"kind": "input", "id": "note", "label": "Notiz"},
            {"kind": "button", "id": "proto", "label": "Protokoll erzeugen"}]},
    ],
}


def _design_system() -> dict:
    return {
        "spec_version": SPEC_VERSION,
        "brand": {
            "name": "Acme Research",
            "short_name": "Acme",
            "logo_variants": {
                "lockup": {"kind": "image", "src": "data:image/png;base64,iVBORw0KGgo="},
            },
            "logo_preferred": "lockup",
        },
        "colors": {
            "light": {"paper": "#fffdf8", "accent": "#007a5a"},
            "dark": {"paper": "#101113", "accent": "#62d6b0"},
        },
        "typography": {
            "fonts": {
                "sans": {
                    "family": "Acme Sans",
                    "stack": ["Acme Sans", "Sona", "system-ui", "sans-serif"],
                },
            },
        },
        "layout": {"radius": {"radius": "10px"}},
    }


def test_scaffold_creates_runnable_app(store, tmp_path, monkeypatch):
    # write generated app under a temp prototypes dir to keep the repo clean
    monkeypatch.setattr(prototypes, "prototypes_dir", lambda: tmp_path)
    rec = prototypes.scaffold_prototype("ueberg-test", "Übergabe-Check", _CONCEPT, store=store)
    assert rec["run"] == "static" and rec["entry"] == "index.html"
    html = (tmp_path / "ueberg-test" / "index.html").read_text(encoding="utf-8")
    assert "Vergleichen" in html and "concept" in html
    assert 'id="sonaloop-design-system"' in html
    assert "--sl-accent:#5e6ad2" in html
    assert "--ff:Sona,Geist,Inter,system-ui,sans-serif" in html
    assert store.get_prototype("ueberg-test")["id"] == rec["id"]


def test_scaffold_uses_active_workspace_design_system_context(store, tmp_path, monkeypatch):
    monkeypatch.setattr(prototypes, "prototypes_dir", lambda: tmp_path)
    ctx = runtime_design_system_context(
        _design_system(), workspace_id="ws_acme", version_id="dsv_1", surface="prototype")
    token = set_runtime_design_system_context(ctx)
    try:
        concept = {**_CONCEPT, "show_brand": True}
        prototypes.scaffold_prototype("ueberg-themed", "Übergabe-Check", concept, store=store)
    finally:
        reset_runtime_design_system_context(token)

    html = (tmp_path / "ueberg-themed" / "index.html").read_text(encoding="utf-8")
    assert '"workspace_id": "ws_acme"' in html
    assert "--accent:#007a5a" in html
    assert "--ff:\"Acme Sans\",Sona,system-ui,sans-serif" in html
    assert 'class="sl-prototype-brand"' in html
    assert 'src="data:image/png;base64,iVBORw0KGgo="' in html


def test_scaffold_canvas_accepts_freeform_frames(store, tmp_path, monkeypatch):
    monkeypatch.setattr(prototypes, "prototypes_dir", lambda: tmp_path)
    concept = {
        "title": "Dispatch Room",
        "summary": "A spatial dispatch prototype rather than a form flow.",
        "start": "ops",
        "frames": [
            {
                "id": "ops",
                "title": "Live dispatch",
                "layout": "map",
                "layers": [
                    {"kind": "map", "id": "route_map", "x": 3, "y": 16, "w": 62, "h": 68,
                     "pins": [
                         {"id": "pickup", "title": "Pickup", "x": 20, "y": 62},
                         {"id": "dropoff", "title": "Daycare", "x": 76, "y": 28},
                     ],
                     "routes": [{"from": "pickup", "to": "dropoff"}]},
                    {"kind": "metric", "id": "eta", "title": "ETA", "value": "11 min",
                     "x": 68, "y": 16, "w": 24, "h": 14},
                    {"kind": "timeline", "id": "handover", "title": "Handover",
                     "x": 68, "y": 34, "w": 26, "h": 34,
                     "items": [{"title": "Harness photo"}, {"title": "Driver arrived"}]},
                    {"kind": "hotspot", "id": "open_detail", "title": "Open care desk",
                     "x": 68, "y": 74, "w": 24, "h": 10, "goto": "care"},
                ],
            },
            {"id": "care", "title": "Care desk", "layers": [
                {"kind": "panel", "id": "notes", "title": "Care notes", "body": "Nervous dog, use ramp."}
            ]},
        ],
    }
    rec = prototypes.scaffold_artifact("dispatch-room", "Dispatch Room", concept,
                                       type="canvas", store=store)
    assert rec["type"] == "canvas"
    html = (tmp_path / "dispatch-room" / "index.html").read_text(encoding="utf-8")
    assert "spa-freeform" not in html  # rendered output, not a template placeholder
    assert "route_map" in html and "Care notes" in html
    assert store.get_prototype("dispatch-room")["type"] == "canvas"


def test_canvas_rejects_dead_navigation(store, tmp_path, monkeypatch):
    monkeypatch.setattr(prototypes, "prototypes_dir", lambda: tmp_path)
    concept = {
        "title": "Dead nav",
        "frames": [
            {"id": "home", "layers": [
                {"kind": "hotspot", "id": "bad", "title": "Broken", "goto": "missing"}
            ]}
        ],
    }
    try:
        prototypes.scaffold_artifact("dead-nav", "Dead nav", concept, type="canvas", store=store)
    except prototypes.PrototypeError as exc:
        assert exc.code == "BAD_CONCEPT"
        assert "missing" in exc.message
    else:
        raise AssertionError("dead freeform navigation should be rejected")


def test_run_prototype_serves_locally(store, tmp_path, monkeypatch):
    monkeypatch.setattr(prototypes, "prototypes_dir", lambda: tmp_path)
    prototypes.scaffold_prototype("ueberg-run", "Übergabe-Check", _CONCEPT, store=store)
    info = prototypes.run_prototype("ueberg-run", store=store)
    try:
        assert info["url"].startswith("http://127.0.0.1:")
        body = None
        for _ in range(20):
            try:
                body = urllib.request.urlopen(info["url"], timeout=2).read().decode("utf-8")
                break
            except Exception:
                time.sleep(0.1)
        assert body is not None and "Vergleichen" in body
    finally:
        prototypes.stop_prototype("ueberg-run", store=store)
