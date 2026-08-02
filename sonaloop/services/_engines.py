"""Methodology-engine seam + research-plan-engine seam + prototypes/Playwright seam.

Split out of the original sonaloop/services.py (behavior-preserving).
Cross-module function references are bound at import time by services/__init__.py."""

from __future__ import annotations

import csv
import hashlib
import json
import random
import re
import uuid
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any

from .. import config
from ..config import (
    utc_now_iso, content_language, ensure_content_language, language_instruction,
    critic_threshold, critic_sample_k,
)
from ..models import (
    CalendarEvent,
    CouncilSession,
    DailySummary,
    Evidence,
    ExperienceEvent,
    OpenQuestion,
    PainPointObservation,
    Persona,
    PrototypeSession,
    Reflection,
    ResearchProject,
    SimulationResult,
    Synthesis,
)
from ..storage import Store
from ..taxonomy import GENERIC_TOOLS, normalized_tool_ids, normalized_tools
from .. import memory as memory_mod
from .. import evaluation as evaluation_mod
from ..llm_simulation import (
    build_cohort_critic_prompt,
    build_consolidation_prompt,
    build_synthesis_outline_prompt,
    build_synthesis_section_prompt,
    validate_synthesis_outline_payload,
    validate_synthesis_section_payload,
    build_digest_prompt,
    build_eval_critic_prompt,
    build_evidence_check_prompt,
    build_persona_revision_prompt,
    build_plan_prompt,
    build_profile_prompt,
    build_synthesis_prompt,
    validate_activity_payload,
    validate_cohort_critic_payload,
    validate_digest_payload,
    validate_eval_critic_payload,
    validate_evidence_check_payload,
    validate_memory_deltas_payload,
    validate_persona_revision_payload,
    validate_plan_payload,
    validate_profile_payload,
    validate_synthesis_payload,
)


from ._common import *  # noqa: F401,F403  (shared helpers + constants)
from ._authoring import PRIMITIVES_CONTRACT  # noqa: E402


from ..methodology import (  # noqa: E402
    MethodologyError,
    list_methodologies,
    get_methodology,
    register_methodology,
)
from ..suggestions import (  # noqa: E402
    suggest_capabilities,
    suggest_roles,
    suggest_artifact_types,
    suggest_section_kinds,
    suggest_chart_kinds,
    suggest_methodologies,
    suggest_stances,
    suggest_finding_kinds,
    suggest_friction_levels,
    suggest_likelihood_levels,
    suggest_tech_comfort,
)
from .. import plan as _plan  # noqa: E402
from ..plan import (  # noqa: E402
    PlanError,
    new_plan,
    validate_plan,
    seed_plan_from_methodology,
    ready_tasks,
    is_complete,
    render_plan_md,
)
from .. import prototypes as _proto  # noqa: E402
from .. import browser as _browser   # noqa: E402



def start_project(title: str, goal: str, methodology: str | None = None,
                  persona_ids: list[str] | None = None, description: str = "",
                  store: Store | None = None, icon: Any | None = None) -> dict[str, Any]:
    """Unified project entry: create a research project + seed its plan. With a methodology the plan
    is seeded from the constellation (analyze/act/verify scaffolding); freeform seeds one root frame
    task (analyze, dischargeable). The plan is the single engine (HX3); a methodology only seeds it."""
    store = store or Store()
    project = create_research_project(title, goal=goal, persona_ids=persona_ids,
                                      description=description, store=store, icon=icon)
    if methodology:
        spec = get_methodology(methodology, store=store)
        project["methodology"] = methodology
        project["updated_at"] = utc_now_iso()
        store.upsert_research_project(project)
        plan = _plan.seed_plan_from_methodology(project["id"], goal, spec)
    else:
        root = {"id": "frame__root", "title": "Frame the inquiry", "bucket": "analyze",
                "capability": "frame", "consumes": [],
                "intent": "Understand before concluding: read persona memory + author the research "
                          "questions/hypotheses this inquiry needs before any council runs."}
        plan = _plan.new_plan(project["id"], goal, "", [root])
    _plan.save_plan(plan, store=store)
    out = {**store.get_research_project(project["id"]),
           "url": project.get("url") or ""}  # the where-to-look link from create_research_project
    emit_lifecycle_event("project.created", {"project_id": project["id"], "title": title,  # noqa: F821 (bound)
                                             "goal": goal, "methodology": methodology or ""}, store)
    # Cohort-depth pre-flight: warn BEFORE Discover, not after Define has gate-passed — a real run
    # produced an entire ungrounded Discover+Define over 0-memory personas before the thin-cohort
    # gap surfaced. Non-blocking (a thin cohort can be intentional); the warning rides the response.
    if persona_ids:
        try:
            d = cohort_memory_depth(persona_ids, store=store)
            if d["facts"] + d["events"] == 0:
                out = dict(out)
                out["warnings"] = [
                    f"cohort memory is EMPTY ({d['personas']} persona(s), 0 facts/events) — councils "
                    f"will be ungrounded; deepen with simulate-cohort (or ground personas from real "
                    f"material) before Discover"]
        except Exception:
            pass
    return out



