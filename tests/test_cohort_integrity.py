"""Cohort depth/leakage preflight: circular Fink shape and deep independent cohort."""
from __future__ import annotations

import asyncio
import base64

import pytest

from sonaloop import plan as P
from sonaloop import services
from sonaloop.cohort_integrity import (
    COHORT_FEATURE_SCHEMA,
    COHORT_POLICY_VERSION,
    DEFAULT_THRESHOLDS,
    SEMANTIC_OVERLAP_SCHEMA,
)
from sonaloop.mcp_server import build_server
from sonaloop.research_integrity import IntegrityError


def _profile(name: str, source_phrase: str) -> dict:
    return {
        "display_name": name,
        "identity_traits": {key: "unspecified" for key in (
            "gender_presentation", "gender_confidence", "age_range",
            "appearance_notes", "avatar_profile", "avatar_constraints")},
        "segment": {"customer_type": "operations", "market": "synthetic",
                    "region": "DACH", "firm_size": "20"},
        "demographics": {"age": 39},
        "role": {"title": "Operations lead", "responsibilities": source_phrase,
                 "seniority": "lead", "decision_power": "shared"},
        "company_context": {"industry": "services", "size": "small",
                            "stack": "ordinary office tools", "operating_model": "team"},
        "goals": [source_phrase], "constraints": ["limited time"],
        "tool_ids": ["e_mail"], "tools": ["E-Mail"],
        "relationships": [{"name": "Team", "type": "colleague", "friction": "handoffs"}],
        "personality": {"working_style": "pragmatic", "communication_style": "direct",
                        "risk_tolerance": "medium", "character_notes": "questions assumptions"},
        "pain_points": [source_phrase], "success_criteria": [source_phrase],
    }


def _persona(store, name: str, phrase: str, *, source: str | None = None) -> str:
    row = services.record_persona(source or f"{name}: {phrase}", _profile(name, phrase), store=store)
    return row["id"]


def _deepen(store, persona_id: str, *, prefix: str) -> None:
    persona = store.get_persona(persona_id)
    persona["created_at"] = "2026-01-01T08:00:00Z"
    persona["updated_at"] = "2026-01-01T08:00:00Z"
    persona.setdefault("provenance", {})["grounding"] = "independent interview + work diary"
    store.upsert_persona(persona, reason="fixture independent history")
    for index in range(3):
        store.insert_experience_event({
            "id": f"event_{prefix}_{index}", "persona_id": persona_id,
            "timestamp": f"2026-01-0{index + 2}T09:00:00Z", "event_type": "ordinary_work",
            "summary": f"{prefix} handled a routine supplier handoff {index}",
        })
        store.insert_entity_fact({
            "id": f"fact_{prefix}_{index}", "persona_id": persona_id,
            "entity_id": f"entity_{prefix}", "fact": f"routine context {index}",
            "status": "active", "t_valid": f"2026-01-0{index + 2}T09:00:00Z",
            "t_invalid": None, "importance": 2, "source_event_id": f"event_{prefix}_{index}",
            "created_at": f"2026-01-0{index + 2}T09:00:00Z",
        })
    store.insert_evidence({
        "id": f"evidence_{prefix}", "persona_id": persona_id,
        "source_type": "synthetic_interview_fixture",
        "content_or_path": "The existing manual checklist is sufficient; a new product is not a priority.",
        "notes": "privacy-safe independent disconfirming evidence",
        "created_at": "2026-01-02T08:00:00Z",
    })


def _product_preflight(store, project_id: str, run_id: str) -> dict:
    dispatch = services.run_step(run_id, store=store)
    assert dispatch["step_id"] == "preflight__product_understanding"
    asset = services.attach_asset(
        project_id, content_base64=base64.b64encode(b"synthetic product state").decode(),
        filename="state.txt", kind="document", title="Synthetic product state",
        dispatch_token=dispatch["dispatch_token"], store=store)
    ref = {"kind": "asset", "id": asset["id"]}
    services.record_product_understanding(
        project_id, target={"name": "Synthetic workflow"}, revision="fixture:1",
        routes=[{"path": "/workspace", "evidence_refs": [ref]}],
        flows=[{"name": "Permission review", "evidence_refs": [ref]}],
        states=[{"state": "interrupted run", "evidence_refs": [ref]}],
        capabilities=[{"key": "resume", "claim": "A permission ledger can resume interrupted work",
                       "status": "observed_present", "evidence_refs": [ref]}],
        evidence_refs=[ref], observed_at="2026-08-08T10:00:00Z",
        dispatch_token=dispatch["dispatch_token"], store=store)
    return ref


