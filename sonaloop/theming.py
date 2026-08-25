"""Workspace design-system v2 contract.

The customer-owned design system is now a structured data object, not a small set
of CSS overrides. Core owns the canonical validator/compiler: callers pass a
workspace design-system payload, this module merges it over the Sonaloop defaults,
validates the result, and exposes deterministic surface inputs for web CSS,
brand rendering, charts and the deck renderer.

No arbitrary CSS, JavaScript, remote runtime fonts or component replacement is
accepted here. Later tickets decide where the compiled data is stored and how each
surface consumes it.
"""
from __future__ import annotations

import contextvars
from copy import deepcopy
import hashlib
import json
import re
from pathlib import Path
from functools import lru_cache
from typing import Any

SPEC_VERSION = "workspace_design_system.v2"

# CSS-injection guard used by the live web extension seam. Values may contain
# quoted font family names, but never declaration-breaking punctuation.
_VAR_RE = re.compile(r"^--[a-z0-9-]+$")
_VAL_RE = re.compile(r"^[#a-zA-Z0-9_.,%()\"'\s/-]+$")

_HEX_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")
_CSS_TOKEN_RE = re.compile(r"^[#a-zA-Z0-9_.,%()\"'\s/-]+$")
_LENGTH_RE = re.compile(r"^(?:0|[0-9]+(?:\.[0-9]+)?(?:px|rem|em|ch|%))$")
_DATA_IMAGE_RE = re.compile(r"^data:image/[a-z0-9.+-]+;base64,[A-Za-z0-9+/=\s]*$")

TOP_LEVEL_KEYS = (
    "spec_version", "meta", "brand", "colors", "typography", "layout",
    "imagery", "charts", "deck", "exports",
)
COLOR_ROLES = (
    "paper", "paper_2", "ink", "ink_2", "muted", "faint", "line", "line_2",
    "panel", "panel_2", "sidebar", "overlay", "accent", "accent_ink",
    "accent_weak", "hover", "selected", "green", "amber", "red", "blue",
    "violet", "skeptical",
)
FONT_ROLES = ("sans", "serif", "mono", "display", "pixel")
BRAND_LOGO_ROLES = ("icon", "wordmark", "lockup", "lockup_dark", "mono", "reversed", "favicon")
IMAGERY_ROLES = ("canvas", "hero", "report_cover", "deck_cover", "section", "closing",
                 "pattern", "product_frame")

_COLOR_TO_CSS = {
    "paper": ("--bg", "--sl-bg"),
    "paper_2": ("--paper-2",),
    "ink": ("--ink", "--sl-ink"),
    "ink_2": ("--ink-2",),
    "muted": ("--muted", "--sl-muted"),
    "faint": ("--faint", "--sl-faint"),
    "line": ("--line", "--sl-line"),
    "line_2": ("--line-2", "--sl-line-2"),
    "panel": ("--panel", "--sl-surface"),
    "panel_2": ("--panel-2", "--sl-surface-2"),
    "sidebar": ("--sidebar", "--sl-sidebar"),
    "overlay": ("--overlay", "--sl-overlay"),
    "accent": ("--accent", "--sl-accent"),
    "accent_ink": ("--accent-ink", "--sl-accent-ink"),
    "accent_weak": ("--accent-weak", "--sl-accent-weak"),
    "hover": ("--hover", "--sl-hover"),
    "selected": ("--sel", "--sl-sel"),
    "green": ("--green", "--sl-green"),
    "amber": ("--amber", "--sl-amber"),
    "red": ("--red", "--sl-red"),
    "blue": ("--blue", "--sl-blue"),
    "violet": ("--violet", "--sl-violet"),
    "skeptical": ("--skep", "--sl-skep"),
}
_FONT_TO_CSS = {
    "sans": ("--sl-sans", "--sans"),
    "mono": ("--sl-mono", "--mono"),
    "pixel": ("--sl-pixel", "--pixel"),
}
_TYPE_TO_CSS = {
    "t_xs": "--t-xs", "t_sm": "--t-sm", "t_body": "--t-body", "t_md": "--t-md",
    "t_prose": "--t-prose", "t_lg": "--t-lg", "t_xl": "--t-xl", "t_2xl": "--t-2xl",
}
_LAYOUT_TO_CSS = {
    "radius_sm": ("--radius-sm", "--sl-radius-sm"),
    "radius": ("--radius", "--sl-radius"),
    "radius_lg": ("--radius-lg", "--sl-radius-lg"),
    "radius_full": ("--radius-full", "--sl-radius-full"),
    "s_1": ("--s-1", "--sl-s-1"),
    "s_2": ("--s-2", "--sl-s-2"),
    "s_3": ("--s-3", "--sl-s-3"),
    "s_4": ("--s-4", "--sl-s-4"),
    "s_5": ("--s-5", "--sl-s-5"),
    "s_6": ("--s-6", "--sl-s-6"),
    "s_8": ("--s-8", "--sl-s-8"),
    "gap_tight": ("--gap-tight", "--sl-gap-tight"),
    "gap_item": ("--gap-item", "--sl-gap-item"),
    "gap_group": ("--gap-group", "--sl-gap-group"),
    "gap_section": ("--gap-section", "--sl-gap-section"),
    "gap_region": ("--gap-region", "--sl-gap-region"),
    "row_dense": ("--row-dense", "--sl-row-dense"),
    "row": ("--row", "--sl-row"),
    "row_h": ("--row-h", "--sl-row-h"),
    "ctl_sm": ("--ctl-sm", "--sl-ctl-sm"),
    "measure_prose": ("--measure-prose", "--sl-measure-prose"),
    "ease": ("--ease", "--sl-ease"),
}

