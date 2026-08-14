from __future__ import annotations

import pytest

from sonaloop import memory, services
from sonaloop.config import utc_now_iso
from conftest import create_persona


def _event(pid: str, event_id: str, day: str, task: str = "Renewal review") -> dict:
    return {
        "id": event_id, "persona_id": pid, "timestamp": f"{day}T09:00:00",
        "event_type": "focus", "summary": task, "task": task, "tool": "E-Mail",
        "participants": [], "collaboration_mode": "solo", "what_happened": task,
        "conversation": [], "key_quotes": [], "actions_done": [],
        "artifacts_touched": [], "persona_thought": "I need the current status.",
        "decision": None, "open_loops": [], "impact": {}, "pain_points": [],
        "goal_refs": [], "calendar_event_id": None, "created_at": utc_now_iso(),
    }


def test_recall_excludes_superseded_facts_and_respects_as_of(store):
    pid = create_persona(store, "Mara")
    store.upsert_entity({"id": "ent_contract", "persona_id": pid, "kind": "project",
                         "name": "Renewal", "status": "signed", "aliases": [],
                         "first_seen": "2026-01-01", "last_seen": "2026-02-01",
                         "created_at": utc_now_iso(), "updated_at": utc_now_iso()})
    store.insert_entity_fact({"id": "fact_old", "persona_id": pid, "entity_id": "ent_contract",
                              "fact": "The renewal is still pending", "status": "pending",
                              "t_valid": "2026-01-01", "t_invalid": "2026-02-01",
                              "importance": 5, "source_event_id": None,
                              "source_kind": "derived_fact", "source_refs": [],
                              "confidence": .6, "review_status": "reviewed",
                              "created_at": utc_now_iso()})
    store.insert_entity_fact({"id": "fact_new", "persona_id": pid, "entity_id": "ent_contract",
                              "fact": "The renewal is signed", "status": "signed",
                              "t_valid": "2026-02-01", "t_invalid": None,
                              "importance": 5, "source_event_id": None,
                              "source_kind": "observed", "source_refs": [],
                              "confidence": .95, "review_status": "reviewed",
                              "created_at": utc_now_iso()})
    store.commit()

    current = services.recall_memory(pid, "renewal", store=store, k=10)["hits"]
    assert {hit["obj_id"] for hit in current if hit["obj_type"] == "fact"} == {"fact_new"}
    january = services.recall_memory(pid, "renewal", as_of="2026-01-15", store=store, k=10)["hits"]
    assert {hit["obj_id"] for hit in january if hit["obj_type"] == "fact"} == {"fact_old"}
    assert current[0].keys() >= {"recency", "importance", "source_kind", "source_refs",
                                 "confidence", "review_status"}


def test_consolidation_wires_fact_to_exact_source_event(store):
    pid = create_persona(store, "Lina")
    event = _event(pid, "evt_renewal", "2026-03-04")
    store.insert_experience_event(event)
    store.commit()
    out = services.record_memory_deltas(pid, "2026-03-04", {
        "entities": [{"mention": "Renewal", "kind": "project", "status": "pending"}],
        "facts": [{"entity": "Renewal", "fact": "Legal is reviewing the renewal",
                   "source_activity_title": "Renewal review", "source_kind": "simulated_episode",
                   "confidence": .65, "review_status": "unreviewed"}],
        "threads": [], "event_links": [],
    }, store=store)
    assert out["facts"] == 1
    fact = store.list_persona_facts(pid)[0]
    assert fact["source_event_id"] == event["id"]
    assert fact["source_refs"] == [{"kind": "event", "id": event["id"]}]


def test_backfill_persists_provider_qualified_embedding_space(store, monkeypatch):
    pid = create_persona(store, "Olli")
    store.insert_experience_event(_event(pid, "evt_embed", "2026-03-04"))
    store.commit()
    monkeypatch.setattr(memory, "embedding_space", lambda: "ollama:nomic-embed-text")
    monkeypatch.setattr(memory, "embed_texts", lambda texts: [[0.1, 0.2] for _ in texts])
    out = memory.backfill_persona_embeddings(store, pid)
    assert out["embedded"] >= 1
    assert store.get_embedding("event", "evt_embed")["model"] == "ollama:nomic-embed-text"


