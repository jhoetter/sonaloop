"""Validated, version-aware persona profile updates."""
from __future__ import annotations

import json
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
    return {"persona_id": persona["id"], "expected_updated_at": persona.get("updated_at"),
            "changed_fields": sorted(changed), "changes": changed,
            "no_op": not changed, "next_recommended_tool": "update_persona"}


def update_persona(persona_id: str, patch: dict[str, Any], reason: str,
                   expected_updated_at: str | None = None,
                   store: Store | None = None) -> dict[str, Any]:
    store = store or Store()
    persona = store.get_persona(persona_id)
    if not persona:
        raise KeyError(f"Unknown persona: {persona_id}")
    if not str(reason or "").strip():
        raise ValueError("persona update requires a non-empty reason")
    if expected_updated_at and expected_updated_at != persona.get("updated_at"):
        raise ValueError("persona changed since it was read; refresh and preview against the current version")
    patch, persona = _validated_persona_patch(persona, patch)
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
