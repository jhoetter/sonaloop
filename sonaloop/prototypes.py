"""Prototype artifacts (spec/methodology-engine-and-prototyping.md, Pillar B §6).

First-class generation of real, minimal, locally-runnable web apps from a host-authored
concept (the spa-min template renders a genuinely clickable SPA — real DOM, real refs — so a
persona-agent can drive it via Playwright), plus a registry and a local-only runner.
"""
from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from . import config
from .config import prototype_templates_dir, prototypes_dir, utc_now_iso
from .models import Prototype
from .storage import Store
class PrototypeError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


# Running-prototype process table (in-memory; the durable record is the DB row).
_PROCS: dict[str, dict[str, Any]] = {}

_CSS_VAR_RE = re.compile(r"^--[a-z0-9-]+$")
_SCRIPT_CLOSE_RE = re.compile(r"</", re.IGNORECASE)
_INJECTED_FONT_RE = re.compile(
    r'<style\s+id=["\']workspace-font-faces["\'][^>]*>.*?</style>',
    re.IGNORECASE | re.DOTALL,
)
_INJECTED_DESIGN_SCRIPT_RE = re.compile(
    r'<script\s+id=["\']sonaloop-design-system["\'][^>]*>.*?</script>',
    re.IGNORECASE | re.DOTALL,
)
_INJECTED_DESIGN_STYLE_RE = re.compile(
    r'<style\s+id=["\']sonaloop-prototype-design-system["\'][^>]*>.*?</style>',
    re.IGNORECASE | re.DOTALL,
)
_INJECTED_BODY_ATTR_RE = re.compile(
    r'\sdata-design-(?:system|preset|density|radius|surface|version)="[^"]*"',
    re.IGNORECASE,
)
_INJECTED_BRAND_RE = re.compile(
    r'<div\s+class=["\']sl-prototype-brand["\'][^>]*>.*?</div>',
    re.IGNORECASE | re.DOTALL,
)

_PROTOTYPE_VAR_ALIASES = {
    "--bg": "--sl-bg",
    "--paper": "--sl-bg",
    "--panel": "--sl-surface",
    "--panel-2": "--sl-surface-2",
    "--ink": "--sl-ink",
    "--muted": "--sl-muted",
    "--line": "--sl-line",
    "--accent": "--sl-accent",
    "--accent-ink": "--sl-accent-ink",
    "--accent-weak": "--sl-accent-weak",
    "--r": "--sl-radius",
    "--sh": "--shadow-sm",
    "--ff": "--sl-sans",
    "--ok": "--sl-chart-status-positive",
    "--good": "--sl-chart-status-positive",
    "--warn": "--sl-chart-status-warning",
    "--bad": "--sl-chart-status-negative",
}

