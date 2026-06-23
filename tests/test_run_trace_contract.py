from __future__ import annotations

from sonaloop import services


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
                          memory_refs=["memory:p1:handover"], store=store)
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
