"""ESV §A.4/A.6 + §B.3 — the deterministic RunLoop driver, driven by a STUB authoring backend (OD-4).

No LLM: the stub host loops run_step → executes the returned dispatch with canned evidence → records
the result → repeats. Proves: the loop completes a methodology, the loop-until-dry critic gate injects
work then converges, and a 'killed' run resumes identically.
"""
from __future__ import annotations

import pytest

from sonaloop import services
from sonaloop.storage import Store

_DIMS = ["exploration_depth", "segment_breadth", "concept_novelty", "evidence_groundedness",
         "honesty_anti_steering", "iteration", "finish"]


def _register_tiny_methodology(store):
    services.register_methodology({
        "key": "esv_test", "name": "ESV Test", "description": "d", "when_to_use": "w",
        "steps": [
            {"id": "explore", "name": "Explore", "tags": ["explore"], "intent": "explore"},
            {"id": "decide", "name": "Decide", "tags": ["decide"], "consumes": ["explore"],
             "requires": {"min_inputs": 2, "gate_tag": "divergence_complete"}, "produces": {"role": "pov"}}]},
        store=store)


def _council(store, cid):
    store.insert_council_session({"id": cid, "created_at": "2026-06-05T00:00:00+00:00", "prompt": "p",
        "persona_ids": ["p1"], "statements": [], "votes": [], "proposal": "", "summary": "",
        "exec_summary": "e", "selection_reason": "x"})
    return cid


def _stub_author(s, pid, store, ctr):
    """Execute one run_step dispatch with canned evidence (the deterministic authoring backend)."""
    kind, step = s["kind"], s["step_id"]
    n = s.get("next_action", {})
    if kind == "analyze":
        services.record_frame(pid, step, ["q?"], memory_refs=["m1"], store=store)
        return
    if step == "__conclusion__":
        syn = services.record_synthesis("Conclusion", "x", [], {"gesamtbild": "G" * 300,
            "positionierung": "P" * 300, "findings": [{"text": "solver", "kind": "pain_solver"}]}, key=s["key"], store=store)
        services.link_evidence(pid, s["terminal_verify"], {"kind": "synthesis", "id": syn["id"]}, store=store)
        return
    plan = services.get_plan(pid, store=store)
    task = next((t for t in plan["tasks"] if t["id"] == step), None)
    if kind == "act":                                   # an injected concept/segment act task
        cid = _council(store, f"c-{step}-{ctr[0]}")
        services.link_evidence(pid, step, {"kind": "council", "id": cid}, store=store)
        services.complete_task(pid, step, store=store)
        return
    # kind == "verify"
    if n.get("act"):                                    # fan incomplete → add act councils
        for c in task["consumes"]:
            for i in (1, 2):
                ctr[0] += 1
                cid = _council(store, f"c-{c}-{ctr[0]}")
                a = services.add_task(pid, "act", "explore", f"angle {ctr[0]}", consumes=[c], store=store)
                services.link_evidence(pid, a["id"], {"kind": "council", "id": cid}, store=store)
                services.complete_task(pid, a["id"], store=store)
        return
    # gate met → judgment + synthesis + complete
    fan = [r["id"] for t in plan["tasks"] if t["bucket"] == "act"
           and set(t["consumes"]) & set(task["consumes"]) for r in t["produces"] if r["kind"] == "council"]
    services.record_judgment(pid, step, "divergence_complete", True, "enough", evidence_refs=fan or ["x"], store=store)
    syn = services.record_synthesis(f"{step} synthesis", "x", fan, {"gesamtbild": "G" * 300,
        "positionierung": "P" * 300, "findings": [{"text": "kp", "kind": "key_problem"}]}, key=s["key"], store=store)
    services.link_evidence(pid, step, {"kind": "synthesis", "id": syn["id"]}, store=store)
    services.complete_task(pid, step, store=store)


def _drive(run_id, pid, store, stop_after=None):
    """The thin host loop: run_step → execute → record → repeat (until done or stop_after steps)."""
    ctr, critic_calls, steps = [0], [0], 0
    for _ in range(300):
        s = services.run_step(run_id, store=store)
        if s["kind"] == "done":
            return s
        if s["kind"] == "critic":
            critic_calls[0] += 1
            if critic_calls[0] == 1:                    # first critic finds a gap
                v = {"passed": False, "scores": {"exploration_depth": 3},
                     "missing": [{"kind": "concept", "what": "build a dark-horse", "suggested_action": "scaffold it"}],
                     "rationale": "thin"}
            else:                                       # subsequent critics: exhaustive
                v = {"passed": True, "scores": {d: 5 for d in _DIMS}, "missing": [], "rationale": "exhaustive"}
            rec = services.record_completeness_critic(
                pid, v, run_id, s["operation_id"], store=store)
            services.record_critic_round(run_id, rec["id"], s["key"], store=store)
            continue
        _stub_author(s, pid, store, ctr)
        services.checkpoint_step(run_id, {"task_id": s["step_id"], "bucket": s["kind"],
                                          "key": s.get("key", ""), "summary": "stub"}, store=store)
        steps += 1
        if stop_after and steps >= stop_after:
            return {"kind": "stopped_for_test", "steps": steps}
    raise AssertionError("run did not converge")


