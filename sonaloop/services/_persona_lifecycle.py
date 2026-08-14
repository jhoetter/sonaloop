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


_ANALYST_REGISTER_SIGNALS = (
    "findability problem", "information architecture", "cognitive load",
    "progressive disclosure", "top task", "top-task", "usability heuristic",
)
_VOICE_DIMENSIONS = ("authenticity", "register_match", "knowledge_grounding",
                     "attribution_separation")


def validate_persona_output(persona_id: str, text: str,
                            context_snapshot_id: str | None = None,
                            field_kind: str = "persona_quote",
                            store: Store | None = None) -> dict[str, Any]:
    """Gather a semantic voice-check assignment plus deterministic warning signals.

    The host authors the semantic verdict; the server never pretends a keyword scan
    proves authenticity.  Persist the verdict with ``record_persona_voice_check``.
    """
    store = store or Store()
    persona = _require_persona(store, persona_id)
    text = str(text or "").strip()
    if not text:
        raise ValueError("persona output validation requires non-empty text")
    if len(text) > 8_000:
        raise ValueError("persona output validation is limited to 8,000 characters")
    if context_snapshot_id:
        snapshot = store.get_persona_context_snapshot(context_snapshot_id)
        if not snapshot or snapshot.get("persona_id") != persona["id"]:
            raise ValueError("context snapshot does not belong to this persona")
        context = snapshot["agent_context"]
    else:
        context = prepare_persona_agent_context(  # noqa: F821 (bound)
            persona["id"], "Validate whether this wording is authentic", store=store)["agent_context"]
    low = text.casefold()
    signals = [{"kind": "analyst_register", "phrase": phrase}
               for phrase in _ANALYST_REGISTER_SIGNALS if phrase in low]
    digest = hashlib.sha256(text.encode()).hexdigest()
    return {
        "schema": "sonaloop.persona_voice_check.v1", "persona_id": persona["id"],
        "persona_version": persona.get("updated_at"),
        "context_snapshot_id": context_snapshot_id, "field_kind": str(field_kind)[:40],
        "text": text, "text_sha256": digest, "deterministic_signals": signals,
        "requires_semantic_verdict": True,
        "agent_context": context,
        "instructions": (
            "Judge the candidate wording against the loaded persona, not generic good writing. "
            "Return a verdict object with integer 0..5 scores for authenticity, register_match, "
            "knowledge_grounding and attribution_separation; `issues` as [{kind, detail}]; "
            "`rewrite` only when needed. A persona is not a UX analyst: immediate partial thought "
            "is preferable to polished diagnosis. Deterministic signals are review prompts, not proof."
        ),
    }


def record_persona_voice_check(persona_id: str, text: str, verdict: dict[str, Any],
                               context_snapshot_id: str | None = None,
                               store: Store | None = None) -> dict[str, Any]:
    """Persist a content-minimal semantic voice verdict; raw candidate text is not stored."""
    store = store or Store()
    persona = _require_persona(store, persona_id)
    brief = validate_persona_output(persona["id"], text, context_snapshot_id, store=store)
    if not isinstance(verdict, dict):
        raise ValueError("voice verdict must be an object")
    scores: dict[str, int] = {}
    raw_scores = verdict.get("scores") or {}
    for dimension in _VOICE_DIMENSIONS:
        try:
            score = int(raw_scores.get(dimension))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"voice verdict score {dimension} must be an integer 0..5") from exc
        if not 0 <= score <= 5:
            raise ValueError(f"voice verdict score {dimension} must be an integer 0..5")
        scores[dimension] = score
    issues = []
    for issue in verdict.get("issues") or []:
        if isinstance(issue, dict) and str(issue.get("detail") or "").strip():
            issues.append({"kind": str(issue.get("kind") or "other")[:40],
                           "detail": str(issue["detail"]).strip()[:500]})
    passed = all(value >= 4 for value in scores.values()) and not issues
    now = utc_now_iso()
    report = {"id": stable_id("voicecheck", persona["id"], brief["text_sha256"],
                              context_snapshot_id or brief.get("persona_version") or "current"),
              "persona_id": persona["id"], "kind": "persona_voice_check",
              "green": passed, "scores": scores, "issues": issues[:20],
              "rewrite": str(verdict.get("rewrite") or "").strip()[:2_000] or None,
              "text_sha256": brief["text_sha256"],
              "context_snapshot_id": context_snapshot_id,
              "deterministic_signals": brief["deterministic_signals"],
              "created_at": now}
    existing = next((item for item in store.list_eval_reports(persona["id"])
                     if item.get("id") == report["id"]), None)
    if existing:
        comparable = ("scores", "issues", "rewrite", "text_sha256", "context_snapshot_id")
        if any(existing.get(key) != report.get(key) for key in comparable):
            raise ValueError("this persona output/context was already checked with a different verdict")
        return existing
    store.insert_eval_report(report)
    store.commit()
    from ..telemetry import capture_product_event
    capture_product_event(
        "persona_voice_checked", subject_kind="persona", subject_id=persona["id"],
        properties={"passed": passed, "issue_count": len(issues),
                    "signal_count": len(brief["deterministic_signals"])},
        idempotency_key=report["id"])
    return report


