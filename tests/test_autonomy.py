"""Autonomy harness — assess_project (HX1) + next_action (HX2).
Spec: spec/harness-evaluation-and-autonomy.md. Pure structural (no LLM/subagents): these are the
lean-loop steering tools a long autonomous run calls each iteration.
"""
from __future__ import annotations

from sonaloop import services as S


def _proj(store):
    personas = [p["slug"] for p in store.list_personas()] or ["p1"]
    return S.start_project("Auto Harness", "Wie können wir X erreichen?", methodology="double_diamond",
                           persona_ids=personas, store=store)["id"], personas


def test_assess_project_pulse_on_fresh_plan(store):
    pid, _ = _proj(store)
    a = S.assess_project(pid, store=store)
    assert a["complete"] is False
    assert a["recommendation"] == "frame"                 # an analyze frame is ready first
    assert "verify" in a["tasks_by_bucket"] and a["tasks_by_bucket"]["verify"]["total"] >= 1
    # the seeded verify is gated-open (needs ≥ min_inputs distinct act tasks/angles)
    assert any("act task" in u or "angles" in u for g in a["open_gates"] for u in g["unmet"])
    assert "saturation" in a and "coverage" in a


def test_next_action_loads_each_step(store):
    pid, personas = _proj(store)
    # 1) analyze step is fully loaded with grounding
    n = S.next_action(pid, store=store)
    assert n["bucket"] == "analyze" and n["complete"] is False
    assert n["grounding"]["persona_pool"]                  # personas available to ground the frame
    # 2) after framing, the gated verify surfaces ACT guidance (framed questions + diverse personas)
    S.record_frame(pid, "frame__discover", ["Was treibt sie?", "Warum nicht?"],
                   memory_refs=["persona: lived memory"], store=store)
    n2 = S.next_action(pid, store=store)
    assert n2["bucket"] == "verify"
    assert n2["act"]["framed_questions"]                   # the consumed frame's questions
    parts = n2["act"]["suggested_participants"]
    assert isinstance(parts, list) and len(parts) == len(set(parts))  # de-duped (empty if no cohort in test DB)
    assert S.assess_project(pid, store=store)["recommendation"] == "act"


def test_assess_project_complete_when_plan_done(store):
    # a freeform project with a single discharged frame is "complete"
    pid = S.start_project("Freeform", "frage?", store=store)["id"]
    S.record_frame(pid, "frame__root", ["q?"], memory_refs=["m"], store=store)
    a = S.assess_project(pid, store=store)
    assert a["complete"] is True and a["recommendation"] == "complete"


def test_cohort_depth_preflight_warns_before_discover(store):
    """A memoryless cohort must be flagged at start_project and on every frame's grounding —
    BEFORE Discover runs ungrounded (a real run gate-passed Discover+Define in 7 minutes over
    5 personas with 0 facts/events). Non-blocking; disappears once memory exists."""
    proj = S.start_project("Pre", "hmw?", "double_diamond", persona_ids=["p1", "p2"], store=store)
    assert any("ungrounded" in w for w in proj["warnings"])
    n = S.next_action(proj["id"], store=store)
    assert "ungrounded" in n["grounding"]["cohort_warning"]
    # record_council over zero-memory participants: a soft warning rides the response (not stored)
    c = S.record_council(proj["id"], "frage?", ["p1", "p2"], statements=[], store=store)
    assert any("ungrounded" in w for w in c["warnings"])
    assert "warnings" not in (store.get_council_session(c["id"]) or {})
    # seed memory → the pre-flight goes quiet
    for i in range(3):
        store.insert_experience_event({"id": f"ev{i}", "persona_id": "p1", "timestamp": f"2026-01-0{i+1}T09:00:00",
                                       "event_type": "work", "summary": "did things"})
        store.insert_experience_event({"id": f"ev{i}b", "persona_id": "p2", "timestamp": f"2026-01-0{i+1}T10:00:00",
                                       "event_type": "work", "summary": "did things"})
    proj2 = S.start_project("Pre2", "hmw?", "double_diamond", persona_ids=["p1", "p2"], store=store)
    assert "warnings" not in proj2
    assert "cohort_warning" not in S.next_action(proj2["id"], store=store)["grounding"]


