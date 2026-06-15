"""F2 eval critic + cohort critic + F5 evidence check.

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



def _sample_activities(store: Store, persona_id: str, start: str | None, end: str | None, k: int) -> list[dict[str, Any]]:
    events = store.list_experience_events(persona_id, start, end)
    if not events:
        return []
    if len(events) > k:
        step = len(events) / k
        events = [events[int(i * step)] for i in range(k)]
    out = []
    for e in events:
        out.append({
            "ref_id": e["id"],
            "timestamp": e["timestamp"],
            "task": e["task"],
            "persona_thought": e.get("persona_thought"),
            "key_quotes": e.get("key_quotes", []),
            "conversation": e.get("conversation", [])[:3],
            "decision": e.get("decision"),
        })
    return out



def brief_eval_critic(persona_id: str, start: str | None = None, end: str | None = None, sample_k: int | None = None, store: Store | None = None) -> dict[str, Any]:
    store = store or Store()
    persona = _require_persona(store, persona_id)
    pid = persona["id"]
    k = sample_k if sample_k is not None else critic_sample_k()
    arcs = []
    for ent in store.list_entities(pid, "project"):
        facts = store.list_entity_facts(ent["id"])
        arcs.append({"entity_id": ent["id"], "name": ent["name"], "status": ent.get("status"),
                     "facts": [{"ref_id": f["id"], "t_valid": f["t_valid"], "status": f.get("status"), "fact": f["fact"]} for f in facts]})
    frame = {
        "persona_name": persona["display_name"], "persona_id": pid,
        "source_description": persona["source_description"],
        "soul": get_persona_soul(pid, store)["content"],
        "period": {"start": start, "end": end},
        "sample_k": k,
        "threshold": critic_threshold(),
        "sample_activities": _sample_activities(store, pid, start, end, k),
        "project_arcs": arcs,
        "digests": [{"scope": d["scope"], "period": d["period_start"], "text": d.get("text")} for d in store.list_digests(pid)],
    }
    return {"persona_id": pid, "schema": "eval_critic", "instructions": build_eval_critic_prompt(frame), "frame": frame}



def record_eval_critic(persona_id: str, verdict: dict[str, Any], start: str | None = None, end: str | None = None, store: Store | None = None) -> dict[str, Any]:
    store = store or Store()
    persona = _require_persona(store, persona_id)
    pid = persona["id"]
    now = utc_now_iso()
    payload = validate_eval_critic_payload(verdict)
    dims = payload["dimensions"]
    threshold = critic_threshold()
    low = sorted([d for d, v in dims.items() if v < threshold])
    green = not low
    report = {
        "id": stable_id("critic", pid, now), "persona_id": pid, "kind": "llm_critic",
        "period_start": start, "period_end": end, "green": green, "threshold": threshold,
        "dimensions": dims, "low_dimensions": low,
        "findings": payload["findings"], "flagged_items": payload["flagged_items"],
        "overall_note": payload["overall_note"], "created_at": now,
    }
    store.insert_eval_report(report)
    for d in low:
        store.insert_anomaly({"id": stable_id("anom", pid, "critic", d, now), "persona_id": pid,
                              "kind": f"critic:{d}", "severity": 3 if dims[d] <= 2 else 2,
                              "detail": f"{d}={dims[d]}/5", "created_at": now})
    for fi in payload["flagged_items"]:
        store.insert_anomaly({"id": stable_id("anom", pid, "critic-flag", fi["ref_id"], fi["issue"][:30]),
                              "persona_id": pid, "kind": f"critic_flag:{fi['dimension']}", "severity": fi["severity"],
                              "detail": fi["issue"], "ref_id": fi["ref_id"], "created_at": now})
    store.commit()
    return report



def latest_critic_report(persona_id: str, store: Store | None = None) -> dict[str, Any] | None:
    store = store or Store()
    persona = _require_persona(store, persona_id)
    crit = [r for r in store.list_eval_reports(persona["id"]) if r.get("kind") == "llm_critic"]
    return crit[0] if crit else None  # list_eval_reports is DESC by created_at



def evaluate_simulation_full(persona_id: str, start: str | None = None, end: str | None = None, store: Store | None = None) -> dict[str, Any]:
    """Combined 'top' verdict (definition v2): structural harness + latest LLM critic."""
    store = store or Store()
    structural = evaluate_simulation(persona_id, start, end, store=store)
    critic = latest_critic_report(persona_id, store=store)
    critic_green = bool(critic and critic.get("green"))
    top = structural["green"] and critic_green
    return {
        "persona_id": persona_id,
        "top": top,
        "structural": {"verdict": structural["verdict"], "green": structural["green"], "summary": structural["summary"]},
        "critic": None if not critic else {
            "green": critic["green"], "dimensions": critic["dimensions"],
            "low_dimensions": critic.get("low_dimensions", []), "flagged": len(critic.get("flagged_items", [])),
        },
        "note": ("top" if top else
                 "structural not green" if not structural["green"] else
                 "no critic run yet" if not critic else
                 f"critic below threshold: {', '.join(critic.get('low_dimensions', []))}"),
    }


# --- Cohort-wide critic (cross-persona outlier detection) --------------------



def _cohort_member_record(store: Store, persona: dict[str, Any]) -> dict[str, Any]:
    pid = persona["id"]
    crit = latest_critic_report(pid, store=store)
    quotes: list[str] = []
    for e in store.list_experience_events(pid)[-12:]:
        for q in (e.get("key_quotes") or []):
            if str(q).strip():
                quotes.append(str(q).strip()[:200])
    return {
        "persona_id": pid,
        "persona_name": persona["display_name"],
        "source_description": str(persona.get("source_description", ""))[:400],
        "segment": (persona.get("segment") or {}).get("customer_type"),
        "role": (persona.get("role") or {}).get("title"),
        "pain_points": (persona.get("pain_points") or [])[:4],
        "goals": (persona.get("goals") or [])[:3],
        "critic_dimensions": (crit or {}).get("dimensions"),
        "project_arcs": len(store.list_entities(pid, "project")),
        "sample_utterances": quotes[:3],
    }



def brief_cohort_critic(persona_ids: list[str] | None = None, start: str | None = None,
                        end: str | None = None, store: Store | None = None) -> dict[str, Any]:
    """GATHER compact per-persona records across the cohort so the host can judge
    which personas fall OUT of the cohort's range (relative outliers / clones)."""
    store = store or Store()
    if persona_ids:
        personas = [_require_persona(store, pid) for pid in persona_ids]
    else:
        personas = [p for p in store.list_personas() if p]
    if len(personas) < 2:
        return {"schema": "cohort_critic", "cohort_size": len(personas),
                "instructions": "Need >=2 personas for a cohort comparison.", "frame": {}}
    frame = {
        "period": {"start": start, "end": end},
        "cohort": [_cohort_member_record(store, p) for p in personas],
    }
    return {"schema": "cohort_critic", "cohort_size": len(personas),
            "persona_ids": [p["id"] for p in personas],
            "instructions": build_cohort_critic_prompt(frame), "frame": frame}



