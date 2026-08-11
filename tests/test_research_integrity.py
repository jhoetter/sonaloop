"""Reaction-Test integrity and governed-dispatch regression coverage."""
from __future__ import annotations

import base64
import asyncio

import pytest

from sonaloop import plan as P
from sonaloop import services
from sonaloop.research_integrity import IntegrityError, resolve_project_ref
from sonaloop.mcp_server import build_server


def _strict_reaction(store, suffix: str = "one"):
    project = services.start_project(
        f"Reaction {suffix}", "Can users understand the real product?",
        methodology="Reaction Test", persona_ids=["persona_a", "persona_b"],
        operation_id=f"test:reaction:{suffix}", store=store,
    )
    run = services.start_run(
        project["id"], operation_id=f"test:reaction-run:{suffix}", store=store)
    dispatch = services.run_step(run["run_id"], store=store)
    assert dispatch["kind"] == "analyze"
    assert dispatch["step_id"] == "preflight__product_understanding"
    assert dispatch["dispatch_token"]
    return project, run, dispatch


def _attach_screen(project_id: str, token: str, store):
    result = services.attach_asset(
        project_id, content_base64=base64.b64encode(b"real-screen-state").decode(),
        filename="home.png", kind="screenshot", title="Home state",
        dispatch_token=token, store=store,
    )
    assert result["dispatch"]["state"] == "linked"
    assert result["dispatch"]["checkpointed"] is False
    return result


def _record_understanding(project_id: str, token: str, asset_id: str, store):
    ref = {"kind": "asset", "id": asset_id}
    return services.record_product_understanding(
        project_id,
        target={"name": "SHKB website", "url": "https://example.test"},
        revision="deploy:abc123",
        routes=[{"path": "/", "evidence_refs": [ref]}],
        flows=[{"name": "Home to financing", "evidence_refs": [ref]}],
        states=[{"state": "home", "evidence_refs": [ref]}],
        capabilities=[
            {"key": "mortgage-navigation", "claim": "A financing route is visible",
             "status": "observed_present", "evidence_refs": [ref]},
            {"key": "calculator", "claim": "A calculator may exist deeper in the flow",
             "status": "unknown"},
        ],
        evidence_refs=[ref], observed_at="2026-08-08T10:00:00Z",
        dispatch_token=token, store=store,
    )


def _override_thin_fixture_cohort(project_id: str, run_id: str, store):
    """These legacy integrity tests use nonexistent persona ids on purpose; make that limitation explicit."""
    dispatch = services.run_step(run_id, store=store)
    assert dispatch["next_action"]["capability"] == "cohort_integrity"
    pids = store.get_research_project(project_id).get("persona_ids") or []
    representation = [
        {"persona_id": pid, "posture": "skeptical" if index else "target",
         "rationale": "legacy fixture countervoice" if index else "legacy fixture target"}
        for index, pid in enumerate(pids)
    ]
    return services.record_cohort_preflight(
        project_id, representation=representation,
        override_rationale=("Legacy dispatch-integrity fixture uses placeholder persona ids; "
                            "cohort quality is outside this test's scope."),
        dispatch_token=dispatch["dispatch_token"], store=store)


def _record_fixture_frame(project_id: str, run_id: str, store, *, question: str,
                          hypotheses: list[str] | None = None):
    dispatch = services.run_step(run_id, store=store)
    assert dispatch["next_action"]["capability"] == "frame"
    result = services.record_frame(
        project_id, dispatch["step_id"], [question], hypotheses=hypotheses or [],
        memory_refs=["memory:persona_a:recent"],
        dispatch_token=dispatch["dispatch_token"], store=store)
    return dispatch, result