_PROTO_SEMANTIC_FALLBACKS = {
    "--proto-bg": ("--sl-bg", "--bg", "#f7f7f5"),
    "--proto-surface": ("--sl-surface", "--panel", "#ffffff"),
    "--proto-surface-2": ("--sl-surface-2", "--panel-2", "--paper-2", "#f1efe8"),
    "--proto-sidebar": ("--sl-sidebar", "--sidebar", "--sl-surface", "#f6f4ef"),
    "--proto-overlay": ("--sl-overlay", "--overlay", "--sl-surface", "#ffffff"),
    "--proto-ink": ("--sl-ink", "--ink", "#1a1815"),
    "--proto-ink-2": ("--ink-2", "--sl-muted", "--muted", "#635e56"),
    "--proto-muted": ("--sl-muted", "--muted", "#635e56"),
    "--proto-faint": ("--sl-faint", "--faint", "--sl-muted", "#8c857a"),
    "--proto-line": ("--sl-line", "--line", "#e9e5db"),
    "--proto-line-2": ("--sl-line-2", "--line-2", "--sl-line", "#f0ede5"),
    "--proto-accent": ("--sl-accent", "--accent", "#5e6ad2"),
    "--proto-accent-ink": ("--sl-accent-ink", "--accent-ink", "#ffffff"),
    "--proto-accent-weak": ("--sl-accent-weak", "--accent-weak", "--sl-surface-2", "#ecebf8"),
    "--proto-hover": ("--sl-hover", "--hover", "--sl-surface-2", "#f4f1ea"),
    "--proto-selected": ("--sl-sel", "--sel", "--sl-accent-weak", "#ecebf8"),
    "--proto-positive": ("--sl-chart-status-positive", "--sl-green", "--green", "#3d9b6b"),
    "--proto-warning": ("--sl-chart-status-warning", "--sl-amber", "--amber", "#b87a25"),
    "--proto-negative": ("--sl-chart-status-negative", "--sl-red", "--red", "#cf4d5f"),
    "--proto-neutral": ("--sl-chart-status-neutral", "--sl-muted", "--muted", "#635e56"),
    "--proto-chart-1": ("--sl-chart-series-1", "--c1", "--sl-accent", "#5e6ad2"),
    "--proto-chart-2": ("--sl-chart-series-2", "--c2", "--sl-violet", "#7a5ed1"),
    "--proto-chart-3": ("--sl-chart-series-3", "--c3", "--sl-blue", "#3d7fc4"),
    "--proto-chart-4": ("--sl-chart-series-4", "--c4", "--sl-green", "#3d9b6b"),
    "--proto-chart-5": ("--sl-chart-series-5", "--c5", "--sl-amber", "#b87a25"),
    "--proto-font": ("--sl-sans", "--sans", "Sona,Geist,Inter,system-ui,sans-serif"),
    "--proto-font-display": ("--sl-display", "--sl-sans", "--sans", "Sona,Geist,Inter,system-ui,sans-serif"),
    "--proto-font-mono": ("--sl-mono", "--mono", "Sona Mono,ui-monospace,monospace"),
    "--proto-type-xs": ("--t-xs", "11px"),
    "--proto-type-sm": ("--t-sm", "12px"),
    "--proto-type-body": ("--t-body", "13px"),
    "--proto-type-md": ("--t-md", "15px"),
    "--proto-type-lg": ("--t-lg", "18px"),
    "--proto-type-xl": ("--t-xl", "24px"),
    "--proto-type-2xl": ("--t-2xl", "32px"),
    "--proto-radius-sm": ("--sl-radius-sm", "--radius-sm", "6px"),
    "--proto-radius": ("--sl-radius", "--radius", "8px"),
    "--proto-radius-lg": ("--sl-radius-lg", "--radius-lg", "--sl-radius", "12px"),
    "--proto-radius-full": ("--sl-radius-full", "--radius-full", "9999px"),
    "--proto-space-1": ("--sl-s-1", "--s-1", "4px"),
    "--proto-space-2": ("--sl-s-2", "--s-2", "8px"),
    "--proto-space-3": ("--sl-s-3", "--s-3", "12px"),
    "--proto-space-4": ("--sl-s-4", "--s-4", "16px"),
    "--proto-space-5": ("--sl-s-5", "--s-5", "20px"),
    "--proto-space-6": ("--sl-s-6", "--s-6", "24px"),
    "--proto-space-8": ("--sl-s-8", "--s-8", "32px"),
    "--proto-gap-tight": ("--sl-gap-tight", "--gap-tight", "4px"),
    "--proto-gap-item": ("--sl-gap-item", "--gap-item", "8px"),
    "--proto-gap-group": ("--sl-gap-group", "--gap-group", "12px"),
    "--proto-gap-section": ("--sl-gap-section", "--gap-section", "24px"),
    "--proto-row": ("--sl-row", "--row", "40px"),
    "--proto-row-dense": ("--sl-row-dense", "--row-dense", "32px"),
    "--proto-control-h": ("--sl-row-h", "--row-h", "--sl-row", "48px"),
    "--proto-control-sm": ("--sl-ctl-sm", "--ctl-sm", "28px"),
    "--proto-measure": ("--sl-measure-prose", "--measure-prose", "70ch"),
    "--proto-ease": ("--sl-ease", "--ease", "cubic-bezier(.4,0,.2,1)"),
    "--proto-shadow-sm": ("--shadow-sm", "0 1px 2px rgba(26,24,21,.05)"),
    "--proto-shadow-lg": ("--shadow-lg", "0 8px 28px rgba(26,24,21,.12),0 1px 2px rgba(26,24,21,.07)"),
}

_PROTO_COMPONENT_DEFAULTS = {
    "--proto-header-bg": "color-mix(in srgb,var(--proto-surface) 92%,transparent)",
    "--proto-card-bg": "var(--proto-surface)",
    "--proto-field-bg": "var(--proto-bg)",
    "--proto-chip-bg": "var(--proto-accent-weak)",
    "--proto-focus": "0 0 0 3px color-mix(in srgb,var(--proto-accent) 22%,transparent)",
    "--proto-active-soft": "color-mix(in srgb,var(--proto-accent) 14%,var(--proto-surface))",
    "--proto-status-good-bg": "color-mix(in srgb,var(--proto-positive) 12%,var(--proto-surface))",
    "--proto-status-warn-bg": "color-mix(in srgb,var(--proto-warning) 12%,var(--proto-surface))",
    "--proto-status-bad-bg": "color-mix(in srgb,var(--proto-negative) 12%,var(--proto-surface))",
    "--proto-card-pad": "var(--proto-space-5)",
    "--proto-panel-pad": "var(--proto-space-4)",
    "--proto-page-pad": "var(--proto-space-6)",
    "--proto-section-gap": "var(--proto-gap-section)",
    "--proto-control-x": "var(--proto-space-3)",
    "--proto-control-y": "var(--proto-space-2)",
    "--proto-card-radius": "var(--proto-radius-lg)",
    "--proto-control-radius": "var(--proto-radius)",
    "--proto-chip-radius": "var(--proto-radius-full)",
}


# --------------------------------------------------------------------------- scaffolding

def _safe_artifact_slug(slug: str) -> str:
    value = str(slug or "")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", value):
        raise PrototypeError("BAD_SLUG", f"unsafe prototype slug: {value!r}")
    return value

def _freeform_frames(concept: dict[str, Any]) -> list[dict[str, Any]]:
    frames = concept.get("frames") or concept.get("scenes")
    if isinstance(frames, list) and frames:
        return [f for f in frames if isinstance(f, dict)]
    if isinstance(concept.get("surface"), dict):
        surface = dict(concept["surface"])
        surface.setdefault("id", "surface")
        surface.setdefault("title", concept.get("title") or "Prototype")
        return [surface]
    screens = concept.get("screens")
    if isinstance(screens, list) and screens:
        return [s for s in screens if isinstance(s, dict)]
    return []