def _start(store, suffix: str, persona_ids: list[str]):
    goal = ("Evaluate whether a visible permission ledger can resume interrupted research jobs "
            "without duplicate work.")
    project = services.start_project(
        f"Synthetic Fink gate {suffix}", goal, "Reaction Test", persona_ids,
        operation_id=f"cohort:{suffix}:project", store=store)
    run = services.start_run(project["id"], operation_id=f"cohort:{suffix}:run", store=store)
    ref = _product_preflight(store, project["id"], run["run_id"])
    dispatch = services.run_step(run["run_id"], store=store)
    assert dispatch["step_id"] == "frame__react"
    services.record_frame(
        project["id"], dispatch["step_id"],
        ["Which reactions would falsify the proposed workflow value?"],
        hypotheses=["The workflow value remains an unverified hypothesis."],
        memory_refs=["memory:fixture:independent-context"],
        dispatch_token=dispatch["dispatch_token"], store=store,
    )
    dispatch = services.run_step(run["run_id"], store=store)
    assert dispatch["step_id"] == "preflight__cohort_integrity"
    return project, run, dispatch, ref


def test_fink_shaped_fresh_profiles_trigger_versioned_reselection_and_real_plan_work(store):
    copied = ("Needs a visible permission ledger because interrupted research jobs must resume "
              "without duplicate work")
    p1 = _persona(store, "Synthetic Lea", copied)
    p2 = _persona(store, "Synthetic Niko", copied)
    project, run, dispatch, _ref = _start(store, "circular", [p1, p2])

    result = services.record_cohort_preflight(
        project["id"],
        representation=[
            {"persona_id": p1, "posture": "target", "rationale": "matches the intended role"},
            {"persona_id": p2, "posture": "skeptical",
             "rationale": "challenges whether the seeded problem is real"},
        ],
        dispatch_token=dispatch["dispatch_token"], store=store)

    assert result["schema"] == "sonaloop.cohort_integrity.v1"
    assert result["policy_version"] == COHORT_POLICY_VERSION
    assert result["status"] == result["raw_status"] == "needs_reselection"
    assert result["thresholds"] == DEFAULT_THRESHOLDS
    assert set(result["leakage"]["circular_persona_ids"]) == {p1, p2}
    assert all(row["feature_schema"] == COHORT_FEATURE_SCHEMA
               and row["score"] >= DEFAULT_THRESHOLDS["lexical_overlap_reselection"]
               for row in result["leakage"]["lexical"])
    assert result["depth"]["totals"]["events"] == 0
    assert all(row["source_provenance"]["origin"] == "authored"
               for row in result["depth"]["personas"])
    assert all(row["fresh_profile_at_project_start"] for row in result["depth"]["personas"])
    assert {row["code"] for row in result["required_work"]} >= {
        "HYPOTHESIS_PROFILE_LEAKAGE", "INDEPENDENT_CONTEXT_TOO_THIN",
        "COUNTERVOICE_UNVERIFIED"}
    assert result["representation"]["satisfied"] is False
    assert result["dispatch"]["checkpointed"] is True

    plan = services.get_plan(project["id"], store=store)
    remediation = next(row for row in plan["tasks"]
                       if row["id"] == result["remediation_task_id"])
    assert remediation["status"] == "todo" and remediation["capability"] == "cohort_integrity"
    frame = next(row for row in plan["tasks"] if row["id"] == "frame__react")
    assert frame["consumes"] == ["preflight__product_understanding"]
    downstream = [row for row in plan["tasks"]
                  if row["bucket"] != "analyze" and row["id"] != remediation["id"]]
    assert downstream and all(remediation["id"] in row["consumes"] for row in downstream)
    nxt = services.run_step(run["run_id"], store=store)
    assert nxt["step_id"] == remediation["id"] and nxt["kind"] == "analyze"


