"""Council artifacts: bring a REAL artifact (a live URL/website, a prototype link, or two A/B
variants) into a council so personas react to what's actually there — not a textual description
(ticket artifacts-into-council; enables the "look at this website, how's my positioning?" job).

This is a MINIMAL, self-contained artifact store scoped to councils — NOT the generic multimodal
Assets foundation (ticket attach-evidence-files-mcp, still backlog). An artifact is a per-project
record with a stable id, a `kind` (url | prototype | variant), the source ref (the URL), a captured
snapshot of what was there, and a captured-at timestamp + content hash so a run is REPRODUCIBLE.

Persistence mirrors how a project already owns its councils: the artifacts list lives inside the
research project's snapshot (`project["artifacts"]`), persisted via upsert_research_project — the same
JSON-blob-per-row model every other project field uses. No new table.

Variant labelling (A/B/C…) is the plumbing the sibling `head_to_head` Format builds its scoring on:
this ticket owns ingestion + "all artifacts are in the room, labelled"; head_to_head consumes the
labelled, captured variants and authors the preference/margin/segment output on top.
"""
from __future__ import annotations

from typing import Any

from ..config import utc_now_iso
from ..storage import Store
from .. import capture as _capture

from ._common import *  # noqa: F401,F403  (stable_id, _require_research_project, …)


# A small, OPEN vocabulary (kept here so there's no magic literal scattered around). `variant` is a
# url-or-prototype that is explicitly part of an A/B comparison; head_to_head reads these.
ARTIFACT_KINDS = ("url", "prototype", "variant")


def _project_artifacts(project: dict[str, Any]) -> list[dict[str, Any]]:
    return project.setdefault("artifacts", [])


def _next_label(existing: list[dict[str, Any]]) -> str:
    """The next A/B/C… label so multiple artifacts in one council are addressable side-by-side."""
    used = {a.get("label") for a in existing}
    for i in range(26):
        lab = chr(ord("A") + i)
        if lab not in used:
            return lab
    return f"V{len(existing) + 1}"


def add_artifact(project_id: str, url: str, kind: str = "url", title: str = "",
                 label: str | None = None, capture: bool = True, key: str | None = None,
                 store: Store | None = None,
                 dispatch_token: str | None = None) -> dict[str, Any]:
    """Bring an artifact into a project's council pool: capture a grounded snapshot of `url` and store a
    stable, reproducible reference. `kind`: url (a live website) | prototype (e.g. a Figma link) |
    variant (one side of an A/B comparison). Capture degrades gracefully — a URL that can't be fetched
    still stores the ref + captured-at so the council is never hard-failed. Pass `capture=False` to skip
    the network fetch (store the ref only). Pass a stable `key` for a DETERMINISTIC id (idempotent
    upsert). Re-adding the same url RE-CAPTURES it (a fresh snapshot/version)."""
    store = store or Store()
    project = _require_research_project(store, project_id)
    dispatch_ctx = prepare_dispatch_write(  # noqa: F821 (bound)
        project["id"], dispatch_token, key, "artifact", store,
        allowed_buckets={"analyze", "act", "verify"})
    url = (url or "").strip()
    if not url:
        raise ValueError("artifact url is required")
    k = kind if kind in ARTIFACT_KINDS else "url"
    arts = _project_artifacts(project)
    aid = stable_id("artifact", key) if key else stable_id("artifact", project["id"], url, k)
    existing = next((a for a in arts if a["id"] == aid), None)
    snapshot = _capture.capture_url(url) if capture else {
        "ok": False, "mode": "skipped", "url": url, "captured_at": utc_now_iso(),
        "title": "", "description": "", "headings": [], "text": "", "status": None,
        "content_hash": stable_id("nocap", url).split("_", 1)[-1]}
    record = {
        "id": aid,
        "kind": k,
        "url": url,
        "title": (title or snapshot.get("title") or url).strip(),
        "label": (existing or {}).get("label") or label or _next_label([a for a in arts if a is not existing]),
        "snapshot": snapshot,
        "captured_at": snapshot.get("captured_at"),
        "content_hash": snapshot.get("content_hash"),
        "created_at": (existing or {}).get("created_at") or utc_now_iso(),
        "updated_at": utc_now_iso(),
        "dispatch_provenance": {
            "state": dispatch_ctx.get("state", "outside_run"),
            **({"dispatch_token": dispatch_ctx["dispatch_token"],
                "run_id": dispatch_ctx["run_id"], "task_id": dispatch_ctx["task_id"]}
               if dispatch_ctx.get("dispatch_token") else {}),
        },
    }
    if existing:
        arts[arts.index(existing)] = record
    else:
        arts.append(record)
    project["updated_at"] = utc_now_iso()
    store.upsert_research_project(project)
    dispatch = bind_dispatch_output(  # noqa: F821 (bound)
        dispatch_ctx, {"kind": "artifact", "id": aid}, "captured supporting stimulus artifact", store,
        complete=False)
    return {**record, "dispatch": dispatch}