def record_cohort_critic(verdict: dict[str, Any], store: Store | None = None) -> dict[str, Any]:
    """Persist a host-authored cohort critique: eval_report (kind=cohort_critic) + an
    anomaly per flagged outlier persona."""
    store = store or Store()
    now = utc_now_iso()
    payload = validate_cohort_critic_payload(verdict)
    outliers = payload["outliers"]
    report = {
        "id": stable_id("cohortcritic", now), "persona_id": None, "kind": "cohort_critic",
        "green": len(outliers) == 0, "outliers": outliers,
        "cohort_note": payload["cohort_note"], "created_at": now,
    }
    store.insert_eval_report(report)
    for o in outliers:
        store.insert_anomaly({
            "id": stable_id("anom", "cohortcritic", o["persona_id"], o["dimension"], now),
            "persona_id": o["persona_id"], "kind": f"cohort_critic:{o['dimension']}",
            "severity": o["severity"], "detail": f"cohort outlier ({o['dimension']}): {o['reason']}",
            "created_at": now,
        })
    store.commit()
    return report


# ===================================================================== #
# F3 — Autonomous loop driver (in-package month bundle). roadmap F3.    #
# ===================================================================== #



def _evidence_for(store: Store, persona_id: str, limit: int = 8) -> list[dict[str, Any]]:
    out = []
    for ev in store.list_evidence(persona_id)[:limit]:
        out.append({"source_type": ev.get("source_type"), "notes": ev.get("notes"),
                    "content": str(ev.get("content_or_path", ""))[:1200]})
    return out



def brief_evidence_check(persona_id: str, store: Store | None = None) -> dict[str, Any]:
    store = store or Store()
    persona = _require_persona(store, persona_id)
    evidence = _evidence_for(store, persona["id"], limit=20)
    if not evidence:
        return {"persona_id": persona["id"], "schema": "evidence_check", "evidence_count": 0,
                "instructions": "No evidence attached. Use attach_evidence first.", "frame": {}}
    frame = {
        "persona_name": persona["display_name"], "persona_id": persona["id"],
        "claims": {"goals": persona.get("goals"), "pain_points": persona.get("pain_points"),
                   "tools": persona.get("tools"), "constraints": persona.get("constraints"),
                   "relationships": persona.get("relationships")},
        "evidence": evidence,
    }
    return {"persona_id": persona["id"], "schema": "evidence_check", "evidence_count": len(evidence),
            "instructions": build_evidence_check_prompt(frame), "frame": frame}



