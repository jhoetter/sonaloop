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
    if step == "__report_handoff__":
        report = store.get_report(s["report_id"])
        if s.get("lead_missing"):
            services.record_synthesis_outline(
                pid,
                {
                    "build_order_narrative": "Evidence to decision.",
                    "sections": [
                        {key: section.get(key) for key in (
                            "id", "heading", "intent", "theme_tags", "source_study_ids")}
                        for section in report.get("sections") or []
                    ],
                },
                report_id=report["id"],
                operation_id=s["operation_id"],
                dispatch_token=s["dispatch_token"],
                store=store,
            )
        for section_id in s.get("incomplete_section_ids") or []:
            services.record_synthesis_section(
                pid, section_id,
                {"markdown": f"Authored report section {section_id}.", "citations": []},
                report_id=report["id"], dispatch_token=s["dispatch_token"], store=store,
            )
        return True
    if kind == "analyze":
        services.record_frame(pid, step, ["q?"], memory_refs=["m1"], store=store)
        return False
    if step == "__conclusion__":
        syn = services.record_synthesis("Conclusion", "x", [], {"gesamtbild": "G" * 300,
            "positionierung": "P" * 300, "findings": [{"text": "solver", "kind": "pain_solver"}]}, key=s["key"], store=store)
        services.link_evidence(pid, s["terminal_verify"], {"kind": "synthesis", "id": syn["id"]}, store=store)
        return False
    plan = services.get_plan(pid, store=store)
    task = next((t for t in plan["tasks"] if t["id"] == step), None)
    if kind == "act":                                   # an injected concept/segment act task
        cid = _council(store, f"c-{step}-{ctr[0]}")
        services.link_evidence(pid, step, {"kind": "council", "id": cid}, store=store)
        services.complete_task(pid, step, store=store)
        return False
    # kind == "verify"
    if n.get("act"):                                    # fan incomplete → add act councils
        for c in task["consumes"]:
            for i in (1, 2):
                ctr[0] += 1
                cid = _council(store, f"c-{c}-{ctr[0]}")
                a = services.add_task(pid, "act", "explore", f"angle {ctr[0]}", consumes=[c], store=store)
                services.link_evidence(pid, a["id"], {"kind": "council", "id": cid}, store=store)
                services.complete_task(pid, a["id"], store=store)
        return False
    # gate met → judgment + synthesis + complete
    fan = [r["id"] for t in plan["tasks"] if t["bucket"] == "act"
           and set(t["consumes"]) & set(task["consumes"]) for r in t["produces"] if r["kind"] == "council"]
    services.record_judgment(pid, step, "divergence_complete", True, "enough", evidence_refs=fan or ["x"], store=store)
    syn = services.record_synthesis(f"{step} synthesis", "x", fan, {"gesamtbild": "G" * 300,
        "positionierung": "P" * 300, "findings": [{"text": "kp", "kind": "key_problem"}]}, key=s["key"], store=store)
    services.link_evidence(pid, step, {"kind": "synthesis", "id": syn["id"]}, store=store)
    services.complete_task(pid, step, store=store)
    return False


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
        auto_checkpointed = _stub_author(s, pid, store, ctr)
        if not auto_checkpointed:
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


