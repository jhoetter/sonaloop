"""Cross-process event bus + live inspector (ticket live-event-stream).

The contract under test: every lifecycle event lands as one capped `events` row
(written by the services-layer '*' subscriber, so ANY recording process feeds the
bus), the web SSE generator tails the table and replays from Last-Event-ID, and
the Activity page renders the feed. Append stays best-effort — a broken bus never
breaks recording.

The SSE generator is driven directly with a scripted request stub (one action per
poll, then disconnect) — an infinite stream through TestClient cannot be shut down
deterministically, the generator owns all the streaming logic anyway."""
from __future__ import annotations

import asyncio
import json

from starlette.testclient import TestClient

from sonaloop import services, web
from sonaloop.services import _events
from sonaloop.web._routes_api import _event_stream

from conftest import create_persona


class _Conn:
    """Request stub: the generator asks is_disconnected() once per poll loop — run one
    scripted action per poll (None = idle poll), disconnect when the script ends."""

    def __init__(self, *actions):
        self._actions = list(actions)

    async def is_disconnected(self) -> bool:
        if not self._actions:
            return True
        action = self._actions.pop(0)
        if action:
            action()
        return False


def _stream(last_id, *actions) -> list[str]:
    async def run():
        return [chunk async for chunk in _event_stream(_Conn(*actions), last_id)]
    return asyncio.run(run())


def _data_frames(chunks: list[str]) -> list[dict]:
    return [json.loads(line[len("data: "):])
            for chunk in chunks for line in chunk.splitlines() if line.startswith("data: ")]


# ---------------------------------------------------------------- the bus table


def test_lifecycle_events_append_bus_rows(store):
    pid = create_persona(store, "Bus Persona")
    project = services.start_project("Bus study", "does it land?", persona_ids=[pid], store=store)
    council = services.record_council(project["id"], "what changed?", [pid], store=store)
    rows = store.list_events_after(0)
    by_event = {r["event"]: r for r in rows}
    assert by_event["persona.created"]["entity_id"] == pid
    assert by_event["persona.created"]["data"]["url"] == f"/personas/{pid}"
    assert by_event["project.created"]["project_id"] == project["id"]
    crow = by_event["council.recorded"]
    assert crow["entity_id"] == council["id"] and crow["project_id"] == project["id"]
    assert crow["data"]["label"] == "what changed?"           # the toast/feed label
    assert crow["data"]["url"] == f'/councils/{council["id"]}'
    assert [r["id"] for r in rows] == sorted(r["id"] for r in rows) and rows[0]["ts"]


def test_bus_table_is_capped_keeping_the_newest(store):
    for i in range(25):
        store.append_event("2026-06-10T00:00:00+00:00", "council.recorded",
                           "council", f"c{i}", None, {}, cap=10)
    rows = store.list_events_after(0, limit=100)
    assert [r["entity_id"] for r in rows] == [f"c{i}" for i in range(15, 25)]
    assert store.latest_event_id() == 25                      # ids keep counting past the trim


def test_broken_bus_never_breaks_recording(store, monkeypatch):
    class Boom:
        def __init__(self):
            raise RuntimeError("bus down")
    monkeypatch.setattr(_events, "Store", Boom)
    pid = create_persona(store, "Resilient Recorder")        # must not raise
    assert pid and store.get_persona(pid) is not None        # the recording persisted
    assert store.list_events_after(0) == []                  # nothing landed, nothing broke


# ------------------------------------------------------------- the SSE endpoint


def test_sse_replays_from_last_event_id(store, monkeypatch):
    monkeypatch.setenv("SONALOOP_EVENTS_POLL", "0.01")
    pid = create_persona(store, "Streamed Persona")
    services.record_synthesis("Streamed answer", "goal", store=store)
    chunks = _stream(0, None)                                 # Last-Event-ID: 0 → full replay
    assert chunks[0] == ": connected\n\n"                     # immediate flush on connect
    frames = _data_frames(chunks)
    assert [f["event"] for f in frames] == ["persona.created", "synthesis.recorded"]
    assert frames[0]["entity_id"] == pid and frames[0]["url"] == f"/personas/{pid}"
    assert any(c.startswith(f'id: {frames[0]["id"]}\n') for c in chunks)   # reconnect cursor


def test_sse_tails_only_new_rows_without_last_event_id(store, monkeypatch):
    monkeypatch.setenv("SONALOOP_EVENTS_POLL", "0.01")
    create_persona(store, "Before Connect")                   # history — must NOT replay
    recorded: dict = {}

    def record_live():
        recorded.update(services.record_synthesis("After connect", "goal", store=store))

    frames = _data_frames(_stream(None, None, record_live, None))   # idle, record, drain
    assert [f["event"] for f in frames] == ["synthesis.recorded"]
    assert frames[0]["entity_id"] == recorded["id"]


def test_sse_sends_heartbeat_comments_when_idle(store, monkeypatch):
    monkeypatch.setenv("SONALOOP_EVENTS_POLL", "0.01")
    monkeypatch.setenv("SONALOOP_EVENTS_HEARTBEAT", "0")      # observe one immediately
    chunks = _stream(None, None, None)
    assert ": ping\n\n" in chunks and not _data_frames(chunks)


def test_sse_endpoint_is_registered():
    routes = {getattr(r, "path", "") for r in web.create_app().routes}
    assert "/api/events" in routes


# ------------------------------------------------------------ the activity page


def test_activity_page_renders_the_feed(store):
    pid = create_persona(store, "Feed Persona")
    services.record_synthesis("Feed answer", "goal", store=store)
    html = TestClient(web.create_app()).get("/activity?lang=en").text
    assert "Persona created" in html and "Report recorded" in html
    assert f'href="/personas/{pid}"' in html                  # rows link to the entity
    assert 'href="/activity"' in html                         # sidebar nav entry


def test_activity_page_empty_state(store):
    html = TestClient(web.create_app()).get("/activity?lang=en").text
    assert "No activity yet" in html
    # the lead is the one-sentence explainer (§9 V8): what this surface even is
    assert web.STRINGS["en"]["activity_lead"] in html


def test_activity_groups_events_per_run(store):
    """ux-contract §9 V8/G3: events recorded INSIDE a run (same project, timestamped within
    the run's interval) fold under one collapsible run header row (details/summary); events
    outside any run stay flat rows."""
    pid = create_persona(store, "Outside Run")                 # before any run → flat row
    proj = services.start_project("Run Group Proj", "frage?", methodology="double_diamond",
                                  persona_ids=[pid], store=store)
    services.start_run(proj["id"], store=store)
    services.record_council(proj["id"], "Inside the run?", [pid],
                            statements=[{"persona_id": pid, "text": "ja"}],
                            key="g3", store=store)             # during the run → grouped
    html = TestClient(web.create_app()).get("/activity?lang=en").text
    # ONE run group renders, headed by the run vocabulary + the project + the event count
    group = html.split('class="sl-rungroup"')[1].split("</details>")[0]
    assert html.count('class="sl-rungroup"') == 1
    assert f'{web.STRINGS["en"]["run_chip"]} · Run Group Proj' in group
    assert "event" in group and "<summary" in html.split('class="sl-rungroup"')[1][:300]
    assert "Council recorded" in group                          # the in-run event sits inside
    # the pre-run events stay flat — outside the details element
    assert "Persona created" not in group
    assert "Persona created" in html


def test_chrome_includes_the_live_client(store):
    html = TestClient(web.create_app()).get("/jobs?lang=en").text
    assert "EventSource('/api/events')" in html               # the live module ships on every page
    assert 'id="live-toast"' in html
