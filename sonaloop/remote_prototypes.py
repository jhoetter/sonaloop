"""Metadata-only admission for externally hosted prototypes."""
from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

from .config import utc_now_iso
from .models import Prototype
from .prototypes import PrototypeError, _safe_artifact_slug
from .storage import Store


def validate_registration(slug: str, url: str, project_id: str | None = None,
                          store: Store | None = None) -> tuple[str, str]:
    """Validate hosted-prototype metadata without fetching or mutating anything."""
    store = store or Store()
    slug = _safe_artifact_slug(slug)
    raw_url = str(url or "").strip()
    parsed = urlsplit(raw_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise PrototypeError("BAD_REMOTE_URL", "remote prototype URL must be absolute http(s)")
    if parsed.username or parsed.password:
        raise PrototypeError("BAD_REMOTE_URL", "remote prototype URL must not contain credentials")
    if project_id and not store.get_research_project(project_id):
        raise PrototypeError("UNKNOWN_PROJECT", f"No research project '{project_id}'")
    existing = store.get_prototype(slug)
    if existing and str(existing.get("project_id") or "") != str(project_id or ""):
        raise PrototypeError(
            "PROTOTYPE_SCOPE_CONFLICT", "prototype slug already belongs to another project")
    return slug, raw_url


def register(slug: str, name: str, url: str, version: str = "v0.1",
             project_id: str | None = None, notes: str = "", fidelity: str = "hifi",
             created_at: str | None = None, store: Store | None = None) -> dict[str, Any]:
    """Store an HTTP(S) app as a first-class prototype without fetching or executing it."""
    store = store or Store()
    slug, raw_url = validate_registration(slug, url, project_id=project_id, store=store)
    existing = store.get_prototype(slug)
    from .services import stable_id
    now = created_at or utc_now_iso()
    tags = [str(fidelity).strip()] if str(fidelity).strip() else []
    pid = (existing or {}).get("id") or stable_id("prototype", slug, now)
    rec = Prototype(
        id=pid, slug=slug, project_id=project_id, name=str(name or "").strip() or slug,
        version=str(version or "v0.1"), kind="web", path="", entry="", run="remote",
        run_cmd=None, notes=str(notes or ""), created_at=(existing or {}).get("created_at", now),
        fidelity=(tags[0] if tags else ""), type="prototype", tags=tags, url=raw_url,
    ).to_dict()
    store.upsert_prototype(rec)
    return rec