def test_deep_independent_cohort_passes_and_retains_disconfirming_sources(store):
    p1 = _persona(store, "Synthetic Mara", "Coordinates supplier handoffs and weekly schedules")
    p2 = _persona(store, "Synthetic Ozan", "Reviews support queues and resolves routine escalations")
    _deepen(store, p1, prefix="mara")
    _deepen(store, p2, prefix="ozan")
    project, run, dispatch, _ref = _start(store, "deep", [p1, p2])

    result = services.record_cohort_preflight(
        project["id"],
        representation=[
            {"persona_id": p1, "posture": "target",
             "rationale": "owns an adjacent operational workflow"},
            {"persona_id": p2, "posture": "indifferent",
             "rationale": "reports no relevance to the routine support task",
             "basis_quote": "existing manual checklist is sufficient",
             "evidence_refs": [{"kind": "evidence", "id": "evidence_ozan"}]},
        ],
        dispatch_token=dispatch["dispatch_token"], store=store)

    assert result["status"] == "pass" and result["required_work"] == []
    totals = result["depth"]["totals"]
    assert totals["personas"] == 2
    assert totals["facts"] >= 6 and totals["events"] >= 6 and totals["evidence"] >= 2
    for row in result["depth"]["personas"]:
        assert row["thin"] is False
        assert row["profile_age_hours_at_project_start"] > 24
        assert row["fresh_profile_at_project_start"] is False
        assert row["source_provenance"]["origin"] == "grounded"
        assert row["source_provenance"]["independent_evidence_sources"]
    # The preflight reads and fingerprints independent disconfirming evidence; it never rewrites it.
    assert "not a priority" in store.list_evidence(p1)[0]["content_or_path"]
    refreshed = store.get_research_project(project["id"])
    from sonaloop.cohort_integrity import preflight_satisfies_project
    assert preflight_satisfies_project(refreshed, store) is True


def test_final_gate_binds_frame_hypotheses_and_later_change_fails_closed(store):
    copied = "Coordinates quarterly inventory rotation across three warehouse teams"
    p1 = _persona(store, "Synthetic Thin", copied)
    p2 = _persona(store, "Synthetic Deep A", "Reviews ordinary service queue handoffs")
    p3 = _persona(store, "Synthetic Deep B", "Maintains weekly supplier schedules")
    _deepen(store, p2, prefix="frame_deep_a")
    _deepen(store, p3, prefix="frame_deep_b")
    project, _run, dispatch, _ref = _start(store, "frame-bound", [p1, p2, p3])
    result = services.record_cohort_preflight(
        project["id"],
        representation=[
            {"persona_id": p1, "posture": "target", "rationale": "thin target contrast"},
            {"persona_id": p2, "posture": "indifferent", "rationale": "independent neutral contrast",
             "basis_quote": "existing manual checklist is sufficient",
             "evidence_refs": [{"kind": "evidence", "id": "evidence_frame_deep_a"}]},
            {"persona_id": p3, "posture": "skeptical", "rationale": "independent skeptical contrast",
             "basis_quote": "new product is not a priority",
             "evidence_refs": [{"kind": "evidence", "id": "evidence_frame_deep_b"}]},
        ], dispatch_token=dispatch["dispatch_token"], store=store)
    assert result["status"] == "pass"
    boundary = result["stimulus_boundary"]
    assert boundary["frame_ids"] == ["frame__react"]
    assert boundary["frame_hypotheses_count"] == 1

    # Governed frame writes are immutable. Simulate a storage repair/migration changing the
    # persisted root frame anyway: the digest binding makes the old pass stale and the next
    # deterministic preview detects the newly copied hypothesis.
    plan = P.get_plan(project["id"], store=store)
    frame = next(row for row in plan["tasks"] if row["id"] == "frame__react")
    frame["frame"]["hypotheses"] = [copied]
    P.save_plan(plan, store=store)
    current_project = store.get_research_project(project["id"])
    from sonaloop.cohort_integrity import preflight_satisfies_project
    assert preflight_satisfies_project(current_project, store) is False
    preview = services.brief_cohort_preflight(project["id"], store=store)["preview"]
    assert preview["status"] == "needs_reselection"
    assert preview["leakage"]["circular_persona_ids"] == [p1]
    from sonaloop.research_integrity import reaction_task_gaps
    gaps = reaction_task_gaps(
        project["id"], {"bucket": "act", "produces": []}, P.get_plan(project["id"], store=store), store)
    assert any("stale" in gap for gap in gaps)


