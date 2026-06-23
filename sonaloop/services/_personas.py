"""Persona CRUD + SOUL rendering + agent context + persona exports.

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
from ..suggestions import suggest_tech_comfort
from ..taxonomy import GENERIC_TOOLS, normalized_tool_ids, normalized_tools
from .. import artifacts as _A
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



def render_soul(persona: dict[str, Any], store: Store | None = None) -> str:
    store = store or Store()
    persona = effective_persona(persona, store)
    revisions = store.list_persona_revisions(persona["id"])
    summaries = store.list_daily_summaries(persona["id"])[-5:]
    reflections = store.list_reflections(persona["id"])[-3:]
    events = store.list_experience_events(persona["id"])[-8:]
    state_line = "No simulated day has been run yet."
    if events:
        latest = events[-1]
        state_line = (
            f"Last seen at {latest['timestamp']} doing `{latest['task']}` in "
            f"{latest.get('collaboration_mode', latest['event_type'])} mode."
        )
    recent_reflections = "\n".join(f"- {r['summary']}" for r in reflections) or "- None yet."
    recent_work_signals = "\n".join(
        f"- `{e['timestamp']}` {e['event_type']} / {e['task']}: {e.get('summary', '')}"
        for e in events
    ) or "- None yet."
    daily_reality = "\n".join(f"- {s['date']}: {s['mood']}; open loops: {', '.join(s['open_loops']) or 'none'}" for s in summaries) or "- Not simulated yet."
    relationships = "\n".join(f"- {r['name']} ({r['type']}): {r['friction']}" for r in persona["relationships"])
    caps = capability_profile(persona)                                      # noqa: F821 (bound)
    comfort = _A.resolve_tech_comfort(caps["tech_comfort"]) or {"value": 3, "label": "comfortable", "hint": ""}
    rungs = caps.get("rungs") or {}
    rung_line = " · ".join(f"{r}={'yes' if rungs.get(r) else 'no'}" for r in CAPABILITY_RUNGS)  # noqa: F821 (bound)
    return f"""# {persona['display_name']}

## Identity
{persona['display_name']} is a synthetic customer persona derived from:

> {persona['source_description']}

This is not a real person. Treat all non-evidence-backed details as simulation assumptions.

## Work Context
- Role: {persona['role']['title']}
- Company context: {persona['company_context']['industry']} ({persona['company_context']['size']} people)
- Tools: {', '.join(persona['tools'])}
- Operating model: {persona['company_context']['operating_model']}

## Inner Operating System
- Working style: {persona['personality']['working_style']}
- Communication style: {persona['personality']['communication_style']}
- Risk tolerance: {persona['personality']['risk_tolerance']}
- Decision filter: {', '.join(persona['success_criteria'])}

## Capabilities
- Session rungs (fidelities this persona can be simulated at): {rung_line}
- Tech comfort: {comfort['value']}/5 ({comfort['label']}) — {comfort['hint']}
- Devices: {', '.join(caps.get('devices') or []) or 'unspecified'}
- Accessibility: {caps.get('accessibility') or 'none noted'}
- Profile provenance: {caps.get('provenance')}

## Daily Reality
{daily_reality}

## Frictions
{chr(10).join(f'- {p}' for p in persona['pain_points'])}

## Motivations
{chr(10).join(f'- {g}' for g in persona['goals'])}

## Relationships
{relationships}

## Voice
Speak as a practical customer under real delivery pressure. Refer to concrete calendar moments, tools, handoffs, meetings, and open loops. Do not sound like a generic market research respondent.

## Simulation Rules
- Stay within the work context above unless new evidence is attached.
- Do not steer this persona toward BIM, AI, automation, or any product direction unless the source description, recent events, or explicit task context supports it.
- Treat inferred goals, tools, and pains as hypotheses, not facts; prefer ordinary daily work over vendor-friendly narratives.
- Prefer mundane repeated friction over dramatic invented events.
- Distinguish meetings, solo focus work, interruptions, admin, decisions, and follow-up.
- Preserve unresolved loops across days.
- Mark uncertainty instead of pretending inferred details are known.