def list_frameworks(store: Store | None = None) -> dict[str, Any]:
    """The plain-language description of every Framework — one clean, structured list the product,
    the website 'how it works' page and the job presets all draw from. Each entry is
    {id, name, what, when, stages:[{id, name, what}]}. Reads the live methodology specs joined with
    the canonical taxonomy (sonaloop/job_taxonomy.framework_descriptions)."""
    from ..job_taxonomy import framework_descriptions
    return {"frameworks": framework_descriptions(store)}


def describe_framework(framework_id: str, store: Store | None = None) -> dict[str, Any]:
    """One Framework's plain-language description by stable id (e.g. 'double_diamond'):
    {id, name, what, when, stages:[{id, name, what}]}. Raises if the id is unknown."""
    from ..job_taxonomy import get_framework_description
    return get_framework_description(framework_id, store)


# --- Job presets + the "sharpen the question" helper (the taxonomy's JOB layer; sonaloop/job_presets.py) ---

def list_job_presets(store: Store | None = None) -> dict[str, Any]:
    """One recipe card per taxonomy Job (positioning, pricing, …) — each seeds a plan: default
    Framework + suggested Formats (with their brief/record tools) + declared persona coverage.
    Derived from the canonical taxonomy at call time; never enforced."""
    from .. import job_presets as _presets
    return {"presets": _presets.job_presets(store)}


def get_job_preset(job_id: str, store: Store | None = None) -> dict[str, Any]:
    """One Job preset by stable taxonomy id. Raises KeyError for an unknown id."""
    from .. import job_presets as _presets
    return _presets.get_job_preset(job_id, store)


def sharpen_question(goal: str, answers: dict[str, str] | None = None, job: str | None = None,
                     store: Store | None = None) -> dict[str, Any]:
    """The deterministic "sharpen the question" helper: fuzzy goal → checklist + clarifying
    questions + likely Job-preset matches + a structured study spec (sonaloop/job_presets.py)."""
    from .. import job_presets as _presets
    return _presets.sharpen_question(goal, answers=answers, job=job, store=store)


def start_job_study(job_id: str, title: str, goal: str, framework: str | None = None,
                    persona_ids: list[str] | None = None, store: Store | None = None,
                    icon: Any | None = None) -> dict[str, Any]:
    """Start a study FROM a Job preset: seed the plan through the preset's default Framework
    (or any `framework` override — presets are swappable, never enforced) and stamp the Job id
    on the project + plan so downstream surfaces (assess_coverage, the inspector) know which
    declared coverage applies. Just a convenience over start_project — the general engine still
    runs anything off-menu."""
    store = store or Store()
    from .. import job_presets as _presets
    try:
        preset = _presets.get_job_preset(job_id, store=store)
    except KeyError as exc:
        raise ValueError(f"unknown job '{job_id}' — list_job_presets() names the valid ids") from exc
    fw = framework or preset["framework"]["id"]
    project = start_project(title, goal, methodology=fw, persona_ids=persona_ids, store=store,
                            icon=icon)
    project["job"] = job_id
    project["updated_at"] = utc_now_iso()
    store.upsert_research_project(project)
    plan = _plan.get_plan(project["id"], store=store)
    if plan:
        plan["job"] = job_id
        _plan.save_plan(plan, store=store)
    out = {"project": store.get_research_project(project["id"]), "preset": preset, "framework": fw,
           "suggested_formats": [f["id"] for f in preset["formats"]],
           "coverage": preset["coverage"]}
    if fw not in preset["framework_options"]:
        out["note"] = (f"Framework '{fw}' is off the preset's menu {preset['framework_options']} — "
                       "allowed; presets seed, never constrain.")
    return out


def get_plan(project_id: str, store: Store | None = None) -> dict[str, Any] | None:
    return _plan.get_plan(project_id, store=store)



def save_plan(plan: dict[str, Any], store: Store | None = None) -> dict[str, Any]:
    return _plan.save_plan(plan, store=store)



def add_task(project_id, bucket, capability, title, intent="", consumes=None, requires=None,
             step="", plan_note="", task_id=None, store: Store | None = None) -> dict[str, Any]:
    return _plan.add_task(project_id, bucket, capability, title, intent, consumes, requires,
                          step, plan_note, task_id, store=store)



def record_frame(project_id, task_id, questions, hypotheses=None, memory_refs=None,
                 store: Store | None = None) -> dict[str, Any]:
    return _plan.record_frame(project_id, task_id, questions, hypotheses, memory_refs, store=store)



