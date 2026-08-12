from __future__ import annotations

import asyncio
import hashlib
import json
import os
import time

from fastapi import Request

from .. import services


def _events_poll_interval() -> float:
    """The SSE table-poll cadence. Env-tunable (tests poll fast); ~1s in production —
    cheap (one indexed read on an at-most-1000-row table) and feels instant."""
    try:
        return max(0.02, min(10.0, float(os.getenv("SONALOOP_EVENTS_POLL", 1.0))))
    except (TypeError, ValueError):
        return 1.0


def _events_heartbeat_every() -> float:
    """Seconds between SSE heartbeat comments (keeps idle proxies/browsers from
    timing the stream out). Env-tunable so tests can observe one immediately."""
    try:
        return max(0.0, float(os.getenv("SONALOOP_EVENTS_HEARTBEAT", 15.0)))
    except (TypeError, ValueError):
        return 15.0


async def _event_stream(request, last_id: int | None, partition=None, scope=None):
    """Tail the cross-process `events` table as SSE frames. `id:` carries the bus row
    id, so EventSource reconnects replay via Last-Event-ID; a fresh connection (no
    last id) starts at the current high-water mark — live tail, no history dump.

    `partition` AND `scope` are the request-bound tenant context captured BY THE
    ENDPOINT: this body outlives the middleware that bound the contextvars (its finally
    resets them before the first poll runs), so every table read re-binds explicitly —
    without it a tenant's stream silently tails the GLOBAL events table (SQLite partition)
    or, on Postgres, sees nothing (RLS fail-closed because the scope is gone)."""
    from ..config import (reset_request_partition, reset_request_tenant_scope,
                          set_request_partition, set_request_tenant_scope)
    from ..storage import Store

    def _read(fn):
        p_token = set_request_partition(partition)
        s_token = set_request_tenant_scope(*scope) if scope else None
        store = Store()                              # fresh per poll: never hold a
        try:                                         # connection across the sleep
            return fn(store)
        finally:
            store.close()
            if s_token is not None:
                reset_request_tenant_scope(s_token)
            reset_request_partition(p_token)

    cursor = last_id if last_id is not None else _read(lambda s: s.latest_event_id())
    yield ": connected\n\n"                         # immediate flush → onopen fires
    last_beat = time.monotonic()
    while True:
        if await request.is_disconnected():
            return
        rows = _read(lambda s: s.list_events_after(cursor))
        for row in rows:
            cursor = row["id"]
            payload = {"id": row["id"], "ts": row["ts"], "event": row["event"],
                       "entity_type": row["entity_type"], "entity_id": row["entity_id"],
                       "project_id": row["project_id"], **row["data"]}
            yield f"id: {row['id']}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
            last_beat = time.monotonic()
        if time.monotonic() - last_beat >= _events_heartbeat_every():
            yield ": ping\n\n"
            last_beat = time.monotonic()
        await asyncio.sleep(_events_poll_interval())


