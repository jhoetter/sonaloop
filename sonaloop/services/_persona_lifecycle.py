"""Governed persona preparation: task readiness, immutable contexts and builds."""
from __future__ import annotations

import hashlib
import json
from datetime import date, timedelta
from typing import Any

from .. import memory as memory_mod
from ..config import utc_now_iso
from ..storage import Store
from ._capabilities import CAPABILITY_RUNGS, capability_profile
from ._common import *  # noqa: F401,F403


def _task_grounding_hits(persona: dict[str, Any], task: str, store: Store,
                         limit: int = 6) -> list[dict[str, Any]]:
    corpus_ids = list((persona.get("grounding") or {}).get("corpus_ids") or [])
    if not corpus_ids:
        return []
    from ._grounding import search_corpus
    return search_corpus(task, corpus_ids, limit=limit, store=store)


def persona_task_readiness(persona_id: str, task: str, project_id: str | None = None,
                           as_of: str | None = None,
                           required_capability: str | None = None,
                           store: Store | None = None) -> dict[str, Any]:
    """Judge whether this persona is prepared for this exact assignment.

    Global depth is necessary but insufficient: task-relevant lived memory or
    independent grounding must also exist, and the requested interaction rung must
    be plausible.  This is a read-only diagnostic, never behavioral proof.
    """
    store = store or Store()
    persona = _require_persona(store, persona_id)
    task = str(task or "").strip()
    if not task:
        raise ValueError("task-specific persona readiness requires a non-empty task")
    if as_of:
        as_of = _parse_date(as_of).isoformat()
    project = None
    if project_id:
        project = _require_research_project(store, project_id)
    if required_capability and required_capability not in CAPABILITY_RUNGS:
        raise ValueError(f"required_capability must be one of {list(CAPABILITY_RUNGS)}")

    global_readiness = persona_readiness(persona["id"], store=store)  # noqa: F821 (bound)
    recall = memory_mod.recall(store, persona["id"], task, as_of=as_of, k=10)
    relevant_hits = [hit for hit in recall["hits"]
                     if float(hit.get("keyword") or 0) > 0
                     or float(hit.get("semantic") or 0) >= .2]
    grounding_hits = _task_grounding_hits(persona, task, store)
    caps = capability_profile(persona)
    capability_ok = not required_capability or bool((caps.get("rungs") or {}).get(required_capability))
    in_project = not project or persona["id"] in (project.get("persona_ids") or [])

    limitations: list[str] = []
    if global_readiness["level"] != "ready":
        limitations.append(f"global_readiness:{global_readiness['level']}")
    if not relevant_hits:
        limitations.append("no_task_relevant_lived_memory")
    if not grounding_hits:
        limitations.append("no_task_relevant_independent_grounding")
    if not capability_ok:
        limitations.append(f"capability_rung_unavailable:{required_capability}")
    if not in_project:
        limitations.append("persona_not_in_project_cohort")

    task_signal = bool(relevant_hits or grounding_hits)
    ready = global_readiness["level"] == "ready" and task_signal and capability_ok and in_project
    level = "ready" if ready else (
        "limited" if task_signal and global_readiness["level"] in {"ready", "developing"}
        and capability_ok and in_project else "not_ready")
    refs = ([{"kind": "memory", "id": hit["obj_id"], "score": hit["score"]}
             for hit in relevant_hits[:6]]
            + [{"kind": "evidence", "id": hit["id"], "score": hit.get("score", 0)}
               for hit in grounding_hits[:6]])
    return {
        "persona_id": persona["id"], "project_id": project_id, "as_of": as_of,
        "level": level, "ready": ready, "global_readiness": global_readiness,
        "task_signals": {"memory_hits": len(relevant_hits),
                         "grounding_hits": len(grounding_hits)},
        "capability": {"required": required_capability, "ok": capability_ok,
                       "profile": caps},
        "project_cohort_member": in_project, "limitations": limitations,
        "refs": refs, "recall": {**recall, "hits": relevant_hits[:6]},
        "grounding_hits": grounding_hits[:6],
        "next_action": ("prepare_persona_for_task" if ready else
                        global_readiness.get("next_action") or "deepen_persona"),
    }


