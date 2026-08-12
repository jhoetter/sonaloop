"""Methodology-engine seam + research-plan-engine seam + prototypes/Playwright seam.

Split out of the original sonaloop/services.py (behavior-preserving).
Cross-module function references are bound at import time by services/__init__.py."""

from __future__ import annotations

import csv
import copy
import hashlib
import json
import random
import re
import uuid
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

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
from .._project_locks import project_lifecycle_locks
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
from ._authoring import PERSONA_VOICE_CONTRACT, PRIMITIVES_CONTRACT  # noqa: E402


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
from .. import plan_evidence as _plan_evidence  # noqa: E402
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
from .. import remote_prototypes as _remote_proto  # noqa: E402
from .. import browser as _browser   # noqa: E402


def _start_project_operation_id(value: str | None) -> str | None:
    if value is None:
        return None
    operation_id = str(value).strip()
    if not operation_id:
        raise ValueError("operation_id must be 1..200 printable characters")
    if len(operation_id) > 200 or not operation_id.isprintable():
        raise ValueError("operation_id must be 1..200 printable characters")
    return operation_id


def _start_project_fingerprint(title: str, goal: str, methodology: str,
                               persona_ids: list[str] | None, description: str,
                               icon: Any | None) -> str:
    canonical = json.dumps({
        "title": title,
        "goal": goal,
        "methodology": methodology,
        "persona_ids": list(persona_ids or []),
        "description": description,
        "icon": icon,
    }, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _start_project_cohort_warning(project: dict[str, Any], store: Store) -> dict[str, Any]:
    """Attach the non-persisted thin-cohort warning to creates and idempotent replays alike."""
    persona_ids = project.get("persona_ids") or []
    if not persona_ids:
        return project
    try:
        d = cohort_memory_depth(persona_ids, store=store)
        if d["facts"] + d["events"] == 0:
            project = dict(project)
            project["warnings"] = [
                f"cohort memory is EMPTY ({d['personas']} persona(s), 0 facts/events) — councils "
                f"will be ungrounded; deepen with simulate-cohort (or ground personas from real "
                f"material) before Discover"
            ]
    except Exception:
        pass
    return project



def start_project(title: str, goal: str, methodology: str | None = None,
                  persona_ids: list[str] | None = None, description: str = "",
                  store: Store | None = None, icon: Any | None = None,
                  operation_id: str | None = None) -> dict[str, Any]:
    """Unified project entry: create a research project + seed its plan. With a methodology the plan
    is seeded from the constellation (analyze/act/verify scaffolding); freeform seeds one root frame
    task (analyze, dischargeable). The plan is the single engine (HX3); a methodology only seeds it.

    ``operation_id`` makes creation retry-safe: replaying the same operation returns the original
    project, while reusing the key for different inputs fails closed. Methodology names/aliases are
    resolved and validated before the first project or plan write.
    """
    store = store or Store()
    spec = None
    canonical_methodology = ""
    if methodology and str(methodology).strip():
        # Resolve BEFORE create_research_project: an unknown methodology must leave no
        # orphan project/root plan behind.
        spec = get_methodology(str(methodology), store=store)
        canonical_methodology = str(spec["key"])

    operation_id = _start_project_operation_id(operation_id)
    fingerprint = _start_project_fingerprint(
        title, goal, canonical_methodology, persona_ids, description, icon)
    project_id = stable_id("rproject_operation", operation_id) if operation_id else None
    replaying = False
    if project_id:
        existing = store.get_research_project(project_id)
        if existing:
            if str(existing.get("operation_id") or "") != operation_id:
                raise PlanError(
                    "IDEMPOTENCY_CONFLICT",
                    "IDEMPOTENCY_CONFLICT: operation_id resolved to an existing project owned by "
                    "another operation",
                )
            previous = str(existing.get("operation_fingerprint") or "")
            if previous and previous != fingerprint:
                raise PlanError(
                    "IDEMPOTENCY_CONFLICT",
                    "IDEMPOTENCY_CONFLICT: operation_id was already used with different "
                    "start_project inputs",
                )
            plan = _plan.get_plan(existing["id"], store=store)
            # Once initialized, this create operation owns an identity, not the
            # project's future mutable state. A late transport replay must return
            # the live project and must never roll back a later intentional
            # set_project_methodology call or its progressed plan.
            fully_initialized = existing.get("operation_state") == "initialized" and bool(plan)
            if fully_initialized:
                from ._common import web_url
                replay = {**existing, "url": web_url(f"/jobs/{existing['id']}"),
                          "idempotent_replay": True}
                return _start_project_cohort_warning(replay, store)
            # A process may have died after the project row but before plan initialization.
            # Resume that same deterministic project instead of returning a half-created shell.
            from ._common import web_url
            project = {**existing, "url": web_url(f"/jobs/{existing['id']}")}
            replaying = True
        else:
            project = create_research_project(
                title, goal=goal, persona_ids=persona_ids, description=description, store=store,
                icon=icon, project_id=project_id, operation_id=operation_id,
                operation_fingerprint=fingerprint)
    else:
        project = create_research_project(
            title, goal=goal, persona_ids=persona_ids, description=description, store=store,
            icon=icon)
    operation_claimed = project.pop("_operation_claimed", None)
    if project_id and operation_claimed is False:
        # Another worker won the atomic deterministic-id claim between our first read and insert.
        # Compare before any plan/project update; different payloads are never allowed to repair.
        if (str(project.get("operation_id") or "") != operation_id
                or str(project.get("operation_fingerprint") or "") != fingerprint):
            raise PlanError(
                "IDEMPOTENCY_CONFLICT",
                "IDEMPOTENCY_CONFLICT: operation_id was concurrently used with different "
                "start_project inputs",
            )
        replaying = True
    if spec:
        project["methodology"] = canonical_methodology
        if spec.get("integrity"):
            project["integrity"] = dict(spec["integrity"])
        if operation_id:
            # New retry-safe front-door projects opt into the dispatch-token
            # write contract. Projects created before this field remain readable
            # and follow the documented legacy path.
            project["governance_contract"] = "dispatch_v1"
        project["updated_at"] = utc_now_iso()
        store.upsert_research_project(project)
        plan = _plan.seed_plan_from_methodology(project["id"], goal, spec)
    else:
        if operation_id:
            project["governance_contract"] = "dispatch_v1"
            project["updated_at"] = utc_now_iso()
            store.upsert_research_project(project)
        root = {"id": "frame__root", "title": "Frame the inquiry", "bucket": "analyze",
                "capability": "frame", "consumes": [],
                "intent": "Understand before concluding: read persona memory + author the research "
                          "questions/hypotheses this inquiry needs before any council runs."}
        plan = _plan.new_plan(project["id"], goal, "", [root])
    _plan.save_plan(plan, store=store)
    if operation_id:
        project["operation_state"] = "initialized"
        project["updated_at"] = utc_now_iso()
        store.upsert_research_project(project)
    out = {**store.get_research_project(project["id"]),
           "url": project.get("url") or ""}  # the where-to-look link from create_research_project
    if replaying:
        out["idempotent_replay"] = True
    if not replaying:
        emit_lifecycle_event("project.created", {"project_id": project["id"], "title": title,  # noqa: F821 (bound)
                                                 "goal": goal, "methodology": canonical_methodology}, store)
        from ..telemetry import capture_product_event
        capture_product_event(
            "job_created",
            project_id=project["id"],
            subject_kind="job",
            subject_id=project["id"],
            properties={
                "methodology": canonical_methodology or "freeform",
                "persona_count": len(persona_ids or []),
            },
            idempotency_key=operation_id or project["id"],
        )
    # Cohort-depth pre-flight: warn BEFORE Discover, not after Define has gate-passed — a real run
    # produced an entire ungrounded Discover+Define over 0-memory personas before the thin-cohort
    # gap surfaced. Non-blocking (a thin cohort can be intentional); the warning rides the response.
    return _start_project_cohort_warning(out, store)



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
                 store: Store | None = None, dispatch_token: str | None = None) -> dict[str, Any]:
    store = store or Store()
    ctx = prepare_dispatch_write(project_id, dispatch_token, None, "frame", store,
                                 allowed_buckets={"analyze"}, required_task_id=task_id)
    # A transport may die after record_frame committed the plan but before the
    # checkpoint was appended.  Replaying the issued token must repair that
    # seam, not fail TASK_NOT_READY or silently change the authored frame.
    plan = _plan.get_plan(project_id, store=store) or {}
    current = next((t for t in plan.get("tasks") or []
                    if str(t.get("id") or "") == str(task_id)), None)
    authored = {
        "questions": [str(q).strip() for q in (questions or []) if str(q).strip()],
        "hypotheses": [str(h).strip() for h in (hypotheses or []) if str(h).strip()],
        "memory_refs": [str(r).strip() for r in (memory_refs or []) if str(r).strip()],
    }
    if ctx.get("dispatch_token") and current and current.get("status") == "done" and current.get("frame"):
        if current.get("frame") != authored:
            raise PlanError(
                "DISPATCH_OUTPUT_CONFLICT",
                "the frame dispatch was already committed with different authored content",
            )
        out = current
    else:
        out = _plan.record_frame(project_id, task_id, questions, hypotheses, memory_refs, store=store)
    dispatch = bind_dispatch_output(
        ctx, {"kind": "frame", "id": task_id}, "recorded evidence-grounded research frame", store)
    if dispatch:
        out = {**out, "dispatch": dispatch}
    return out



def link_evidence(project_id, task_id, ref, store: Store | None = None,
                  dispatch_token: str | None = None) -> dict[str, Any]:
    store = store or Store()
    prepare_dispatch_write(project_id, dispatch_token, None, str((ref or {}).get("kind") or "evidence"),
                           store, required_task_id=task_id)
    return _plan.link_evidence(project_id, task_id, ref, store=store)



