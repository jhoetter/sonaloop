"""M004 canonical evidence-health and safe recovery acceptance."""
from __future__ import annotations

import base64
import json
from datetime import datetime, timedelta, timezone

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
    assert health["schema"] == "sonaloop.project_health.v2"
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


def test_project_health_resolves_each_repeated_claim_reference_once(store, monkeypatch):
    """A report-sized claim set must not turn the status projection into N+1 reads."""
    from sonaloop.services import _recovery

    project = services.start_project(
        "Health reference cache", "Question", methodology=None, store=store)
    ref = {"kind": "asset", "id": "same-evidence"}
    store.upsert_synthesis({
        "id": "synthesis_repeated_health_ref",
        "title": "Repeated reference",
        "project_id": project["id"],
        "scope": "convergence",
        "status": "done",
        "created_at": "2026-08-11T00:00:00Z",
        "council_ids": [],
        "statements": [],
        "findings": [],
        "claim_posture": {
            "schema": "sonaloop.claim_posture.v1",
            "verified": True,
            "prose_uncovered": False,
            "counts": {"inferred": 3, "unsupported": 0},
            "claims": [
                {"id": f"claim-{index}", "text": "Same source", "posture": "inferred",
                 "refs": [dict(ref)]}
                for index in range(3)
            ],
        },
    })
    calls = []

    def _count_ref(project_id, candidate, candidate_store):
        calls.append((project_id, candidate, candidate_store))
        return True

    monkeypatch.setattr(_recovery, "_ref_exists", _count_ref)
    services.project_health(project["id"], store=store)

    assert len(calls) == 1
    assert calls[0][1] == ref


def test_project_health_keeps_distinct_reference_anchors(store, monkeypatch):
    """Anchor validity is part of a reference address; quote/role prose is not."""
    from sonaloop.services import _recovery

    project = services.start_project(
        "Health anchored reference cache", "Question", methodology=None, store=store)
    refs = [
        {"kind": "session", "id": "same-session", "anchor": "step:1", "quote": "First"},
        {"kind": "session", "id": "same-session", "anchor": "step:1", "quote": "Retold"},
        {"kind": "session", "id": "same-session", "anchor": "step:2", "quote": "Second"},
    ]
    store.upsert_synthesis({
        "id": "synthesis_anchored_health_refs",
        "title": "Anchored references",
        "project_id": project["id"],
        "scope": "convergence",
        "status": "done",
        "created_at": "2026-08-11T00:00:00Z",
        "council_ids": [],
        "statements": [],
        "findings": [],
        "claim_posture": {
            "schema": "sonaloop.claim_posture.v1",
            "verified": True,
            "prose_uncovered": False,
            "counts": {"inferred": 3, "unsupported": 0},
            "claims": [
                {"id": f"claim-{index}", "text": "Anchored source", "posture": "inferred",
                 "refs": [ref]}
                for index, ref in enumerate(refs)
            ],
        },
    })
    calls = []

    def _count_ref(project_id, candidate, candidate_store):
        calls.append((project_id, candidate, candidate_store))
        return True

    monkeypatch.setattr(_recovery, "_ref_exists", _count_ref)
    services.project_health(project["id"], store=store)

    assert [call[1]["anchor"] for call in calls] == ["step:1", "step:2"]


def test_project_health_fails_closed_for_malformed_legacy_reference(store):
    project = services.start_project(
        "Malformed health reference", "Question", methodology=None, store=store)
    store.upsert_synthesis({
        "id": "synthesis_malformed_health_ref",
        "title": "Malformed reference",
        "project_id": project["id"],
        "scope": "convergence",
        "status": "done",
        "created_at": "2026-08-11T00:00:00Z",
        "council_ids": [],
        "statements": [],
        "findings": [],
        "claim_posture": {
            "schema": "sonaloop.claim_posture.v1",
            "verified": True,
            "prose_uncovered": False,
            "counts": {"inferred": 1, "unsupported": 0},
            "claims": [{"id": "claim-bad", "text": "Bad source", "posture": "inferred",
                        "refs": [["not", "a", "ref"]]}],
        },
    })

    health = services.project_health(project["id"], store=store)

    assert any(issue["code"] == "invalid_evidence_ref"
               for issue in health["integrity_findings"])


