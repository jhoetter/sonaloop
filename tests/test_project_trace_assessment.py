from sonaloop import plan as PL
from sonaloop import services


def _force_done(project_id: str, store) -> None:
    plan = PL.get_plan(project_id, store=store)
    for task in plan["tasks"]:
        task["status"] = "done"
    PL.save_plan(plan, store=store)


def test_assess_project_reports_act_evidence_not_cited_by_closed_gate(store):
    project = services.create_research_project("Trace assessment", goal="Keep evidence connected",
                                               store=store)
    pid = project["id"]
    services.record_frame(pid, "frame__root", ["What evidence matters?"],
                          memory_refs=["note:seed"], store=store)
    act = services.add_task(pid, "act", "survey", "Survey evidence",
                            consumes=["frame__root"], store=store)
    survey = services.record_survey(
        pid, "Assessment survey",
        [{"id": "q1", "text": "Useful?", "kind": "single", "options": ["yes", "no"]}],
        status="open", store=store)["survey"]
    services.link_evidence(pid, act["id"], {"kind": "survey", "id": survey["id"]}, store=store)
    services.add_task(pid, "verify", "decide", "Closed gate",
                      consumes=["frame__root"], store=store)
    _force_done(pid, store)

    assessed = services.assess_project(pid, store=store)
    assert any("Survey evidence" in gap and "no completed gate cites it" in gap
               for gap in assessed["gaps"])

    services.record_judgment(pid, "verify__decide", "trace_closed", True, "survey used",
                             evidence_refs=[f"survey:{survey['id']}"], store=store)
    assessed = services.assess_project(pid, store=store)
    assert not any("Survey evidence" in gap and "no completed gate cites it" in gap
                   for gap in assessed["gaps"])


def test_assess_project_accepts_explicitly_parked_evidence(store):
    project = services.create_research_project("Trace parked", goal="Keep evidence connected",
                                               store=store)
    pid = project["id"]
    services.record_frame(pid, "frame__root", ["What evidence matters?"],
                          memory_refs=["note:seed"], store=store)
    act = services.add_task(pid, "act", "survey", "Survey evidence",
                            consumes=["frame__root"], store=store)
    survey = services.record_survey(
        pid, "Parked survey",
        [{"id": "q1", "text": "Useful?", "kind": "single", "options": ["yes", "no"]}],
        status="open", store=store)["survey"]
    services.link_evidence(pid, act["id"], {"kind": "survey", "id": survey["id"]}, store=store)
    services.add_task(pid, "verify", "decide", "Closed gate",
                      consumes=["frame__root"], store=store)
    _force_done(pid, store)

    services.park_evidence(pid, [f"survey:{survey['id']}"],
                           "Side signal; not used for this gate", task_id=act["id"], store=store)
    assessed = services.assess_project(pid, store=store)
    assert not any("Survey evidence" in gap and "no completed gate cites it" in gap
                   for gap in assessed["gaps"])