def test_product_understanding_is_mandatory_versioned_and_auto_checkpointed(store):
    project, run, dispatch = _strict_reaction(store)
    pid, token = project["id"], dispatch["dispatch_token"]

    with pytest.raises(P.PlanError) as bypass:
        services.record_frame(pid, dispatch["step_id"], ["Can users find it?"],
                              memory_refs=["memory:persona_a:day"],
                              dispatch_token=token, store=store)
    assert bypass.value.code in {"PRODUCT_UNDERSTANDING_REQUIRED", "DISPATCH_OUTPUT_KIND_CONFLICT"}

    screen = _attach_screen(pid, token, store)
    result = _record_understanding(pid, token, screen["id"], store)
    assert result["schema"] == "sonaloop.product_understanding.v1"
    assert result["dispatch"]["state"] == "completed"
    assert result["dispatch"]["checkpointed"] is True
    assert services.get_plan(pid, store=store)["tasks"][0]["status"] == "done"
    journal = services.run_journal(run["run_id"], store=store)
    assert len(journal["steps"]) == 1
    assert journal["steps"][0]["dispatch_token"] == token
    assert f"product_understanding:{result['id']}" in journal["steps"][0]["produced_refs"]

    # Exact transport replay resolves one immutable version and one checkpoint.
    replay = _record_understanding(pid, token, screen["id"], store)
    assert replay["id"] == result["id"] and replay["idempotent_replay"] is True
    assert replay["dispatch"]["receipt"]["deduplicated"] is True
    assert len(services.get_product_understanding(pid, store=store)["history"]) == 1
    assert len(services.run_journal(run["run_id"], store=store)["steps"]) == 1
    graph = services.get_project_graph(pid, store=store)
    assert graph["project"]["product_understanding_current_id"] == result["id"]
    from sonaloop.web.pages.projects import _product_understanding_html
    rendered = _product_understanding_html(graph["project"])
    assert "Product Understanding" in rendered and "deploy:abc123" in rendered
    assert rendered.startswith('<details class="sl-integrity sl-integrity--product"')
    assert "1 of 2 product areas evidenced · 1 still open" in rendered
    assert "Evidenced product areas (1)" in rendered
    assert "Areas still to verify (1)" in rendered
    assert "Technical reference" in rendered
    assert 'class="sl-integrity-metrics"' in rendered
    assert "sl-pu-card" not in rendered and "sl-cohort-grid" not in rendered


def test_product_understanding_fails_closed_on_absence_without_verification(store):
    project, _run, dispatch = _strict_reaction(store, "absence")
    screen = _attach_screen(project["id"], dispatch["dispatch_token"], store)
    ref = {"kind": "asset", "id": screen["id"]}
    with pytest.raises(IntegrityError) as exc:
        services.record_product_understanding(
            project["id"], {"name": "App"}, "rev-1",
            routes=[{"path": "/", "evidence_refs": [ref]}], flows=[], states=[],
            capabilities=[{"claim": "There is no run-completion control",
                           "status": "observed_absent", "evidence_refs": [ref]}],
            evidence_refs=[ref], observed_at="2026-08-08T10:00:00Z",
            dispatch_token=dispatch["dispatch_token"], store=store,
        )
    assert exc.value.code == "ABSENCE_VERIFICATION_REQUIRED"
    with pytest.raises(KeyError):
        services.get_product_understanding(project["id"], store=store)


def test_governed_writes_reject_missing_wrong_scope_and_changed_frame_replay(store):
    project, run, dispatch = _strict_reaction(store, "scope")
    pid, token = project["id"], dispatch["dispatch_token"]
    with pytest.raises(P.PlanError) as missing:
        services.attach_asset(
            pid, content_base64=base64.b64encode(b"x").decode(), filename="x.png",
            store=store)
    assert missing.value.code == "DISPATCH_TOKEN_REQUIRED"

    other = services.start_project(
        "Other", "Other goal", methodology="Reaction Test",
        operation_id="test:reaction:other", store=store)
    with pytest.raises(P.PlanError) as scoped:
        services.attach_asset(
            other["id"], content_base64=base64.b64encode(b"x").decode(), filename="x.png",
            dispatch_token=token, store=store)
    assert scoped.value.code in {"UNKNOWN_DISPATCH_TOKEN", "DISPATCH_SCOPE_MISMATCH"}
    assert not (store.get_research_project(other["id"]).get("assets") or [])

    screen = _attach_screen(pid, token, store)
    _record_understanding(pid, token, screen["id"], store)
    frame_dispatch, first = _record_fixture_frame(
        pid, run["run_id"], store, question="Where does comprehension fail?")
    assert first["dispatch"]["checkpointed"] is True
    replay = services.record_frame(
        pid, frame_dispatch["step_id"], ["Where does comprehension fail?"],
        memory_refs=["memory:persona_a:recent"],
        dispatch_token=frame_dispatch["dispatch_token"], store=store)
    assert replay["dispatch"]["receipt"]["deduplicated"] is True
    with pytest.raises(P.PlanError) as changed:
        services.record_frame(
            pid, frame_dispatch["step_id"], ["A different question"],
            memory_refs=["memory:persona_a:recent"],
            dispatch_token=frame_dispatch["dispatch_token"], store=store)
    assert changed.value.code == "DISPATCH_OUTPUT_CONFLICT"
    _override_thin_fixture_cohort(pid, run["run_id"], store)


