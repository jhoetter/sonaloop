"""M004 canonical evidence-health and safe recovery acceptance."""
from __future__ import annotations

import base64

import pytest
from starlette.testclient import TestClient

from sonaloop import services, web
from sonaloop.mcp_server import build_server


def _reaction_with_understanding(store, suffix: str = "ux"):
    project = services.start_project(
        f"Reaction recovery {suffix}", "Can users understand the actual product?",
        methodology="Reaction Test", operation_id=f"reaction:{suffix}", store=store)
    run = services.start_run(project["id"], operation_id=f"reaction-run:{suffix}", store=store)
    dispatch = services.run_step(run["run_id"], store=store)
    asset = services.attach_asset(
        project["id"], content_base64=base64.b64encode(b"screen-state").decode(),
        filename="home.png", kind="screenshot", title="Home screen",
        dispatch_token=dispatch["dispatch_token"], store=store)
    ref = {"kind": "asset", "id": asset["id"]}
    understanding = services.record_product_understanding(
        project["id"], target={"name": "Example app", "url": "https://example.test"},
        revision="deploy:42",
        routes=[{"path": "/", "evidence_refs": [ref]}],
        flows=[{"name": "Home to finance", "evidence_refs": [ref]}],
        states=[{"state": "home", "evidence_refs": [ref]}],
        capabilities=[
            {"key": "route", "claim": "A finance route is present",
             "status": "observed_present", "evidence_refs": [ref]},
            {"key": "chat", "claim": "No chat control is visible",
             "status": "observed_absent", "evidence_refs": [ref],
             "verification_attempt": {"procedure": "Inspected the complete captured home state"}},
            {"key": "calculator", "claim": "A calculator may exist beyond this state",
             "status": "unknown"},
        ], evidence_refs=[ref], observed_at="2026-08-08T12:00:00Z",
        dispatch_token=dispatch["dispatch_token"], store=store)
    return project, run, ref, understanding


def test_project_health_names_incomplete_dispatch_and_safe_existing_resume(store):
    project = services.start_project(
        "Recovery", "Research question", methodology="double_diamond",
        operation_id="recovery:create", store=store)
    run = services.start_run(project["id"], operation_id="recovery:run", store=store)
    dispatch = services.run_step(run["run_id"], store=store)

    health = services.project_health(project["id"], store=store)
    assert health["schema"] == "sonaloop.project_health.v1"
    assert health["state"] == "running"
    assert health["unmet_invariant"]["code"] == "dispatch_incomplete"
    assert health["safe_next_action"]["kind"] == "resume_existing_run"
    assert health["safe_next_action"]["arguments"] == {
        "project_id": project["id"], "run_id": run["run_id"],
        "operation_id": "recovery:run"}
    assert health["recovery_signals"]["host_connection"] == "unknown"
    assert health["recovery_signals"]["dispatch"] == "incomplete"
    assert health["trace"]["external_host_visibility"] == "not_observable"
    assert "hidden provider prompts" in health["trace"]["limitation"]

    first = services.resume_project_run(project["id"], run["run_id"], "recovery:run", store=store)
    second = services.resume_project_run(project["id"], run["run_id"], "recovery:run", store=store)
    assert first == second
    assert len(store.list_runs(project["id"])) == 1
    assert store.get_run(run["run_id"])["dispatches"][0]["dispatch_token"] == dispatch["dispatch_token"]
    with pytest.raises(Exception, match="RUN_NOT_FINISHABLE"):
        services.finish_run(run["run_id"], "finished", store=store)


def test_unverified_is_distinct_from_engine_finished(store):
    project = services.start_project("Legacy complete", "q", operation_id="legacy-complete", store=store)
    services.record_frame(project["id"], "frame__root", ["q?"], memory_refs=["memory:a"], store=store)
    health = services.project_health(project["id"], store=store)
    assert health["state"] == "unverified"
    assert health["engine_finished"] is False
    assert health["unmet_invariant"]["code"] in {"critic_pending", "engine_completion_missing"}

    # A persisted engine-finished journal is a different canonical state. This
    # fixture intentionally writes the journal boundary directly; finish_run's
    # behavioral gate is covered elsewhere.
    now = "2026-08-08T12:00:00+00:00"
    store.upsert_run({"run_id": "run_engine_done", "project_id": project["id"],
                      "status": "finished", "cursor": 0, "steps": [], "dispatches": [],
                      "critic_rounds": [], "created_at": now, "updated_at": now})
    finished = services.project_health(project["id"], store=store)
    assert finished["state"] == "finished"
    assert finished["driver_state"] == "engine_finished"
    assert finished["engine_finished"] is True


