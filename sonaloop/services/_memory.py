"""Memory retrieval / inspection / evaluation / embeddings / forgetting.

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



def recall_memory(persona_id: str, query: str, as_of: str | None = None, k: int = 8, store: Store | None = None) -> dict[str, Any]:
    store = store or Store()
    persona = _require_persona(store, persona_id)
    return memory_mod.recall(store, persona["id"], query, as_of=as_of, k=k)



def list_active_projects(persona_id: str, store: Store | None = None) -> list[dict[str, Any]]:
    store = store or Store()
    persona = _require_persona(store, persona_id)
    return memory_mod.list_active_projects(store, persona["id"])



def get_project(persona_id: str, entity_id: str, as_of: str | None = None, store: Store | None = None) -> dict[str, Any]:
    store = store or Store()
    persona = _require_persona(store, persona_id)
    return memory_mod.get_project_timeline(store, persona["id"], entity_id, as_of=as_of)



def get_state_at(persona_id: str, as_of: str, store: Store | None = None) -> dict[str, Any]:
    store = store or Store()
    persona = _require_persona(store, persona_id)
    return memory_mod.get_state_at(store, persona["id"], _parse_date(as_of).isoformat())



# Output-budget caps (ticket mcp-output-budget-audit): months of lived memory make
# the unwindowed timeline arbitrarily large; the newest rows are kept and the
# in-band note names the params that return the rest. Raise per call if needed.
TIMELINE_MAX_FACTS = 100
TIMELINE_MAX_EVENTS = 200


def get_timeline(persona_id: str, start: str | None = None, end: str | None = None,
                 entity_id: str | None = None, store: Store | None = None,
                 max_facts: int = TIMELINE_MAX_FACTS,
                 max_events: int = TIMELINE_MAX_EVENTS) -> dict[str, Any]:
    """Facts + experience events on one persona's timeline. Both lists are sorted
    oldest→newest and capped to the NEWEST `max_facts`/`max_events` rows;
    `facts_total`/`events_total` always count the whole (windowed) set and a `note`
    appears whenever a cap trims — never a silent truncation. Narrow with
    `start`/`end`/`entity_id`, or raise the caps explicitly."""
    store = store or Store()
    persona = _require_persona(store, persona_id)
    pid = persona["id"]
    if entity_id:
        facts = store.list_entity_facts(entity_id)
    else:
        facts = store.list_persona_facts(pid)
    if start:
        facts = [f for f in facts if f["t_valid"][:10] >= start]
    if end:
        facts = [f for f in facts if f["t_valid"][:10] <= end]
    events = store.list_experience_events(pid, start, end)
    facts_total, events_total = len(facts), len(events)
    out = {"persona_id": pid, "start": start, "end": end,
           "facts_total": facts_total, "events_total": events_total}
    trimmed = []
    if max_facts and facts_total > max_facts:
        facts = facts[-max_facts:]               # t_valid-ordered: keep the newest
        trimmed.append(f"facts to the newest {max_facts} of {facts_total}")
    if max_events and events_total > max_events:
        events = events[-max_events:]            # timestamp-ordered: keep the newest
        trimmed.append(f"events to the newest {max_events} of {events_total}")
    if trimmed:
        out["note"] = (f"trimmed {' and '.join(trimmed)} — narrow with start/end/entity_id "
                       f"or raise max_facts/max_events for more.")
    out["facts"] = facts
    out["events"] = [{"timestamp": e["timestamp"], "task": e["task"],
                      "event_type": e["event_type"]} for e in events]
    return out



def search_entities(persona_id: str, kind: str | None = None, name: str | None = None, store: Store | None = None) -> list[dict[str, Any]]:
    store = store or Store()
    persona = _require_persona(store, persona_id)
    ents = store.list_entities(persona["id"], kind)
    if name:
        n = memory_mod.normalize_name(name)
        ents = [e for e in ents if n in memory_mod.normalize_name(e["name"]) or n in memory_mod.normalize_name(" ".join(e.get("aliases", [])))]
    return ents



def get_open_loops(persona_id: str, status: str | None = "open", store: Store | None = None) -> list[dict[str, Any]]:
    store = store or Store()
    persona = _require_persona(store, persona_id)
    return store.list_threads(persona["id"], status)



def resolve_entity(persona_id: str, mention: str, kind: str | None = None, store: Store | None = None) -> dict[str, Any] | None:
    store = store or Store()
    persona = _require_persona(store, persona_id)
    return memory_mod.resolve_entity(store, persona["id"], mention, kind)



def list_memory_anomalies(persona_id: str | None = None, store: Store | None = None) -> list[dict[str, Any]]:
    store = store or Store()
    return store.list_anomalies(persona_id)



def get_persona_memory(persona_id: str, store: Store | None = None) -> dict[str, Any]:
    store = store or Store()
    persona = _require_persona(store, persona_id)
    content = memory_mod.render_memory_md(store, persona)
    path = memory_path(persona)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return {"path": runtime_path_ref(path), "content": content}


# ---- Evaluation (§12.5) & embeddings/forgetting (§12.6) ------------------



def evaluate_simulation(persona_id: str | None = None, start: str | None = None, end: str | None = None, store: Store | None = None, persist: bool = True) -> dict[str, Any]:
    store = store or Store()
    period = {"start": start, "end": end} if (start or end) else None
    return evaluation_mod.evaluate_simulation(persona_id, period, store=store, persist=persist)



def evaluate_cohort_diversity(persona_ids: list[str] | None = None, store: Store | None = None, persist: bool = True) -> dict[str, Any]:
    """Structural bulk-generation gate: flag near-duplicate personas + uniform cohorts."""
    store = store or Store()
    resolved = [_require_persona(store, pid)["id"] for pid in persona_ids] if persona_ids else None
    return evaluation_mod.evaluate_cohort_diversity(resolved, store=store, persist=persist)



def backfill_embeddings(persona_id: str | None = None, store: Store | None = None) -> dict[str, Any]:
    store = store or Store()
    personas = [store.get_persona(persona_id)] if persona_id else store.list_personas()
    out = {}
    for p in [x for x in personas if x]:
        out[p["slug"]] = memory_mod.backfill_persona_embeddings(store, p["id"])
    return out



def prune_memory(persona_id: str, keep_days: int = 120, as_of: str | None = None, store: Store | None = None) -> dict[str, Any]:
    """Salience-based forgetting (§12.6): archive old, low-salience episodes.

    Archived episodes leave active keyword *and* semantic recall while their raw
    audit/timeline record remains intact.  Entity-linked episodes and open loops are
    retained.  This is reversible through ``restore_memory_episode``.
    """
    store = store or Store()
    persona = _require_persona(store, persona_id)
    pid = persona["id"]
    ref = _parse_date(as_of).isoformat() if as_of else max(
        [e["timestamp"][:10] for e in store.list_experience_events(pid)] or [utc_now_iso()[:10]])
    cutoff = (date.fromisoformat(ref) - timedelta(days=keep_days)).isoformat()
    linked = set()
    for ent in store.list_entities(pid):
        linked.update(store.list_entity_events(ent["id"]))
    archived = 0
    archived_at = utc_now_iso()
    for e in store.list_experience_events(pid):
        if (e["timestamp"][:10] < cutoff and e["id"] not in linked and not e.get("open_loops")
                and e.get("memory_state") != "archived"):
            if store.has_embedding("event", e["id"]):
                store.conn.execute("DELETE FROM embeddings WHERE obj_type='event' AND obj_id=?", (e["id"],))
            store.set_experience_event_memory_state(e["id"], "archived", archived_at)
            archived += 1
    store.commit()
    return {"persona_id": pid, "cutoff": cutoff, "archived_events": archived,
            "raw_events_retained": True}


def restore_memory_episode(persona_id: str, event_id: str,
                           store: Store | None = None) -> dict[str, Any]:
    """Restore one archived episode to active recall and re-embed it when possible."""
    store = store or Store()
    persona = _require_persona(store, persona_id)
    event = store.get_experience_event(event_id)
    if not event or event.get("persona_id") != persona["id"]:
        raise KeyError(f"Unknown memory episode for persona: {event_id}")
    restored = store.set_experience_event_memory_state(event_id, "active")
    embedded = memory_mod.upsert_object_embedding(
        store, "event", event_id, persona["id"],
        f"{event.get('task','')}. {event.get('what_happened','')} {event.get('persona_thought','')}")
    store.commit()
    return {"persona_id": persona["id"], "event_id": event_id,
            "restored": restored, "embedded": embedded}


# ===================================================================== #
# F2 — LLM critic (semantic eval stage).                                #
# ===================================================================== #

# Default per-dimension critic threshold. The live value is resolved from
# config.critic_threshold() (env-tunable) at call time; this constant is kept as
# a documented default / backward-compatible reference.
