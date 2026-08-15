"""Syntheses (study arcs) — including project-scope reports (a report IS a synthesis).

Split out of the original sonaloop/services.py (behavior-preserving).
Cross-module function references are bound at import time by services/__init__.py."""

from __future__ import annotations

import csv
import hashlib
import json
import random
import uuid
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any

from ..config import (
    utc_now_iso, content_language, ensure_content_language, language_instruction,
    critic_threshold, critic_sample_k,
)
from ._authoring import MARKDOWN_CONTRACT, PRIMITIVES_CONTRACT
from .. import artifacts as _A
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
from ..research_integrity import apply_claim_postures, claim_posture_markdown
from ..report_handoff import report_handoff_state, terminal_synthesis_source_ids
from .._project_locks import project_lifecycle_locks
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
from ._synthesis_share import (
    PDF_FONTS as _PDF_FONTS,
    SHARE_LABELS as _SHARE_LABELS,
    share_inline_images as _share_inline_images_impl,
    share_rewrite_links as _share_rewrite_links,
    theme_block as _theme_block,
)
from ._report_sources import (
    bound_report_outline_frame,
    bound_report_sources,
    report_source_compact as _study_compact,
    report_source_full as _study_full,
)


from ._common import *  # noqa: F401,F403  (shared helpers + constants)


_SHARE_INLINE_MAX_BYTES = 8 * 1024 * 1024


def _share_inline_images(html_text: str, missing_label: str = "media unavailable", *,
                         store: Store | None = None, project_id: str = "") -> str:
    """Compatibility seam retaining the historically monkeypatchable size budget."""
    return _share_inline_images_impl(html_text, missing_label, store=store, project_id=project_id,
                                     max_bytes=_SHARE_INLINE_MAX_BYTES)



def _council_brief_row(store: Store, cid: str) -> dict[str, Any]:
    c = store.get_council_session(cid)
    if not c:
        return {"council_id": cid, "missing": True}
    # Per-persona material so the host can author the `voices` layer (who/why) — from the statements.
    turns = [{"persona_id": st.get("persona_id"), "stance": (st.get("stance") or {}).get("label"),
              "content": st.get("text")}
             for st in _A.council_statements(c)]
    votes = [{"persona_id": v.get("persona_id"), "speaker": v.get("speaker"),
              "vote": v.get("vote"), "reason": v.get("reason")}
             for v in c.get("votes", [])]
    return {
        "council_id": cid, "prompt": c.get("prompt"), "created_at": c.get("created_at"),
        "exec_summary": c.get("exec_summary") or c.get("summary"),
        "vote_tally": _A.vote_tally(c.get("votes", [])),   # canonical stance terms (votes ARE stances)
        "turns": turns, "votes": votes,
        "proposal": c.get("proposal"),
    }



def _synthesis_provenance(store: Store, council_ids: list[str], topic: str | None) -> dict[str, Any]:
    """Assemble inline-citable provenance for a synthesis: attached real evidence and
    relevant recalled facts (each with a stable id) for every persona in the chain.
    This is what lets generated conclusions cite their source (recall hits + evidence)."""
    persona_ids: list[str] = []
    for cid in council_ids:
        c = store.get_council_session(cid) or {}
        for pid in c.get("persona_ids", []) or []:
            if pid not in persona_ids:
                persona_ids.append(pid)
    evidence: list[dict[str, Any]] = []
    recall: list[dict[str, Any]] = []
    for pid in persona_ids:
        persona = store.get_persona(pid) or {}
        name = persona.get("display_name", pid)
        for ev in store.list_evidence(pid)[:6]:
            evidence.append({"ref": ev["id"], "persona": name, "kind": "evidence",
                             "source_type": ev.get("source_type"),
                             "quote": str(ev.get("content_or_path", ""))[:400]})
        if topic and str(topic).strip():
            try:
                hits = memory_mod.recall(store, pid, topic, k=2).get("hits", [])
            except Exception:
                hits = []
            for h in hits:
                recall.append({"ref": h.get("id", ""), "persona": name, "kind": "recall",
                               "quote": str(h.get("text") or h.get("fact") or "")[:400]})
    return {"evidence": evidence[:30], "recall": recall[:30]}



def brief_synthesis(council_ids: list[str], title: str | None = None, start_input: str | None = None,
                    goal: str | None = None, store: Store | None = None) -> dict[str, Any]:
    """GATHER an ordered chain of councils so the host can author a synthesis."""
    store = store or Store()
    chain = [_council_brief_row(store, cid) for cid in council_ids]
    frame = {
        "title": title, "goal": goal, "start_input": start_input,
        "councils_in_order": chain,
        "provenance": _synthesis_provenance(store, council_ids, goal or start_input or title),
    }
    return {"schema": "synthesis", "council_ids": council_ids,
            "instructions": build_synthesis_prompt(frame) + MARKDOWN_CONTRACT + PRIMITIVES_CONTRACT, "frame": frame}



