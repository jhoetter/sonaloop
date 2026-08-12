from __future__ import annotations

import pytest

from sonaloop import services
from sonaloop import plan as plan_mod


def _build_dispatch(store, suffix: str):
    project = services.start_project(
        f"Build dispatch {suffix}", "Build a testable artifact", None,
        persona_ids=["p1"], operation_id=f"build-project-{suffix}", store=store,
    )
    task = {
        "id": "act__build",
        "bucket": "act",
        "capability": "build",
        "expected_output_kind": "build",
        "title": "Build the artifact",
        "status": "ready",
        "consumes": [],
        "produces": [],
        "requires": {"min_inputs": 0},
    }
    plan_mod.save_plan({
        "project_id": project["id"], "goal": "Build a testable artifact", "tasks": [task],
    }, store=store)
    run = services.start_run(
        project["id"], operation_id=f"build-run-{suffix}", store=store)
    dispatch = services.run_step(run["run_id"], store=store)
    assert dispatch["kind"] == "act"
    return project, run, dispatch


def test_checkpoint_step_persists_trace_io_fields(store):
    project = services.start_project("Trace journal", "How might we trace run IO?", None,
                                     persona_ids=["p1"], store=store)
    run = services.start_run(project["id"], store=store)

    services.checkpoint_step(run["run_id"], {
        "task_id": "act__explore",
        "bucket": "act",
        "key": services.run_key(run["run_id"], "act__explore"),
        "evidence": ["council:c1"],
        "consume_refs": ["frame:frame__root"],
        "optional_context_refs": ["memory:p1:day"],
        "produced_refs": ["council:c1"],
        "downstream_refs": ["verify__define"],
        "open_questions": ["What matters?"],
        "parked_refs": ["url_artifact:u1"],
        "expected_output_kind": "explore",
        "summary": "ran council",
    }, store=store)

    entry = services.run_journal(run["run_id"], store=store)["steps"][0]
    assert entry["evidence"] == ["council:c1"]          # old callers still have the compatibility field
    assert entry["consume_refs"] == ["frame:frame__root"]
    assert entry["optional_context_refs"] == ["memory:p1:day"]
    assert entry["produced_refs"] == ["council:c1"]
    assert entry["downstream_refs"] == ["verify__define"]
    assert entry["open_questions"] == ["What matters?"]
    assert entry["parked_refs"] == ["url_artifact:u1"]
    assert entry["expected_output_kind"] == "explore"


def test_run_step_dispatch_exposes_trace_inputs_for_act_task(store):
    project = services.start_project("Trace dispatch", "How might we trace dispatch IO?", None,
                                     persona_ids=["p1"], store=store)
    pid = project["id"]
    run = services.start_run(pid, store=store)

    first = services.run_step(run["run_id"], store=store)
    assert first["kind"] == "analyze"
    assert first["consume_refs"] == []
    assert first["expected_output_kind"] == "frame"
    assert first["must_link_before_complete"] is False

    services.record_frame(pid, "frame__root", ["Which moment matters most?"],
                          memory_refs=["memory:p1:handover"],
                          dispatch_token=first["dispatch_token"], store=store)
    act = services.add_task(pid, "act", "explore", "Explore handover moments",
                            consumes=["frame__root"], store=store)

    second = services.run_step(run["run_id"], store=store)
    assert second["kind"] == "act"
    assert second["step_id"] == act["id"]
    assert second["consume_task_ids"] == ["frame__root"]
    assert second["consume_refs"] == ["frame:frame__root"]
    assert second["optional_context_refs"] == ["memory:p1:handover"]
    assert second["open_questions"] == ["Which moment matters most?"]
    assert second["expected_output_kind"] == "explore"
    assert second["must_link_before_complete"] is True
    persisted = next(
        row for row in store.get_run(run["run_id"])["dispatches"]
        if row["dispatch_token"] == second["dispatch_token"])
    assert persisted["dispatch_cursor"] == 1
    assert persisted["workspace_id"] == "local"
    assert len(persisted["input_fingerprint"]) == 64
    assert persisted["expected_output_kind"] == "explore"
    assert persisted["output_contract"]["max_primary_outputs"] == 1


def test_complete_task_without_trace_link_returns_nudge(store):
    project = services.start_project("Trace nudge", "How might we avoid silent orphans?", None,
                                     persona_ids=["p1"], store=store)
    pid = project["id"]
    services.record_frame(pid, "frame__root", ["Which output matters?"],
                          memory_refs=["memory:p1:handover"], store=store)
    act = services.add_task(pid, "act", "explore", "Explore without link",
                            consumes=["frame__root"], store=store)

    out = services.complete_task(pid, act["id"], store=store)
    assert out["trace_nudge"]["code"] == "TRACE_LINK_MISSING"
    assert out["trace_nudge"]["next_tool"] == "link_evidence"


def test_governed_complete_task_without_trace_link_fails_before_mutation(store):
    project = services.start_project(
        "Governed trace guard", "How might we prevent empty dispatches?", None,
        persona_ids=["p1"], operation_id="governed-trace-guard", store=store)
    run = services.start_run(
        project["id"], operation_id="governed-trace-guard-run", store=store)
    frame = services.run_step(run["run_id"], store=store)
    services.record_frame(
        project["id"], frame["step_id"], ["What output proves the work?"],
        memory_refs=["memory:p1:trace"], dispatch_token=frame["dispatch_token"], store=store)
    act = services.add_task(
        project["id"], "act", "session", "Record the observed session",
        consumes=["frame__root"], store=store)
    dispatch = services.run_step(run["run_id"], store=store)
    assert dispatch["step_id"] == act["id"]

    with pytest.raises(plan_mod.PlanError) as missing:
        services.complete_task(
            project["id"], act["id"], dispatch_token=dispatch["dispatch_token"], store=store)
    assert missing.value.code == "TRACE_LINK_MISSING"
    assert services.get_plan(project["id"], store=store)["tasks"][-1]["status"] != "done"
    assert len(services.run_journal(run["run_id"], store=store)["steps"]) == 1