def prepare_persona_for_task(persona_id: str, task: str, project_id: str | None = None,
                             as_of: str | None = None,
                             required_capability: str | None = None,
                             recent_events: int = 8,
                             store: Store | None = None) -> dict[str, Any]:
    """Freeze the exact persona context used for one assignment.

    The snapshot stores the effective SOUL, memory cutoff, loaded refs, capability
    profile and readiness limitations.  Re-opening it later never re-runs recall.
    """
    store = store or Store()
    persona = _require_persona(store, persona_id)
    readiness = persona_task_readiness(
        persona["id"], task, project_id, as_of, required_capability, store=store)
    context = prepare_persona_agent_context(  # noqa: F821 (bound)
        persona["id"], task, recent_events, as_of, store=store)
    events = store.list_experience_events(
        persona["id"], end=(f"{as_of}T23:59" if as_of else None))
    memory_cutoff = as_of or (events[-1]["timestamp"] if events else None)
    frozen = {
        "schema": "sonaloop.persona_context_snapshot.v1",
        "persona_id": persona["id"], "persona_version": persona.get("updated_at"),
        "project_id": project_id, "task": task, "as_of": as_of,
        "memory_cutoff": memory_cutoff, "embedding_space": memory_mod.embedding_space(),
        "required_capability": required_capability, "readiness": readiness,
        "loaded_refs": readiness["refs"], "agent_context": context["agent_context"],
        "recent_event_ids": context["recent_event_ids"], "soul_path": context["soul_path"],
    }
    canonical = json.dumps(frozen, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode()).hexdigest()
    snapshot = {"id": f"pctx_{digest[:20]}", **frozen, "context_sha256": digest,
                "created_at": utc_now_iso()}
    store.insert_persona_context_snapshot(snapshot)
    snapshot = store.get_persona_context_snapshot(snapshot["id"]) or snapshot
    from ..telemetry import capture_product_event
    capture_product_event(
        "persona_context_prepared", project_id=project_id or "",
        subject_kind="persona", subject_id=persona["id"],
        properties={"readiness_level": readiness["level"],
                    "memory_hits": readiness["task_signals"]["memory_hits"],
                    "grounding_hits": readiness["task_signals"]["grounding_hits"],
                    "has_as_of": bool(as_of), "has_capability_gate": bool(required_capability)},
        idempotency_key=snapshot["id"],
    )
    return snapshot


def get_persona_context_snapshot(snapshot_id: str,
                                 store: Store | None = None) -> dict[str, Any]:
    store = store or Store()
    snapshot = store.get_persona_context_snapshot(snapshot_id)
    if not snapshot:
        raise KeyError(f"Unknown persona context snapshot: {snapshot_id}")
    return snapshot


def list_persona_context_snapshots(persona_id: str,
                                   store: Store | None = None) -> list[dict[str, Any]]:
    store = store or Store()
    persona = _require_persona(store, persona_id)
    return [{key: row.get(key) for key in (
        "id", "persona_id", "persona_version", "project_id", "as_of", "memory_cutoff",
        "required_capability", "context_sha256", "created_at")}
        | {"readiness_level": (row.get("readiness") or {}).get("level")}
        for row in store.list_persona_context_snapshots(persona["id"])]


def _build_dispatch(build: dict[str, Any], store: Store) -> dict[str, Any]:
    pid = build["persona_id"]
    readiness = persona_readiness(pid, store=store)  # noqa: F821 (bound)
    gaps = set(readiness["gaps"])
    if "profile_specificity" in gaps:
        return {"kind": "profile", "tool": "preview_persona_update",
                "purpose": "author a concrete profile patch, preview it, then update_persona",
                "params": {"persona_id": pid}}
    if "claim_level_grounding" in gaps:
        persona = store.get_persona(pid) or {}
        corpus_ids = list((persona.get("grounding") or {}).get("corpus_ids") or [])
        return ({"kind": "grounding", "tool": "brief_grounding",
                 "purpose": "ground load-bearing persona claims in exact corpus chunks",
                 "params": {"persona_id": pid, "corpus_ids": corpus_ids}}
                if corpus_ids else
                {"kind": "blocked", "tool": "ingest_corpus",
                 "purpose": "attach independent real material before persona memory is trusted",
                 "params": {"persona_id": pid},
                 "blocking_reason": "no grounding corpus exists yet"})
    if "authored_capabilities" in gaps:
        return {"kind": "capability", "tool": "suggest_tech_comfort",
                "purpose": "choose and persist an authored capability profile",
                "params": {"persona_id": pid}}

    start, end = build["window"]["start"], build["window"]["end"]
    plan = store.find_covering_plan(pid, "month", start) or store.find_covering_plan(pid, "month", end)
    if not plan:
        return {"kind": "period", "tool": "brief_period",
                "purpose": "author the ordinary baseline and representative sample days",
                "params": {"persona_id": pid, "scope": "month", "date": end}}
    sample_days = [d for d in (plan.get("sample_days") or []) if start <= d <= end]
    if not sample_days:
        return {"kind": "period", "tool": "brief_period",
                "purpose": "the stored period has no representative sample_days; revise it",
                "params": {"persona_id": pid, "scope": "month", "date": end}}
    summaries = {s["date"] for s in store.list_daily_summaries(pid, start, end)}
    for day in sample_days:
        if day not in summaries:
            return {"kind": "day", "tool": "brief_day",
                    "purpose": "author and record this representative lived day",
                    "params": {"persona_id": pid, "date": day}}
        day_facts = [f for f in store.list_persona_facts(pid) if f["t_valid"][:10] == day]
        if not day_facts:
            return {"kind": "consolidation", "tool": "brief_consolidation",
                    "purpose": "turn the recorded day into sourced durable memory",
                    "params": {"persona_id": pid, "date": day}}
    digest = next((d for d in reversed(store.list_digests(pid))
                   if d["period_start"] <= end and d["period_end"] >= start), None)
    if not digest:
        return {"kind": "digest", "tool": "brief_digest",
                "purpose": "capture the period arc after all sampled days are consolidated",
                "params": {"persona_id": pid, "scope": "month", "date": end}}
    critics = [r for r in store.list_eval_reports(pid) if r.get("kind") == "llm_critic"
               and str(r.get("created_at") or "") >= build["created_at"]]
    if not critics or not critics[0].get("green"):
        return {"kind": "critic", "tool": "brief_eval_critic",
                "purpose": "author and record the semantic authenticity verdict",
                "params": {"persona_id": pid, "start": start, "end": end},
                "prior_failed": bool(critics)}
    if readiness["level"] != "ready":
        return {"kind": "review", "tool": readiness["next_action"],
                "purpose": "resolve the remaining readiness gate",
                "params": {"persona_id": pid}, "gaps": readiness["gaps"]}
    return {"kind": "done", "tool": "prepare_persona_for_task",
            "purpose": "persona baseline passed; prepare a frozen task-specific context",
            "params": {"persona_id": pid}}