def link_evidence(project_id, task_id, ref, store: Store | None = None) -> dict[str, Any]:
    return _plan.link_evidence(project_id, task_id, ref, store=store)



def complete_task(project_id, task_id, store: Store | None = None) -> dict[str, Any]:
    return _plan.complete_task(project_id, task_id, store=store)



def iterate_task(project_id, task_id, note="", store: Store | None = None) -> dict[str, Any]:
    return _plan.iterate_task(project_id, task_id, note, store=store)



def assess_progress(project_id, task_id, rationale, evidence_refs, delta="",
                    store: Store | None = None) -> dict[str, Any]:
    return _plan.assess_progress(project_id, task_id, rationale, evidence_refs, delta, store=store)





def assess_project(project_id, store: Store | None = None) -> dict[str, Any]:
    return _plan.assess_project(project_id, store=store)


def project_run_state(project_id, store: Store | None = None) -> dict[str, Any] | None:
    return _plan.project_run_state(project_id, store=store)


def next_action(project_id, store: Store | None = None) -> dict[str, Any]:
    return _plan.next_action(project_id, store=store)


# start_methodology_project RETIRED — use start_project(methodology=<key>) (the canonical entry).



def set_project_methodology(project_id: str, methodology_key: str,
                            store: Store | None = None) -> dict[str, Any]:
    """Bind an existing research project to a methodology by (re)seeding its plan from the
    constellation (the plan is the single engine; HX3)."""
    store = store or Store()
    project = store.get_research_project(project_id)
    if not project:
        raise MethodologyError("UNKNOWN_PROJECT", f"Unknown research project: {project_id}")
    spec = get_methodology(methodology_key, store=store)
    project["methodology"] = methodology_key
    project["updated_at"] = utc_now_iso()
    store.upsert_research_project(project)
    plan = _plan.seed_plan_from_methodology(project_id, project.get("goal", ""), spec)
    _plan.save_plan(plan, store=store)
    return store.get_research_project(project_id)



# brief_next + record_judgment: thin forwards to the plan engine (the project's single engine; HX3).



def brief_next(project_id: str, store: Store | None = None) -> dict[str, Any]:
    return _plan.brief_next(project_id, store=store)



def record_judgment(project_id, task_id, gate_tag, decided, rationale,
                    evidence_refs=None, store: Store | None = None) -> dict[str, Any]:
    return _plan.record_judgment(project_id, task_id, gate_tag, decided, rationale,
                                 evidence_refs, store=store)


def park_evidence(project_id: str, refs: list[Any], reason: str, task_id: str = "",
                  store: Store | None = None) -> dict[str, Any]:
    return _plan.park_evidence(project_id, refs, reason, task_id, store=store)



def export_plan_md(project_id: str, store: Store | None = None) -> str:
    store = store or Store()
    p = _plan.get_plan(project_id, store=store)
    if not p:
        raise PlanError("NO_PLAN", f"project {project_id} has no plan")
    md = _plan.render_plan_md(p)
    # The decisions taken on this research (with citations) close the plan document — what the
    # work led to, on which evidence, rejecting what (ticket decision-record-artifact).
    dec = decisions_section_md(project_id, store=store)  # noqa: F821 (bound)
    return md + ("\n" + dec if dec else "")


# --- Prototypes + Playwright harness seam (spec §6/§7) -------------------------
from .. import prototypes as _proto  # noqa: E402
from .. import browser as _browser   # noqa: E402



def scaffold_artifact(slug, name, concept, type="prototype", tags=None, template=None,
                      project_id=None, store: Store | None = None):
    return _proto.scaffold_artifact(slug, name, concept, type=type, tags=tags, template=template,
                                    project_id=project_id, store=store)



def scaffold_prototype(slug, name, concept, kind="web", template=None,
                       project_id=None, fidelity=None, store: Store | None = None):
    return _proto.scaffold_prototype(slug, name, concept, kind, template, project_id, fidelity=fidelity, store=store)



def register_prototype(slug, name, path, entry="index.html", run="static", run_cmd=None,
                       version="v0.1", project_id=None, notes="", fidelity="", created_at=None,
                       store: Store | None = None):
    return _proto.register_prototype(slug, name, path, entry, run, run_cmd, version, project_id, notes,
                                     fidelity=fidelity, created_at=created_at, store=store)



def list_prototypes_artifacts(project_id=None, store: Store | None = None):
    return _proto.list_prototypes(project_id, store=store)



def get_prototype_artifact(prototype_id, store: Store | None = None):
    return _proto.get_prototype(prototype_id, store=store)


def refresh_prototype_design_system(prototype_id, store: Store | None = None):
    return _proto.refresh_prototype_design_system(prototype_id, store=store)



def run_prototype(prototype_id, store: Store | None = None):
    return _proto.run_prototype(prototype_id, store=store)



def stop_prototype(prototype_id, store: Store | None = None):
    return _proto.stop_prototype(prototype_id, store=store)