def test_project_health_distinguishes_never_started_stalled_and_expired(store):
    never = services.start_project(
        "Created only", "q", methodology="double_diamond", store=store)
    never_health = services.project_health(never["id"], stale_hours=1, store=store)
    assert never_health["state"] == "stalled"
    assert never_health["driver_state"] == "not_started"
    assert never_health["run_inventory"] == {
        "active": 0, "historical_finished": 0, "total": 0,
    }
    assert never_health["unmet_invariant"]["code"] == "run_not_started"
    assert never_health["safe_next_action"]["kind"] == "start_governed_run"

    quiet = services.start_project(
        "Quiet owner", "q", methodology="double_diamond", store=store)
    run = services.start_run(quiet["id"], store=store)
    run["updated_at"] = (datetime.now(timezone.utc) - timedelta(hours=7)).isoformat()
    store.upsert_run(run)
    quiet_health = services.project_health(quiet["id"], store=store)
    assert quiet_health["state"] == "stalled"
    assert quiet_health["driver_state"] == "stalled"
    assert quiet_health["activity_lifecycle"]["state"] == "current"

    run["updated_at"] = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
    store.upsert_run(run)
    expired_health = services.project_health(quiet["id"], store=store)
    assert expired_health["state"] == "expired"
    assert expired_health["driver_state"] == "expired"
    assert expired_health["persisted_run_status"] == "active"
    assert expired_health["unverified_output"] is False
    assert expired_health["activity_lifecycle"]["resumable"] is True
    assert expired_health["run_inventory"]["total"] == 1
    assert expired_health["safe_next_action"]["kind"] == "resume_existing_run"
    assert any(row["code"] == "run_expired"
               for row in expired_health["integrity_findings"])


def test_project_health_prefers_a_newer_stopped_attempt_over_historical_finish(store):
    project = services.start_project("Reopened then stopped", "q", store=store)
    finished = services.start_run(
        project["id"], operation_id="history:finished", store=store,
    )
    finished["status"] = "finished"
    finished["updated_at"] = "2026-08-08T10:00:00+00:00"
    store.upsert_run(finished)
    newer = services.start_run(
        project["id"], operation_id="history:stopped", store=store,
    )
    services.finish_run(newer["run_id"], "stopped", store=store)

    health = services.project_health(project["id"], store=store)

    assert health["run_id"] == newer["run_id"]
    assert health["driver_state"] == "stopped"
    assert health["state"] == "stalled"
    assert health["safe_next_action"]["kind"] == "start_governed_run"


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
    lineage_tag = page[page.rindex("<details", 0, page.index('id="project-lineage"')):
                       page.index(">", page.index('id="project-lineage"')) + 1]
    assert 'class="sl-project-lineage"' in lineage_tag and " open" not in lineage_tag
    project_head = page.split('class="proj-head"', 1)[1].split('class="outlinecard', 1)[0]
    assert 'id="project-lineage"' in project_head

    archive_only = services.start_project(
        "Archived only", "q", operation_id="archive-only-create", store=store)
    services.archive_project(
        archive_only["id"], "archive:only", "Operator archived this record", store=store)
    archived_page = TestClient(web.create_app()).get(
        f'/jobs/{archive_only["id"]}?lang=en').text
    archived_head = archived_page.split('class="proj-head"', 1)[1].split(
        'class="outlinecard', 1)[0]
    assert 'data-project-archived' in archived_head
    assert "Archived; evidence is preserved." in archived_head
    assert 'id="project-lineage"' not in archived_page

    active = services.start_project("Active", "q", operation_id="active-create", store=store)
    services.start_run(active["id"], operation_id="active-run", store=store)
    with pytest.raises(ValueError, match="ACTIVE_RUN_ARCHIVE_BLOCKED"):
        services.archive_project(active["id"], "archive:active", "Do not race", store=store)


def test_jobs_overview_hides_archived_before_search_count_and_enrichment(store, monkeypatch):
    active = services.start_project(
        "VISIBLE CURRENT JOB", "q", operation_id="overview:active", store=store)
    archived = services.start_project(
        "HIDDEN ARCHIVED JOB", "q", operation_id="overview:archived", store=store)
    services.archive_project(
        archived["id"], "overview:archive", "Preserve completed historical work", store=store)

    enriched_ids = []
    original_enrich = services._research.enrich_research_project

    def track_enrichment(project, scoped_store, _batch=None):
        enriched_ids.append(project["id"])
        return original_enrich(project, scoped_store, _batch=_batch)

    monkeypatch.setattr(services._research, "enrich_research_project", track_enrichment)
    client = TestClient(web.create_app())

    overview = client.get("/jobs?lang=en").text
    assert f'href="/jobs/{active["id"]}"' in overview
    assert f'href="/jobs/{archived["id"]}"' not in overview
    assert 'class="h1cnt">1<' in overview
    assert enriched_ids == [active["id"]]

    active_search = client.get("/jobs", params={"q": "VISIBLE CURRENT", "lang": "en"}).text
    assert f'href="/jobs/{active["id"]}"' in active_search
    assert f'href="/jobs/{archived["id"]}"' not in active_search

    archive_search = client.get("/jobs", params={"q": "HIDDEN ARCHIVED", "lang": "en"}).text
    assert f'href="/jobs/{archived["id"]}"' not in archive_search
    assert "No jobs yet." in archive_search

    # Archiving changes overview membership, not evidence retention or addressability.
    detail = client.get(f'/jobs/{archived["id"]}?lang=en').text
    assert archived["title"] in detail
    assert "Archived; evidence is preserved." in detail


