"""Memory-delta consolidation, digests, world context, persona revisions.

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



def brief_consolidation(persona_id: str, date_value: str | None = None, store: Store | None = None) -> dict[str, Any]:
    store = store or Store()
    persona = _require_persona(store, persona_id)
    day = _parse_date(date_value).isoformat()
    events = store.list_experience_events(persona["id"], f"{day}T00:00", f"{day}T23:59")
    activities = [{
        "title": e["task"], "event_type": e["event_type"], "tool": e.get("tool"),
        "participants": e.get("participants", []), "what_happened": e.get("what_happened"),
        "decision": e.get("decision"), "open_loops": e.get("open_loops", []),
    } for e in events]
    frame = {
        "persona_name": persona["display_name"], "persona_id": persona["id"], "date": day,
        "activities": activities,
        "known_entities": [{"name": en["name"], "kind": en["kind"], "status": en.get("status")}
                           for en in store.list_entities(persona["id"])],
        "open_threads": [t["text"] for t in store.list_threads(persona["id"], "open")],
        "anti_steering": _ANTI_STEERING,
    }
    return {"persona_id": persona["id"], "date": day, "schema": "memory_deltas",
            "instructions": build_consolidation_prompt(frame), "frame": frame,
            "activity_count": len(activities)}



def record_memory_deltas(persona_id: str, date_value: str, deltas: dict[str, Any], store: Store | None = None) -> dict[str, Any]:
    store = store or Store()
    persona = _require_persona(store, persona_id)
    pid = persona["id"]
    day = _parse_date(date_value).isoformat()
    now = utc_now_iso()
    payload = validate_memory_deltas_payload(deltas)
    mention_to_id: dict[str, str] = {}
    created = updated = 0

    def _register(eid: str, *mentions: str) -> None:
        for m in mentions:
            if m:
                mention_to_id[memory_mod.normalize_name(m)] = eid

    for e in payload["entities"]:
        existing = memory_mod.resolve_entity(store, pid, e["mention"], e["kind"])
        if existing:
            existing["status"] = e["status"] or existing.get("status")
            existing["aliases"] = sorted(set(existing.get("aliases", []) + e["aliases"]))
            existing["last_seen"] = day
            existing["updated_at"] = now
            store.upsert_entity(existing)
            _register(existing["id"], e["mention"], existing["name"], *e["aliases"])
            updated += 1
        else:
            eid = stable_id("ent", pid, e["kind"], memory_mod.normalize_name(e["mention"]))
            store.upsert_entity({
                "id": eid, "persona_id": pid, "kind": e["kind"], "name": e["mention"],
                "status": e["status"], "aliases": e["aliases"], "first_seen": day,
                "last_seen": day, "created_at": now, "updated_at": now,
            })
            _register(eid, e["mention"], *e["aliases"])
            created += 1

    def _eid(mention: str, kind: str = "topic") -> str:
        key = memory_mod.normalize_name(mention)
        if key in mention_to_id:
            return mention_to_id[key]
        existing = memory_mod.resolve_entity(store, pid, mention, None)
        if existing:
            _register(existing["id"], mention)
            return existing["id"]
        eid = stable_id("ent", pid, kind, key)
        store.upsert_entity({"id": eid, "persona_id": pid, "kind": kind, "name": mention, "status": None,
                             "aliases": [], "first_seen": day, "last_seen": day, "created_at": now, "updated_at": now})
        _register(eid, mention)
        return eid

    facts_written = 0
    events = store.list_experience_events(pid, f"{day}T00:00", f"{day}T23:59")
    by_title = {memory_mod.normalize_name(e["task"]): e for e in events}
    for f in payload["facts"]:
        eid = _eid(f["entity"], "project")
        valid_from = f["valid_from"] or day
        if f["invalidates"]:
            inv = memory_mod.normalize_name(f["invalidates"])
            for old in store.list_entity_facts(eid, valid_only=True):
                on = memory_mod.normalize_name(old["fact"])
                if on == inv or inv in on or on in inv:
                    store.invalidate_entity_fact(old["id"], valid_from)
        if f["status"]:
            ns = memory_mod.normalize_name(f["status"])
            for old in store.list_entity_facts(eid, valid_only=True):
                if old.get("status") and memory_mod.normalize_name(old["status"]) != ns:
                    store.invalidate_entity_fact(old["id"], valid_from)
        source_event = None
        if f.get("source_event_id"):
            candidate = store.get_experience_event(f["source_event_id"])
            if not candidate or candidate.get("persona_id") != pid:
                raise ValueError(f"Unknown source_event_id for this persona: {f['source_event_id']}")
            source_event = candidate
        elif f.get("source_activity_title"):
            source_event = by_title.get(memory_mod.normalize_name(f["source_activity_title"]))
            if not source_event:
                raise ValueError("source_activity_title does not match an activity on the "
                                 f"consolidated day: {f['source_activity_title']}")
        source_refs = list(f.get("source_refs") or [])
        if source_event and not any(ref.get("id") == source_event["id"] for ref in source_refs):
            source_refs.insert(0, {"kind": "event", "id": source_event["id"]})
        fid = stable_id("fact", eid, f["fact"], valid_from)
        store.insert_entity_fact({
            "id": fid, "persona_id": pid, "entity_id": eid, "fact": f["fact"], "status": f["status"],
            "t_valid": valid_from, "t_invalid": f["valid_to"], "importance": f["importance"],
            "source_event_id": source_event["id"] if source_event else None,
            "source_kind": f["source_kind"], "source_refs": source_refs,
            "confidence": f["confidence"], "review_status": f["review_status"],
            "created_at": now,
        })
        facts_written += 1
        if f["status"]:
            ent = store.get_entity(eid)
            ent["status"] = f["status"]
            ent["last_seen"] = day
            ent["updated_at"] = now
            store.upsert_entity(ent)

    threads_opened = threads_resolved = 0
    for t in payload["threads"]:
        teid = _eid(t["entity"]) if t["entity"] else None
        if t["action"] == "resolve":
            target = None
            ref = memory_mod.normalize_name(t["ref"] or t["text"])
            for th in store.list_threads(pid, "open"):
                tn = memory_mod.normalize_name(th["text"])
                if tn == ref or ref in tn or tn in ref:
                    target = th
                    break
            if target:
                target.update({"status": "resolved", "closed_on": day, "updated_at": now})
                store.upsert_thread(target)
                threads_resolved += 1
                continue
        tid = stable_id("thread", pid, t["text"])
        store.upsert_thread({
            "id": tid, "persona_id": pid, "entity_id": teid, "text": t["text"],
            "status": "resolved" if t["action"] == "resolve" else "open",
            "opened_on": day, "closed_on": day if t["action"] == "resolve" else None,
            "created_at": now, "updated_at": now,
        })
        threads_opened += 1

    links = 0
    for link in payload["event_links"]:
        ev = by_title.get(memory_mod.normalize_name(link["activity_title"]))
        if not ev:
            continue
        for m in link["entities"]:
            store.link_event_entity(ev["id"], _eid(m), pid)
            links += 1
    store.commit()
    emb = memory_mod.backfill_persona_embeddings(store, pid)
    return {"persona_id": pid, "date": day, "entities_created": created, "entities_updated": updated,
            "facts": facts_written, "threads_opened": threads_opened, "threads_resolved": threads_resolved,
            "event_links": links, "embeddings": emb}





# ---- Planning (Phase A, multi-resolution §4A) ----------------------------



def brief_digest(persona_id: str, scope: str, date_value: str | None = None, store: Store | None = None) -> dict[str, Any]:
    store = store or Store()
    persona = _require_persona(store, persona_id)
    scope = scope if scope in {"week", "month", "quarter", "year"} else "week"
    start, end = _scope_bounds(_parse_date(date_value), scope)
    summaries = store.list_daily_summaries(persona["id"], start.isoformat(), end.isoformat())
    frame = {
        "persona_name": persona["display_name"], "persona_id": persona["id"], "scope": scope,
        "period_start": start.isoformat(), "period_end": end.isoformat(),
        "daily_summaries": summaries,
        "active_projects": memory_mod.list_active_projects(store, persona["id"]),
        "valid_facts": [f["fact"] for f in store.list_persona_facts(persona["id"], valid_only=True)][:40],
        "open_threads": [t["text"] for t in store.list_threads(persona["id"], "open")],
        "anti_steering": _ANTI_STEERING,
    }
    return {"persona_id": persona["id"], "scope": scope, "period_start": start.isoformat(),
            "period_end": end.isoformat(), "schema": "digest",
            "instructions": build_digest_prompt(frame), "frame": frame}



def put_digest(persona_id: str, scope: str, date_value: str, digest: dict[str, Any], store: Store | None = None) -> dict[str, Any]:
    store = store or Store()
    persona = _require_persona(store, persona_id)
    scope = scope if scope in {"week", "month", "quarter", "year"} else "week"
    start, end = _scope_bounds(_parse_date(date_value), scope)
    payload = validate_digest_payload(digest)
    rec = {"id": stable_id("digest", persona["id"], scope, start.isoformat()), "persona_id": persona["id"],
           "scope": scope, "period_start": start.isoformat(), "period_end": end.isoformat(),
           "created_at": utc_now_iso(), **payload}
    store.upsert_digest(rec)
    store.commit()
    memory_mod.upsert_object_embedding(store, "digest", rec["id"], persona["id"], payload["text"])
    store.commit()
    return rec



def list_digests(persona_id: str, scope: str | None = None, store: Store | None = None) -> list[dict[str, Any]]:
    store = store or Store()
    persona = _require_persona(store, persona_id)
    return store.list_digests(persona["id"], scope)


# ---- World context (§12.3) -----------------------------------------------



def set_world_context(items: list[dict[str, Any]], store: Store | None = None) -> dict[str, Any]:
    store = store or Store()
    now = utc_now_iso()
    written = 0
    for it in items or []:
        if not str(it.get("fact", "")).strip() or not str(it.get("category", "")).strip():
            continue
        valid_from = str(it.get("valid_from", "")).strip()[:10] or now[:10]
        rec = {
            "id": stable_id("world", it["category"], it["fact"], valid_from),
            "category": str(it["category"]).strip()[:80], "fact": str(it["fact"]).strip()[:400],
            "t_valid": valid_from, "t_invalid": (str(it["valid_to"]).strip()[:10] if it.get("valid_to") else None),
            "relevance_tags": [str(x).strip()[:60] for x in (it.get("relevance_tags") or [])][:8],
            "created_at": now,
        }
        store.insert_world_context(rec)
        written += 1
    store.commit()
    return {"written": written}



def get_world_context(as_of: str | None = None, store: Store | None = None) -> list[dict[str, Any]]:
    store = store or Store()
    return store.list_world_context(as_of=as_of)


# ---- Persona evolution (§12.2) -------------------------------------------



def brief_persona_revision(persona_id: str, date_value: str | None = None, store: Store | None = None) -> dict[str, Any]:
    store = store or Store()
    persona = _require_persona(store, persona_id)
    eff = effective_persona(persona, store)
    as_of = _parse_date(date_value).isoformat()
    frame = {
        "persona_name": persona["display_name"], "persona_id": persona["id"], "as_of": as_of,
        "source_description": persona["source_description"],
        "current_goals": eff.get("goals"), "current_pains": eff.get("pain_points"),
        "current_tools": eff.get("tools"), "current_personality": eff.get("personality"),
        "recent_digests": [d.get("text") for d in store.list_digests(persona["id"])[-4:]],
        "valid_facts": [f["fact"] for f in store.list_persona_facts(persona["id"], valid_only=True)][:40],
        "anti_steering": _ANTI_STEERING,
    }
    return {"persona_id": persona["id"], "as_of": as_of, "schema": "persona_revision",
            "instructions": build_persona_revision_prompt(frame), "frame": frame}



def record_persona_revision(persona_id: str, revision: dict[str, Any], store: Store | None = None) -> dict[str, Any]:
    store = store or Store()
    persona = _require_persona(store, persona_id)
    payload = validate_persona_revision_payload(revision)
    valid_refs = {
        "fact": {f["id"] for f in store.list_persona_facts(persona["id"])},
        "digest": {d["id"] for d in store.list_digests(persona["id"])},
        "event": {e["id"] for e in store.list_experience_events(persona["id"])},
        "evidence": ({e["id"] for e in store.list_evidence(persona["id"])}
                     | {cid for claim in ((persona.get("grounding") or {}).get("claims") or [])
                        for cid in (claim.get("chunk_ids") or [])}),
    }
    for ref in payload["refs"]:
        if ref["kind"] not in valid_refs or ref["id"] not in valid_refs[ref["kind"]]:
            raise ValueError(f"Persona revision ref does not resolve for this persona: {ref}")
    eff_on = payload["effective_on"] or utc_now_iso()[:10]
    rec = {"id": stable_id("rev", persona["id"], eff_on, payload["rationale"][:40]),
           "persona_id": persona["id"], "effective_on": eff_on,
           "rationale": payload["rationale"], "changes": payload["changes"],
           "refs": payload["refs"], "created_at": utc_now_iso()}
    store.insert_persona_revision(rec)
    # re-render SOUL with the new effective identity
    persona["soul"] = write_soul(persona, store)
    persona["updated_at"] = utc_now_iso()
    store.upsert_persona(persona, reason="persona revision")
    store.commit()
    return rec



def list_persona_revisions(persona_id: str, store: Store | None = None) -> list[dict[str, Any]]:
    store = store or Store()
    persona = _require_persona(store, persona_id)
    return store.list_persona_revisions(persona["id"])


# ---- Retrieval / inspection (§5.2, §5.6) ---------------------------------