def delete_prototype_artifact(prototype_id, store: Store | None = None):
    return _proto.delete_prototype(prototype_id, store=store)



def proto_open(prototype_id=None, url=None, persona_id=None, store: Store | None = None):
    store = store or Store()
    if prototype_id and not url:
        url = _proto.run_prototype(prototype_id, store=store)["url"]
    if not url:
        raise ValueError("proto_open needs a prototype_id or a url")
    return _browser.open_session(url, prototype_id, persona_id)



def proto_act(session_id, action, store: Store | None = None):
    return _browser.act(session_id, action)



def proto_read(session_id, store: Store | None = None):
    return _browser.read(session_id)



def proto_close(session_id, store: Store | None = None):
    return _browser.close(session_id)



def proto_drive(prototype_id=None, url=None, persona_id=None, actions=None,
                reaction=None, date_value=None, store: Store | None = None):
    """A complete proband session in ONE process: open → scripted actions → read → close —
    and, when `reaction` is given, record_prototype_session against the still-warm log.
    This exists because browser sessions (and their retained logs) live in process memory:
    stateless CLI invocations can never act on / verify a session another process opened."""
    store = store or Store()
    opened = proto_open(prototype_id, url, persona_id, store=store)
    sid = opened["session_id"]
    steps = []
    try:
        for a in (actions or []):
            steps.append(proto_act(sid, a, store=store))
        final = proto_read(sid, store=store)
    finally:
        proto_close(sid, store=store)
    out = {"session_id": sid, "opened": opened.get("snapshot"), "steps": steps,
           "final": final.get("snapshot")}
    if reaction is not None:
        rec = record_prototype_session(persona_id, prototype_id, sid,
                                       date_value or date.today().isoformat(), reaction, store=store)
        out["recorded"] = {"id": rec["prototype_session"]["id"],
                           "grounded_verified": rec.get("grounded_verified")}
    else:
        out["note"] = ("groundedness: the session log lives in THIS process — record the reaction in "
                       "the same proto_drive call (reaction=…) or this same process; a later "
                       "session-record from a fresh CLI process records UNVERIFIED")
    return out



def list_proto_sessions(store: Store | None = None):
    return _browser.list_sessions()



def brief_prototype_session(persona_id, prototype_id, store: Store | None = None):
    store = store or Store()
    proto = _proto.get_prototype(prototype_id, store=store)
    persona = _require_persona(store, persona_id)
    profile = capability_profile(persona)   # declared, else derived heuristic (capability ticket)
    ctx = prepare_persona_agent_context(
        persona_id, task=f"Use the prototype '{proto['name']}' as you really would and report what you experienced",
        recent_events=8, store=store)
    screens = []
    try:
        import json as _json
        cpath = _proto._prototype_app_dir(proto) / "concept.json"
        if cpath.exists():
            screens = [{"id": s["id"], "title": s.get("title", s["id"])}
                       for s in _json.loads(cpath.read_text(encoding="utf-8")).get("screens", [])]
    except Exception:
        pass
    brief = {
        "schema": "prototype_session", "persona_id": persona_id,
        "prototype": {"id": proto["id"], "name": proto["name"], "slug": proto["slug"], "screens": screens},
        "agent_context": ctx.get("agent_context"),
        "capabilities": profile,
        "instructions": ("Open the running app (proto_open), drive it like THIS persona "
                         "(proto_act click/type/select on refs from the latest snapshot), observe the REAL "
                         "state, then author a grounded reaction. Anti-steering: only praise what you actually "
                         "exercised; honest friction and rejection are first-class. Cite the states you saw in "
                         "observed_state_refs.") + capability_context_line(profile) + PRIMITIVES_CONTRACT,
    }
    gate = capability_fidelity_warnings(profile, "prototype", proto["name"])  # warn, never block
    if gate:
        brief["warnings"] = gate
    return brief