DEFAULT_DESIGN_SYSTEM: dict[str, Any] = {
    "spec_version": SPEC_VERSION,
    "meta": {"name": "Sonaloop default", "source": "sonaloop"},
    "brand": {
        "name": "Sonaloop",
        "short_name": "Sonaloop",
        "tagline": "Synthetic research that disagrees with you",
        "logo_variants": {
            "icon": {"kind": "builtin", "ref": "sonaloop"},
            "lockup": {"kind": "text_lockup", "text": "Sonaloop"},
        },
        "logo_preferred": "lockup",
        "deck_logo_preferred": "icon",
        "report_logo_preferred": "lockup",
    },
    "colors": {
        "light": {
            "paper": "#faf8f3", "paper_2": "#f1efe8", "ink": "#1a1815",
            "ink_2": "#635e56", "muted": "#635e56", "faint": "#8c857a",
            "line": "#e9e5db", "line_2": "#f0ede5", "panel": "#ffffff",
            "panel_2": "#f1efe8", "sidebar": "#f6f4ef", "overlay": "#ffffff",
            "accent": "#5e6ad2", "accent_ink": "#ffffff", "accent_weak": "#ecebf8",
            "hover": "#f4f1ea", "selected": "#ece9df", "green": "#3d9b6b",
            "amber": "#b87a25", "red": "#cf4d5f", "blue": "#3d7fc4",
            "violet": "#7a5ed1", "skeptical": "#c2683f",
        },
        "dark": {
            "paper": "#101113", "paper_2": "#1c1d21", "ink": "#e6e7ea",
            "ink_2": "#8a8f98", "muted": "#8a8f98", "faint": "#6b7076",
            "line": "#23252a", "line_2": "#1b1d21", "panel": "#16171a",
            "panel_2": "#1c1d21", "sidebar": "#0d0e10", "overlay": "#1a1b1e",
            "accent": "#7c84e8", "accent_ink": "#ffffff", "accent_weak": "#1d2030",
            "hover": "#1a1b1f", "selected": "#1f2128", "green": "#4cb782",
            "amber": "#d9a23b", "red": "#e0566a", "blue": "#5e9fe0",
            "violet": "#9a8cff", "skeptical": "#d98a63",
        },
    },
    "typography": {
        "fonts": {
            "sans": {"family": "Sona", "stack": ["Sona", "Geist", "Inter", "system-ui", "sans-serif"]},
            "serif": {"family": "Sona", "stack": ["Sona", "Geist", "Inter", "system-ui", "sans-serif"]},
            "mono": {"family": "Sona Mono", "stack": ["Sona Mono", "Geist Mono", "ui-monospace", "monospace"]},
            "display": {"family": "Sona", "stack": ["Sona", "Geist", "Inter", "system-ui", "sans-serif"]},
            "pixel": {"family": "Sona Pixel", "stack": ["Sona Pixel", "ui-monospace", "monospace"]},
        },
        "type_scale": {
            "t_xs": "11px", "t_sm": "12px", "t_body": "13px", "t_md": "15px",
            "t_prose": "16px", "t_lg": "18px", "t_xl": "24px", "t_2xl": "32px",
        },
    },
    "layout": {
        "radius": {"radius_sm": "6px", "radius": "8px", "radius_lg": "12px", "radius_full": "9999px"},
        "spacing": {"s_1": "4px", "s_2": "8px", "s_3": "12px", "s_4": "16px", "s_5": "20px", "s_6": "24px", "s_8": "32px"},
        "gaps": {"gap_tight": "4px", "gap_item": "8px", "gap_group": "12px", "gap_section": "24px", "gap_region": "32px"},
        "density": {"row_dense": "32px", "row": "40px", "row_h": "48px", "ctl_sm": "28px"},
        "reading": {"measure_prose": "70ch"},
        "motion": {"ease": "cubic-bezier(.4,0,.2,1)"},
        "elevation": {
            "light": {"shadow_sm": "0 1px 2px rgba(26,24,21,.05)",
                      "shadow_lg": "0 8px 28px rgba(26,24,21,.12),0 1px 2px rgba(26,24,21,.07)"},
            "dark": {"shadow_sm": "0 1px 2px rgba(0,0,0,.4)",
                     "shadow_lg": "0 8px 28px rgba(0,0,0,.45),0 1px 2px rgba(0,0,0,.3)"},
        },
    },
    "imagery": {
        "sets": {
            "canvas": {"label": "Canvas", "light_asset": "builtin:canvas.light",
                       "dark_asset": "builtin:canvas.dark", "deck_asset": "builtin:canvas.deck"},
            "meadow": {"label": "Meadow", "light_asset": "builtin:meadow.light",
                       "dark_asset": "builtin:meadow.dark", "deck_asset": "builtin:meadow.deck"},
        },
        "roles": {"canvas": "canvas", "hero": "canvas", "report_cover": "canvas",
                  "deck_cover": "canvas", "section": "meadow", "closing": "canvas",
                  "pattern": "canvas", "product_frame": "canvas"},
    },
    "charts": {
        "series": ["#5e6ad2", "#7a5ed1", "#3d7fc4", "#3d9b6b", "#b87a25", "#cf4d5f", "#c2683f"],
        "status": {"positive": "#3d9b6b", "warning": "#b87a25", "negative": "#cf4d5f",
                   "skeptical": "#c2683f", "neutral": "#635e56"},
        "grid": "#e9e5db",
        "label_font_role": "sans",
    },
    "deck": {
        "boundary": "tokenized_master_deck",
        "master_asset_ref": "", "style_reference_asset_ref": "",
        "logo_preferred": "icon",
        "canvas_preferred": "canvas",
        "font_role": "sans",
        "chart_series": ["#5e6ad2", "#7a5ed1", "#3d7fc4", "#3d9b6b", "#b87a25", "#cf4d5f", "#c2683f"],
        "layout_kinds": ["cover", "agenda", "section", "canvas-section", "summary", "insight",
                         "recommendation", "risk", "quote", "voices", "stats", "chart",
                         "comparison", "timeline", "closing", "content", "image"],
    },
    "exports": {
        "html": {"bundle_assets": True, "snapshot_design_system_version": True},
        "pdf": {"render_from_html": True, "snapshot_design_system_version": True},
        "pptx": {"native_shapes": True, "snapshot_design_system_version": True,
                 "warn_on_uninstalled_fonts": True},
    },
}