def record_synthesis(title: str, start_input: str, council_ids: list[str] | None = None,
                     payload: dict[str, Any] | None = None,
                     goal: str = "", synthesis_id: str | None = None, key: str | None = None,
                     predictions: list | None = None, project_id: str = "",
                     created_at: str | None = None, store: Store | None = None,
                     dispatch_token: str | None = None) -> dict[str, Any]:
    """Persist a host-authored synthesis. A synthesis is a FIRST-CLASS answer/report node and is
    DECOUPLED from councils: `council_ids` is an OPTIONAL list of referenced evidence and may be
    empty — e.g. an affinity-clustering synthesis over observations, a synthesis over other
    syntheses, or a standalone analysis. Councils are independent nodes a synthesis MAY cite (via
    `references`/`citations`/`voices`); they are not sub-parts of it. Pass `project_id` when the
    synthesis answers one project's inquiry so the project graph lists it (a synthesis citing
    only that project's councils is absorbed even without it).

    For the iterative driver loop: pass the SAME synthesis_id each round to update
    one growing study arc in place (chain + interim learnings + next_council_question).
    """
    store = store or Store()
    council_ids = list(council_ids or [])
    if dispatch_token and not project_id:
        owners = {str((store.get_council_session(cid) or {}).get("project_id") or "")
                  for cid in council_ids}
        owners.discard("")
        if len(owners) == 1:
            project_id = owners.pop()
    if project_id:                       # validated ownership, never a dangling ref
        project_id = _require_research_project(store, project_id)["id"]
    payload_fingerprint = canonical_payload_fingerprint({  # noqa: F821 (bound)
        "title": title, "start_input": start_input, "council_ids": council_ids,
        "payload": payload or {}, "goal": goal, "synthesis_id": synthesis_id or "",
        "predictions": predictions or [], "project_id": project_id,
        "created_at": created_at or "",
    })
    dispatch_ctx = (prepare_dispatch_write(  # noqa: F821 (bound)
        project_id, dispatch_token, key, "synthesis", store,
        allowed_buckets={"act", "verify"}, payload_fingerprint=payload_fingerprint) if project_id else
        {"state": "outside_run", "operation_id": str(key or ""), "key": str(key or "")})
    effective_key = str(dispatch_ctx.get("primitive_key") or key or "") or None
    if effective_key and not synthesis_id:  # deterministic id → idempotent resumable upsert (HX6)
        synthesis_id = stable_id("synthesis", effective_key)
    data = validate_synthesis_payload(payload or {})
    _pl = payload or {}
    # Primitives-only authoring (spec/unified-artifact-schema): the host authors findings/statements/
    # prompts directly — the ONE representation. No compatibility list/voice input shapes.
    findings = [_A.validate_finding(f) for f in (_pl.get("findings") or [])]
    statements = [_A.validate_statement(s) for s in (_pl.get("statements") or [])]
    prompts = [_A.validate_prompt(p) for p in (_pl.get("prompts") or [])]
    # Stable part ids so findings/voices are addressable + deep-linkable (spec/artifact-cross-references).
    _A.assign_part_ids(findings, "f")
    _A.assign_part_ids(statements, "st")
    _A.assign_part_ids(prompts, "p")
    posture: dict[str, Any] = {}
    if project_id:
        statements, findings, posture = apply_claim_postures(
            project_id, statements, findings, _pl.get("claims") or [], store,
            prose_present=bool(str(data.get("arc_narrative") or "").strip()
                               or str(data.get("gesamtbild") or "").strip()
                               or str(data.get("positionierung") or "").strip()),
        )
    existing = store.get_synthesis(synthesis_id) if synthesis_id else None
    existing_fingerprint = str(((existing or {}).get("dispatch_provenance") or {}).get(
        "payload_fingerprint") or "")
    if (project_id and dispatch_ctx.get("dispatch_token") and existing
            and existing_fingerprint == payload_fingerprint):
        dispatch_result = bind_dispatch_output(  # noqa: F821 (bound)
            dispatch_ctx, {"kind": "synthesis", "id": existing["id"]},
            "recorded synthesis evidence", store)
        return {
            **existing, "idempotent_replay": True,
            "url": web_url(f"/syntheses/{existing['id']}"),  # noqa: F821 (bound)
            "project_url": web_url(f"/jobs/{project_id}"),  # noqa: F821 (bound)
            "dispatch": dispatch_result,
        }
    # honor an explicit/keyed synthesis_id even on first create (so a keyed run is idempotent)
    sid = (existing or {}).get("id") or synthesis_id or stable_id("synthesis", title or "synthesis", utc_now_iso())
    created = (existing or {}).get("created_at") or created_at or utc_now_iso()
    prev = existing or {}
    rec = Synthesis(
        id=sid, title=title, start_input=start_input, council_ids=council_ids,
        arc_narrative=data["arc_narrative"], gesamtbild=data["gesamtbild"],
        positionierung=data["positionierung"], references=data["references"],
        created_at=created,
        goal=goal or prev.get("goal", ""),
        status=data["status"], next_council_question=data["next_council_question"],
        stop_reason=data["stop_reason"], iterations=len(council_ids),
        citations=data["citations"],
        # The findings/statements/prompts primitives; on an update that omits one, keep the prior value
        # so re-recording an arc in place doesn't wipe it.
        statements=statements or prev.get("statements", []),
        findings=findings or prev.get("findings", []),
        prompts=prompts or prev.get("prompts", []),
        scope=prev.get("scope", "convergence"),
        project_id=project_id or prev.get("project_id", ""),
        lead=prev.get("lead", ""),
        sections=prev.get("sections", []),
        graph_snapshot=prev.get("graph_snapshot"),
    ).to_dict()
    if project_id:
        from ..correlation import stamp_workflow_trace
        stamp_workflow_trace(rec, project_id)
    predictions_out = [_A.validate_predicted_behavior(pb) for pb in (predictions or [])]
    _A.assign_part_ids(predictions_out, "pb")
    rec["predictions"] = predictions_out or prev.get("predictions", [])
    if posture:
        rec["claim_posture"] = posture
    if project_id:
        rec["dispatch_provenance"] = {
            "state": dispatch_ctx.get("state", "outside_run"),
            **({"dispatch_token": dispatch_ctx["dispatch_token"],
                "run_id": dispatch_ctx["run_id"], "task_id": dispatch_ctx["task_id"],
                "operation_id": dispatch_ctx["operation_id"]}
               if dispatch_ctx.get("dispatch_token") else {}),
            **({"payload_fingerprint": payload_fingerprint,
                "payload_revision": int(dispatch_ctx.get("payload_revision") or 1)}
               if dispatch_ctx.get("dispatch_token") else {}),
        }
    rec["updated_at"] = utc_now_iso()
    store.upsert_synthesis(rec)
    dispatch_result = (bind_dispatch_output(  # noqa: F821 (bound)
        dispatch_ctx, {"kind": "synthesis", "id": sid}, "recorded synthesis evidence", store)
        if project_id else {"state": "outside_run", "checkpointed": False})
    emit_lifecycle_event("synthesis.recorded", {"synthesis_id": sid, "title": title,  # noqa: F821 (bound)
                                                "status": rec["status"], "council_ids": council_ids,
                                                "project_id": rec.get("project_id") or ""}, store)
    from ..telemetry import capture_product_event
    capture_product_event(
        "synthesis_recorded",
        project_id=str(rec.get("project_id") or ""),
        subject_kind="synthesis",
        subject_id=sid,
        properties={
            "council_count": len(council_ids),
            "scope": rec.get("scope") or "unknown",
            "status": rec.get("status") or "unknown",
        },
    )
    # Soft honesty signal (GAP-3): the synthesis IS the answer — flag (don't block) when it persists with
    # no prose AND no findings AND no voices, so the host notices a hollow answer node.
    out = dict(rec)
    out["url"] = web_url(f"/syntheses/{sid}")  # noqa: F821 (bound) — the report's own page to hand the user
    if rec.get("project_id"):
        out["project_url"] = web_url(f"/jobs/{rec['project_id']}")  # noqa: F821 (bound)
    out["dispatch"] = dispatch_result
    has_substance = any([rec["gesamtbild"].strip(), rec["positionierung"].strip(), rec["arc_narrative"].strip(),
                         rec["findings"], rec["statements"]])
    warnings: list[str] = []
    if posture and not posture.get("verified"):
        warnings.append(
            "UNVERIFIED_HYPOTHESIS_DRAFT: prose/claims are not fully evidence-postured; a Reaction "
            "Test cannot pass its terminal gate until unsupported/uncovered claims are repaired"
        )
    if not has_substance:
        warnings.append("SYNTHESIS_THIN: this synthesis persisted with no prose (gesamtbild/"
                        "positionierung) and no structured blocks (clusters/key_problems/ranking/"
                        "shortlist) — the answer node is near-empty. The synthesis IS the answer: "
                        "author it rich here, don't leave the substance only in councils/notes.")
    if rec.get("project_id"):           # governance parity with record_council
        try:
            from ..plan_assess import project_run_state
            rs = project_run_state(rec["project_id"], store=store)
            if rs and rs.get("state") == "stalled":
                warnings.append("recorded OUTSIDE the governed run loop — plan has ready work and no "
                                f"active run ({rs.get('note', '')}); drive via start_run → run_step → "
                                "checkpoint_step so gates and assess_project stay honest")
        except Exception:
            pass
    if warnings:
        out["warnings"] = warnings
    return out



