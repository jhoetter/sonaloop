"""Asset store for embeddable media — prototype screenshots, uploaded images
(spec/meta-report-presentation-and-pdf.md §2).

Files live under the active partition's `assets/` directory. Local SQLite serves
that tree at `/data/assets/…`; shared-Postgres deployments keep raw file delivery
blocked and use an active-workspace-authorized opaque-id route instead. An asset id
is the content hash + extension (`assets/<hash>.png`). `capture_prototype_shot` uses the Playwright
harness to screenshot a static prototype — the harness CAPTURES, it does not
generate text, so the no-in-process-LLM invariant is preserved.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from .config import DATA_DIR, partition_dir

_IMPORTED_ASSETS_DIR = DATA_DIR / "assets"
ASSETS_DIR = _IMPORTED_ASSETS_DIR


def asset_store_dir() -> Path:
    """Active content-addressed screenshot store.

    ``ASSETS_DIR`` remains a compatibility/test override; when untouched, resolve
    dynamically so request-bound workspace partitions cannot collide.
    """
    if ASSETS_DIR != _IMPORTED_ASSETS_DIR:
        return Path(ASSETS_DIR)
    return partition_dir() / "assets"


def put_asset(data: bytes, ext: str = "png") -> str:
    """Write bytes to the content-addressed store; return the asset id (`assets/<hash>.<ext>`)."""
    root = asset_store_dir()
    root.mkdir(parents=True, exist_ok=True)
    aid = hashlib.sha1(data).hexdigest()[:16]
    name = f"{aid}.{ext.lstrip('.')}"
    (root / name).write_bytes(data)
    return f"assets/{name}"


def asset_url(asset_id: str) -> str:
    """The static URL for an asset id (served from the /data mount)."""
    return f"/data/{asset_id}"


def capture_prototype_shot(prototype_id: str, store=None, width: int = 1120, height: int = 720) -> str:
    """Screenshot a STATIC prototype (its entry HTML via file://) into an asset; record the asset id on
    the prototype (`shot`) so the report can embed it. Uses the Playwright harness (a hard dependency)."""
    from .storage import Store
    store = store or Store()
    p = store.get_prototype(prototype_id)
    if not p:
        raise KeyError(f"Unknown prototype: {prototype_id}")
    from .prototypes import _prototype_app_dir
    app_dir = _prototype_app_dir(p)
    entry = (app_dir / p.get("entry", "index.html")).resolve()
    if not entry.is_relative_to(app_dir):
        raise ValueError(f"prototype entry escapes app directory: {p.get('entry')!r}")
    if not entry.exists():
        raise FileNotFoundError(f"Prototype has no entry file to screenshot: {entry}")
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        pg = b.new_page(viewport={"width": width, "height": height}, device_scale_factor=2)
        pg.goto(entry.resolve().as_uri(), wait_until="networkidle")
        pg.wait_for_timeout(300)
        png = pg.screenshot()
        b.close()
    aid = put_asset(png, "png")
    rec = dict(p)
    rec["shot"] = aid
    store.upsert_prototype(rec)
    return aid