def _validate_freeform_concept(concept: dict[str, Any]) -> dict[str, Any]:
    frames = _freeform_frames(concept)
    if not frames:
        raise PrototypeError("BAD_CONCEPT", "freeform concept needs frames/scenes, surface, or screens")
    idset = {str(f.get("id", "")).strip() for f in frames if str(f.get("id", "")).strip()}
    if len(idset) != len(frames):
        raise PrototypeError("BAD_CONCEPT", "each freeform frame needs a unique id")

    def _walk(obj: Any, where: str) -> None:
        if isinstance(obj, dict):
            tgt = str(obj.get("goto") or "").strip()
            if tgt and tgt not in idset:
                raise PrototypeError("BAD_CONCEPT", f"{where} navigates to '{tgt}', which is not a frame id "
                                                    f"(dead interaction); valid frames: {sorted(idset)}")
            for key, value in obj.items():
                if key in {"formula", "when", "html", "css", "js"}:
                    continue
                _walk(value, where)
        elif isinstance(obj, list):
            for value in obj:
                _walk(value, where)

    for frame in frames:
        _walk(frame, f"frame '{frame.get('id', '')}'")
    if concept.get("start") and concept["start"] not in idset:
        raise PrototypeError("BAD_CONCEPT", "start must be a frame id")
    return concept


def _validate_concept(concept: dict[str, Any], template: str | None = None) -> dict[str, Any]:
    if not isinstance(concept, dict) or not str(concept.get("title", "")).strip():
        raise PrototypeError("BAD_CONCEPT", "concept needs a non-empty title")
    freeform = template == "spa-freeform" or any(isinstance(concept.get(k), list) for k in ("frames", "scenes")) \
        or isinstance(concept.get("surface"), dict)
    if freeform:
        return _validate_freeform_concept(concept)
    screens = concept.get("screens")
    if not isinstance(screens, list) or not screens:
        raise PrototypeError("BAD_CONCEPT", "concept needs >= 1 screen")
    idset = {s["id"] for s in screens if isinstance(s, dict) and str(s.get("id", "")).strip()}

    def _norm_nav(obj: dict[str, Any], where: str) -> None:
        """Accept a STRING `goto` OR `action` as the screen-navigation key (templates differ),
        normalize both so any renderer navigates, and REJECT a target that resolves to no screen — so
        a prototype can't scaffold (then get proband-tested) with a silently dead interaction (GAP-4).
        A non-string `action`/`goto` (a nested action object) is the template's concern — left as-is."""
        goto, action = obj.get("goto"), obj.get("action")
        tgt = goto.strip() if isinstance(goto, str) else (action.strip() if isinstance(action, str) else "")
        if not tgt:
            return
        if tgt not in idset:
            raise PrototypeError("BAD_CONCEPT", f"{where} navigates to '{tgt}', which is not a screen id "
                                                f"(dead interaction); valid screens: {sorted(idset)}")
        obj["goto"] = tgt
        if not isinstance(action, (dict, list)):   # don't clobber a nested action object
            obj["action"] = tgt

    for s in screens:
        if not isinstance(s, dict) or not str(s.get("id", "")).strip():
            raise PrototypeError("BAD_CONCEPT", "each screen needs an id")
        for el in s.get("elements", []) or []:
            if not isinstance(el, dict) or not str(el.get("id", "")).strip():
                raise PrototypeError("BAD_CONCEPT", "each element needs an id")
            if el.get("kind") not in _ELEMENT_KINDS:
                raise PrototypeError("BAD_CONCEPT", f"bad element kind: {el.get('kind')}")
            if el["kind"] == "verdict" and not (isinstance(el.get("cases"), list) and el["cases"]):
                raise PrototypeError("BAD_CONCEPT", f"verdict element '{el['id']}' needs a non-empty `cases` list "
                                                    "[{when:<expr>, text}] (the data-driven conditional display)")
            if el["kind"] in ("chart", "timeline") and not (el.get("x") or el.get("points") or el.get("series")):
                raise PrototypeError("BAD_CONCEPT", f"{el['kind']} element '{el['id']}' needs `x`{{from,to,step}} + "
                                                    "`series`[{formula}] (or `points`)")
            _norm_nav(el, f"screen '{s['id']}' element '{el['id']}'")
        # screen-level card-like blocks (cards / options) also navigate — validate them too (the old
        # validator ignored these, which is how a dead `action`-only card slipped through).
        for blk in ("cards", "options"):
            for card in s.get(blk, []) or []:
                if isinstance(card, dict):
                    _norm_nav(card, f"screen '{s['id']}' {blk} '{card.get('id', card.get('title',''))}'")
    if concept.get("start") and concept["start"] not in idset:
        raise PrototypeError("BAD_CONCEPT", "start must be a screen id")
    return concept