def get_synthesis(synthesis_id: str, store: Store | None = None) -> dict[str, Any]:
    store = store or Store()
    syn = store.get_synthesis(synthesis_id)
    if not syn:
        raise KeyError(f"Unknown synthesis: {synthesis_id}")
    out = {**syn, "url": web_url(f"/syntheses/{syn['id']}")}  # noqa: F821 (bound)
    if syn.get("project_id"):
        out["project_url"] = web_url(f"/jobs/{syn['project_id']}")  # noqa: F821 (bound)
    return out



def list_syntheses(store: Store | None = None) -> list[dict[str, Any]]:
    store = store or Store()
    return [{**s, "url": web_url(f"/syntheses/{s['id']}")}  # noqa: F821 (bound)
            for s in store.list_syntheses()]


# Stakeholder-report headers follow the CONTENT language (de|en) so a German
# project gets a German report and an English project an English one.



_SYNTHESIS_EXPORT_LABELS = {
    "de": {
        "report_title": "Report",
        "arc_line": "Studien-Bogen aus {n} Councils · Status: {status} · erzeugt {date}.",
        "goal": "Ziel", "next_council": "Vorgeschlagener nächster Council (self-contained)",
        "stop_reason": "Abschlussgrund", "start": "Ausgangspunkt", "arc": "Bogen / Verlauf",
        "big_picture": "Gesamtbild", "recommendations": "Handlungsempfehlungen",
        "effort": "Aufwand", "value": "Nutzen", "positioning": "Positionierung",
        "q_quick": "Quick Wins", "q_big": "Big Bets", "q_fill": "Lückenfüller", "q_sink": "Zeitfresser",
        "pain_solvers": "Validierte Pain-Solver / Delight-Engines", "segments": "Segmente",
        "key_problems": "Kernprobleme", "clusters": "Affinity-Cluster",
        "ranking": "Ranking", "shortlist": "Shortlist",
        "voices": "Stimmen (pro Persona)", "relevance": "Relevanz", "argument": "Argument",
        "shift": "Wandel", "open_questions": "Offene Fragen / Nächste Studie",
        "sources": "Quellen (Councils in Reihenfolge)",
        # deck (PPTX) slide labels — UX V11
        "verdict": "Fazit", "exec_summary": "Executive Summary",
        "sentiment": "Stimmungsbild", "stance_dist": "Haltung der Wortbeiträge",
        "voices_h": "Stimmen", "details_in_report": "Details im vollständigen Report",
        "votes_w": "Votes", "contributions_w": "Wortbeiträge", "councils_w": "Councils",
        "st_2": "Befürwortend", "st_1": "Bedingt", "st_0": "Neutral",
        "st_-1": "Skeptisch", "st_-2": "Ablehnend",
    },
    "en": {
        "report_title": "Report",
        "arc_line": "Study arc across {n} councils · status: {status} · generated {date}.",
        "goal": "Goal", "next_council": "Proposed next council (self-contained)",
        "stop_reason": "Stop reason", "start": "Starting point", "arc": "Arc / trajectory",
        "big_picture": "Overall picture", "recommendations": "Recommendations",
        "effort": "Effort", "value": "Value", "positioning": "Positioning",
        "q_quick": "Quick wins", "q_big": "Big bets", "q_fill": "Fill-ins", "q_sink": "Time sinks",
        "pain_solvers": "Validated pain-solvers / delight-engines", "segments": "Segments",
        "key_problems": "Key problems", "clusters": "Affinity clusters",
        "ranking": "Ranking", "shortlist": "Shortlist",
        "voices": "Voices (per persona)", "relevance": "Relevance", "argument": "Argument",
        "shift": "Shift", "open_questions": "Open questions / Next study",
        "sources": "Sources (councils in order)",
        # deck (PPTX) slide labels — UX V11
        "verdict": "Verdict", "exec_summary": "Executive summary",
        "sentiment": "Sentiment", "stance_dist": "Stance of the contributions",
        "voices_h": "Voices", "details_in_report": "Details in the full report",
        "votes_w": "votes", "contributions_w": "contributions", "councils_w": "councils",
        "st_2": "Support", "st_1": "Conditional", "st_0": "Neutral",
        "st_-1": "Skeptical", "st_-2": "Oppose",
    },
}