def record_prototype_session(persona_id, prototype_id, session_id, date_value, reaction,
                             key: str | None = None, store: Store | None = None):
    store = store or Store()
    proto = _proto.get_prototype(prototype_id, store=store)
    refs = [str(r).strip() for r in (reaction.get("observed_state_refs") or []) if str(r).strip()]
    if not refs:
        raise ValueError("reaction.observed_state_refs must cite >= 1 observed state (a ref or text actually seen)")
    log = _browser.session_log(session_id)
    grounded = True
    if log:
        seen_refs: set[str] = set()
        seen_text = ""
        for entry in log:
            if entry.get("kind") == "snapshot":
                seen_refs.update(entry.get("refs", []))
                seen_text += " " + (entry.get("text") or "")
        unmatched = [r for r in refs if r not in seen_refs and r.lower() not in seen_text.lower()]
        if unmatched:
            raise ValueError(f"prototype-reaction groundedness: observed_state_refs not present in the session log: {unmatched}")
    else:
        grounded = False  # session closed / harness unavailable — record but mark unverified
    now = utc_now_iso()
    from .. import artifacts as _A
    statements = [_A.validate_statement(s) for s in (reaction.get("statements") or [])]
    sess = PrototypeSession(
        id=(stable_id("protosession", key) if key else stable_id("protosession", persona_id, prototype_id, now)),
        persona_id=persona_id,
        prototype_id=proto["id"], session_id=session_id, date=date_value, reaction=reaction,
        observed_state_refs=refs, created_at=now, statements=statements).to_dict()
    sess["grounded_verified"] = grounded
    # A prototype can be updated after this run. Stamp the version observed NOW so later critics do
    # not accidentally attribute historical reactions to whatever version happens to be current.
    sess["prototype_version"] = str(proto.get("version") or "unknown")
    store.insert_prototype_session(sess)
    # write the real use into persona memory so the test council surfaces it
    name = proto["name"]
    facts = []
    for h in (reaction.get("liked") or [])[:4]:
        facts.append({"entity": name, "fact": str(h), "status": "positiv", "valid_from": date_value, "importance": 4})
    for h in (reaction.get("friction") or [])[:4]:
        facts.append({"entity": name, "fact": str(h), "status": "offen", "valid_from": date_value, "importance": 4})
    if reaction.get("verdict"):
        facts.append({"entity": name, "fact": "Verdict: " + str(reaction["verdict"]), "status": "neutral",
                      "valid_from": date_value, "importance": 3})
    deltas = {
        "entities": [{"mention": name, "kind": "topic", "status": "ausprobiert", "aliases": [proto["slug"]]}],
        "facts": facts or [{"entity": name, "fact": str(reaction.get("summary", "Prototype tried")),
                            "status": "neutral", "valid_from": date_value, "importance": 3}],
        "threads": [], "event_links": [],
    }
    try:
        record_memory_deltas(persona_id, date_value, deltas, store=store)
        memory_written = True
    except Exception:
        memory_written = False
    out = {"prototype_session": sess, "grounded_verified": grounded, "memory_written": memory_written}
    if not grounded:
        # GAP-5: an unverified session is soft evidence — make it visible (and the gate now requires a
        # GROUNDED session when the harness can verify), instead of silently passing as "real usage".
        msg = ("UNVERIFIED_SESSION: no observed-state log for this session_id, so the reaction is NOT "
               "verified against real usage.")
        if _browser.available():
            msg += (" Playwright IS available here — open the prototype (proto_open/proto_act/proto_read) "
                    "and record from the SAME session_id; the log is now retained across proto_close, so a "
                    "real drive will verify. An unverified session does NOT satisfy a session_of_tags gate.")
        out["warnings"] = [msg]
    return out


# ===================== ESV §A.2 — the resumable run object (driver journal) =====================

def run_key(run_id: str, task_id: str, angle: str = "") -> str:
    """The deterministic key every per-step write carries so a re-run is an idempotent upsert."""
    return f"{run_id}:{task_id}:{angle}" if angle else f"{run_id}:{task_id}"


def start_run(project_id: str, budget: int | None = None, run_id: str | None = None,
              store: Store | None = None) -> dict[str, Any]:
    """Create (or load) the run object for a project — the resumable journal the driver advances. If
    `run_id` already exists, it is returned as-is (resume)."""
    store = store or Store()
    if not store.get_research_project(project_id):
        raise PlanError("UNKNOWN_PROJECT", f"unknown research project: {project_id}")
    if run_id:
        existing = store.get_run(run_id)
        if existing:
            return existing
    now = utc_now_iso()
    plan = _plan.get_plan(project_id, store=store) or {}
    run = {"run_id": run_id or stable_id("run", project_id, now), "project_id": project_id,
           "methodology": plan.get("methodology", ""), "status": "active",
           "budget": int(budget) if budget is not None else None, "cursor": 0,
           "steps": [], "critic_rounds": [], "created_at": now, "updated_at": now}
    store.upsert_run(run)
    return run


def run_journal(run_id: str, store: Store | None = None) -> dict[str, Any]:
    """The run's journal (steps + critic rounds + cursor + status) — the single source of truth for
    resume. Lean: ids + 1-line summaries only, never authored text."""
    store = store or Store()
    r = store.get_run(run_id)
    if not r:
        raise PlanError("UNKNOWN_RUN", f"unknown run: {run_id}")
    return r


_RUN_STEP_TRACE_LIST_FIELDS = (
    "consume_refs",
    "optional_context_refs",
    "produced_refs",
    "downstream_refs",
    "open_questions",
    "parked_refs",
)