def test_reaction_council_requires_stimulus_posture_and_auto_links(store):
    project, run, dispatch = _strict_reaction(store, "council")
    pid = project["id"]
    screen = _attach_screen(pid, dispatch["dispatch_token"], store)
    _record_understanding(pid, dispatch["dispatch_token"], screen["id"], store)
    frame_dispatch, _frame = _record_fixture_frame(
        pid, run["run_id"], store, question="What does the home state communicate?")
    _override_thin_fixture_cohort(pid, run["run_id"], store)
    act = next(task for task in services.get_plan(pid, store=store)["tasks"]
               if task["id"] == "act__react__comprehension")
    act_dispatch = services.run_step(run["run_id"], store=store)
    assert act_dispatch["kind"] == "act"
    assert act_dispatch["step_id"] == act["id"]
    ref = {"kind": "asset", "id": screen["id"]}

    with pytest.raises(P.PlanError) as missing:
        services.record_council(
            pid, "React to the home state", ["persona_a"],
            statements=[{"persona_id": "persona_a", "text": "The route is clear.",
                         "refs": [ref]}], store=store)
    assert missing.value.code == "DISPATCH_TOKEN_REQUIRED"

    draft = services.record_council(
        pid, "React to the home state", ["persona_a"],
        statements=[{"persona_id": "persona_a", "text": "The route is clear.",
                     "refs": [ref]}],
        findings=[{"text": "The label looks understandable", "kind": "summary",
                   "refs": [ref], "meta": {"claim_posture": "inferred"}}],
        summary="The route works.", dispatch_token=act_dispatch["dispatch_token"], store=store)
    assert draft["dispatch"]["state"] == "linked"
    assert draft["claim_posture"]["prose_uncovered"] is True
    current_act = next(t for t in services.get_plan(pid, store=store)["tasks"]
                       if t["id"] == act["id"])
    assert current_act["status"] != "done"

    synthesis_ids_before = {row["id"] for row in store.list_syntheses()}
    with pytest.raises(P.PlanError) as wrong_kind:
        services.record_synthesis(
            "Wrong primary", "Must not share a council dispatch", [],
            payload={"gesamtbild": "This would be a second primary output."},
            project_id=pid, dispatch_token=act_dispatch["dispatch_token"], store=store)
    assert wrong_kind.value.code == "DISPATCH_OUTPUT_KIND_CONFLICT"
    assert {row["id"] for row in store.list_syntheses()} == synthesis_ids_before

    repaired = services.record_council(
        pid, "React to the home state", ["persona_a"],
        statements=[{"persona_id": "persona_a", "text": "The route is clear.",
                     "refs": [ref]}],
        findings=[{"text": "The label looks understandable", "kind": "summary",
                   "refs": [ref], "meta": {"claim_posture": "inferred"}}],
        summary="The route works.",
        claims=[{"text": "The simulated persona interpreted the label as a route.",
                 "posture": "simulated", "refs": [ref]}],
        dispatch_token=act_dispatch["dispatch_token"], store=store)
    assert repaired["id"] == draft["id"]
    assert repaired["claim_posture"]["verified"] is True
    assert repaired["dispatch"]["checkpointed"] is True
    stored = store.get_council_session(repaired["id"])
    assert stored["statements"][0]["meta"]["claim_posture"] == "simulated"
    assert stored["dispatch_provenance"]["dispatch_token"] == act_dispatch["dispatch_token"]
    assert stored["dispatch_provenance"]["payload_revision"] == 2
    replay = services.record_council(
        pid, "React to the home state", ["persona_a"],
        statements=[{"persona_id": "persona_a", "text": "The route is clear.",
                     "refs": [ref]}],
        findings=[{"text": "The label looks understandable", "kind": "summary",
                   "refs": [ref], "meta": {"claim_posture": "inferred"}}],
        summary="The route works.",
        claims=[{"text": "The simulated persona interpreted the label as a route.",
                 "posture": "simulated", "refs": [ref]}],
        dispatch_token=act_dispatch["dispatch_token"], store=store)
    assert replay["idempotent_replay"] is True
    assert replay["id"] == repaired["id"]
    assert replay["dispatch"]["receipt"]["deduplicated"] is True
    with pytest.raises(P.PlanError) as changed_after_commit:
        services.record_council(
            pid, "React to the home state", ["persona_a"],
            statements=[{"persona_id": "persona_a", "text": "The route is clear.",
                         "refs": [ref]}],
            summary="Changed after checkpoint",
            claims=[{"text": "The simulated persona interpreted the label as a route.",
                     "posture": "simulated", "refs": [ref]}],
            dispatch_token=act_dispatch["dispatch_token"], store=store)
    assert changed_after_commit.value.code == "DISPATCH_OUTPUT_CONFLICT"
    assert store.get_council_session(repaired["id"])["summary"] == "The route works."
    exported = services.export_council_session(repaired["id"], "md", store=store)
    assert "Claim provenance" in exported
    assert "`simulated`" in exported and "asset:" in exported