def export_synthesis(synthesis_id: str, format: str = "md", store: Store | None = None) -> str:
    """Render the synthesis as a stakeholder report (Markdown), referencing each council."""
    store = store or Store()
    syn = get_synthesis(synthesis_id, store)
    if syn.get("scope") == "project":      # a report → the report exporter (one export across scopes)
        return export_report(syn.get("project_id", ""), report_id=synthesis_id, format=format, store=store)
    if format == "json":
        return json.dumps(syn, indent=2, ensure_ascii=False)
    role = {r["council_id"]: r.get("role", "") for r in syn.get("references", [])}
    status = syn.get("status", "done")
    L = _SYNTHESIS_EXPORT_LABELS[content_language()]
    lines = [f"# {L['report_title']}: {syn['title']}", "",
             f"*{L['arc_line'].format(n=len(syn['council_ids']), status=status, date=syn['created_at'])}*", ""]
    lines += claim_posture_markdown(syn.get("claim_posture"),
                                    de=content_language() == "de")
    if syn.get("goal"):
        lines += [f"## {L['goal']}", syn["goal"], ""]
    if status == "in_progress" and syn.get("next_council_question"):
        lines += [f"## {L['next_council']}", syn["next_council_question"], ""]
    if status == "done" and syn.get("stop_reason"):
        lines += [f"## {L['stop_reason']}", syn["stop_reason"], ""]
    lines += [f"## {L['start']}", syn.get("start_input", ""), "",
             f"## {L['arc']}", syn.get("arc_narrative", ""), "",
             f"## {L['big_picture']}", syn.get("gesamtbild", ""), "",
             f"## {L['recommendations']}"]
    # Report blocks are reconstructed from the stored findings/statements (storage is primitives-only).
    _fs = _A.synthesis_findings(syn)
    def _fmeta(kind, key):  # collect a meta value across findings of a kind
        return [( (f.get("meta") or {}).get(key, ""), f.get("text", "")) for f in _fs if f.get("kind") == kind]
    recs = _A.synthesis_recommendations(syn)
    lines += [f"{i}. " + (f"{txt} _({L['effort']} {a}/5 · {L['value']} {n}/5)_" if a and n else txt)
              for i, (txt, a, n) in enumerate(recs, 1)] or ["—"]
    lines += ["", f"## {L['positioning']}", syn.get("positionierung", "")]
    # Structured convergence blocks (GAP-3): render when present so the methodology's converge output
    # (key problems / affinity clusters / down-select ranking + shortlist) survives into the report.
    if _A.finding_texts(syn, "key_problem"):
        lines += ["", f"## {L['key_problems']}"] + [f"- {x}" for x in _A.finding_texts(syn, "key_problem")]
    if _fmeta("cluster", "detail"):
        lines += ["", f"## {L['clusters']}"] + [f"- **{label}** — {insight}" for insight, label in _fmeta("cluster", "detail")]
    if _fmeta("ranking", "detail"):
        lines += ["", f"## {L['ranking']}"] + [f"- **{ref}**: {rat}" for rat, ref in _fmeta("ranking", "detail")]
    if _A.finding_texts(syn, "shortlist"):
        lines += ["", f"## {L['shortlist']}"] + [f"- {x}" for x in _A.finding_texts(syn, "shortlist")]
    lines += ["", f"## {L['pain_solvers']}"]
    lines += [f"- {x}" for x in _A.finding_texts(syn, "pain_solver")] or ["—"]
    lines += ["", f"## {L['segments']}"]
    lines += [f"- **{seg}**: {why}" for why, seg in _fmeta("segment", "detail")] or ["—"]
    voices = _A.synthesis_statements(syn)
    if voices:
        lines += ["", f"## {L['voices']}"]
        for v in sorted(voices, key=lambda x: -((x.get("stance") or {}).get("value", 0))):
            name = store.get_persona(v.get("persona_id", "")) or {}
            head = f"- **{name.get('name') or v.get('persona_id','')}**"
            if v.get("relevance"):
                head += f" — {L['relevance']}: {v['relevance']}"
            lines.append(head)
            if v.get("text"):
                lines.append(f"  - {L['argument']}: {v['text']}")
            sh = v.get("shift")
            if sh and (sh.get("trigger") or sh.get("to")):
                lines.append(f"  - {L['shift']}: {sh.get('from','')}→{sh.get('to','')} — {sh.get('trigger','')}")
            for e in v.get("refs", []):
                if e.get("kind") == "council" and e.get("quote"):
                    lines.append(f"  - „{e.get('quote','')}“ [{e.get('id','')}]")
    lines += ["", f"## {L['open_questions']}"]
    lines += [f"- {x}" for x in _A.finding_texts(syn, "open_question")] or ["—"]
    cites = syn.get("citations", [])
    if cites:
        cite_label = "Belege (Evidenz / Recall)" if content_language() == "de" else "Citations (evidence / recall)"
        lines += ["", f"## {cite_label}"]
        for c in cites:
            q = f" — „{c['quote']}“" if c.get("quote") else ""
            lines.append(f"- [{c.get('kind','')}:{c.get('ref','')}]{q}")
    lines += ["", f"## {L['sources']}"]
    for cid in syn["council_ids"]:
        c = store.get_council_session(cid)
        prompt = (c.get("prompt") if c else cid)
        lines.append(f"- `{cid}` — {role.get(cid, '')}".rstrip(" —") + (f"  ·  {prompt}" if prompt else ""))
    return "\n".join(lines) + "\n"


