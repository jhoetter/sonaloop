"""Presentation-from-data resolver (spec/methodology-presentation-from-data.md).

The UI must render a methodology ENTIRELY from data. This module is the single resolver: given a
tag (capability/role/artifact-type/discriminator) and an optional object-level `presentation` block,
it returns {label, short, color, icon, glyph} from one of three sources only:

  (S1) verbatim     — the raw tag string
  (S2) data hint    — a `presentation` block authored via MCP (object-level, or in suggestions/*.json)
  (S3) generic fn   — hash(tag)->palette color; raw string label; no icon/glyph

There is NO code map keyed to a specific value (no {"lofi": ...}, no {"prototype": ...}). All such
hints live in suggestions/*.json (authored via MCP) and are looked up by tag here.
"""
from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from .config import suggestions_dir

# Public deck-preview seam (sonaloop-research's deck.py rasterises the title slide of a
# generated .pptx). Re-exported here so extensions import a public name rather than the
# private _pptx_preview module; PIL/python-pptx stay lazy inside the function.
from ._pptx_preview import render_first_slide  # noqa: F401, E402

# A fixed, value-agnostic palette (colors are assigned by HASHING the tag, not by name).
PALETTE = ["#6b7cff", "#34a853", "#f29900", "#a142f4", "#ea4335", "#00897b", "#5f6368", "#d81b60"]

# Structural default glyphs (keyed to the geometric fan/waist BOOLEAN, never to a value string).
FAN_GLYPH, WAIST_GLYPH = "◇", "◆"  # ◇ hollow (fan) / ◆ filled (waist)

# Maps the (open-ended) Unicode notation glyphs used in suggestions/*.json and the
# fan/waist structural defaults onto sonaloop-design icon names, so the research graph
# and overview render real icons instead of text glyphs. Unmapped glyphs fall back
# to "square" (a neutral marker) rather than leaking raw Unicode.
GLYPH_ICON: dict[str, str] = {
    "◇": "diamond", "◆": "diamondFilled",
    "▢": "square", "▣": "squareSplit", "▤": "squareRows",
    "▥": "squareCols", "▦": "squareGrid", "▭": "rectangle",
    "⇄": "exchange", "∿": "wave", "❯∿": "wave",
    "⌕": "search", "✎": "pencil", "➤": "caretRight",
}


def glyph_icon(glyph: str | None) -> str:
    """Resolve a notation glyph to a sonaloop-design name. "" for no glyph; an
    unknown non-empty glyph maps to the neutral 'square' so nothing renders raw."""
    if not glyph:
        return ""
    return GLYPH_ICON.get(glyph, "square")

# The conventional artifact type for legacy records that predate the `type` field. A single
# back-compat default (not a value-keyed table); the real type list lives in artifact_types.json.
DEFAULT_ARTIFACT_TYPE = "prototype"


def hash_color(tag: str, palette: list[str] | None = None) -> str:
    pal = palette or PALETTE
    if not tag:
        return "#9aa0a6"
    return pal[sum(ord(c) for c in tag) % len(pal)]


