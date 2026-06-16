"""Research-plan engine (spec/research-plan-engine.md).

The orchestrator's SOURCE OF TRUTH for a project: a per-project DAG of tasks bucketed
analyze/act/verify, each bound to a capability and referencing the evidence it produced
(councils / syntheses / artifacts / sessions / frames). The methodology constellation seeds a
plan; a freeform project starts from a single `frame` task. Rendered to plan.md on demand.

Tag-driven, like the methodology engine: `bucket` and `capability` and evidence `kind` are OPEN
tags validated by reference — there is NO closed set in code. The host authors the plan + all text.
"""
from __future__ import annotations

from typing import Any

from .config import utc_now_iso
from .storage import Store


class PlanError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


# ------------------------------------------------------------------ normalization

def _ref(r: dict[str, Any]) -> dict[str, str]:
    """An EvidenceRef {kind, id} — kind is a free tag (council/synthesis/artifact/session/frame/…)."""
    return {"kind": str((r or {}).get("kind", "")), "id": str((r or {}).get("id", ""))}


def _norm_task(raw: dict[str, Any]) -> dict[str, Any]:
    requires = dict(raw.get("requires") or {})
    return {
        "id": raw.get("id"),
        "title": raw.get("title", raw.get("id") or ""),
        "intent": raw.get("intent", ""),
        "phase_intent": raw.get("phase_intent", ""),  # the PHASE's ambitions (surfaced on the act lane)
        "plan_note": raw.get("plan_note", ""),
        "bucket": raw.get("bucket", ""),            # analyze | act | verify (free tag)
        "capability": raw.get("capability", ""),    # frame | explore | cluster | decide | … (free tag)
        "step": raw.get("step", ""),                # optional grouping under a constellation step
        "consumes": [str(c) for c in (raw.get("consumes") or [])],
        "status": raw.get("status", "todo"),        # todo | active | done | blocked
        "produces": [_ref(r) for r in (raw.get("produces") or [])],
        "requires": {
            "min_inputs": int(requires["min_inputs"]) if requires.get("min_inputs") is not None else None,
            "gate_tag": requires.get("gate_tag", ""),
            "artifact_tags": list(requires.get("artifact_tags") or []),
            "session_of_tags": list(requires.get("session_of_tags") or []),
        },
        "loop_back": raw.get("loop_back", ""),
        "presentation": dict(raw.get("presentation") or {}),
        "frame": dict(raw["frame"]) if raw.get("frame") else None,   # analyze output (questions/hypotheses)
    }


def _assert_acyclic(tasks: list[dict[str, Any]]) -> None:
    by_id = {t["id"]: t for t in tasks}
    state: dict[str, int] = {}

    def visit(tid: str) -> None:
        if state.get(tid) == 1:
            return
        if state.get(tid) == 0:
            raise PlanError("BAD_PLAN", f"`consumes` graph has a cycle at '{tid}'")
        state[tid] = 0
        for c in by_id[tid]["consumes"]:
            visit(c)
        state[tid] = 1

    for t in tasks:
        visit(t["id"])


def validate_plan(plan: dict[str, Any]) -> dict[str, Any]:
    """Validate + normalize a plan in place. Tag-agnostic: only graph mechanics + references."""
    if not isinstance(plan, dict):
        raise PlanError("BAD_PLAN", "plan must be an object")
    if not plan.get("project_id"):
        raise PlanError("BAD_PLAN", "plan needs a project_id")
    tasks = [_norm_task(t) for t in (plan.get("tasks") or [])]
    ids = [t["id"] for t in tasks]
    if not all(ids) or len(set(ids)) != len(ids):
        raise PlanError("BAD_PLAN", "task ids must be present and unique")
    idset = set(ids)
    for t in tasks:
        if not t["bucket"]:
            raise PlanError("BAD_PLAN", f"task '{t['id']}' needs a bucket tag")
        for c in t["consumes"]:
            if c not in idset:
                raise PlanError("BAD_PLAN", f"task '{t['id']}' consumes unknown task '{c}'")
            if c == t["id"]:
                raise PlanError("BAD_PLAN", f"task '{t['id']}' cannot consume itself")
        if t["loop_back"] and t["loop_back"] not in idset:
            raise PlanError("BAD_PLAN", f"task '{t['id']}' loop_back '{t['loop_back']}' is not a task")
    _assert_acyclic(tasks)
    plan["tasks"] = tasks
    return plan