# ===================================================================== #
# Council write-back + reads (MCP parity for host-authored councils).    #
# Lets the run-council / synthesize skills persist via MCP instead of    #
# writing the store directly.                                            #
# ===================================================================== #



def delete_synthesis(synthesis_id: str, store: Store | None = None) -> dict[str, Any]:
    """Delete a synthesis (study) and detach it from any project graphs that contain it."""
    store = store or Store()
    detached = []
    for p in store.list_research_projects():
        if synthesis_id in (p.get("study_ids") or []):
            p["study_ids"].remove(synthesis_id)
            p.get("study_tags", {}).pop(synthesis_id, None)
            p["updated_at"] = utc_now_iso()
            store.upsert_research_project(p)
            detached.append(p["id"])
    return {"deleted": store.delete_synthesis(synthesis_id), "detached_from_projects": detached}



def brief_synthesis_outline(project_id: str, store: Store | None = None) -> dict[str, Any]:
    """GATHER the whole project graph + each study's compact content so the host can
    author the project REPORT outline (then author its sections)."""
    store = store or Store()
    graph = get_project_graph(project_id, store=store)
    tags = _require_research_project(store, project_id).get("study_tags", {})
    pinned_sources = terminal_synthesis_source_ids(graph)
    if not pinned_sources:
        pinned_sources = next(([source_id] for source_id in reversed(graph["build_order"])
                               if str(source_id).startswith("synthesis:")), [])
    studies, source_budget = bound_report_sources(
        [_study_compact(store, sid, tags.get(sid, [])) for sid in graph["build_order"]],
        max_chars=12_000, pinned_source_ids=pinned_sources)
    frame, visible_ids = bound_report_outline_frame(
        graph, studies, source_budget, pinned_source_ids=pinned_sources)
    return {"project_id": graph["project"]["id"], "schema": "synthesis_outline",
            "study_ids": visible_ids, "study_ids_total": len(graph["build_order"]),
            "instructions": build_synthesis_outline_prompt(frame) + MARKDOWN_CONTRACT, "frame": frame}



