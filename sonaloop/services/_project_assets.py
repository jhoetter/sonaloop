"""Project assets: files, images & screenshots as first-class, citable evidence
(ticket attach-evidence-files-mcp — the generic multimodal Assets foundation the
council-artifacts module points at).

An asset is REAL MATERIAL on a project — stored once in the active runtime
partition's content-addressed `assets/` directory and recorded on the project
(`project["assets"]`, the same JSON-blob-per-row model artifacts use; no new
table). Local SQLite serves that tree at `/data/assets/…`; shared-Postgres RLS
deployments keep raw runtime-file routes blocked and expose assets through an
authenticated, active-workspace-only opaque-id route. Ids are stable
(content-addressed per project) so personas/councils can cite them and
re-attaching the same bytes is idempotent.

Direction (ticket project-assets-direction-deliverables-page-section): an asset
flows `in` (evidence brought INTO the project — a screenshot, a PDF, an
interview note; the default, and what every pre-direction record means) or
`out` (a deliverable PRODUCED from the project — the exported PPTX/PDF a
synthesis renders; attached by export_synthesis_deliverable with
source `synthesis:<id>`). No migration: a record without the field is `in`.

Multimodal contract: image assets are not merely stored — `get_asset_content`
hands back the bytes, and the MCP `view_asset` tool returns them as an actual
image so the HOST looks at the evidence before authoring persona reactions
(no in-process vision; the host's eyes are the vision model). Text documents
carry an inline excerpt so councils can quote them directly."""

from __future__ import annotations

import base64
import hashlib
import mimetypes
from pathlib import Path
from typing import Any

from ..config import utc_now_iso
from ..storage import Store

from ._common import *  # noqa: F401,F403  (stable_id, _require_research_project, …)


IMAGE_EXTS = {"png", "jpg", "jpeg", "gif", "webp", "svg", "bmp"}
DOCUMENT_EXTS = {"pdf", "md", "txt", "csv", "json", "html", "docx", "rtf"}
TEXT_EXCERPT_EXTS = {"md", "txt", "csv", "json", "html", "rtf"}
PREVIEW_EXTS = {"pptx"}      # document types with a first-page preview renderer (W6)
ASSET_KINDS = ("image", "screenshot", "document", "file")
ASSET_DIRECTIONS = ("in", "out")   # in = evidence brought into the project · out = deliverable produced from it
MAX_ASSET_BYTES = 25 * 1024 * 1024
_EXCERPT_CHARS = 4000


def _assets_dir() -> Path:
    """The asset binary store of the ACTIVE data partition (DATA_DIR/assets for the
    local store, DATA_DIR/workspaces/<ws>/assets for shared tenancy). The local
    inspector serves DATA_DIR at /data; shared-Postgres browser delivery uses the
    authenticated asset route, while MCP `view_asset` resolves the active partition directly."""
    from ..config import partition_dir
    return partition_dir() / "assets"


def _assets_url_base() -> str:
    """The logical `/data` URL prefix stored on records.

    It is directly fetchable in local SQLite mode. In shared-Postgres mode raw
    `/data` delivery is blocked; browser renderers replace it with the authorized
    opaque-id route and MCP callers use `view_asset`.
    """
    from .. import config
    try:
        rel = _assets_dir().resolve().relative_to(Path(config.DATA_DIR).resolve())
    except ValueError:                  # a partition rooted outside DATA_DIR (not the norm)
        return "/data/assets"
    return "/data/" + rel.as_posix()


def _project_assets(project: dict[str, Any]) -> list[dict[str, Any]]:
    return project.setdefault("assets", [])


def _infer_kind(ext: str, declared: str | None) -> str:
    if declared in ASSET_KINDS:
        return declared
    if ext in IMAGE_EXTS:
        return "image"
    if ext in DOCUMENT_EXTS:
        return "document"
    return "file"


def _text_excerpt(data: bytes, ext: str) -> str:
    if ext not in TEXT_EXCERPT_EXTS or len(data) > 512 * 1024:
        return ""
    try:
        return data.decode("utf-8", errors="ignore")[:_EXCERPT_CHARS].strip()
    except Exception:
        return ""


def _write_asset_preview(data: bytes, ext: str, sha: str) -> str:
    """The first-page preview PNG beside the binary (ux-contract §10 W6): `<sha>.preview.png`
    in the content-addressed store (served from /data only in local mode). The CHOSEN SEAM is
    attach_asset itself — every path that creates a document asset (the deliverable export,
    an MCP attach, a seed) gets its preview in the one place asset records are born; a
    re-export carries new bytes → a new sha → a fresh preview beside the new binary.
    Graceful: only PREVIEW_EXTS render; bytes that don't open as a deck return '' and the
    record keeps its extension badge. Content-addressed = idempotent (existing file wins)."""
    if ext not in PREVIEW_EXTS:
        return ""
    target = _assets_dir() / f"{sha}.preview.png"
    if not target.exists():
        from .._pptx_preview import render_first_slide
        png = render_first_slide(data)
        if not png:
            return ""
        target.write_bytes(png)
    return f"{_assets_url_base()}/{sha}.preview.png"