def begin_persona_build(persona_id: str, operation_id: str, days: int = 28,
                        store: Store | None = None) -> dict[str, Any]:
    """Create or idempotently resume one governed persona-memory build."""
    store = store or Store()
    persona = _require_persona(store, persona_id)
    operation_id = str(operation_id or "").strip()
    if not operation_id:
        raise ValueError("begin_persona_build requires a stable operation_id")
    days = max(7, min(90, int(days)))
    existing = store.get_persona_build_by_operation(persona["id"], operation_id)
    if existing:
        if int(existing["window"]["days"]) != days:
            raise ValueError("operation_id was already used with a different persona-build payload")
        return {**existing, "created": False,
                "dispatch": _build_dispatch(existing, store)}
    end = date.today()
    start = end - timedelta(days=days - 1)
    now = utc_now_iso()
    build_id = "pbuild_" + hashlib.sha256(
        f"{persona['id']}|{operation_id}".encode()).hexdigest()[:20]
    build = {"schema": "sonaloop.persona_build.v1", "build_id": build_id,
             "persona_id": persona["id"], "operation_id": operation_id,
             "status": "active", "cursor": 0, "journal": [],
             "window": {"start": start.isoformat(), "end": end.isoformat(), "days": days},
             "created_at": now, "updated_at": now}
    store.upsert_persona_build(build)
    from ..telemetry import capture_product_event
    capture_product_event("persona_build_started", subject_kind="persona", subject_id=persona["id"],
                          properties={"days": days}, idempotency_key=build_id)
    return {**build, "created": True, "dispatch": _build_dispatch(build, store)}


def persona_build_step(build_id: str, store: Store | None = None) -> dict[str, Any]:
    """Re-assess durable state and advance one resumable persona build dispatch."""
    store = store or Store()
    build = store.get_persona_build(build_id)
    if not build:
        raise KeyError(f"Unknown persona build: {build_id}")
    dispatch = _build_dispatch(build, store)
    dispatch_key = hashlib.sha256(json.dumps(dispatch, sort_keys=True).encode()).hexdigest()[:16]
    if not build["journal"] or build["journal"][-1].get("dispatch_key") != dispatch_key:
        build["journal"].append({"cursor": len(build["journal"]), "dispatch_key": dispatch_key,
                                 "kind": dispatch["kind"], "tool": dispatch["tool"],
                                 "at": utc_now_iso()})
        build["cursor"] = len(build["journal"])
    if dispatch["kind"] == "done":
        build["status"] = "complete"
        build["completed_at"] = utc_now_iso()
    build["updated_at"] = utc_now_iso()
    store.upsert_persona_build(build)
    from ..telemetry import capture_product_event
    capture_product_event(
        "persona_build_completed" if build["status"] == "complete" else "persona_build_advanced",
        subject_kind="persona", subject_id=build["persona_id"],
        properties={"dispatch_kind": dispatch["kind"], "cursor": build["cursor"]},
        idempotency_key=f"{build_id}:{dispatch_key}:{build['status']}")
    return {**build, "dispatch": dispatch,
            "readiness": persona_readiness(build["persona_id"], store=store)}  # noqa: F821 (bound)


def get_persona_build(build_id: str, store: Store | None = None) -> dict[str, Any]:
    store = store or Store()
    build = store.get_persona_build(build_id)
    if not build:
        raise KeyError(f"Unknown persona build: {build_id}")
    return {**build, "dispatch": _build_dispatch(build, store),
            "readiness": persona_readiness(build["persona_id"], store=store)}  # noqa: F821 (bound)


def list_persona_builds(persona_id: str, store: Store | None = None) -> list[dict[str, Any]]:
    store = store or Store()
    persona = _require_persona(store, persona_id)
    return store.list_persona_builds(persona["id"])