def record_evidence_check(persona_id: str, result: dict[str, Any], store: Store | None = None) -> dict[str, Any]:
    store = store or Store()
    persona = _require_persona(store, persona_id)
    pid = persona["id"]
    now = utc_now_iso()
    payload = validate_evidence_check_payload(result)
    report = {"id": stable_id("evcheck", pid, now), "persona_id": pid, "kind": "evidence_check",
              "green": len(payload["contradicted"]) == 0, **payload, "created_at": now}
    store.insert_eval_report(report)
    for c in payload["contradicted"]:
        store.insert_anomaly({"id": stable_id("anom", pid, "evidence", c["claim"][:40]), "persona_id": pid,
                              "kind": "evidence_contradiction", "severity": 3,
                              "detail": f"{c['claim']} — Evidenz: {c['evidence_says']}", "created_at": now})
    # provenance summary on the persona (evidence-backed vs assumption)
    persona.setdefault("provenance", {})["evidence_validation"] = {
        "confirmed": len(payload["confirmed"]), "contradicted": len(payload["contradicted"]),
        "unsupported": len(payload["unsupported"]), "checked_at": now,
    }
    persona["updated_at"] = now
    persona["soul"] = write_soul(persona, store)
    store.upsert_persona(persona, reason="evidence check")
    store.commit()
    return report


# ===================================================================== #
# Portable snapshot export of generated state → data/export/ (local-only)#
# (DB stays gitignored; this is the diffable, reproducible artifact).    #
# ===================================================================== #


# ===================== ESV §B — adversarial completeness / quality critic =====================
from ..config import suggestions_dir as _suggestions_dir  # noqa: E402


def _completeness_rubric() -> list[dict[str, Any]]:
    """The rubric dimensions + thresholds + probes (DATA: suggestions/critic_rubric.json)."""
    p = _suggestions_dir() / "critic_rubric.json"
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return []
    out = []
    for d in data.get("dimensions", []) or []:
        if d.get("key"):
            out.append({"key": d["key"], "threshold": int(d.get("threshold", 4)), "probe": d.get("probe", "")})
    return out


def _seg_label(p: dict[str, Any]) -> str:
    s = p.get("segment") or {}
    return str(s.get("einstellung") or s.get("lebensphase") or s.get("customer_type") or p.get("slug") or "")


def brief_completeness_critic(project_id: str, store: Store | None = None) -> dict[str, Any]:
    """GATHER a COMPUTED exhaustiveness snapshot (no LLM) for an INDEPENDENT critic subagent to judge:
    coverage, the generative `breadth_candidates` (segments/angles/concepts/risks/fidelity-rungs that
    are missing), novelty, groundedness, finish, and the rubric. The critic authors a verdict; the
    driver turns each `missing` item into real work and re-runs until dry (spec/ESV §B)."""
    store = store or Store()
    graph = get_project_graph(project_id, store=store)               # noqa: F821 (bound)
    plan = get_plan(project_id, store=store) or {"tasks": []}        # noqa: F821
    a = assess_project(project_id, store=store)                      # noqa: F821
    project = graph["project"]
    persona_ids = project.get("persona_ids", [])
    seg_pool: dict[str, list[str]] = {}
    for pid in persona_ids:
        p = store.get_persona(pid)
        if p:
            seg_pool.setdefault(_seg_label(p), []).append(pid)
    councils = [n for n in graph["nodes"] if str(n["study_id"]).startswith("council:")]
    engaged: set[str] = set()
    for n in councils:
        c = store.get_council_session(str(n["study_id"]).split(":", 1)[1]) or {}
        engaged.update(c.get("persona_ids", []))
    engaged_segments = {s for s, ps in seg_pool.items() if any(x in engaged for x in ps)}
    frame_tasks = [t for t in plan["tasks"] if t.get("capability") == "frame" and t.get("status") == "done"]
    acted_frames = {c for t in plan["tasks"] if t.get("bucket") == "act"
                    and any(r.get("kind") != "frame" for r in t.get("produces", [])) for c in t.get("consumes", [])}
    # Solution-idea notes (one note entity; the former 'concept'): identified by their structured `data`
    # (a lens/artifact_kind from ideation), not a separate kind. Raw observations carry no such data.
    concept_notes = [n for n in list_notes(project_id, store=store)  # noqa: F821
                     if (n.get("data") or {}).get("artifact_kind") or (n.get("data") or {}).get("lens")]
    risks = [o["text"] for o in store.list_open_questions(project_id) if o.get("status") == "open"]
    declared_fids: set[str] = set()
    for t in plan["tasks"]:
        for tg in (t.get("requires", {}) or {}).get("session_of_tags", []) or []:
            declared_fids.add(tg)
    present_fids = {(p.get("fidelity") or "") for p in graph.get("prototypes") or []}
    sessions = [x for x in store.list_prototype_sessions()
                if (store.get_prototype(x.get("prototype_id", "")) or {}).get("project_id") == project_id]
    frame = {
        "goal": project.get("goal", ""), "methodology": project.get("methodology", ""),
        "coverage": {"councils": len(councils),
                     "syntheses": sum(1 for n in graph["nodes"] if str(n["study_id"]).startswith("synthesis:")),
                     "prototypes": len(graph.get("prototypes") or []), "personas_engaged": len(engaged),
                     "personas_total": len(persona_ids), "segments_engaged": sorted(engaged_segments)},
        "breadth_candidates": {
            "segments_not_in_any_council": sorted(set(seg_pool) - engaged_segments),
            "frames_without_act": [t["id"] for t in frame_tasks if t["id"] not in acted_frames],
            "concepts_not_prototyped": [n.get("title") or n["id"] for n in concept_notes
                                        if not (n.get("data") or {}).get("prototype_id")],
            "risks_not_tested": risks[:10],
            "fidelity_rungs_missing": sorted(declared_fids - present_fids - {""})},
        "novelty": a.get("novelty", {}),
        "groundedness": {"sessions": len(sessions), "grounded": sum(1 for x in sessions if x.get("grounded_verified"))},
        "finish": a.get("finish", {}), "open_questions": risks[:10],
        "rubric": _completeness_rubric(),
    }
    instructions = (
        "Adversarially judge whether this design-research project is EXHAUSTIVE and finished. Score each "
        "rubric dimension 0-5 (>= its threshold to pass). Then list every concrete `missing` piece of work "
        "from breadth_candidates (and anything else you spot) as {kind, what, why, suggested_action} — "
        "kind ∈ {segment, angle, concept, risk, fidelity_rung, finish}. Be a skeptic: default to passed=false "
        "if ANY segment/angle/concept/risk is unexplored or the project isn't organized+concluded+handed-off. "
        "Then call record_completeness_critic(project_id, verdict). You CANNOT pass with non-empty missing.")
    return {"project_id": project_id, "schema": "completeness_critic", "frame": frame, "instructions": instructions}


