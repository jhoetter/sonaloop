"""PowerPoint master inspection and semantic layout selection.

Uploaded customer decks are treated as layout/theme sources.  Their layout names are
the only portable signal available across PowerPoint, Keynote and LibreOffice, so the
matching deliberately stays conservative and falls back to the emptiest layout.
"""
from __future__ import annotations

from collections import Counter
import io
import re
from typing import Any


_BLANK_NAMES = {"blank", "leer", "leere folie", "vide", "en blanco"}


def _name(value: Any) -> str:
    return re.sub(r"[^\w]+", " ", str(value or "").casefold()).strip()


def layout_role(name: str) -> str:
    """Infer a small, platform-neutral role from a presentation layout name."""
    value = _name(name)
    if value in _BLANK_NAMES:
        return "blank"
    if any(token in value for token in (
            "closing", "thank", "questions", "abschluss", "schluss", "danke", "fragen")):
        return "closing"
    if any(token in value for token in (
            "section", "chapter", "divider", "kapitel", "abschnitt", "trennfolie")):
        return "section"
    if (value in {"title slide", "title", "titelfolie", "deckblatt", "cover"}
            or any(token in value for token in ("cover", "title slide", "titelfolie", "deckblatt"))):
        return "cover"
    if any(token in value for token in (
            "content", "inhalt", "body", "text", "chart", "diagram", "comparison",
            "vergleich", "image", "picture", "bild", "title only", "nur titel")):
        return "content"
    return "other"


def blank_layout(prs):
    layouts = list(prs.slide_layouts)
    if not layouts:
        raise ValueError("PowerPoint master contains no slide layouts")
    for layout in layouts:
        if layout_role(getattr(layout, "name", "")) == "blank":
            return layout
    return min(layouts, key=lambda layout: len(layout.placeholders))


def layout_for_slide(prs, slide: dict, fallback=None):
    """Choose the customer's closest semantic layout for a generated slide."""
    kind = str(slide.get("kind") or "content").casefold()
    wanted = (
        "cover" if kind in {"cover", "title"}
        else "section" if kind in {"section", "canvas-section"}
        else "closing" if kind == "closing"
        else "content"
    )
    matches = [layout for layout in prs.slide_layouts
               if layout_role(getattr(layout, "name", "")) == wanted]
    if matches:
        primary_tokens = {
            "cover": ("cover", "title slide", "titelfolie", "deckblatt"),
            "section": ("section", "kapitel", "abschnitt", "divider"),
            "closing": ("closing", "abschluss", "schluss", "thank", "danke"),
            "content": ("content", "inhalt", "body"),
        }[wanted]
        return min(matches, key=lambda layout: (
            0 if any(token in _name(getattr(layout, "name", ""))
                     for token in primary_tokens) else 1,
            len(_name(getattr(layout, "name", ""))),
            len(layout.placeholders),
        ))
    if wanted == "closing":
        sections = [layout for layout in prs.slide_layouts
                    if layout_role(getattr(layout, "name", "")) == "section"]
        if sections:
            return min(sections, key=lambda layout: len(layout.placeholders))
    return fallback or blank_layout(prs)


def inspect_master_template(data: bytes) -> dict[str, Any]:
    """Return a safe layout profile without retaining any customer slide content."""
    from pptx import Presentation

    prs = Presentation(io.BytesIO(data))
    layouts = []
    roles: Counter[str] = Counter()
    for index, layout in enumerate(prs.slide_layouts):
        role = layout_role(getattr(layout, "name", ""))
        roles[role] += 1
        placeholder_types = []
        for placeholder in layout.placeholders:
            raw = placeholder.placeholder_format.type
            placeholder_types.append(str(getattr(raw, "name", raw)).casefold())
        layouts.append({
            "index": index,
            "name": str(getattr(layout, "name", "") or f"Layout {index + 1}"),
            "role": role,
            "placeholder_count": len(layout.placeholders),
            "placeholder_types": placeholder_types,
        })
    return {
        "layout_count": len(layouts),
        "layouts": layouts,
        "role_counts": dict(sorted(roles.items())),
    }
