from __future__ import annotations

import html
import re

from starlette.testclient import TestClient

from sonaloop import services, web
from sonaloop.project_trace import trace_node_health
from sonaloop.web._detail import _relations_html
from sonaloop.web._project_graph_view import augment_project_graph


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
    outline = client.get(f"/jobs/{pid}?lang=en").text
    m = re.search(rf'data-oid="{re.escape(survey["id"])}"[^>]*data-rel-out="([^"]*)"', outline)
    assert m, "survey row is missing its outline trace relation"
    assert f"synthesis:{syn['id']}" in html.unescape(m.group(1))

    detail = client.get(f"/surveys/{survey['id']}?lang=en").text
    assert "Relations" in detail
    assert "Feeds into" in detail
    assert "Trace report" in detail
    assert "used by gate" in detail


def test_detail_relations_group_duplicate_visible_targets(store):
    html = _relations_html(
        store, "synthetic:node", None, aside=True,
        extra_out=[
            {"href": "/sessions/a", "title": "Prototype run", "kind_label": "Session", "rel_label": "input"},
            {"href": "/sessions/b", "title": "Prototype run", "kind_label": "Session", "rel_label": "input"},
            {"href": "/sessions/c", "title": "Prototype run", "kind_label": "Session", "rel_label": "used by gate"},
        ],
    )
    assert html.count("Prototype run") == 1
    assert "3x Session" in html
    assert "input, used by gate" in html


def test_synthesis_detail_uses_referenced_councils_instead_of_duplicate_relation_inputs(store):
    project = services.start_project("Synthesis relations", "How might we avoid duplicate evidence?",
                                     None, persona_ids=["p1"], store=store)
    c1 = services.record_council(project["id"], "What gets lost?", [], key="rel-c1", store=store)
    c2 = services.record_council(project["id"], "What proves value?", [], key="rel-c2", store=store)
    syn = services.record_synthesis(
        "Define synthesis", "What matters?", [c1["id"], c2["id"]],
        {"gesamtbild": "Two councils inform this synthesis."},
        project_id=project["id"], store=store)
    html = TestClient(web.create_app()).get(f'/syntheses/{syn["id"]}?lang=en').text
    assert "rp-title__icon" in html and "pi-syntheses" in html
    assert "Referenced councils" in html
    if "RELATIONS" in html:
        rel = html.split("RELATIONS", 1)[1].split("Referenced councils", 1)[0]
        assert "Based on" not in rel
        assert "What gets lost?" not in rel


def test_project_report_sources_feed_outline_and_detail_relations(store):
    project = services.start_project(
        "Report lineage", "How might we keep the final hand-off traceable?", store=store)
    synthesis = services.record_synthesis(
        "Gate synthesis", "What did the evidence establish?", [],
        {"gesamtbild": "The evidence converged."}, project_id=project["id"], store=store)
    report = services.scaffold_synthesis(project["id"], store=store)
    assert any(f'synthesis:{synthesis["id"]}' in section["source_study_ids"]
               for section in report["sections"])

    client = TestClient(web.create_app())
    outline = client.get(f'/jobs/{project["id"]}?lang=en').text
    report_row = re.search(
        rf'<a[^>]*data-oid="{re.escape(report["id"])}"[^>]*>', outline)
    synthesis_row = re.search(
        rf'<a[^>]*data-oid="synthesis:{re.escape(synthesis["id"])}"[^>]*>', outline)
    assert report_row and f'data-rel-in="synthesis:{synthesis["id"]}"' in report_row.group(0)
    assert synthesis_row and f'data-rel-out="{report["id"]}"' in synthesis_row.group(0)
    assert "1 input" in report_row.group(0) or "1 input" in outline
    assert "1 output" in synthesis_row.group(0) or "1 output" in outline

    detail = client.get(f'/syntheses/{report["id"]}?lang=en').text
    assert "Relations" in detail
    assert "Based on" in detail
    assert "Gate synthesis" in detail

    graph = services.get_project_graph(project["id"], store=store)
    augmented = augment_project_graph(
        graph, sessions={}, decisions=[], hypotheses=[], surveys=[], assets=[])
    health = trace_node_health(augmented["nodes"], augmented["edges"], graph.get("plan"))
    assert health[f'synthesis:{synthesis["id"]}'] == "consumed"
    assert health[f'report:{report["id"]}'] == "terminal"