@lru_cache(maxsize=1)
def _hints() -> dict[str, dict[str, Any]]:
    """Flatten all suggestions/*.json into a tag -> presentation(+meta) map. Includes nested
    artifact-type discriminators. Pure data; reloadable by clearing the cache."""
    out: dict[str, dict[str, Any]] = {}
    d = suggestions_dir()
    if not d.exists():
        return out
    for path in sorted(d.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if data.get("kind") == "ideation_lenses":
            continue  # creativity lenses are not presentation tags; read via ideation_lenses()
        for item in data.get("items", []) or []:
            tag = item.get("tag")
            if not tag:
                continue
            entry = dict(item.get("presentation") or {})
            for k in ("renderer", "default_template", "_note"):
                if item.get(k):
                    entry[k] = item[k]
            out.setdefault(tag, {}).update(entry)
            # nested discriminators (e.g. an artifact type's lofi/midfi) are tags too
            for disc in item.get("discriminators", []) or []:
                dtag = disc.get("tag")
                if not dtag:
                    continue
                dentry = dict(disc.get("presentation") or {})
                if disc.get("template"):
                    dentry["template"] = disc["template"]
                dentry["_parent"] = tag
                out.setdefault(dtag, {}).update(dentry)
    return out


def reload_hints() -> None:
    _hints.cache_clear()


def present(tag: str, own: dict[str, Any] | None = None) -> dict[str, Any]:
    """Resolve display fields for a tag. own = an object-level `presentation` block (highest
    priority, S2); then suggestions hints (S2); then generic fallbacks (S3)."""
    hint = _hints().get(tag, {})
    merged = {**hint, **(own or {})}
    label = merged.get("label") or (tag or "")
    return {
        "label": label,
        "short": merged.get("short") or label,
        "color": merged.get("color") or hash_color(tag),
        "icon": merged.get("icon") or "",
        "glyph": merged.get("glyph") or "",
    }


def step_glyph(is_fan: bool, own: dict[str, Any] | None = None) -> str:
    """The strip glyph is a function of the STRUCTURAL fan/waist boolean (S3), or a data override (S2)."""
    g = (own or {}).get("glyph")
    return g or (FAN_GLYPH if is_fan else WAIST_GLYPH)


# ---- artifact-type registry helpers (data-driven; replaces the TEMPLATES code map) ----

def artifact_type_meta(type_tag: str) -> dict[str, Any]:
    return _hints().get(type_tag, {})


def discriminator_tags(type_tag: str) -> list[str]:
    """Tags declared as discriminators of an artifact type (data-driven; e.g. the fidelity
    ladder lofi/midfi/hifi under `prototype`). No fidelity vocabulary is hardcoded in code."""
    return [t for t, v in _hints().items() if v.get("_parent") == type_tag]


@lru_cache(maxsize=1)
def edge_colors() -> dict[str, str]:
    """Graph edge-type → color, from suggestions/edge_types.json (DATA; no edge color hardcoded in
    engine/UI — Layer 2). Empty if the file is missing; callers fall back to a generic grey."""
    import json
    p = suggestions_dir() / "edge_types.json"
    out: dict[str, str] = {}
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return out
        for it in data.get("items", []) or []:
            if it.get("tag"):
                out[it["tag"]] = (it.get("presentation") or {}).get("color") or "#9aa0a6"
    return out


@lru_cache(maxsize=1)
def ideation_lenses() -> list[dict[str, Any]]:
    """SUGGESTED creativity lenses (DATA) surfaced on ideation steps to push the solution space toward
    non-obvious, innovative concepts (analogy, make-the-invisible-experienceable→simulation, reversal,
    extreme-user, …). Pure suggestion; editable in suggestions/ideation_lenses.json."""
    import json
    p = suggestions_dir() / "ideation_lenses.json"
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return []
    return [{"tag": i.get("tag", ""), "label": i.get("label", ""), "prompt": i.get("prompt", "")}
            for i in data.get("items", []) or [] if i.get("prompt")]


def artifact_palette() -> list[dict[str, Any]]:
    """The available artifact ARCHETYPES (top-level types with a renderer) as DATA, so the orchestrator
    can diversify concept KIND instead of defaulting to a form — a guided flow, a comparison, an
    overview, a card interface, an interactive MODEL (steerable numbers/curve), …. Pure suggestion;
    invent your own by adding to suggestions/artifact_types.json."""
    out = [{"tag": tag, "label": v.get("label") or tag, "note": v.get("_note", "")}
           for tag, v in _hints().items() if v.get("default_template") and not v.get("_parent")]
    return sorted(out, key=lambda x: x["tag"])


def resolve_template(type_tag: str, tags: list[str] | None = None,
                     explicit: str | None = None) -> str | None:
    """Resolve a renderer template for an artifact from DATA. Precedence: an explicit template wins;
    else a discriminator OF THIS TYPE that a tag matches (the fidelity ladder under `prototype`); else
    the type's own default_template; else a global tag→template match (back-compat for a tag used as a
    standalone type). Scoping discriminators to the type prevents a shared discriminator tag (e.g.
    `midfi`) on one type from hijacking another type's template."""
    if explicit:
        return explicit
    hints = _hints()
    # 1) a discriminator declared UNDER type_tag (e.g. prototype's lofi/midfi/hifi)
    for tg in (tags or []):
        h = hints.get(tg) or {}
        if h.get("template") and h.get("_parent") == type_tag:
            return h["template"]
    # 2) the type's own default renderer (a model tagged `midfi` stays spa-model, self-theming)
    own_default = (hints.get(type_tag) or {}).get("default_template")
    if own_default:
        return own_default
    # 3) back-compat: a tag that itself maps to a template
    for tg in (tags or []):
        tmpl = (hints.get(tg) or {}).get("template")
        if tmpl:
            return tmpl
    return None