def validate_customer_design_system_v2(raw: Any) -> dict[str, Any]:
    """Validate and normalize a workspace design-system payload.

    The returned dict is complete: partial payloads are merged over
    DEFAULT_DESIGN_SYSTEM and then validated, so downstream renderers can consume it
    without applying their own defaults.
    """
    if not isinstance(raw, dict):
        raise ValueError("workspace design system must be an object")
    unknown = sorted(set(map(str, raw)) - set(TOP_LEVEL_KEYS))
    if unknown:
        raise ValueError(f"unknown design-system key(s) {unknown} - valid: {list(TOP_LEVEL_KEYS)}")
    spec = raw.get("spec_version", SPEC_VERSION)
    if spec != SPEC_VERSION:
        raise ValueError(f"design-system spec_version must be {SPEC_VERSION!r}")
    ds = deepcopy(DEFAULT_DESIGN_SYSTEM)
    _deep_merge(ds, raw)
    ds["spec_version"] = SPEC_VERSION
    _validate_meta(ds["meta"])
    _validate_brand(ds["brand"])
    _validate_colors(ds["colors"])
    _validate_typography(ds["typography"])
    _validate_layout(ds["layout"])
    _validate_imagery(ds["imagery"])
    _validate_charts(ds["charts"])
    _validate_deck(ds["deck"])
    _validate_exports(ds["exports"])
    return ds


def validate_customer_theme(raw: Any) -> dict[str, Any]:
    """Compatibility name for callers that still route through `theme_overrides=`.

    It validates the new v2 design-system shape only.
    """
    return validate_customer_design_system_v2(raw)


def compile_customer_design_system(raw: Any) -> dict[str, Any]:
    """Return deterministic compiled surface inputs for a v2 design system."""
    ds = validate_customer_design_system_v2(raw)
    canonical_json = json.dumps(ds, sort_keys=True, separators=(",", ":"))
    return {
        "spec_version": SPEC_VERSION,
        "compiled_hash": hashlib.sha256(canonical_json.encode("utf-8")).hexdigest(),
        "design_system": ds,
        "css": customer_design_system_css(ds),
        "css_vars": {
            "light": theme_override_vars(ds, scheme="light"),
            "dark": theme_override_vars(ds, scheme="dark"),
        },
        "brand": brand_context(ds),
        "charts": chart_palette(ds),
        "deck": deck_theme(ds),
    }