def _trace_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def checkpoint_step(run_id: str, step: dict[str, Any], store: Store | None = None) -> dict[str, Any]:
    """Append a completed step to the journal (ids + a 1-line summary). Returns the new cursor.

    The original `evidence` field stays for old callers. The explicit trace fields let autonomous
    authors record the I/O contract they actually fulfilled, so later UI/assessment can distinguish
    "new evidence not consumed yet" from "forgotten evidence".
    """
    store = store or Store()
    r = store.get_run(run_id)
    if not r:
        raise PlanError("UNKNOWN_RUN", f"unknown run: {run_id}")
    entry = {"idx": len(r["steps"]), "task_id": step.get("task_id", ""), "bucket": step.get("bucket", ""),
             "key": step.get("key", ""), "evidence": step.get("evidence", []),
             "summary": str(step.get("summary", ""))[:300]}
    for field in _RUN_STEP_TRACE_LIST_FIELDS:
        entry[field] = _trace_list(step.get(field))
    if not entry["produced_refs"] and step.get("evidence"):
        entry["produced_refs"] = _trace_list(step.get("evidence"))
    if "expected_output_kind" in step:
        entry["expected_output_kind"] = str(step.get("expected_output_kind") or "")
    r["steps"].append(entry)
    r["cursor"] = len(r["steps"])
    r["updated_at"] = utc_now_iso()
    store.upsert_run(r)
    return {"cursor": r["cursor"], "run_id": run_id}


def record_critic_round(run_id: str, passed: bool, missing_count: int, store: Store | None = None) -> dict[str, Any]:
    """Log one completeness-critic round on the run (for the loop-until-dry gate + observability)."""
    store = store or Store()
    r = store.get_run(run_id)
    if not r:
        raise PlanError("UNKNOWN_RUN", f"unknown run: {run_id}")
    r.setdefault("critic_rounds", []).append({"round": len(r.get("critic_rounds", [])),
                                              "passed": bool(passed), "missing": int(missing_count)})
    r["updated_at"] = utc_now_iso()
    store.upsert_run(r)
    return {"round": len(r["critic_rounds"]) - 1, "passed": bool(passed)}


def finish_run(run_id: str, status: str = "finished", store: Store | None = None) -> dict[str, Any]:
    """Mark the run finished/stopped."""
    store = store or Store()
    r = store.get_run(run_id)
    if not r:
        raise PlanError("UNKNOWN_RUN", f"unknown run: {run_id}")
    r["status"] = status
    r["updated_at"] = utc_now_iso()
    store.upsert_run(r)
    emit_lifecycle_event("run.finished", {"run_id": run_id, "project_id": r["project_id"],  # noqa: F821 (bound)
                                          "status": status, "steps": len(r["steps"])}, store)
    return {"run_id": run_id, "status": status, "steps": len(r["steps"])}


# ===================== ESV §A.3 — the deterministic RunLoop engine (the keystone) =====================
# A pure, deterministic brain (NO LLM, NO spawning): the host skill loops `run_step(run_id)` →
# spawns ONE subagent per returned dispatch (the SAME Agent-tool primitive used today) → records the
# result → repeat. run_step bundles assess_project + next_action + the deterministic finish work +
# the loop-until-dry critic gate, so the agent can't drift or stop early, and a killed run resumes from
# the live plan state. K=2 dry critic rounds to pass; hard cap of 4 rounds (OD-5).
_RUN_K_DRY = 2
_RUN_MAX_CRITIC = 4


def _rl_trailing_dry(rounds: list[dict[str, Any]]) -> int:
    n = 0
    for r in reversed(rounds):
        if r.get("passed"):
            n += 1
        else:
            break
    return n


def _rl_frame(plan: dict[str, Any], hint: str = "") -> str | None:
    frames = [t for t in plan["tasks"] if t.get("capability") == "frame"]
    if hint:
        m = [t for t in frames if hint in t["id"] or hint in (t.get("step", "") or "")]
        if m:
            return m[-1]["id"]
    return frames[0]["id"] if frames else None


def inject_work(project_id: str, missing: dict[str, Any], store: Store | None = None) -> bool:
    """Turn one critic `missing` item into REAL plan work (deterministic, open tags). segment/angle →
    an act council under the discover frame; concept/fidelity_rung → an act build under the ideate
    frame; risk → an open question; anything else → an open question so it stays visible."""
    store = store or Store()
    plan = _plan.get_plan(project_id, store=store) or {"tasks": []}
    kind = str(missing.get("kind", "")).lower()
    what = str(missing.get("what", "more work")).strip()[:120] or "more work"
    if kind in ("concept", "fidelity_rung"):
        frame = _rl_frame(plan, "ideate") or _rl_frame(plan)
        if frame:
            add_task(project_id, "act", "build", f"[critic] {what}", consumes=[frame], store=store)
            return True
    if kind in ("segment", "angle"):
        frame = _rl_frame(plan, "discover") or _rl_frame(plan)
        if frame:
            add_task(project_id, "act", "explore", f"[critic] {what}", consumes=[frame], store=store)
            return True
    record_open_questions(project_id, [f"[{kind or 'gap'}] {what}"], store=store)  # noqa: F821 (bound)
    return True