def complete_task(project_id, task_id, store: Store | None = None,
                  dispatch_token: str | None = None) -> dict[str, Any]:
    store = store or Store()
    ctx = prepare_dispatch_write(project_id, dispatch_token, None, "task_completion", store,
                                 required_task_id=task_id)
    if ctx.get("dispatch_token"):
        plan = _plan.get_plan(project_id, store=store) or {}
        governed_task = next(
            (row for row in plan.get("tasks") or [] if str(row.get("id") or "") == str(task_id)), {})
        produced = [ref for ref in governed_task.get("produces") or [] if ref.get("kind") != "frame"]
        if governed_task.get("bucket") in {"act", "verify"} and not produced:
            raise PlanError(
                "TRACE_LINK_MISSING",
                f"governed task '{task_id}' cannot complete without linked evidence; record the "
                "declared output or link its evidence ref before retrying",
            )
    out = _plan.complete_task(project_id, task_id, store=store)
    if ctx.get("dispatch_token"):
        out = {**out, "dispatch": finalize_dispatch(ctx, "completed plan task", store)}
    return out



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
    project["methodology"] = str(spec["key"])
    if spec.get("integrity"):
        project["integrity"] = dict(spec["integrity"])
    else:
        project.pop("integrity", None)
    project["updated_at"] = utc_now_iso()
    store.upsert_research_project(project)
    plan = _plan.seed_plan_from_methodology(project_id, project.get("goal", ""), spec)
    _plan.save_plan(plan, store=store)
    return store.get_research_project(project_id)



# brief_next + record_judgment: thin forwards to the plan engine (the project's single engine; HX3).



def brief_next(project_id: str, store: Store | None = None) -> dict[str, Any]:
    return _plan.brief_next(project_id, store=store)



def record_judgment(project_id, task_id, gate_tag, decided, rationale,
                    evidence_refs=None, store: Store | None = None,
                    dispatch_token: str | None = None) -> dict[str, Any]:
    store = store or Store()
    ctx = prepare_dispatch_write(project_id, dispatch_token, None, "judgment", store,
                                 allowed_buckets={"verify"}, required_task_id=task_id)
    out = _plan.record_judgment(project_id, task_id, gate_tag, decided, rationale,
                                evidence_refs, store=store,
                                operation_id=str(ctx.get("operation_id") or ""))
    if ctx.get("dispatch_token"):
        out = {**out, "dispatch": finalize_dispatch(ctx, "recorded gate judgment", store)}
    return out


def park_evidence(project_id: str, refs: list[Any], reason: str, task_id: str = "",
                  store: Store | None = None) -> dict[str, Any]:
    return _plan_evidence.park_evidence(project_id, refs, reason, task_id, store=store)


def unpark_evidence(project_id: str, refs: list[Any], reason: str, task_id: str = "",
                    store: Store | None = None) -> dict[str, Any]:
    return _plan_evidence.unpark_evidence(project_id, refs, reason, task_id, store=store)



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


def _capture_prototype_registered(rec: dict[str, Any]) -> None:
    from ..telemetry import capture_product_event
    fidelity = str(rec.get("fidelity") or "").strip().casefold()
    run_mode = str(rec.get("run") or "").strip().casefold()
    capture_product_event(
        "prototype_registered",
        project_id=rec.get("project_id") or "",
        subject_kind="prototype",
        subject_id=rec["id"],
        properties={
            "fidelity": fidelity if fidelity in {"lofi", "midfi", "hifi", "production"} else "other",
            "run_mode": run_mode if run_mode in {"static", "remote"} else "other",
            "remote": run_mode == "remote",
        },
        idempotency_key=f"{rec['id']}:{rec.get('version') or ''}",
    )



def scaffold_artifact(slug, name, concept, type="prototype", tags=None, template=None,
                      project_id=None, store: Store | None = None):
    return _proto.scaffold_artifact(slug, name, concept, type=type, tags=tags, template=template,
                                    project_id=project_id, store=store)



def scaffold_prototype(slug, name, concept, kind="web", template=None,
                       project_id=None, fidelity=None, store: Store | None = None):
    rec = _proto.scaffold_prototype(
        slug, name, concept, kind, template, project_id, fidelity=fidelity, store=store)
    _capture_prototype_registered(rec)
    return rec



def register_prototype(slug, name, path, entry="index.html", run="static", run_cmd=None,
                       version="v0.1", project_id=None, notes="", fidelity="", created_at=None,
                       store: Store | None = None):
    rec = _proto.register_prototype(
        slug, name, path, entry, run, run_cmd, version, project_id, notes,
        fidelity=fidelity, created_at=created_at, store=store)
    _capture_prototype_registered(rec)
    return rec


def register_remote_prototype(slug, name, url, version="v0.1", project_id=None, notes="",
                              fidelity="hifi", note_id=None, store: Store | None = None,
                              dispatch_token: str | None = None):
    """Register metadata for a hosted prototype and optionally pair its originating note.

    The URL is stored, never fetched. In a governed run the artifact is linked as supporting
    evidence to the current dispatch; the session remains the primary output of a test task.
    """
    store = store or Store()
    if not project_id:
        raise ValueError("register_remote_prototype requires project_id")
    _remote_proto.validate_registration(slug, url, project_id=project_id, store=store)
    paired_note = None
    if note_id:
        from ._sections import get_note
        found = get_note(note_id, store=store)
        if str((found.get("project") or {}).get("id") or "") != str(project_id):
            raise PlanError("DISPATCH_SCOPE_MISMATCH", "concept note belongs to another project")
    fingerprint = canonical_payload_fingerprint({
        "slug": slug, "name": name, "url": url, "version": version,
        "project_id": project_id, "notes": notes, "fidelity": fidelity,
        "note_id": note_id or "",
    })
    ctx = prepare_dispatch_write(
        project_id, dispatch_token, None, "artifact", store,
        allowed_buckets={"act", "verify"}, payload_fingerprint=fingerprint)
    prototype = _remote_proto.register(
        slug, name, url, version, project_id, notes, fidelity, store=store)
    _capture_prototype_registered(prototype)
    if note_id:
        from ._sections import set_note_data
        paired_note = set_note_data(
            note_id, {"artifact_kind": "prototype", "prototype_id": prototype["id"]}, store=store)
    out = {"prototype": prototype}
    if paired_note:
        out["note"] = paired_note
    if ctx.get("dispatch_token"):
        out["dispatch"] = bind_dispatch_output(
            ctx, {"kind": "artifact", "id": prototype["id"]},
            "registered hosted prototype", store, complete=False)
    return out



def list_prototypes_artifacts(project_id=None, store: Store | None = None):
    return _proto.list_prototypes(project_id, store=store)



def get_prototype_artifact(prototype_id, store: Store | None = None):
    return _proto.get_prototype(prototype_id, store=store)


def refresh_prototype_design_system(prototype_id, store: Store | None = None):
    return _proto.refresh_prototype_design_system(prototype_id, store=store)


def resolve_prototype_file(prototype_id, asset_path="", refresh_entry=False,
                           store: Store | None = None):
    from .. import prototype_files
    return prototype_files.resolve_prototype_file(
        prototype_id, asset_path, refresh_entry=refresh_entry, store=store)


def prototype_entry_available(prototype_id, store: Store | None = None):
    from .. import prototype_files
    return prototype_files.prototype_entry_available(prototype_id, store=store)



def run_prototype(prototype_id, store: Store | None = None):
    return _proto.run_prototype(prototype_id, store=store)



def stop_prototype(prototype_id, store: Store | None = None):
    return _proto.stop_prototype(prototype_id, store=store)



def delete_prototype_artifact(prototype_id, store: Store | None = None):
    store = store or Store()
    existing = store.get_prototype(prototype_id)
    out = _proto.delete_prototype(prototype_id, store=store)
    if existing and out.get("deleted"):
        from ..telemetry import capture_product_event
        capture_product_event(
            "prototype_deleted",
            project_id=existing.get("project_id") or "",
            subject_kind="prototype",
            subject_id=existing["id"],
            properties={"remote": existing.get("run") == "remote"},
            idempotency_key=existing["id"],
        )
    return out



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
                reaction=None, date_value=None, dispatch_token=None,
                store: Store | None = None):
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
                                       date_value or date.today().isoformat(), reaction,
                                       dispatch_token=dispatch_token, store=store)
        out["recorded"] = {"id": rec["prototype_session"]["id"],
                           "grounded_verified": rec.get("grounded_verified")}
        if rec.get("dispatch"):
            out["dispatch"] = rec["dispatch"]
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
                         "observed_state_refs.")
                        + capability_context_line(profile)
                        + PERSONA_VOICE_CONTRACT
                        + PRIMITIVES_CONTRACT,
    }
    gate = capability_fidelity_warnings(profile, "prototype", proto["name"])  # warn, never block
    if gate:
        brief["warnings"] = gate
    return brief


_DURABLE_BROWSER_ACTION_TYPES = {
    "click", "type", "fill_credential", "select", "key", "scroll", "wait",
}
_DURABLE_SCREENSHOT_RE = re.compile(r"^step-[0-9]+\.png$")