## Current State
{state_line}

## Recent Work Signals
{recent_work_signals}

## Recent Reflections
{recent_reflections}

## Grown Identity (Revisions)
{chr(10).join(f"- {r['effective_on']}: {r.get('rationale','')[:200]}" for r in revisions) or "- None; core identity unchanged."}
"""



def write_soul(persona: dict[str, Any], store: Store | None = None) -> dict[str, Any]:
    path = soul_path(persona)
    path.parent.mkdir(parents=True, exist_ok=True)
    content = render_soul(persona, store)
    path.write_text(content, encoding="utf-8")
    return {"path": str(path.relative_to(config.ROOT)), "updated_at": utc_now_iso()}



def _replace_compatibility_inferred_defaults(persona: dict[str, Any]) -> bool:
    changed = False
    source_tool_ids, source_tools = normalized_tools(persona["source_description"])
    has_explicit_source_tools = bool(source_tools) and source_tools != [label for _, label in GENERIC_TOOLS]
    is_deterministically_inferred = persona.get("provenance", {}).get("profile_fields") == "deterministically inferred from source description"
    if is_deterministically_inferred and has_explicit_source_tools and persona.get("tools") != source_tools:
        persona["tool_ids"] = source_tool_ids
        persona["tools"] = source_tools
        changed = True
    company = persona.get("company_context", {})
    if is_deterministically_inferred and has_explicit_source_tools and company.get("stack") != source_tools:
        company["stack"] = source_tools
        persona["company_context"] = company
        changed = True
    return changed



def ensure_persona_runtime_fields(persona: dict[str, Any], store: Store | None = None) -> dict[str, Any]:
    changed = False
    if _replace_compatibility_inferred_defaults(persona):
        changed = True
    if (
        "identity_traits" not in persona
        or "avatar_profile" not in persona.get("identity_traits", {})
        or "tool_ids" not in persona
        or "tools" not in persona
    ):
        # Profile fields are host-authored; we never regenerate them server-side.
        # A persona missing them is malformed — point the host at the repair path
        # instead of crashing every read with the generic "generation disabled".
        raise ValueError(
            f"Persona {persona['id']} is missing host-authored profile fields "
            "(identity_traits/tools/tool_ids). Re-author it via brief_persona -> "
            "record_persona to repair it."
        )
    if "soul" not in persona or not persona.get("soul"):
        persona["soul"] = write_soul(persona, store)
        changed = True
    else:
        path = config.ROOT / persona["soul"]["path"]
        if not path.exists():
            persona["soul"] = write_soul(persona, store)
            changed = True
    if changed:
        persona["soul"] = write_soul(persona, store)
        persona["updated_at"] = utc_now_iso()
        (store or Store()).upsert_persona(persona, reason="ensure runtime fields")
    return persona



def _profile_to_persona_dict(
    description: str,
    profile: dict[str, Any],
    segment_hint: str | None,
    evidence: str | None,
    now: str,
    persona_id: str | None = None,
    previous: dict[str, Any] | None = None,
) -> dict[str, Any]:
    display_name = profile["display_name"]
    return Persona(
        id=persona_id or stable_id("persona", description, segment_hint or ""),
        slug=previous.get("slug") if previous else slugify(display_name),
        display_name=display_name,
        source_description=description,
        provenance={
            "source_description": "user",
            "segment_hint": "user" if segment_hint else "not_provided",
            "profile_fields": "llm_derived_from_source_description",
            "evidence": "attached" if evidence else "none",
            "synthetic_notice": "This profile is simulated and must be validated against real customer evidence.",
        },
        identity_traits=profile["identity_traits"],
        segment=profile["segment"],
        demographics=profile["demographics"],
        role=profile["role"],
        company_context=profile["company_context"],
        goals=profile["goals"],
        constraints=profile["constraints"],
        tool_ids=profile["tool_ids"],
        tools=profile["tools"],
        relationships=profile["relationships"],
        personality=profile["personality"],
        pain_points=profile["pain_points"],
        success_criteria=profile["success_criteria"],
        avatar=previous.get("avatar") if previous else None,
        soul=previous.get("soul") if previous else None,
        created_at=previous.get("created_at") if previous else now,
        updated_at=now,
    ).to_dict()



_PERSONA_AUTHORING_HINT = (
    "Persona profiles are host-authored (no server-side text generation). "
    "Gather with brief_persona(description[, segment_hint, evidence]) -> author the "
    "profile JSON it asks for -> persist with record_persona(description, profile)."
)

# The short capabilities ask appended to every persona-authoring brief: declare the profile
# explicitly, or accept defaults + a deterministic heuristic derivation on read.
_CAPABILITIES_BRIEF = (
    "\n\nCapabilities (optional but encouraged): add a `capabilities` object to the profile JSON — "
    "{rungs: {see, walk, drive, login} booleans (which session fidelities are plausible for this "
    "person; login=true only if simulated credentials make sense), tech_comfort: 1-5 (the closed "
    "vocabulary — see suggest_tech_comfort()), devices: ['desktop','mobile', …], accessibility: "
    "free-text notes session briefs must surface, provenance: 'authored'}. Absent -> safe defaults "
    "plus a deterministic profile derived from role/demographics on read (marked "
    "provenance='derived')."
)



def brief_persona(description: str, segment_hint: str | None = None, evidence: str | None = None,
                  store: Store | None = None) -> dict[str, Any]:
    """Gather the prompt + frame for authoring ONE synthetic persona profile.

    The host (Claude Code / Codex) writes the profile JSON from `instructions`,
    then calls record_persona. Detects + persists the content language from the
    source description the first time (so later runs/UI stay consistent)."""
    description = (description or "").strip()
    if not description:
        raise ValueError("brief_persona needs a non-empty source description.")
    language = ensure_content_language(" ".join(filter(None, [description, segment_hint, evidence])))
    return {
        "schema": "profile",
        "language": language,
        "description": description,
        "segment_hint": segment_hint,
        "has_evidence": bool(evidence),
        "instructions": build_profile_prompt(description, segment_hint, evidence, language)
        + _CAPABILITIES_BRIEF,
        "tech_comfort": suggest_tech_comfort(),
        "frame": {"description": description, "segment_hint": segment_hint, "evidence": evidence},
    }



def record_persona(
    description: str,
    profile: dict[str, Any],
    segment_hint: str | None = None,
    evidence: str | None = None,
    generate_avatar: bool = False,
    store: Store | None = None,
) -> dict[str, Any]:
    """Validate + persist a host-authored persona profile (the JSON authored from
    brief_persona). This is the create path; nothing is generated server-side."""
    store = store or Store()
    now = utc_now_iso()
    validated = validate_profile_payload(profile)
    persona = _profile_to_persona_dict(description, validated, segment_hint, evidence, now)
    if profile.get("capabilities") is not None:
        # Declared capabilities are validated + normalized over the safe defaults; absent stays
        # None so reads return the derived heuristic profile without rewriting the persona.
        persona["capabilities"] = merge_capabilities(None, profile["capabilities"])  # noqa: F821 (bound)
    persona["soul"] = write_soul(persona, store)
    store.upsert_persona(persona, reason="record_persona (host-authored)")
    if evidence:
        attach_evidence(persona["id"], "user_note", evidence, "Initial persona evidence", store)
    if generate_avatar:
        from ..avatar import AVATAR_DISABLED_NOTE, avatars_enabled, generate_persona_avatar

        if not avatars_enabled():
            # Fail-soft (cold start without the optional key): the persona is the product,
            # the avatar is eye-candy — record the helpful note in-band instead of raising.
            persona["avatar_note"] = AVATAR_DISABLED_NOTE
        else:
            avatar = generate_persona_avatar(persona["id"], store=store)
            persona["avatar"] = avatar
            persona["updated_at"] = utc_now_iso()
            store.upsert_persona(persona, reason="generated avatar")
    emit_lifecycle_event("persona.created", {"persona_id": persona["id"], "slug": persona["slug"],  # noqa: F821 (bound)
                                             "display_name": persona.get("display_name", "")}, store)
    return persona



def create_persona(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
    raise NotImplementedError(_PERSONA_AUTHORING_HINT)



def bulk_create_personas(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
    raise NotImplementedError(
        "Bulk creation is host-authored: brief_persona per description, author each "
        "profile, then record_persona for each. " + _PERSONA_AUTHORING_HINT
    )



def refresh_persona_from_source(persona_id: str, store: Store | None = None,
                                force: bool = False) -> dict[str, Any]:
    """For catalog-pulled personas "refresh from source" has a concrete meaning: re-pull
    the persona from its recorded catalog ref (drift-safe — a locally modified profile is
    skipped and reported unless force=True). Native personas re-author instead (hint)."""
    store = store or Store()
    persona = store.get_persona(persona_id)
    if not persona:
        raise KeyError(f"Unknown persona: {persona_id}")
    stamp = (persona.get("provenance") or {}).get("catalog")
    if not stamp:
        raise NotImplementedError(
            "Refreshing a NATIVE profile re-authors it: brief_persona(persona.source_description) "
            "-> author -> record_persona. " + _PERSONA_AUTHORING_HINT
        )
    out = catalog_pull(persona_slugs=[persona["slug"]], ref=stamp.get("ref") or "main",  # noqa: F821 (bound)
                       force=force, store=store)
    return {**out, "persona_id": persona["id"], "refreshed_from": stamp}



def get_persona(persona_id: str, store: Store | None = None) -> dict[str, Any]:
    store = store or Store()
    persona = store.get_persona(persona_id)
    if not persona:
        raise KeyError(f"Unknown persona: {persona_id}")
    persona = ensure_persona_runtime_fields(persona, store)
    # The capability profile in effect — derived in the RETURNED dict only when the stored
    # persona never declared one (the persona itself is not rewritten on read).
    persona["capabilities"] = capability_profile(persona)                   # noqa: F821 (bound)
    return {
        "persona": persona,
        "calendar_events": store.list_calendar_events(persona["id"])[-10:],
        "experience_events": store.list_experience_events(persona["id"])[-20:],
        "daily_summaries": store.list_daily_summaries(persona["id"])[-10:],
        "pain_points": store.list_pain_points(persona["id"]),
        "reflections": store.list_reflections(persona["id"])[-5:],
    }



def _persona_summary(p: dict[str, Any]) -> dict[str, Any]:
    """A LEAN one-line persona overview for list views / the autonomous loop, so listing the cohort
    never bloats context (drill in with get_persona for the full profile)."""
    seg = p.get("segment") or {}
    bits = [seg.get("lebensphase"), seg.get("einstellung"), seg.get("kanal"), seg.get("region"),
            seg.get("finanzlage")]
    return {"id": p["id"], "slug": p["slug"], "display_name": p.get("display_name", ""),
            "url": web_url(f"/personas/{p['id']}"),  # noqa: F821 (bound) — the link to hand the user
            "age_range": (p.get("identity_traits") or {}).get("age_range", ""),
            "role": (p.get("role") or {}).get("title", ""),
            "segment": " · ".join(str(b) for b in bits if b)[:140]}


def list_personas(filters: dict[str, Any] | None = None, store: Store | None = None,
                  compact: bool = False) -> list[dict[str, Any]]:
    """List personas. `compact=True` returns lean one-line summaries (slug/name/age/role/segment) —
    the right shape for agents/list views to avoid context bloat; full profiles via get_persona."""
    store = store or Store()
    personas = [ensure_persona_runtime_fields(p, store) for p in store.list_personas()]
    if filters:
        needle = " ".join(str(v).lower() for v in filters.values() if v)
        personas = [p for p in personas if needle in json.dumps(p, ensure_ascii=False).lower()]
    if compact:
        return [_persona_summary(p) for p in personas]
    for p in personas:                                  # the profile in effect (derived on read)
        p["capabilities"] = capability_profile(p)       # noqa: F821 (bound)
    return personas



def update_persona(persona_id: str, patch: dict[str, Any], reason: str, store: Store | None = None) -> dict[str, Any]:
    store = store or Store()
    persona = store.get_persona(persona_id)
    if not persona:
        raise KeyError(f"Unknown persona: {persona_id}")
    if "capabilities" in patch:
        # Capability patches are validated (shape + vocabulary) and merged onto the declared
        # profile (else the safe defaults) into a FULL normalized profile, marked authored.
        patch = {**patch,
                 "capabilities": merge_capabilities(persona.get("capabilities"),  # noqa: F821 (bound)
                                                    patch["capabilities"])}
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(persona.get(key), dict):
            persona[key].update(value)
        else:
            persona[key] = value
    persona["updated_at"] = utc_now_iso()
    persona["soul"] = write_soul(persona, store)
    store.upsert_persona(persona, reason=reason)
    emit_lifecycle_event("persona.updated", {"persona_id": persona["id"], "reason": reason}, store)  # noqa: F821 (bound)
    return persona



def get_persona_soul(persona_id: str, store: Store | None = None) -> dict[str, Any]:
    store = store or Store()
    persona = store.get_persona(persona_id)
    if not persona:
        raise KeyError(f"Unknown persona: {persona_id}")
    persona = ensure_persona_runtime_fields(persona, store)
    path = config.ROOT / persona["soul"]["path"]
    if not path.exists():
        persona["soul"] = write_soul(persona, store)
        store.upsert_persona(persona, reason="recreated SOUL.md")
        path = config.ROOT / persona["soul"]["path"]
    return {"persona_id": persona["id"], "path": persona["soul"]["path"], "content": path.read_text(encoding="utf-8")}



def prepare_persona_agent_context(
    persona_id: str,
    task: str | None = None,
    recent_events: int = 8,
    store: Store | None = None,
) -> dict[str, Any]:
    """Build the context packet a subagent must receive to act as a persona.

    This is the MCP workflow guarantee: persona-facing agents do not infer from
    the visible UI. They receive the durable SOUL.md content, current state, and
    recent lived events from the server.
    """
    store = store or Store()
    persona = store.get_persona(persona_id)
    if not persona:
        raise KeyError(f"Unknown persona: {persona_id}")
    persona = ensure_persona_runtime_fields(persona, store)
    soul = get_persona_soul(persona["id"], store)
    state = get_current_state(persona["id"], store=store)
    events = store.list_experience_events(persona["id"])[-max(0, recent_events):]
    event_lines = [
        f"- {e['timestamp']} [{e['event_type']} / {e.get('collaboration_mode', 'unknown')}]: "
        f"{e.get('what_happened', e['summary'])} "
        f"Actions: {', '.join(e.get('actions_done', []))}. "
        f"Open loops: {', '.join(e.get('open_loops', [])) or 'none'}"
        for e in events
    ]

    # --- Memory grounding (spec §5.2/§5.7): the persona can draw on its own
    # project history ON DEMAND, not narrate it constantly. Recall is keyed to
    # the actual task/question so only relevant past surfaces. ---
    active_projects = memory_mod.list_active_projects(store, persona["id"])
    open_threads = store.list_threads(persona["id"], "open")
    recall_hits = memory_mod.recall(store, persona["id"], task, k=6)["hits"] if task and task.strip() else []
    projects_block = "\n".join(
        f"- {p['name']} — Status: {p.get('status') or 'unbekannt'} (offene Fäden: {p['open_loops']})"
        for p in active_projects[:10]
    ) or "- (keine erfassten Projekte)"
    threads_block = "\n".join(f"- {t['text']}" for t in open_threads[:10]) or "- (keine offenen Fäden)"
    recall_block = "\n".join(
        f"- [{h['obj_type']}] {h['when'] or ''}: {h['text']}" for h in recall_hits
    ) or "- (nichts spezifisch Relevantes gefunden)"
    # Real-material grounding (docs/grounding.md): the task-relevant source chunks ride
    # the context with their ids, so the persona's words cite REAL signal, not vibes.
    grounded_block = grounding_context_block(persona, task, store)  # noqa: F821 (bound)

    agent_context = f"""# Persona Subagent Context

