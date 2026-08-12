"""Presentation geometry for screenshot-relative session reading hypotheses."""
from __future__ import annotations

from pathlib import Path

from .. import config


def focus_crop(focus: dict, asset: dict | None) -> dict | None:
    """Map a full-long-shot focus rectangle into a bounded 16:10 viewport.

    Stored percentages stay relative to the unchanged source. Missing or legacy dimensions
    fail soft to the full image; local pre-metadata assets read only their image header.
    """
    image = (asset or {}).get("image") or {}
    try:
        width, height = int(image["width"]), int(image["height"])
    except (KeyError, TypeError, ValueError):
        try:
            from PIL import Image
            name = Path(str((asset or {})["asset_path"])).name
            with Image.open(config.partition_dir() / "assets" / name) as source:
                width, height = source.size
        except (KeyError, OSError, TypeError, ValueError):
            return None
    if width <= 0 or height <= 0:
        return None
    stage_ratio = 16 / 10
    natural_view = (width / height) / stage_ratio
    focus_height = focus["height"] / 100
    visible = min(1.0, max(natural_view, focus_height + .10))
    focus_center = (focus["y"] + focus["height"] / 2) / 100
    top = min(max(focus_center - visible / 2, 0), 1 - visible)
    mapped = dict(focus)
    mapped["y"] = max(0.0, (focus["y"] / 100 - top) / visible * 100)
    mapped["height"] = min(100 - mapped["y"], focus_height / visible * 100)
    return {"top": top * 100, "focus": mapped, "width": width}


def focus_lens_attrs(crop: dict | None) -> dict:
    """HTML attributes for a crop without adding an inline-style literal to page modules."""
    attrs = {"class_": "sl-session-lens sl-session-crop" if crop else "sl-session-lens"}
    if crop:
        attrs["style"] = f'--crop-y:-{crop["top"]:g}%;--shot-max:{crop["width"]}px'
        attrs["data-focus-source"] = "full-screenshot"
    return attrs