# ------------------------------------------------------------------ lifecycle

def new_plan(project_id: str, goal: str = "", methodology: str = "",
             tasks: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    now = utc_now_iso()
    return validate_plan({"project_id": project_id, "goal": goal, "methodology": methodology,
                          "tasks": tasks or [], "created_at": now, "updated_at": now})


def seed_plan_from_methodology(project_id: str, goal: str, spec: dict[str, Any]) -> dict[str, Any]:
    """Expand a methodology constellation into a seed plan: a `frame` (analyze) task per fan step
    and a `verify` task per decide step, wired along the step DAG and carrying the decide gates.
    The orchestrator fills the `act` lane (councils/artifacts/sessions consuming each frame) at run
    time. The first fan's frame is the root analyze task (dischargeable)."""
    from . import methodology as M
    steps = spec["steps"]
    fan_frame = {s["id"]: f"frame__{s['id']}" for s in steps if not M._is_decide(s)}
    decide_verify = {s["id"]: f"verify__{s['id']}" for s in steps if M._is_decide(s)}

    def map_target(step_id: str) -> str:
        return fan_frame.get(step_id) or decide_verify.get(step_id) or ""

    tasks: list[dict[str, Any]] = []
    for s in steps:
        sid = s["id"]
        cap = s["tags"][0] if s.get("tags") else ""
        # EVERY constellation edge maps 1:1 onto a seeded edge — including same-type ones
        # (fan→fan, decide→decide), so a non-alternating DAG keeps its ordering. The breadth
        # gate stays honest: frame tasks only ever produce `frame` refs and verify siblings are
        # excluded by bucket, so neither counts as act evidence in verify_unmet/_fan_tasks.
        cons = [map_target(c) for c in s["consumes"]]
        if M._is_decide(s):
            tasks.append({
                "id": decide_verify[sid], "title": f"Decide · {s['name']}", "bucket": "verify",
                "capability": cap or "decide", "step": sid, "intent": s["intent"], "consumes": cons,
                "requires": s["requires"], "loop_back": map_target(s.get("loop_back", "")),
                "produces": [], "presentation": s.get("presentation") or {}})
        else:
            # The frame task's intent describes ONLY the framing step — a modest record_frame. The
            # phase's full ambitions (ideation lenses, prototype ladder, breadth) ride along as
            # `phase_intent` and surface on the ACT lane via next_action; packing them into the
            # frame instruction made the next step read like a whole new project at exactly the
            # phase boundary where a host decides whether to continue (a real run balked there).
            tasks.append({
                "id": fan_frame[sid], "title": f"Frame · {s['name']}", "bucket": "analyze",
                "capability": "frame", "step": sid, "consumes": cons,
                "intent": f"Frame the questions/angles for '{s['name']}' before acting — read persona "
                          f"memory + prior evidence, then record_frame(questions, hypotheses, "
                          f"memory_refs). Do not conclude early; the phase's build/ideation ambitions "
                          f"surface on the act lane once this frame is recorded.",
                "phase_intent": s["intent"],
                "produces": [], "presentation": s.get("presentation") or {}})
    return new_plan(project_id, goal, spec["key"], tasks)


def get_plan(project_id: str, store: Store | None = None) -> dict[str, Any] | None:
    store = store or Store()
    p = store.get_research_plan(project_id)
    return validate_plan(p) if p else None


def save_plan(plan: dict[str, Any], store: Store | None = None) -> dict[str, Any]:
    store = store or Store()
    validate_plan(plan)
    plan.setdefault("created_at", utc_now_iso())
    plan["updated_at"] = utc_now_iso()
    store.upsert_research_plan(plan)
    return plan


def task(plan: dict[str, Any], task_id: str) -> dict[str, Any] | None:
    return next((t for t in plan["tasks"] if t["id"] == task_id), None)


def ready_tasks(plan: dict[str, Any]) -> list[dict[str, Any]]:
    """The frontier: tasks whose `consumes` are all done and which are not themselves done."""
    done = {t["id"] for t in plan["tasks"] if t["status"] == "done"}
    return [t for t in plan["tasks"]
            if t["status"] != "done" and all(c in done for c in t["consumes"])]


def is_complete(plan: dict[str, Any]) -> bool:
    return all(t["status"] == "done" for t in plan["tasks"]) and bool(plan["tasks"])


# ------------------------------------------------------------------ mutations

def add_task(project_id: str, bucket: str, capability: str, title: str, intent: str = "",
             consumes: list[str] | None = None, requires: dict | None = None, step: str = "",
             plan_note: str = "", task_id: str | None = None, store: Store | None = None) -> dict[str, Any]:
    """Insert a task into the plan (the orchestrator shaping the breadth — e.g. another act council,
    an extra analyze, a mid-stream synthesis). Returns the created task."""
    store = store or Store()
    plan = get_plan(project_id, store=store)
    if plan is None:
        raise PlanError("NO_PLAN", f"project {project_id} has no plan")
    tid = task_id or _fresh_id(plan, f"{bucket}__{capability or 'task'}")
    raw = {"id": tid, "title": title, "bucket": bucket, "capability": capability, "intent": intent,
           "step": step, "consumes": consumes or [], "requires": requires or {}, "plan_note": plan_note}
    plan["tasks"].append(_norm_task(raw))
    save_plan(plan, store=store)
    return task(plan, tid)


def _fresh_id(plan: dict[str, Any], base: str) -> str:
    existing = {t["id"] for t in plan["tasks"]}
    if base not in existing:
        return base
    i = 2
    while f"{base}_{i}" in existing:
        i += 1
    return f"{base}_{i}"


def record_frame(project_id: str, task_id: str, questions: list[str], hypotheses: list[str] | None = None,
                 memory_refs: list[str] | None = None, store: Store | None = None) -> dict[str, Any]:
    """Discharge an `analyze` frame task: author research questions + hypotheses grounded in cited
    persona memory / prior evidence. Default-but-discharge­able: must cite >=1 memory ref and >=1
    question (can't be silently skipped), but a minimal honest frame discharges it."""
    store = store or Store()
    plan = get_plan(project_id, store=store)
    if plan is None:
        raise PlanError("NO_PLAN", f"project {project_id} has no plan")
    t = task(plan, task_id)
    if not t:
        raise PlanError("BAD_FRAME", f"unknown task '{task_id}'")
    if t["bucket"] != "analyze":
        raise PlanError("BAD_FRAME", f"record_frame targets an analyze task (got bucket '{t['bucket']}')")
    qs = [str(q).strip() for q in (questions or []) if str(q).strip()]
    refs = [str(r).strip() for r in (memory_refs or []) if str(r).strip()]
    if not qs:
        raise PlanError("BAD_FRAME", "a frame needs >= 1 research question")
    if not refs:
        raise PlanError("BAD_FRAME", "a frame must cite >= 1 memory ref (persona memory / prior evidence)")
    t["frame"] = {"questions": qs, "hypotheses": [str(h).strip() for h in (hypotheses or []) if str(h).strip()],
                  "memory_refs": refs}
    t["produces"] = [{"kind": "frame", "id": task_id}]
    t["status"] = "done"
    save_plan(plan, store=store)
    return t


# ------------------------------------------------------------------ evidence, judgments, gates

def link_evidence(project_id: str, task_id: str, ref: dict[str, Any],
                  store: Store | None = None) -> dict[str, Any]:
    """Attach an evidence ref {kind,id} (council/artifact/session/synthesis) to a task (usually an
    act task whose run-council/scaffold/session just produced it)."""
    store = store or Store()
    plan = get_plan(project_id, store=store)
    if plan is None:
        raise PlanError("NO_PLAN", f"project {project_id} has no plan")
    t = task(plan, task_id)
    if not t:
        raise PlanError("BAD_LINK", f"unknown task '{task_id}'")
    r = _ref(ref)
    if not r["id"] or not r["kind"]:
        raise PlanError("BAD_LINK", "evidence ref needs a kind and an id")
    if r not in t["produces"]:
        t["produces"].append(r)
    save_plan(plan, store=store)
    return t


def record_judgment(project_id: str, task_id: str, gate_tag: str, decided: bool, rationale: str,
                    evidence_refs: list[str] | None = None, store: Store | None = None) -> dict[str, Any]:
    """Record an evidence-backed gate judgment against a task (the fan or the verify). gate_tag is a
    FREE tag; a decided judgment needs a rationale + >=1 evidence_ref."""
    store = store or Store()
    plan = get_plan(project_id, store=store)
    if plan is None:
        raise PlanError("NO_PLAN", f"project {project_id} has no plan")
    if task(plan, task_id) is None:
        raise PlanError("BAD_JUDGMENT", f"unknown task '{task_id}'")
    if not (gate_tag or "").strip():
        raise PlanError("BAD_JUDGMENT", "a judgment needs a gate_tag")
    refs = [str(r) for r in (evidence_refs or []) if str(r).strip()]
    if decided and not rationale.strip():
        raise PlanError("BAD_JUDGMENT", "a decided judgment needs a rationale")
    if decided and not refs:
        raise PlanError("BAD_JUDGMENT", "a decided gate judgment needs >= 1 evidence_ref")
    j = {"task_id": task_id, "gate_tag": gate_tag, "decided": bool(decided),
         "rationale": rationale.strip(), "evidence_refs": refs, "created_at": utc_now_iso()}
    plan.setdefault("judgments", []).append(j)
    save_plan(plan, store=store)
    return j


def _ref_text(raw: Any) -> str:
    if isinstance(raw, dict):
        r = _ref(raw)
        return f"{r['kind']}:{r['id']}" if r["kind"] and r["id"] else r["id"]
    return str(raw or "").strip()


def park_evidence(project_id: str, refs: list[Any], reason: str, task_id: str = "",
                  store: Store | None = None) -> dict[str, Any]:
    """Mark evidence as deliberately not flowing into a downstream gate.

    This is the explicit counterpart to a trace gap: a produced ref can be useful context but not
    decision evidence. Parking keeps it visible and auditable instead of letting agents silently
    strand it.
    """
    store = store or Store()
    plan = get_plan(project_id, store=store)
    if plan is None:
        raise PlanError("NO_PLAN", f"project {project_id} has no plan")
    if task_id and task(plan, task_id) is None:
        raise PlanError("BAD_PARK", f"unknown task '{task_id}'")
    clean = [r for r in (_ref_text(x) for x in (refs or [])) if r]
    if not clean:
        raise PlanError("BAD_PARK", "park_evidence needs >= 1 evidence ref")
    why = str(reason or "").strip()
    if not why:
        raise PlanError("BAD_PARK", "park_evidence needs a reason")
    rec = {"task_id": task_id, "refs": clean, "reason": why, "created_at": utc_now_iso()}
    parked = plan.setdefault("parked_refs", [])
    key = (task_id, tuple(sorted(clean)), why)
    if not any((p.get("task_id", ""), tuple(sorted(p.get("refs") or [])), p.get("reason", "")) == key
               for p in parked):
        parked.append(rec)
        save_plan(plan, store=store)
    return rec


def _fan_tasks(plan: dict[str, Any], vtask: dict[str, Any]) -> list[dict[str, Any]]:
    """The act 'fan' a verify task consolidates: sibling tasks sharing one of its consumed frames."""
    frames = set(vtask["consumes"])
    return [t for t in plan["tasks"]
            if t["id"] != vtask["id"] and (set(t["consumes"]) & frames) and t["bucket"] != "verify"]


def _fan_evidence(plan: dict[str, Any], vtask: dict[str, Any]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for t in _fan_tasks(plan, vtask):
        for r in t["produces"]:
            if r["kind"] != "frame":
                out.append(r)
    return out


def _eff_min(vtask: dict[str, Any]) -> int:
    mi = vtask["requires"]["min_inputs"]
    return mi if mi is not None else 2


def verify_unmet(plan: dict[str, Any], vtask: dict[str, Any], store: Store) -> list[str]:
    """Non-raising: what a verify task still needs before it can complete."""
    from . import methodology as M
    pid = plan["project_id"]
    req = vtask["requires"]
    unmet: list[str] = []
    # Breadth = distinct ACT tasks (angles) that produced evidence — NOT raw evidence refs. Counting
    # refs let one prototype's (artifact + N sessions) masquerade as "enough exploration", so a phase
    # could converge on a single angle. Distinct tasks force genuine breadth (≥ min_inputs angles).
    fan_tasks = [t for t in _fan_tasks(plan, vtask) if any(r.get("kind") != "frame" for r in t.get("produces", []))]
    eff = _eff_min(vtask)
    if len(fan_tasks) < eff:
        unmet.append(f"need >= {eff} act tasks (distinct angles) with evidence in the fan (have {len(fan_tasks)})")
    if req["gate_tag"]:
        scope = {vtask["id"], *vtask["consumes"], *[t["id"] for t in _fan_tasks(plan, vtask)]}
        ok = any(j.get("decided") and j["gate_tag"] == req["gate_tag"] and j["task_id"] in scope
                 for j in plan.get("judgments", []))
        if not ok:
            unmet.append(f"a decided `{req['gate_tag']}` judgment must exist")
    for tg in req["artifact_tags"]:
        if not M._project_artifacts_with(store, pid, tg):
            unmet.append(f"need >= 1 artifact tagged `{tg}`")
    for tg in req["session_of_tags"]:
        sess = M._sessions_of(store, pid, tg)
        if not sess:
            unmet.append(f"need >= 1 recorded session of an artifact tagged `{tg}`")
        elif _grounding_verifiable() and not any(s.get("grounded_verified") for s in sess):
            # GAP-5: when the harness CAN verify, an unverified session is not real-usage evidence —
            # a converge can't pass its proband-test gate on it. Degrades gracefully where Playwright
            # is unavailable (then any recorded session counts, as before).
            unmet.append(f"need >= 1 GROUNDED session of `{tg}` — {len(sess)} recorded but none verified "
                         f"against real observed usage; drive the prototype (proto_open/proto_act) and "
                         f"cite states you actually saw, then record")
    return unmet


def _grounding_verifiable() -> bool:
    """True when the Playwright harness is available, so an ungrounded proband session is a real gap
    (not just a degraded-environment artefact). Lazy import avoids a hard browser dependency."""
    try:
        from . import browser as _browser
        return bool(_browser.available())
    except Exception:
        return False


def complete_task(project_id: str, task_id: str, store: Store | None = None) -> dict[str, Any]:
    """Mark a ready task done. Verify tasks are gate-checked (breadth + gate judgment + artifacts/
    sessions) and rejected until satisfied. Completion never loops: a task's `loop_back` is honored
    by the HOST calling iterate_task (plan_iterate.py) when it judges another round is needed."""
    store = store or Store()
    plan = get_plan(project_id, store=store)
    if plan is None:
        raise PlanError("NO_PLAN", f"project {project_id} has no plan")
    t = task(plan, task_id)
    if not t:
        raise PlanError("BAD_TASK", f"unknown task '{task_id}'")
    ready = {x["id"] for x in ready_tasks(plan)}
    if task_id not in ready:
        raise PlanError("TASK_NOT_READY", f"task '{task_id}' is not on the ready frontier")
    if t["bucket"] == "verify":
        unmet = verify_unmet(plan, t, store)
        if unmet:
            raise PlanError("GATE_UNMET", f"verify task '{task_id}' blocked: {unmet}")
    t["status"] = "done"
    save_plan(plan, store=store)
    # Non-terminal completion: say so in-band — the host deciding "is this enough?" right after a
    # gate passes is exactly where a run stalls, so the response itself carries the progress truth.
    out = dict(t)
    n_done = sum(1 for x in plan["tasks"] if x["status"] == "done")
    if n_done < len(plan["tasks"]):
        nxt = [x["id"] for x in ready_tasks(plan)]
        out["progress"] = {"tasks_done": n_done, "tasks_total": len(plan["tasks"]), "next_ready": nxt,
                           "note": (f"{n_done}/{len(plan['tasks'])} tasks done — the project is NOT "
                                    f"finished; next ready: {', '.join(nxt) or 'none (blocked)'}")}
        rs = run_state(project_id, plan, store)
        if rs:
            out["run_state"] = rs
    return out


def coverage_hint(project_id: str, store: Store | None = None) -> dict[str, Any]:
    """A NON-binding, descriptive evidence-coverage snapshot (counts only — never a score or a
    gate). Helps the host judge progress; it does not decide anything."""
    store = store or Store()
    plan = get_plan(project_id, store=store)
    refs = [r for t in (plan["tasks"] if plan else []) for r in t["produces"]]
    kinds: dict[str, int] = {}
    for r in refs:
        kinds[r["kind"]] = kinds.get(r["kind"], 0) + 1
    artifacts = store.list_prototypes(project_id)
    sessions = [s for s in store.list_prototype_sessions()
                if (store.get_prototype(s.get("prototype_id", "")) or {}).get("project_id") == project_id]
    personas_touched = set()
    for t in (plan["tasks"] if plan else []):
        for r in t["produces"]:
            if r["kind"] == "council":
                for pid in (store.get_council_session(r["id"]) or {}).get("persona_ids", []):
                    personas_touched.add(pid)
    return {"evidence_by_kind": kinds, "artifacts": len(artifacts), "sessions": len(sessions),
            "personas_touched": len(personas_touched),
            "tasks_done": sum(1 for t in (plan["tasks"] if plan else []) if t["status"] == "done"),
            "tasks_total": len(plan["tasks"]) if plan else 0}


def assess_progress(project_id: str, task_id: str, rationale: str, evidence_refs: list[str],
                    delta: str = "", store: Store | None = None) -> dict[str, Any]:
    """Record an evidence-backed, LLM-judged assessment of progress toward the HMW goal. `delta` is a
    FREE host judgment (e.g. 'näher', 'beantwortet', or prose) — never a hardcoded numeric metric.
    A non-binding coverage snapshot is attached for context."""
    store = store or Store()
    plan = get_plan(project_id, store=store)
    if plan is None:
        raise PlanError("NO_PLAN", f"project {project_id} has no plan")
    if task(plan, task_id) is None:
        raise PlanError("BAD_PROGRESS", f"unknown task '{task_id}'")
    refs = [str(r) for r in (evidence_refs or []) if str(r).strip()]
    if not rationale.strip():
        raise PlanError("BAD_PROGRESS", "a progress assessment needs a rationale")
    if not refs:
        raise PlanError("BAD_PROGRESS", "a progress assessment must cite >= 1 evidence_ref")
    rec = {"task_id": task_id, "goal": plan.get("goal", ""), "delta": str(delta),
           "rationale": rationale.strip(), "evidence_refs": refs,
           "coverage": coverage_hint(project_id, store=store), "created_at": utc_now_iso()}
    plan.setdefault("progress", []).append(rec)
    save_plan(plan, store=store)
    return rec


def brief_next(project_id: str, store: Store | None = None) -> dict[str, Any]:
    """Plan router: the ready task frontier + per-task instructions (bucket/capability aware)."""
    store = store or Store()
    plan = get_plan(project_id, store=store)
    if plan is None:
        raise PlanError("NO_PLAN", f"project {project_id} has no plan")
    ready = ready_tasks(plan)
    if not ready:
        done = is_complete(plan)
        return {"project_id": project_id, "complete": done, "ready": [],
                "instructions": ("Plan complete — export plan.md and present the answer." if done
                                 else "No ready tasks — resolve a blocker / open question, or add tasks.")}
    # prefer analyze, then act, then verify when several are ready
    pref = {"analyze": 0, "act": 1, "verify": 2}
    primary = sorted(ready, key=lambda t: (pref.get(t["bucket"], 3), plan["tasks"].index(t)))[0]
    unmet: list[str] = []
    if primary["bucket"] == "analyze":
        instr = (f"ANALYZE/{primary['capability']}: {primary['intent']} → record_frame(questions, "
                 f"hypotheses, memory_refs citing persona memory). Understand before concluding.")
        if primary["capability"] == "frame":
            unmet.append("record_frame (>=1 question + >=1 memory ref)")
    elif primary["bucket"] == "verify":
        unmet = verify_unmet(plan, primary, store)
        instr = (f"VERIFY/{primary['capability']}: consolidate the fan into a {primary['capability']} "
                 f"(record_synthesis / record_decision), record the gate judgment, then complete_task.")
        if primary["loop_back"]:
            instr += (f" If the outcome says iterate, iterate_task('{primary['id']}') opens the next "
                      f"round from '{primary['loop_back']}' (host-judged, never automatic).")
    else:
        instr = (f"ACT/{primary['capability']}: do the work (run-council on a framed question / "
                 f"scaffold_artifact / record_artifact_session), link_evidence, then complete_task. "
                 f"Breadth = angles × persona diversity, not one council per persona.")
    return {
        "project_id": project_id, "task": primary["id"], "ready": [t["id"] for t in ready],
        "bucket": primary["bucket"], "capability": primary["capability"], "title": primary["title"],
        "intent": primary["intent"], "step": primary["step"], "consumes": primary["consumes"],
        "requires": primary["requires"], "unmet": unmet, "complete": False, "instructions": instr,
        "goal": plan.get("goal", ""),
    }


# Methodology-agnostic divergence nudges surfaced on act steps so concept breadth (KIND + boldness) is
# reliable, not luck of a disciplined agent. These reference the DATA palette; no methodology vocabulary
# or design-thinking step is hardcoded (spec/exploration-depth-and-prototype-variety GAP-2 / SPEC-A).
_DIVERGENCE_NUDGES = [
    "Diversify the KIND of artifact (see artifact_palette): a guided flow, a comparison, an overview, a "
    "card interface, or an interactive MODEL (steerable numbers/curve a persona can actually drive) — "
    "not N near-identical forms.",
    "Include >= 1 deliberately EXTREME / unexpected concept (a 'dark-horse') to stretch the space; an "
    "honest 'this is not for you' verdict can be a legitimate, trust-winning concept.",
    "For an exploratory step, consider a DISCONFIRMATION council: deliberately load the segments most "
    "likely to REJECT the premise and test a Non-Fit motion — the most honest insight often comes from "
    "the refuters, not the supporters.",
]


def _artifact_palette() -> list[dict[str, Any]]:
    try:
        from . import presentation as _pres
        return _pres.artifact_palette()
    except Exception:
        return []


def _ideation_lenses() -> list[dict[str, Any]]:
    try:
        from . import presentation as _pres
        return _pres.ideation_lenses()
    except Exception:
        return []


def _diverse_participants(store: Store, persona_ids: list[str], k: int = 6) -> list[str]:
    """Pick up to k personas SPREAD across a segment axis (attitude/life-stage), so a council gets
    real diversity rather than keyword-matched look-alikes (anti-steering)."""
    buckets: dict[str, list[str]] = {}
    for pid in persona_ids:
        p = store.get_persona(pid)
        if not p:
            continue
        seg = p.get("segment") or {}
        key = str(seg.get("einstellung") or seg.get("lebensphase") or seg.get("kanal") or p.get("slug"))
        buckets.setdefault(key, []).append(p["slug"])
    pools = list(buckets.values())
    out: list[str] = []
    i = 0
    while len(out) < k and any(pools) and i < 500:
        pool = pools[i % len(pools)]
        if pool:
            out.append(pool.pop(0))
        i += 1
    return out[:k]


def next_action(project_id: str, store: Store | None = None) -> dict[str, Any]:
    """Lean orchestration step (spec/harness-evaluation-and-autonomy.md HX2): the ready task FULLY
    loaded, so a long autonomous run is one `next_action` → author (subagent) → persist per
    iteration, keeping host context lean. For analyze → grounding (prior syntheses + open questions);
    for act → the framed questions of the consumed frame + segment-diverse suggested participants;
    for verify → the fan to consolidate + the gate to satisfy. Carries the project recommendation."""
    store = store or Store()
    plan = get_plan(project_id, store=store)
    if plan is None:
        raise PlanError("NO_PLAN", f"project {project_id} has no plan")
    b = brief_next(project_id, store=store)
    if b.get("complete"):
        return {"complete": True, "recommendation": "complete", "instructions": b.get("instructions", "")}
    t = task(plan, b["task"])
    project = store.get_research_project(project_id) or {}
    persona_ids = project.get("persona_ids", [])
    out: dict[str, Any] = {"complete": False, "task": b["task"], "bucket": b["bucket"],
                           "capability": b["capability"], "title": b["title"], "intent": b["intent"],
                           "unmet": b.get("unmet", []), "instructions": b["instructions"]}
    if b["bucket"] == "analyze":
        try:
            oqs = [o["text"] for o in store.list_open_questions(project_id) if o.get("status") == "open"]
        except Exception:
            oqs = []
        out["grounding"] = {
            "prior_syntheses": [{"id": s["id"], "title": s.get("title", "")} for s in store.list_syntheses()][:8],
            "open_questions": oqs[:8], "persona_pool": persona_ids,
            "guidance": "record_frame: >=1 research question grounded in CITED persona memory / prior evidence.",
        }
        # cohort-depth pre-flight: while the cohort has ~no memory, every frame repeats the warning
        # ("grounded in persona memory" cannot bind to empty lives) — it disappears once depth exists.
        try:
            if persona_ids:
                m = store.count_memory_for_personas(persona_ids)
                if (m["facts"] + m["events"]) / max(1, len(persona_ids)) < 1:
                    out["grounding"]["cohort_warning"] = (
                        "cohort memory is ~empty — councils will be ungrounded; deepen with "
                        "simulate-cohort (or ground personas from real material) before acting")
        except Exception:
            pass
    elif b["bucket"] == "act":
        questions: list[str] = []
        phase: list[str] = []
        for c in t["consumes"]:
            f = task(plan, c)
            if f and f.get("frame"):
                questions += f["frame"].get("questions", [])
            if f and f.get("phase_intent"):
                phase.append(f["phase_intent"])
        out["act"] = {
            "phase_intent": " ".join(phase),
            "framed_questions": questions[:6],
            "suggested_participants": _diverse_participants(store, persona_ids, k=6),
            "artifact_palette": _artifact_palette(),
            "divergence": _DIVERGENCE_NUDGES,
            "ideation_lenses": _ideation_lenses(),
            "guidance": ("Add an act task per ANGLE; run a REAL multi-persona council, or "
                         "scaffold_artifact + a grounded proband session; link_evidence + complete. "
                         "Breadth = angles × persona diversity, not one council per persona."),
        }
    else:  # verify
        fan = _fan_evidence(plan, t)
        short = len(fan) < _eff_min(t)        # gate not yet satisfiable → ACT first, don't try to converge
        out["verify"] = {
            "fan_evidence": fan, "gate_tag": t["requires"].get("gate_tag"),
            "needs": b.get("unmet", []),
            "guidance": (
                f"Gate not yet satisfiable ({len(fan)}/{_eff_min(t)} inputs) — do the ACT work in `act` "
                f"first (consolidate only once the fan is complete)."
                if short else
                "Consolidate the fan into a synthesis (record_synthesis — councils are OPTIONAL/decoupled), "
                "record the gate judgment, assess_progress, complete_task."),
        }
        if t["loop_back"]:
            out["verify"]["guidance"] += (f" Iteration is host-judged: iterate_task('{t['id']}') opens "
                                          f"the next round from '{t['loop_back']}' when the evidence says loop.")
        # If the fan is still short of min_inputs, the real next move is ACT work for this diamond:
        # surface the consuming frames' questions + diverse participants so the host adds act tasks.
        if short:
            questions: list[str] = []
            phase: list[str] = []
            for c in t["consumes"]:
                f = task(plan, c)
                if f and f.get("frame"):
                    questions += f["frame"].get("questions", [])
                if f and f.get("phase_intent"):
                    phase.append(f["phase_intent"])
            out["act"] = {
                "for_frame": t["consumes"], "framed_questions": questions[:6],
                "phase_intent": " ".join(phase),
                "suggested_participants": _diverse_participants(store, persona_ids, k=6),
                "guidance": ("This verify's fan is incomplete — do ACT work first: add an act task "
                             "per ANGLE consuming the frame, run real councils / build+test prototypes, "
                             "link_evidence + complete, until the gate's min_inputs is met."),
            }
    try:
        out["recommendation"] = assess_project(project_id, store=store)["recommendation"]
    except Exception:
        out["recommendation"] = ""
    rs = run_state(project_id, plan, store)
    if rs:
        out["run_state"] = rs
    return out


# plan.md render lives in plan_render.py, iteration rounds in plan_iterate.py (kept under the
# LOC bar); re-exported for cohesion.
from .plan_render import render_plan_md  # noqa: E402,F401
from .plan_iterate import iterate_task  # noqa: E402,F401
from .plan_assess import assess_project, project_run_state, run_state  # noqa: E402,F401