def test_project_run_state_active_expired_finished(store):
    """A ready step with no driver must be visible: stalled immediately (no open run), active
    while a run is checkpointing, finished when the plan is done — computed on read."""
    pid, _ = _proj(store)
    rs = S.project_run_state(pid, store=store)
    assert rs["state"] == "stalled" and "start_run" in rs["note"]    # open work, nobody driving
    assert rs["next_ready"] == ["frame__discover"]
    run = S.start_run(pid, store=store)
    assert S.project_run_state(pid, store=store)["state"] == "active"
    # a 24h-quiet open run becomes expired but retains the same resumable journal
    run["updated_at"] = "2020-01-01T00:00:00+00:00"
    store.upsert_run(run)
    rs = S.project_run_state(pid, store=store)
    assert rs["state"] == "expired" and run["run_id"] in rs["note"]  # resume call names the run
    # Task completion alone is not engine completion: only a governed run may
    # become finished after the finish/critic/handoff contract.
    fid = S.start_project("Freeform", "frage?", store=store)["id"]
    S.record_frame(fid, "frame__root", ["q?"], memory_refs=["m"], store=store)
    completed = S.project_run_state(fid, store=store)
    assert completed["state"] == "unverified"
    assert completed["engine_finished"] is False
    # and the project list carries it
    listed = {p["id"]: p for p in S.list_research_projects(store=store)}
    assert listed[pid]["run_state"]["state"] == "expired"


def test_frame_intent_is_one_step_and_phase_ambitions_ride_the_act_lane(store):
    """The seeded frame task asks for record_frame ONLY; the phase's build/ideation ambitions
    (lenses, prototype ladder, dark horse) live in `phase_intent` and surface via next_action's
    act lane — a frame instruction that read like a whole new project made a real run balk at
    the phase boundary."""
    pid = S.start_project("Deep", "hmw?", "double_diamond_deep", persona_ids=["p1"], store=store)["id"]
    plan = S.get_plan(pid, store=store)
    ideate = next(t for t in plan["tasks"] if t["id"] == "frame__ideate")
    assert "record_frame" in ideate["intent"]
    assert "DIVERSE IN KIND" not in ideate["intent"] and "dark-horse" not in ideate["intent"]
    assert "DIVERSE IN KIND" in ideate["phase_intent"]          # the ambitions are kept, not lost
    # once the frame is recorded, the act lane (the short verify's act guidance) carries them
    S.record_frame(pid, "frame__discover", ["q?"], memory_refs=["m"], store=store)
    n = S.next_action(pid, store=store)                          # verify__define, fan short → act guidance
    assert n["bucket"] == "verify" and "phase_intent" in n["act"]
    assert "DISTINCT ANGLES" in n["act"]["phase_intent"]         # discover's phase ambitions, in place


def test_run_state_nudge_when_loop_is_ungoverned(store):
    """A multi-task plan with open work and NO active run must say so in-band (the stalled Codex
    run freestyled next_action and never saw 'you are not done'); the nudge disappears once
    start_run governs the loop, and never fires for a trivial single-task inquiry."""
    pid, _ = _proj(store)
    n = S.next_action(pid, store=store)
    assert n["run_state"]["active_run"] is False
    assert "start_run" in n["run_state"]["note"] and "NOT finished" in n["run_state"]["note"]
    a = S.assess_project(pid, store=store)
    assert a["run_state"]["tasks_total"] == a["coverage"]["tasks_total"]
    # the envelope's dynamic hint points at start_run while ungoverned
    from sonaloop.mcp_server._env import _env
    import time as _time
    env = _env("next_action", n, _time.perf_counter())
    assert env["next_recommended_tool"]["name"] == "start_run"
    # governed: the nudge is gone
    S.start_run(pid, store=store)
    assert "run_state" not in S.next_action(pid, store=store)
    assert "run_state" not in S.assess_project(pid, store=store)
    # single-task freeform inquiry: never nudged
    fid = S.start_project("Freeform", "frage?", store=store)["id"]
    assert "run_state" not in S.next_action(fid, store=store)


