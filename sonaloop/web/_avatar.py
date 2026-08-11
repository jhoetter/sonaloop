"""Persona avatar rendering — portrait when the image exists, initials otherwise.

Split out of web/_components.py (LOC bar); re-exported there so every existing
`from ._components import _avatar` import keeps working.
"""
from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import quote

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
        parts = Path(path).parts
        if (len(parts) != 3 or parts[:2] != ("data", "avatars")
                or not re.fullmatch(
                    r"[A-Za-z0-9][A-Za-z0-9_.-]{0,191}\.png",
                    parts[2],
                    re.IGNORECASE,
                )):
            return None
    rel = path.removeprefix("data/")
    partition = config.partition_dir().resolve()
    candidate = (partition / Path(rel)).resolve()
    if not candidate.is_relative_to(partition) or not candidate.is_file():
        return None
    if config.postgres_row_tenancy_enabled():
        # The raw /data tree remains process-globally blocked in Cloud.  Resolve the
        # portrait through the authenticated, RLS-backed route instead; the opaque
        # persona id is looked up again inside the active workspace before bytes are
        # served.  The backing-file check above preserves the initials fallback when
        # a portable snapshot carries metadata but not the optional image binary.
        persona_id = str(p.get("id") or "")
        return f"/personas/{quote(persona_id, safe='')}/avatar" if persona_id else None
    return f"/{path}"


def _avatar_thumbnail_src(p: dict) -> str | None:
    """The small opaque-id derivative used by avatar atoms/groups.

    `_avatar_src` still performs the backing-file existence/path check and remains
    the full-resolution source for the persona detail and report figures.  The
    thumbnail route repeats the Store/RLS lookup before serving any pixels.
    """
    source = _avatar_src(p)
    if not source:
        return None
    persona_id = str(p.get("id") or "")
    return (f"/personas/{quote(persona_id, safe='')}/avatar/thumbnail"
            if persona_id else source)


def _avatar(p: dict, size: int = 36) -> str:
    src = _avatar_thumbnail_src(p)
    if src:
        return h("img", {"class_": "sl-avatar", "style": f"width:{size}px;height:{size}px",
                         "src": src, "alt": ""})
    name = p.get("display_name", "?")
    ini = "".join(w[0] for w in name.split()[:2]).upper() or "?"
    c = _AV_COLORS[sum(map(ord, p.get("id", "x"))) % len(_AV_COLORS)]
    fs = max(10, size // 3)
    return h("span", {"class_": "sl-avatar", "style": f"width:{size}px;height:{size}px;background:{c};font-size:{fs}px"}, ini)