def ensure_asset_preview(project_id: str, asset_id: str | None = None,
                         store: Store | None = None) -> list[dict[str, Any]]:
    """The maintenance hook for records attached BEFORE the preview seam existed (W6
    backfill): (re)generate the missing first-page preview for the project's document
    assets — one asset when `asset_id` is given, every previewable one otherwise.
    Returns the records that gained a `preview_url`. CLI: `sonaloop backfill-previews`."""
    store = store or Store()
    project = _require_research_project(store, project_id)  # noqa: F821 (bound)
    updated = []
    for a in _project_assets(project):
        if asset_id and a["id"] != asset_id:
            continue
        ext = Path(a.get("asset_path", "")).suffix.lstrip(".").lower()
        if a.get("preview_url") or ext not in PREVIEW_EXTS:
            continue
        binary = _assets_dir() / Path(a.get("asset_path", "")).name
        if not binary.is_file():
            continue
        sha = binary.stem
        url = _write_asset_preview(binary.read_bytes(), ext, sha)
        if url:
            a["preview_url"] = url
            a["updated_at"] = utc_now_iso()
            updated.append(a)
    if updated:
        project["updated_at"] = utc_now_iso()
        store.upsert_research_project(project)
    return updated


def attach_asset(project_id: str, path: str | None = None, content_base64: str | None = None,
                 filename: str | None = None, kind: str | None = None, title: str = "",
                 notes: str = "", source: str = "", direction: str | None = None,
                 store: Store | None = None,
                 dispatch_token: str | None = None) -> dict[str, Any]:
    """Attach a file/image/screenshot to a project as a citable asset. Pass EITHER
    `path` (a local file — e.g. a screenshot captured during the project) OR
    `content_base64` (+ `filename` for the extension). The binary lands in the
    content-addressed store; the record (stable id, kind, media type, excerpt for
    text documents) lands on the project. `direction` is `in` (evidence, the
    default) or `out` (a deliverable produced from the project). Re-attaching
    identical bytes is an idempotent upsert (title/notes/direction refresh).
    Emits `asset.attached`."""
    store = store or Store()
    project = _require_research_project(store, project_id)  # noqa: F821 (bound)
    if direction is not None and direction not in ASSET_DIRECTIONS:
        raise ValueError(f"direction must be one of {ASSET_DIRECTIONS}, got {direction!r}")
    if bool(path) == bool(content_base64):
        raise ValueError("Pass exactly one of `path` or `content_base64`.")
    src = Path(path).expanduser() if path else None
    if src is not None:
        if not src.is_file():
            raise FileNotFoundError(f"No such file: {path}")
        from .. import config
        if config.postgres_row_tenancy_enabled() and not src.resolve().is_relative_to(
                config.partition_dir().resolve()):
            raise ValueError("asset path must stay inside the active workspace partition; "
                             "upload external material with content_base64")
    dispatch_ctx = prepare_dispatch_write(  # noqa: F821 (bound)
        project["id"], dispatch_token, None, "asset", store,
        allowed_buckets={"analyze", "act", "verify"})
    if path:
        assert src is not None
        data = src.read_bytes()
        name = filename or src.name
        source = source or str(src)
    else:
        data = base64.b64decode(content_base64, validate=True)
        if not filename:
            raise ValueError("`filename` is required with content_base64 (it carries the extension).")
        name = filename
    if not data:
        raise ValueError("Asset is empty.")
    if len(data) > MAX_ASSET_BYTES:
        raise ValueError(f"Asset exceeds the {MAX_ASSET_BYTES // (1024 * 1024)}MB cap.")
    ext = (Path(name).suffix.lstrip(".") or "bin").lower()
    sha = hashlib.sha1(data).hexdigest()[:16]
    adir = _assets_dir()
    adir.mkdir(parents=True, exist_ok=True)
    (adir / f"{sha}.{ext}").write_bytes(data)
    assets = _project_assets(project)
    aid = stable_id("asset", project["id"], sha)  # noqa: F821 (bound)
    existing = next((a for a in assets if a["id"] == aid), None)
    record = {
        "id": aid,
        "kind": _infer_kind(ext, kind),
        "filename": name,
        "title": (title or (existing or {}).get("title") or name).strip(),
        "notes": notes or (existing or {}).get("notes", ""),
        "source": source or (existing or {}).get("source", ""),
        # in (evidence; also every pre-direction record) | out (deliverable). Kept on re-attach.
        "direction": direction or (existing or {}).get("direction") or "in",
        "media_type": mimetypes.guess_type(name)[0] or "application/octet-stream",
        "bytes": len(data),
        # asset_path is the record's stable KEY (its basename addresses the store);
        # readers resolve via _assets_dir(), never against this literal prefix.
        "asset_path": f"data/assets/{sha}.{ext}",
        "url": f"{_assets_url_base()}/{sha}.{ext}",
        # W6: document file cards show the title slide — '' (no renderer / unreadable deck)
        # degrades to the extension badge everywhere.
        "preview_url": _write_asset_preview(data, ext, sha),
        "text_excerpt": _text_excerpt(data, ext),
        "created_at": (existing or {}).get("created_at") or utc_now_iso(),
        "updated_at": utc_now_iso(),
        "dispatch_provenance": {
            "state": dispatch_ctx.get("state", "outside_run"),
            **({"dispatch_token": dispatch_ctx["dispatch_token"],
                "run_id": dispatch_ctx["run_id"], "task_id": dispatch_ctx["task_id"]}
               if dispatch_ctx.get("dispatch_token") else {}),
        },
    }
    if (existing or {}).get("supersedes"):       # the provenance chain survives a re-attach upsert
        record["supersedes"] = existing["supersedes"]
    if existing:
        assets[assets.index(existing)] = record
    else:
        assets.append(record)
    project["updated_at"] = utc_now_iso()
    store.upsert_research_project(project)
    emit_lifecycle_event("asset.attached", {"project_id": project["id"], "asset_id": aid,  # noqa: F821 (bound)
                                            "kind": record["kind"], "filename": name}, store)
    dispatch = bind_dispatch_output(  # noqa: F821 (bound)
        dispatch_ctx, {"kind": "asset", "id": aid}, "attached supporting stimulus asset", store,
        complete=False)
    return {**record, "dispatch": dispatch}


