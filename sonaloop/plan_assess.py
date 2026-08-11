"""Project meta-assessment + the run-state autonomy nudge (split out of plan.py for the LOC bar).

`assess_project` is the long run's pulse (HX1): read-only, COMPUTED, no LLM verdict. `run_state`
is the in-band warning that a multi-task plan is being driven without the governed run loop —
returned on the loop tools' responses so it reaches every host at the moment it decides whether
to continue (spec/harness-evaluation-and-autonomy.md).
"""
from __future__ import annotations

from typing import Any

from .storage import Store
from .report_handoff import report_handoff_state


def run_state(project_id: str, plan: dict[str, Any], store: Store) -> dict[str, Any] | None:
    """The in-band autonomy nudge: a multi-task plan with open work but NO active run object is
    ungoverned — no budget, no journal, no critic will ever say "done", so the host's turn
    discipline is the only thing keeping the project alive (a real run stalled exactly this way,
    freestyling next_action and stopping at a phase boundary). Returned on the loop tools'
    responses so the warning reaches every host at the moment it decides whether to continue.
    None when a run is active, the plan is finished, or it is a trivial single-task inquiry."""
    tasks = plan["tasks"]
    open_tasks = [t for t in tasks if t["status"] != "done"]
    if len(tasks) <= 1 or not open_tasks:
        return None
    try:
        runs = store.list_runs(project_id)
    except Exception:
        runs = []
    if any(r.get("status") == "active" for r in runs):
        return None
    done = len(tasks) - len(open_tasks)
    return {"active_run": False, "tasks_done": done, "tasks_total": len(tasks),
            "note": (f"no active run — {done}/{len(tasks)} tasks done and the project is NOT "
                     f"finished; call start_run('{project_id}') so the loop is governed and "
                     f"resumable (budget, journal, critic decide the end — not your judgment). "
                     f"Stopping now strands the project mid-run.")}


def project_run_state(project_id: str, store: Store | None = None,
                      stale_hours: int = 6) -> dict[str, Any] | None:
    """Compatibility view over the canonical :func:`project_health` projector.

    Historically this function promoted a completed plan to ``finished`` even
    when no governed run had passed the finish/critic/handoff contract.  That
    created two conflicting truths in list/substrate responses.  Keep the
    legacy shape for callers, but never recompute lifecycle truth here.
    """
    from . import plan as _p
    store = store or Store()
    plan = _p.get_plan(project_id, store=store)
    if plan is None:
        return None
    from .services._recovery import project_health
    health = project_health(project_id, store=store, stale_hours=stale_hours)
    state = "active" if health["state"] == "running" else health["state"]
    out = {
        "state": state,
        "last_activity": health["last_activity"],
        "next_ready": list((health.get("tasks") or {}).get("next_ready") or []),
        "canonical_schema": health["schema"],
        "engine_finished": health["engine_finished"],
    }
    reason = str((health.get("safe_next_action") or {}).get("reason") or "")
    tool = str((health.get("safe_next_action") or {}).get("tool") or "")
    if tool and tool not in reason:
        args = dict((health.get("safe_next_action") or {}).get("arguments") or {})
        rendered = ", ".join(f"{key}={value!r}" for key, value in sorted(args.items()))
        reason = f"{reason} Call {tool}({rendered}).".strip()
    finding = health.get("unmet_invariant") or {}
    if finding.get("message"):
        reason = f"{finding['message']} {reason}".strip()
    if reason:
        out["note"] = reason
    return out