# Element kinds the SPA renderers understand. Extended for the interactive/computational rung
# (range/number/computed/bar — GAP-1) and the experience layer (chart/verdict/timeline — ESV5,
# rendered by spa-journey) so a prototype can be a real, production-credible experience.
_ELEMENT_KINDS = {"button", "input", "select", "text", "link", "range", "number", "computed", "bar",
                  "chart", "verdict", "timeline"}


def _prototype_design_context() -> dict[str, Any]:
    from .theming import active_runtime_design_system_context, runtime_design_system_context
    return active_runtime_design_system_context() or runtime_design_system_context(surface="prototype")


def _css_decls(mapping: dict[str, Any]) -> str:
    return ";".join(
        f"{key}:{value}"
        for key, value in mapping.items()
        if _CSS_VAR_RE.match(str(key))
    )


def _first_var(vars_: dict[str, Any], keys: tuple[str, ...]) -> str:
    fallback = ""
    for key in keys:
        raw = str(key)
        if raw.startswith("--"):
            value = str(vars_.get(raw, "")).strip()
            if value:
                return value
        elif not fallback:
            fallback = raw
    return fallback


def _aliased_vars(vars_: dict[str, Any]) -> dict[str, Any]:
    out = dict(vars_)
    for alias, keys in _PROTO_SEMANTIC_FALLBACKS.items():
        out[alias] = _first_var(out, keys)
    for alias, value in _PROTO_COMPONENT_DEFAULTS.items():
        out.setdefault(alias, value)
    for alias, source in _PROTOTYPE_VAR_ALIASES.items():
        if source in out:
            out[alias] = out[source]
    out.setdefault("--r", out["--proto-radius"])
    out.setdefault("--sh", out["--proto-shadow-sm"])
    out.setdefault("--ff", out["--proto-font"])
    out.setdefault("--good", out["--proto-positive"])
    out.setdefault("--ok", out["--proto-positive"])
    out.setdefault("--warn", out["--proto-warning"])
    out.setdefault("--bad", out["--proto-negative"])
    return out