def _latest_report(store: Store, project_id: str, report_id: str | None) -> dict[str, Any]:
    if report_id:
        r = store.get_report(report_id)
        if not r:
            raise KeyError(f"Unknown report: {report_id}")
        if str(r.get("project_id") or "") != project_id:
            raise ValueError("REPORT_SCOPE_MISMATCH: report does not belong to project")
        return r
    reports = store.list_reports(project_id)
    if not reports:
        raise KeyError(f"No report for project {project_id} — run brief_synthesis_outline -> record_synthesis_outline first.")
    return reports[0]



def brief_synthesis_section(project_id: str, section_id: str, report_id: str | None = None,
                            store: Store | None = None) -> dict[str, Any]:
    """GATHER the full content of a section's source studies (+ their councils) so the
    host can author that section grounded with citations."""
    store = store or Store()
    project = _require_research_project(store, project_id)
    report = _latest_report(store, project["id"], report_id)
    section = next((s for s in report.get("sections", []) if s["id"] == section_id), None)
    if not section:
        raise KeyError(f"Unknown section {section_id} in report {report['id']}")
    studies, source_budget = bound_report_sources(
        [_study_full(store, sid) for sid in section.get("source_study_ids", [])])
    frame = {"heading": section["heading"], "intent": section.get("intent", ""), "theme_tags": section.get("theme_tags", []),
             "studies": studies, "source_budget": source_budget}
    return {"project_id": project["id"], "report_id": report["id"], "section_id": section_id,
            "schema": "synthesis_section", "instructions": build_synthesis_section_prompt(frame) + MARKDOWN_CONTRACT, "frame": frame}



