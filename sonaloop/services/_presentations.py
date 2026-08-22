"""Gather → author → persist service for report presentation plans."""
from __future__ import annotations

from typing import Any

from .. import result_schemas as _result_schemas
from ..config import utc_now_iso
from ..presentation import (
    PRESENTATION_KINDS,
    PRESENTATION_PLAN_SCHEMA,
    presentation_plan_qa,
    validate_presentation_plan,
)
from ..storage import Store
from ._common import *  # noqa: F401,F403


def _methodology_deck_profile(project: dict[str, Any], store: Store) -> dict[str, Any]:
    key = str(project.get("methodology") or "")
    if not key:
        return {}
    try:
        spec = get_methodology(key, store=store)  # noqa: F821 (bound)
    except Exception:
        return {}
    return dict((spec.get("presentation") or {}).get("deck") or {})


def _methodology_result_contract(project: dict[str, Any]) -> dict[str, Any]:
    key = str(project.get("methodology") or "")
    if not key:
        return {}
    try:
        contract = dict(_result_schemas.contract_for_methodology(key))
        contract["schemas"] = _result_schemas.schemas_for_methodology(key)
        return contract
    except KeyError:
        return {}


def brief_presentation(synthesis_id: str, audience: str = "stakeholder",
                       duration_minutes: int = 10,
                       store: Store | None = None) -> dict[str, Any]:
    """Gather the bounded evidence + method profile a host needs to author a deck plan."""
    store = store or Store()
    report = get_synthesis(synthesis_id, store)  # noqa: F821 (bound)
    project_id = str(report.get("project_id") or "")
    if not project_id:
        raise ValueError("presentation plans require a project-scope report")
    project = _require_research_project(store, project_id)  # noqa: F821 (bound)
    handoff = get_design_handoff(project_id, max_findings=36, max_voices=32, store=store)  # noqa: F821 (bound)
    cohort = []
    for row in handoff.get("cohort") or []:
        persona = store.get_persona(str(row.get("id") or "")) or {}
        cohort.append({**row, "avatar_available": bool((persona.get("avatar") or {}).get("path"))})
    handoff["cohort"] = cohort
    try:
        duration = max(1, min(180, int(duration_minutes)))
    except (TypeError, ValueError) as exc:
        raise ValueError("duration_minutes must be an integer") from exc
    return {
        "schema": "sonaloop.presentation_brief.v1",
        "report_id": report["id"],
        "project_id": project_id,
        "audience": str(audience or "stakeholder"),
        "duration_minutes": duration,
        "methodology": {
            "key": project.get("methodology", ""),
            "deck_profile": _methodology_deck_profile(project, store),
            "result_contract": _methodology_result_contract(project),
        },
        "evidence_bundle": handoff,
        "existing_plan": report.get("presentation_plan"),
        "instructions": [
            "Author a decision presentation, not a summary of report sections.",
            "Each core slide has one conclusion-led headline and an evidence-linked visual story.",
            "Show real stimuli, screens, personas, prototypes and observed transitions when available.",
            "Keep detailed profiles, raw response tables, methodology and source trails in the appendix.",
            "Speaker notes carry the talk track, evidence, caveats, transition and appendix pointers.",
            "Never present synthetic reactions as observed behavior of real customers; keep that limitation visible.",
            "Use the methodology deck profile as supporting guidance, never as permission to invent missing evidence.",
        ],
        "output_contract": {
            "schema": PRESENTATION_PLAN_SCHEMA,
            "supported_slide_kinds": list(PRESENTATION_KINDS),
            "required_top_level": ["title", "audience", "objective", "duration_minutes", "slides"],
            "slide_required": ["id", "kind", "headline", "speaker_notes"],
            "evidence_rule": "Every substantive core slide carries evidence_refs.",
            "speaker_notes": {
                "required": ["talk_track"],
                "recommended": ["takeaway", "evidence", "caveats", "transition", "backup", "timing_seconds"],
            },
        },
    }


def record_presentation_plan(synthesis_id: str, plan: dict[str, Any],
                             operation_id: str | None = None,
                             store: Store | None = None) -> dict[str, Any]:
    """Persist a reviewed brand-neutral deck plan on its project report."""
    store = store or Store()
    report = get_synthesis(synthesis_id, store)  # noqa: F821 (bound)
    if report.get("scope") != "project" or not report.get("project_id"):
        raise ValueError("presentation plans require a project-scope report")
    normalized = validate_presentation_plan(plan)
    operation_id = str(operation_id or "").strip()
    if len(operation_id) > 200 or (operation_id and not operation_id.isprintable()):
        raise ValueError("operation_id must be at most 200 printable characters")
    fingerprint = canonical_payload_fingerprint({  # noqa: F821 (bound)
        "synthesis_id": report["id"], "plan": normalized,
    })
    operations = [dict(row) for row in (report.get("presentation_operations") or [])
                  if isinstance(row, dict)]
    if operation_id:
        claimed = next((row for row in operations
                        if str(row.get("operation_id") or "") == operation_id), None)
        if claimed:
            if str(claimed.get("payload_fingerprint") or "") != fingerprint:
                raise ValueError("PRESENTATION_OPERATION_CONFLICT: operation_id was reused with different content")
            return {**report, "idempotent_replay": True,
                    "presentation_qa": presentation_plan_qa(report.get("presentation_plan") or {})}
    if str(report.get("presentation_plan_fingerprint") or "") == fingerprint:
        return {**report, "idempotent_replay": True,
                "presentation_qa": presentation_plan_qa(normalized)}
    now = utc_now_iso()
    if operation_id:
        operations.append({"operation_id": operation_id, "payload_fingerprint": fingerprint,
                           "recorded_at": now})
    updated = dict(report)
    updated.update({
        "presentation_plan": normalized,
        "presentation_plan_fingerprint": fingerprint,
        "presentation_plan_revision": int(report.get("presentation_plan_revision") or 0) + 1,
        "presentation_operations": operations,
        "presentation_qa": presentation_plan_qa(normalized),
        "updated_at": now,
    })
    store.upsert_synthesis(updated)
    from ..telemetry import capture_product_event
    capture_product_event(
        "presentation_planned",
        project_id=str(report.get("project_id") or ""),
        subject_kind="report",
        subject_id=report["id"],
        properties={
            "core_slides": len(normalized["slides"]),
            "appendix_slides": len(normalized["appendix"]),
            "audience": normalized["audience"],
            "qa_status": updated["presentation_qa"]["status"],
        },
        idempotency_key=fingerprint,
    )
    return {**updated, "idempotent_replay": False}