def list_artifacts(project_id: str, store: Store | None = None) -> list[dict[str, Any]]:
    """Every artifact ingested into a project, in insertion order (label A, B, C, …)."""
    store = store or Store()
    project = _require_research_project(store, project_id)
    return list(_project_artifacts(project))


def get_artifact(project_id: str, artifact_id: str, store: Store | None = None) -> dict[str, Any]:
    """One artifact by id (or by its A/B label) within a project."""
    store = store or Store()
    project = _require_research_project(store, project_id)
    for a in _project_artifacts(project):
        if a["id"] == artifact_id or a.get("label") == artifact_id:
            return a
    raise KeyError(f"Unknown artifact '{artifact_id}' in project {project_id}")


def delete_artifact(project_id: str, artifact_id: str, store: Store | None = None) -> dict[str, Any]:
    """Remove an artifact from a project's pool (by id or label)."""
    store = store or Store()
    project = _require_research_project(store, project_id)
    arts = _project_artifacts(project)
    keep = [a for a in arts if a["id"] != artifact_id and a.get("label") != artifact_id]
    deleted = len(arts) - len(keep)
    if deleted:
        project["artifacts"] = keep
        project["updated_at"] = utc_now_iso()
        store.upsert_research_project(project)
    return {"deleted": deleted}


def _artifact_brief(a: dict[str, Any]) -> dict[str, Any]:
    """The compact, council-facing view of an artifact — what a persona is shown so its reaction is
    grounded in the REAL artifact (its captured copy), labelled A/B/… for side-by-side comparison."""
    snap = a.get("snapshot") or {}
    return {
        "id": a["id"], "label": a.get("label"), "kind": a.get("kind"),
        "url": a.get("url"), "title": a.get("title"),
        "captured": bool(snap.get("ok")),
        "captured_at": a.get("captured_at"),
        "content_hash": a.get("content_hash"),
        "description": snap.get("description", ""),
        "headings": snap.get("headings", []),
        "snapshot_text": snap.get("text", ""),
        "capture_note": (snap.get("error") or ("not captured" if snap.get("mode") in ("skipped", "unavailable") else "")),
    }


def council_artifact_briefs(project_id: str, artifact_ids: list[str] | None = None,
                            store: Store | None = None) -> list[dict[str, Any]]:
    """The artifacts to put IN the council room, as compact briefs. `artifact_ids` selects a subset (by
    id or label) for THIS council; None = every artifact ingested into the project. The order/labels are
    preserved so two variants are present and comparable in one run (head_to_head reads these)."""
    store = store or Store()
    arts = list_artifacts(project_id, store=store)
    if artifact_ids:
        want = {str(x) for x in artifact_ids}
        arts = [a for a in arts if a["id"] in want or a.get("label") in want]
    return [_artifact_brief(a) for a in arts]


def render_artifacts_context(briefs: list[dict[str, Any]]) -> str:
    """Render the selected artifacts as a single labelled text block the host folds into each persona's
    council context, so personas react to the REAL captured artifact(s). For multiple artifacts every
    one is present and labelled A/B/… for side-by-side comparison (the head_to_head plumbing)."""
    if not briefs:
        return ""
    multi = len(briefs) > 1
    head = ("ARTIFACTS IN THE ROOM — react to what is ACTUALLY there (the captured copy below), not to "
            "a description. " + ("Two or more variants are present; compare them side-by-side and name "
            "which wins for whom and why." if multi else "")).strip()
    parts = [head]
    for b in briefs:
        tag = f"VARIANT {b['label']}" if multi else "ARTIFACT"
        lines = [f"--- {tag}: {b.get('title') or b.get('url')} ({b.get('kind')}) ---",
                 f"URL: {b.get('url')}"]
        if b.get("captured"):
            lines.append(f"Captured at {b.get('captured_at')} (hash {b.get('content_hash')}).")
            if b.get("description"):
                lines.append(f"Description: {b['description']}")
            if b.get("headings"):
                lines.append("Headings: " + " · ".join(b["headings"][:12]))
            if b.get("snapshot_text"):
                lines.append("Captured content:\n" + b["snapshot_text"])
        else:
            lines.append("Capture unavailable — react to the reference itself; do not invent content "
                         f"you cannot see. ({b.get('capture_note') or 'no snapshot'})")
        parts.append("\n".join(lines))
    return "\n\n".join(parts)
