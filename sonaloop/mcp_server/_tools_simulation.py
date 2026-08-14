from __future__ import annotations

import time
from typing import Any

from .. import services
from ._env import _env


def register_simulation(mcp):
    # ================= Planning (Phase A, multi-resolution) =================
    @mcp.tool()
    def brief_day(persona_id: str, date: str | None = None) -> dict[str, Any]:
        """GATHER context for planning ONE day (active projects, open threads, recall,
        world). Returns instructions for you to author a day plan; then put_day_plan."""
        t = time.perf_counter()
        return _env("brief_day", services.brief_day(persona_id, date), t)

    @mcp.tool()
    def put_day_plan(persona_id: str, date: str, plan: dict[str, Any]) -> dict[str, Any]:
        """Persist the day plan you authored from brief_day."""
        t = time.perf_counter()
        return _env("put_day_plan", services.put_day_plan(persona_id, date, plan), t)

    @mcp.tool()
    def record_day(persona_id: str, date: str, day_plan: dict[str, Any], plan: dict[str, Any],
                   activities: dict[str, Any], deltas: dict[str, Any] | None = None,
                   workday_start_hour: int | None = None, seed: str | None = None) -> dict[str, Any]:
        """Persist a host-authored SINGLE day end-to-end (put_day_plan -> simulate the
        authored blocks/activities -> optional consolidation). See brief_day's
        `day_bundle_hint` for the schema. Use record_month_bundle for whole months."""
        t = time.perf_counter()
        return _env("record_day", services.record_day(persona_id, date, day_plan, plan, activities, deltas, workday_start_hour, seed), t)

    @mcp.tool()
    def get_day_plan(persona_id: str, date: str) -> dict[str, Any]:
        """Fetch the stored day plan for a persona on a given date."""
        t = time.perf_counter()
        return _env("get_day_plan", services.get_day_plan(persona_id, date), t)

    @mcp.tool()
    def brief_period(persona_id: str, scope: str, date: str | None = None) -> dict[str, Any]:
        """GATHER context for a week|month|quarter|year plan, incl. candidate sample days.
        Author a period plan (with sample_days) then put_period_plan. Trends over long
        spans come from period plans + sampled days, not from simulating every day."""
        t = time.perf_counter()
        return _env("brief_period", services.brief_period(persona_id, scope, date), t)

    @mcp.tool()
    def put_period_plan(persona_id: str, scope: str, date: str, plan: dict[str, Any]) -> dict[str, Any]:
        """Persist a period plan (its sample_days drive which days you simulate concretely)."""
        t = time.perf_counter()
        return _env("put_period_plan", services.put_period_plan(persona_id, scope, date, plan), t)

    @mcp.tool()
    def get_period_plan(persona_id: str, scope: str, date: str) -> dict[str, Any]:
        """Fetch a stored period plan (week|month|quarter|year) for a persona."""
        t = time.perf_counter()
        return _env("get_period_plan", services.get_period_plan(persona_id, scope, date), t)

    @mcp.tool()
    def list_period_plans(persona_id: str, scope: str | None = None) -> dict[str, Any]:
        """List a persona's period plans (optionally filtered by scope)."""
        t = time.perf_counter()
        return _env("list_period_plans", services.list_period_plans(persona_id, scope), t)

    # ================= Simulation (Phase B) =================
    # The life-simulation is HOST-AUTHORED per day: brief_day → (host authors the day_plan + activities) →
    # record_day, and brief_month/record_month_bundle for a sampled month. There is no in-process
    # simulate_day/simulate_range/continue_simulation generator (retired — host authors all text).

    # M2 — clear_simulations / purge_runtime_data are DESTRUCTIVE operator actions, removed from the
    # agent surface (CLI-only: `sonaloop clear-simulations` / `purge`). spec/mcp-surface-cleanup M2.

    # ================= Consolidation (Phase C) =================
    @mcp.tool()
    def brief_consolidation(persona_id: str, date: str | None = None) -> dict[str, Any]:
        """GATHER a simulated day + known entities. Returns instructions for you to author
        memory_deltas (entities/facts/threads/event_links); then record_memory_deltas."""
        t = time.perf_counter()
        return _env("brief_consolidation", services.brief_consolidation(persona_id, date), t)

    @mcp.tool()
    def record_memory_deltas(persona_id: str, date: str, deltas: dict[str, Any]) -> dict[str, Any]:
        """Persist host-authored memory deltas: resolves/dedupes entities, writes bi-temporal
        facts (invalidating superseded status), opens/resolves threads, links events, embeds."""
        t = time.perf_counter()
        return _env("record_memory_deltas", services.record_memory_deltas(persona_id, date, deltas), t)

    # ================= Digests (Phase D) =================
    @mcp.tool()
    def brief_digest(persona_id: str, scope: str, date: str | None = None) -> dict[str, Any]:
        """GATHER a period for a consolidated digest (replaces hardcoded reflections)."""
        t = time.perf_counter()
        return _env("brief_digest", services.brief_digest(persona_id, scope, date), t)

    @mcp.tool()
    def put_digest(persona_id: str, scope: str, date: str, digest: dict[str, Any]) -> dict[str, Any]:
        """Persist + embed the digest you authored from brief_digest."""
        t = time.perf_counter()
        return _env("put_digest", services.put_digest(persona_id, scope, date, digest), t)

    @mcp.tool()
    def list_digests(persona_id: str, scope: str | None = None) -> dict[str, Any]:
        """List a persona's consolidated digests (optionally filtered by scope)."""
        t = time.perf_counter()
        return _env("list_digests", services.list_digests(persona_id, scope), t)

    # ================= Memory retrieval (the "check history" surface) =================
    @mcp.tool()
    def recall_memory(persona_id: str, query: str, as_of: str | None = None, k: int = 8) -> dict[str, Any]:
        """Hybrid (semantic + keyword/entity + recency + importance) recall over episodes,
        facts, digests, threads. USE when you want to check if the past has something relevant.
        `as_of` respects bi-temporal validity for time-travel."""
        t = time.perf_counter()
        return _env("recall_memory", services.recall_memory(persona_id, query, as_of, k), t)

    @mcp.tool()
    def list_active_projects(persona_id: str) -> dict[str, Any]:
        """Compact list of the persona's open projects with status + open-loop counts."""
        t = time.perf_counter()
        return _env("list_active_projects", services.list_active_projects(persona_id), t)

    @mcp.tool()
    def get_project(persona_id: str, entity_id: str, as_of: str | None = None) -> dict[str, Any]:
        """Full fact/status timeline of one project (use `as_of` for how it looked then)."""
        t = time.perf_counter()
        return _env("get_project", services.get_project(persona_id, entity_id, as_of), t)

    @mcp.tool()
    def get_state_at(persona_id: str, as_of: str) -> dict[str, Any]:
        """Time-travel: entities + facts + open threads + world valid at a given date."""
        t = time.perf_counter()
        return _env("get_state_at", services.get_state_at(persona_id, as_of), t)

    @mcp.tool()
    def get_timeline(persona_id: str, start: str | None = None, end: str | None = None,
                     entity_id: str | None = None, max_facts: int = 100,
                     max_events: int = 200) -> dict[str, Any]:
        """Chronological facts + experience events for a persona over a date range
        (optionally one entity). Capped to the newest `max_facts`/`max_events` rows —
        facts_total/events_total count everything and a `note` says when a cap trimmed;
        narrow with start/end/entity_id or raise the caps."""
        t = time.perf_counter()
        return _env("get_timeline", services.get_timeline(persona_id, start, end, entity_id,
                                                          max_facts=max_facts,
                                                          max_events=max_events), t)

    @mcp.tool()
    def search_entities(persona_id: str, kind: str | None = None, name: str | None = None) -> dict[str, Any]:
        """Find a persona's memory entities by kind and/or name substring."""
        t = time.perf_counter()
        return _env("search_entities", services.search_entities(persona_id, kind, name), t)

    @mcp.tool()
    def get_open_loops(persona_id: str, status: str | None = "open") -> dict[str, Any]:
        """A persona's unresolved threads / open loops (filter by status)."""
        t = time.perf_counter()
        return _env("get_open_loops", services.get_open_loops(persona_id, status), t)

    @mcp.tool()
    def resolve_entity(persona_id: str, mention: str, kind: str | None = None) -> dict[str, Any]:
        """Resolve a free-text mention to an existing entity (dedup), or null if new."""
        t = time.perf_counter()
        return _env("resolve_entity", services.resolve_entity(persona_id, mention, kind), t)

    @mcp.tool()
    def get_persona_memory(persona_id: str) -> dict[str, Any]:
        """Pure read of MEMORY.md content: active projects, threads and digests."""
        t = time.perf_counter()
        return _env("get_persona_memory", services.get_persona_memory(persona_id), t)

    @mcp.tool()
    def export_persona_memory(persona_id: str, out_path: str | None = None) -> dict[str, Any]:
        """Explicitly write the rendered MEMORY.md projection to disk."""
        t = time.perf_counter()
        return _env("export_persona_memory",
                    services.export_persona_memory(persona_id, out_path), t)

    # ----- F3 autonomous loop driver (month bundles) — relocated here (M3) -----
    @mcp.tool()
    def brief_month(persona_id: str, month: str) -> dict[str, Any]:
        """GATHER context to author a whole month bundle (period plan + sample days + digest),
        chained on the prior month. Then record_month_bundle."""
        t = time.perf_counter()
        return _env("brief_month", services.brief_month(persona_id, month), t)

    @mcp.tool()
    def record_month_bundle(persona_id: str, month: str, bundle: dict[str, Any]) -> dict[str, Any]:
        """Persist a host-authored month bundle through the full loop (plan->sample days->
        simulate->consolidate->digest->embed)."""
        t = time.perf_counter()
        return _env("record_month_bundle", services.record_month_bundle(persona_id, month, bundle), t)

    # ----- Persona timeline / activity reads — relocated here (M3) -----
    @mcp.tool()
    def get_current_state(persona_id: str, at_time: str | None = None) -> dict[str, Any]:
        """A persona's live state — what they're doing now / at a given time."""
        t = time.perf_counter()
        return _env("get_current_state", services.get_current_state(persona_id, at_time), t)

    @mcp.tool()
    def get_calendar(persona_id: str, date: str | None = None) -> dict[str, Any]:
        """A persona's calendar events for one day."""
        t = time.perf_counter()
        return _env("get_calendar", services.get_calendar(persona_id, date), t)

    @mcp.tool()
    def get_calendar_period(persona_id: str, date: str | None = None, view: str = "day") -> dict[str, Any]:
        """A persona's calendar for a day|week|month|year view — LEAN event rows
        (id/timestamp/event_type/task/tool/summary, capped to the newest 400 with an
        in-band note when more exist). Full payloads: get_activity(activity_id) for one
        event, get_calendar(persona_id, date) for one day."""
        t = time.perf_counter()
        return _env("get_calendar_period", services.get_calendar_period(persona_id, date, view), t)

    @mcp.tool()
    def get_activity(activity_id: str) -> dict[str, Any]:
        """Fetch one simulated activity (block) by id."""
        t = time.perf_counter()
        return _env("get_activity", services.get_activity(activity_id), t)

    @mcp.tool()
    def summarize_persona_period(persona_id: str, start_date: str | None = None, end_date: str | None = None, lens: str | None = None) -> dict[str, Any]:
        """Gather a persona's experience over a date range (optional lens) for summarisation."""
        t = time.perf_counter()
        return _env("summarize_persona_period", services.summarize_persona_period(persona_id, start_date, end_date, lens), t)

    @mcp.tool()
    def extract_pain_points(persona_id: str, start_date: str | None = None, end_date: str | None = None) -> dict[str, Any]:
        """Surface a persona's pain-point observations over a date range."""
        t = time.perf_counter()
        return _env("extract_pain_points", services.extract_pain_points(persona_id, start_date, end_date), t)
