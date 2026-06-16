from sonaloop.project_trace import trace_node_health


def _plan(status: str = "pending") -> dict:
    return {"tasks": [
        {"id": "frame__discover", "bucket": "analyze", "status": "done", "consumes": [],
         "produces": [{"kind": "frame", "id": "frame__discover"}]},
        {"id": "verify__deliver", "bucket": "verify", "status": status,
         "consumes": ["frame__discover"],
         "produces": [{"kind": "synthesis", "id": "syn_final"}]},
    ]}


def test_trace_node_without_output_is_active_while_plan_is_open():
    nodes = [{"study_id": "survey:sv1", "kind": "survey"}]
    assert trace_node_health(nodes, [], _plan("pending")) == {"survey:sv1": "active"}


def test_trace_node_without_output_is_orphaned_after_plan_completes():
    nodes = [{"study_id": "survey:sv1", "kind": "survey"}]
    assert trace_node_health(nodes, [], _plan("done")) == {"survey:sv1": "orphaned"}


def test_trace_node_without_output_can_be_explicitly_parked():
    nodes = [{"study_id": "survey:sv1", "kind": "survey"}]
    plan = _plan("done")
    plan["parked_refs"] = [{"refs": ["survey:sv1"], "reason": "side signal"}]
    assert trace_node_health(nodes, [], plan) == {"survey:sv1": "parked"}


def test_trace_node_with_output_is_consumed_and_terminal_verify_synthesis_ends():
    nodes = [
        {"study_id": "survey:sv1", "kind": "survey"},
        {"study_id": "synthesis:syn_final", "kind": "synthesis"},
    ]
    edges = [{"from_study": "survey:sv1", "to_study": "synthesis:syn_final",
              "type": "judgment_evidence"}]
    assert trace_node_health(nodes, edges, _plan("done")) == {
        "survey:sv1": "consumed",
        "synthesis:syn_final": "terminal",
    }


def test_trace_start_material_with_output_is_source():
    nodes = [
        {"study_id": "note:n1", "kind": "note"},
        {"study_id": "council:c1", "kind": "council"},
    ]
    edges = [{"from_study": "note:n1", "to_study": "council:c1", "type": "uses_material"}]
    assert trace_node_health(nodes, edges, _plan("pending"))["note:n1"] == "source"