def theme_override_vars(theme: dict[str, Any], *, scheme: str = "light") -> dict[str, str]:
    """Flatten a validated v2 design system into CSS custom properties for one scheme."""
    ds = validate_customer_design_system_v2(theme)
    if scheme not in ("light", "dark"):
        raise ValueError("scheme must be 'light' or 'dark'")
    out: dict[str, str] = {}
    for role, value in ds["colors"][scheme].items():
        for var in _COLOR_TO_CSS.get(role, ()):
            out[var] = value
    for idx, color in enumerate(ds["charts"]["series"][:7], 1):
        out[f"--c{idx}"] = color
        out[f"--sl-chart-series-{idx}"] = color
    for role, color in ds["charts"]["status"].items():
        out[f"--sl-chart-status-{role}"] = color
    out["--sl-chart-grid"] = ds["charts"]["grid"]
    for role, spec in ds["typography"]["fonts"].items():
        if role in _FONT_TO_CSS:
            stack = _font_stack_css(spec["stack"])
            for var in _FONT_TO_CSS[role]:
                out[var] = stack
    for role, value in ds["typography"]["type_scale"].items():
        if role in _TYPE_TO_CSS:
            out[_TYPE_TO_CSS[role]] = value
    for group in ("radius", "spacing", "gaps", "density", "reading", "motion"):
        for role, value in ds["layout"][group].items():
            for var in _LAYOUT_TO_CSS.get(role, ()):
                out[var] = value
    for key, css_var in (("shadow_sm", "--shadow-sm"), ("shadow_lg", "--shadow-lg")):
        out[css_var] = ds["layout"]["elevation"][scheme][key]
    return out


def customer_design_system_css(theme: dict[str, Any]) -> str:
    """A complete override block for a validated v2 design system."""
    ds = validate_customer_design_system_v2(theme)
    light = _decls(theme_override_vars(ds, scheme="light"))
    dark = _decls(theme_override_vars(ds, scheme="dark"))
    return ("<style id=\"theme-overrides\">"
            f":root{{{light}}}"
            f":root[data-theme=\"light\"]{{{light}}}"
            f":root[data-theme=\"dark\"]{{{dark}}}"
            f"@media (prefers-color-scheme: dark){{:root{{{dark}}}}}"
            "</style>")


def customer_theme_css(theme: dict[str, Any]) -> str:
    """Compatibility name for export code; emits v2 design-system CSS only."""
    return customer_design_system_css(theme)


def brand_context(theme: dict[str, Any]) -> dict[str, str | None]:
    ds = validate_customer_design_system_v2(theme)
    brand = ds["brand"]
    preferred = brand.get("logo_preferred") or "lockup"
    variant = brand.get("logo_variants", {}).get(preferred) or {}
    variants = brand.get("logo_variants", {})  # Never recolor customer art.
    dark_role = ("lockup_dark" if variants.get("lockup_dark") else "reversed" if variants.get("reversed") else None)
    dark_variant = variants.get(dark_role) if dark_role else {}
    return {
        "name": brand["name"], "short_name": brand.get("short_name") or brand["name"],
        "logo": variant.get("src") or variant.get("asset_ref"),
        "logo_role": preferred,
        "logo_dark": (dark_variant or {}).get("src") or (dark_variant or {}).get("asset_ref"),
        "logo_dark_role": dark_role,
    }


def chart_palette(theme: dict[str, Any]) -> dict[str, Any]:
    ds = validate_customer_design_system_v2(theme)
    return deepcopy(ds["charts"])


