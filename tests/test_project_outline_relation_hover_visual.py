"""Browser regression for project-outline relation hover geometry.

The relation rail is intentionally lightweight, but it must still dock to the same row
anchors users see: the leading primitive icons. Static HTML tests can prove the edges exist;
this browser test proves the rendered paths attach to the correct rows and do not require
offsetting the whole list to make room.
"""
from __future__ import annotations

import socket
import threading
import time

import pytest

from sonaloop import browser, services, web


def _start_app() -> tuple[object, threading.Thread, int]:
    import uvicorn

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(web.create_app(), host="127.0.0.1", port=port,
                                           log_level="error"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 15
    while not server.started:
        assert time.time() < deadline, "app did not boot"
        time.sleep(0.05)
    return server, thread, port


@pytest.mark.skipif(not browser.available(), reason="chromium not installed")
def test_outline_relation_hover_paths_dock_to_row_icons(store):
    project = services.start_project("Relation hover", "How might we prove value?",
                                     methodology="double_diamond", store=store)
    council = services.record_council(project["id"], "What matters?", [], store=store)
    synthesis = services.record_synthesis("Evidence summary", "What matters?",
                                           council_ids=[council["id"]],
                                           project_id=project["id"], store=store)
    decision = services.record_decision(
        project["id"], "Use the evidence", "Proceed from the report.",
        based_on=[{"kind": "synthesis", "id": synthesis["id"]}],
        status="adopted", store=store,
    )["decision"]

    server, thread, port = _start_app()
    from playwright.sync_api import sync_playwright
    try:
        with sync_playwright() as pw:
            b = pw.chromium.launch()
            pg = b.new_context(viewport={"width": 1440, "height": 900}).new_page()
            pg.goto(f"http://127.0.0.1:{port}/projects/{project['id']}?lang=en",
                    wait_until="load")
            pg.wait_for_timeout(300)
            result = pg.evaluate(
                """({councilId, synthesisId, decisionId}) => {
                  const outline = document.querySelector('.outline[data-relgraph]');
                  const row = id => outline.querySelector(`[data-oid="${id}"]`);
                  const parse = d => {
                    const n = (d.match(/-?\\d+(?:\\.\\d+)?/g) || []).map(Number);
                    return {sx:n[0], sy:n[1], ex:n[6], ey:n[7]};
                  };
                  const anchor = r => {
                    const a = outline.getBoundingClientRect();
                    const ico = r.querySelector('.ol-ico') || r;
                    const b = ico.getBoundingClientRect();
                    return {
                      x: Math.max(2, b.left - a.left - 12),
                      y: b.top - a.top + b.height / 2 + outline.scrollTop,
                    };
                  };
                  const active = row(synthesisId);
                  active.dispatchEvent(new MouseEvent('mouseover', {
                    bubbles: true, clientX: active.getBoundingClientRect().left + 4,
                    clientY: active.getBoundingClientRect().top + 4,
                  }));
                  const paths = [...outline.querySelectorAll('path.ol-rel')].map(p => parse(p.getAttribute('d')));
                  const a = anchor(active);
                  const source = anchor(row(councilId));
                  const targets = [source, anchor(row(decisionId))];
                  const topIcons = [...outline.querySelectorAll('.olrow:not(.ol-tw) .ol-ico')]
                    .map(el => Math.round(el.getBoundingClientRect().left));
                  return {paths, a, source, targets, topIcons};
                }""",
                {"councilId": f"council:{council['id']}",
                 "synthesisId": f"synthesis:{synthesis['id']}",
                 "decisionId": decision["id"]},
            )
            assert len(result["paths"]) == 2
            source_path = next(p for p in result["paths"] if round(p["sy"]) == round(result["source"]["y"]))
            output_path = next(p for p in result["paths"] if round(p["sy"]) == round(result["a"]["y"]))
            assert abs(source_path["ex"] - result["a"]["x"]) <= 1
            assert abs(source_path["ey"] - result["a"]["y"]) <= 1
            assert abs(output_path["sx"] - result["a"]["x"]) <= 1
            assert abs(output_path["sy"] - result["a"]["y"]) <= 1
            target_ys = sorted(round(t["y"]) for t in result["targets"])
            actual_ys = sorted(round(p["ey"]) for p in result["paths"])
            assert actual_ys == sorted([round(result["a"]["y"]), target_ys[-1]])
            assert max(result["topIcons"]) - min(result["topIcons"]) <= 1
            b.close()
    finally:
        server.should_exit = True
        thread.join(timeout=10)
