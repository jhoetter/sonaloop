"""The queryable substrate: versioned paginated reads, the study result,
durable persona chat, and the access-guard seam (ticket queryable-substrate)."""
from __future__ import annotations

import pytest

from sonaloop import services
from sonaloop.services import _hooks, _substrate

from conftest import create_persona


@pytest.fixture(autouse=True)
def _clean_seams(monkeypatch):
    monkeypatch.setattr(_hooks, "_HANDLERS", {})
    monkeypatch.setattr(_hooks, "_ENTRY_POINTS_LOADED", True)
    monkeypatch.setattr(_substrate, "_ACCESS_GUARDS", [])
    yield


@pytest.fixture
def seeded(store):
    """Two personas, two projects, councils + a synthesis — a small queryable world."""
    p1 = create_persona(store, "Anna Architect")
    p2 = create_persona(store, "Bernd Builder")
    pr1 = services.start_project("Pricing study", "is the price right?", persona_ids=[p1], store=store)
    pr2 = services.start_project("Onboarding study", "where do users drop off?",
                                 persona_ids=[p1, p2], store=store)
    c1 = services.record_council(pr1["id"], "React to the price", [p1], store=store)
    c2 = services.record_council(pr2["id"], "Walk the onboarding", [p1, p2], store=store)
    syn = services.record_synthesis("Pricing answer", "is the price right?",
                                    council_ids=[c1["id"]], store=store)
    return {"personas": [p1, p2], "projects": [pr1, pr2], "councils": [c1, c2], "synthesis": syn}


def test_envelopes_are_versioned_and_paginated(store, seeded):
    out = services.query_projects(limit=1, store=store)
    assert out["substrate_version"] == _substrate.SUBSTRATE_VERSION
    assert out["total"] == 2 and len(out["items"]) == 1 and out["next_offset"] == 1
    page2 = services.query_projects(limit=1, offset=out["next_offset"], store=store)
    assert page2["items"][0]["id"] != out["items"][0]["id"] and page2["next_offset"] is None
    # stable ordering: same call, same order
    assert services.query_projects(store=store)["items"] == services.query_projects(store=store)["items"]


def test_query_filters(store, seeded):
    pr1, pr2 = seeded["projects"]
    p1, p2 = seeded["personas"]
    assert [r["id"] for r in services.query_projects(q="pricing", store=store)["items"]] == [pr1["id"]]
    only_p2 = services.query_councils(persona_id=p2, store=store)["items"]
    assert [r["id"] for r in only_p2] == [seeded["councils"][1]["id"]]
    by_project = services.query_councils(project_id=pr1["id"], store=store)["items"]
    assert [r["id"] for r in by_project] == [seeded["councils"][0]["id"]]
    assert services.query_syntheses(q="nonexistent-term", store=store)["total"] == 0
    future = "2999-01-01T00:00:00+00:00"
    assert services.query_projects(since=future, store=store)["total"] == 0
    assert services.query_personas(q="anna", store=store)["total"] == 1


def test_rows_are_lean_with_stable_ids(store, seeded):
    row = services.query_councils(store=store)["items"][0]
    assert set(row) == {"id", "project_id", "prompt", "persona_ids", "statements",
                        "votes", "questions", "created_at"}
    srow = services.query_syntheses(store=store)["items"][0]
    assert srow["id"] == seeded["synthesis"]["id"] and srow["council_ids"]


def test_study_result_is_the_automation_shape(store, seeded):
    pr1 = seeded["projects"][0]
    res = services.get_study_result(pr1["id"], store=store)
    assert res["substrate_version"] == _substrate.SUBSTRATE_VERSION
    assert res["project"]["id"] == pr1["id"] and res["project"]["councils"] == 1
    assert [c["id"] for c in res["councils"]] == [seeded["councils"][0]["id"]]
    assert isinstance(res["syntheses"], list) and "counts" in res
    with pytest.raises(KeyError):
        services.get_study_result("research_nope", store=store)


def test_chat_roundtrip_with_history(store, seeded):
    pid = seeded["personas"][0]
    brief = services.chat_with_persona(pid, "Would you pay 49€/month?", store=store)
    assert brief["schema"] == "persona_chat" and brief["turns"] == 0
    assert "agent_context" in brief and "record_chat_turn" in brief["instructions"]
    assert "PERSONA VOICE BOUNDARY" in brief["agent_context"]
    assert "PERSONA VOICE BOUNDARY" in brief["instructions"]
    chat_id = brief["chat_id"]
    out = services.record_chat_turn(pid, chat_id, "Would you pay 49€/month?",
                                    "Only if it replaces a tool I already pay for.", store=store)
    assert out["turns"] == 1
    cont = services.chat_with_persona(pid, "And at 29€?", chat_id=chat_id, store=store)
    assert cont["turns"] == 1 and "replaces a tool" in cont["history"]
    services.record_chat_turn(pid, chat_id, "And at 29€?", "That I would trial.", store=store)
    chat = services.get_chat(chat_id, store=store)
    assert [t["idx"] for t in chat["turns"]] == [0, 1]
    rows = services.list_chats(persona_id=pid, store=store)
    assert rows["total"] == 1 and rows["items"][0]["turns"] == 2


def test_chat_validation(store, seeded):
    p1, p2 = seeded["personas"]
    brief = services.chat_with_persona(p1, "hi", store=store)
    with pytest.raises(ValueError):        # chat belongs to p1
        services.chat_with_persona(p2, "hi", chat_id=brief["chat_id"], store=store)
    with pytest.raises(ValueError):        # empty reply
        services.record_chat_turn(p1, brief["chat_id"], "hi", "  ", store=store)
    with pytest.raises(KeyError):
        services.get_chat("chat_missing", store=store)


def test_chat_recorded_event_emitted(store, seeded):
    seen = []
    services.add_hook_handler("chat.recorded", seen.append)
    pid = seeded["personas"][0]
    brief = services.chat_with_persona(pid, "hello", store=store)
    services.record_chat_turn(pid, brief["chat_id"], "hello", "moin", store=store)
    assert seen and seen[0]["data"] == {"chat_id": brief["chat_id"], "persona_id": pid, "turns": 1}


def test_access_guard_seam_denies_and_allows(store, seeded):
    calls = []

    def guard(operation, resource):
        calls.append(operation)
        if operation == "get_study_result":
            raise PermissionError("workspace scope")

    services.register_access_guard(guard)
    services.query_projects(store=store)                       # allowed, but seen
    assert "query_projects" in calls
    with pytest.raises(PermissionError):
        services.get_study_result(seeded["projects"][0]["id"], store=store)
    _substrate.clear_access_guards()
    assert services.get_study_result(seeded["projects"][0]["id"], store=store)["project"]


def test_schema_is_documented_and_versioned():
    schema = services.substrate_schema()
    assert schema["substrate_version"] == _substrate.SUBSTRATE_VERSION
    assert {"persona", "project", "council", "synthesis", "chat"} <= set(schema["rows"])
    assert "auth_seam" in schema and "chat_flow" in schema


def test_limits_are_clamped(store, seeded):
    out = services.query_projects(limit=10_000, offset=-5, store=store)
    assert out["limit"] == _substrate._MAX_LIMIT and out["offset"] == 0