def validate_completeness_verdict(verdict: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(verdict, dict):
        raise ValueError("completeness verdict must be a JSON object")
    rubric = {d["key"] for d in _completeness_rubric()}
    scores = {}
    for k, v in (verdict.get("scores") or {}).items():
        try:
            scores[str(k)[:60]] = max(0, min(5, int(v)))
        except Exception:
            continue
    missing = []
    for m in (verdict.get("missing") or [])[:50]:
        if not isinstance(m, dict) or not str(m.get("what", "")).strip():
            continue
        missing.append({"kind": str(m.get("kind", "")).strip()[:40], "what": str(m["what"]).strip()[:300],
                        "why": str(m.get("why", "")).strip()[:300],
                        "suggested_action": str(m.get("suggested_action", "")).strip()[:300]})
    thresholds = {d["key"]: d["threshold"] for d in _completeness_rubric()}
    rubric_ok = all(scores.get(k, 0) >= thr for k, thr in thresholds.items()) if thresholds else True
    passed = bool(verdict.get("passed")) and rubric_ok and not missing
    return {"scores": scores, "passed": passed, "missing": missing,
            "rationale": str(verdict.get("rationale", "")).strip()[:4000],
            "evidence_refs": [str(r).strip()[:80] for r in (verdict.get("evidence_refs") or []) if str(r).strip()][:50],
            "rubric_ok": rubric_ok}


def record_completeness_critic(project_id: str, verdict: dict[str, Any], store: Store | None = None) -> dict[str, Any]:
    """Persist an INDEPENDENT critic verdict. Honesty gate: a verdict cannot be `passed` while it still
    lists `missing` work OR while a rubric dimension is below threshold."""
    store = store or Store()
    project = _require_research_project(store, project_id)           # noqa: F821
    v = validate_completeness_verdict(verdict)
    if verdict.get("passed") and (v["missing"] or not v["rubric_ok"]):
        raise ValueError("completeness verdict cannot be passed=true while `missing` is non-empty or a "
                         "rubric dimension is below threshold (honesty: you can't pass with open gaps)")
    now = utc_now_iso()
    rec = {"id": stable_id("completeness", project["id"], now), "project_id": project["id"],  # noqa: F821
           "scores": v["scores"], "passed": v["passed"], "missing": v["missing"],
           "rationale": v["rationale"], "evidence_refs": v["evidence_refs"], "created_at": now}
    project.setdefault("critic_reports", []).append(rec)
    project["updated_at"] = now
    store.upsert_research_project(project)
    return rec