def test_archived_only_history_is_empty_overview_not_fresh_database(store):
    archived = services.start_project(
        "ONLY ARCHIVED HISTORY", "q", operation_id="overview:archive-only", store=store)
    services.archive_project(
        archived["id"], "overview:archive-only:apply", "Keep evidence", store=store)
    client = TestClient(web.create_app())

    for path in ("/jobs?lang=en", "/?lang=en"):
        overview = client.get(path).text
        assert f'href="/jobs/{archived["id"]}"' not in overview
        assert "No jobs yet." in overview
        assert "First steps" not in overview

    # An unrelated/unknown status remains normal work; only the exact archive
    # lifecycle is hidden by this overview policy.
    legacy = services.start_project(
        "VISIBLE LEGACY STATUS", "q", operation_id="overview:legacy-status", store=store)
    legacy_row = store.get_research_project(legacy["id"])
    legacy_row.pop("status", None)
    store.conn.execute(
        "UPDATE research_projects SET data=? WHERE id=?",
        (json.dumps(legacy_row, ensure_ascii=False), legacy["id"]),
    )
    store.conn.commit()
    overview = client.get("/jobs?lang=en").text
    assert f'href="/jobs/{legacy["id"]}"' in overview
    assert f'href="/jobs/{archived["id"]}"' not in overview


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
    for language, verified, sources, absences, unknown, compact, technical in (
        ("en", "Claim provenance complete", "Sources", "verified absences", "unknown",
         "2 of 3 product areas evidenced · 1 still open", "Technical reference"),
        ("de", "Claim-Herkunft vollständig", "Quellen", "verifizierte Abwesenheiten", "unbekannt",
         "2 von 3 Produktbereichen belegt · 1 noch offen", "Technische Referenz"),
    ):
        council_html = client.get(f'/councils/{council["id"]}?lang={language}').text
        report_html = client.get(f'/syntheses/{synthesis["id"]}?lang={language}').text
        for html in (council_html, report_html):
            assert verified in html and sources in html
            assert 'id="claim-health"' in html and 'role="status"' in html
            assert 'class="claim-notice claim-notice--verified"' in html
            assert ref["id"] in html and "Product Understanding" in html
            assert absences in html and unknown in html
            assert compact in html and technical not in html
            # Trust/evidence blocks precede authored result prose.
            assert html.index('id="claim-health"') < html.index('id="product-understanding"')
        assert report_html.index('id="product-understanding"') < report_html.index("captured state and simulated")
        # Claim health is quiet supporting structure, not a second alert card. Status remains
        # explicit in DOM copy/icon/ARIA instead of a redundant coloured left rail.
        assert ('claim-notice{display:flex;align-items:flex-start;gap:9px;border:0;'
                'border-bottom:1px solid var(--line);border-radius:0;background:transparent') in report_html
        assert '.claim-notice--verified{border-left-color:' not in report_html


def test_project_keeps_persisted_setup_evidence_in_one_closed_quiet_disclosure(store):
    project, _run, ref, _understanding = _reaction_with_understanding(store, "project-setup")
    page = TestClient(web.create_app()).get(f'/jobs/{project["id"]}?lang=en').text

    marker = page.index('id="research-setup-details"')
    details_tag = page[page.rindex("<details", 0, marker):page.index(">", marker) + 1]
    assert 'class="sl-project-setup"' in details_tag and " open" not in details_tag
    assert "Research setup details" in page
    assert 'id="product-understanding"' in page and ref["id"] in page
    assert 'class="sl-integrity sl-integrity--product sl-integrity--embedded"' in page
    assert "2 of 3 product areas evidenced · 1 still open" in page
    assert "Evidenced product areas (2)" in page
    assert "Areas still to verify (1)" in page
    assert "Technical reference" not in page
    assert "flow manifest" not in page and "Manifest digest" not in page
    # Project evidence uses a flat, nested disclosure, not a full-width status
    # card or a permanently expanded technical inventory.
    setup = page[marker:page.index('class="outlinecard', marker)]
    assert 'class="sl-pu-card"' not in setup
    assert "border-left:3px" not in setup


def test_mcp_and_cli_recovery_surface_is_present():
    names = {tool.name for tool in build_server()._tool_manager.list_tools()}
    assert {"project_health", "resume_project_run", "supersede_project", "archive_project"} <= names
    from sonaloop.cli import build_parser
    parser = build_parser()
    assert parser.parse_args(["project-health", "p1"]).command == "project-health"
    assert parser.parse_args(["run-resume", "p1", "r1"]).run_id == "r1"