def export_report(project_id: str, report_id: str | None = None, format: str = "md",
                  store: Store | None = None) -> str:
    """Assemble the report (outline + authored sections) into a stakeholder document."""
    store = store or Store()
    project = _require_research_project(store, project_id)
    report = _latest_report(store, project["id"], report_id)
    if format == "json":
        return json.dumps(report, indent=2, ensure_ascii=False)
    de = content_language() == "de"
    secs = report.get("sections", [])
    # readable titles for refs (study_ids are 'kind:id' graph refs; citations may be bare ids) — resolve
    # from the report's graph snapshot first, else look the id up in syntheses/councils.
    node_title = {n["study_id"]: (n.get("title") or "") for n in (report.get("graph_snapshot") or {}).get("nodes", [])}

    def _ref_title(ref: str) -> str:
        if node_title.get(ref):
            return node_title[ref]
        rid = ref.split(":", 1)[-1]
        s = store.get_synthesis(rid)
        if s:
            return s.get("title", rid)
        c = store.get_council_session(rid)
        if c:
            return (c.get("prompt") or rid)[:70]
        return rid

    n_studies = len({x for sec in secs for x in sec.get("source_study_ids", [])})
    lines = [f"# {report['title']}", "",
             f"*{'Report' if de else 'Report'} · {len(secs)} "
             f"{'Abschnitte' if de else 'sections'} · {n_studies} "
             f"{'Studien' if de else 'studies'} · {report['created_at'][:10]}*", ""]
    lines += claim_posture_markdown(report.get("claim_posture"), de=de)
    if report.get("limitations"):
        lines += [f"## {'Limitationen' if de else 'Limitations'}"]
        for limitation in report.get("limitations") or []:
            original = str(limitation.get("original_status") or "")
            rationale = str(limitation.get("rationale") or "")
            lines.append(
                f"- `cohort_integrity_override` · {original}: {rationale}"
            )
        lines.append("")
    if report.get("lead"):
        lines += [f"## {'Wie dieses Verständnis entstand' if de else 'How this understanding was built'}",
                  report["lead"], ""]
    for sec in secs:
        lines += [f"## {sec['heading']}"]
        if sec.get("markdown"):
            lines += [sec["markdown"]]
            if sec.get("citations"):
                lines += ["", f"*{'Belege' if de else 'Citations'}:*"]
                for c in sec["citations"]:
                    cc = f" · {_ref_title(c['council_id'])}" if c.get("council_id") else ""
                    q = f" — „{c['quote']}“" if c.get("quote") else ""
                    lines.append(f"- **{_ref_title(c['study_id'])}**{cc}{q}")
        else:
            lines += [f"_({'Abschnitt noch nicht verfasst' if de else 'section not yet authored'})_"]
        if sec.get("source_study_ids"):
            lines += ["", "_" + ("Quellen" if de else "Sources") + ": " +
                      ", ".join(_ref_title(x) for x in sec["source_study_ids"]) + "_"]
        lines += [""]
    # Decisions taken on this research close the report — what the work led to, on which
    # evidence, rejecting what (ticket decision-record-artifact).
    dec = decisions_section_md(project["id"], store=store, de=de)  # noqa: F821 (bound)
    if dec:
        lines += [dec.rstrip(), ""]
    return "\n".join(lines) + "\n"


# ===================================================================== #
# Shareable read-only report bundle (ticket shareable-report-bundle).    #
# The SAME inspector document (web/_report.render_report — one render    #
# path, also the PDF's source) exported as a self-contained static HTML  #
# directory under an unguessable token: data/export/share/<token>/.      #
# No auth, no server — the token-in-path is the share secret.            #
# ===================================================================== #