You must act from the perspective of this synthetic customer persona.

## Required Source
The following SOUL.md has been loaded from `{soul['path']}`. Treat it as the
authoritative persona identity and simulation rules.

---

{soul['content']}

---

## Current State
{json.dumps(state, indent=2, ensure_ascii=False)}

## Recent Lived Events
{chr(10).join(event_lines) if event_lines else '- No simulated events yet.'}

## Active Projects (memory)
{projects_block}

## Open Loops (memory)
{threads_block}

## Relevant Memory (recalled for this task — background, use only if it fits)
{recall_block}
{f'''
## Grounded Source Material (REAL signal from this persona's corpora)
{grounded_block}
''' if grounded_block else ''}
## Task
{task or 'No task supplied. Use this context for persona-grounded reasoning.'}

## Operating Rules
- Stay grounded in SOUL.md, recent events, and the persona's project memory.
- Speak from the persona's lived work context, not as a generic consultant.
- Memory is background: refer to past projects/loops only when the question
  genuinely calls for it — do not recite memories unprompted.
- When uncertain, say what is inferred or synthetic.
- Cite concrete calendar moments, tools, people, projects, and open loops when relevant.
{"- Prefer the REAL signal in Grounded Source Material over synthetic detail and cite its chunk ids in refs." if grounded_block else ""}
"""
    return {
        "persona_id": persona["id"],
        "display_name": persona["display_name"],
        "soul_loaded": True,
        "soul_path": soul["path"],
        "current_state": state,
        "recent_event_ids": [e["id"] for e in events],
        "active_projects": active_projects,
        "open_threads": [t["id"] for t in open_threads],
        "recall_hits": recall_hits,
        "agent_context": agent_context,
    }



def attach_evidence(persona_id: str, source_type: str, content_or_path: str, notes: str | None = None, store: Store | None = None) -> dict[str, Any]:
    store = store or Store()
    persona = store.get_persona(persona_id)
    if not persona:
        raise KeyError(f"Unknown persona: {persona_id}")
    evidence = Evidence(
        id=stable_id("evidence", persona["id"], source_type, content_or_path[:120]),
        persona_id=persona["id"],
        source_type=source_type,
        content_or_path=content_or_path,
        notes=notes,
        created_at=utc_now_iso(),
    ).to_dict()
    store.insert_evidence(evidence)
    emit_lifecycle_event("evidence.attached", {"persona_id": persona["id"], "evidence_id": evidence["id"],  # noqa: F821 (bound)
                                               "source_type": source_type}, store)
    return evidence



def export_persona(persona_id: str, format: str = "json", store: Store | None = None) -> str:
    data = get_persona(persona_id, store)
    if format == "md":
        p = data["persona"]
        return f"# {p['display_name']}\n\n```json\n{json.dumps(data, indent=2, ensure_ascii=False)}\n```\n"
    return json.dumps(data, indent=2, ensure_ascii=False)



def export_logs(persona_id: str, start_date: str | None = None, end_date: str | None = None, format: str = "json", store: Store | None = None) -> str:
    store = store or Store()
    persona = store.get_persona(persona_id)
    if not persona:
        raise KeyError(f"Unknown persona: {persona_id}")
    events = store.list_experience_events(persona["id"], start_date, end_date)
    if format == "csv":
        import io

        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=["timestamp", "event_type", "summary", "task", "tool"])
        writer.writeheader()
        for e in events:
            writer.writerow({k: e.get(k, "") for k in writer.fieldnames or []})
        return buf.getvalue()
    if format == "md":
        lines = [f"# Logs for {persona['display_name']}", ""]
        for e in events:
            lines.append(f"- `{e['timestamp']}` **{e['event_type']}**: {e['summary']}")
            if e.get("persona_thought"):
                lines.append(f"  - Thought: {e['persona_thought']}")
            if e.get("key_quotes"):
                lines.append(f"  - Quotes: {' | '.join(e['key_quotes'])}")
            if e.get("actions_done"):
                lines.append(f"  - Actions: {'; '.join(e['actions_done'])}")
        return "\n".join(lines) + "\n"
    return json.dumps(events, indent=2, ensure_ascii=False)



def effective_persona(persona: dict[str, Any], store: Store | None = None) -> dict[str, Any]:
    """Apply persona_revisions (slow, evidence-backed drift) as an overlay view.

    Does NOT mutate the stored base persona — the source identity is preserved;
    this returns the *grown* identity used for SOUL rendering and simulation.
    """
    store = store or Store()
    revisions = store.list_persona_revisions(persona["id"])
    if not revisions:
        return persona
    p = json.loads(json.dumps(persona))
    for rev in revisions:
        ch = rev.get("changes", {})
        for field, add_key, rm_key in [
            ("goals", "goals_add", "goals_remove"),
            ("constraints", "constraints_add", "constraints_remove"),
            ("pain_points", "pains_add", "pains_remove"),
            ("tools", "tools_add", "tools_remove"),
        ]:
            cur = list(p.get(field, []))
            for add in ch.get(add_key, []):
                if add not in cur:
                    cur.append(add)
            rm = set(ch.get(rm_key, []))
            p[field] = [x for x in cur if x not in rm]
        if "tools_add" in ch or "tools_remove" in ch:
            try:
                p["tool_ids"] = normalized_tool_ids(" ".join(p.get("tools", []))) or p.get("tool_ids", [])
            except Exception:  # noqa: BLE001
                pass
        if isinstance(ch.get("personality"), dict):
            p.setdefault("personality", {}).update(ch["personality"])
    return p



def _day_memory_context(store: Store, persona: dict[str, Any], day_iso: str) -> dict[str, Any]:
    pid = persona["id"]
    active = memory_mod.list_active_projects(store, pid)
    threads = store.list_threads(pid, "open")
    world = store.list_world_context(as_of=day_iso)
    seed = " ".join((persona.get("goals", [])[:2] + persona.get("pain_points", [])[:2]))
    hits = memory_mod.recall(store, pid, seed, as_of=day_iso, k=6)["hits"] if seed.strip() else []
    return {
        "covering_period_plan": store.find_covering_plan(pid, "month", day_iso),
        "covering_week_plan": store.find_covering_plan(pid, "week", day_iso),
        "day_plan": store.get_plan(pid, "day", day_iso),
        "active_projects": active,
        "open_threads": [{"id": t["id"], "text": t["text"], "entity_id": t.get("entity_id")} for t in threads],
        "world_context": [{"category": w["category"], "fact": w["fact"]} for w in world],
        "recall": hits,
    }



def delete_persona(persona_id: str, store: Store | None = None) -> dict[str, Any]:
    """Delete a persona and all of its persona-scoped rows + rendered SOUL/avatar files."""
    store = store or Store()
    persona = store.get_persona(persona_id)
    if not persona:
        raise KeyError(f"Unknown persona: {persona_id}")
    deleted = store.delete_persona_cascade(persona["id"])
    removed: list[str] = []
    d = persona_dir(persona)
    if d.exists():
        for path in sorted(d.rglob("*"), reverse=True):
            if path.is_file():
                path.unlink()
                removed.append(str(path.relative_to(config.ROOT)))
        try:
            d.rmdir()
        except OSError:
            pass
    return {"persona_id": persona["id"], "deleted": deleted, "removed_files": removed}


# ===================================================================== #
# Project REPORT: a project-scope synthesis over a whole project graph.   #
# gather graph -> author OUTLINE -> author each SECTION (grounded) ->     #
# export. Two-level provenance: section -> study -> council.              #
# ===================================================================== #