def deck_theme(theme: dict[str, Any]) -> dict[str, Any]:
    ds = validate_customer_design_system_v2(theme)
    colors = ds["colors"]["light"]
    chart_status = ds["charts"]["status"]
    from . import _deck

    type_roles = deepcopy(_deck.TYPE)
    scale = ds["typography"]["type_scale"]
    role_sizes = {
        "eyebrow": _pt_from_length(scale["t_sm"], type_roles["eyebrow"]["size"]),
        "display": _pt_from_length(scale["t_2xl"], type_roles["display"]["size"], multiplier=1.25),
        "title": _pt_from_length(scale["t_xl"], type_roles["title"]["size"]),
        "subtitle": _pt_from_length(scale["t_md"], type_roles["subtitle"]["size"]),
        "lead": _pt_from_length(scale["t_lg"], type_roles["lead"]["size"]),
        "statement": _pt_from_length(scale["t_xl"], type_roles["statement"]["size"], multiplier=1.08),
        "body": _pt_from_length(scale["t_body"], type_roles["body"]["size"]),
        "quote": _pt_from_length(scale["t_xl"], type_roles["quote"]["size"]),
        "attribution": _pt_from_length(scale["t_sm"], type_roles["attribution"]["size"]),
        "caption": _pt_from_length(scale["t_xs"], type_roles["caption"]["size"]),
        "num": _pt_from_length(scale["t_md"], type_roles["num"]["size"]),
        "bignum": _pt_from_length(scale["t_2xl"], type_roles["bignum"]["size"], multiplier=3.4),
        "kpi": _pt_from_length(scale["t_2xl"], type_roles["kpi"]["size"]),
        "kpiLabel": _pt_from_length(scale["t_xs"], type_roles["kpiLabel"]["size"]),
    }
    for role, size in role_sizes.items():
        if role in type_roles:
            type_roles[role]["size"] = size

    font_role = ds["deck"]["font_role"]
    font = deepcopy(ds["typography"]["fonts"][font_role])
    warnings: list[dict[str, Any]] = []
    if font["family"] != DEFAULT_DESIGN_SYSTEM["typography"]["fonts"][font_role]["family"]:
        warnings.append({
            "code": "pptx_font_not_embedded",
            "role": font_role,
            "family": font["family"],
            "asset_ids": list(font.get("asset_ids") or []),
            "message": "PowerPoint recipients may need this font installed; deck text remains editable.",
        })
    return {
        "boundary": ds["deck"]["boundary"],
        "master_asset_ref": ds["deck"].get("master_asset_ref") or "", "style_reference_asset_ref": ds["deck"].get("style_reference_asset_ref") or "",
        "logo_preferred": ds["deck"]["logo_preferred"],
        "canvas_preferred": ds["deck"]["canvas_preferred"],
        "font_role": font_role,
        "font": font,
        "series": list(ds["deck"]["chart_series"]),
        "palette": {
            "bg": _pptx_hex(colors["paper"]),
            "panel": _pptx_hex(colors["panel"]),
            "surface2": _pptx_hex(colors["panel_2"]),
            "line": _pptx_hex(colors["line"]),
            "ink": _pptx_hex(colors["ink"]),
            "muted": _pptx_hex(colors["muted"]),
            "faint": _pptx_hex(colors["faint"]),
            "accent": _pptx_hex(colors["accent"]),
            "accentInk": _pptx_hex(colors["accent_ink"]),
            "accentWeak": _pptx_hex(colors["accent_weak"]),
            "green": _pptx_hex(chart_status.get("positive") or colors["green"]),
            "amber": _pptx_hex(chart_status.get("warning") or colors["amber"]),
            "red": _pptx_hex(chart_status.get("negative") or colors["red"]),
            "violet": _pptx_hex(colors["violet"]),
            "blue": _pptx_hex(colors["blue"]),
            "skep": _pptx_hex(chart_status.get("skeptical") or colors["skeptical"]),
            "series": [_pptx_hex(c) for c in ds["deck"]["chart_series"]],
        },
        "type": type_roles,
        "geometry": {
            "frame": deepcopy(_deck.FRAME),
            "radius": deepcopy(ds["layout"]["radius"]),
            "spacing": deepcopy(ds["layout"]["spacing"]),
        },
        "assets": _deck_asset_manifest(ds),
        "colors": deepcopy(ds["colors"]["light"]),
        "brand": brand_context(ds),
        "chart_palette": chart_palette(ds),
        "warnings": warnings,
    }


def _pptx_hex(value: str) -> str:
    raw = str(value).strip().lstrip("#")
    if len(raw) == 3:
        raw = "".join(ch * 2 for ch in raw)
    return raw.upper()


def _pt_from_length(value: str, fallback: int | float, *, multiplier: float = 1.0) -> int:
    raw = str(value).strip()
    m = re.match(r"^([0-9]+(?:\.[0-9]+)?)px$", raw)
    if not m:
        return int(round(float(fallback)))
    return max(1, int(round(float(m.group(1)) * 0.75 * multiplier)))


def _deck_asset_manifest(ds: dict[str, Any]) -> dict[str, Any]:
    brand = ds["brand"]
    logo_role = ds["deck"].get("logo_preferred") or brand.get("deck_logo_preferred") or brand.get("logo_preferred")
    logo_spec = deepcopy((brand.get("logo_variants") or {}).get(logo_role) or {})
    imagery: dict[str, Any] = {}
    sets = ds["imagery"]["sets"]
    for role in ("deck_cover", "section", "closing", "canvas"):
        set_key = ds["imagery"]["roles"].get(role)
        spec = deepcopy(sets.get(set_key) or {})
        imagery[role] = {
            "role": role,
            "set": set_key,
            "ref": spec.get("deck_asset") or spec.get("light_asset") or spec.get("dark_asset") or "",
            "label": spec.get("label") or set_key,
        }
    return {
        "logo": {
            "role": logo_role,
            "ref": logo_spec.get("asset_ref") or logo_spec.get("src") or logo_spec.get("ref") or "",
            "kind": logo_spec.get("kind") or "",
        },
        "imagery": imagery,
    }


def font_face_manifest(theme: dict[str, Any], asset_urls: dict[str, str] | None = None) -> list[dict[str, Any]]:
    """Font-face inputs for workspace renderers.

    Core validates the font roles and records which uploaded font assets belong to
    each role. Cloud owns the actual workspace asset URLs, so callers may pass an
    `asset_urls` map when they want CSS emitted in this process.
    """
    ds = validate_customer_design_system_v2(theme)
    urls = dict(asset_urls or {})
    faces: list[dict[str, Any]] = []
    for role, spec in ds["typography"]["fonts"].items():
        for asset_id in spec.get("asset_ids") or []:
            asset_id = str(asset_id)
            rec = {"role": role, "family": spec["family"], "asset_id": asset_id,
                   "url": urls.get(asset_id, "")}
            faces.append(rec)
    return faces


