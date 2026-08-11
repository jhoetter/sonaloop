from sonaloop.project_trace import collect_project_trace_edges, trace_node_health


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


def test_project_report_sources_form_one_terminal_handoff_edge():
    nodes = [
        {"study_id": "synthesis:gate", "kind": "synthesis"},
        {"study_id": "report:final", "kind": "report"},
    ]
    plan = {"tasks": [{
        "id": "verify__gate", "bucket": "verify", "status": "done", "consumes": [],
        # A governed hand-off can bind both outputs to the same terminal task. The
        # report's authored section source, not output ordering, defines the edge.
        "produces": [
            {"kind": "synthesis", "id": "gate"},
            {"kind": "report", "id": "final"},
        ],
    }]}
    graph = {"plan": plan, "reports": [{
        "id": "final",
        "source_study_ids": ["synthesis:gate", "synthesis:gate"],
        "legacy_citation_study_ids": [],
    }]}

    edges = collect_project_trace_edges(graph, nodes)
    handoff = [edge for edge in edges
               if edge["from_study"] == "synthesis:gate"
               and edge["to_study"] == "report:final"]

    assert len(handoff) == 1
    assert handoff[0]["type"] == "based_on"
    assert handoff[0]["provenance"] == "authored"
    assert handoff[0]["source"] == "report.sections.source_study_ids"
    assert trace_node_health(nodes, edges, plan) == {
        "synthesis:gate": "consumed",
        "report:final": "terminal",
    }


def test_plan_trace_resolves_frame_hops_into_prototype_inputs():
    nodes = [
        {"study_id": "synthesis:def", "kind": "synthesis"},
        {"study_id": "prototype:p1", "kind": "prototype"},
        {"study_id": "session:s1", "kind": "session"},
        {"study_id": "synthesis:deliver", "kind": "synthesis"},
    ]
    plan = {"tasks": [
        {"id": "verify__define", "bucket": "verify", "status": "done", "consumes": [],
         "produces": [{"kind": "synthesis", "id": "def"}]},
        {"id": "frame__develop", "bucket": "analyze", "status": "done",
         "consumes": ["verify__define"], "produces": [{"kind": "frame", "id": "frame__develop"}]},
        {"id": "act__build", "bucket": "act", "status": "done", "consumes": ["frame__develop"],
         "produces": [{"kind": "prototype", "id": "p1"}, {"kind": "session", "id": "s1"}]},
        {"id": "verify__deliver", "bucket": "verify", "status": "done", "consumes": ["act__build"],
         "produces": [{"kind": "synthesis", "id": "deliver"}]},
    ]}

    edges = collect_project_trace_edges({"plan": plan}, nodes)
    triples = {(e["from_study"], e["to_study"], e["type"]) for e in edges}

    assert ("synthesis:def", "prototype:p1", "task_consumes") in triples
    assert ("synthesis:def", "session:s1", "task_consumes") in triples
    assert ("prototype:p1", "synthesis:deliver", "task_consumes") in triples
    assert ("session:s1", "synthesis:deliver", "task_consumes") in triples
