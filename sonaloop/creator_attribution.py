"""Least-privilege projections of immutable server-side creator attribution."""
from __future__ import annotations

from typing import Any


def public_creator_projection(value: Any) -> dict[str, str] | None:
    """Expose only a revalidated display label on public project surfaces."""
    if not isinstance(value, dict):
        return None
    label = value.get("label")
    if not isinstance(label, str):
        return None
    label = label.strip()
    if not label or len(label) > 160 or not label.isprintable():
        return None
    return {"label": label}