def assess_project(project_id: str, store: Store | None = None) -> dict[str, Any]:
    """Project-level meta-assessment (read-only, COMPUTED — no LLM verdict): coverage, open evidence
    gates, open questions, a saturation hint, structural gaps, and a computed
    continue/converge/complete/blocked recommendation. The host reads this every iteration to stay
    purposeful in a long run and to decide when to stop (spec/harness-evaluation-and-autonomy.md HX1).
    """
    from . import plan as _p
    store = store or Store()
    plan = _p.get_plan(project_id, store=store)
    if plan is None:
        raise _p.PlanError("NO_PLAN", f"project {project_id} has no plan")
    tasks = plan["tasks"]
    by_bucket: dict[str, dict[str, int]] = {}
    for t in tasks:
        b = by_bucket.setdefault(t["bucket"], {"done": 0, "total": 0})
        b["total"] += 1
        b["done"] += 1 if t["status"] == "done" else 0
    # open evidence gates: every not-done verify and what it still needs
    open_gates = []
    for t in tasks:
        if t["bucket"] == "verify" and t["status"] != "done":
            unmet = _p.verify_unmet(plan, t, store)
            open_gates.append({"task": t["id"], "title": t["title"], "unmet": unmet})
    cov = _p.coverage_hint(project_id, store=store)
    try:
        oqs = [o["text"] for o in store.list_open_questions(project_id) if o.get("status") == "open"]
    except Exception:
        oqs = []
    # saturation hint: act evidence accumulated vs convergences produced (a coarse, honest proxy —
    # NOT a score; "are we still diverging faster than we converge?"). PLAN-AWARE: the ratio only
    # means anything once the plan's divergent work has actually happened — a half-done plan must
    # never read "converging" (a real run stalled after Define because this hint + empty
    # open_questions matched the published stop rule with the entire second diamond untouched).
    n_act = sum(1 for t in tasks if t["bucket"] == "act" and t["status"] == "done")
    n_syn = cov["evidence_by_kind"].get("synthesis", 0)
    n_council = cov["evidence_by_kind"].get("council", 0)
    divergent_open = any(t["status"] != "done" and t["bucket"] in ("analyze", "act") for t in tasks)
    if all(t["status"] == "done" for t in tasks):
        sat_hint = "complete"               # a finished plan is not "diverging" in any sense
    elif not n_act:
        sat_hint = "early — no act evidence yet"
    elif divergent_open:
        sat_hint = "still diverging"        # later phases haven't produced their act evidence yet
    elif n_syn and n_act <= n_syn * 2:
        sat_hint = "converging"             # all divergent work done; consolidation keeps pace
    else:
        sat_hint = "still diverging"
    # structural gaps
    gaps = []
    for g in open_gates:
        for u in g["unmet"]:
            gaps.append(f"{g['title']}: {u}")
    judged_refs = {str(r) for j in plan.get("judgments", []) for r in (j.get("evidence_refs") or [])}
    parked_refs = {str(r) for p in plan.get("parked_refs", []) for r in (p.get("refs") or [])}
    for tsk in tasks:
        if tsk["bucket"] != "act" or tsk.get("status") != "done":
            continue
        downstream_closed = any(v.get("bucket") == "verify" and v.get("status") == "done"
                                and set(v.get("consumes") or []) & set(tsk.get("consumes") or [])
                                for v in tasks)
        if not downstream_closed:
            continue
        for ref in tsk.get("produces", []):
            if ref.get("kind") == "frame":
                continue
            rid, kind = str(ref.get("id") or ""), str(ref.get("kind") or "")
            names = {rid, f"{kind}:{rid}"}
            if not rid or (names & judged_refs) or (names & parked_refs):
                continue
            gaps.append(f"{tsk['title']}: produced {kind}:{rid} but no completed gate cites it — "
                        f"record_judgment(evidence_refs=[...]) or park the evidence explicitly")
    # CONTENT-quality gaps (right level of assessment, not just structure): a verify that converged
    # without a linked synthesis (orphaned convergence), or whose synthesis is near-empty (the answer
    # artifact is hollow — substance may be stranded in notes). Soft signals; they don't block the gate.
    for tsk in tasks:
        if tsk["bucket"] != "verify":
            continue
        syn_refs = [r for r in tsk.get("produces", []) if r.get("kind") == "synthesis"]
        if tsk["status"] == "done" and not syn_refs:
            gaps.append(f"{tsk['title']}: completed without a linked synthesis — record_synthesis → "
                        f"link_evidence (the converging answer artifact is missing/orphaned)")
        for r in syn_refs:
            syn = store.get_synthesis(r["id"]) or {}
            body = (syn.get("gesamtbild", "") + syn.get("positionierung", "") + syn.get("arc_narrative", "")).strip()
            if len(body) < 200:
                gaps.append(f"{tsk['title']}: synthesis is thin/empty — fill gesamtbild/positionierung "
                            f"(the synthesis IS the answer; don't leave it only in notes)")
    # proband-session groundedness (GAP-5): unverified sessions mean the "personas really USED it"
    # evidence is soft — surface it so a long run doesn't converge on unverified usage.
    try:
        psess = [s for s in store.list_prototype_sessions()
                 if (store.get_prototype(s.get("prototype_id", "")) or {}).get("project_id") == project_id]
        ungrounded = [s for s in psess if not s.get("grounded_verified")]
        if psess and ungrounded:
            gaps.append(f"{len(ungrounded)}/{len(psess)} proband session(s) ungrounded (not verified "
                        f"against real observed usage) — re-test by driving the prototype so the evidence is real")
    except Exception:
        pass
    # novelty signal: distinct artifact KINDS + whether an interactive `model` exists, so a run sees
    # if its solution space is too narrow (forms only) and can push for bolder concept diversity. A
    # descriptive hint, never a hard gate — innovation is host-judged, not enforced (no hardcoded DT).
    try:
        protos = store.list_prototypes(project_id)
        kinds = sorted({(p.get("type") or "prototype") for p in protos})
        has_model = any((p.get("type") == "model") for p in protos)
        if protos:
            novelty = {"artifact_kinds": kinds, "distinct_kinds": len(kinds), "has_interactive_model": has_model,
                       "hint": ("diverse" if (len(kinds) >= 3 or has_model)
                                else "narrow — few concept KINDS and no interactive model; consider an "
                                     "experienceable model + a dark-horse (see next_action.act.ideation_lenses)")}
            if novelty["hint"].startswith("narrow"):
                gaps.append("solution space is narrow (few artifact kinds, no interactive model) — "
                            "apply the ideation lenses for a bolder, more experienceable concept")
        else:
            novelty = {"artifact_kinds": [], "distinct_kinds": 0, "has_interactive_model": False, "hint": "no artifacts yet"}
    except Exception:
        novelty = {}
    # FINISH readiness: gates-passed is NOT the same as a finished, exhaustive, well-told project. A
    # run must not stop at "a good starting point". `finish` checks the project is ORGANIZED (sections),
    # CONCLUDED (a substantial terminal synthesis), and HANDED OFF (a report) — generic, data-
    # driven, methodology-agnostic. When the plan's gates are all met but these are missing, the
    # recommendation is `finish`, not `complete`.
    finish_gaps: list[str] = []
    # only a SUBSTANTIAL project (a methodology run, or one that produced prototypes) is held to the
    # finish bar — a minimal freeform inquiry (a lone frame) is legitimately complete as-is.
    substantial = bool(plan.get("methodology")) or bool(store.list_prototypes(project_id))
    handoff = report_handoff_state(None)
    handoff_ok = not substantial
    try:
        project = store.get_research_project(project_id) or {}
        if substantial and not (project.get("sections") or []):
            finish_gaps.append("not organized — create phase/theme SECTIONS (Discover/Define/Solution/"
                               "Prototype-ladder/Deliver) so the hi-fi + conclusion are surfaced")
        # a substantial terminal conclusion: the last verify task's synthesis, non-thin
        verify_syn = [r["id"] for t in tasks if t["bucket"] == "verify"
                      for r in t.get("produces", []) if r.get("kind") == "synthesis"]
        concl = store.get_synthesis(verify_syn[-1]) if verify_syn else None
        body = (concl or {}).get("gesamtbild", "") + (concl or {}).get("positionierung", "") if concl else ""
        if substantial and (not concl or len(body.strip()) < 400):
            finish_gaps.append("no substantial CONCLUSION — author a rich terminal solution-presentation "
                               "synthesis (the answer, who-wins + non-targets, validated solvers, build spec)")
        try:
            handoff = report_handoff_state(store.list_reports(project_id))
            handoff_ok = not substantial or handoff["complete"]
            if substantial and not handoff["exists"]:
                finish_gaps.append("no REPORT — author the project narrative/handover (scaffold_synthesis)")
            elif substantial and not handoff["complete"]:
                finish_gaps.append(
                    "REPORT incomplete — author every scaffolded section with "
                    "record_synthesis_section before handing it off")
        except Exception:
            handoff_ok = not substantial
            finish_gaps.append("REPORT state unavailable — retry the read before completion")
    except Exception:
        # Unknown evidence is never evidence of completion.  This path is read-only,
        # so surface a stable gap rather than swallowing a storage/decoder failure
        # into `finished=true`.
        finish_gaps = ["finish evidence unavailable — retry project/synthesis reads before completion"]
    if finish_gaps:
        gaps.extend(finish_gaps)
    finish = {"organized": not any("organized" in g for g in finish_gaps),
              "concluded": not any("CONCLUSION" in g for g in finish_gaps),
              "handed_off": handoff_ok,
              "finished": not finish_gaps, "gaps": finish_gaps,
              "report_handoff": handoff}
    # memory_depth (ESV6): councils are only as deep as the simulated lives behind them — flag a thin
    # cohort so a run deepens memory (simulate-cohort) before concluding it has explored deeply.
    memory_depth = {}
    try:
        pids = (store.get_research_project(project_id) or {}).get("persona_ids", [])
        if pids:
            m = store.count_memory_for_personas(pids)
            avg = (m["facts"] + m["events"]) / max(1, len(pids))
            memory_depth = {"personas": len(pids), "facts": m["facts"], "events": m["events"],
                            "avg_per_persona": round(avg, 1),
                            "hint": "deep" if avg >= 6 else "thin — deepen the cohort (simulate-cohort) for richer councils"}
            if memory_depth["hint"].startswith("thin"):
                gaps.append("cohort memory is thin (few simulated events/facts per persona) — deepen it "
                            "(simulate-cohort) so councils are grounded in rich lived experience")
    except Exception:
        memory_depth = {}
    ready = _p.ready_tasks(plan)
    tasks_complete = _p.is_complete(plan)
    from . import result_outcomes as _result_outcomes
    result_contract = _result_outcomes.project_result_contract_state(store, project_id)
    complete = tasks_complete and result_contract.get("satisfied", True)
    rs = run_state(project_id, plan, store)
    if tasks_complete and not result_contract.get("satisfied", True):
        rec = "finish"
    elif complete and finish_gaps:
        rec = "finish"            # gates met but not a finished, organized, concluded project
    elif complete:
        rec = "complete"
    elif not ready:
        rec = "blocked"
    else:
        ready_verify = [t for t in ready if t["bucket"] == "verify" and not _p.verify_unmet(plan, t, store)]
        ready_analyze = [t for t in ready if t["bucket"] == "analyze"]
        if ready_verify:
            rec = "converge"          # a gate is satisfied → consolidate
        elif ready_analyze:
            rec = "frame"             # understand before acting
        else:
            rec = "act"               # do more work to satisfy a gate
    from .services import web_url
    return {
        "project_id": project_id, "goal": plan.get("goal", ""), "complete": complete,
        "tasks_complete": tasks_complete,
        # the link to hand the user alongside the status (was absent — an agent reporting
        # project health had no URL to show)
        "url": web_url(f"/jobs/{project_id}"),
        "recommendation": rec,
        **({"run_state": rs} if rs else {}),
        "coverage": cov,
        "tasks_by_bucket": by_bucket,
        "open_gates": open_gates,
        "open_questions": oqs,
        "saturation": {"act_done": n_act, "councils": n_council, "syntheses": n_syn,
                       "hint": sat_hint},
        "novelty": novelty,
        "finish": finish,
        "result_contract": result_contract,
        "memory_depth": memory_depth,
        "gaps": gaps,
        "ready": [t["id"] for t in ready],
        "next": _p.brief_next(project_id, store=store).get("instructions", ""),
    }
