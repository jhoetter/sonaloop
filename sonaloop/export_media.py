"""Resolve authenticated runtime-image URLs for self-contained report exports."""
from __future__ import annotations

import mimetypes
import re
from typing import Any
from urllib.parse import unquote


def resolve_export_image(
        src: str, *, store: Any = None, project_id: str = "") -> tuple[bytes, str] | None:
    """Resolve one known opaque browser URL without widening its authorization scope."""
    asset_route = re.fullmatch(r"/assets/([^/?#]+)/content", src)
    # Compact Inspector atoms use the thumbnail route; exports inline the original
    # authorized portrait so the self-contained artifact stays resolution-independent.
    avatar_route = re.fullmatch(r"/personas/([^/?#]+)/avatar(?:/thumbnail)?", src)
    if asset_route is not None:
        if store is None or not project_id:
            return None
        asset_id = unquote(asset_route.group(1))
        if not asset_id or "/" in asset_id or "\\" in asset_id:
            return None
        try:
            from .services._project_assets import get_asset_content
            data, record = get_asset_content(project_id, asset_id, store=store)
        except (FileNotFoundError, KeyError, ValueError):
            return None
        mime = (str(record.get("media_type") or "").strip()
                or mimetypes.guess_type(str(record.get("filename") or ""))[0]
                or "application/octet-stream")
        return data, mime
    if avatar_route is not None:
        if store is None:
            return None
        persona_id = unquote(avatar_route.group(1))
        if not persona_id or "/" in persona_id or "\\" in persona_id:
            return None
        try:
            from .avatar import get_persona_avatar_content
            data, _persona = get_persona_avatar_content(persona_id, store=store)
        except (FileNotFoundError, KeyError, ValueError):
            return None
        return data, "image/png"
    return None