def font_face_css(theme: dict[str, Any], asset_urls: dict[str, str] | None = None) -> str:
    faces = []
    for rec in font_face_manifest(theme, asset_urls):
        if not rec.get("url"):
            continue
        fmt = "woff2" if str(rec["url"]).lower().endswith(".woff2") else "woff"
        family = str(rec["family"]).replace("\\", "\\\\").replace('"', '\\"')
        url = str(rec["url"]).replace("\\", "\\\\").replace('"', '\\"')
        faces.append(
            f'@font-face{{font-family:"{family}";src:url("{url}") format("{fmt}");'
            "font-weight:400;font-style:normal;font-display:swap}}"
        )
    return "<style id=\"workspace-font-faces\">" + "".join(faces) + "</style>" if faces else ""


def _runtime_cache_key(workspace_id: str, version_id: str, compiled_hash: str,
                       scheme: str, surface: str) -> str:
    return "|".join((workspace_id or "default", version_id or "default",
                     compiled_hash, scheme, surface))


@lru_cache(maxsize=256)
def _runtime_context_cached(canonical_json: str, workspace_id: str, version_id: str,
                            compiled_hash: str, scheme: str, surface: str) -> dict[str, Any]:
    ds = json.loads(canonical_json)
    compiled = compile_customer_design_system(ds)
    return {
        "workspace_id": workspace_id,
        "version_id": version_id,
        "surface": surface,
        "scheme": scheme,
        "cache_key": _runtime_cache_key(workspace_id, version_id, compiled_hash, scheme, surface),
        "spec_version": compiled["spec_version"],
        "compiled_hash": compiled_hash,
        "design_system": compiled["design_system"],
        "css_vars": compiled["css_vars"][scheme],
        "css_vars_by_scheme": compiled["css_vars"],
        "css": compiled["css"],
        "brand": compiled["brand"],
        "charts": compiled["charts"],
        "deck": compiled["deck"],
        "imagery": deepcopy(compiled["design_system"]["imagery"]),
    }


def runtime_design_system_context(theme: dict[str, Any] | None = None, *,
                                  workspace_id: str = "",
                                  version_id: str = "",
                                  scheme: str = "light",
                                  surface: str = "app",
                                  font_asset_urls: dict[str, str] | None = None) -> dict[str, Any]:
    """Compiled design-system context consumed by request, report and export renderers."""
    if scheme not in ("light", "dark"):
        raise ValueError("scheme must be 'light' or 'dark'")
    ds = validate_customer_design_system_v2(theme or DEFAULT_DESIGN_SYSTEM)
    canonical_json = json.dumps(ds, sort_keys=True, separators=(",", ":"))
    compiled_hash = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
    ctx = deepcopy(_runtime_context_cached(
        canonical_json, workspace_id or "", version_id or "", compiled_hash, scheme, surface or "app"))
    ctx["font_faces"] = font_face_manifest(ds, font_asset_urls)
    ctx["font_face_css"] = font_face_css(ds, font_asset_urls)
    return ctx


_ACTIVE_RUNTIME_DESIGN_SYSTEM: contextvars.ContextVar[dict[str, Any] | None] = contextvars.ContextVar(
    "active_runtime_design_system", default=None)


def set_runtime_design_system_context(context: dict[str, Any] | None) -> contextvars.Token:
    return _ACTIVE_RUNTIME_DESIGN_SYSTEM.set(deepcopy(context) if context else None)


def reset_runtime_design_system_context(token: contextvars.Token) -> None:
    _ACTIVE_RUNTIME_DESIGN_SYSTEM.reset(token)


def active_runtime_design_system_context() -> dict[str, Any] | None:
    ctx = _ACTIVE_RUNTIME_DESIGN_SYSTEM.get()
    return deepcopy(ctx) if ctx else None


def _deep_merge(dst: dict[str, Any], src: dict[str, Any]) -> None:
    for key, value in src.items():
        if key == "spec_version":
            continue
        if isinstance(value, dict) and isinstance(dst.get(key), dict):
            _deep_merge(dst[key], value)
        else:
            dst[key] = deepcopy(value)


def _validate_meta(meta: Any) -> None:
    _object(meta, "meta")
    if "name" in meta and not str(meta["name"]).strip():
        raise ValueError("meta.name must be non-empty when provided")


def _validate_brand(brand: Any) -> None:
    _object(brand, "brand")
    _keys(brand, "brand", ("name", "short_name", "tagline", "logo_variants", "logo_preferred",
                           "deck_logo_preferred", "report_logo_preferred", "clear_space"))
    if not str(brand.get("name", "")).strip():
        raise ValueError("brand.name must be a non-empty string")
    variants = _object(brand.get("logo_variants", {}), "brand.logo_variants")
    bad_roles = sorted(set(map(str, variants)) - set(BRAND_LOGO_ROLES))
    if bad_roles:
        raise ValueError(f"unknown logo variant(s) {bad_roles} - valid: {list(BRAND_LOGO_ROLES)}")
    for role, spec in variants.items():
        _validate_asset_ref(spec, f"brand.logo_variants.{role}", allow_builtin=True)
    for pref in ("logo_preferred", "deck_logo_preferred", "report_logo_preferred"):
        if brand.get(pref) and brand[pref] not in variants:
            raise ValueError(f"brand.{pref} references missing logo variant {brand[pref]!r}")