def _durable_session_url(value: Any) -> str:
    """Retain the observed route without query/fragment credentials or tracking data."""
    raw = str(value or "").strip()
    if not raw or any(char in raw for char in ("\\", "\r", "\n", "\t")):
        return ""
    try:
        parsed = urlsplit(raw)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError:
        return ""
    if parsed.scheme not in {"http", "https"} or not hostname:
        return ""
    # Reconstruct from hostname/port instead of parsed.netloc: netloc may still
    # contain URL userinfo (user:password@host). Invalid ports fail above.
    safe_host = f"[{hostname}]" if ":" in hostname else hostname
    safe_netloc = safe_host + (f":{port}" if port is not None else "")
    return urlunsplit((parsed.scheme, safe_netloc, parsed.path or "/", "", ""))


def _durable_session_screenshot(value: Any, session_id: str) -> str:
    """Accept only harness-owned ``step-N.png`` paths and persist their basename."""
    raw = str(value or "").strip().replace("\\", "/")
    if not raw:
        return ""
    path = Path(raw)
    parts = path.parts
    if path.is_absolute() or ".." in parts or not _DURABLE_SCREENSHOT_RE.fullmatch(path.name):
        return ""
    if len(parts) == 1 or (len(parts) == 2 and parts[0] == str(session_id)):
        return path.name
    return ""


def _durable_prototype_steps(log: list[dict[str, Any]] | None,
                             session_id: str) -> list[dict[str, Any]]:
    """Project the retained browser log into a durable, privacy-safe replay trace.

    The in-memory log keeps page text and action payloads only long enough to
    verify ``observed_state_refs``.  Durable evidence needs addressable
    ``step:N`` anchors, not a copy of the page or typed values, so each snapshot
    retains only its order, coarse action type, route, title, and screenshot.
    """
    steps: list[dict[str, Any]] = []
    pending_action: dict[str, Any] | None = None
    for entry in log or []:
        kind = str((entry or {}).get("kind") or "")
        if kind == "action":
            raw_action = entry.get("action") if isinstance(entry.get("action"), dict) else {}
            action_type = str((raw_action or {}).get("type") or "")
            pending_action = {
                "type": action_type if action_type in _DURABLE_BROWSER_ACTION_TYPES else "act",
            }
            target = str((raw_action or {}).get("ref") or "")
            if re.fullmatch(r"e[0-9]+", target):
                pending_action["target"] = target
            continue
        if kind != "snapshot":
            continue
        if not steps:
            action = {"type": "open"}
        elif pending_action:
            action = pending_action
        else:
            action = {"type": "look"}
        state = {
            "url": _durable_session_url(entry.get("url")),
            "title": " ".join(str(entry.get("title") or "").split())[:300],
            "screenshot": _durable_session_screenshot(entry.get("screenshot"), session_id),
        }
        steps.append({
            "index": len(steps),
            "action": action,
            "state": {key: value for key, value in state.items() if value},
        })
        pending_action = None
    return steps



def record_prototype_session(persona_id, prototype_id, session_id, date_value, reaction,
                             key: str | None = None, store: Store | None = None,
                             dispatch_token: str | None = None):
    store = store or Store()
    proto = _proto.get_prototype(prototype_id, store=store)
    project_id = str(proto.get("project_id") or "")
    dispatch_ctx = (prepare_dispatch_write(
        project_id, dispatch_token, key, "session", store,
        allowed_buckets={"act", "verify"}) if project_id else
        {"state": "outside_run", "operation_id": str(key or ""), "key": str(key or "")})
    effective_key = str(dispatch_ctx.get("primitive_key") or key or "") or None
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
        id=(stable_id("protosession", effective_key) if effective_key
            else stable_id("protosession", persona_id, prototype_id, now)),
        persona_id=persona_id,
        prototype_id=proto["id"], session_id=session_id, date=date_value, reaction=reaction,
        observed_state_refs=refs, created_at=now, statements=statements,
        steps=_durable_prototype_steps(log, session_id)).to_dict()
    sess["grounded_verified"] = grounded
    captured_steps = sum(bool((step.get("state") or {}).get("screenshot"))
                         for step in sess.get("steps") or [])
    if captured_steps == len(sess.get("steps") or []) and captured_steps:
        sess["visual_trace"] = "screen_replay"
    elif captured_steps:
        sess["visual_trace"] = "screen_partial"
    else:
        sess["visual_trace"] = "text_only"
    # A prototype can be updated after this run. Stamp the version observed NOW so later critics do
    # not accidentally attribute historical reactions to whatever version happens to be current.
    sess["prototype_version"] = str(proto.get("version") or "unknown")
    if project_id:
        sess["dispatch_provenance"] = {
            "state": dispatch_ctx.get("state", "outside_run"),
            **({"dispatch_token": dispatch_ctx["dispatch_token"],
                "run_id": dispatch_ctx["run_id"], "task_id": dispatch_ctx["task_id"],
                "operation_id": dispatch_ctx["operation_id"]}
               if dispatch_ctx.get("dispatch_token") else {}),
        }
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
    if project_id:
        out["dispatch"] = bind_dispatch_output(
            dispatch_ctx, {"kind": "session", "id": sess["id"]},
            "recorded grounded prototype session", store)
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
    from ..telemetry import capture_product_event
    capture_product_event(
        "session_recorded",
        project_id=project_id,
        subject_kind="session",
        subject_id=sess["id"],
        properties={
            "fidelity": "prototype",
            "step_count": len(sess.get("steps") or []),
            "grounded": grounded,
            "visual_trace": sess.get("visual_trace") or "unknown",
        },
        idempotency_key=sess["id"],
    )
    return out


# ===================== ESV §A.2 — the resumable run object (driver journal) =====================

def run_key(run_id: str, task_id: str, angle: str = "") -> str:
    """The deterministic key every per-step write carries so a re-run is an idempotent upsert."""
    return f"{run_id}:{task_id}:{angle}" if angle else f"{run_id}:{task_id}"


def _dispatch_token(run_id: str, project_id: str, task_id: str, key: str) -> str:
    """Opaque, deterministic identity for one issued run/task operation.

    This is a scope/correlation token, not an authorization bearer. Workspace
    authorization remains the storage/request tenant boundary.
    """
    scope = config.request_tenant_scope()
    workspace_id = str(scope[1]) if scope else "local"
    return stable_id("dispatch", workspace_id, run_id, project_id, task_id, key)


_BASE_SUPPORTING_OUTPUT_KINDS = (
    "asset", "flow", "reference", "evidence", "cohort_selection",
)
_BASE_CLOSING_OUTPUT_KINDS = ("judgment", "task_completion")
_BUILD_PRIMARY_OUTPUT_KINDS = ("artifact", "prototype")
_BUILD_SUPPORTING_OUTPUT_KINDS = (
    "session", "usability_session", "prototype_session",
)


def _ordered_output_kinds(*groups: Any) -> list[str]:
    """Return stable, de-duplicated output-kind names from contract fragments."""
    out: list[str] = []
    for group in groups:
        for value in group or []:
            kind = str(value or "").strip()
            if kind and kind not in out:
                out.append(kind)
    return out