def _rl_inject_pending(project_id: str, run: dict[str, Any], store: Store) -> int:
    """If the latest critic round was NOT passed and its gaps haven't been injected, inject them."""
    rounds = run.get("critic_rounds", [])
    if not rounds or run.get("injected_for", 0) >= len(rounds):
        return 0
    if rounds[-1].get("passed"):
        run["injected_for"] = len(rounds); store.upsert_run(run); return 0
    reports = (store.get_research_project(project_id) or {}).get("critic_reports", [])
    missing = reports[-1].get("missing", []) if reports else []
    cnt = sum(1 for m in missing if inject_work(project_id, m, store=store))
    run["injected_for"] = len(rounds); run["updated_at"] = utc_now_iso(); store.upsert_run(run)
    return cnt


def _rl_summary(project_id: str, store: Store) -> dict[str, Any]:
    g = get_project_graph(project_id, store=store)  # noqa: F821 (bound)
    sessions = [x for x in store.list_prototype_sessions()
                if (store.get_prototype(x.get("prototype_id", "")) or {}).get("project_id") == project_id]
    return {"councils": sum(1 for n in g["nodes"] if str(n["study_id"]).startswith("council:")),
            "syntheses": sum(1 for n in g["nodes"] if str(n["study_id"]).startswith("synthesis:")),
            "prototypes": len(g.get("prototypes") or []), "sections": len(g.get("sections") or []),
            "grounded_sessions": sum(1 for x in sessions if x.get("grounded_verified")),
            "total_sessions": len(sessions)}


def _ref_token(ref: dict[str, Any]) -> str:
    kind, rid = str((ref or {}).get("kind", "")), str((ref or {}).get("id", ""))
    return f"{kind}:{rid}" if kind and rid else rid


def _rl_trace_contract(project_id: str, task_id: str, store: Store) -> dict[str, Any]:
    plan = _plan.get_plan(project_id, store=store) or {}
    tasks = {str(t.get("id")): t for t in plan.get("tasks") or []}
    t = tasks.get(task_id) or {}
    consumes = [str(c) for c in (t.get("consumes") or [])]
    consume_refs: list[str] = []
    optional_context_refs: list[str] = []
    open_questions: list[str] = []
    for cid in consumes:
        ct = tasks.get(cid) or {}
        if ct.get("frame"):
            consume_refs.append(f"frame:{cid}")
            optional_context_refs.extend(str(r) for r in (ct["frame"].get("memory_refs") or []) if str(r).strip())
            open_questions.extend(str(q) for q in (ct["frame"].get("questions") or []) if str(q).strip())
        else:
            consume_refs.extend(_ref_token(r) for r in (ct.get("produces") or []) if _ref_token(r))
    expected = "frame" if t.get("bucket") == "analyze" else str(t.get("capability") or t.get("bucket") or "")
    return {"consume_task_ids": consumes, "consume_refs": consume_refs,
            "optional_context_refs": optional_context_refs, "open_questions": open_questions,
            "expected_output_kind": expected,
            "must_link_before_complete": t.get("bucket") in ("act", "verify")}


def _rl_dispatch(run: dict[str, Any], n: dict[str, Any], store: Store) -> dict[str, Any]:
    trace = _rl_trace_contract(run["project_id"], n["task"], store)
    return {"kind": n["bucket"], "step_id": n["task"], "key": run_key(run["run_id"], n["task"]),
            "next_action": n, "directive": n.get("instructions", ""), **trace}