def test_build_dispatch_reserves_primary_slot_for_artifact_not_session(store):
    project, run, dispatch = _build_dispatch(store, "future-contract")
    pid, token = project["id"], dispatch["dispatch_token"]

    contract = dispatch["output_contract"]
    assert contract["allowed_primary_kinds"] == ["artifact", "prototype"]
    assert {"session", "usability_session", "prototype_session"} <= set(
        contract["supporting_kinds"])

    with pytest.raises(plan_mod.PlanError) as wrong_kind:
        services.prepare_dispatch_write(
            pid, token, None, "council", store, allowed_buckets={"act"})
    assert wrong_kind.value.code == "DISPATCH_OUTPUT_KIND_CONFLICT"

    session_ctx = services.prepare_dispatch_write(
        pid, token, None, "session", store, allowed_buckets={"act"})
    assert session_ctx["output_role"] == "supporting"
    linked = services.bind_dispatch_output(
        session_ctx, {"kind": "session", "id": "session_support"},
        "recorded supporting observed session", store,
    )
    assert linked["state"] == "linked"
    assert linked["checkpointed"] is False
    after_session = services.run_journal(run["run_id"], store=store)
    persisted = next(row for row in after_session["dispatches"]
                     if row["dispatch_token"] == token)
    assert persisted["primary_output_kind"] == ""
    assert after_session["steps"] == []
    assert services.get_plan(pid, store=store)["tasks"][0]["status"] != "done"

    artifact_ctx = services.prepare_dispatch_write(
        pid, token, None, "artifact", store, allowed_buckets={"act"})
    assert artifact_ctx["output_role"] == "primary"
    completed = services.bind_dispatch_output(
        artifact_ctx, {"kind": "artifact", "id": "artifact_primary"},
        "recorded the built artifact", store,
    )
    assert completed["state"] == "completed"
    assert completed["checkpointed"] is True
    final = services.run_journal(run["run_id"], store=store)
    persisted = next(row for row in final["dispatches"] if row["dispatch_token"] == token)
    assert persisted["primary_output_kind"] == "artifact"
    assert final["steps"][0]["produced_refs"] == [
        "session:session_support", "artifact:artifact_primary",
    ]


def test_already_issued_build_dispatch_repairs_legacy_session_primary(store):
    project, run, dispatch = _build_dispatch(store, "legacy-upgrade")
    token = dispatch["dispatch_token"]
    old_run = services.run_journal(run["run_id"], store=store)
    old_dispatch = next(row for row in old_run["dispatches"]
                        if row["dispatch_token"] == token)
    old_dispatch["output_contract"] = {
        "schema": "sonaloop.dispatch_output_contract.v1",
        "max_primary_outputs": 1,
        "allowed_primary_kinds": ["build"],
        "supporting_kinds": ["asset", "flow", "reference", "evidence"],
        "closing_kinds": ["judgment", "task_completion"],
    }
    old_dispatch["primary_output_kind"] = "session"
    store.upsert_run(old_run)

    # Replaying run_step upgrades the declared contract without changing its
    # deterministic input fingerprint or erasing the legacy claim.
    replay = services.run_step(run["run_id"], store=store)
    assert replay["dispatch_token"] == token
    assert replay["output_contract"]["allowed_primary_kinds"] == ["artifact", "prototype"]
    assert "session" in replay["output_contract"]["supporting_kinds"]
    replayed = services.run_journal(run["run_id"], store=store)
    replayed_dispatch = next(row for row in replayed["dispatches"]
                             if row["dispatch_token"] == token)
    assert replayed_dispatch["primary_output_kind"] == "session"

    repaired = services.prepare_dispatch_write(
        project["id"], token, None, "artifact", store, allowed_buckets={"act"})
    assert repaired["output_role"] == "primary"
    persisted = next(
        row for row in services.run_journal(run["run_id"], store=store)["dispatches"]
        if row["dispatch_token"] == token
    )
    assert persisted["primary_output_kind"] == "artifact"
    assert persisted["primary_output_repair_history"][-1]["from"] == "session"
    assert persisted["primary_output_repair_history"][-1]["to"] == "artifact"

    with pytest.raises(plan_mod.PlanError) as unrelated:
        services.prepare_dispatch_write(
            project["id"], token, None, "council", store, allowed_buckets={"act"})
    assert unrelated.value.code == "DISPATCH_OUTPUT_KIND_CONFLICT"


def test_committed_build_dispatch_does_not_rewrite_legacy_primary(store):
    project, run, dispatch = _build_dispatch(store, "locked-legacy")
    token = dispatch["dispatch_token"]
    old_run = services.run_journal(run["run_id"], store=store)
    old_dispatch = next(row for row in old_run["dispatches"]
                        if row["dispatch_token"] == token)
    old_dispatch["primary_output_kind"] = "session"
    old_dispatch["status"] = "completed"
    store.upsert_run(old_run)

    with pytest.raises(plan_mod.PlanError) as locked:
        services.prepare_dispatch_write(
            project["id"], token, None, "prototype", store, allowed_buckets={"act"})
    assert locked.value.code == "DISPATCH_OUTPUT_KIND_CONFLICT"
    persisted = next(
        row for row in services.run_journal(run["run_id"], store=store)["dispatches"]
        if row["dispatch_token"] == token
    )
    assert persisted["primary_output_kind"] == "session"