def test_legacy_report_uses_only_snapshot_valid_citations_as_source_fallback(store):
    project = services.start_project("Legacy report lineage", "Question", store=store)
    synthesis = services.record_synthesis(
        "Legacy gate", "What matters?", [], {"gesamtbild": "Grounded conclusion."},
        project_id=project["id"], store=store)
    frozen_graph = services.get_project_graph(project["id"], store=store)
    report_id = "report_legacy_lineage"
    store.upsert_synthesis({
        "id": report_id, "title": "Legacy final report", "scope": "project",
        "project_id": project["id"], "status": "done", "created_at": "2026-08-11T12:00:00Z",
        "lead": "A complete historical hand-off.", "graph_snapshot": frozen_graph,
        "sections": [{
            "id": "sec1", "heading": "Gate", "markdown": "The evidence converged.",
            "source_study_ids": [],
            "citations": [
                "malformed-legacy-citation",
                {"study_id": f'synthesis:{synthesis["id"]}', "council_id": "", "quote": ""},
                {"study_id": "synthesis:foreign", "council_id": "", "quote": ""},
            ],
        }],
    })

    graph = services.get_project_graph(project["id"], store=store)
    report_stub = next(row for row in graph["reports"] if row["id"] == report_id)
    assert report_stub["source_study_ids"] == []
    assert report_stub["legacy_citation_study_ids"] == [f'synthesis:{synthesis["id"]}']
    augmented = augment_project_graph(
        graph, sessions={}, decisions=[], hypotheses=[], surveys=[], assets=[])
    report_edges = [edge for edge in augmented["edges"]
                    if edge.get("to_study") == f"report:{report_id}"]
    assert [(edge["from_study"], edge["source"]) for edge in report_edges] == [
        (f'synthesis:{synthesis["id"]}', "report.sections.citations")]


def test_report_lineage_never_crosses_its_frozen_snapshot(store):
    project = services.start_project("Frozen report lineage", "Question", store=store)
    first = services.record_synthesis(
        "Frozen source", "What mattered?", [], {"gesamtbild": "First evidence."},
        project_id=project["id"], store=store)
    frozen_graph = services.get_project_graph(project["id"], store=store)
    later = services.record_synthesis(
        "Later source", "What changed later?", [], {"gesamtbild": "Later evidence."},
        project_id=project["id"], store=store)
    report_id = "report_frozen_lineage"
    store.upsert_synthesis({
        "id": report_id, "title": "Frozen final report", "scope": "project",
        "project_id": project["id"], "status": "done", "created_at": "2026-08-11T12:00:00Z",
        "lead": "A frozen hand-off.", "graph_snapshot": frozen_graph,
        "sections": [{
            "id": "sec1", "heading": "Gate", "markdown": "The first evidence converged.",
            "source_study_ids": [f'synthesis:{first["id"]}', f'synthesis:{later["id"]}'],
            "citations": [{"study_id": f'synthesis:{first["id"]}',
                           "council_id": "", "quote": ""}],
        }],
    })

    graph = services.get_project_graph(project["id"], store=store)
    report_stub = next(row for row in graph["reports"] if row["id"] == report_id)
    assert report_stub["source_study_ids"] == [f'synthesis:{first["id"]}']
    augmented = augment_project_graph(
        graph, sessions={}, decisions=[], hypotheses=[], surveys=[], assets=[])
    report_edges = [edge for edge in augmented["edges"]
                    if edge.get("to_study") == f"report:{report_id}"]
    assert [edge["from_study"] for edge in report_edges] == [f'synthesis:{first["id"]}']