def test_complete_task_reports_progress_when_not_terminal(store):
    pid, _ = _proj(store)
    S.record_frame(pid, "frame__discover", ["q?"], memory_refs=["m"], store=store)
    t = S.add_task(pid, "act", "explore", "Council", consumes=["frame__discover"], store=store)
    S.link_evidence(pid, t["id"], {"kind": "council", "id": "c1"}, store=store)
    done = S.complete_task(pid, t["id"], store=store)
    assert done["status"] == "done"
    assert done["progress"]["tasks_done"] < done["progress"]["tasks_total"]
    assert "NOT finished" in done["progress"]["note"] and done["progress"]["next_ready"]
    assert done["run_state"]["active_run"] is False        # still ungoverned → nudge rides along


def test_saturation_never_converging_while_a_diamond_is_unopened(store):
    """The stalled-run snapshot (2026-06-10): Discover+Define done, second diamond untouched.
    The old ratio-only hint read "converging" here — with open_questions empty, both published
    stop conditions were green at the exact stall point. Plan-aware: still diverging."""
    pid = S.start_project("Stall", "hmw?", "double_diamond", persona_ids=["p1"], store=store)["id"]
    a = S.assess_project(pid, store=store)
    assert a["saturation"]["hint"].startswith("early")            # no act evidence at all yet
    S.record_frame(pid, "frame__discover", ["q1?", "q2?"], memory_refs=["m1"], store=store)
    for i in (1, 2):
        t = S.add_task(pid, "act", "explore", f"Council {i}", consumes=["frame__discover"], store=store)
        S.link_evidence(pid, t["id"], {"kind": "council", "id": f"c{i}"}, store=store)
        S.complete_task(pid, t["id"], store=store)
    syn = S.record_synthesis("Define POV", "hmw?", ["c1", "c2"], {"gesamtbild": "pov"}, store=store)
    S.link_evidence(pid, "verify__define", {"kind": "synthesis", "id": syn["id"]}, store=store)
    S.record_judgment(pid, "verify__define", "divergence_complete", True, "saturating",
                      evidence_refs=["c1", "c2"], store=store)
    S.complete_task(pid, "verify__define", store=store)
    a = S.assess_project(pid, store=store)
    # 2 act done vs 1 synthesis satisfied the old ratio — but frame__ideate (analyze) is still open
    assert a["saturation"]["act_done"] == 2 and a["saturation"]["syntheses"] >= 1
    assert a["saturation"]["hint"] == "still diverging"
    assert a["complete"] is False


def test_saturation_converging_once_divergent_work_is_done(store):
    """When every analyze/act task is done and consolidation kept pace, the hint is honest again."""
    pid = S.start_project("Conv", "frage?", store=store)["id"]          # freeform: one root frame
    S.record_frame(pid, "frame__root", ["q?"], memory_refs=["m"], store=store)
    t = S.add_task(pid, "act", "explore", "Council", consumes=["frame__root"], store=store)
    S.link_evidence(pid, t["id"], {"kind": "council", "id": "c1"}, store=store)
    S.complete_task(pid, t["id"], store=store)
    syn = S.record_synthesis("Answer", "frage?", ["c1"], {"gesamtbild": "answer"}, store=store)
    v = S.add_task(pid, "verify", "consolidate", "Decide", consumes=["frame__root"],
                   requires={"min_inputs": 1, "gate_tag": "decided"}, store=store)
    S.link_evidence(pid, v["id"], {"kind": "synthesis", "id": syn["id"]}, store=store)
    a = S.assess_project(pid, store=store)
    assert a["saturation"]["hint"] == "converging"                      # 1 act ≤ 2·1 syn, nothing divergent open
    # and once every task is done, the hint is honest about it (a finished freelancer-run read
    # "still diverging" because 5 act vs 2 syntheses failed the ratio — on a COMPLETE plan)
    S.record_judgment(pid, v["id"], "decided", True, "done", evidence_refs=["c1"], store=store)
    S.complete_task(pid, v["id"], store=store)
    assert S.assess_project(pid, store=store)["saturation"]["hint"] == "complete"
