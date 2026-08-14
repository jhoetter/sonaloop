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