def export_synthesis_html(synthesis_id: str, out_dir: str | None = None,
                          store: Store | None = None,
                          theme_overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    """Export ANY report (synthesis) as a SHAREABLE, read-only static HTML bundle:
    `data/export/share/<token>/index.html` — the exact inspector document (one render path:
    web/_report.render_report) minus all app chrome, every asset inlined (CSS, charts, figures,
    avatars), zero external requests, opens from file://. Host the directory anywhere (S3, Pages,
    an intranet share); the unguessable token directory name is the share secret. `out_dir`
    overrides the parent directory but must stay inside the active data partition. `theme_overrides` (a
    customer theme per theming.validate_customer_theme) re-skins the bundle — a research
    deliverable carries the customer's brand, not Sonaloop's."""
    theme_css = _theme_block(theme_overrides)        # validate before any work
    store = store or Store()
    syn = get_synthesis(synthesis_id, store)
    # Import the web layer so render_report + every register_css() fragment it uses are live in
    # this process — the SAME assembly the inspector page and the PDF exporter draw from.
    from ..web import _components as _wc       # noqa: F401  (component + base CSS)
    from ..web import _synthesis as _ws        # noqa: F401  (convergence-view CSS)
    from ..web._report import render_report
    from ..web._html import collect_css
    from ..web_assets import CSS
    from .. import __version__
    from html import escape as _h_esc

    L0 = _SHARE_LABELS.get(content_language(), _SHARE_LABELS["en"])
    body = _share_inline_images(_share_rewrite_links(str(render_report(syn, store))),
                                missing_label=L0["missing"], store=store,
                                project_id=str(syn.get("project_id") or ""))

    # Footer stamp: project · generated date · sonaloop version — reproducible provenance.
    # Project resolution mirrors the inspector page, plus the cited councils as a fallback
    # (councils are project-scoped at creation; a decoupled synthesis inherits their project).
    proj = (store.get_research_project(syn["project_id"]) if syn.get("project_id")
            else parent_project_of_synthesis(synthesis_id, store))  # noqa: F821 (bound)
    for cid in (syn.get("council_ids") or []) if not proj else []:
        proj = parent_project_of_council(cid, store=store)          # noqa: F821 (bound)
        if proj:
            break
    L = L0
    stamp = " · ".join(x for x in [
        L["footer"],
        (f'{L["project"]}: {proj["title"]}' if proj else ""),
        f'{L["generated"]} {utc_now_iso()[:10]}',
        f"sonaloop {__version__}"] if x)
    footer = f'<footer class="share-foot">{_h_esc(stamp)}</footer>'

    share_css = (".share-unlinked{color:inherit}"
                 ".share-missing{color:var(--muted);font-size:var(--t-sm);font-style:italic}"
                 ".share-foot{max-width:780px;margin:48px auto 0;padding:14px 0;"
                 "border-top:1px solid var(--line);color:var(--muted);font-size:var(--t-sm)}")
    # No font/CDN <link>s (unlike the PDF's Google-Fonts head): the bundle makes ZERO requests;
    # Geist falls back to the system stack, the pixel font is already an inline data: woff2.
    doc = (f'<!doctype html><html lang="{content_language()}"><head><meta charset="utf-8">'
           f'<meta name="viewport" content="width=device-width,initial-scale=1">'
           f'<title>{_h_esc(syn.get("title", "Report"))}</title>'
           f"<style>{CSS}{collect_css()}{share_css}</style>{theme_css}</head>"
           f'<body><main class="content"><div class="page">{body}</div>{footer}</main></body></html>')

    token = uuid.uuid4().hex                  # unguessable slug — the path IS the share secret
    from ..config import partition_dir
    part = partition_dir()
    data_root = part.resolve()
    parent = Path(out_dir) if out_dir else part / "export" / "share"
    if not parent.is_absolute():
        parent = part / parent
    if not parent.resolve().is_relative_to(data_root):
        raise ValueError(f"export path escapes the data dir ({data_root}): {out_dir!r}")
    path = write_export(doc, parent / token / "index.html")
    return {"synthesis_id": syn["id"], "token": token, "dir": str(parent / token), "path": path,
            "url": export_download_url(path),  # noqa: F821 (bound) — the served /data link
            "title": syn.get("title", "")}


def export_synthesis_pdf(synthesis_id: str, store: Store | None = None,
                         theme_overrides: dict[str, Any] | None = None,
                         audience: str = "detailed") -> bytes:
    """Render ANY report (synthesis) to a self-contained PDF — the report HTML + the app's CSS through
    headless Chromium (print media), no running web server needed. Raises if the browser is absent.
    `theme_overrides` (a customer theme per theming.validate_customer_theme) re-skins the PDF."""
    theme_css = _theme_block(theme_overrides)        # validate before the browser gate
    from .. import browser as _browser
    if not _browser.available():
        raise RuntimeError("PDF export needs the headless browser (run `sonaloop setup` / "
                           "`playwright install chromium`).")
    store = store or Store()
    syn = get_synthesis(synthesis_id, store)
    # import the web layer so render_report + all register_css() styles are registered in this process
    from ..web import _components as _wc       # noqa: F401  (component + base CSS)
    from ..web import _synthesis as _ws        # noqa: F401  (convergence-view CSS)
    from ..web._report import render_report
    from ..web._html import collect_css
    from ..web_assets import CSS
    from html import escape as _h_esc
    # There is no live app origin while Chromium prints this temporary file.  Resolve local
    # /data refs and shared-Postgres opaque routes before printing so the PDF is self-contained.
    body = _share_inline_images(str(render_report(syn, store, audience=audience)), store=store,
                                project_id=str(syn.get("project_id") or ""))
    doc = (f'<!doctype html><html lang="{content_language()}"><head><meta charset="utf-8">'
           f'{_PDF_FONTS}<style>{CSS}{collect_css()}</style>{theme_css}</head>'
           f'<body><main class="content"><div class="page">{body}</div></main></body></html>')
    import os
    import tempfile
    from playwright.sync_api import sync_playwright
    title = _h_esc(syn.get("title", "Report"))
    _hf = "font-size:8px;color:#9aa0a6;width:100%;padding:0 16mm"
    with tempfile.TemporaryDirectory() as td:
        fp = os.path.join(td, "report.html")
        with open(fp, "w", encoding="utf-8") as fh:
            fh.write(doc)
        with sync_playwright() as pw:
            b = pw.chromium.launch()
            pg = b.new_page()
            pg.goto("file://" + fp, wait_until="networkidle")
            pg.emulate_media(media="print")
            pg.wait_for_timeout(250)
            pdf = pg.pdf(format="A4", print_background=True,
                         margin={"top": "18mm", "bottom": "16mm", "left": "16mm", "right": "16mm"},
                         display_header_footer=True,
                         header_template=f'<div style="{_hf}">{title}</div>',
                         footer_template=f'<div style="{_hf};text-align:center;padding:0">'
                                         f'<span class="pageNumber"></span> / <span class="totalPages"></span></div>')
            b.close()
    return pdf
