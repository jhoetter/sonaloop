"""Report hand-off truth, retries and concurrent authoring."""
from __future__ import annotations

import asyncio
import base64
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from sonaloop import services
from sonaloop.services import _engines
from sonaloop.report_handoff import report_handoff_state
from sonaloop.mcp_server import build_server
from sonaloop.storage import Store


def _outline(*headings: str, lead: str = "Evidence to decision.") -> dict:
    return {
        "build_order_narrative": lead,
        "sections": [
            {"heading": heading, "intent": f"Author {heading}.",
             "theme_tags": [], "source_study_ids": []}
            for heading in headings
        ],
    }


def test_empty_scaffold_is_progress_not_a_handoff(store):
    project = services.start_project(
        "Draft truth", "Question", methodology="double_diamond", store=store)

    report = services.scaffold_synthesis(project["id"], store=store)
    handoff = report_handoff_state(report)

    assert report["status"] == "in_progress"
    assert handoff["exists"] is True and handoff["complete"] is False
    assert handoff["reports"][0]["authored_section_count"] == 0
    assert services.assess_project(project["id"], store=store)["finish"]["handed_off"] is False
    health = services.project_health(project["id"], store=store)
    assert any(row["code"] == "report_incomplete" for row in health["integrity_findings"])
    assert not any(row["code"] == "orphaned_evidence" and report["id"] in row["message"]
                   for row in health["integrity_findings"])


def test_reaction_scaffold_freezes_graph_sources_for_structural_sections(store):
    project = services.start_project(
        "Structural Reaction report", "Question", methodology="Reaction Test", store=store)
    source_id = "structural_report_source"
    store.upsert_synthesis({
        "id": source_id, "title": "Reaction evidence", "project_id": project["id"],
        "scope": "study", "status": "done", "created_at": "2026-08-11T00:00:00Z",
        "council_ids": [], "statements": [], "findings": [],
    })

    report = services.scaffold_synthesis(project["id"], store=store)
    frozen = list(report["graph_snapshot"]["build_order"])

    assert f"synthesis:{source_id}" in frozen
    assert len(report["sections"]) > 2
    assert all(section["source_study_ids"] for section in report["sections"])
    assert any(section["source_study_ids"] == frozen for section in report["sections"])