def test_observed_behavior_cannot_be_laundered_from_a_screenshot(store):
    project, run, dispatch = _strict_reaction(store, "observation")
    pid = project["id"]
    screen = _attach_screen(pid, dispatch["dispatch_token"], store)
    _record_understanding(pid, dispatch["dispatch_token"], screen["id"], store)
    frame_dispatch, _frame = _record_fixture_frame(
        pid, run["run_id"], store, question="What did users do?")
    _override_thin_fixture_cohort(pid, run["run_id"], store)
    act = next(task for task in services.get_plan(pid, store=store)["tasks"]
               if task["id"] == "act__react__comprehension")
    act_dispatch = services.run_step(run["run_id"], store=store)
    assert act_dispatch["step_id"] == act["id"]
    with pytest.raises(IntegrityError) as exc:
        services.record_council(
            pid, "What did the user do?", ["persona_a"],
            statements=[{"persona_id": "persona_a", "text": "I clicked the financing link.",
                         "refs": [{"kind": "asset", "id": screen["id"]}],
                         "meta": {"claim_posture": "observed"}}],
            dispatch_token=act_dispatch["dispatch_token"], store=store)
    assert exc.value.code == "OBSERVATION_EVIDENCE_REQUIRED"
    assert store.list_council_sessions() == []


def test_observed_behavior_anchor_must_name_a_real_session_step(store):
    project, _run, _dispatch = _strict_reaction(store, "real-step-anchor")
    session_id = "usession_grounded_anchor"
    store.insert_usability_session({
        "id": session_id,
        "project_id": project["id"],
        "persona_id": "persona_a",
        "subject": {"kind": "live_url", "url": "https://example.test"},
        "fidelity": "live",
        "grounded_verified": True,
        "steps": [{"index": 0, "state": {"screen": "home"}}],
        "created_at": "2026-08-08T10:00:00Z",
    })

    valid = resolve_project_ref(
        project["id"],
        {"kind": "session", "id": session_id, "anchor": "step:0"},
        store,
        observed_behavior=True,
    )
    assert valid["class"] == "grounded_observation"
    for anchor in ("step:1", "step:not-a-number", "step:-1"):
        with pytest.raises(IntegrityError) as exc:
            resolve_project_ref(
                project["id"],
                {"kind": "session", "id": session_id, "anchor": anchor},
                store,
                observed_behavior=True,
            )
        assert exc.value.code == "OBSERVATION_ANCHOR_REQUIRED"


def test_legacy_project_remains_backward_compatible_with_explicit_provenance(store):
    project = services.start_project("Legacy", "Old host", methodology=None, store=store)
    council = services.record_council(project["id"], "Q?", [], store=store)
    assert council["dispatch"]["state"] == "legacy"
    assert store.get_council_session(council["id"])["dispatch_provenance"]["state"] == "legacy"


def test_initialize_instructions_feature_detect_cloud_front_door_and_integrity_contract():
    instructions = build_server().instructions
    assert "if this host exposes `begin_research_job`" in instructions
    assert "exact same `begin_research_job` call" in instructions
    assert "never recover by calling start_project/start_run separately" in instructions
    assert "dispatch_token" in instructions and "auto-links + auto-checkpoints" in instructions
    assert "Product Understanding preflight" in instructions
    assert "Cohort Integrity preflight" in instructions
    assert "A screenshot proves product state, never observed user behavior" in instructions


def test_mcp_schemas_expose_product_preflight_claims_and_dispatch_tokens():
    tools = {tool.name: tool for tool in asyncio.run(build_server().list_tools())}
    assert {"brief_product_understanding", "record_product_understanding",
            "get_product_understanding", "brief_cohort_preflight",
            "record_cohort_preflight", "get_cohort_preflight"} <= tools.keys()
    pu = tools["record_product_understanding"].inputSchema["properties"]
    assert {"target", "revision", "routes", "flows", "states", "capabilities",
            "dispatch_token"} <= pu.keys()
    council = tools["record_council"].inputSchema["properties"]
    assert "claims" in council and "dispatch_token" in council
    synthesis = tools["record_synthesis"].inputSchema["properties"]
    assert "dispatch_token" in synthesis
    for name in ("record_frame", "record_judgment", "complete_task", "attach_asset",
                 "define_flow", "record_usability_session", "record_prototype_session"):
        assert "dispatch_token" in tools[name].inputSchema["properties"], name