def _validate_colors(colors: Any) -> None:
    _object(colors, "colors")
    _keys(colors, "colors", ("light", "dark"))
    for scheme in ("light", "dark"):
        palette = _object(colors.get(scheme), f"colors.{scheme}")
        missing = sorted(set(COLOR_ROLES) - set(palette))
        extra = sorted(set(map(str, palette)) - set(COLOR_ROLES))
        if missing:
            raise ValueError(f"colors.{scheme} missing role(s) {missing}")
        if extra:
            raise ValueError(f"unknown colors.{scheme} role(s) {extra} - valid: {list(COLOR_ROLES)}")
        for role, value in palette.items():
            _hex(value, f"colors.{scheme}.{role}")


def _validate_typography(typography: Any) -> None:
    _object(typography, "typography")
    _keys(typography, "typography", ("fonts", "type_scale"))
    fonts = _object(typography.get("fonts"), "typography.fonts")
    extra = sorted(set(map(str, fonts)) - set(FONT_ROLES))
    if extra:
        raise ValueError(f"unknown typography font role(s) {extra} - valid: {list(FONT_ROLES)}")
    for role in FONT_ROLES:
        spec = _object(fonts.get(role), f"typography.fonts.{role}")
        _keys(spec, f"typography.fonts.{role}", ("family", "stack", "asset_ids", "fallback"))
        if not str(spec.get("family", "")).strip():
            raise ValueError(f"typography.fonts.{role}.family must be non-empty")
        stack = spec.get("stack")
        if not isinstance(stack, list) or not stack:
            raise ValueError(f"typography.fonts.{role}.stack must be a non-empty list")
        for item in stack:
            _css_token(str(item), f"typography.fonts.{role}.stack")
    scale = _object(typography.get("type_scale"), "typography.type_scale")
    extra_scale = sorted(set(map(str, scale)) - set(_TYPE_TO_CSS))
    if extra_scale:
        raise ValueError(f"unknown typography.type_scale role(s) {extra_scale}")
    for role in _TYPE_TO_CSS:
        _length(scale.get(role), f"typography.type_scale.{role}")


def _validate_layout(layout: Any) -> None:
    _object(layout, "layout")
    _keys(layout, "layout", ("radius", "spacing", "gaps", "density", "reading", "motion", "elevation"))
    for group in ("radius", "spacing", "gaps", "density", "reading"):
        values = _object(layout.get(group), f"layout.{group}")
        for role, value in values.items():
            if role not in _LAYOUT_TO_CSS:
                raise ValueError(f"unknown layout.{group} role {role!r}")
            _length(value, f"layout.{group}.{role}")
    motion = _object(layout.get("motion"), "layout.motion")
    _keys(motion, "layout.motion", ("ease",))
    _css_token(str(motion.get("ease", "")), "layout.motion.ease")
    elevation = _object(layout.get("elevation"), "layout.elevation")
    _keys(elevation, "layout.elevation", ("light", "dark"))
    for scheme in ("light", "dark"):
        shadows = _object(elevation.get(scheme), f"layout.elevation.{scheme}")
        _keys(shadows, f"layout.elevation.{scheme}", ("shadow_sm", "shadow_lg"))
        for key, value in shadows.items():
            _css_token(str(value), f"layout.elevation.{scheme}.{key}")


def _validate_imagery(imagery: Any) -> None:
    _object(imagery, "imagery")
    _keys(imagery, "imagery", ("sets", "roles"))
    sets = _object(imagery.get("sets"), "imagery.sets")
    for name, spec in sets.items():
        _css_token(str(name), "imagery.sets key")
        spec = _object(spec, f"imagery.sets.{name}")
        _keys(spec, f"imagery.sets.{name}", ("label", "light_asset", "dark_asset", "deck_asset",
                                             "width", "height", "description"))
        for field in ("light_asset", "dark_asset", "deck_asset"):
            if field in spec:
                _asset_id_or_builtin(spec[field], f"imagery.sets.{name}.{field}")
    roles = _object(imagery.get("roles"), "imagery.roles")
    _keys(roles, "imagery.roles", IMAGERY_ROLES)
    for role in IMAGERY_ROLES:
        if roles.get(role) not in sets:
            raise ValueError(f"imagery.roles.{role} references missing set {roles.get(role)!r}")


def _validate_charts(charts: Any) -> None:
    _object(charts, "charts")
    _keys(charts, "charts", ("series", "status", "grid", "label_font_role"))
    series = charts.get("series")
    if not isinstance(series, list) or len(series) < 3:
        raise ValueError("charts.series must contain at least three colors")
    for idx, color in enumerate(series):
        _hex(color, f"charts.series[{idx}]")
    status = _object(charts.get("status"), "charts.status")
    _keys(status, "charts.status", ("positive", "warning", "negative", "skeptical", "neutral"))
    for key, color in status.items():
        _hex(color, f"charts.status.{key}")
    _hex(charts.get("grid"), "charts.grid")
    if charts.get("label_font_role") not in FONT_ROLES:
        raise ValueError("charts.label_font_role must reference a typography font role")