def test_reaction_report_health_uses_section_citations_not_a_generic_claim_envelope(store):
    project = services.start_project(
        "Cited Reaction report", "Question", methodology="Reaction Test", store=store)
    asset = services.attach_asset(
        project["id"], content_base64=base64.b64encode(b"bounded stimulus").decode(),
        filename="stimulus.txt", kind="document", store=store)
    source_id = "source_for_report_health"
    cross_phase_id = "cross_phase_source_for_report_health"
    store.upsert_synthesis({
        "id": source_id, "title": "Bounded source", "project_id": project["id"],
        "scope": "study", "status": "done", "created_at": "2026-08-11T00:00:00Z",
        "council_ids": [], "statements": [], "findings": [],
        "claim_posture": {
            "schema": "sonaloop.claim_posture.v1", "verified": True,
            "prose_uncovered": False, "counts": {"inferred": 1, "unsupported": 0},
            "claims": [{"id": "source-claim", "text": "Bounded source claim",
                        "posture": "inferred", "refs": [{"kind": "asset", "id": asset["id"]}]}],
        },
    })
    store.upsert_synthesis({
        "id": cross_phase_id, "title": "Cross-phase source", "project_id": project["id"],
        "scope": "study", "status": "done", "created_at": "2026-08-11T00:00:01Z",
        "council_ids": [], "statements": [], "findings": [],
    })
    persisted = store.get_research_project(project["id"])
    persisted["study_ids"] = [
        f"synthesis:{source_id}", f"synthesis:{cross_phase_id}"]
    store.upsert_research_project(persisted)

    report = services.record_synthesis_outline(
        project["id"], {
            "build_order_narrative": "Evidence to conclusion.",
            "sections": [{"heading": "Finding", "intent": "Bounded conclusion",
                          "theme_tags": [],
                          "source_study_ids": [f"synthesis:{source_id}"]}],
        }, store=store)
    report = services.record_synthesis_section(
        project["id"], "sec1",
        {"markdown": "The bounded evidence supports this conclusion.",
         "citations": [{"study_id": f"synthesis:{source_id}",
                         "council_id": "", "quote": "Bounded source claim"}]},
        report_id=report["id"], store=store)
    assert report["handoff"]["complete"] is True and not report.get("claim_posture")

    healthy = services.project_health(project["id"], store=store)
    assert not any(row["code"] == "claim_provenance_incomplete"
                   and report["id"] in row.get("target", "")
                   for row in healthy["integrity_findings"])

    strict = store.get_report(report["id"])
    strict["sections"][0]["citations"].append(
        {"study_id": f"synthesis:{cross_phase_id}",
         "council_id": "", "quote": ""})
    store.upsert_synthesis(strict)
    strict_health = services.project_health(project["id"], store=store)
    assert not any(row["code"] in {"claim_provenance_incomplete", "invalid_evidence_ref"}
                   and report["id"] in row.get("target", "")
                   for row in strict_health["integrity_findings"])

    anchored_foreign = store.get_report(report["id"])
    anchored_foreign["sections"][0]["citations"].append(
        {"study_id": "synthesis:not_in_frozen_graph", "council_id": "", "quote": ""})
    store.upsert_synthesis(anchored_foreign)
    anchored_foreign_health = services.project_health(project["id"], store=store)
    assert any(row["code"] == "invalid_evidence_ref"
               and row.get("target") == f"/syntheses/{report['id']}"
               for row in anchored_foreign_health["integrity_findings"])

    unanchored = store.get_report(report["id"])
    unanchored["sections"][0]["citations"] = [
        {"study_id": f"synthesis:{cross_phase_id}", "council_id": "", "quote": ""}]
    store.upsert_synthesis(unanchored)
    unanchored_health = services.project_health(project["id"], store=store)
    assert any(row["code"] == "claim_provenance_incomplete"
               and report["id"] in row.get("target", "")
               for row in unanchored_health["integrity_findings"])
    assert not any(row["code"] == "invalid_evidence_ref"
                   and report["id"] in row.get("target", "")
                   for row in unanchored_health["integrity_findings"])

    legacy = store.get_report(report["id"])
    legacy["sections"][0]["source_study_ids"] = []
    legacy["sections"][0]["citations"] = [
        {"study_id": f"synthesis:{source_id}",
         "council_id": "", "quote": "Bounded source claim"}]
    store.upsert_synthesis(legacy)
    legacy_health = services.project_health(project["id"], store=store)
    assert not any(row["code"] in {"claim_provenance_incomplete", "invalid_evidence_ref"}
                   and report["id"] in row.get("target", "")
                   for row in legacy_health["integrity_findings"])

    foreign = store.get_report(report["id"])
    foreign["sections"][0]["citations"] = [
        {"study_id": "synthesis:not_in_frozen_graph", "council_id": "", "quote": ""}]
    store.upsert_synthesis(foreign)
    foreign_health = services.project_health(project["id"], store=store)
    assert any(row["code"] == "claim_provenance_incomplete"
               and report["id"] in row.get("target", "")
               for row in foreign_health["integrity_findings"])
    assert any(row["code"] == "invalid_evidence_ref"
               and report["id"] in row.get("target", "")
               for row in foreign_health["integrity_findings"])

    uncited = store.get_report(report["id"])
    uncited["sections"][0]["citations"] = []
    store.upsert_synthesis(uncited)
    unhealthy = services.project_health(project["id"], store=store)
    assert any(row["code"] == "claim_provenance_incomplete"
               and report["id"] in row.get("target", "")
               and "without a valid citation" in row["message"]
               for row in unhealthy["integrity_findings"])


def test_scaffold_operation_id_replays_existing_draft(store):
    project = services.create_research_project("Scaffold retry", goal="g", store=store)
    first = services.scaffold_synthesis(
        project["id"], operation_id="host:scaffold:1", store=store)
    replay = services.scaffold_synthesis(
        project["id"], operation_id="host:scaffold:1", store=store)

    assert first["id"] == replay["id"]
    assert replay["idempotent_replay"] is True
    assert len(store.list_reports(project["id"])) == 1


def test_lead_and_every_section_are_required_and_completion_updates_status(store):
    project = services.create_research_project("Lead truth", goal="g", store=store)
    report = services.record_synthesis_outline(
        project["id"], _outline("One", "Two", lead=""), store=store)
    for section in report["sections"]:
        report = services.record_synthesis_section(
            project["id"], section["id"], {"markdown": f"Body {section['id']}"},
            report_id=report["id"], store=store)

    assert report["status"] == "in_progress"
    assert report["handoff"]["lead_missing"] is True
    assert all(section["status"] == "done" and section["updated_at"]
               for section in report["sections"])

    repaired = services.record_synthesis_outline(
        project["id"], _outline("One", "Two", lead="Now the evidence story is explicit."),
        report_id=report["id"], operation_id="report:lead-repair", store=store)
    assert repaired["id"] == report["id"]
    assert repaired["status"] == "done"
    assert repaired["handoff"]["complete"] is True
    assert all(section["markdown"].startswith("Body") for section in repaired["sections"])


