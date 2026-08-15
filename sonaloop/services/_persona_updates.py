"""Validated, version-aware persona profile updates."""
from __future__ import annotations

import json
import hashlib
import hmac
from typing import Any

from ..config import utc_now_iso
from ..llm_simulation import validate_profile_payload
from ..storage import Store
from ._common import *  # noqa: F401,F403


_EDITABLE_PERSONA_FIELDS = frozenset({
    "display_name", "source_description", "identity_traits", "segment", "demographics",
    "role", "company_context", "goals", "constraints", "tool_ids", "tools",
    "relationships", "personality", "pain_points", "success_criteria", "capabilities",
})
_IDENTITY_PERSONA_FIELDS = frozenset({
    "display_name", "source_description", "identity_traits", "segment", "demographics",
    "role", "company_context",
})


def _update_preview_token(persona: dict[str, Any], patch: dict[str, Any]) -> str:
    frozen = json.dumps({
        "persona_id": persona["id"],
        "updated_at": persona.get("updated_at"),
        "patch": patch,
    }, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return "update-persona:" + hashlib.sha256(frozen.encode("utf-8")).hexdigest()[:24]


def _persona_update_impact(persona_id: str, store: Store) -> dict[str, int]:
    projects = [row for row in store.list_research_projects()
                if persona_id in (row.get("persona_ids") or [])]
    councils = [row for row in store.list_council_sessions()
                if persona_id in (row.get("persona_ids") or [])]
    return {
        "linked_projects": len(projects),
        "active_runs": sum(
            row.get("status") == "active"
            for project in projects for row in store.list_runs(project["id"])
        ),
        "historical_councils": len(councils),
        "historical_sessions": (
            len(store.list_usability_sessions(persona_id=persona_id))
            + len(store.list_prototype_sessions(persona_id=persona_id))
        ),
        "frozen_context_snapshots": len(store.list_persona_context_snapshots(persona_id)),
    }


def _validated_persona_patch(persona: dict[str, Any],
                             patch: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    if not isinstance(patch, dict) or not patch:
        raise ValueError("persona patch must be a non-empty object")
    forbidden = sorted(set(patch) - _EDITABLE_PERSONA_FIELDS)
    if forbidden:
        raise ValueError(
            f"persona patch contains immutable/unknown fields {forbidden}; editable fields are "
            f"{sorted(_EDITABLE_PERSONA_FIELDS)}. Use record_persona_revision for slow identity drift.")
    clean = dict(patch)
    if "capabilities" in clean:
        clean["capabilities"] = merge_capabilities(  # noqa: F821 (bound)
            persona.get("capabilities"), clean["capabilities"])
    candidate = json.loads(json.dumps(persona))
    for key, value in clean.items():
        if isinstance(value, dict) and isinstance(candidate.get(key), dict):
            candidate[key].update(value)
        else:
            candidate[key] = value
    validate_profile_payload({key: candidate.get(key) for key in (
        "display_name", "identity_traits", "segment", "demographics", "role",
        "company_context", "goals", "constraints", "tool_ids", "tools",
        "relationships", "personality", "pain_points", "success_criteria",
    )})
    return clean, candidate


def preview_persona_update(persona_id: str, patch: dict[str, Any],
                           expected_updated_at: str | None = None,
                           store: Store | None = None) -> dict[str, Any]:
    """Validate a patch and show a bounded field-level diff without mutating."""
    store = store or Store()
    persona = store.get_persona(persona_id)
    if not persona:
        raise KeyError(f"Unknown persona: {persona_id}")
    if expected_updated_at and expected_updated_at != persona.get("updated_at"):
        raise ValueError("persona changed since it was read; refresh and preview against the current version")
    clean, candidate = _validated_persona_patch(persona, patch)
    changed = {key: {"before": persona.get(key), "after": candidate.get(key)}
               for key in clean if persona.get(key) != candidate.get(key)}
    changed_fields = sorted(changed)
    identity_fields = sorted(set(changed_fields) & _IDENTITY_PERSONA_FIELDS)
    confirmation_required = bool(identity_fields)
    return {"persona_id": persona["id"], "expected_updated_at": persona.get("updated_at"),
            "changed_fields": changed_fields, "changes": changed,
            "risk": {
                "level": "identity" if confirmation_required else "routine",
                "identity_fields": identity_fields,
                "confirmation_required": confirmation_required,
            },
            "impact": _persona_update_impact(persona["id"], store),
            "confirmation_token": (_update_preview_token(persona, clean)
                                   if confirmation_required else ""),
            "history_contract": {
                "past_sessions_unchanged": True,
                "frozen_context_snapshots_unchanged": True,
                "future_context_uses_updated_profile": True,
            },
            "no_op": not changed, "next_recommended_tool": "update_persona"}


def update_persona(persona_id: str, patch: dict[str, Any], reason: str,
                   expected_updated_at: str | None = None,
                   preview_token: str | None = None,
                   store: Store | None = None) -> dict[str, Any]:
    store = store or Store()
    persona = store.get_persona(persona_id)
    if not persona:
        raise KeyError(f"Unknown persona: {persona_id}")
    if not str(reason or "").strip():
        raise ValueError("persona update requires a non-empty reason")
    if expected_updated_at and expected_updated_at != persona.get("updated_at"):
        raise ValueError("persona changed since it was read; refresh and preview against the current version")
    patch, candidate = _validated_persona_patch(persona, patch)
    changed_fields = {key for key in patch if persona.get(key) != candidate.get(key)}
    identity_fields = changed_fields & _IDENTITY_PERSONA_FIELDS
    if identity_fields:
        expected_token = _update_preview_token(persona, patch)
        if not preview_token or not hmac.compare_digest(preview_token, expected_token):
            raise ValueError(
                "identity-changing persona updates require the exact confirmation_token from "
                "preview_persona_update for the current persona version and patch"
            )
    persona = candidate
    persona["updated_at"] = utc_now_iso()
    persona["soul"] = write_soul(persona, store)  # noqa: F821 (bound)
    store.upsert_persona(persona, reason=reason)
    emit_lifecycle_event(  # noqa: F821 (bound)
        "persona.updated", {"persona_id": persona["id"], "reason": reason}, store)
    from ..telemetry import capture_product_event
    capture_product_event(
        "persona_updated", subject_kind="persona", subject_id=persona["id"],
        properties={"changed_fields": sorted(str(key) for key in patch)[:20]})
    return persona
