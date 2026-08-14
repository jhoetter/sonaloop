"""Structural persona readiness, memory onboarding, and safe deletion preview."""
from __future__ import annotations

import hashlib
import hmac
import json
from datetime import date, timedelta
from typing import Any

from ..storage import Store


def persona_readiness(persona_id: str, store: Store | None = None) -> dict[str, Any]:
    """Explain whether profile, grounding and lived memory are structurally ready."""
    store = store or Store()
    persona = store.get_persona(persona_id)
    if not persona:
        raise KeyError(f"Unknown persona: {persona_id}")
    pid = persona["id"]
    memory = store.count_memory_for_personas([pid])
    events, facts = int(memory.get("events") or 0), int(memory.get("facts") or 0)
    evidence = len(store.list_evidence(pid))
    grounding = persona.get("grounding") or {}
    grounded_claims = len(grounding.get("claims") or [])
    grounding_corpora = len(set(grounding.get("corpus_ids") or []))
    summaries = len(store.list_daily_summaries(pid))
    reflections = len(store.list_reflections(pid))
    digests = len(store.list_digests(pid))
    critic_reports = [r for r in store.list_eval_reports(pid) if r.get("kind") == "llm_critic"]
    latest_critic = critic_reports[0] if critic_reports else None
    critic_green = bool(latest_critic and latest_critic.get("green"))
    critic_at = str((latest_critic or {}).get("created_at") or "")
    blocking_anomalies = [a for a in store.list_anomalies(pid)
                          if int(a.get("severity") or 0) >= 3
                          and (not critic_at or str(a.get("created_at") or "") >= critic_at)]
    relationships = len(persona.get("relationships") or [])
    specificity = [str((persona.get("personality") or {}).get(key) or "").strip()
                   for key in ("working_style", "communication_style", "risk_tolerance",
                               "character_notes")]
    profile_lists = sum(bool(persona.get(key)) for key in (
        "goals", "constraints", "pain_points", "success_criteria", "tools"))
    profile_score = min(25, profile_lists * 3 + min(5, relationships * 3)
                        + min(5, sum(len(value) >= 20 for value in specificity)))
    grounding_score = (15 if grounded_claims >= 2 and grounding_corpora >= 1 else
                       11 if grounded_claims == 1 else 5 if evidence else 0)
    memory_score = min(22, events * 2) + min(13, facts * 3)
    continuity_score = min(9, summaries * 3) + min(6, reflections * 3)
    capability_score = 10 if persona.get("capabilities") else 4
    score = min(100, profile_score + grounding_score + memory_score
                + continuity_score + capability_score)
    memory_level = "deep" if (
        events >= 8 and facts >= 4 and summaries >= 3 and reflections >= 1 and digests >= 1
    ) else (
        "developing" if events >= 4 or facts >= 2 or summaries >= 1 else "thin")
    level = "ready" if (
        score >= 75 and memory_level == "deep" and profile_score >= 20
        and grounded_claims >= 1 and bool(persona.get("capabilities"))
        and critic_green and not blocking_anomalies
    ) else (
        "developing" if score >= 40 or memory_level == "developing" else "thin")
    gaps: list[str] = []
    for missing, condition in (
        ("profile_specificity", profile_score < 20),
        ("claim_level_grounding", grounded_claims < 1),
        ("lived_events", events < 8), ("durable_facts", facts < 4),
        ("calendar_continuity", summaries < 3 or reflections < 1), ("period_digest", digests < 1),
        ("authored_capabilities", not persona.get("capabilities")),
        ("semantic_critic", not critic_green),
        ("unresolved_memory_anomalies", bool(blocking_anomalies))):
        if condition:
            gaps.append(missing)
    next_action = (
        "ready_for_research" if level == "ready" else
        "deepen_profile" if profile_score < 20 else
        "ground_claims" if not grounded_claims else
        "author_capabilities" if not persona.get("capabilities") else
        "simulate_and_consolidate" if memory_level != "deep" else
        "run_semantic_critic" if not critic_green else
        "resolve_memory_anomalies" if blocking_anomalies else
        "review_readiness_gaps"
    )
    return {
        "persona_id": pid, "level": level, "score": score, "memory_level": memory_level,
        "counts": {"events": events, "facts": facts, "evidence": evidence,
                   "grounded_claims": grounded_claims, "grounding_corpora": grounding_corpora,
                   "daily_summaries": summaries, "reflections": reflections,
                   "digests": digests, "blocking_anomalies": len(blocking_anomalies)},
        "dimensions": {"profile": profile_score, "grounding": grounding_score,
                       "memory": memory_score, "continuity": continuity_score,
                       "capabilities": capability_score},
        "critic": ({"green": bool(latest_critic.get("green")),
                    "created_at": latest_critic.get("created_at"),
                    "low_dimensions": latest_critic.get("low_dimensions") or []}
                   if latest_critic else None),
        "gaps": gaps,
        "next_action": next_action,
    }


