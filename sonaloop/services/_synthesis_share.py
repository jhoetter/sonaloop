"""Security-sensitive helpers for self-contained synthesis exports."""

from __future__ import annotations

import base64
import html as html_mod
import mimetypes
import re
from pathlib import Path
from typing import Any

from ..storage import Store


SHARE_LABELS = {
    "de": {"project": "Projekt", "generated": "erzeugt", "footer": "Schreibgeschützter Report",
           "missing": "Medium nicht verfügbar"},
    "en": {"project": "Project", "generated": "generated", "footer": "Read-only report",
           "missing": "media unavailable"},
}

# These post-processors enforce the zero-request invariant and accept both quote styles.
_A_TAG = re.compile(r"<a\b([^>]*)>(.*?)</a>", re.DOTALL | re.IGNORECASE)
_HREF_ATTR = re.compile(r'''\bhref=(?:"([^"]*)"|'([^']*)')''', re.IGNORECASE)
_CLASS_ATTR = re.compile(r'''\bclass=(?:"([^"]*)"|'([^']*)')''', re.IGNORECASE)
_IMG_TAG = re.compile(r"<img\b[^>]*>", re.IGNORECASE)
_SRC_ATTR = re.compile(r'''\bsrc=(?:"([^"]*)"|'([^']*)')''', re.IGNORECASE)
_INLINE_MAX_BYTES = 8 * 1024 * 1024


def share_rewrite_links(html_text: str) -> str:
    """Turn live/external links into styled text while retaining internal anchors."""
    def _one(match: re.Match) -> str:
        attrs, inner = match.group(1), match.group(2)
        href_match = _HREF_ATTR.search(attrs)
        href = (href_match.group(1) if href_match and href_match.group(1) is not None
                else (href_match.group(2) if href_match else "")) or ""
        if href.startswith("#"):
            return match.group(0)
        class_match = _CLASS_ATTR.search(attrs)
        css_class = (class_match.group(1) if class_match and class_match.group(1) is not None
                     else (class_match.group(2) if class_match else "")) or ""
        classes = f"{css_class} share-unlinked".strip()
        return f'<span class="{classes}">{inner}</span>'

    return _A_TAG.sub(_one, html_text)


def share_inline_images(html_text: str, missing_label: str = "media unavailable", *,
                        store: Store | None = None, project_id: str = "",
                        max_bytes: int = _INLINE_MAX_BYTES) -> str:
    """Inline admitted local media; unresolved or escaping sources fail closed visibly."""
    from .. import config

    data_root = config.partition_dir().resolve()
    note = f'<span class="share-missing">[{html_mod.escape(missing_label)}]</span>'

    def _one(match: re.Match) -> str:
        tag = match.group(0)
        src_match = _SRC_ATTR.search(tag)
        if not src_match:
            return note
        group = 1 if src_match.group(1) is not None else 2
        src = html_mod.unescape(src_match.group(group))
        if src.startswith("data:"):
            return tag
        data: bytes
        mime: str
        if src.startswith("/data/"):
            rel = Path(src[len("/data/"):])
            try:
                physical_prefix = data_root.relative_to(Path(config.DATA_DIR).resolve())
            except ValueError:
                physical_prefix = Path()
            if physical_prefix.parts and rel.parts[:len(physical_prefix.parts)] == physical_prefix.parts:
                file_path = (Path(config.DATA_DIR) / rel).resolve()
            else:
                file_path = (data_root / rel).resolve()
            if not file_path.is_relative_to(data_root) or not file_path.is_file():
                return note
            if file_path.stat().st_size > max_bytes:
                return note
            data = file_path.read_bytes()
            mime = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
        else:
            from ..export_media import resolve_export_image

            resolved = resolve_export_image(src, store=store, project_id=project_id)
            if resolved is None:
                return note
            data, mime = resolved
            if len(data) > max_bytes:
                return note
        uri = f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"
        return tag[:src_match.start(group)] + uri + tag[src_match.end(group):]

    return _IMG_TAG.sub(_one, html_text)


def theme_block(theme_overrides: dict[str, Any] | None) -> str:
    """Validate and render the customer-theme CSS override for an export."""
    if not theme_overrides:
        return ""
    from ..theming import customer_theme_css, validate_customer_theme

    return customer_theme_css(validate_customer_theme(theme_overrides))


PDF_FONTS = ('<link rel="preconnect" href="https://fonts.googleapis.com">'
             '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
             '<link href="https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600;700'
             '&family=Geist+Mono:wght@400;500&display=swap" rel="stylesheet">')