def brief_memory_from_chat(persona_id: str, chat_id: str,
                           turn_indexes: list[int] | None = None,
                           store: Store | None = None) -> dict[str, Any]:
    """Gather exact chat turns for a proposed conversation-continuity memory.

    A generated reply is never independent evidence and this path cannot write
    identity revisions or durable facts.
    """
    store = store or Store()
    persona = _require_persona(store, persona_id)
    chat = store.get_persona_chat(chat_id)
    if not chat or chat.get("persona_id") != persona["id"]:
        raise KeyError(f"Unknown chat for persona: {chat_id}")
    indexes = sorted(set(int(i) for i in (turn_indexes if turn_indexes is not None
                                          else range(len(chat.get("turns") or [])))))
    turns = [turn for turn in chat.get("turns") or [] if int(turn.get("idx", -1)) in indexes]
    if not turns:
        raise ValueError("at least one existing chat turn is required")
    if len(turns) > 20:
        raise ValueError("one chat memory proposal is limited to 20 turns")
    return {
        "schema": "sonaloop.chat_memory_proposal.v1", "persona_id": persona["id"],
        "chat_id": chat_id, "turn_indexes": indexes, "turns": turns,
        "instructions": (
            "Author only cross-chat conversational continuity: {summary, continuity_notes:[...]}. "
            "Do not promote the persona's generated claims into evidence, lived episodes, profile "
            "traits or identity revisions. Then call record_memory_proposal; a human/host review "
            "must approve it before another chat may load it."
        ),
    }


def record_memory_proposal(persona_id: str, chat_id: str, turn_indexes: list[int],
                           proposal: dict[str, Any], store: Store | None = None) -> dict[str, Any]:
    """Persist one pending chat-continuity proposal without changing persona memory."""
    store = store or Store()
    brief = brief_memory_from_chat(persona_id, chat_id, turn_indexes, store=store)
    if not isinstance(proposal, dict):
        raise ValueError("memory proposal must be an object")
    summary = str(proposal.get("summary") or "").strip()
    notes = [str(note).strip()[:500] for note in (proposal.get("continuity_notes") or [])
             if str(note).strip()]
    if not summary or not notes:
        raise ValueError("memory proposal requires summary and continuity_notes")
    clean = {"summary": summary[:1_200], "continuity_notes": notes[:12]}
    pid = brief["persona_id"]
    canonical = json.dumps({"persona_id": pid, "chat_id": chat_id,
                            "turn_indexes": brief["turn_indexes"], "proposal": clean},
                           sort_keys=True, ensure_ascii=False)
    proposal_id = "memprop_" + hashlib.sha256(canonical.encode()).hexdigest()[:20]
    now = utc_now_iso()
    record = {"id": proposal_id, "schema": "sonaloop.persona_memory_proposal.v1",
              "persona_id": pid, "chat_id": chat_id,
              "turn_indexes": brief["turn_indexes"], "proposal": clean,
              "source_kind": "conversation", "source_refs": [
                  {"kind": "chat_turn", "id": f"{chat_id}:{idx}"}
                  for idx in brief["turn_indexes"]],
              "scope": "conversation_continuity_only", "status": "pending",
              "created_at": now, "updated_at": now}
    store.upsert_persona_memory_proposal(record)
    return record


def review_memory_proposal(proposal_id: str, decision: str, reason: str,
                           store: Store | None = None) -> dict[str, Any]:
    """Approve/reject conversation continuity; never writes facts or identity."""
    store = store or Store()
    record = store.get_persona_memory_proposal(proposal_id)
    if not record:
        raise KeyError(f"Unknown persona memory proposal: {proposal_id}")
    decision = str(decision or "").strip().lower()
    if decision not in {"approve", "reject"}:
        raise ValueError("memory proposal decision must be approve|reject")
    if record.get("status") != "pending":
        if record.get("decision") == decision:
            return record
        raise ValueError("memory proposal was already reviewed with a different decision")
    if not str(reason or "").strip():
        raise ValueError("memory proposal review requires a reason")
    record.update({"status": "approved" if decision == "approve" else "rejected",
                   "decision": decision, "review_reason": str(reason).strip()[:1_000],
                   "reviewed_at": utc_now_iso(), "updated_at": utc_now_iso()})
    store.upsert_persona_memory_proposal(record)
    from ..telemetry import capture_product_event
    capture_product_event(
        "persona_memory_proposal_reviewed", subject_kind="persona",
        subject_id=record["persona_id"],
        properties={"decision": decision, "turn_count": len(record["turn_indexes"])},
        idempotency_key=f"{proposal_id}:{decision}")
    return record


def get_memory_proposal(proposal_id: str, store: Store | None = None) -> dict[str, Any]:
    store = store or Store()
    record = store.get_persona_memory_proposal(proposal_id)
    if not record:
        raise KeyError(f"Unknown persona memory proposal: {proposal_id}")
    return record


def list_memory_proposals(persona_id: str, status: str | None = None,
                          store: Store | None = None) -> list[dict[str, Any]]:
    store = store or Store()
    persona = _require_persona(store, persona_id)
    if status and status not in {"pending", "approved", "rejected"}:
        raise ValueError("memory proposal status must be pending|approved|rejected")
    return store.list_persona_memory_proposals(persona["id"], status)