def test_prune_archives_but_retains_and_restore_reactivates(store):
    pid = create_persona(store, "Nora")
    store.insert_experience_event(_event(pid, "evt_old", "2025-01-01", "Old routine"))
    store.commit()
    result = services.prune_memory(pid, keep_days=30, as_of="2026-01-01", store=store)
    assert result["archived_events"] == 1
    assert store.get_experience_event("evt_old")["memory_state"] == "archived"
    assert not services.recall_memory(pid, "old routine", store=store)["hits"]
    restored = services.restore_memory_episode(pid, "evt_old", store=store)
    assert restored["restored"] is True
    assert services.recall_memory(pid, "old routine", store=store)["hits"]


def test_persona_update_preview_version_and_immutable_fields(store):
    pid = create_persona(store, "Safia")
    current = store.get_persona(pid)
    preview = services.preview_persona_update(
        pid, {"goals": ["Reduce hand-off delay"]}, current["updated_at"], store=store)
    assert preview["changed_fields"] == ["goals"]
    updated = services.update_persona(
        pid, {"goals": ["Reduce hand-off delay"]}, "grounded interview correction",
        current["updated_at"], store=store)
    assert updated["goals"] == ["Reduce hand-off delay"]
    with pytest.raises(ValueError, match="changed since"):
        services.update_persona(pid, {"goals": ["Stale"]}, "stale", current["updated_at"], store=store)
    with pytest.raises(ValueError, match="immutable"):
        services.preview_persona_update(pid, {"id": "other"}, store=store)


def test_identity_revision_requires_resolving_source_refs(store):
    pid = create_persona(store, "Imani")
    with pytest.raises(ValueError, match="source ref"):
        services.record_persona_revision(pid, {
            "rationale": "A pattern emerged", "effective_on": "2026-03-01",
            "changes": {"goals_add": ["Reduce support work"]},
        }, store=store)
    store.insert_experience_event(_event(pid, "evt_pattern", "2026-03-01"))
    store.commit()
    revision = services.record_persona_revision(pid, {
        "rationale": "The repeated support episode changed priorities",
        "effective_on": "2026-03-01", "refs": [{"kind": "event", "id": "evt_pattern"}],
        "changes": {"goals_add": ["Reduce support work"]},
    }, store=store)
    assert revision["refs"] == [{"kind": "event", "id": "evt_pattern"}]


def _make_ready(store, pid: str) -> None:
    current = store.get_persona(pid)
    services.update_persona(pid, {
        "personality": {
            "working_style": "Works from a written priority list and checks dependencies first.",
            "communication_style": "Uses short concrete sentences and asks for an owner and a date.",
            "risk_tolerance": "Accepts reversible trials but avoids unowned operational risk.",
            "character_notes": "Often pauses before committing and verifies what happens to existing work.",
        },
        "capabilities": {"rungs": {"see": True, "walk": True, "drive": False,
                                    "login": False},
                         "tech_comfort": 3, "devices": ["mobile"],
                         "accessibility": "", "provenance": "authored"},
    }, "prepare test persona", current["updated_at"], store=store)
    corpus = services.ingest_corpus(
        "In the mobile banking interview the participant repeatedly asked where pending "
        "payments and confirmation details would appear before approving a transfer.",
        "interview", "Mobile banking interview", store=store)
    chunk = store.list_corpus_chunks(corpus["id"])[0]
    services.record_grounding(
        pid, [corpus["id"]],
        [{"claim": "Checks confirmation details before approving transfers",
          "chunk_ids": [chunk["id"]]}], store=store)
    for idx in range(8):
        day = f"2026-03-{idx // 3 + 1:02d}"
        store.insert_experience_event(_event(
            pid, f"evt_ready_{idx}", day,
            "Review pending mobile banking transfer confirmation" if idx == 0 else f"Routine {idx}"))
    for idx in range(3):
        day = f"2026-03-{idx + 1:02d}"
        store.upsert_daily_summary({"id": f"sum_{idx}", "persona_id": pid, "date": day,
                                    "mood": "steady", "completed": ["routine"],
                                    "blockers": [], "open_loops": [], "pain_points": [],
                                    "notable_memories": [], "created_at": utc_now_iso()})
    store.insert_reflection({"id": "ref_ready", "persona_id": pid,
                             "period_start": "2026-03-01", "period_end": "2026-03-03",
                             "summary": "Normal work continued.", "themes": ["routine"],
                             "pain_points": [], "created_at": utc_now_iso()})
    store.upsert_entity({"id": "ent_ready", "persona_id": pid, "kind": "project",
                         "name": "Payments", "status": "active", "aliases": [],
                         "first_seen": "2026-03-01", "last_seen": "2026-03-03",
                         "created_at": utc_now_iso(), "updated_at": utc_now_iso()})
    for idx in range(4):
        store.insert_entity_fact({"id": f"fact_ready_{idx}", "persona_id": pid,
                                  "entity_id": "ent_ready",
                                  "fact": ("Pending transfer confirmation needs a final review"
                                           if idx == 0 else f"Routine fact {idx}"),
                                  "status": "active", "t_valid": f"2026-03-0{idx + 1}",
                                  "t_invalid": None, "importance": 4,
                                  "source_event_id": f"evt_ready_{idx}",
                                  "source_kind": "simulated_episode",
                                  "source_refs": [{"kind": "event", "id": f"evt_ready_{idx}"}],
                                  "confidence": .6, "review_status": "reviewed",
                                  "created_at": utc_now_iso()})
    store.upsert_digest({"id": "digest_ready", "persona_id": pid, "scope": "month",
                         "period_start": "2026-03-01", "period_end": "2026-03-31",
                         "text": "A normal month with careful review before payment approval.",
                         "themes": ["care"], "project_arcs": [], "trends": [],
                         "created_at": utc_now_iso()})
    store.insert_eval_report({"id": "critic_ready", "persona_id": pid,
                              "kind": "llm_critic", "period_start": "2026-03-01",
                              "period_end": "2026-03-31", "green": True, "threshold": 4,
                              "dimensions": {"anti_steering": 5, "in_character": 5},
                              "low_dimensions": [], "flagged_items": [],
                              "created_at": utc_now_iso()})
    store.commit()