def _normalized_output_contract(
    expected_kind: str,
    *,
    allowed_primary_kinds: list[str] | None = None,
    existing: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the effective persisted contract, including narrow upgrade seams.

    A ``build`` task is complete only when it produces the thing being built.
    Sessions can support that artifact, but must not consume its single primary
    output slot.  Normalizing here also lets an already-issued dispatch expose
    the corrected contract when ``run_step`` is replayed after a deployment.
    """
    current = dict(existing or {})
    declared_primary = list(allowed_primary_kinds or [])
    if expected_kind == "build":
        primary = list(_BUILD_PRIMARY_OUTPUT_KINDS)
    else:
        primary = declared_primary
    supporting = _ordered_output_kinds(
        current.get("supporting_kinds"),
        _BASE_SUPPORTING_OUTPUT_KINDS,
        _BUILD_SUPPORTING_OUTPUT_KINDS if expected_kind == "build" else (),
    )
    closing = _ordered_output_kinds(
        current.get("closing_kinds"), _BASE_CLOSING_OUTPUT_KINDS)
    return {
        **current,
        "schema": str(current.get("schema") or "sonaloop.dispatch_output_contract.v1"),
        "max_primary_outputs": 1,
        "allowed_primary_kinds": primary,
        "supporting_kinds": supporting,
        "closing_kinds": closing,
    }


def _issue_dispatch(run_id: str, project_id: str, task_id: str, bucket: str,
                    key: str, store: Store, public_step_id: str | None = None,
                    trace_contract: dict[str, Any] | None = None) -> dict[str, Any]:
    """Persist one replay-safe dispatch claim on the run and return it."""
    token = _dispatch_token(run_id, project_id, task_id, key)
    scope = config.request_tenant_scope()
    workspace_id = str(scope[1]) if scope else "local"
    trace_contract = dict(trace_contract or {})
    expected_kind = str(trace_contract.get("expected_output_kind") or "")
    exact_primary = list(trace_contract.get("allowed_primary_kinds") or []) or {
        "frame": ["frame"],
        "product_understanding": ["product_understanding"],
        "cohort_integrity": ["cohort_preflight"],
        "synthesis": ["synthesis"],
    }.get(expected_kind, [])
    output_contract = _normalized_output_contract(
        expected_kind, allowed_primary_kinds=exact_primary)
    input_fingerprint = canonical_payload_fingerprint(trace_contract) if trace_contract else ""
    for _attempt in range(16):
        current = store.get_run(run_id)
        if not current or str(current.get("project_id") or "") != project_id:
            raise PlanError("UNKNOWN_RUN", f"unknown run: {run_id}")
        existing = next((d for d in (current.get("dispatches") or [])
                         if str(d.get("dispatch_token") or "") == token), None)
        if existing:
            expected = (project_id, task_id, bucket, key)
            actual = (str(existing.get("project_id") or ""), str(existing.get("task_id") or ""),
                      str(existing.get("bucket") or ""), str(existing.get("key") or ""))
            if actual != expected:
                raise PlanError("DISPATCH_CONFLICT", "dispatch token is bound to different scope")
            if (expected_kind and existing.get("expected_output_kind")
                    and existing.get("expected_output_kind") != expected_kind):
                raise PlanError("DISPATCH_CONFLICT", "dispatch token has a different output contract")
            if (input_fingerprint and existing.get("input_fingerprint")
                    and existing.get("input_fingerprint") != input_fingerprint):
                raise PlanError("DISPATCH_INPUT_CONFLICT", "dispatch inputs changed after issuance")
            # Contract-only upgrades are safe: they preserve dispatch identity,
            # authored inputs, payload claims, and any existing primary output.
            # In particular, do not rewrite a legacy ``session`` primary here;
            # prepare_dispatch_write repairs that claim only when the real build
            # artifact arrives while the dispatch is still mutable.
            if expected_kind == "build":
                normalized = _normalized_output_contract(
                    expected_kind,
                    allowed_primary_kinds=exact_primary,
                    existing=dict(existing.get("output_contract") or {}),
                )
                if normalized != dict(existing.get("output_contract") or {}):
                    updated = copy.deepcopy(current)
                    target = next(
                        d for d in (updated.get("dispatches") or [])
                        if str(d.get("dispatch_token") or "") == token
                    )
                    target["output_contract"] = normalized
                    updated["updated_at"] = utc_now_iso()
                    if store.compare_and_swap_run(current, updated):
                        return target
                    continue
            return existing
        updated = copy.deepcopy(current)
        dispatch = {
            "dispatch_token": token,
            "operation_id": token,
            "workspace_id": workspace_id,
            "project_id": project_id,
            "run_id": run_id,
            "task_id": task_id,
            "step_id": public_step_id or task_id,
            "bucket": bucket,
            "key": key,
            "dispatch_cursor": int(current.get("cursor") or len(current.get("steps") or [])),
            "expected_output_kind": expected_kind,
            "input_fingerprint": input_fingerprint,
            "output_contract": output_contract,
            "primary_output_kind": "",
            "payload_fingerprints": {},
            "payload_revisions": {},
            "status": "issued",
            "issued_at": utc_now_iso(),
        }
        updated.setdefault("dispatches", []).append(dispatch)
        updated["updated_at"] = utc_now_iso()
        if store.compare_and_swap_run(current, updated):
            return dispatch
    raise PlanError("DISPATCH_CONTENTION",
                    "run changed repeatedly while issuing the dispatch; retry run_step")


def _strict_dispatch_project(project: dict[str, Any]) -> bool:
    return str(project.get("governance_contract") or "") == "dispatch_v1"


def prepare_dispatch_write(
    project_id: str,
    dispatch_token: str | None,
    key: str | None,
    output_kind: str,
    store: Store,
    *,
    allowed_buckets: set[str] | None = None,
    required_capability: str = "",
    required_task_id: str = "",
    payload_fingerprint: str = "",
) -> dict[str, Any]:
    """Validate a primitive write before mutation and return its provenance.

    Retry-safe front-door projects (``governance_contract=dispatch_v1``) require
    a token while an active governed run owns the project. Legacy projects and
    deliberate outside-run authoring remain available and are explicitly
    stamped instead of pretending they came through the run loop.
    """
    project = store.get_research_project(project_id)
    if not project:
        raise PlanError("UNKNOWN_PROJECT", f"unknown research project: {project_id}")
    token = str(dispatch_token or "").strip()
    runs = store.list_runs(project_id)
    active = [r for r in runs if r.get("status") == "active"]
    if not token:
        if active and _strict_dispatch_project(project):
            raise PlanError(
                "DISPATCH_TOKEN_REQUIRED",
                f"{output_kind} write belongs to an active governed run; pass the dispatch_token "
                "returned by run_step (legacy/outside-run writes are allowed only without such an owner)",
            )
        return {
            "state": "legacy" if not _strict_dispatch_project(project) else "outside_run",
            "project_id": project_id,
            "output_kind": output_kind,
            "operation_id": str(key or ""),
            "key": str(key or ""),
        }

    found_run = None
    found = None
    for run in runs:
        row = next((d for d in (run.get("dispatches") or [])
                    if str(d.get("dispatch_token") or "") == token), None)
        if row:
            found_run, found = run, row
            break
    if not found or not found_run:
        raise PlanError("UNKNOWN_DISPATCH_TOKEN", "dispatch_token was not issued for this project")
    if str(found.get("project_id") or "") != project_id:
        raise PlanError("DISPATCH_SCOPE_MISMATCH", "dispatch_token belongs to another project")
    scope = config.request_tenant_scope()
    active_workspace = str(scope[1]) if scope else "local"
    if str(found.get("workspace_id") or active_workspace) != active_workspace:
        raise PlanError("DISPATCH_SCOPE_MISMATCH", "dispatch_token belongs to another workspace")
    if allowed_buckets and str(found.get("bucket") or "") not in allowed_buckets:
        raise PlanError(
            "DISPATCH_SCOPE_MISMATCH",
            f"dispatch bucket {found.get('bucket')!r} cannot author {output_kind}",
        )
    if required_task_id and str(found.get("task_id") or "") != str(required_task_id):
        raise PlanError("DISPATCH_SCOPE_MISMATCH",
                        f"dispatch_token belongs to task {found.get('task_id')!r}, not {required_task_id!r}")
    plan = _plan.get_plan(project_id, store=store) or {}
    task = next((t for t in plan.get("tasks") or []
                 if str(t.get("id") or "") == str(found.get("task_id") or "")), None)
    if not task:
        raise PlanError("DISPATCH_SCOPE_MISMATCH", "dispatch task no longer exists in this plan")
    if required_capability and str(task.get("capability") or "") != required_capability:
        raise PlanError(
            "DISPATCH_SCOPE_MISMATCH",
            f"dispatch task capability is {task.get('capability')!r}, expected {required_capability!r}",
        )
    explicit_key = str(key or "").strip()
    if explicit_key and explicit_key not in {str(found.get("key") or ""), token}:
        raise PlanError(
            "DISPATCH_KEY_CONFLICT",
            "an explicit primitive key must equal the dispatch key/token; retries may not mint a new output",
        )
    checkpoint = next((s for s in (found_run.get("steps") or [])
                       if str(s.get("dispatch_token") or "") == token
                       or str(s.get("key") or "") == str(found.get("key") or "")), None)
    if found_run.get("status") != "active" and not checkpoint:
        raise PlanError("DISPATCH_CLOSED", "run closed before this dispatch produced a checkpoint")
    output_contract = dict(found.get("output_contract") or {})
    expected_kind = str(found.get("expected_output_kind") or "")
    support = set(output_contract.get("supporting_kinds") or
                  ["asset", "flow", "reference", "evidence"])
    # Server-added supporting repairs must work on an already-issued production
    # dispatch. They never claim/replace its one primary output.
    support.add("cohort_selection")
    if expected_kind == "build":
        # Compatibility for dispatches issued before build outputs were split
        # into the artifact itself (primary) and observed sessions (supporting).
        support.update(_BUILD_SUPPORTING_OUTPUT_KINDS)
    else:
        # A session/verify dispatch may repair or attach the artifact it exercised without
        # stealing that dispatch's one primary-output slot.
        support.add("artifact")
    closing = set(output_contract.get("closing_kinds") or ["judgment", "task_completion"])
    is_primary = output_kind not in support | closing
    allowed = set(output_contract.get("allowed_primary_kinds") or [])
    if expected_kind == "build":
        # Do not trust the historical ``["build"]`` declaration: ``build`` is
        # the task intent, not a recordable primitive kind.
        allowed = set(_BUILD_PRIMARY_OUTPUT_KINDS)
    if is_primary and allowed and output_kind not in allowed:
        raise PlanError(
            "DISPATCH_OUTPUT_KIND_CONFLICT",
            f"dispatch expects {sorted(allowed)!r}, not {output_kind!r}",
        )
    claimed_kind = str(found.get("primary_output_kind") or "")
    fingerprint = str(payload_fingerprint or "").strip()
    prior_fingerprint = str((found.get("payload_fingerprints") or {}).get(output_kind) or "")
    output_locked = bool(checkpoint or found.get("status") == "completed"
                         or (task or {}).get("status") == "done")
    repairs_legacy_build_primary = bool(
        is_primary
        and expected_kind == "build"
        and claimed_kind in _BUILD_SUPPORTING_OUTPUT_KINDS
        and output_kind in _BUILD_PRIMARY_OUTPUT_KINDS
        and not output_locked
    )
    if (is_primary and claimed_kind and claimed_kind != output_kind
            and not repairs_legacy_build_primary):
        raise PlanError(
            "DISPATCH_OUTPUT_KIND_CONFLICT",
            f"single-output dispatch is already bound to {claimed_kind!r}, not {output_kind!r}",
        )
    if fingerprint and prior_fingerprint and prior_fingerprint != fingerprint and output_locked:
        raise PlanError(
            "DISPATCH_OUTPUT_CONFLICT",
            "the committed dispatch output cannot be replayed with different authored content",
        )
    needs_claim = ((is_primary and (not claimed_kind or repairs_legacy_build_primary))
                   or (fingerprint and fingerprint != prior_fingerprint))
    if needs_claim:
        for _attempt in range(16):
            current_run = store.get_run(str(found_run.get("run_id") or ""))
            current_dispatch = next((d for d in (current_run or {}).get("dispatches") or []
                                     if str(d.get("dispatch_token") or "") == token), None)
            if not current_run or not current_dispatch:
                raise PlanError("UNKNOWN_DISPATCH_TOKEN", "dispatch disappeared while claiming output")
            current_kind = str(current_dispatch.get("primary_output_kind") or "")
            current_checkpoint = next((s for s in (current_run.get("steps") or [])
                                       if str(s.get("dispatch_token") or "") == token), None)
            current_plan = _plan.get_plan(project_id, store=store) or {}
            current_task = next(
                (row for row in (current_plan.get("tasks") or [])
                 if str(row.get("id") or "") == str(current_dispatch.get("task_id") or "")),
                task,
            )
            current_output_locked = bool(
                current_checkpoint
                or current_dispatch.get("status") == "completed"
                or (current_task or {}).get("status") == "done"
            )
            repairs_current_build_primary = bool(
                is_primary
                and expected_kind == "build"
                and current_kind in _BUILD_SUPPORTING_OUTPUT_KINDS
                and output_kind in _BUILD_PRIMARY_OUTPUT_KINDS
                and not current_output_locked
            )
            if (is_primary and current_kind and current_kind != output_kind
                    and not repairs_current_build_primary):
                raise PlanError("DISPATCH_OUTPUT_KIND_CONFLICT",
                                "another primary output already claimed this dispatch")
            current_fp = str((current_dispatch.get("payload_fingerprints") or {}).get(output_kind) or "")
            if (fingerprint and current_fp and current_fp != fingerprint
                    and current_output_locked):
                raise PlanError("DISPATCH_OUTPUT_CONFLICT",
                                "the committed dispatch output cannot be revised")
            updated = copy.deepcopy(current_run)
            target = next(d for d in updated.get("dispatches") or []
                          if str(d.get("dispatch_token") or "") == token)
            if is_primary:
                target["primary_output_kind"] = output_kind
                if repairs_current_build_primary:
                    target.setdefault("primary_output_repair_history", []).append({
                        "from": current_kind,
                        "to": output_kind,
                        "repaired_at": utc_now_iso(),
                        "reason": "legacy build session was classified as the primary output",
                    })
            if expected_kind == "build":
                target["output_contract"] = _normalized_output_contract(
                    expected_kind,
                    allowed_primary_kinds=list(_BUILD_PRIMARY_OUTPUT_KINDS),
                    existing=dict(target.get("output_contract") or {}),
                )
            if fingerprint:
                fps = target.setdefault("payload_fingerprints", {})
                revisions = target.setdefault("payload_revisions", {})
                if current_fp and current_fp != fingerprint:
                    target.setdefault("payload_revision_history", []).append({
                        "output_kind": output_kind, "from": current_fp, "to": fingerprint,
                        "revised_at": utc_now_iso(), "reason": "pre-checkpoint authored repair",
                    })
                fps[output_kind] = fingerprint
                revisions[output_kind] = int(revisions.get(output_kind) or 0) + (
                    1 if current_fp != fingerprint else 0)
            updated["updated_at"] = utc_now_iso()
            if store.compare_and_swap_run(current_run, updated):
                found_run, found = updated, target
                prior_fingerprint = fingerprint or prior_fingerprint
                break
        else:
            raise PlanError("DISPATCH_CONTENTION",
                            "run changed repeatedly while binding the dispatch output")
    return {
        **found,
        "state": "governed",
        "output_kind": output_kind,
        # The dispatch key is the deterministic primitive key.  A transport
        # retry therefore updates/returns one record rather than duplicating it.
        "primitive_key": str(found.get("key") or token),
        "checkpointed": bool(checkpoint),
        "expected_output_kind": str(found.get("expected_output_kind") or ""),
        "input_fingerprint": str(found.get("input_fingerprint") or ""),
        "output_role": (
            "primary" if is_primary else "closing" if output_kind in closing else "supporting"
        ),
        "payload_fingerprint": prior_fingerprint,
        "payload_revision": int((found.get("payload_revisions") or {}).get(output_kind) or 0),
    }


def record_dispatch_progress(
    project_id: str,
    dispatch_token: str,
    action_key: str,
    kind: str,
    payload: dict[str, Any],
    result_digest: str,
    store: Store,
    *,
    allowed_buckets: set[str] | None = None,
    required_capability: str = "",
) -> dict[str, Any]:
    """Persist one replay-safe supporting progress receipt on an issued dispatch.

    Progress is not evidence and never claims or checkpoints the primary output.
    Only fingerprints/digests are journaled, so screen bytes and authored text do
    not leak into the run record.  The same action key with different inputs
    fails closed instead of silently advancing a weak host.
    """
    ctx = prepare_dispatch_write(
        project_id, dispatch_token, None, "reference", store,
        allowed_buckets=allowed_buckets, required_capability=required_capability,
    )
    key = str(action_key or "").strip()
    progress_kind = str(kind or "").strip()
    digest = str(result_digest or "").strip()
    if not key or len(key) > 300 or not key.isprintable():
        raise PlanError("DISPATCH_PROGRESS_BAD_INPUT", "action_key must be 1-300 printable characters")
    if not progress_kind or len(progress_kind) > 100 or not progress_kind.isprintable():
        raise PlanError("DISPATCH_PROGRESS_BAD_INPUT", "kind must be 1-100 printable characters")
    if not digest or len(digest) > 200 or not digest.isprintable():
        raise PlanError("DISPATCH_PROGRESS_BAD_INPUT", "result_digest must be 1-200 printable characters")
    input_fingerprint = canonical_payload_fingerprint(payload)
    for _attempt in range(16):
        current = store.get_run(str(ctx.get("run_id") or ""))
        dispatch = next((row for row in (current or {}).get("dispatches") or []
                         if str(row.get("dispatch_token") or "") == dispatch_token), None)
        if not current or not dispatch:
            raise PlanError("UNKNOWN_DISPATCH_TOKEN", "dispatch disappeared while recording progress")
        existing = dict((dispatch.get("progress_receipts") or {}).get(key) or {})
        if existing:
            if (str(existing.get("input_fingerprint") or "") != input_fingerprint
                    or str(existing.get("result_digest") or "") != digest
                    or str(existing.get("kind") or "") != progress_kind):
                raise PlanError(
                    "DISPATCH_PROGRESS_CONFLICT",
                    "the same dispatch progress key was reused with different inputs or result",
                )
            return {**existing, "idempotent_replay": True}
        receipt = {
            "id": stable_id("progress", str(dispatch_token), key),
            "action_key": key,
            "kind": progress_kind,
            "input_fingerprint": input_fingerprint,
            "result_digest": digest,
            "status": "recorded",
            "recorded_at": utc_now_iso(),
        }
        updated = copy.deepcopy(current)
        target = next(row for row in updated.get("dispatches") or []
                      if str(row.get("dispatch_token") or "") == dispatch_token)
        target.setdefault("progress_receipts", {})[key] = receipt
        updated["updated_at"] = utc_now_iso()
        if store.compare_and_swap_run(current, updated):
            return {**receipt, "idempotent_replay": False}
    raise PlanError("DISPATCH_CONTENTION", "run changed repeatedly while recording progress")


def _dispatch_ref_token(ref: dict[str, Any]) -> str:
    kind, rid = str(ref.get("kind") or ""), str(ref.get("id") or "")
    return f"{kind}:{rid}" if kind and rid else rid


def finalize_dispatch(ctx: dict[str, Any], summary: str, store: Store) -> dict[str, Any]:
    """Complete/checkpoint a token-bound task after its required writes exist."""
    if not ctx.get("dispatch_token"):
        return {"state": ctx.get("state", "outside_run"), "checkpointed": False}
    pid, tid = str(ctx["project_id"]), str(ctx["task_id"])
    plan = _plan.get_plan(pid, store=store) or {}
    task = next((t for t in plan.get("tasks") or [] if str(t.get("id") or "") == tid), None)
    if not task:
        raise PlanError("DISPATCH_SCOPE_MISMATCH", "dispatch task no longer exists")
    if task.get("status") != "done":
        try:
            completed = _plan.complete_task(pid, tid, store=store)
        except PlanError as exc:
            if exc.code in {"GATE_UNMET", "REACTION_EVIDENCE_UNMET"}:
                return {"state": "linked", "checkpointed": False, "task_id": tid,
                        "needs": exc.message}
            raise
        if completed.get("trace_nudge"):
            return {"state": "linked", "checkpointed": False, "task_id": tid,
                    "needs": completed["trace_nudge"]["message"]}
    fresh = _plan.get_plan(pid, store=store) or {}
    fresh_task = next((t for t in fresh.get("tasks") or [] if str(t.get("id") or "") == tid), task)
    if ctx.get("checkpointed"):
        # Historical versions could checkpoint a dispatch before its plan gate had actually
        # completed. Once missing evidence repairs that gate, keep the immutable old receipt and
        # reconcile the plan instead of attempting a conflicting second checkpoint for the key.
        # Exact transport replays take this path too, so preserve checkpoint_step's public
        # idempotency signal even though no second journal write is attempted here.
        receipt = {**dict(ctx.get("receipt") or {}), "deduplicated": True}
        return {
            "state": "completed", "checkpointed": True, "task_id": tid,
            "receipt": receipt,
            "reconciled_existing_checkpoint": True,
        }
    refs = [_dispatch_ref_token(r) for r in (fresh_task.get("produces") or [])
            if r.get("kind") != "frame" or ctx.get("output_kind") == "frame"]
    receipt = checkpoint_step(str(ctx["run_id"]), {
        "task_id": tid,
        "bucket": str(ctx.get("bucket") or ""),
        "key": str(ctx.get("key") or ""),
        "dispatch_token": str(ctx["dispatch_token"]),
        "evidence": refs,
        "produced_refs": refs,
        "summary": summary,
    }, store=store)
    return {"state": "completed", "checkpointed": True, "task_id": tid, "receipt": receipt}


def bind_dispatch_output(ctx: dict[str, Any], ref: dict[str, Any], summary: str,
                         store: Store, *, complete: bool = True) -> dict[str, Any]:
    """Auto-link one produced ref and, when ready, complete/checkpoint its dispatch."""
    if not ctx.get("dispatch_token"):
        return {"state": ctx.get("state", "outside_run"), "checkpointed": False,
                "provenance": "not governed by an active dispatch"}
    _plan.link_evidence(str(ctx["project_id"]), str(ctx["task_id"]), ref, store=store)
    # Supporting evidence belongs in the task trace, but it cannot finish a
    # single-primary dispatch by itself. Callers may still explicitly suppress
    # completion for legacy contexts that predate output-role classification.
    if not complete or ctx.get("output_role") == "supporting":
        return {"state": "linked", "checkpointed": False, "task_id": ctx["task_id"],
                "produced_ref": _dispatch_ref_token(ref)}
    return finalize_dispatch({**ctx, "output_kind": str(ref.get("kind") or ctx.get("output_kind") or "")},
                             summary, store)


def _start_run_locked(project_id: str, budget: int | None = None, run_id: str | None = None,
                      store: Store | None = None,
                      operation_id: str | None = None) -> dict[str, Any]:
    """Create (or load) the run object for a project — the resumable journal the driver advances. If
    `run_id` already exists, it is returned as-is (resume). A stable ``operation_id`` gives callers
    retry-safe initial creation when they do not yet know the generated run id. A project can own
    only one active run: a second create fails with the exact existing id and resume call."""
    store = store or Store()
    project = store.get_research_project(project_id)
    if not project:
        raise PlanError("UNKNOWN_PROJECT", f"unknown research project: {project_id}")
    lifecycle = str(project.get("status") or "active")
    if lifecycle in {"archived", "superseded"}:
        raise PlanError(
            "PROJECT_CLOSED",
            f"PROJECT_CLOSED: project {project_id} is {lifecycle}; preserved projects cannot "
            "acquire a new run.",
        )
    operation_id = _start_project_operation_id(operation_id)
    if operation_id and run_id:
        raise ValueError("start_run accepts either run_id (resume) or operation_id (retry-safe create), not both")
    requested_budget = int(budget) if budget is not None else None
    fingerprint = hashlib.sha256(json.dumps(
        {"project_id": project_id, "budget": requested_budget},
        sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")).hexdigest()
    effective_run_id = (
        stable_id("run_operation", operation_id) if operation_id else str(run_id or "") or None
    )

    def replay_or_conflict(existing: dict[str, Any]) -> dict[str, Any]:
        if str(existing.get("project_id") or "") != str(project_id):
            raise PlanError(
                "RUN_IDEMPOTENCY_CONFLICT",
                "RUN_IDEMPOTENCY_CONFLICT: run identity belongs to another project",
            )
        previous = str(existing.get("operation_fingerprint") or "")
        if operation_id and (
            str(existing.get("operation_id") or "") != operation_id
            or (previous and previous != fingerprint)
        ):
            raise PlanError(
                "RUN_IDEMPOTENCY_CONFLICT",
                "RUN_IDEMPOTENCY_CONFLICT: operation_id was reused with different start_run inputs",
            )
        if run_id and budget is not None and existing.get("budget") != requested_budget:
            raise PlanError(
                "RUN_IDEMPOTENCY_CONFLICT",
                "RUN_IDEMPOTENCY_CONFLICT: run_id resume cannot change its budget",
            )
        return {**existing, "idempotent_replay": True}

    if effective_run_id:
        existing = store.get_run(effective_run_id)
        if existing:
            return replay_or_conflict(existing)
    now = utc_now_iso()
    plan = _plan.get_plan(project_id, store=store) or {}
    run = {"run_id": effective_run_id or stable_id("run", project_id, now), "project_id": project_id,
           "methodology": plan.get("methodology", ""), "status": "active",
           "budget": requested_budget, "cursor": 0,
           "steps": [], "dispatches": [], "critic_rounds": [], "created_at": now, "updated_at": now}
    if operation_id:
        run["operation_id"] = operation_id
        run["operation_fingerprint"] = fingerprint
    owner = store.claim_active_run(run)
    owner_run_id = str(owner["run_id"])
    if owner_run_id == run["run_id"]:
        if owner.get("created"):
            return run
        existing = store.get_run(owner_run_id)
        if not existing:  # pragma: no cover - committed claim must expose its journal
            raise RuntimeError("run operation claim exists without its run journal")
        return replay_or_conflict(existing)
    raise PlanError(
        "ACTIVE_RUN_EXISTS",
        f"ACTIVE_RUN_EXISTS: project {project_id} already has active run {owner_run_id}. "
        f"Resume it with start_run(project_id={project_id!r}, run_id={owner_run_id!r}), "
        f"then continue with run_step(run_id={owner_run_id!r}); do not create a replacement run.",
    )


def start_run(project_id: str, budget: int | None = None, run_id: str | None = None,
              store: Store | None = None, operation_id: str | None = None) -> dict[str, Any]:
    """Create or resume the project's sole active governed run.

    Lifecycle changes and new run ownership are serialized across processes, so an archive or
    supersede can never race a new active journal onto a closed project.
    """
    store = store or Store()
    with project_lifecycle_locks(store, [project_id]):
        result = _start_run_locked(
            project_id, budget=budget, run_id=run_id, store=store,
            operation_id=operation_id,
        )
    if not result.get("idempotent_replay"):
        from ..telemetry import capture_product_event
        capture_product_event(
            "run_started",
            project_id=project_id,
            subject_kind="run",
            subject_id=str(result["run_id"]),
            properties={"budget": result.get("budget"), "resumed": False},
            idempotency_key=str(result["run_id"]),
        )
    return result


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


def _checkpoint_entry(step: dict[str, Any], idx: int) -> dict[str, Any]:
    entry = {"idx": idx, "task_id": step.get("task_id", ""), "bucket": step.get("bucket", ""),
             "key": str(step.get("key") or ""), "evidence": step.get("evidence", []),
             "dispatch_token": str(step.get("dispatch_token") or ""),
             "summary": str(step.get("summary", ""))[:300]}
    for field in _RUN_STEP_TRACE_LIST_FIELDS:
        entry[field] = _trace_list(step.get(field))
    if not entry["produced_refs"] and step.get("evidence"):
        entry["produced_refs"] = _trace_list(step.get("evidence"))
    if "expected_output_kind" in step:
        entry["expected_output_kind"] = str(step.get("expected_output_kind") or "")
    return entry


def _checkpoint_payload(entry: dict[str, Any]) -> dict[str, Any]:
    """The immutable content claimed by a deterministic checkpoint key."""
    payload = {
        "task_id": entry.get("task_id", ""),
        "bucket": entry.get("bucket", ""),
        "key": str(entry.get("key") or ""),
        "dispatch_token": str(entry.get("dispatch_token") or ""),
        "evidence": entry.get("evidence", []),
        "summary": str(entry.get("summary", ""))[:300],
    }
    for field in _RUN_STEP_TRACE_LIST_FIELDS:
        payload[field] = _trace_list(entry.get(field))
    if not payload["produced_refs"] and payload["evidence"]:
        payload["produced_refs"] = _trace_list(payload["evidence"])
    if "expected_output_kind" in entry:
        payload["expected_output_kind"] = str(entry.get("expected_output_kind") or "")
    return payload


def _checkpoint_receipt(run_id: str, entry: dict[str, Any]) -> dict[str, Any]:
    idx = int(entry.get("idx", 0))
    return {"run_id": run_id, "cursor": idx + 1, "step_idx": idx,
            "key": str(entry.get("key") or "")}


def checkpoint_step(run_id: str, step: dict[str, Any], store: Store | None = None) -> dict[str, Any]:
    """Append a completed step to the journal (ids + a 1-line summary). Returns the new cursor.

    The original `evidence` field stays for old callers. The explicit trace fields let autonomous
    authors record the I/O contract they actually fulfilled, so later UI/assessment can distinguish
    "new evidence not consumed yet" from "forgotten evidence". A non-empty deterministic ``key``
    is an idempotency key: retrying it returns the original cursor without appending another row.
    """
    store = store or Store()
    for _attempt in range(16):
        current = store.get_run(run_id)
        if not current:
            raise PlanError("UNKNOWN_RUN", f"unknown run: {run_id}")
        entry = _checkpoint_entry(step, len(current.get("steps") or []))
        key = entry["key"]
        token = entry["dispatch_token"]
        issued = None
        if token:
            issued = next((d for d in (current.get("dispatches") or [])
                           if str(d.get("dispatch_token") or "") == token), None)
            if not issued:
                raise PlanError("UNKNOWN_DISPATCH_TOKEN",
                                "checkpoint dispatch_token was not issued by this run")
            if (str(issued.get("task_id") or "") != str(entry.get("task_id") or "")
                    or str(issued.get("key") or "") != key
                    or str(issued.get("bucket") or "") != str(entry.get("bucket") or "")):
                raise PlanError("DISPATCH_SCOPE_MISMATCH",
                                "checkpoint task/bucket/key do not match the issued dispatch")
        else:
            project = store.get_research_project(str(current.get("project_id") or "")) or {}
            if _strict_dispatch_project(project) and current.get("status") == "active":
                raise PlanError(
                    "DISPATCH_TOKEN_REQUIRED",
                    "checkpoint belongs to a dispatch_v1 run; echo run_step.dispatch_token",
                )
        if key:
            previous = next((row for row in (current.get("steps") or [])
                             if str(row.get("key") or "") == key), None)
            if previous is not None:
                if _checkpoint_payload(previous) != _checkpoint_payload(entry):
                    raise PlanError(
                        "CHECKPOINT_KEY_CONFLICT",
                        "CHECKPOINT_KEY_CONFLICT: checkpoint key was already committed with a different payload",
                    )
                receipt = dict(previous.get("receipt") or _checkpoint_receipt(run_id, previous))
                return {**receipt, "deduplicated": True}
        updated = copy.deepcopy(current)
        entry["receipt"] = _checkpoint_receipt(run_id, entry)
        updated.setdefault("steps", []).append(entry)
        if issued:
            for dispatch in updated.get("dispatches") or []:
                if str(dispatch.get("dispatch_token") or "") == token:
                    dispatch["status"] = "completed"
                    dispatch["completed_at"] = utc_now_iso()
                    dispatch["produced_refs"] = list(entry.get("produced_refs") or [])
                    dispatch["receipt"] = dict(entry["receipt"])
                    break
        updated["cursor"] = len(updated["steps"])
        updated["updated_at"] = utc_now_iso()
        if store.compare_and_swap_run(current, updated):
            return {**entry["receipt"], "deduplicated": False}
    raise PlanError(
        "CHECKPOINT_CONTENTION",
        "CHECKPOINT_CONTENTION: the run journal changed repeatedly; retry the same deterministic key",
    )


def record_critic_round(
    run_id: str,
    critic_report_id: str,
    key: str,
    store: Store | None = None,
) -> dict[str, Any]:
    """Atomically bind one persisted critic report to one deterministic run round.

    Pass the report id returned by ``record_completeness_critic`` and the critic
    dispatch key returned by ``run_step``. Passed/missing state is derived from
    the report, so retries cannot manufacture two independent dry rounds.
    """
    store = store or Store()
    key = str(key or "").strip()
    if not key:
        raise ValueError("critic round key is required")
    for _attempt in range(16):
        current = store.get_run(run_id)
        if not current:
            raise PlanError("UNKNOWN_RUN", f"unknown run: {run_id}")
        project = store.get_research_project(current["project_id"]) or {}
        report = next((item for item in (project.get("critic_reports") or [])
                       if str(item.get("id") or "") == str(critic_report_id)), None)
        if report is None or str(report.get("run_id") or "") != str(run_id):
            raise PlanError(
                "CRITIC_REPORT_MISMATCH",
                "CRITIC_REPORT_MISMATCH: report must exist and belong to this run",
            )
        rounds = current.get("critic_rounds") or []
        keyed = next((item for item in rounds if str(item.get("key") or "") == key), None)
        if keyed is not None:
            if str(keyed.get("critic_report_id") or "") != str(critic_report_id):
                raise PlanError(
                    "CRITIC_ROUND_CONFLICT",
                    "CRITIC_ROUND_CONFLICT: critic key was already bound to another report",
                )
            return {"round": int(keyed["round"]), "passed": bool(keyed.get("passed")),
                    "critic_report_id": critic_report_id, "key": key, "deduplicated": True}
        already = next((item for item in rounds
                        if str(item.get("critic_report_id") or "") == str(critic_report_id)), None)
        if already is not None:
            return {"round": int(already["round"]), "passed": bool(already.get("passed")),
                    "critic_report_id": critic_report_id, "key": str(already.get("key") or ""),
                    "deduplicated": True}
        updated = copy.deepcopy(current)
        round_row = {
            "round": len(rounds),
            "key": key,
            "critic_report_id": str(critic_report_id),
            "passed": bool(report.get("passed")),
            "missing": len(report.get("missing") or []),
        }
        updated.setdefault("critic_rounds", []).append(round_row)
        updated["updated_at"] = utc_now_iso()
        if store.compare_and_swap_run(current, updated):
            return {**round_row, "deduplicated": False}
    raise PlanError(
        "CRITIC_ROUND_CONTENTION",
        "CRITIC_ROUND_CONTENTION: run critic journal changed repeatedly; retry the same key",
    )


def finish_run(run_id: str, status: str = "finished", store: Store | None = None) -> dict[str, Any]:
    """Close a run, failing closed when ``finished`` is not engine-verified.

    ``stopped`` and ``capped`` remain explicit operational exits.  A successful finish is a
    research-quality claim: the plan/result contract and finish work must be complete and both
    the run journal and persisted project must contain the required trailing dry critic rounds.
    Normal callers should loop :func:`run_step`; its deterministic done branch satisfies these
    same checks before calling this function.
    """
    store = store or Store()
    r = store.get_run(run_id)
    if not r:
        raise PlanError("UNKNOWN_RUN", f"unknown run: {run_id}")
    allowed_statuses = {"finished", "stopped", "capped"}
    if status not in allowed_statuses:
        raise PlanError(
            "INVALID_RUN_STATUS",
            "INVALID_RUN_STATUS: status must be one of finished, stopped, capped",
        )
    if status == "finished":
        assessment = assess_project(r["project_id"], store=store)
        project = store.get_research_project(r["project_id"]) or {}
        critic_reports = {str(report.get("id") or ""): report
                          for report in (project.get("critic_reports") or [])}
        dry_rounds: list[dict[str, Any]] = []
        seen_report_ids: set[str] = set()
        for round_row in reversed(r.get("critic_rounds") or []):
            report_id = str(round_row.get("critic_report_id") or "")
            if (not round_row.get("passed") or round_row.get("missing")
                    or not report_id or report_id in seen_report_ids):
                break
            report = critic_reports.get(report_id)
            if (not report or str(report.get("run_id") or "") != str(run_id)
                    or not report.get("passed") or report.get("missing")):
                break
            seen_report_ids.add(report_id)
            dry_rounds.append(round_row)
        missing: list[str] = []
        if not assessment.get("complete"):
            missing.append("the plan/result contract is still open")
        if not (assessment.get("finish") or {}).get("finished"):
            missing.append("organize/conclusion/report finish work is incomplete")
        if len(dry_rounds) < _RUN_K_DRY:
            missing.append(
                f"the run lacks {_RUN_K_DRY} distinct, persisted and run-bound trailing critic passes"
            )
        if missing:
            raise PlanError(
                "RUN_NOT_FINISHABLE",
                "RUN_NOT_FINISHABLE: " + "; ".join(missing) +
                ". Continue with run_step(run_id); do not force-finish the run.",
            )
    if r.get("status") == status:
        store.release_active_run_claim(r["project_id"], run_id)
        return {"run_id": run_id, "status": status, "steps": len(r.get("steps") or []),
                "deduplicated": True}
    r["status"] = status
    r["updated_at"] = utc_now_iso()
    store.upsert_run(r)
    # Status is canonical; releasing the matching ownership row is repairable. A
    # concurrent newer owner cannot be removed because deletion also matches run_id.
    store.release_active_run_claim(r["project_id"], run_id)
    emit_lifecycle_event("run.finished", {"run_id": run_id, "project_id": r["project_id"],  # noqa: F821 (bound)
                                          "status": status, "steps": len(r["steps"])}, store)
    from ..telemetry import capture_product_event
    capture_product_event(
        "run_finished",
        project_id=str(r["project_id"]),
        subject_kind="run",
        subject_id=run_id,
        properties={
            "run_status": status,
            "step_count": len(r.get("steps") or []),
            "critic_rounds": len(r.get("critic_rounds") or []),
        },
        idempotency_key=f"{run_id}:{status}",
    )
    return {"run_id": run_id, "status": status, "steps": len(r["steps"]),
            "deduplicated": False}


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
    seen: set[str] = set()
    for r in reversed(rounds):
        report_id = str(r.get("critic_report_id") or "")
        if r.get("passed") and not r.get("missing") and report_id and report_id not in seen:
            seen.add(report_id)
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
    explicit_output = str(t.get("expected_output_kind") or "")
    expected = (explicit_output or
                (str(t.get("capability") or "frame") if t.get("bucket") == "analyze"
                 else str(t.get("capability") or t.get("bucket") or "")))
    return {"consume_task_ids": consumes, "consume_refs": consume_refs,
            "optional_context_refs": optional_context_refs, "open_questions": open_questions,
            "expected_output_kind": expected,
            "allowed_primary_kinds": [explicit_output] if explicit_output else [],
            "must_link_before_complete": t.get("bucket") in ("act", "verify")}


def _rl_dispatch(run: dict[str, Any], n: dict[str, Any], store: Store) -> dict[str, Any]:
    trace = _rl_trace_contract(run["project_id"], n["task"], store)
    key = run_key(run["run_id"], n["task"])
    dispatch = _issue_dispatch(run["run_id"], run["project_id"], n["task"], n["bucket"], key,
                               store, trace_contract=trace)
    routed = copy.deepcopy(n)
    blocking = routed.get("blocking_action") or {}
    arguments = (blocking.get("next_call") or {}).get("arguments") or {}
    if arguments:
        if "run_id" in arguments:
            arguments["run_id"] = str(run["run_id"])
        if "dispatch_token" in arguments:
            arguments["dispatch_token"] = str(dispatch["dispatch_token"])
        tool = str((blocking.get("next_call") or {}).get("tool") or "")
        if tool in {"record_flow_manifest", "select_reaction_test_cohort"}:
            suffix = "flow-manifest" if tool == "record_flow_manifest" else "cohort-selection"
            arguments["operation_id"] = f"{dispatch['operation_id']}:{suffix}"
    return {"kind": n["bucket"], "step_id": n["task"], "key": key,
            "dispatch_token": dispatch["dispatch_token"], "operation_id": dispatch["operation_id"],
            "dispatch_cursor": dispatch["dispatch_cursor"],
            "input_fingerprint": dispatch["input_fingerprint"],
            "output_contract": dict(dispatch["output_contract"]),
            "next_action": routed,
            **({"blocking_action": blocking} if blocking else {}),
            "directive": (routed.get("instructions", "") + " Pass this dispatch_token to every record/"
                          "completion write for the step; token-aware recorders auto-link and checkpoint, "
                          "so do not checkpoint a second time when dispatch.checkpointed=true."), **trace}


def _rl_report_handoff_dispatch(
    run: dict[str, Any], project_id: str, store: Store,
) -> dict[str, Any]:
    """Issue/replay the one resumable, authored report hand-off dispatch.

    A report outline is only progress.  The same dispatch stays open while the
    host authors its sections, and the final ``record_synthesis_section`` binds
    the report and checkpoints it.  Re-entering ``run_step`` after a host/model
    interruption therefore points at the same report and first unfinished
    section instead of creating another Job/report or advancing to the critic.
    """
    plan = _plan.get_plan(project_id, store=store) or {}
    tasks = list(plan.get("tasks") or [])
    terminal = next(
        (str(task.get("id") or "") for task in reversed(tasks)
         if str(task.get("bucket") or "") == "verify" and str(task.get("id") or "")),
        "",
    ) or next(
        (str(task.get("id") or "") for task in reversed(tasks)
         if str(task.get("id") or "")),
        "",
    )
    if not terminal:
        raise PlanError(
            "REPORT_HANDOFF_TASK_MISSING",
            "REPORT_HANDOFF_TASK_MISSING: the completed project has no plan task to own its report",
        )
    key = run_key(str(run["run_id"]), "report-handoff")
    dispatch = _issue_dispatch(
        str(run["run_id"]), project_id, terminal, "verify", key, store,
        public_step_id="__report_handoff__",
        trace_contract={
            "expected_output_kind": "report",
            "allowed_primary_kinds": ["report"],
            "terminal": True,
            "consume_refs": [f"task:{terminal}"],
            "must_link_before_complete": True,
        },
    )
    report = scaffold_synthesis(  # noqa: F821 (bound by services package)
        project_id,
        operation_id=str(dispatch["operation_id"]),
        dispatch_token=str(dispatch["dispatch_token"]),
        store=store,
    )
    report_dispatch = dict(report.get("dispatch") or {})
    # This can happen only when another exact retry authored the final section
    # between assessment and scaffold.  Advance from the now-checkpointed state
    # instead of asking the host to touch a finalized report.
    if report_dispatch.get("checkpointed"):
        return run_step(str(run["run_id"]), store=store)

    handoff = dict(report.get("handoff") or {})
    report_state = next(iter(handoff.get("reports") or []), {})
    pending = [str(value) for value in
               (report_state.get("incomplete_section_ids") or []) if str(value)]
    all_sections = [str(section.get("id") or "")
                    for section in (report.get("sections") or [])
                    if str(section.get("id") or "")]
    next_section = pending[0] if pending else ""
    if next_section:
        next_call = {
            "tool": "brief_synthesis_section",
            "arguments": {
                "project_id": project_id,
                "section_id": next_section,
                "report_id": str(report["id"]),
            },
        }
        recovery = (
            "Call brief_synthesis_section for the next incomplete section; author its markdown and "
            "citations from that brief; then call record_synthesis_section with this exact report_id "
            "and dispatch_token. Repeat for every incomplete_section_id. The final section "
            "auto-links and checkpoints the report; then call run_step again."
        )
    else:
        # A legacy partially authored report can have complete bodies but no
        # cover lead.  Keep it resumable and explicit rather than silently
        # manufacturing an authored claim.
        next_call = {
            "tool": "brief_synthesis_outline",
            "arguments": {"project_id": project_id},
        }
        recovery = (
            "The existing report bodies are preserved, but its lead is empty. Call "
            "brief_synthesis_outline, author a non-empty build_order_narrative with the exact existing "
            "section structure, then call record_synthesis_outline with this exact report_id and "
            "dispatch_token, omitting operation_id for this in-place lead repair. The completed report "
            "auto-links and checkpoints; then call run_step again."
        )
    blocking_action = {
        "code": "REPORT_HANDOFF_INCOMPLETE",
        "reason": "The project report is a draft until its lead and every section are authored.",
        "next_call": next_call,
        "recovery_sequence": recovery,
    }
    return {
        "kind": "verify",
        "step_id": "__report_handoff__",
        "task_id": terminal,
        "key": key,
        "dispatch_token": dispatch["dispatch_token"],
        "operation_id": dispatch["operation_id"],
        "dispatch_cursor": dispatch["dispatch_cursor"],
        "input_fingerprint": dispatch["input_fingerprint"],
        "output_contract": dict(dispatch["output_contract"]),
        "terminal_verify": terminal,
        "report_id": str(report["id"]),
        "section_ids": all_sections,
        "incomplete_section_ids": pending,
        "lead_missing": bool(report_state.get("lead_missing")),
        "blocking_action": blocking_action,
        "directive": recovery,
        "consume_refs": [f"task:{terminal}"],
        "expected_output_kind": "report",
        "allowed_primary_kinds": ["report"],
        "must_link_before_complete": True,
    }


def run_step(run_id: str, store: Store | None = None) -> dict[str, Any]:
    """The deterministic brain. Returns the next dispatch for the host to execute:
    {kind: analyze|act|verify, step_id, key, next_action, directive} → spawn ONE authoring subagent
    then checkpoint_step; {kind: critic, brief} → spawn an INDEPENDENT critic then record_critic_round;
    {kind: done, status, summary} → stop. Deterministic finish work organizes the graph and issues
    one resumable authored report hand-off before the critic; critic-gap injection remains inline.
    Idempotent / resumable: it reads the live plan and report state."""
    store = store or Store()
    run = store.get_run(run_id)
    if not run:
        raise PlanError("UNKNOWN_RUN", f"unknown run: {run_id}")
    pid = run["project_id"]
    persisted_status = str(run.get("status") or "active")
    if persisted_status != "active":
        # Terminal journals are immutable. A lost response or an overeager
        # external host may repeat run_step after completion; replay the
        # terminal observation without issuing a new dispatch or mutating the
        # plan. Unknown persisted states fail closed as stopped rather than
        # becoming an accidental execution capability.
        terminal_status = (
            persisted_status
            if persisted_status in {"finished", "stopped", "capped"}
            else "stopped"
        )
        return {
            "kind": "done",
            "status": terminal_status,
            "persisted_status": persisted_status,
            "idempotent_replay": True,
            "summary": _rl_summary(pid, store),
        }
    budget = run.get("budget")
    if budget is not None and len(run.get("steps", [])) >= budget:
        # A capped run may organize what exists, but must not manufacture an
        # empty report that looks like a hand-off.  The next resumed/new run can
        # issue the governed report-authoring dispatch when the evidence is ready.
        derive_sections(pid, store=store)  # noqa: F821 (bound)
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
        a = assess_project(pid, store=store)
        if not a["finish"].get("concluded"):
            terminal = next((t["id"] for t in reversed((_plan.get_plan(pid, store=store) or {}).get("tasks", []))
                             if t["bucket"] == "verify"), None)
            conclusion_key = run_key(run_id, "conclusion")
            dispatch = _issue_dispatch(
                run_id, pid, terminal, "verify", conclusion_key, store,
                public_step_id="__conclusion__",
                trace_contract={"expected_output_kind": "synthesis", "terminal": True,
                                "consume_refs": [f"task:{terminal}"]},
            )
            return {"kind": "verify", "step_id": "__conclusion__", "task_id": terminal,
                    "key": conclusion_key, "dispatch_token": dispatch["dispatch_token"],
                    "operation_id": dispatch["operation_id"],
                    "dispatch_cursor": dispatch["dispatch_cursor"],
                    "input_fingerprint": dispatch["input_fingerprint"],
                    "output_contract": dict(dispatch["output_contract"]),
                    "terminal_verify": terminal,
                    "directive": ("Author a RICH terminal solution-presentation synthesis (record_synthesis: "
                                  "gesamtbild + positionierung + pain_solvers + ranking/shortlist; the answer, "
                                  "who-wins + deliberate non-targets, validated solvers, build spec) and "
                                  "pass this dispatch_token. The recorder auto-links it to terminal verify task "
                                  f"`{terminal}` and checkpoints the conclusion.")}
        if not a["finish"].get("handed_off"):
            return _rl_report_handoff_dispatch(run, pid, store)
    if a["complete"] and a["finish"]["finished"]:
        rounds = run.get("critic_rounds", [])
        if _rl_trailing_dry(rounds) >= _RUN_K_DRY:
            finish_run(run_id, "finished", store=store)
            return {"kind": "done", "status": "finished", "summary": _rl_summary(pid, store)}
        if len(rounds) >= _RUN_MAX_CRITIC:
            finish_run(run_id, "capped", store=store)
            return {"kind": "done", "status": "capped", "summary": _rl_summary(pid, store)}
        critic_key = run_key(run_id, f"critic:{len(rounds)}")
        return {"kind": "critic", "run_id": run_id, "key": critic_key,
                "operation_id": critic_key,
                "brief": brief_completeness_critic(pid, store=store),  # noqa: F821
                "directive": ("Spawn an INDEPENDENT critic subagent: author the verdict from the brief; "
                              "call record_completeness_critic(project_id, verdict, run_id, "
                              "operation_id=<this dispatch operation_id>); then call record_critic_round("
                              "run_id, critic_report_id=<returned id>, key=<this dispatch key>).")}
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
