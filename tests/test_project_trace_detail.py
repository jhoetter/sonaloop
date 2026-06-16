from __future__ import annotations

import html
import re

from starlette.testclient import TestClient

from sonaloop import services, web


def test_detail_relations_use_augmented_project_trace_edges(store):
    project = services.start_project("Trace details", "How might we expose trace relations?", None,
                                     persona_ids=["p1"], store=store)
    pid = project["id"]
    services.record_frame(pid, "frame__root", ["Which proof matters?"],
                          memory_refs=["memory:p1:shift"], store=store)
    act = services.add_task(pid, "act", "survey", "Run proof survey",
                            consumes=["frame__root"], store=store)
    survey = services.record_survey(
        pid, "Proof survey",
        [{"id": "q1", "text": "Useful?", "kind": "single", "options": ["yes", "no"]}],
        status="open", store=store)["survey"]
    services.link_evidence(pid, act["id"], {"kind": "survey", "id": survey["id"]}, store=store)
    verify = services.add_task(pid, "verify", "synthesize", "Trace report gate",
                               consumes=["frame__root"], store=store)
    syn = services.record_synthesis("Trace report", "start", [], {"gesamtbild": "Used evidence"},
                                    project_id=pid, store=store)
    services.link_evidence(pid, verify["id"], {"kind": "synthesis", "id": syn["id"]}, store=store)
    services.record_judgment(pid, verify["id"], "trace_closed", True, "survey proves it",
                             evidence_refs=[f"survey:{survey['id']}"], store=store)

    client = TestClient(web.create_app())
    outline = client.get(f"/projects/{pid}?lang=en").text
    m = re.search(rf'data-oid="{re.escape(survey["id"])}"[^>]*data-rel-out="([^"]*)"', outline)
    assert m, "survey row is missing its outline trace relation"
    assert f"synthesis:{syn['id']}" in html.unescape(m.group(1))

    detail = client.get(f"/surveys/{survey['id']}?lang=en").text
    assert "Relations" in detail
    assert "Feeds into" in detail
    assert "Trace report" in detail
    assert "used by gate" in detail