def test_runloop_drives_to_finished_with_critic_loop(store):
    _register_tiny_methodology(store)
    pid = services.start_project("ESV4", "hmw?", "esv_test", persona_ids=["p1"], store=store)["id"]
    run = services.start_run(pid, budget=60, store=store)
    out = _drive(run["run_id"], pid, store)
    assert out["kind"] == "done" and out["status"] == "finished"
    a = services.assess_project(pid, store=store)
    assert a["complete"] and a["finish"]["finished"]               # organized + concluded + handed-off
    # the critic loop ran (>=3 rounds: 1 fail injects work, then 2 dry passes) and the gap was injected
    rounds = services.run_journal(run["run_id"], store=store)["critic_rounds"]
    assert sum(1 for r in rounds if r["passed"]) >= 2 and any(not r["passed"] for r in rounds)
    assert any("[critic]" in t["title"] for t in services.get_plan(pid, store=store)["tasks"])  # injected work


def test_runloop_resumes_identically_after_kill(store):
    _register_tiny_methodology(store)
    pid = services.start_project("ESV4r", "hmw?", "esv_test", persona_ids=["p1"], store=store)["id"]
    run = services.start_run(pid, budget=60, store=store)
    rid = run["run_id"]
    _drive(rid, pid, store, stop_after=2)                          # "kill" partway
    ev_mid = sorted(s["id"] for s in store.list_syntheses())
    # resume (same run_id) and finish
    services.start_run(pid, run_id=rid, store=store)
    out = _drive(rid, pid, store)
    assert out["kind"] == "done" and out["status"] == "finished"
    # no duplicate keyed work: completing is idempotent, the plan reached a single finished state
    assert services.assess_project(pid, store=store)["finish"]["finished"] is True
    assert set(ev_mid).issubset(set(s["id"] for s in store.list_syntheses()))   # earlier evidence preserved


def test_pipeline_regression_score_and_memory_depth(store):
    """ESV6: a full driver run produces a FINISHED, organized, concluded, handed-off project; score_run
    persists the quality snapshot; assess_project surfaces memory_depth (thin cohort flagged)."""
    _register_tiny_methodology(store)
    pid = services.start_project("ESV6", "hmw?", "esv_test", persona_ids=["p1"], store=store)["id"]
    run = services.start_run(pid, budget=60, store=store)
    out = _drive(run["run_id"], pid, store)
    assert out["kind"] == "done" and out["status"] == "finished"
    # the finished project is organized + concluded + handed-off, with a structured terminal synthesis
    g = services.get_project_graph(pid, store=store)
    assert len(g["sections"]) >= 1 and store.list_reports(pid)
    from sonaloop import artifacts as A
    syns = store.list_syntheses()
    assert any((s.get("gesamtbild") or "").strip()
               and (A.finding_texts(s, "key_problem") or A.finding_texts(s, "pain_solver")) for s in syns)
    # memory_depth: a 1-persona cohort with no simulated life is flagged thin
    md = services.assess_project(pid, store=store)["memory_depth"]
    assert md["personas"] == 1 and md["hint"].startswith("thin")
    assert services.cohort_memory_depth(["p1"], store=store)["avg_per_persona"] == 0.0
    # score_run persists a quality snapshot
    sc = services.score_run(pid, store=store)
    assert sc["complete"] is True and sc["finish"]["finished"] is True and "councils" in sc["coverage"]


@pytest.mark.parametrize("terminal_status", ["finished", "stopped", "capped"])
def test_run_step_replays_terminal_journal_without_dispatch(store, terminal_status):
    if terminal_status == "finished":
        _register_tiny_methodology(store)
        pid = services.start_project(
            "Terminal finished", "hmw?", "esv_test", persona_ids=["p1"], store=store,
        )["id"]
        run = services.start_run(pid, budget=60, store=store)
        assert _drive(run["run_id"], pid, store)["status"] == "finished"
    else:
        pid = services.start_project(
            f"Terminal {terminal_status}", "hmw?", "", store=store,
        )["id"]
        run = services.start_run(pid, budget=10, store=store)
        services.finish_run(run["run_id"], terminal_status, store=store)
    before = services.run_journal(run["run_id"], store=store)

    replay = services.run_step(run["run_id"], store=store)

    after = services.run_journal(run["run_id"], store=store)
    assert replay["kind"] == "done"
    assert replay["status"] == terminal_status
    assert replay["persisted_status"] == terminal_status
    assert replay["idempotent_replay"] is True
    assert after == before