def test_deep_profile_overlap_still_requires_reselection_and_goal_edits_stale_pass(store):
    copied = "The workflow value remains an unverified hypothesis"
    p1 = _persona(store, "Synthetic Deep Leak", copied)
    p2 = _persona(store, "Synthetic Independent", "Maintains ordinary support schedules")
    _deepen(store, p1, prefix="deep_leak")
    _deepen(store, p2, prefix="deep_independent")
    project, _run, dispatch, _ref = _start(store, "deep-leak", [p1, p2])
    leaked = services.record_cohort_preflight(
        project["id"], representation=[
            {"persona_id": p1, "posture": "target", "rationale": "deep target profile"},
            {"persona_id": p2, "posture": "skeptical", "rationale": "independent countervoice",
             "basis_quote": "new product is not a priority",
             "evidence_refs": [{"kind": "evidence", "id": "evidence_deep_independent"}]},
        ], dispatch_token=dispatch["dispatch_token"], store=store)
    assert leaked["depth"]["totals"]["thin"] == 0
    assert leaked["status"] == "needs_reselection"
    assert leaked["leakage"]["high_overlap_persona_ids"] == [p1]

    # A separate non-overlapping cohort pass becomes stale on either mutable project stimulus field.
    q1 = _persona(store, "Synthetic Goal A", "Coordinates ordinary calendar handoffs")
    q2 = _persona(store, "Synthetic Goal B", "Reviews routine support queues")
    _deepen(store, q1, prefix="goal_a")
    _deepen(store, q2, prefix="goal_b")
    passed_project, _passed_run, passed_dispatch, _ = _start(store, "goal-stale", [q1, q2])
    passed = services.record_cohort_preflight(
        passed_project["id"], representation=[
            {"persona_id": q1, "posture": "target", "rationale": "independent target"},
            {"persona_id": q2, "posture": "indifferent", "rationale": "independent neutral",
             "basis_quote": "existing manual checklist is sufficient",
             "evidence_refs": [{"kind": "evidence", "id": "evidence_goal_b"}]},
        ], dispatch_token=passed_dispatch["dispatch_token"], store=store)
    assert passed["status"] == "pass"
    from sonaloop.cohort_integrity import preflight_satisfies_project
    edited = store.get_research_project(passed_project["id"])
    assert preflight_satisfies_project(edited, store)
    edited["goal"] = edited["goal"] + " Changed after the gate."
    store.upsert_research_project(edited)
    assert not preflight_satisfies_project(store.get_research_project(edited["id"]), store)
    edited = store.get_research_project(edited["id"])
    edited["goal"] = passed_project["goal"]
    edited["description"] = "A newly added stimulus description"
    store.upsert_research_project(edited)
    assert not preflight_satisfies_project(store.get_research_project(edited["id"]), store)


def test_grounded_countervoice_must_express_matching_council_stance(store):
    p1 = _persona(store, "Synthetic Council Target", "Coordinates ordinary supplier schedules")
    p2 = _persona(store, "Synthetic Council Skeptic", "Reviews routine service queues")
    _deepen(store, p1, prefix="council_target")
    _deepen(store, p2, prefix="council_skeptic")
    project, run, dispatch, stimulus_ref = _start(store, "countervoice-stance", [p1, p2])
    gate = services.record_cohort_preflight(
        project["id"], representation=[
            {"persona_id": p1, "posture": "target", "rationale": "independent target"},
            {"persona_id": p2, "posture": "skeptical", "rationale": "independent skeptic",
             "basis_quote": "new product is not a priority",
             "evidence_refs": [{"kind": "evidence", "id": "evidence_council_skeptic"}]},
        ], dispatch_token=dispatch["dispatch_token"], store=store)
    assert gate["status"] == "pass"
    act = next(task for task in services.get_plan(project["id"], store=store)["tasks"]
               if task["id"] == "act__react__comprehension")
    act_dispatch = services.run_step(run["run_id"], store=store)
    assert act_dispatch["step_id"] == act["id"]
    ref = {"kind": "asset", "id": stimulus_ref["id"]}
    base = {
        "project_id": project["id"], "prompt": "React to the bounded stimulus",
        "persona_ids": [p1, p2], "summary": "Mixed simulated reactions.",
        "claims": [{"text": "The synthetic reactions were mixed.",
                    "posture": "simulated", "refs": [ref]}],
        "dispatch_token": act_dispatch["dispatch_token"], "store": store,
    }
    mismatched = services.record_council(
        **base, statements=[
            {"persona_id": p1, "text": "This may help.", "stance": {"value": 1}, "refs": [ref]},
            {"persona_id": p2, "text": "I also support it.", "stance": {"value": 1}, "refs": [ref]},
        ])
    assert mismatched["dispatch"]["checkpointed"] is False
    assert next(row for row in services.get_plan(project["id"], store=store)["tasks"]
                if row["id"] == act["id"])["status"] != "done"
    repaired = services.record_council(
        **base, statements=[
            {"persona_id": p1, "text": "This may help.", "stance": {"value": 1}, "refs": [ref]},
            {"persona_id": p2, "text": "The evidence does not justify it.",
             "stance": {"value": -1}, "refs": [ref]},
        ])
    assert repaired["dispatch"]["checkpointed"] is True