def run_step(run_id: str, store: Store | None = None) -> dict[str, Any]:
    """The deterministic brain. Returns the next dispatch for the host to execute:
    {kind: analyze|act|verify, step_id, key, next_action, directive} → spawn ONE authoring subagent
    then checkpoint_step; {kind: critic, brief} → spawn an INDEPENDENT critic then record_critic_round;
    {kind: done, status, summary} → stop. Deterministic finish work (organize + report outline +
    critic-gap injection) is done inline. Idempotent / resumable: it reads the live plan state."""
    store = store or Store()
    run = store.get_run(run_id)
    if not run:
        raise PlanError("UNKNOWN_RUN", f"unknown run: {run_id}")
    pid = run["project_id"]
    budget = run.get("budget")
    if budget is not None and len(run.get("steps", [])) >= budget:
        derive_sections(pid, store=store); scaffold_synthesis(pid, store=store)  # noqa: F821 (bound)
        finish_run(run_id, "capped", store=store)
        return {"kind": "done", "status": "capped", "summary": _rl_summary(pid, store)}
    _rl_inject_pending(pid, run, store)
    a = assess_project(pid, store=store)
    rec = a["recommendation"]
    if rec in ("frame", "act", "converge"):
        n = next_action(pid, store=store)
        if not n.get("complete"):
            return _rl_dispatch(run, n, store)
    if rec == "finish" or (a["complete"] and not a["finish"]["finished"]):
        if not a["finish"].get("organized"):
            derive_sections(pid, store=store)              # noqa: F821 (bound)
        if not a["finish"].get("handed_off"):
            scaffold_synthesis(pid, store=store)          # noqa: F821 (bound)
        a = assess_project(pid, store=store)
        if not a["finish"].get("concluded"):
            terminal = next((t["id"] for t in reversed((_plan.get_plan(pid, store=store) or {}).get("tasks", []))
                             if t["bucket"] == "verify"), None)
            return {"kind": "verify", "step_id": "__conclusion__", "key": run_key(run_id, "conclusion"),
                    "terminal_verify": terminal,
                    "directive": ("Author a RICH terminal solution-presentation synthesis (record_synthesis: "
                                  "gesamtbild + positionierung + pain_solvers + ranking/shortlist; the answer, "
                                  "who-wins + deliberate non-targets, validated solvers, build spec) and "
                                  f"link_evidence it to the terminal verify task `{terminal}`.")}
    if a["complete"] and a["finish"]["finished"]:
        rounds = run.get("critic_rounds", [])
        if _rl_trailing_dry(rounds) >= _RUN_K_DRY:
            finish_run(run_id, "finished", store=store)
            return {"kind": "done", "status": "finished", "summary": _rl_summary(pid, store)}
        if len(rounds) >= _RUN_MAX_CRITIC:
            finish_run(run_id, "capped", store=store)
            return {"kind": "done", "status": "capped", "summary": _rl_summary(pid, store)}
        return {"kind": "critic", "run_id": run_id, "brief": brief_completeness_critic(pid, store=store),  # noqa: F821
                "directive": ("Spawn an INDEPENDENT critic subagent: author the verdict from the brief, call "
                              "record_completeness_critic(project_id, verdict) then record_critic_round.")}
    finish_run(run_id, "stopped", store=store)
    return {"kind": "done", "status": "stopped", "summary": _rl_summary(pid, store)}


# ===================== ESV §D.2/D.3 — memory depth + the eval (quality) harness =====================

def cohort_memory_depth(persona_ids: list[str] | None = None, store: Store | None = None) -> dict[str, Any]:
    """How deep is the cohort's simulated memory? (avg facts+events per persona). Councils are only as
    deep as the lives behind them — a thin cohort should be deepened (simulate-cohort) before a run."""
    store = store or Store()
    pids = persona_ids or [p["id"] for p in store.list_personas()]
    m = store.count_memory_for_personas(pids)
    avg = (m["facts"] + m["events"]) / max(1, len(pids))
    return {"personas": len(pids), "facts": m["facts"], "events": m["events"], "avg_per_persona": round(avg, 1),
            "hint": "deep" if avg >= 6 else "thin — deepen the cohort (simulate-cohort) for richer councils"}


def score_run(project_id: str, store: Store | None = None) -> dict[str, Any]:
    """Persist a RunScore snapshot of a finished project's quality (the last critic's rubric scores +
    finish + novelty + groundedness + memory depth), so output quality is TRACKED over time (a
    regression signal for the methodology itself, not just the code) — ESV §D.3."""
    store = store or Store()
    project = store.get_research_project(project_id)
    if not project:
        raise PlanError("UNKNOWN_PROJECT", f"unknown research project: {project_id}")
    a = assess_project(project_id, store=store)
    critics = project.get("critic_reports", [])
    last_critic = critics[-1] if critics else {}
    g = get_project_graph(project_id, store=store)            # noqa: F821 (bound)
    sessions = [x for x in store.list_prototype_sessions()
                if (store.get_prototype(x.get("prototype_id", "")) or {}).get("project_id") == project_id]
    now = utc_now_iso()
    score = {"id": stable_id("runscore", project_id, now), "project_id": project_id, "created_at": now,
             "complete": a.get("complete"), "finish": a.get("finish", {}), "novelty": a.get("novelty", {}),
             "memory_depth": a.get("memory_depth", {}),
             "critic_passed": bool(last_critic.get("passed")), "critic_scores": last_critic.get("scores", {}),
             "coverage": {"councils": sum(1 for n in g["nodes"] if str(n["study_id"]).startswith("council:")),
                          "syntheses": sum(1 for n in g["nodes"] if str(n["study_id"]).startswith("synthesis:")),
                          "prototypes": len(g.get("prototypes") or []), "sections": len(g.get("sections") or [])},
             "groundedness": {"sessions": len(sessions),
                              "grounded": sum(1 for x in sessions if x.get("grounded_verified"))}}
    project.setdefault("run_scores", []).append(score)
    project["updated_at"] = now
    store.upsert_research_project(project)
    return score