def _validate_deck(deck: Any) -> None:
    _object(deck, "deck")
    _keys(deck, "deck", ("boundary", "master_asset_ref", "style_reference_asset_ref", "logo_preferred", "canvas_preferred", "font_role", "chart_series", "layout_kinds"))
    if deck.get("boundary") != "tokenized_master_deck":
        raise ValueError("deck.boundary must be 'tokenized_master_deck'")
    if deck.get("font_role") not in FONT_ROLES:
        raise ValueError("deck.font_role must reference a typography font role")
    for key in ("master_asset_ref", "style_reference_asset_ref"):
        if asset_ref := str(deck.get(key) or "").strip():
            _asset_path_or_data(asset_ref, f"deck.{key}")
    series = deck.get("chart_series")
    if not isinstance(series, list) or len(series) < 3:
        raise ValueError("deck.chart_series must contain at least three colors")
    for idx, color in enumerate(series):
        _hex(color, f"deck.chart_series[{idx}]")
    if not isinstance(deck.get("layout_kinds"), list) or "cover" not in deck["layout_kinds"]:
        raise ValueError("deck.layout_kinds must include at least 'cover'")


def _validate_exports(exports: Any) -> None:
    _object(exports, "exports")
    _keys(exports, "exports", ("html", "pdf", "pptx"))
    for group in ("html", "pdf", "pptx"):
        _object(exports.get(group), f"exports.{group}")


def _validate_asset_ref(spec: Any, path: str, *, allow_builtin: bool = False) -> None:
    obj = _object(spec, path)
    _keys(obj, path, ("kind", "ref", "src", "asset_ref", "text", "scheme", "width", "height", "metadata"))
    kind = str(obj.get("kind", "")).strip()
    if allow_builtin and kind in {"builtin", "text_lockup", "composite"}:
        return
    src = obj.get("src") or obj.get("asset_ref") or obj.get("ref")
    if not src and kind != "text_lockup":
        raise ValueError(f"{path} must carry src, ref or asset_ref")
    if src:
        _asset_path_or_data(str(src), path)


def _asset_id_or_builtin(value: Any, path: str) -> None:
    s = str(value or "").strip()
    if not s:
        raise ValueError(f"{path} must be non-empty")
    if s.startswith("builtin:"):
        if not re.match(r"^builtin:[a-zA-Z0-9_.-]+$", s):
            raise ValueError(f"{path} contains an unsafe builtin asset id")
        return
    _asset_path_or_data(s, path)


def _asset_path_or_data(value: str, path: str) -> str:
    if value.startswith("workspace-asset:"):
        if not re.match(r"^workspace-asset:[A-Za-z0-9_.:-]+@[A-Fa-f0-9]{8,64}$", value):
            raise ValueError(f"{path} contains an invalid workspace asset ref")
        return value
    if value.startswith("data:"):
        if not _DATA_IMAGE_RE.match(value):
            raise ValueError(f"{path} data URI must be base64 image/*")
        return value
    if value.startswith("//") or re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", value):
        raise ValueError(f"{path} must be a local asset or data:image URI")
    from .config import partition_dir
    data_root = partition_dir().resolve()
    fp = Path(value) if Path(value).is_absolute() else partition_dir() / value
    if not fp.resolve().is_relative_to(data_root):
        raise ValueError(f"{path} path escapes the data dir ({data_root}): {value!r}")
    return str(fp)


def _object(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be an object")
    return value


def _keys(obj: dict[str, Any], path: str, allowed: tuple[str, ...]) -> None:
    unknown = sorted(set(map(str, obj)) - set(allowed))
    if unknown:
        raise ValueError(f"unknown {path} key(s) {unknown} - valid: {list(allowed)}")


def _hex(value: Any, path: str) -> None:
    if not isinstance(value, str) or not _HEX_RE.match(value.strip()):
        raise ValueError(f"{path} must be a #rgb or #rrggbb color")


def _length(value: Any, path: str) -> None:
    if not isinstance(value, str) or not _LENGTH_RE.match(value.strip()):
        raise ValueError(f"{path} must be a CSS length token")


def _css_token(value: str, path: str) -> None:
    if not value or not _CSS_TOKEN_RE.match(value):
        raise ValueError(f"{path} contains an unsafe CSS token")


def _font_stack_css(stack: list[str]) -> str:
    def one(name: str) -> str:
        n = str(name).strip()
        _css_token(n, "font stack")
        if re.search(r"\s", n) and not (n.startswith('"') and n.endswith('"')):
            return '"' + n.replace('"', "") + '"'
        return n
    return ",".join(one(x) for x in stack)


def _decls(mapping: dict[str, str]) -> str:
    decls: list[str] = []
    for key, value in mapping.items():
        if not _VAR_RE.match(key) or not _VAL_RE.match(str(value)):
            raise ValueError(f"compiled CSS declaration is unsafe: {key!r}: {value!r}")
        decls.append(f"{key}:{value}")
    return ";".join(decls)
