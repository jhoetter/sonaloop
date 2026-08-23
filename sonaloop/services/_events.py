"""Cross-process event bus: every lifecycle event → one durable `events` row.

The MCP server, the CLI and the web inspector are separate processes sharing one
SQLite DB, so an in-process hook alone can't reach the inspector. This module
registers a '*' in-process handler at import time — i.e. in ANY process that loads
the services layer — which appends each emitted event as a lean bus row (ts, event
name, the primary entity, owning project, a short label + inspector URL). The web
app tails the table for its live SSE stream (`GET /api/events`) and Activity feed.

Best-effort like every hook subscriber (docs/lifecycle-hooks.md): a failing append
is swallowed by emit_lifecycle_event's handler guard and never breaks the recording
operation. Storage caps the table on append (storage._hooks.EVENTS_CAP)."""

from __future__ import annotations

from typing import Any

from ..config import utc_now_iso
from ..storage import Store
from ._hooks import add_hook_handler

# event -> (entity_type, payload key carrying the entity id, payload key carrying a
# short human label). project_id rides along from the payload whenever present;
# persona-scoped events link to the persona (the page where the change is visible).
_ENTITY: dict[str, tuple[str, str, str]] = {
    "persona.created": ("persona", "persona_id", "display_name"),
    "persona.updated": ("persona", "persona_id", "reason"),
    "evidence.attached": ("persona", "persona_id", "source_type"),
    "persona.grounded": ("persona", "persona_id", ""),
    "chat.recorded": ("persona", "persona_id", ""),
    "day.recorded": ("persona", "persona_id", "date"),
    "prediction.scored": ("project", "project_id", ""),
    "calibration.round_recorded": ("project", "scope", ""),
    "asset.attached": ("asset", "asset_id", "filename"),
    "council.recorded": ("council", "council_id", "prompt"),
    "synthesis.recorded": ("synthesis", "synthesis_id", "title"),
    "project.created": ("project", "project_id", "title"),
    "project.updated": ("project", "project_id", "title"),
    "run.finished": ("run", "run_id", "status"),
}

# entity_type -> the inspector detail route (the toast/feed link target).
_ENTITY_ROUTE = {"persona": "/personas/", "council": "/councils/",
                 "synthesis": "/syntheses/", "project": "/jobs/",
                 "asset": "/assets/"}        # the U8 asset detail page (global id resolution)


def event_url(entity_type: str, entity_id: str, project_id: str | None) -> str:
    """The inspector URL an event points at. A run has no page of its own → its
    project; calibration's 'global' scope (no project row) → the projects index."""
    if entity_type == "run":
        return f"/jobs/{project_id}" if project_id else "/jobs"
    route = _ENTITY_ROUTE.get(entity_type)
    if route and entity_id and entity_id != "global":
        return route + entity_id
    return "/jobs"


def _append_bus_event(envelope: dict[str, Any]) -> None:
    """The '*' subscriber: map the envelope onto one bus row. Unknown events (a future
    catalogue addition) still land — generically, with no entity link."""
    data = envelope.get("data") or {}
    entity_type, id_key, label_key = _ENTITY.get(envelope["event"], ("", "", ""))
    entity_id = str(data.get(id_key) or "")
    project_id = str(data.get("project_id") or "") or None
    if entity_type == "project" and not project_id:
        project_id = entity_id or None
    store = Store()
    try:
        event_data = {
            "label": str(data.get(label_key) or "")[:160],  # lean: never full authored text
            "url": event_url(entity_type, entity_id, project_id),
        }
        if data.get("direction") in {"in", "out"}:
            event_data["direction"] = data["direction"]
        store.append_event(
            envelope.get("emitted_at") or utc_now_iso(), envelope["event"],
            entity_type, entity_id, project_id,
            event_data)
    finally:
        store.close()


# Registered at import — the services layer is the only mutation path, so every
# process that records data feeds the bus. (Validated pattern: '*'.)
add_hook_handler("*", _append_bus_event)
