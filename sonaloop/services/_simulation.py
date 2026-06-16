"""Simulation day/range + day/period plans + month bundle. Holds the host-authored simulation globals cluster (generate_day_plan_with_llm / generate_activity monkeypatch + simulate_day/record_day/record_month_bundle).

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



def clear_simulations(store: Store | None = None) -> dict[str, Any]:
    store = store or Store()
    deleted = store.clear_simulation_state()
    refreshed: list[str] = []
    for persona in store.list_personas():
        persona = ensure_persona_runtime_fields(persona, store)
        persona["soul"] = write_soul(persona, store)
        persona["updated_at"] = utc_now_iso()
        store.upsert_persona(persona, reason="clear simulations regenerated SOUL.md")
        refreshed.append(persona["id"])
    return {
        "deleted": deleted,
        "personas_refreshed": refreshed,
        "kept": ["personas", "avatars", "evidence", "audit_log"],
    }



def purge_runtime_data(remove_files: bool = True, store: Store | None = None) -> dict[str, Any]:
    store = store or Store()
    deleted = store.purge_runtime_state()
    removed_files: list[str] = []
    if remove_files:
        for root in [config.ROOT / "data" / "avatars", config.ROOT / "data" / "personas", config.ROOT / "personas"]:
            if root.exists():
                for path in sorted(root.rglob("*"), reverse=True):
                    if path.is_file():
                        path.unlink()
                        removed_files.append(str(path.relative_to(config.ROOT)))
                    elif path.is_dir():
                        try:
                            path.rmdir()
                        except OSError:
                            pass
                try:
                    root.rmdir()
                except OSError:
                    pass
    return {
        "deleted": deleted,
        "removed_files": removed_files,
        "kept": ["empty database schema", ".env", ".env.example"],
    }



def simulate_day(
    persona_id: str,
    date_value: str | None = None,
    timezone: str | None = None,
    seed: str | None = None,
    constraints: dict[str, Any] | None = None,
    day_plan: dict[str, Any] | None = None,
    activities: dict[str, Any] | None = None,
    store: Store | None = None,
) -> dict[str, Any]:
    """Build one simulated day from HOST-AUTHORED content: `day_plan` (the blocks) + `activities`
    (one per block title). No in-process generation — text is authored by the MCP host and validated
    here. Internal builder driven by record_day/record_month_bundle (spec memory: host authors all text)."""
    from .. import llm_simulation as _llm
    store = store or Store()
    persona = store.get_persona(persona_id)
    if not persona:
        raise KeyError(f"Unknown persona: {persona_id}")
    persona = ensure_persona_runtime_fields(persona, store)
    day = _parse_date(date_value)
    rng = _make_rng(seed, persona["id"], day.isoformat())
    now = utc_now_iso()
    tz = timezone or "Europe/Berlin"
    work_start = constraints.get("workday_start", 8) if constraints else 8
    soul = get_persona_soul(persona["id"], store)
    recent_events = store.list_experience_events(persona["id"])[-12:]
    recent_summaries = store.list_daily_summaries(persona["id"])[-5:]
    plan_frame = {
        "persona_name": persona["display_name"],
        "persona_id": persona["id"],
        "date": day.isoformat(),
        "timezone": tz,
        "workday_start_hour": int(work_start),
        "soul_path": soul["path"],
        "soul": soul["content"],
        "allowed_tools": persona["tools"],
        "allowed_tool_ids": persona.get("tool_ids", []),
        "allowed_pain_points": persona["pain_points"],
        "recent_events": [
            {
                "timestamp": e["timestamp"],
                "event_type": e["event_type"],
                "task": e["task"],
                "what_happened": e.get("what_happened"),
                "open_loops": e.get("open_loops", []),
            }
            for e in recent_events
        ],
        "recent_summaries": recent_summaries,
        "constraints": constraints or {},
        "seed_hint": seed or stable_id("day-plan", persona["id"], day.isoformat()),
    }
    # Plan/memory-aware: surface the covering plan, active projects, open threads,
    # relevant recalled memory and the world backdrop so the day knits into the arc.
    plan_frame["memory"] = _day_memory_context(store, persona, day.isoformat())
    day_plan = _llm.validate_day_plan_payload(day_plan or {}, plan_frame)

    calendar: list[dict[str, Any]] = []
    experience: list[dict[str, Any]] = []
    current = _event_time(day, int(work_start), rng.choice([0, 5, 10, 15, 20, 25, 35, 40, 45, 50]))
    blocks = day_plan["blocks"]
    open_loops: list[str] = []
    completed: list[str] = []
    blockers: list[str] = []
    day_pains: list[str] = []
    for idx, block in enumerate(blocks):
        title = block["title"]
        minutes = block["duration_minutes"]
        kind = block["event_type"]
        gap = rng.choice([5, 10, 15])
        start = current + timedelta(minutes=gap)
        end = start + timedelta(minutes=minutes)
        current = end
        participants = block.get("participants", [])
        tool = block["tool"]
        pain = rng.choice(persona["pain_points"])
        prior_events = store.list_experience_events(persona["id"])[-5:]
        frame = {
            "persona_name": persona["display_name"],
            "persona_id": persona["id"],
            "soul_path": soul["path"],
            "soul": soul["content"],
            "date": day.isoformat(),
            "start": start.isoformat(timespec="minutes"),
            "end": end.isoformat(timespec="minutes"),
            "title": title,
            "event_type": kind,
            "collaboration_mode": {
                "meeting": "meeting",
                "focus": "working alone",
                "interruption": "interruption with another stakeholder",
                "admin": "working alone",
            }.get(kind, "working alone"),
            "participants": participants,
            "tool": tool,
            "why_it_happens": block.get("why_it_happens"),
            "allowed_tools": persona["tools"],
            "allowed_tool_ids": persona.get("tool_ids", []),
            "allowed_pain_points": persona["pain_points"],
            "seed_hint": seed or stable_id("seed", persona["id"], day.isoformat(), title),
            "recent_events": [
                {
                    "timestamp": e["timestamp"],
                    "event_type": e["event_type"],
                    "summary": e["summary"],
                    "open_loops": e.get("open_loops", []),
                }
                for e in prior_events
            ],
        }
        if frame["title"] not in (activities or {}):
            raise ValueError(f"simulate_day: no authored activity for block '{frame['title']}'.")
        generated = _llm.validate_activity_payload((activities or {})[frame["title"]], frame)
        generated_pains = generated.get("pain_points", []) or [pain]
        day_pains.extend(generated_pains)
        outcome = "left an open follow-up" if generated.get("open_loops") else "resolved enough to move forward"
        if "open" in outcome:
            open_loops.append(title)
            blockers.extend(generated_pains)
        else:
            completed.append(title)
        cal = CalendarEvent(
            id=stable_id("cal", persona["id"], start.isoformat(), title),
            persona_id=persona["id"],
            start=start.isoformat(timespec="minutes"),
            end=end.isoformat(timespec="minutes"),
            title=title,
            participants=participants,
            location_or_tool=tool,
            intent=f"{persona['display_name']} needs to {title}.",
            outcome=outcome,
            created_at=now,
        ).to_dict()
        exp = ExperienceEvent(
            id=stable_id("evt", persona["id"], start.isoformat(), title),
            persona_id=persona["id"],
            timestamp=start.isoformat(timespec="minutes"),
            event_type=kind,
            summary=f"{persona['display_name']} {title} using {tool}; outcome: {outcome}.",
            task=title,
            tool=tool,
            participants=participants,
            collaboration_mode=frame["collaboration_mode"],
            what_happened=generated["what_happened"],
            conversation=generated["conversation"],
            key_quotes=generated["key_quotes"],
            actions_done=generated["actions_done"],
            artifacts_touched=generated["artifacts_touched"],
            persona_thought=generated["persona_thought"],
            decision=generated["decision"],
            open_loops=generated["open_loops"],
            impact={
                "mood": generated["mood"],
                "energy_delta": generated["energy_delta"],
                "timezone": tz,
                "generation_mode": generated.get("generation_mode", "llm"),
                "llm_error": generated.get("llm_error"),
            },
            pain_points=generated_pains,
            goal_refs=persona["goals"][:2],
            calendar_event_id=cal["id"],
            created_at=now,
        ).to_dict()
        calendar.append(cal)
        experience.append(exp)
        store.insert_calendar_event(cal)
        store.insert_experience_event(exp)

    summary = DailySummary(
        id=stable_id("day", persona["id"], day.isoformat()),
        persona_id=persona["id"],
        date=day.isoformat(),
        mood=day_plan.get("mood_forecast") or ("mixed" if blockers else "steady"),
        completed=completed,
        blockers=sorted(set(blockers)),
        open_loops=open_loops,
        pain_points=sorted(set(day_pains)),
        notable_memories=[e["summary"] for e in experience[-3:]],
        created_at=now,
    ).to_dict()
    store.upsert_daily_summary(summary)

    # Reflection/consolidation is no longer hardcoded. Periodic, evidence-backed
    # summaries are host-authored via brief_digest/put_digest (spec §4 Phase D,
    # §12.5). Day-level memory (entities, facts, threads) is built by
    # brief_consolidation/record_memory_deltas. Kept None here on purpose.
    reflection = None

    persona["soul"] = write_soul(persona, store)
    persona["updated_at"] = utc_now_iso()
    store.upsert_persona(persona, reason="simulation updated soul")

    for pain in sorted(set(day_pains)):
        pain_obs = PainPointObservation(
            id=stable_id("pain", persona["id"], pain),
            persona_id=persona["id"],
            issue=pain,
            severity=min(5, 2 + day_pains.count(pain)),
            frequency=sum(1 for e in store.list_experience_events(persona["id"]) if pain in e.get("pain_points", [])),
            evidence_event_ids=[e["id"] for e in experience if pain in e["pain_points"]],
            affected_workflow="daily coordination and project delivery",
            opportunity="Reduce manual reconciliation and make ownership visible at the moment of work.",
            created_at=now,
        ).to_dict()
        store.upsert_pain_point(pain_obs)

    store.commit()
    emit_lifecycle_event("day.recorded", {"persona_id": persona["id"], "date": day.isoformat(),  # noqa: F821 (bound)
                                          "events": len(experience)}, store)
    return SimulationResult(
        persona=persona,
        date=day.isoformat(),
        calendar_events=calendar,
        experience_events=experience,
        daily_summary=summary,
        reflection=reflection,
    ).to_dict()



# simulate_range / continue_simulation RETIRED: the life-simulation is host-authored per day
# (brief_day → record_day / record_month_bundle); there is no in-process multi-day generator.



def get_current_state(persona_id: str, at_time: str | None = None, store: Store | None = None) -> dict[str, Any]:
    store = store or Store()
    persona = store.get_persona(persona_id)
    if not persona:
        raise KeyError(f"Unknown persona: {persona_id}")
    events = store.list_experience_events(persona["id"])
    summaries = store.list_daily_summaries(persona["id"])
    latest = events[-1] if events else None
    latest_summary = summaries[-1] if summaries else {}
    return {
        "persona_id": persona["id"],
        "display_name": persona["display_name"],
        "at_time": at_time or utc_now_iso(),
        "current_activity": latest["task"] if latest else "not simulated yet",
        "current_tool": latest["tool"] if latest else None,
        "collaboration_mode": latest.get("collaboration_mode") if latest else None,
        "mood": (latest.get("impact") or {}).get("mood", "unknown") if latest else "unknown",
        "current_thought": latest.get("persona_thought") if latest else "unknown",
        "blocked_by": latest_summary.get("blockers") or [],
        "likely_next": (latest_summary.get("open_loops") or persona["goals"])[:3] if summaries else persona["goals"][:2],
        "synthetic_notice": "State is simulated unless backed by attached evidence.",
    }



def get_calendar(persona_id: str, date_value: str | None = None, store: Store | None = None) -> dict[str, Any]:
    store = store or Store()
    persona = store.get_persona(persona_id)
    if not persona:
        raise KeyError(f"Unknown persona: {persona_id}")
    day = _parse_date(date_value).isoformat() if date_value else None
    start = f"{day}T00:00" if day else None
    end = f"{day}T23:59" if day else None
    calendar = store.list_calendar_events(persona["id"], start, end)
    events = store.list_experience_events(persona["id"], start, end)
    event_by_calendar = {e.get("calendar_event_id"): e for e in events}
    blocks = []
    for cal in calendar:
        exp = event_by_calendar.get(cal["id"])
        blocks.append(
            {
                "calendar_event": cal,
                "activity": exp,
                "collaboration_mode": exp.get("collaboration_mode") if exp else None,
                "persona_thought": exp.get("persona_thought") if exp else None,
                "open_loops": exp.get("open_loops", []) if exp else [],
            }
        )
    return {"persona": persona, "date": day, "blocks": blocks}



# A summary-mode period view keeps at most this many event rows (a YEAR of dense
# simulation is thousands) — the newest are kept and the in-band note names the
# narrower handles (view/date, get_calendar, get_activity) for the rest.
PERIOD_EVENT_CAP = 300

# The lean per-event row of the summary view: enough to render a calendar and to
# decide which days to drill into; the full payload stays one get_activity away.
_PERIOD_EVENT_FIELDS = ("id", "timestamp", "event_type", "task", "tool")


def get_calendar_period(persona_id: str, date_value: str | None = None, view: str = "day",
                        store: Store | None = None, detail: str = "summary") -> dict[str, Any]:
    """A persona's calendar over a day/week/month/year window.

    `detail="summary"` (the default; output-budget fix, ticket mcp-output-budget-audit)
    returns LEAN event rows + a lean persona header — a month of simulated life was
    >200k chars with full payloads. Full single-event payloads: get_activity(id) /
    get_calendar(date); `detail="full"` returns the previous full shape (large)."""
    store = store or Store()
    persona = store.get_persona(persona_id)
    if not persona:
        raise KeyError(f"Unknown persona: {persona_id}")
    anchor = _parse_date(date_value)
    view = view if view in {"day", "week", "month", "year"} else "day"
    start_day, end_day = _period_bounds(anchor, view)
    start = f"{start_day.isoformat()}T00:00"
    end = f"{end_day.isoformat()}T23:59"
    events = store.list_experience_events(persona["id"], start, end)
    summaries = store.list_daily_summaries(persona["id"], start_day.isoformat(), end_day.isoformat())
    out: dict[str, Any] = {
        "persona": persona,
        "view": view,
        "anchor_date": anchor.isoformat(),
        "period_start": start_day.isoformat(),
        "period_end": end_day.isoformat(),
        "daily_summaries": summaries,
    }
    if detail != "full":
        from ._personas import _persona_summary
        out["persona"] = _persona_summary(persona)
        out["daily_summaries"] = [{"date": s.get("date"), "mood": s.get("mood")}
                                  for s in summaries]
        total = len(events)
        if total > PERIOD_EVENT_CAP:
            events = events[-PERIOD_EVENT_CAP:]   # timestamp-ordered: keep the newest
            out["note"] = (
                f"showing the {PERIOD_EVENT_CAP} most recent of {total} events in this period — "
                f"narrow the window (view/date) or use get_calendar(persona_id, date) for one day; "
                f"events are summary rows, the full activity is get_activity(activity_id).")
        events = [{k: e.get(k) for k in _PERIOD_EVENT_FIELDS} for e in events]
        out["events_total"] = total
    days: dict[str, list[dict[str, Any]]] = {}
    for event in events:
        days.setdefault(event["timestamp"][:10], []).append(event)
    out["days"] = days
    return out



def get_activity(activity_id: str, store: Store | None = None) -> dict[str, Any]:
    store = store or Store()
    event = store.get_experience_event(activity_id)
    if not event:
        raise KeyError(f"Unknown activity: {activity_id}")
    persona = store.get_persona(event["persona_id"])
    return {"persona": persona, "activity": event}



def summarize_persona_period(persona_id: str, start_date: str | None = None, end_date: str | None = None, lens: str | None = None, store: Store | None = None) -> dict[str, Any]:
    store = store or Store()
    persona = store.get_persona(persona_id)
    if not persona:
        raise KeyError(f"Unknown persona: {persona_id}")
    events = store.list_experience_events(persona["id"], start_date, end_date)
    summaries = store.list_daily_summaries(persona["id"], start_date, end_date)
    pains: dict[str, int] = {}
    for e in events:
        for pain in e.get("pain_points", []):
            pains[pain] = pains.get(pain, 0) + 1
    return {
        "persona": {"id": persona["id"], "display_name": persona["display_name"], "slug": persona["slug"]},
        "period": {"start": start_date, "end": end_date, "lens": lens or "work experience"},
        "days": len(summaries),
        "events": len(events),
        "top_pain_points": sorted(pains.items(), key=lambda x: x[1], reverse=True),
        "completed": [item for s in summaries for item in (s.get("completed") or [])][:20],
        "blockers": sorted(set(item for s in summaries for item in (s.get("blockers") or []))),
        "open_loops": [item for s in summaries for item in (s.get("open_loops") or [])][-10:],
    }



def extract_pain_points(persona_id: str, start_date: str | None = None, end_date: str | None = None, store: Store | None = None) -> list[dict[str, Any]]:
    summary = summarize_persona_period(persona_id, start_date, end_date, store=store)
    store = store or Store()
    persona = store.get_persona(persona_id)
    assert persona is not None
    observations = []
    for issue, frequency in summary["top_pain_points"]:
        obs = PainPointObservation(
            id=stable_id("pain", persona["id"], issue),
            persona_id=persona["id"],
            issue=issue,
            severity=min(5, max(1, frequency)),
            frequency=frequency,
            evidence_event_ids=[],
            affected_workflow="workday execution",
            opportunity="Investigate whether the real workflow can be changed without adding hidden work.",
            created_at=utc_now_iso(),
        ).to_dict()
        store.upsert_pain_point(obs)
        observations.append(obs)
    store.commit()
    return observations



def brief_day(persona_id: str, date_value: str | None = None, store: Store | None = None) -> dict[str, Any]:
    store = store or Store()
    persona = _require_persona(store, persona_id)
    day = _parse_date(date_value).isoformat()
    frame = {"persona_name": persona["display_name"], "persona_id": persona["id"], "scope": "day",
             "date": day, "soul": get_persona_soul(persona["id"], store)["content"],
             "memory": _day_memory_context(store, persona, day), "anti_steering": _ANTI_STEERING,
             "allowed_tools": persona["tools"], "allowed_tool_ids": persona.get("tool_ids", []),
             "allowed_pain_points": persona["pain_points"]}
    day_bundle_hint = (
        "To simulate this ONE day end-to-end, author a day bundle and call "
        "record_day(persona_id, date, day_plan, plan, activities[, deltas]): "
        "`plan` = this analysis (validate_plan_payload schema); `day_plan` = "
        "{mood_forecast, blocks:[{title, event_type, duration_minutes, collaboration_mode, "
        "participants, tool(from allowed_tools), why_it_happens}]} (>=5 blocks); `activities` = "
        "an object keyed by each block title -> {what_happened, conversation, key_quotes, "
        "actions_done, artifacts_touched, persona_thought, decision, open_loops, mood, "
        "energy_delta(-3..2), pain_points(from allowed_pain_points)}; `deltas` = optional "
        "consolidation (see brief_consolidation). " + language_instruction(content_language())
    )
    return {"persona_id": persona["id"], "date": day, "scope": "day", "schema": "plan",
            "instructions": build_plan_prompt(frame), "day_bundle_hint": day_bundle_hint, "frame": frame}



def record_day(persona_id: str, date_value: str, day_plan: dict[str, Any], plan: dict[str, Any],
               activities: dict[str, Any], deltas: dict[str, Any] | None = None,
               workday_start_hour: int | None = None, seed: str | None = None,
               store: Store | None = None) -> dict[str, Any]:
    """Persist a host-authored single day: put_day_plan -> simulate the authored
    blocks/activities -> optional record_memory_deltas. Mirrors one day of a month
    bundle, for when you want detail on a single date rather than a whole month."""
    store = store or Store()
    persona = _require_persona(store, persona_id)
    pid = persona["id"]
    day = _parse_date(date_value).isoformat()

    put_day_plan(pid, day, plan, store=store)
    cons = {"workday_start": int(workday_start_hour)} if workday_start_hour is not None else None
    sim = simulate_day(pid, day, seed=seed, constraints=cons, day_plan=day_plan, activities=activities, store=store)
    result = {"persona_id": pid, "date": day, "activities": len(sim["experience_events"])}
    if deltas:
        rec = record_memory_deltas(pid, day, deltas, store=store)
        result["entities"] = rec.get("entities_created")
        result["facts"] = rec.get("facts")
    return result



def put_day_plan(persona_id: str, date_value: str, plan: dict[str, Any], store: Store | None = None) -> dict[str, Any]:
    store = store or Store()
    persona = _require_persona(store, persona_id)
    day = _parse_date(date_value).isoformat()
    payload = validate_plan_payload(plan, "day")
    rec = {"id": stable_id("plan", persona["id"], "day", day), "persona_id": persona["id"],
           "scope": "day", "period_start": day, "period_end": day, "created_at": utc_now_iso(), **payload}
    store.upsert_plan(rec)
    store.commit()
    return rec



def get_day_plan(persona_id: str, date_value: str, store: Store | None = None) -> dict[str, Any] | None:
    store = store or Store()
    persona = _require_persona(store, persona_id)
    return store.get_plan(persona["id"], "day", _parse_date(date_value).isoformat())



def brief_period(persona_id: str, scope: str, date_value: str | None = None, store: Store | None = None) -> dict[str, Any]:
    store = store or Store()
    persona = _require_persona(store, persona_id)
    scope = scope if scope in {"week", "month", "quarter", "year"} else "month"
    anchor = _parse_date(date_value)
    start, end = _scope_bounds(anchor, scope)
    candidate_days = []
    d = start
    while d <= end:
        if d.weekday() < 5:
            candidate_days.append(d.isoformat())
        d += timedelta(days=1)
    from ..config import default_sample_days_per_month
    frame = {
        "persona_name": persona["display_name"], "persona_id": persona["id"], "scope": scope,
        "period_start": start.isoformat(), "period_end": end.isoformat(),
        "soul": get_persona_soul(persona["id"], store)["content"],
        "active_projects": memory_mod.list_active_projects(store, persona["id"]),
        "open_threads": [t["text"] for t in store.list_threads(persona["id"], "open")],
        "recent_digests": [d.get("text") for d in store.list_digests(persona["id"])[-4:]],
        "world_context": [{"category": w["category"], "fact": w["fact"]}
                          for w in store.list_world_context(as_of=end.isoformat())],
        "candidate_days": candidate_days,
        "suggested_sample_count": default_sample_days_per_month() if scope == "month" else max(2, len(candidate_days) // 10),
        "anti_steering": _ANTI_STEERING,
    }
    return {"persona_id": persona["id"], "scope": scope, "period_start": start.isoformat(),
            "period_end": end.isoformat(), "schema": "plan", "instructions": build_plan_prompt(frame), "frame": frame}



def put_period_plan(persona_id: str, scope: str, date_value: str, plan: dict[str, Any], store: Store | None = None) -> dict[str, Any]:
    store = store or Store()
    persona = _require_persona(store, persona_id)
    scope = scope if scope in {"week", "month", "quarter", "year"} else "month"
    start, end = _scope_bounds(_parse_date(date_value), scope)
    payload = validate_plan_payload(plan, scope)
    rec = {"id": stable_id("plan", persona["id"], scope, start.isoformat()), "persona_id": persona["id"],
           "scope": scope, "period_start": start.isoformat(), "period_end": end.isoformat(),
           "created_at": utc_now_iso(), **payload}
    store.upsert_plan(rec)
    store.commit()
    return rec



def get_period_plan(persona_id: str, scope: str, date_value: str, store: Store | None = None) -> dict[str, Any] | None:
    store = store or Store()
    persona = _require_persona(store, persona_id)
    start, _ = _scope_bounds(_parse_date(date_value), scope)
    return store.get_plan(persona["id"], scope, start.isoformat())



def list_period_plans(persona_id: str, scope: str | None = None, store: Store | None = None) -> list[dict[str, Any]]:
    store = store or Store()
    persona = _require_persona(store, persona_id)
    return store.list_plans(persona["id"], scope)


# ---- Digests (Phase D, §12.6) --------------------------------------------



def brief_month(persona_id: str, month: str, store: Store | None = None) -> dict[str, Any]:
    """Gather context to author a whole MONTH bundle (period plan + sample days +
    digest). Chains on the prior month's digest + current project state."""
    store = store or Store()
    persona = _require_persona(store, persona_id)
    pid = persona["id"]
    start = date.fromisoformat(f"{month}-01")
    prev_end = start - timedelta(days=1)
    prev_digests = [d for d in store.list_digests(pid, "month") if d["period_end"] <= prev_end.isoformat()]
    frame = {
        "persona_name": persona["display_name"], "persona_id": pid, "month": month,
        "soul": get_persona_soul(pid, store)["content"],
        "active_projects": memory_mod.list_active_projects(store, pid),
        "open_threads": [t["text"] for t in store.list_threads(pid, "open")],
        "prior_month_digest": prev_digests[-1]["text"] if prev_digests else None,
        "world_context": [{"category": w["category"], "fact": w["fact"]}
                          for w in store.list_world_context(as_of=start.isoformat())],
        "anti_steering": _ANTI_STEERING,
    }
    instructions = (
        "Author a MONTH bundle as JSON {period_plan, days:[{date, workday_start_hour, seed, "
        "day_plan, plan, activities, deltas}], digest}. Pick 3-4 working-day sample_days that "
        "show an arc (routine, conflict, milestone). Continue the SAME projects from "
        "active_projects/prior_month_digest with progressing status; use exact persona tools and "
        "pain_points; vary start hours and block counts; realistic done/open mix. See the "
        "simulate-cohort skill for the full schema. Anti-steering: " + _ANTI_STEERING
    )
    return {"persona_id": pid, "month": month, "schema": "month_bundle", "instructions": instructions, "frame": frame}



