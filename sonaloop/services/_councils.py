"""Council briefs/asks + council write-back/reads + export.

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

from ..config import (
    utc_now_iso, content_language, ensure_content_language, language_instruction,
    critic_threshold, critic_sample_k,
)
from ._authoring import MARKDOWN_CONTRACT, PRIMITIVES_CONTRACT
from .. import artifacts as _artifacts
from .. import primitive_taxonomy_registry as _taxonomy_registry
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



def brief_council(project_id: str, prompt: str, persona_ids: list[str] | None = None,
                  filters: dict[str, Any] | None = None, count: int = 3, context: str | None = None,
                  artifact_ids: list[str] | None = None, store: Store | None = None) -> dict[str, Any]:
    """Gather everything needed to run a host-authored council and persist it with
    record_council. A council is scoped to a research project, so `project_id` is required
    and validated up front (create one with create_research_project first; personas are
    global and need no project). Returns candidate personas (to select from) OR, when
    persona_ids are given, each participant's loaded agent context to author turns against.

    Point the council at REAL artifacts with `artifact_ids` (or omit it to include every artifact
    ingested into the project): each participant's context is grounded in the CAPTURED artifact(s) —
    a live URL/website, a prototype link, or two A/B variants — so reactions are about what is actually
    there, not a description. Two+ variants are present and labelled A/B/… for side-by-side comparison.
    Add artifacts first via add_artifact(project_id, url, kind=...).

    Methodology lives in the run-council skill: load each persona's SOUL + memory,
    react in character (support/skepticism/indifference/rejection all valid), then
    author proposal/votes/exec_summary and call record_council."""
    store = store or Store()
    project = _require_research_project(store, project_id)  # fail fast if no/unknown project
    # Artifacts in the room: the captured copy of every selected artifact, labelled A/B/… so personas
    # react to the REAL thing (this is the heart of the artifacts-into-council ticket).
    artifact_briefs = council_artifact_briefs(project["id"], artifact_ids, store=store)
    artifacts_context = render_artifacts_context(artifact_briefs)
    # Evidence assets in the room: every file/image/screenshot attached to the project rides along —
    # image assets tell the HOST to view_asset them first (ticket attach-evidence-files-mcp).
    asset_briefs = project_asset_briefs(project["id"], store=store)
    assets_context = render_assets_context(asset_briefs)
    artifacts_context = "\n\n".join(filter(None, [artifacts_context, assets_context]))
    language = ensure_content_language(" ".join(filter(None, [prompt, context])))
    if not persona_ids:
        personas = list_personas(filters, store)
        candidates = [
            {"persona_id": p["id"], "display_name": p["display_name"],
             "source_description": p["source_description"], "role": p.get("role", {}),
             "company_context": p.get("company_context", {}), "goals": p.get("goals", []),
             "constraints": p.get("constraints", []), "tools": p.get("tools", []),
             "pain_points": p.get("pain_points", []), "success_criteria": p.get("success_criteria", [])}
            for p in personas
        ]
        return {
            "schema": "council_selection", "language": language, "project_id": project["id"], "prompt": prompt,
            "count": min(max(1, count), len(candidates)) if candidates else 0,
            "candidate_personas": candidates, "artifacts": artifact_briefs, "assets": asset_briefs,
            "instructions": (
                "Select the personas whose lived contexts produce useful, honest contrast on this "
                "prompt (never bias toward support; do not invent IDs). Then call brief_council again "
                f"with persona_ids=[...] to get each participant's context. {language_instruction(language)}"
                if candidates else "No personas exist yet. Create some via brief_persona/record_persona first."
            ),
        }
    # The artifact block rides along with the external context so a persona's loaded context is grounded
    # in the captured artifact(s) — it sits in the keyed memory recall AND in agent_context below.
    artifact_task = "\n\n".join(filter(None, [context or "", artifacts_context])) or None
    participants = []
    for pid in persona_ids:
        p = store.get_persona(pid)
        if not p:
            continue
        ctx = prepare_persona_agent_context(
            p["id"], f"Council prompt: {prompt}\nExternal context: {artifact_task or 'none'}", store=store)
        agent_context = ctx["agent_context"]
        if artifacts_context:
            agent_context = f"{agent_context}\n\n=== ARTIFACTS ===\n{artifacts_context}"
        participants.append({
            "persona_id": p["id"], "display_name": p["display_name"],
            "soul_path": ctx["soul_path"], "agent_context": agent_context,
        })
    return {
        "schema": "council", "language": language, "project_id": project["id"], "prompt": prompt,
        "external_context": context, "participants": participants,
        "artifacts": artifact_briefs, "assets": asset_briefs, "artifacts_context": artifacts_context,
        "instructions": (
            ("EVIDENCE ASSETS ARE IN THE ROOM: view_asset every image asset and read every document "
             "excerpt BEFORE authoring reactions — ground statements in the real material and cite "
             "asset ids in refs.\n" if asset_briefs else "") +
            ("ARTIFACTS ARE IN THE ROOM: each participant's agent_context ends with the CAPTURED "
             "artifact(s) (a live URL/website, a prototype link, or labelled A/B variants). Ground every "
             "statement in what is ACTUALLY there — quote the captured copy, don't invent unseen content; "
             "with two+ variants, name which wins for whom and why.\n" if artifact_briefs else "") +
            "Run this council in the shape the task calls for (the UI derives the mode):\n"
            "• DISCOVERY (default for early research): pass `questions` = the OPEN, conversational "
            "user-research questions you ask. Author ONE `statement` per (persona, question) — that "
            "persona's honest answer — with about={kind:'prompt', id:'q0'|'q1'|…} pointing at the "
            "question it answers, so the page renders a moderated Q→A transcript. Do NOT invent a "
            "hypothesis and do NOT collect votes — you are LISTENING. Leave proposal/votes empty.\n"
            "• EVALUATION (reacting to a concept/prototype): set `proposal`; each statement reacts with "
            "about={kind:'prompt', id:'proposal'} + a stance "
            "({value -2..2, label?: support|conditional|neutral|skeptical|oppose}); no hard votes.\n"
            "• DECISION (rare — an explicit choice): set `proposal` + `votes` (the same stance-scale "
            "terms: support|conditional|neutral|skeptical|oppose) for the tally.\n"
            "On each statement set persona_id, text (the persona's words, in voice), stance where "
            "applicable, about (the prompt it answers), and refs (the memories/sources drawn on, incl. "
            "{kind:'memory', text}). Ground every statement in agent_context, honest + anti-steering. "
            "Add `findings` for any council-level analysis + a rich Markdown exec_summary. Persist via "
            "record_council(project_id, prompt, persona_ids, statements=[...], questions=[...] | "
            f"proposal=…, votes=…, summary, exec_summary, findings=[...]). {language_instruction(language)}"
            + MARKDOWN_CONTRACT + PRIMITIVES_CONTRACT
        ),
    }






def run_council(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
    raise NotImplementedError(
        "Councils are host-authored: brief_council(prompt) -> pick personas -> "
        "brief_council(prompt, persona_ids) -> author turns + synthesis -> record_council(...). "
        "See the run-council skill."
    )



def brief_ask(persona_id: str, question: str, context: str | None = None, store: Store | None = None) -> dict[str, Any]:
    """Gather one persona's loaded agent context to author an honest answer to a
    question. The host writes the answer from the returned agent_context (the
    persona's SOUL + recent events + task-keyed memory)."""
    store = store or Store()
    persona = store.get_persona(persona_id)
    if not persona:
        raise KeyError(f"Unknown persona: {persona_id}")
    language = ensure_content_language(" ".join(filter(None, [question, context])))
    agent_ctx = prepare_persona_agent_context(persona_id, question, store=store)
    return {
        "schema": "persona_answer", "language": language, "persona_id": persona["id"],
        "display_name": persona["display_name"], "question": question, "external_context": context,
        "soul_path": agent_ctx["soul_path"], "agent_context": agent_ctx["agent_context"],
        "instructions": (
            "Answer AS this persona, grounded in the agent_context — do not force support; "
            "say what is uncertain if the record is thin. " + language_instruction(language)
        ),
    }



def ask_persona(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
    raise NotImplementedError(
        "Persona answers are host-authored: brief_ask(persona_id, question) returns the "
        "persona's loaded context; you write the answer in character."
    )



def compare_personas(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
    raise NotImplementedError(
        "Compare is host-authored: brief_ask per persona on the same question, then author "
        "each answer and contrast them."
    )



def export_council_session(session_id: str, format: str = "json", store: Store | None = None) -> str:
    store = store or Store()
    session = store.get_council_session(session_id)
    if not session:
        raise KeyError(f"Unknown council session: {session_id}")
    if format == "md":
        de = content_language() == "de"
        h_session = "Council-Sitzung" if de else "Council Session"
        h_turns = "Wortbeiträge" if de else "Turns"
        h_proposal = "Vorschlag" if de else "Proposal"
        h_votes = "Stimmen" if de else "Votes"
        h_summary = "Zusammenfassung" if de else "Summary"
        lines = [f"# {h_session}", "", f"**Prompt:** {session['prompt']}", "", f"## {h_turns}"]
        for st in _artifacts.council_statements(session):
            who = (store.get_persona(st.get("persona_id", "")) or {}).get("name") or st.get("persona_id", "")
            lines.append(f"- **{who}**: {st.get('text', '')}")
        lines.extend(["", f"## {h_proposal}", session["proposal"], "", f"## {h_votes}"])
        for v in session["votes"]:
            lines.append(f"- **{v.get('speaker') or v.get('persona_id', '')}**: {v.get('vote', '')} - {v.get('reason', '')}")
        lines.extend(["", f"## {h_summary}", session["summary"]])
        return "\n".join(lines) + "\n"
    return json.dumps(session, indent=2, ensure_ascii=False)



def council_mode(council: dict[str, Any]) -> str:
    """DERIVE a council's shape (no closed vocabulary, no stored type): `decision` (a proposal put to a
    vote — For/Against), `evaluation` (a concept/proposal reacted to conversationally, no hard vote), or
    `discovery` (open user-research questions → answers). spec/methodology-and-clarity-redesign.md Q2."""
    has_prop = bool((council.get("proposal") or "").strip())
    has_votes = bool(council.get("votes"))
    if has_prop and has_votes:
        return "decision"
    if has_prop:
        return "evaluation"
    return "discovery"


def council_form(council: dict[str, Any]) -> str:
    """Classify an existing CouncilSession through the primitive/form registry.

    Stored data stays unchanged: specialized formats still ride their current
    blocks (`head_to_head`, `red_team`, `price_ladder`, `ideation`) and base
    councils still derive from proposal/votes. This helper is the bridge from
    historic product aliases to structural form ids.
    """
    stamped = council.get("form") or {}
    if stamped.get("primitive") == "council" and stamped.get("id"):
        form = _taxonomy_registry.resolve_form("council", str(stamped["id"]))
        if form is not None:
            return str(form["id"])
    for marker, alias in (
        ("head_to_head", "head_to_head"),
        ("red_team", "red_team"),
        ("price_ladder", "price_ladder"),
        ("ideation", "ideation"),
    ):
        if council.get(marker):
            form = _taxonomy_registry.resolve_form("council", alias)
            return str((form or {}).get("id") or alias)
    mode = council_mode(council)
    form = _taxonomy_registry.resolve_form("council", mode)
    return str((form or {}).get("id") or mode)


def council_form_definition(council: dict[str, Any]) -> dict[str, Any]:
    form_id = council_form(council)
    form = _taxonomy_registry.resolve_form("council", form_id)
    if form is None:
        raise KeyError(f"No registered council form '{form_id}'")
    return form


def _validate_council_form_payload(form: dict[str, Any], payload: dict[str, Any]) -> None:
    if not isinstance(payload, dict):
        raise ValueError("payload must be a dict")
    renderer = form.get("renderer") or {}
    if not renderer.get("library") or not renderer.get("detail"):
        raise ValueError(f"council form {form.get('id')} lacks a compatible renderer")
    required = (form.get("schema") or {}).get("required") or []
    missing = [field for field in required if field not in payload]
    if missing:
        raise ValueError(f"payload for council/{form.get('id')} missing required fields: {', '.join(missing)}")


def record_council_form(project_id: str, form_id: str, payload: dict[str, Any],
                        persona_ids: list[str], prompt: str = "",
                        summary: str = "", exec_summary: str = "",
                        selection_reason: str = "", key: str | None = None,
                        findings: list | None = None, created_at: str | None = None,
                        store: Store | None = None) -> dict[str, Any]:
    """Record a registered council form through one generic API.

    Existing specialized tools remain wrappers/presets over the same persisted
    CouncilSession shape. This function validates the requested form against the
    registry, normalizes the payload into `record_council`, and stamps form
    metadata so readers can distinguish structural form from historic mode.
    """
    store = store or Store()
    form = _taxonomy_registry.resolve_form("council", form_id)
    if form is None:
        raise KeyError(f"No registered council form '{form_id}'")
    _validate_council_form_payload(form, payload)
    canonical = str(form["id"])
    structural = str(form.get("extends") or canonical)
    prompt = str(prompt or payload.get("prompt") or payload.get("proposal") or "Council form").strip()
    statements = payload.get("statements") or []
    questions = payload.get("questions") or []
    proposal = str(payload.get("proposal") or "")
    votes = payload.get("votes") or []

    def _stamp(session: dict[str, Any]) -> dict[str, Any]:
        stored = store.get_council_session(session["id"]) or dict(session)
        stored["form"] = {"primitive": "council", "id": canonical, "label": form.get("label", ""),
                          "source": "generic"}
        stored["form_payload"] = dict(payload)
        store.insert_council_session(stored)
        return {**stored, "url": web_url(f"/councils/{stored['id']}"),  # noqa: F821 (bound)
                "project_url": web_url(f"/projects/{project_id}")}  # noqa: F821 (bound)

    # For built-in structured forms, delegate to the existing recorders so the
    # specialized blocks are complete (result/case_against/derived ladder/etc.).
    # A partial `head_to_head` or `red_team` marker would trigger detail renderers
    # that expect the deterministic aggregate to be present.
    if structural == "option_comparison":
        return _stamp(record_head_to_head(  # noqa: F821 (bound after services package import)
            project_id, prompt, payload.get("options") or [], payload.get("preferences") or [],
            persona_ids, statements=statements, summary=summary, exec_summary=exec_summary,
            selection_reason=selection_reason, findings=findings, key=key,
            variant_meta=payload.get("variant_meta"), created_at=created_at, store=store))
    if structural == "objection_review":
        return _stamp(record_red_team(  # noqa: F821
            project_id, prompt, objections=payload.get("objections") or [],
            endorsements=payload.get("endorsements") or [],
            stance=str(payload.get("stance") or payload.get("stance_mode") or "against"),
            persona_ids=persona_ids, statements=statements, summary=summary,
            exec_summary=exec_summary, selection_reason=selection_reason,
            findings=findings, key=key, created_at=created_at, store=store))
    if structural == "ladder_review":
        return _stamp(record_price_ladder(  # noqa: F821
            project_id, prompt, payload.get("price_points") or payload.get("rungs") or [],
            responses=payload.get("responses") or [], persona_ids=persona_ids,
            statements=statements, summary=summary, exec_summary=exec_summary,
            selection_reason=selection_reason, findings=findings, key=key,
            created_at=created_at, store=store))
    if structural == "idea_review":
        return _stamp(record_ideation_summary(  # noqa: F821
            project_id, str(payload.get("problem") or prompt),
            payload.get("shortlist") or [], statements=statements, summary=summary,
            exec_summary=exec_summary, selection_reason=selection_reason,
            key=key, created_at=created_at, store=store))

    if structural == "open_discussion":
        questions = questions or [prompt]
    elif structural == "proposal_reaction":
        if not proposal:
            proposal = prompt
    elif structural == "vote":
        if not proposal:
            proposal = prompt

    out = record_council(
        project_id, prompt, persona_ids, statements=statements, votes=votes,
        proposal=proposal, summary=summary, exec_summary=exec_summary,
        selection_reason=selection_reason or f"generic council form: {canonical}",
        questions=questions, key=key, findings=findings, created_at=created_at, store=store)
    return _stamp(out)


def record_council(project_id: str, prompt: str, persona_ids: list[str],
                   statements: list | None = None, votes: list[dict[str, Any]] | None = None,
                   proposal: str = "", summary: str = "", exec_summary: str = "",
                   selection_reason: str = "", questions: list[str] | None = None,
                   key: str | None = None, findings: list | None = None,
                   prompts: list | None = None, predictions: list | None = None,
                   created_at: str | None = None,
                   store: Store | None = None) -> dict[str, Any]:
    """Persist a host-authored council. A council is a research artefact and MUST live inside a research
    project — `project_id` is required and validated. Author the voices as `statements` (the ONE voice
    primitive: {persona_id, text, stance, about:{kind:'prompt',id}, refs}); set `questions` (discovery) or
    `proposal`(+`votes` for a decision) to shape the mode. `findings`/`prompts` are optional. Pass a stable
    `key` for a DETERMINISTIC id (idempotent upsert → resumable runs; spec/harness-evaluation HX6)."""
    store = store or Store()
    project = _require_research_project(store, project_id)  # fail fast if no/unknown project
    existing = store.get_council_session(stable_id("council", key)) if key else None
    cid = stable_id("council", key) if key else stable_id("council", prompt, utc_now_iso())

    def _nvote(v):
        # A vote IS a stance (stance_scale.json — the ONE positivity vocabulary): `vote` stores the
        # canonical term, `stance` the resolved {value,label}; an unresolvable token survives as
        # stance.label_raw — never silently dropped or coerced without trace.
        v = dict(v) if isinstance(v, dict) else {"vote": str(v)}
        st = _artifacts.validate_stance(v.get("vote") or v.get("stance") or v.get("label"))
        if st:
            v["vote"], v["stance"] = st["label"], st
        return v

    votes = [_nvote(v) for v in (votes or [])]
    qs = [str(q).strip() for q in (questions or []) if str(q).strip()]
    # Primitives-only: statements are the ONE voice representation; prompts are built from the council's
    # canonical question/proposal fields when not authored explicitly.
    statements_out = [_artifacts.validate_statement(s) for s in (statements or [])]
    nat_prompts = [_artifacts.validate_prompt(p) for p in (prompts or [])]
    prompts_out = nat_prompts or _artifacts.council_prompts(
        {"prompt": prompt, "questions": qs, "proposal": proposal})
    findings_out = [_artifacts.validate_finding(f) for f in (findings or [])]
    # Stable part ids so other artifacts can cross-reference these statements/findings + the UI can
    # deep-link to them (spec/artifact-cross-references.md). Prompts keep their semantic ids (q0/proposal).
    # Predicted behaviors (ticket behavioral-prediction-output): concrete actions, not sentiment —
    # canonical likelihood + evidence refs; stamp persona_id so segment aggregation can attribute.
    predictions_out = [_artifacts.validate_predicted_behavior(pb) for pb in (predictions or [])]
    _artifacts.assign_part_ids(statements_out, "st")
    _artifacts.assign_part_ids(findings_out, "f")
    _artifacts.assign_part_ids(prompts_out, "p")
    _artifacts.assign_part_ids(predictions_out, "pb")
    session = CouncilSession(
        id=cid,
        prompt=prompt, persona_ids=persona_ids, selection_reason=selection_reason or "host-authored",
        proposal=proposal, votes=votes, summary=summary,
        exec_summary=exec_summary, questions=qs,
        created_at=(existing or {}).get("created_at") or created_at or utc_now_iso(),
        project_id=project["id"],
        statements=statements_out,
        findings=findings_out,
        prompts=prompts_out,
    ).to_dict()
    if predictions_out:
        session["predictions"] = predictions_out
    store.insert_council_session(session)
    # Register the council on its project so the project owns it directly (idempotent).
    council_ids = project.setdefault("council_ids", [])
    if cid not in council_ids:
        council_ids.append(cid)
        project["updated_at"] = utc_now_iso()
        store.upsert_research_project(project)
    emit_lifecycle_event("council.recorded", {"council_id": cid, "project_id": project["id"],  # noqa: F821 (bound)
                                              "prompt": prompt, "persona_ids": persona_ids,
                                              "statements": len(statements_out), "votes": len(votes)}, store)
    # Soft pre-flight on the RESPONSE only (never stored, never blocking — a thin cohort can be
    # intentional): a "memory-grounded" council over participants with zero simulated memory is
    # ungrounded by construction; say so at record time, not first in assess_project's gap tail.
    warnings: list[str] = []
    try:
        m = store.count_memory_for_personas(persona_ids)
        if persona_ids and m["facts"] + m["events"] == 0:
            warnings.append(
                "participants have ZERO simulated memory (0 facts/events) — this council is "
                "ungrounded; deepen the cohort (simulate-cohort) before relying on it")
    except Exception:
        pass
    # Same soft contract for governance: remote hosts demonstrably record outside the governed
    # loop, leaving the plan untouched ('runs stalled') while evidence piles up beside it. The
    # graph absorbs such councils (plan_graph), but gates/assessments only stay honest inside
    # the loop — say so here, where the host is still listening.
    try:
        from ..plan_assess import project_run_state
        rs = project_run_state(project["id"], store=store)
        if rs and rs.get("state") == "stalled":
            warnings.append(
                "recorded OUTSIDE the governed run loop — the project's plan has ready work and "
                f"no active run ({rs.get('note', '')}); drive councils via start_run → run_step → "
                "checkpoint_step so plan gates and assess_project stay honest")
    except Exception:
        pass
    # The links a remote agent hands the user: the council's own page + its project (absent
    # before, so an agent that just ran a council couldn't say WHERE to see it).
    out = {**session, "url": web_url(f"/councils/{cid}"),  # noqa: F821 (bound)
           "project_url": web_url(f"/projects/{project['id']}")}  # noqa: F821 (bound)
    if warnings:
        out["warnings"] = warnings
    return out



def get_council(session_id: str, store: Store | None = None) -> dict[str, Any]:
    store = store or Store()
    c = store.get_council_session(session_id)
    if not c:
        raise KeyError(f"Unknown council session: {session_id}")
    out = {**c, "url": web_url(f"/councils/{c['id']}")}  # noqa: F821 (bound)
    if c.get("project_id"):
        out["project_url"] = web_url(f"/projects/{c['project_id']}")  # noqa: F821 (bound)
    return out



def list_councils(store: Store | None = None) -> list[dict[str, Any]]:
    store = store or Store()
    return [{"id": c["id"], "prompt": c["prompt"], "created_at": c["created_at"],
             "url": web_url(f"/councils/{c['id']}"),  # noqa: F821 (bound)
             "personas": len(c.get("persona_ids", [])), "turns": len(_artifacts.council_statements(c)),
             "votes": _artifacts.vote_tally(c.get("votes", []))}
            for c in store.list_council_sessions()]


# ===================================================================== #
# Research graph: Project container + typed study edges + theme tags +   #
# open questions + frontier. A Study(=Synthesis) is a node; councils sit  #
# inside a node. See spec/research-graph-and-meta-report.md.              #
# ===================================================================== #



def delete_council(session_id: str, store: Store | None = None) -> dict[str, Any]:
    """Delete a council session. Syntheses keep their council_id reference (harmless)."""
    store = store or Store()
    return {"deleted": store.delete_council_session(session_id)}