def register_api(app) -> None:
    from fastapi import Query
    from fastapi.responses import JSONResponse, StreamingResponse

    @app.get("/api/events")
    async def api_events(request: Request):
        """Live event stream (SSE) for the inspector: new bus rows as they land,
        Last-Event-ID replay, heartbeat comments. Plain StreamingResponse — no deps."""
        raw_last = request.headers.get("last-event-id") or request.query_params.get("last_event_id")
        try:
            last_id = int(raw_last) if raw_last is not None else None
        except ValueError:
            last_id = None
        from ..config import request_partition, request_tenant_scope
        return StreamingResponse(
            _event_stream(request, last_id, partition=request_partition(),
                          scope=request_tenant_scope()),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @app.get("/api/runs")
    def api_runs():
        """Run states across all projects (ticket agents-running-panel) — the live
        topbar widget refetches this on SSE events; same read the /runs page uses."""
        from ._runs_widget import collect_run_states
        return JSONResponse(collect_run_states())

    @app.get("/api/personas")
    def api_personas():
        return JSONResponse(services.list_personas())

    @app.get("/api/personas/{persona_id}")
    def api_persona(persona_id: str):
        try:
            return JSONResponse(services.get_persona(persona_id))
        except KeyError:
            return JSONResponse({"error": "profile_not_found"}, status_code=404)

    @app.get("/api/personas/{persona_id}/calendar")
    def api_calendar(persona_id: str, date_value: str | None = Query(default=None, alias="date")):
        try:
            return JSONResponse(services.get_calendar(persona_id, date_value))
        except KeyError:
            return JSONResponse({"error": "profile_not_found"}, status_code=404)

    @app.get("/api/personas/{persona_id}/calendar-period")
    def api_calendar_period(persona_id: str, date_value: str | None = Query(default=None, alias="date"), view: str = "day"):
        try:
            return JSONResponse(services.get_calendar_period(persona_id, date_value, view))
        except KeyError:
            return JSONResponse({"error": "profile_not_found"}, status_code=404)

    @app.get("/api/personas/{persona_id}/memory")
    def api_memory(persona_id: str):
        try:
            return JSONResponse(services.get_persona_memory(persona_id))
        except KeyError:
            return JSONResponse({"error": "profile_not_found"}, status_code=404)

    @app.get("/api/personas/{persona_id}/projects")
    def api_projects(persona_id: str):
        try:
            return JSONResponse(services.list_active_projects(persona_id))
        except KeyError:
            return JSONResponse({"error": "profile_not_found"}, status_code=404)

    @app.get("/api/personas/{persona_id}/state-at")
    def api_state_at(persona_id: str, as_of: str = Query(...)):
        try:
            return JSONResponse(services.get_state_at(persona_id, as_of))
        except KeyError:
            return JSONResponse({"error": "profile_not_found"}, status_code=404)

    @app.get("/api/personas/{persona_id}/recall")
    def api_recall(persona_id: str, q: str = Query(...), as_of: str | None = Query(default=None), k: int = 8):
        try:
            return JSONResponse(services.recall_memory(persona_id, q, as_of, k))
        except KeyError:
            return JSONResponse({"error": "profile_not_found"}, status_code=404)

    @app.get("/api/personas/{persona_id}/evaluate")
    def api_evaluate(persona_id: str):
        try:
            return JSONResponse(services.evaluate_simulation_full(persona_id))
        except KeyError:
            return JSONResponse({"error": "profile_not_found"}, status_code=404)

    @app.get("/api/activities/{activity_id}")
    def api_activity(activity_id: str):
        try:
            return JSONResponse(services.get_activity(activity_id))
        except KeyError:
            return JSONResponse({"error": "activity_not_found"}, status_code=404)

    @app.get("/api/councils")
    def api_councils():
        return JSONResponse(services.list_councils())

    @app.get("/api/syntheses")
    def api_syntheses():
        return JSONResponse(services.list_syntheses())

    @app.get("/api/syntheses/{synthesis_id}")
    def api_synthesis(synthesis_id: str):
        try:
            return JSONResponse(services.get_synthesis(synthesis_id))
        except KeyError:
            return JSONResponse({"error": "synthesis_not_found"}, status_code=404)

    @app.get("/api/search")
    def api_search(q: str = Query(default="")):
        """Global command-palette search (UX V6). The searchable entity types live in the
        coverage registry (web/_palette_registry.SEARCH_SOURCES) — one declaration
        feeds this endpoint AND the palette's grouping/labels/icons. `rows` are ranked +
        capped per kind (fast no matter the store size); `closest` carries the nearest-hit
        suggestions ONLY when nothing matched (the palette's teach-don't-dead-end state)."""
        from ..storage import Store
        from ._palette_registry import closest_rows, search_rows
        store = Store()
        try:
            rows = search_rows(q, store=store)
            closest = [] if rows or not (q or "").strip() else closest_rows(q, store=store)
        finally:
            store.close()                # cloud is Postgres: an unclosed Store leaks a connection per call
        normalized = (q or "").strip()
        if normalized:
            from ..telemetry import capture_product_event
            length = len(normalized)
            bucket = "1_3" if length <= 3 else ("4_15" if length <= 15 else "16_plus")
            capture_product_event(
                "search_used",
                properties={
                    "surface": "command_palette",
                    "input_length_bucket": bucket,
                    "result_count": len(rows),
                },
                idempotency_key=(
                    f"palette:{int(time.time()) // 60}:"
                    f"{hashlib.sha256(normalized.encode('utf-8')).hexdigest()[:16]}"
                ),
            )
        return JSONResponse({"rows": rows, "closest": closest})
