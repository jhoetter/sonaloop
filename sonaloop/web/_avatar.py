"""Persona avatar rendering — portrait when the image exists, initials otherwise.

Split out of web/_components.py (LOC bar); re-exported there so every existing
`from ._components import _avatar` import keeps working.
"""
from __future__ import annotations

from ._html import h

_AV_COLORS = ["#3d7b5f", "#2f6f9f", "#a66b1f", "#7a5ea6", "#b3493f", "#4a7d7d", "#5a6b8a"]


def _avatar_src(p: dict) -> str | None:
    """The persona's portrait URL — only when the image file actually EXISTS under DATA_DIR.
    Avatar records travel with snapshots while the binaries may not (avatars are optional
    eye-candy, sonaloop/avatar.py); a recorded-but-missing file must degrade to the initials
    fallback, never to a broken <img> frame (ux-audit P5 finding)."""
    path = (p.get("avatar") or {}).get("path") or ""
    if not path:
        return None
    from .. import config
    if config.postgres_row_tenancy_enabled():
        # Shared row-tenancy intentionally exposes no raw /data mount until an
        # authenticated workspace-file route exists; render initials, not a broken
        # (or accidentally global) image URL.
        return None
    rel = path[len("data/"):] if path.startswith("data/") else path
    candidate = (config.partition_dir() / rel).resolve()
    if not candidate.is_relative_to(config.partition_dir().resolve()):
        return None
    return f"/{path}" if candidate.is_file() else None


def _avatar(p: dict, size: int = 36) -> str:
    src = _avatar_src(p)
    if src:
        return h("img", {"class_": "sl-avatar", "style": f"width:{size}px;height:{size}px",
                         "src": src, "alt": ""})
    name = p.get("display_name", "?")
    ini = "".join(w[0] for w in name.split()[:2]).upper() or "?"
    c = _AV_COLORS[sum(map(ord, p.get("id", "x"))) % len(_AV_COLORS)]
    fs = max(10, size // 3)
    return h("span", {"class_": "sl-avatar", "style": f"width:{size}px;height:{size}px;background:{c};font-size:{fs}px"}, ini)