def attach_prototype_shot(project_id: str, prototype_id: str, title: str = "",
                          notes: str = "", store: Store | None = None) -> dict[str, Any]:
    """The capture path for artifacts PRODUCED during a project: screenshot a
    registered prototype (Playwright harness) and attach the shot as image evidence."""
    from .. import assets as _assets
    store = store or Store()
    shot = _assets.capture_prototype_shot(prototype_id, store=store)  # "assets/<hash>.png"
    shot_file = _assets.asset_store_dir() / Path(shot).name
    return attach_asset(project_id, path=str(shot_file), kind="screenshot",
                        title=title or f"Prototype shot: {prototype_id}",
                        notes=notes, source=f"prototype:{prototype_id}", store=store)


def list_assets(project_id: str, store: Store | None = None) -> list[dict[str, Any]]:
    """Every asset attached to a project (lean records; bytes via get_asset_content)."""
    store = store or Store()
    project = _require_research_project(store, project_id)  # noqa: F821 (bound)
    return [{k: v for k, v in a.items() if k != "text_excerpt"} for a in _project_assets(project)]


def get_asset(project_id: str, asset_id: str, store: Store | None = None) -> dict[str, Any]:
    """One asset record by id (or filename) — includes the text excerpt for documents."""
    store = store or Store()
    project = _require_research_project(store, project_id)  # noqa: F821 (bound)
    for a in _project_assets(project):
        if a["id"] == asset_id or a.get("filename") == asset_id:
            return a
    raise KeyError(f"Unknown asset '{asset_id}' in project {project_id}")


def record_asset_supersession(project_id: str, asset_id: str, replaced: list[dict[str, Any]],
                              store: Store | None = None) -> dict[str, Any]:
    """Record the supersede chain on a SURVIVING asset record (UX U8 — provenance: which earlier
    version this file replaced). `replaced` entries are lean `{id, filename, created_at}` stubs:
    the stale records themselves are already detached (remove_asset — a deliverable re-export
    keeps exactly one live record per (synthesis, format)), so the chain keeps enough of each to
    read honestly on the asset's provenance block. Idempotent per replaced id."""
    store = store or Store()
    project = _require_research_project(store, project_id)  # noqa: F821 (bound)
    for a in _project_assets(project):
        if a["id"] == asset_id:
            seen = {s.get("id") for s in a.get("supersedes") or []}
            new = [r for r in replaced if r.get("id") and r["id"] not in seen and r["id"] != asset_id]
            if new:
                a["supersedes"] = (a.get("supersedes") or []) + new
                a["updated_at"] = utc_now_iso()
                project["updated_at"] = utc_now_iso()
                store.upsert_research_project(project)
            return a
    raise KeyError(f"Unknown asset '{asset_id}' in project {project_id}")