def test_lead_repair_does_not_widen_the_frozen_report_graph(store):
    project = services.create_research_project("Immutable report graph", goal="g", store=store)
    first_id = "report_graph_first"
    second_id = "report_graph_later"
    store.upsert_synthesis({
        "id": first_id, "title": "First evidence", "project_id": project["id"],
        "scope": "study", "status": "done", "created_at": "2026-08-11T00:00:00Z",
        "council_ids": [], "statements": [], "findings": [],
    })
    persisted = store.get_research_project(project["id"])
    persisted["study_ids"] = [f"synthesis:{first_id}"]
    store.upsert_research_project(persisted)
    outline = {
        "build_order_narrative": "",
        "sections": [{"heading": "Evidence", "intent": "Trace the evidence.",
                      "theme_tags": [],
                      "source_study_ids": [f"synthesis:{first_id}"]}],
    }
    report = services.record_synthesis_outline(project["id"], outline, store=store)
    frozen_before = dict(report["graph_snapshot"])
    report = services.record_synthesis_section(
        project["id"], report["sections"][0]["id"],
        {"markdown": "The first source anchors a cross-phase conclusion.",
         "citations": [
             {"study_id": f"synthesis:{first_id}", "council_id": "", "quote": ""},
             {"study_id": f"synthesis:{second_id}", "council_id": "", "quote": ""},
         ]},
        report_id=report["id"], store=store)
    before_health = services.project_health(project["id"], store=store)
    assert any(row["code"] == "invalid_evidence_ref"
               and row.get("target") == f"/syntheses/{report['id']}"
               for row in before_health["integrity_findings"])

    store.upsert_synthesis({
        "id": second_id, "title": "Later evidence", "project_id": project["id"],
        "scope": "study", "status": "done", "created_at": "2026-08-11T00:01:00Z",
        "council_ids": [], "statements": [], "findings": [],
    })
    persisted = store.get_research_project(project["id"])
    persisted["study_ids"] = [f"synthesis:{first_id}", f"synthesis:{second_id}"]
    store.upsert_research_project(persisted)
    repaired_outline = {**outline, "build_order_narrative": "Lead repaired after authoring."}
    repaired = services.record_synthesis_outline(
        project["id"], repaired_outline, report_id=report["id"], store=store)

    assert repaired["graph_snapshot"] == frozen_before
    after_health = services.project_health(project["id"], store=store)
    assert any(row["code"] == "invalid_evidence_ref"
               and row.get("target") == f"/syntheses/{report['id']}"
               for row in after_health["integrity_findings"])


def test_outline_reuses_empty_scaffold_and_operation_replays_or_conflicts(store):
    project = services.create_research_project("Retry report", goal="g", store=store)
    scaffold = services.scaffold_synthesis(project["id"], store=store)
    authored_outline = _outline("Evidence", "Decision")

    first = services.record_synthesis_outline(
        project["id"], authored_outline, operation_id="host:outline:1", store=store)
    replay = services.record_synthesis_outline(
        project["id"], authored_outline, operation_id="host:outline:1", store=store)

    assert first["id"] == scaffold["id"] == replay["id"]
    assert len(store.list_reports(project["id"])) == 1
    assert replay["idempotent_replay"] is True
    with pytest.raises(ValueError, match="REPORT_OUTLINE_OPERATION_CONFLICT"):
        services.record_synthesis_outline(
            project["id"], _outline("Different"), operation_id="host:outline:1", store=store)


def test_new_operation_preserves_completed_report_as_intentional_second_report(store):
    project = services.create_research_project("Two reports", goal="g", store=store)
    first = services.record_synthesis_outline(
        project["id"], _outline("First"), operation_id="host:first", store=store)
    first = services.record_synthesis_section(
        project["id"], "sec1", {"markdown": "First report body."},
        report_id=first["id"], store=store)
    assert first["handoff"]["complete"] is True

    second = services.record_synthesis_outline(
        project["id"], _outline("Second"), operation_id="host:second", store=store)

    assert second["id"] != first["id"]
    assert second["status"] == "in_progress"
    assert len(store.list_reports(project["id"])) == 2
    assert report_handoff_state(store.list_reports(project["id"]))["complete"] is True


