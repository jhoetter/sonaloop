from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from fastapi.testclient import TestClient

from sonaloop import config, services, web
from sonaloop.mcp_server import build_server
from sonaloop.storage import Store


def _actor(actor_id: str, label: str, *, channel: str = "test") -> dict[str, str]:
    return {
        "schema": config.REQUEST_ACTOR_SCHEMA,
        "kind": "user",
        "id": actor_id,
        "label": label,
        "role": "member",
        "channel": channel,
        "captured_at": "2026-08-09T16:00:00+00:00",
    }


def _start_as(actor: dict[str, str], *, operation_id: str, store: Store) -> dict:
    token = config.set_request_actor(actor)
    try:
        return services.start_project(
            "Attributed study", "Who created this?", operation_id=operation_id, store=store,
        )
    finally:
        config.reset_request_actor(token)


def test_request_actor_context_is_normalized_copy_isolated_and_reset():
    supplied = _actor("subject-1", "Alice")
    supplied["ignored"] = "not part of the provider-neutral contract"
    token = config.set_request_actor(supplied)
    try:
        supplied["label"] = "Changed outside"
        current = config.current_request_actor()
        assert current == _actor("subject-1", "Alice")
        assert "ignored" not in current
        current["label"] = "Changed returned copy"
        assert config.current_request_actor()["label"] == "Alice"
    finally:
        config.reset_request_actor(token)
    assert config.current_request_actor() is None

    with pytest.raises(ValueError, match="kind"):
        config.set_request_actor({**_actor("subject-1", "Alice"), "kind": "provider-specific"})
    with pytest.raises(ValueError, match="label"):
        config.set_request_actor(_actor("subject-1", "x" * 161))
    with pytest.raises(ValueError, match="timezone"):
        config.set_request_actor({
            **_actor("subject-1", "Alice"), "captured_at": "2026-08-09T16:00:00",
        })


def test_first_creator_persists_across_replay_and_cannot_be_overwritten(store):
    alice = _actor("subject-alice", "Alice", channel="mcp")
    bob = _actor("subject-bob", "Bob", channel="web")
    first = _start_as(alice, operation_id="creator:create:1", store=store)
    replay = _start_as(bob, operation_id="creator:create:1", store=store)

    assert replay["id"] == first["id"]
    assert replay["idempotent_replay"] is True
    assert replay["created_by"] == alice
    assert store.get_research_project(first["id"])["created_by"] == alice

    # Structural patches never accept this field, and even an internal whole-row upsert cannot
    # replace the immutable snapshot or backfill it onto a legacy record.
    updated = services.update_research_project(
        first["id"], {"goal": "Updated goal", "created_by": bob}, store=store,
    )
    assert updated["created_by"] == alice
    attempted = dict(store.get_research_project(first["id"]))
    attempted["created_by"] = bob
    store.upsert_research_project(attempted)
    assert store.get_research_project(first["id"])["created_by"] == alice

    legacy = services.start_project("Legacy", "No actor", store=store)
    assert "created_by" not in legacy
    legacy_attempt = dict(store.get_research_project(legacy["id"]))
    legacy_attempt["created_by"] = bob
    store.upsert_research_project(legacy_attempt)
    assert "created_by" not in store.get_research_project(legacy["id"])


def test_concurrent_start_project_keeps_the_atomic_winner_creator():
    with Store():
        pass
    barrier = Barrier(2)
    actors = [_actor("subject-a", "Actor A"), _actor("subject-b", "Actor B")]

    def create(actor: dict[str, str]) -> dict:
        token = config.set_request_actor(actor)
        try:
            with Store() as thread_store:
                barrier.wait(timeout=10)
                return services.start_project(
                    "Racing attribution", "Same create intent",
                    operation_id="creator:race:1", store=thread_store,
                )
        finally:
            config.reset_request_actor(token)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [future.result() for future in [
            pool.submit(create, actors[0]), pool.submit(create, actors[1]),
        ]]

    assert results[0]["id"] == results[1]["id"]
    with Store() as check:
        persisted = check.get_research_project(results[0]["id"])
    assert persisted["created_by"] in actors
    assert all(result["created_by"] == persisted["created_by"] for result in results)
    assert sum(bool(result.get("idempotent_replay")) for result in results) == 1


def test_creator_is_not_model_controlled_and_ui_renders_only_a_label(store):
    tools = {tool.name: tool for tool in asyncio.run(build_server().list_tools())}
    for name in ("create_research_project", "start_project"):
        assert "created_by" not in tools[name].inputSchema["properties"]

    attributed = _start_as(
        _actor("private-subject", "Alice <Admin>", channel="mcp"),
        operation_id="creator:ui:1", store=store,
    )
    legacy = services.start_project("Legacy UI", "No attribution", store=store)
    client = TestClient(web.create_app())

    english = client.get(f"/jobs/{attributed['id']}?lang=en").text
    german = client.get(f"/jobs/{attributed['id']}?lang=de").text
    legacy_html = client.get(f"/jobs/{legacy['id']}?lang=en").text
    assert "Created by Alice &lt;Admin&gt;" in english
    assert "Erstellt von Alice &lt;Admin&gt;" in german
    assert "private-subject" not in english + german
    assert 'class="sl-project-creator"' not in legacy_html
    assert "Created by" not in legacy_html
