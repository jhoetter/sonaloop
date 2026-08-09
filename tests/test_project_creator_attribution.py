from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
import socket
from threading import Barrier
import threading
import time

import pytest
from fastapi.testclient import TestClient

from sonaloop import browser, config, services, web
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
    english_list = client.get("/jobs?lang=en").text
    german_list = client.get("/jobs?lang=de").text
    assert "Created by Alice &lt;Admin&gt;" in english
    assert "Erstellt von Alice &lt;Admin&gt;" in german
    assert "private-subject" not in english + german
    assert 'class="sl-project-creator"' not in legacy_html
    assert "Created by" not in legacy_html
    # The overview keeps attribution as a quiet second line, not another pill.
    assert 'class="row-byline">Created by Alice &lt;Admin&gt;</span>' in english_list
    assert 'class="row-byline">Erstellt von Alice &lt;Admin&gt;</span>' in german_list
    assert "private-subject" not in english_list + german_list
    legacy_row = english_list.split(f'href="/jobs/{legacy["id"]}"', 1)[1].split(
        'class="row"', 1,
    )[0]
    assert "row-byline" not in legacy_row and "Created by" not in legacy_row


@pytest.mark.skipif(not browser.available(), reason="chromium not installed")
def test_creator_byline_stays_visible_without_colliding_at_wide_and_narrow_widths(store):
    actor = _actor("layout-private-subject", "Johannes Hötter", channel="mcp")
    project = _start_as(actor, operation_id="creator:layout:1", store=store)

    import uvicorn
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(
        web.create_app(), host="127.0.0.1", port=port, log_level="error",
    ))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 15
    while not server.started:
        assert time.time() < deadline, "app did not boot"
        time.sleep(0.05)

    from playwright.sync_api import sync_playwright
    try:
        with sync_playwright() as playwright:
            chromium = playwright.chromium.launch()
            for width in (1440, 640):
                page = chromium.new_context(viewport={"width": width, "height": 900}).new_page()
                page.goto(f"http://127.0.0.1:{port}/jobs?lang=en", wait_until="load")
                row = page.locator(f'a.row[href="/jobs/{project["id"]}"]')
                byline = row.locator(".row-byline")
                assert byline.is_visible()
                assert byline.inner_text() == "Created by Johannes Hötter"
                geometry = row.evaluate("""el => {
                  const box = n => { const r=n.getBoundingClientRect(); return {
                    left:r.left,right:r.right,top:r.top,bottom:r.bottom,width:r.width,height:r.height}; };
                  return {row:box(el), title:box(el.querySelector('.title')),
                    right:box(el.querySelector('.right')), byline:box(el.querySelector('.row-byline')),
                    viewport:document.documentElement.clientWidth,
                    overflow:document.documentElement.scrollWidth};
                }""")
                assert geometry["byline"]["left"] >= geometry["title"]["left"]
                assert geometry["byline"]["bottom"] <= geometry["row"]["bottom"] + 1
                assert geometry["right"]["right"] <= geometry["row"]["right"] + 1
                assert geometry["overflow"] <= geometry["viewport"]
                if width == 1440:
                    assert geometry["title"]["right"] <= geometry["right"]["left"] + 1
                else:
                    assert geometry["right"]["top"] >= geometry["title"]["bottom"] - 1
                page.context.close()
            chromium.close()
    finally:
        server.should_exit = True
        thread.join(timeout=10)