def test_concurrent_section_writes_preserve_both_bodies(store):
    project = services.create_research_project("Concurrent report", goal="g", store=store)
    report = services.record_synthesis_outline(
        project["id"], _outline("One", "Two"), operation_id="host:concurrent", store=store)
    barrier = Barrier(2)

    def write(section_id: str) -> dict:
        with Store() as scoped:
            barrier.wait(timeout=10)
            return services.record_synthesis_section(
                project["id"], section_id, {"markdown": f"Authored {section_id}."},
                report_id=report["id"], store=scoped)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [future.result() for future in (
            pool.submit(write, "sec1"), pool.submit(write, "sec2"))]

    persisted = store.get_report(report["id"])
    assert {section["markdown"] for section in persisted["sections"]} == {
        "Authored sec1.", "Authored sec2."}
    assert persisted["status"] == "done"
    assert any(result["handoff"]["complete"] for result in results)


def test_project_health_honors_parked_evidence(store):
    project = services.create_research_project("Parked evidence", goal="g", store=store)
    council = {
        "id": "c_parked", "project_id": project["id"],
        "created_at": "2026-08-11T00:00:00+00:00", "prompt": "Side signal",
        "persona_ids": [], "statements": [], "votes": [], "proposal": "",
        "summary": "", "exec_summary": "", "selection_reason": "",
    }
    store.insert_council_session(council)
    services.park_evidence(
        project["id"], ["council:c_parked"], "Useful context, not gate evidence.", store=store)

    health = services.project_health(project["id"], store=store)
    assert not any(row["code"] == "orphaned_evidence" and "c_parked" in row["message"]
                   for row in health["integrity_findings"])


def test_dispatch_bound_scaffold_is_progress_and_final_section_checkpoints(store):
    project = services.create_research_project("Governed report", goal="g", store=store)
    services.record_frame(
        project["id"], "frame__root", ["What is the answer?"],
        memory_refs=["memory:seed"], store=store)
    handoff_task = services.add_task(
        project["id"], "verify", "report_handoff", "Deliver report",
        consumes=["frame__root"], requires={"min_inputs": 0}, store=store)
    persisted_project = store.get_research_project(project["id"])
    persisted_project["governance_contract"] = "dispatch_v1"
    store.upsert_research_project(persisted_project)
    run = services.start_run(
        project["id"], operation_id="run:governed-report", store=store)
    dispatch = _engines._issue_dispatch(
        run["run_id"], project["id"], handoff_task["id"], "verify",
        "report:handoff", store,
        trace_contract={"expected_output_kind": "report",
                        "allowed_primary_kinds": ["report"]},
    )

    draft = services.scaffold_synthesis(
        project["id"], dispatch_token=dispatch["dispatch_token"], store=store)
    assert draft["dispatch"]["state"] == "progress"
    assert draft["dispatch"]["checkpointed"] is False
    assert services.get_plan(project["id"], store=store)["tasks"][-1]["status"] != "done"

    for section in draft["sections"]:
        result = services.record_synthesis_section(
            project["id"], section["id"], {"markdown": f"Complete {section['heading']}."},
            report_id=draft["id"], dispatch_token=dispatch["dispatch_token"], store=store)

    assert result["dispatch"]["checkpointed"] is True
    assert result["handoff"]["complete"] is True
    assert services.get_plan(project["id"], store=store)["tasks"][-1]["status"] == "done"
    replay = services.record_synthesis_section(
        project["id"], result["sections"][-1]["id"],
        {"markdown": f"Complete {result['sections'][-1]['heading']}."},
        report_id=result["id"], dispatch_token=dispatch["dispatch_token"], store=store)
    assert replay["idempotent_replay"] is True
    assert replay["dispatch"]["checkpointed"] is True


def test_mcp_report_writes_expose_retry_and_dispatch_contract():
    tools = {tool.name: tool for tool in asyncio.run(build_server().list_tools())}
    scaffold = tools["scaffold_synthesis"].inputSchema["properties"]
    outline = tools["record_synthesis_outline"].inputSchema["properties"]
    section = tools["record_synthesis_section"].inputSchema["properties"]

    assert {"operation_id", "dispatch_token"} <= scaffold.keys()
    assert {"report_id", "operation_id", "dispatch_token"} <= outline.keys()
    assert "dispatch_token" in section