def test_report_handoff_replays_same_dispatch_and_report_until_every_section_is_authored(store):
    _register_tiny_methodology(store)
    pid = services.start_project(
        "Resumable report handoff", "hmw?", "esv_test", persona_ids=["p1"], store=store,
    )["id"]
    run = services.start_run(pid, budget=60, store=store)
    ctr = [0]

    for _ in range(40):
        step = services.run_step(run["run_id"], store=store)
        assert step["kind"] != "critic", "critic must wait for the authored report hand-off"
        if step.get("step_id") == "__report_handoff__":
            break
        assert step["kind"] != "done"
        assert _stub_author(step, pid, store, ctr) is False
        services.checkpoint_step(
            run["run_id"],
            {"task_id": step["step_id"], "bucket": step["kind"],
             "key": step.get("key", ""), "summary": "stub"},
            store=store,
        )
    else:  # pragma: no cover - diagnostic guard
        raise AssertionError("run never issued its report hand-off")

    assert step["kind"] == "verify"
    assert step["expected_output_kind"] == "report"
    assert step["blocking_action"]["next_call"]["tool"] == "brief_synthesis_section"
    assert len(step["incomplete_section_ids"]) >= 2
    report_id = step["report_id"]
    token = step["dispatch_token"]
    first_section, *remaining = step["incomplete_section_ids"]
    partial = services.record_synthesis_section(
        pid, first_section, {"markdown": "First section is authored.", "citations": []},
        report_id=report_id, dispatch_token=token, store=store,
    )
    assert partial["dispatch"]["state"] == "progress"
    assert partial["dispatch"]["checkpointed"] is False

    replay = services.run_step(run["run_id"], store=store)
    assert replay["step_id"] == "__report_handoff__"
    assert replay["report_id"] == report_id
    assert replay["dispatch_token"] == token
    assert first_section not in replay["incomplete_section_ids"]
    assert replay["incomplete_section_ids"] == remaining

    final = None
    for section_id in replay["incomplete_section_ids"]:
        final = services.record_synthesis_section(
            pid, section_id, {"markdown": f"Authored {section_id}.", "citations": []},
            report_id=report_id, dispatch_token=token, store=store,
        )
    assert final and final["dispatch"]["checkpointed"] is True
    assert final["handoff"]["complete"] is True
    assert services.run_step(run["run_id"], store=store)["kind"] == "critic"


def test_report_handoff_repairs_legacy_empty_lead_without_replacing_authored_bodies(store):
    _register_tiny_methodology(store)
    pid = services.start_project(
        "Legacy lead repair", "hmw?", "esv_test", persona_ids=["p1"], store=store,
    )["id"]
    run = services.start_run(pid, budget=60, store=store)
    ctr = [0]

    for _ in range(40):
        step = services.run_step(run["run_id"], store=store)
        assert step["kind"] != "critic"
        if step.get("step_id") == "__report_handoff__":
            break
        assert step["kind"] != "done"
        assert _stub_author(step, pid, store, ctr) is False
        services.checkpoint_step(
            run["run_id"],
            {"task_id": step["step_id"], "bucket": step["kind"],
             "key": step.get("key", ""), "summary": "stub"},
            store=store,
        )
    else:  # pragma: no cover - diagnostic guard
        raise AssertionError("run never issued its report hand-off")

    report = store.get_report(step["report_id"])
    report["lead"] = ""
    report["status"] = "done"  # legacy rows could falsely claim completion
    for section in report["sections"]:
        section["markdown"] = f"Preserved authored body for {section['id']}."
        section["status"] = "done"
    store.upsert_synthesis(report)

    recovery = services.run_step(run["run_id"], store=store)
    assert recovery["step_id"] == "__report_handoff__"
    assert recovery["report_id"] == step["report_id"]
    assert recovery["dispatch_token"] == step["dispatch_token"]
    assert recovery["lead_missing"] is True
    assert recovery["incomplete_section_ids"] == []
    assert "omitting operation_id" in recovery["directive"]

    repaired_outline = {
        "build_order_narrative": "A truthful evidence-to-decision lead.",
        "sections": [
            {key: section.get(key) for key in (
                "id", "heading", "intent", "theme_tags", "source_study_ids")}
            for section in report["sections"]
        ],
    }
    repaired = services.record_synthesis_outline(
        pid, repaired_outline, report_id=report["id"],
        dispatch_token=recovery["dispatch_token"], store=store,
    )
    assert repaired["id"] == report["id"]
    assert repaired["handoff"]["complete"] is True
    assert repaired["dispatch"]["checkpointed"] is True
    assert [section["markdown"] for section in repaired["sections"]] == [
        section["markdown"] for section in report["sections"]]

    retry = services.record_synthesis_outline(
        pid, repaired_outline, report_id=report["id"],
        dispatch_token=recovery["dispatch_token"], store=store,
    )
    assert retry["idempotent_replay"] is True
    assert retry["dispatch"]["checkpointed"] is True
    assert services.run_step(run["run_id"], store=store)["kind"] == "critic"


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