def test_optional_semantic_feature_is_provider_neutral_and_input_bound(store):
    p1 = _persona(store, "Synthetic Ada", "Coordinates supplier handoffs")
    p2 = _persona(store, "Synthetic Bo", "Maintains a weekly support rota")
    project, _run, dispatch, _ref = _start(store, "semantic", [p1, p2])
    brief = services.brief_cohort_preflight(project["id"], store=store)
    inputs = brief["required_input"]["semantic_feature"]["input_digests"]
    feature = {
        "schema": SEMANTIC_OVERLAP_SCHEMA,
        "feature_version": "cosine-similarity.v1",
        "model_id": "provider-neutral-test-vector-space",
        "scores": [{"persona_id": pid, "input_digest": inputs[pid], "score": 0.91}
                   for pid in (p1, p2)],
    }
    result = services.record_cohort_preflight(
        project["id"], semantic_feature=feature,
        representation=[
            {"persona_id": p1, "posture": "target", "rationale": "adjacent workflow owner"},
            {"persona_id": p2, "posture": "non_target", "rationale": "deliberate non-target"},
        ], dispatch_token=dispatch["dispatch_token"], store=store)
    assert result["status"] == "needs_reselection"
    assert result["leakage"]["semantic"]["threshold"] == \
        DEFAULT_THRESHOLDS["semantic_overlap_reselection"]
    assert result["leakage"]["semantic"]["model_id"] == "provider-neutral-test-vector-space"

    # A score for stale/different text cannot be attached to the current cohort.
    p3 = _persona(store, "Synthetic Cy", "Schedules ordinary team meetings")
    next_dispatch = services.run_step(_run["run_id"], store=store)
    with pytest.raises(IntegrityError) as exc:
        services.record_cohort_preflight(
            project["id"], persona_ids=[p1, p3],
            selection_rationale="replace one leaked fixture profile",
            semantic_feature=feature,
            representation=[
                {"persona_id": p1, "posture": "target", "rationale": "adjacent workflow owner"},
                {"persona_id": p3, "posture": "skeptical", "rationale": "questions relevance"},
            ], dispatch_token=next_dispatch["dispatch_token"], store=store)
    assert exc.value.code in {"BAD_SEMANTIC_FEATURE", "SEMANTIC_INPUT_MISMATCH"}


def test_override_requires_rationale_and_survives_in_report_limitations(store):
    p1 = _persona(store, "Synthetic Dia", "Coordinates weekly schedules")
    p2 = _persona(store, "Synthetic Eli", "Tracks a routine service queue")
    project, _run, dispatch, _ref = _start(store, "override", [p1, p2])
    representation = [
        {"persona_id": p1, "posture": "target", "rationale": "adjacent role"},
        {"persona_id": p2, "posture": "skeptical", "rationale": "questions the premise"},
    ]
    with pytest.raises(IntegrityError) as exc:
        services.record_cohort_preflight(
            project["id"], representation=representation,
            override_rationale="too short", dispatch_token=dispatch["dispatch_token"], store=store)
    assert exc.value.code == "COHORT_OVERRIDE_RATIONALE_REQUIRED"

    result = services.record_cohort_preflight(
        project["id"], representation=representation,
        override_rationale=("Time-boxed directional exercise; the result must not be treated as "
                            "independent validation."),
        dispatch_token=dispatch["dispatch_token"], store=store)
    assert result["status"] == "overridden" and result["raw_status"] == "needs_reselection"
    report = services.scaffold_synthesis(project["id"], store=store)
    assert report["limitations"][0]["cohort_preflight_id"] == result["id"]
    exported = services.export_report(project["id"], report["id"], store=store)
    assert "Limitations" in exported and "Time-boxed directional exercise" in exported
    assert services.get_cohort_preflight(project["id"], store=store)["limitations"]
    from sonaloop.web._cohort_integrity_view import render_cohort_integrity
    rendered = render_cohort_integrity(store.get_research_project(project["id"]), store)
    assert "Cohort Integrity" in rendered
    assert "Time-boxed directional exercise" in rendered


def test_mcp_and_cli_contract_expose_structured_cohort_gate():
    tools = {row.name: row for row in asyncio.run(build_server().list_tools())}
    assert {"brief_cohort_preflight", "record_cohort_preflight",
            "get_cohort_preflight"} <= tools.keys()
    props = tools["record_cohort_preflight"].inputSchema["properties"]
    assert {"representation", "semantic_feature", "override_rationale", "persona_ids",
            "selection_rationale", "dispatch_token"} <= props.keys()