def brief_persona_memory_onboarding(persona_id: str, days: int = 28,
                                    store: Store | None = None) -> dict[str, Any]:
    """Plan the host-authored sequence from static profile to critic-checked memory."""
    store = store or Store()
    persona = store.get_persona(persona_id)
    if not persona:
        raise KeyError(f"Unknown persona: {persona_id}")
    days = max(7, min(int(days), 90))
    end, start = date.today(), date.today() - timedelta(days=days - 1)
    readiness = persona_readiness(persona_id, store=store)
    first_tool = {
        "deepen_profile": "brief_persona_revision",
        "ground_claims": "brief_grounding",
        "author_capabilities": "update_persona",
        "run_semantic_critic": "brief_eval_critic",
    }.get(readiness["next_action"], "brief_period")
    return {
        "persona_id": persona["id"],
        "window": {"start": start.isoformat(), "end": end.isoformat(), "days": days},
        "readiness": readiness,
        "quality_contract": [
            "Use independent evidence when available; do not turn the product brief into persona memory.",
            "Plan ordinary routine, interruptions and hand-offs alongside exceptional moments.",
            "Simulate representative sampled days, then consolidate facts/entities/open loops after each day.",
            "Create a period digest and run the simulation critic before research use.",
            "Keep unresolved loops continuous across days and preserve skeptical/indifferent behavior.",
        ],
        "workflow": [
            {"step": 1, "tool": first_tool,
             "purpose": f'resolve the first structural gap: {readiness["next_action"]}'},
            {"step": 2, "tool": "brief_period", "purpose": "author a 4-week baseline and sample days"},
            {"step": 3, "tool": "put_period_plan", "purpose": "persist the host-authored baseline"},
            {"step": 4, "tool": "brief_day → record_day", "purpose": "author each representative lived day"},
            {"step": 5, "tool": "brief_consolidation → record_memory_deltas",
             "purpose": "turn days into durable entities, facts and open loops"},
            {"step": 6, "tool": "brief_digest → put_digest", "purpose": "capture the period arc"},
            {"step": 7, "tool": "brief_eval_critic → record_eval_critic",
             "purpose": "author and persist the semantic authenticity critic"},
            {"step": 8, "tool": "evaluate_simulation_full",
             "purpose": "combine structural and persisted semantic verdicts"},
            {"step": 9, "tool": "persona_readiness", "purpose": "verify every gate is current"},
        ],
        "next_recommended_tool": first_tool,
    }


def persona_deletion_impact(persona_id: str, store: Store | None = None) -> dict[str, Any]:
    """Read-only impact preview plus exact state-bound destructive token."""
    store = store or Store()
    persona = store.get_persona(persona_id)
    if not persona:
        raise KeyError(f"Unknown persona: {persona_id}")
    pid = persona["id"]
    projects = [p["id"] for p in store.list_research_projects()
                if pid in (p.get("persona_ids") or [])]
    active_runs = [run.get("run_id") or run.get("id") or "active"
                   for project_id in projects for run in store.list_runs(project_id)
                   if run.get("status") == "active"]
    councils = [row["id"] for row in store.list_council_sessions()
                if pid in (row.get("persona_ids") or [])]
    usability = store.list_usability_sessions(persona_id=pid)
    prototype = store.list_prototype_sessions(persona_id=pid)
    memory, evidence = store.count_memory_for_personas([pid]), len(store.list_evidence(pid))
    fingerprint = json.dumps({
        "id": pid, "updated_at": persona.get("updated_at"), "projects": projects,
        "active_runs": active_runs,
        "councils": councils, "usability": [x["id"] for x in usability],
        "prototype": [x["id"] for x in prototype], "memory": memory,
    }, sort_keys=True, separators=(",", ":"))
    token = "delete-persona:" + hashlib.sha256(fingerprint.encode()).hexdigest()[:24]
    return {
        "persona_id": pid, "display_name": persona.get("display_name", ""),
        "confirmation_token": token, "will_delete": {**memory, "evidence": evidence},
        "will_detach_from_projects": len(projects),
        "blocked_by_active_runs": len(active_runs),
        "historical_artifacts_preserved": {
            "councils": len(councils), "usability_sessions": len(usability),
            "prototype_sessions": len(prototype)},
        "warning": ((f"Deletion is blocked while {len(active_runs)} research run(s) are active. "
                     if active_runs else "")
                    + "Historical sessions and councils remain inspectable, but the persona profile, "
                    "SOUL and private lived memory are removed. Project cohorts are detached."),
    }


def delete_persona_confirmed(persona_id: str, confirmation_token: str,
                             store: Store | None = None) -> dict[str, Any]:
    """Delete only with the current token from persona_deletion_impact."""
    store = store or Store()
    preview = persona_deletion_impact(persona_id, store=store)
    if preview["blocked_by_active_runs"]:
        raise ValueError("Persona deletion is blocked while a linked research run is active.")
    if not confirmation_token or not hmac.compare_digest(
            confirmation_token, preview["confirmation_token"]):
        raise ValueError("Persona deletion requires the exact confirmation_token returned by "
                         "persona_deletion_impact for the persona's current state.")
    from ._personas import delete_persona
    return delete_persona(persona_id, store=store)