def _json_script_payload(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return _SCRIPT_CLOSE_RE.sub("<\\/", raw)


def _brand_spec(ctx: dict[str, Any]) -> dict[str, str]:
    ds = ctx.get("design_system") or {}
    brand = ds.get("brand") if isinstance(ds, dict) else {}
    if not isinstance(brand, dict):
        return {}
    preferred = brand.get("logo_preferred") or "lockup"
    variants = brand.get("logo_variants") if isinstance(brand.get("logo_variants"), dict) else {}
    variant = variants.get(preferred) or variants.get("lockup") or variants.get("icon") or {}
    if not isinstance(variant, dict):
        variant = {}
    name = str(brand.get("short_name") or brand.get("name") or "").strip()
    text = str(variant.get("text") or name).strip()
    src = str(variant.get("src") or variant.get("asset_ref") or variant.get("ref") or "").strip()
    if src.startswith(("workspace-asset:", "builtin:")):
        src = ""
    return {"name": name, "text": text, "src": src, "role": str(preferred)}


def _px(value: Any) -> float | None:
    m = re.match(r"^([0-9]+(?:\.[0-9]+)?)px$", str(value or "").strip())
    return float(m.group(1)) if m else None


def _design_mode(ctx: dict[str, Any], group: str) -> str:
    ds = ctx.get("design_system") or {}
    layout = ds.get("layout") if isinstance(ds, dict) else {}
    if not isinstance(layout, dict):
        return "default"
    if group == "density":
        row = _px(((layout.get("density") or {}).get("row_h"))
                  or ((layout.get("density") or {}).get("row")))
        if row is None:
            return "default"
        if row <= 38:
            return "compact"
        if row >= 50:
            return "spacious"
        return "comfortable"
    if group == "radius":
        radius = _px(((layout.get("radius") or {}).get("radius")))
        if radius is None:
            return "default"
        if radius <= 4:
            return "sharp"
        if radius >= 18:
            return "round"
        return "soft"
    return "default"


def _slug_attr(value: Any) -> str:
    raw = str(value or "").strip().lower()
    return re.sub(r"[^a-z0-9_-]+", "-", raw).strip("-")[:80]


def _prototype_body_attrs(ctx: dict[str, Any]) -> str:
    ds = ctx.get("design_system") or {}
    meta = ds.get("meta") if isinstance(ds, dict) else {}
    if not isinstance(meta, dict):
        meta = {}
    preset = meta.get("preset") or meta.get("preset_name") or meta.get("source") or ""
    attrs = {
        "data-design-system": "workspace" if ctx.get("workspace_id") else "sonaloop",
        "data-design-preset": _slug_attr(preset),
        "data-design-density": _design_mode(ctx, "density"),
        "data-design-radius": _design_mode(ctx, "radius"),
        "data-design-surface": str(ctx.get("surface") or "prototype"),
    }
    if ctx.get("version_id"):
        attrs["data-design-version"] = str(ctx["version_id"])
    return " ".join(
        f'{key}="{_esc_attr(value)}"'
        for key, value in attrs.items()
        if str(value).strip()
    )


def _prototype_runtime_css() -> str:
    return (
        "body{background:var(--proto-bg);color:var(--proto-ink);"
        "font:var(--proto-type-body)/1.5 var(--proto-font);letter-spacing:0}"
        "body{--bg:var(--proto-bg);--paper:var(--proto-bg);"
        "--panel:var(--proto-surface);--panel-2:var(--proto-surface-2);"
        "--ink:var(--proto-ink);--muted:var(--proto-muted);--line:var(--proto-line);"
        "--accent:var(--proto-accent);--accent-ink:var(--proto-accent-ink);"
        "--accent-weak:var(--proto-accent-weak);--r:var(--proto-radius);"
        "--sh:var(--proto-shadow-sm);--ff:var(--proto-font);"
        "--good:var(--proto-positive);--ok:var(--proto-positive);"
        "--warn:var(--proto-warning);--bad:var(--proto-negative)}"
        "body[data-design-density=compact]{--proto-card-pad:var(--proto-space-4);"
        "--proto-page-pad:var(--proto-space-5);--proto-control-y:var(--proto-space-1)}"
        "body[data-design-density=spacious]{--proto-card-pad:var(--proto-space-6);"
        "--proto-page-pad:var(--proto-space-8);--proto-control-y:var(--proto-space-3)}"
        "body[data-design-radius=sharp]{--proto-chip-radius:var(--proto-radius-sm)}"
        "body[data-design-radius=round]{--proto-card-radius:var(--proto-radius-lg);"
        "--proto-control-radius:var(--proto-radius-full)}"
        "header{background:var(--proto-header-bg);border-color:var(--proto-line);"
        "padding:var(--proto-space-4) var(--proto-page-pad)}"
        "h1{font-family:var(--proto-font-display);font-size:var(--proto-type-xl);"
        "line-height:1.12;color:var(--proto-ink)}"
        "h2{font-family:var(--proto-font-display);font-size:var(--proto-type-lg);"
        "line-height:1.18;color:var(--proto-ink)}"
        ".sub,p,.meta,.metric-delta,.computed .clabel,.barhead,.state,.kind-label{color:var(--proto-muted)}"
        "nav,.rail{background:var(--proto-surface);border-color:var(--proto-line);"
        "gap:var(--proto-gap-item)}"
        "nav{padding:var(--proto-space-3) var(--proto-page-pad)}"
        "main,.wrap{padding:var(--proto-page-pad)}"
        ".screen,.step,.card,.tile,.col,.layer,.state,.computed,.barwrap,.chartwrap,.verdict,"
        ".pin,.ticket,.sl-prototype-panel{background:var(--proto-card-bg);border-color:var(--proto-line);"
        "border-radius:var(--proto-card-radius);box-shadow:var(--proto-shadow-sm)}"
        ".stage{background:var(--proto-surface);border-color:var(--proto-line);"
        "border-radius:var(--proto-card-radius);box-shadow:var(--proto-shadow-lg)}"
        ".panel,.panel-2,.col,.ticket,.computed,.barwrap,.chartwrap,.imagebox,.state{"
        "background:var(--proto-surface-2)}"
        ".card,.tile,.step,.layer,.computed,.barwrap,.chartwrap,.verdict{padding:var(--proto-card-pad)}"
        ".grid,.cols,.cards,.tiles,.board,.timeline,.rail,.nav,.rangerow,.chartlegend{"
        "gap:var(--proto-gap-group)}"
        "button,.btn,nav button,.dot,.pin,.actions button,input,select,textarea{"
        "font:inherit;border-color:var(--proto-line);border-radius:var(--proto-control-radius);"
        "min-height:var(--proto-control-sm)}"
        "input,select,textarea{background:var(--proto-field-bg);color:var(--proto-ink);"
        "padding:var(--proto-control-y) var(--proto-control-x)}"
        "input[type=range]{accent-color:var(--proto-accent)}"
        "button,.btn{padding:var(--proto-control-y) var(--proto-control-x)}"
        "button:focus-visible,.btn:focus-visible,input:focus-visible,select:focus-visible,"
        "textarea:focus-visible,a:focus-visible{outline:none;box-shadow:var(--proto-focus)}"
        "nav button.active,.dot.active .n,.dot.done .n,.btn,.el button,.kind-hotspot,.kind-button,"
        ".actions button.primary,.barfill,.meter span,.route,.avatar{"
        "background:var(--proto-accent);color:var(--proto-accent-ink);border-color:var(--proto-accent)}"
        ".dot.active,nav button.active{border-color:var(--proto-accent)}"
        ".dot.active,.dot.done,.card.clickable:hover,a,.el a{color:var(--proto-accent)}"
        ".dot .n,.kind-label,.card .tag,.col,.ticket{background:var(--proto-accent-weak)}"
        ".btn.secondary,.el button.secondary,.actions button:not(.primary){"
        "background:var(--proto-surface);color:var(--proto-ink);border-color:var(--proto-line)}"
        ".metric-value,.computed .cval,.barhead b,.rangeval{color:var(--proto-ink)}"
        ".kind-status.good,.verdict[data-tone=good]{border-color:var(--proto-positive);"
        "background:var(--proto-status-good-bg);color:var(--proto-positive)}"
        ".kind-status.warn,.verdict[data-tone=warn]{border-color:var(--proto-warning);"
        "background:var(--proto-status-warn-bg);color:var(--proto-warning)}"
        ".kind-status.bad,.verdict[data-tone=bad]{border-color:var(--proto-negative);"
        "background:var(--proto-status-bad-bg);color:var(--proto-negative)}"
        "#toast{background:var(--proto-ink);color:var(--proto-bg);"
        "border-radius:var(--proto-control-radius);box-shadow:var(--proto-shadow-lg)}"
        "code,kbd,pre,samp{font-family:var(--proto-font-mono)}"
    )


def _prototype_design_system_head(ctx: dict[str, Any]) -> str:
    by_scheme = ctx.get("css_vars_by_scheme") or {}
    light = _aliased_vars(by_scheme.get("light") or ctx.get("css_vars") or {})
    dark = _aliased_vars(by_scheme.get("dark") or light)
    brand = _brand_spec(ctx)
    payload = {
        "workspace_id": ctx.get("workspace_id") or "",
        "version_id": ctx.get("version_id") or "",
        "surface": ctx.get("surface") or "prototype",
        "spec_version": ctx.get("spec_version") or "",
        "compiled_hash": ctx.get("compiled_hash") or "",
        "brand": brand,
        "css_vars": {"light": light, "dark": dark},
        "design_system": ctx.get("design_system") or {},
    }
    light_decls = _css_decls(light)
    dark_decls = _css_decls(dark)
    font_css = str(ctx.get("font_face_css") or "")
    return (
        font_css
        + '<script id="sonaloop-design-system" type="application/json">'
        + _json_script_payload(payload)
        + "</script>"
        + '<style id="sonaloop-prototype-design-system">'
        + f":root{{{light_decls}}}"
        + f":root[data-theme=\"light\"]{{{light_decls}}}"
        + f":root[data-theme=\"dark\"]{{{dark_decls}}}"
        + f"@media (prefers-color-scheme: dark){{:root:not([data-theme]){{{dark_decls}}}}}"
        + _prototype_runtime_css()
        + ".sl-prototype-brand{display:flex;align-items:center;gap:8px;margin:0 0 8px;"
        + "color:var(--proto-muted);font:600 var(--proto-type-sm)/1.2 var(--proto-font)}"
        + ".sl-prototype-brand img{max-height:var(--proto-control-sm);max-width:180px;object-fit:contain}"
        + "</style>"
    )


def _prototype_brand_markup(ctx: dict[str, Any], concept: dict[str, Any]) -> str:
    if not bool(concept.get("show_brand") or concept.get("brand_header")):
        return ""
    brand = _brand_spec(ctx)
    src, text = brand.get("src", ""), brand.get("text", "")
    if src.startswith("data:image/"):
        img = f'<img alt="" src="{_esc(src)}">'
        return f'<div class="sl-prototype-brand" data-logo-role="{_esc(brand.get("role", ""))}">{img}</div>'
    if text:
        return f'<div class="sl-prototype-brand">{_esc(text)}</div>'
    return ""


def _strip_design_system(html: str) -> str:
    html = _INJECTED_FONT_RE.sub("", html)
    html = _INJECTED_DESIGN_SCRIPT_RE.sub("", html)
    html = _INJECTED_DESIGN_STYLE_RE.sub("", html)
    html = _INJECTED_BRAND_RE.sub("", html)

    def clean_body(match: re.Match[str]) -> str:
        attrs = _INJECTED_BODY_ATTR_RE.sub("", match.group(1))
        return "<body" + attrs + ">"

    return re.sub(r"<body\b([^>]*)>", clean_body, html, count=1, flags=re.IGNORECASE)


def _inject_design_system(html: str, concept: dict[str, Any], ctx: dict[str, Any]) -> str:
    html = _strip_design_system(html)
    head = _prototype_design_system_head(ctx)
    if "</head>" in html:
        html = html.replace("</head>", head + "</head>", 1)
    attrs = _prototype_body_attrs(ctx)
    if attrs:
        html = re.sub(r"<body\b", "<body " + attrs, html, count=1)
    brand = _prototype_brand_markup(ctx, concept)
    if brand and "<header>" in html:
        html = html.replace("<header>", "<header>" + brand, 1)
    return html


def _render_spa(name: str, concept: dict[str, Any], template: str) -> str:
    tdir = prototype_templates_dir() / template
    if not (tdir / "index.html").exists():
        raise PrototypeError("UNKNOWN_TEMPLATE", f"renderer template '{template}' not found")
    tpl = (tdir / "index.html").read_text(encoding="utf-8")
    html = (tpl
            .replace("__TITLE__", _esc(concept.get("title") or name))
            .replace("__SUMMARY__", _esc(concept.get("summary", "")))
            .replace("__CONCEPT_JSON__", json.dumps(concept, ensure_ascii=False)))
    return _inject_design_system(html, concept, _prototype_design_context())


def _esc(s: str) -> str:
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _esc_attr(s: Any) -> str:
    return _esc(str(s)).replace('"', "&quot;")


def scaffold_artifact(slug: str, name: str, concept: dict[str, Any], type: str = "prototype",
                      tags: list[str] | None = None, template: str | None = None,
                      project_id: str | None = None, store: Store | None = None) -> dict[str, Any]:
    """Scaffold a real, runnable artifact of any TYPE. The renderer template is resolved from DATA
    (the artifact-type registry in suggestions/artifact_types.json) — there is no code template map
    and no fidelity enum. `tags` carry discriminators (e.g. a fidelity tag)."""
    from . import presentation as _pres
    store = store or Store()
    slug = _safe_artifact_slug(slug)
    tags = list(tags or [])
    resolved = _pres.resolve_template(type, tags, explicit=template)
    if not resolved:
        raise PrototypeError("UNKNOWN_TEMPLATE",
                             f"no renderer template for artifact type '{type}' (tags={tags}); "
                             f"declare one in suggestions/artifact_types.json")
    concept = _validate_concept(concept, template=resolved)
    out_dir = prototypes_dir() / slug
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "index.html").write_text(_render_spa(name, concept, resolved), encoding="utf-8")
    (out_dir / "concept.json").write_text(json.dumps(concept, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        stored_path = str(out_dir.relative_to(config.ROOT))
    except ValueError:
        stored_path = str(out_dir)
    unit = "screens"
    count = len(concept.get("screens") or [])
    if not count:
        count = len(_freeform_frames(concept))
        unit = "frames"
    return register_artifact(slug, name, stored_path, entry="index.html", run="static", version="v0.1",
                             project_id=project_id, type=type, tags=tags,
                             notes=f"generated from {resolved} ({count} {unit})", store=store)


def _prototype_app_dir(p: dict[str, Any]) -> Path:
    raw = Path(p["path"])
    candidate = (raw if raw.is_absolute() else config.ROOT / raw).resolve()
    if config.postgres_row_tenancy_enabled():
        root = prototypes_dir().resolve()
        if not candidate.is_relative_to(root):
            raise PrototypeError(
                "BAD_PATH", "prototype path must stay inside the active workspace partition")
    return candidate


def _prototype_concept(app_dir: Path) -> dict[str, Any]:
    try:
        raw = json.loads((app_dir / "concept.json").read_text(encoding="utf-8"))
    except Exception:
        return {}
    return raw if isinstance(raw, dict) else {}


def refresh_prototype_design_system(prototype_id: str, store: Store | None = None) -> dict[str, Any]:
    """Atomically re-materialize static HTML with the current runtime design system."""
    store = store or Store()
    p = get_prototype(prototype_id, store=store)
    if p.get("run") != "static":
        return {"prototype": p, "refreshed": False, "reason": "non_static"}
    app_dir = _prototype_app_dir(p)
    entry = (app_dir / p.get("entry", "index.html")).resolve()
    try:
        entry.relative_to(app_dir)
    except ValueError:
        raise PrototypeError("BAD_ENTRY", f"prototype entry escapes app dir: {p.get('entry')}")
    if entry.suffix.lower() not in ("", ".html", ".htm"):
        return {"prototype": p, "refreshed": False, "reason": "non_html_entry"}
    if not entry.exists():
        raise PrototypeError("MISSING_FILES", f"prototype entry not found: {entry}")
    html = entry.read_text(encoding="utf-8")
    updated = _inject_design_system(html, _prototype_concept(app_dir), _prototype_design_context())
    if updated != html:
        # Concurrent preview/Playwright readers must never observe a partial document.
        fd, tmp_name = tempfile.mkstemp(prefix=f".{entry.name}.", suffix=".tmp", dir=app_dir)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as tmp:
                tmp.write(updated)
                tmp.flush()
                os.fsync(tmp.fileno())
            os.chmod(tmp_name, entry.stat().st_mode)
            os.replace(tmp_name, entry)
        finally:
            try: os.unlink(tmp_name)
            except FileNotFoundError: pass
    return {"prototype": p, "refreshed": updated != html, "path": str(entry)}


def register_artifact(slug: str, name: str, path: str, entry: str = "index.html", run: str = "static",
                      run_cmd: str | None = None, version: str = "v0.1", project_id: str | None = None,
                      notes: str = "", type: str = "prototype", tags: list[str] | None = None,
                      created_at: str | None = None, store: Store | None = None) -> dict[str, Any]:
    store = store or Store()
    slug = _safe_artifact_slug(slug)
    if config.postgres_row_tenancy_enabled() and (
            run != "static" or str(run_cmd or "").strip()):
        raise PrototypeError(
            "UNSAFE_RUNNER",
            "shared-Postgres workspaces may register static prototypes only (run_cmd must be empty)")
    from .services import stable_id
    now = created_at or utc_now_iso()
    tags = list(tags or [])
    existing = store.get_prototype(slug)
    pid = (existing or {}).get("id") or stable_id("prototype", slug, now)
    # compatibility `fidelity` = the first discriminator tag (kept so old readers/_artifact_tags still work)
    fidelity = next((t for t in tags if t), "") or (existing or {}).get("fidelity", "")
    rec = Prototype(id=pid, slug=slug, project_id=project_id, name=name, version=version,
                    kind="web", path=path, entry=entry, run=run, run_cmd=run_cmd, notes=notes,
                    created_at=(existing or {}).get("created_at", now),
                    fidelity=fidelity, type=type, tags=tags).to_dict()
    # Registration is an operator escape hatch locally.  In shared tenancy it
    # must not become a read/execute handle into another workspace or host path.
    _prototype_app_dir(rec)
    store.upsert_prototype(rec)
    return rec


# back-compat wrappers: a "prototype" is just an artifact whose type tag is "prototype";
# the compatibility `fidelity` argument becomes a discriminator tag.
def scaffold_prototype(slug: str, name: str, concept: dict[str, Any], kind: str = "web",
                       template: str | None = None, project_id: str | None = None,
                       fidelity: str | None = None, store: Store | None = None) -> dict[str, Any]:
    # Back-compat: historical callers pass kind="web". Newer agentic harnesses may pass a
    # DATA artifact type here (e.g. "canvas") to avoid forcing every prototype through the
    # classic screens/elements flow.
    artifact_type = "prototype" if kind in ("", "web", "prototype") else kind
    return scaffold_artifact(slug, name, concept, type=artifact_type,
                             tags=[fidelity] if fidelity else [], template=template,
                             project_id=project_id, store=store)


def register_prototype(slug: str, name: str, path: str, entry: str = "index.html", run: str = "static",
                       run_cmd: str | None = None, version: str = "v0.1", project_id: str | None = None,
                       notes: str = "", fidelity: str = "", created_at: str | None = None,
                       store: Store | None = None) -> dict[str, Any]:
    return register_artifact(slug, name, path, entry, run, run_cmd, version, project_id, notes,
                             type="prototype", tags=[fidelity] if fidelity else [], created_at=created_at, store=store)


def list_prototypes(project_id: str | None = None, store: Store | None = None) -> list[dict[str, Any]]:
    store = store or Store()
    out = store.list_prototypes(project_id)
    for p in out:
        p["running"] = p["id"] in _PROCS
        p["url"] = _PROCS.get(p["id"], {}).get("url") or p.get("url") or ""
    return out


def get_prototype(prototype_id: str, store: Store | None = None) -> dict[str, Any]:
    store = store or Store()
    p = store.get_prototype(prototype_id)
    if not p:
        raise PrototypeError("UNKNOWN_PROTOTYPE", f"No prototype '{prototype_id}'")
    p["running"] = p["id"] in _PROCS
    p["url"] = _PROCS.get(p["id"], {}).get("url") or p.get("url") or ""
    return p


def delete_prototype(prototype_id: str, store: Store | None = None) -> dict[str, Any]:
    store = store or Store()
    p = store.get_prototype(prototype_id)
    if p and p["id"] in _PROCS:
        stop_prototype(p["id"], store=store)
    return {"deleted": store.delete_prototype(prototype_id)}


# --------------------------------------------------------------------------- runner (local only)

def _free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def run_prototype(prototype_id: str, store: Store | None = None) -> dict[str, Any]:
    store = store or Store()
    p = get_prototype(prototype_id, store=store)
    if p.get("run") == "remote":
        if not p.get("url"):
            raise PrototypeError("MISSING_REMOTE_URL", "remote prototype has no URL")
        return {"prototype_id": p["id"], "url": p["url"], "pid": None,
                "running": False, "remote": True}
    # Redundant execution boundary for legacy/tampered rows that predate the
    # registration check. Workspace-authored strings must never reach a shell on
    # the shared Cloud host; local SQLite keeps the operator runner unchanged.
    if config.postgres_row_tenancy_enabled() and (
            p.get("run") != "static" or str(p.get("run_cmd") or "").strip()):
        raise PrototypeError(
            "UNSAFE_RUNNER",
            "shared-Postgres workspaces may run static prototypes only (run_cmd must be empty)")
    refresh_prototype_design_system(p["id"], store=store)
    if p["id"] in _PROCS:
        return {"prototype_id": p["id"], "url": _PROCS[p["id"]]["url"], "pid": _PROCS[p["id"]]["proc"].pid,
                "already_running": True}
    app_dir = _prototype_app_dir(p)
    if not app_dir.exists():
        raise PrototypeError("MISSING_FILES", f"prototype dir not found: {p['path']}")
    port = _free_port()
    if p["run"] == "static":
        cmd = [sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1",
               "--directory", str(app_dir)]
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        if not p.get("run_cmd"):
            raise PrototypeError("NO_RUN_CMD", f"run='{p['run']}' needs a run_cmd")
        env_cmd = p["run_cmd"].replace("{port}", str(port))
        proc = subprocess.Popen(env_cmd, shell=True, cwd=str(app_dir),
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{port}/{p['entry'] if p['run'] == 'static' else ''}".rstrip("/")
    if p["run"] == "static":
        url = f"http://127.0.0.1:{port}/{p['entry']}"
    _PROCS[p["id"]] = {"proc": proc, "url": url, "port": port}
    return {"prototype_id": p["id"], "url": url, "pid": proc.pid}


def stop_prototype(prototype_id: str, store: Store | None = None) -> dict[str, Any]:
    store = store or Store()
    p = store.get_prototype(prototype_id)
    key = (p or {}).get("id", prototype_id)
    entry = _PROCS.pop(key, None)
    if not entry:
        return {"stopped": False}
    try:
        entry["proc"].terminate()
        entry["proc"].wait(timeout=5)
    except Exception:
        try:
            entry["proc"].kill()
        except Exception:
            pass
    return {"stopped": True, "prototype_id": key}


def running_url(prototype_id: str) -> str | None:
    return _PROCS.get(prototype_id, {}).get("url")