def record_month_bundle(persona_id: str, month: str, bundle: dict[str, Any], store: Store | None = None) -> dict[str, Any]:
    """Persist a host-authored month bundle through the full loop:
    put_period_plan -> per sample day (put_day_plan, simulate, consolidate) -> put_digest -> embed.
    """
    store = store or Store()
    persona = _require_persona(store, persona_id)
    pid = persona["id"]
    first = f"{month}-01"

    put_period_plan(pid, "month", first, bundle["period_plan"], store=store)
    days_done = []
    for day in bundle["days"]:
        d = day["date"]
        put_day_plan(pid, d, day["day_plan"], store=store)
        cons = {"workday_start": int(day["workday_start_hour"])} if day.get("workday_start_hour") is not None else None
        sim = simulate_day(pid, d, seed=day.get("seed"), constraints=cons,
                           day_plan=day["plan"], activities=day["activities"], store=store)
        rec = record_memory_deltas(pid, d, day["deltas"], store=store)
        days_done.append({"date": d, "activities": len(sim["experience_events"]),
                          "entities": rec["entities_created"], "facts": rec["facts"]})

    put_digest(pid, "month", first, bundle["digest"], store=store)
    backfill_embeddings(pid, store=store)
    return {"persona_id": pid, "month": month, "days": days_done, "sample_days": len(days_done)}


# ===================================================================== #
# F5 — Evidence integration (validate synthesis vs real evidence). F5.  #
# ===================================================================== #