def get_asset_content(project_id: str, asset_id: str,
                      store: Store | None = None) -> tuple[bytes, dict[str, Any]]:
    """The asset's bytes + its record — the multimodal feed (MCP view_asset wraps this).
    The read is contained to the asset store, never an arbitrary path from the record."""
    record = get_asset(project_id, asset_id, store=store)
    # The record's asset_path is the canonical `data/assets/<sha>.<ext>`; we address the
    # store by its BASENAME (partition-correct), but a path that isn't that exact shape
    # (a tampered/compatibility record) is rejected loudly rather than silently coerced.
    ap = record["asset_path"]
    if ap != f"data/assets/{Path(ap).name}":
        raise ValueError(f"Asset path escapes the asset store: {ap}")
    target = (_assets_dir() / Path(ap).name).resolve()
    if not target.is_relative_to(_assets_dir().resolve()):
        raise ValueError(f"Asset path escapes the asset store: {ap}")
    if not target.exists():
        raise FileNotFoundError(f"Asset binary missing: {record['asset_path']} (re-attach or import-snapshot)")
    return target.read_bytes(), record


def get_asset_preview_content(project_id: str, asset_id: str,
                              store: Store | None = None) -> tuple[bytes, dict[str, Any]]:
    """The generated PNG preview for a document asset, contained to its active
    workspace store.  This mirrors :func:`get_asset_content` for the authenticated
    web delivery route; callers cannot supply a filename or filesystem path."""
    record = get_asset(project_id, asset_id, store=store)
    if not record.get("preview_url"):
        raise FileNotFoundError(f"Asset has no preview: {record['id']}")
    ap = record["asset_path"]
    if ap != f"data/assets/{Path(ap).name}":
        raise ValueError(f"Asset path escapes the asset store: {ap}")
    sha = Path(ap).stem
    target = (_assets_dir() / f"{sha}.preview.png").resolve()
    if not target.is_relative_to(_assets_dir().resolve()):
        raise ValueError(f"Asset preview path escapes the asset store: {ap}")
    if not target.exists():
        raise FileNotFoundError(f"Asset preview binary missing: {record['id']}")
    return target.read_bytes(), record


def remove_asset(project_id: str, asset_id: str, store: Store | None = None) -> dict[str, Any]:
    """Detach an asset from a project (by id or filename). The binary stays in the
    content-addressed store — it may be shared by other projects and is cheap."""
    store = store or Store()
    project = _require_research_project(store, project_id)  # noqa: F821 (bound)
    assets = _project_assets(project)
    keep = [a for a in assets if a["id"] != asset_id and a.get("filename") != asset_id]
    deleted = len(assets) - len(keep)
    if deleted:
        project["assets"] = keep
        project["updated_at"] = utc_now_iso()
        store.upsert_research_project(project)
    return {"deleted": deleted}


def project_asset_briefs(project_id: str, asset_ids: list[str] | None = None,
                         store: Store | None = None) -> list[dict[str, Any]]:
    """The assets to put IN the council room, as compact evidence briefs.
    `asset_ids` selects a subset (by id or filename); None = every project asset."""
    store = store or Store()
    project = _require_research_project(store, project_id)  # noqa: F821 (bound)
    assets = _project_assets(project)
    if asset_ids:
        want = {str(x) for x in asset_ids}
        assets = [a for a in assets if a["id"] in want or a.get("filename") in want]
    return [{"id": a["id"], "project_id": project["id"], "kind": a.get("kind"),
             "title": a.get("title"), "filename": a.get("filename"), "notes": a.get("notes", ""),
             "media_type": a.get("media_type"), "is_image": a.get("kind") in ("image", "screenshot"),
             "text_excerpt": a.get("text_excerpt", ""), "source": a.get("source", "")}
            for a in assets]


def render_assets_context(briefs: list[dict[str, Any]]) -> str:
    """Render the evidence assets as one labelled block for persona contexts. Image
    assets instruct the HOST to view_asset them first — the host's eyes feed the
    persona an honest description of what is actually there; text documents are
    quoted inline via their excerpt."""
    if not briefs:
        return ""
    parts = ["EVIDENCE ASSETS IN THE ROOM — ground reactions in this real material, not in "
             "assumptions about it."]
    for b in briefs:
        lines = [f"--- ASSET: {b.get('title') or b.get('filename')} ({b.get('kind')}, id {b['id']}) ---"]
        if b.get("notes"):
            lines.append(f"Notes: {b['notes']}")
        if b.get("is_image"):
            lines.append(f"IMAGE EVIDENCE: call view_asset('{b['project_id']}', '{b['id']}') and LOOK at it "
                         "before authoring any reaction; relay only what is actually visible.")
        elif b.get("text_excerpt"):
            lines.append("Content (excerpt):\n" + b["text_excerpt"])
        else:
            lines.append(f"Binary evidence ({b.get('media_type')}); cite it by id — do not invent its contents.")
        parts.append("\n".join(lines))
    return "\n\n".join(parts)