def test_task_readiness_and_context_snapshot_are_specific_and_reproducible(store):
    pid = create_persona(store, "Talia")
    _make_ready(store, pid)
    readiness = services.persona_task_readiness(
        pid, "approve a pending mobile banking transfer", required_capability="walk", store=store)
    assert readiness["level"] == "ready"
    assert readiness["task_signals"]["memory_hits"] >= 1
    assert readiness["task_signals"]["grounding_hits"] >= 1
    blocked = services.persona_task_readiness(
        pid, "approve a pending mobile banking transfer", required_capability="drive", store=store)
    assert blocked["level"] != "ready"
    assert "capability_rung_unavailable:drive" in blocked["limitations"]

    first = services.prepare_persona_for_task(
        pid, "approve a pending mobile banking transfer", as_of="2026-03-03",
        required_capability="walk", store=store)
    second = services.prepare_persona_for_task(
        pid, "approve a pending mobile banking transfer", as_of="2026-03-03",
        required_capability="walk", store=store)
    assert first["id"] == second["id"]
    assert first["context_sha256"] == second["context_sha256"]
    assert services.get_persona_context_snapshot(first["id"], store=store) == first
    assert first["persona_version"] == store.get_persona(pid)["updated_at"]


def test_persona_build_is_idempotent_and_returns_state_derived_dispatch(store):
    pid = create_persona(store, "Build Persona")
    first = services.begin_persona_build(pid, "onboard-build-persona", days=28, store=store)
    again = services.begin_persona_build(pid, "onboard-build-persona", days=28, store=store)
    assert first["build_id"] == again["build_id"]
    assert first["created"] is True and again["created"] is False
    assert first["dispatch"]["tool"] == "preview_persona_update"
    stepped = services.persona_build_step(first["build_id"], store=store)
    assert stepped["status"] == "active"
    assert stepped["journal"][-1]["tool"] == "preview_persona_update"
    with pytest.raises(ValueError, match="different persona-build payload"):
        services.begin_persona_build(pid, "onboard-build-persona", days=60, store=store)


def test_historical_context_does_not_read_future_event_or_revision(store):
    pid = create_persona(store, "Historical")
    store.insert_experience_event(_event(pid, "evt_past", "2026-01-01", "Past work"))
    store.insert_experience_event(_event(pid, "evt_future", "2026-04-01", "Future work"))
    store.commit()
    services.record_persona_revision(pid, {
        "rationale": "A later observed event changed priorities", "effective_on": "2026-04-01",
        "refs": [{"kind": "event", "id": "evt_future"}],
        "changes": {"goals_add": ["Future-only goal"]},
    }, store=store)
    context = services.prepare_persona_agent_context(
        pid, "What are you working on?", as_of="2026-02-01", store=store)
    assert context["recent_event_ids"] == ["evt_past"]
    assert "Future-only goal" not in context["agent_context"]
    assert "Future work" not in context["agent_context"]