def test_new_active_run_wins_over_historical_finished_run(store):
    project = services.start_project(
        "Recovery precedence", "q", methodology="double_diamond",
        operation_id="recovery-precedence:create", store=store)
    store.upsert_run({
        "run_id": "run_historical_finished", "project_id": project["id"],
        "operation_id": "recovery-precedence:old", "status": "finished",
        "cursor": 0, "steps": [], "dispatches": [], "critic_rounds": [],
        "created_at": "2026-08-07T12:00:00+00:00",
        "updated_at": "2026-08-07T12:01:00+00:00",
    })
    active = services.start_run(
        project["id"], operation_id="recovery-precedence:active", store=store)

    health = services.project_health(project["id"], stale_hours=24, store=store)

    assert health["state"] == "running"
    assert health["driver_state"] == "running"
    assert health["engine_finished"] is False
    assert health["run_id"] == active["run_id"]
    assert health["run_inventory"] == {
        "active": 1, "historical_finished": 1, "total": 2,
    }
    assert health["safe_next_action"]["kind"] == "resume_existing_run"
    assert health["safe_next_action"]["arguments"]["run_id"] == active["run_id"]


def test_supersede_and_archive_are_explicit_idempotent_and_non_destructive(store):
    old = services.start_project("Old result", "q", operation_id="old-create", store=store)
    new = services.start_project("Canonical result", "q", operation_id="new-create", store=store)
    old_row = store.get_research_project(old["id"])
    old_row["assets"] = [{"id": "asset_old", "title": "Preserved evidence"}]
    store.upsert_research_project(old_row)

    first = services.supersede_project(
        new["id"], old["id"], "lineage:one", "Explicit operator reconciliation", store=store)
    second = services.supersede_project(
        new["id"], old["id"], "lineage:one", "Explicit operator reconciliation", store=store)
    assert first["evidence_deleted"] is False and second["idempotent"] is True
    assert store.get_research_project(new["id"])["supersedes_project_id"] == old["id"]
    obsolete = store.get_research_project(old["id"])
    assert obsolete["status"] == "superseded"
    assert obsolete["superseded_by_project_id"] == new["id"]
    assert obsolete["assets"][0]["id"] == "asset_old"

    archived = services.archive_project(
        new["id"], "archive:one", "Operator explicitly archived canonical record", store=store)
    assert archived["evidence_deleted"] is False
    assert services.archive_project(
        new["id"], "archive:one", "Operator explicitly archived canonical record", store=store)["idempotent"]
    page = TestClient(web.create_app()).get(f'/jobs/{old["id"]}?lang=en').text
    assert "Job lineage" in page and new["id"] in page

    active = services.start_project("Active", "q", operation_id="active-create", store=store)
    services.start_run(active["id"], operation_id="active-run", store=store)
    with pytest.raises(ValueError, match="ACTIVE_RUN_ARCHIVE_BLOCKED"):
        services.archive_project(active["id"], "archive:active", "Do not race", store=store)


def test_bilingual_evidence_health_precedes_report_and_has_exact_sources(store):
    project, run, ref, _understanding = _reaction_with_understanding(store, "dom")
    services.finish_run(run["run_id"], "stopped", store=store)
    council = services.record_council(
        project["id"], "React to the captured home state", ["persona_a"],
        statements=[{"persona_id": "persona_a", "text": "The route is visible.", "refs": [ref]}],
        summary="The simulated participant noticed the route.",
        claims=[{"id": "claim-route", "text": "The captured state contains a finance route.",
                 "posture": "inferred", "refs": [ref]}], store=store)
    synthesis = services.record_synthesis(
        "Reaction report", "Summarize", [council["id"]], project_id=project["id"],
        payload={"gesamtbild": "The captured state and simulated reaction are kept distinct.",
                 "claims": [{"id": "report-route", "text": "The route is present in the stimulus.",
                              "posture": "inferred", "refs": [ref]}]}, store=store)

    client = TestClient(web.create_app())
    for language, verified, sources, absences, unknown in (
        ("en", "Claim provenance complete", "Sources", "verified absences", "unknown"),
        ("de", "Claim-Herkunft vollständig", "Quellen", "verifizierte Abwesenheiten", "unbekannt"),
    ):
        council_html = client.get(f'/councils/{council["id"]}?lang={language}').text
        report_html = client.get(f'/syntheses/{synthesis["id"]}?lang={language}').text
        for html in (council_html, report_html):
            assert verified in html and sources in html
            assert 'id="claim-health"' in html and 'role="status"' in html
            assert ref["id"] in html and "Product Understanding" in html
            assert absences in html and unknown in html
            # Trust/evidence blocks precede authored result prose.
            assert html.index('id="claim-health"') < html.index('id="product-understanding"')
        assert report_html.index('id="product-understanding"') < report_html.index("captured state and simulated")


def test_mcp_and_cli_recovery_surface_is_present():
    names = {tool.name for tool in build_server()._tool_manager.list_tools()}
    assert {"project_health", "resume_project_run", "supersede_project", "archive_project"} <= names
    from sonaloop.cli import build_parser
    parser = build_parser()
    assert parser.parse_args(["project-health", "p1"]).command == "project-health"
    assert parser.parse_args(["run-resume", "p1", "r1"]).run_id == "r1"
