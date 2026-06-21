"""Prototype artifacts (spec/methodology-engine-and-prototyping.md, Pillar B §6).

First-class generation of real, minimal, locally-runnable web apps from a host-authored
concept (the spa-min template renders a genuinely clickable SPA — real DOM, real refs — so a
persona-agent can drive it via Playwright), plus a registry and a local-only runner.
"""
from __future__ import annotations

import json
import re
import socket
import subprocess
import sys
from pathlib import Path
from typing import Any

from .config import ROOT, prototype_templates_dir, prototypes_dir, utc_now_iso
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

_PROTOTYPE_VAR_ALIASES = {
    "--bg": "--sl-bg",
    "--paper": "--sl-bg",
    "--panel": "--sl-surface",
    "--ink": "--sl-ink",
    "--muted": "--sl-muted",
    "--line": "--sl-line",
    "--accent": "--sl-accent",
    "--accent-ink": "--sl-accent-ink",
    "--r": "--sl-radius",
    "--sh": "--shadow-sm",
    "--ff": "--sl-sans",
    "--ok": "--sl-chart-status-positive",
    "--good": "--sl-chart-status-positive",
    "--warn": "--sl-chart-status-warning",
    "--bad": "--sl-chart-status-negative",
}


# --------------------------------------------------------------------------- scaffolding

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


def _aliased_vars(vars_: dict[str, Any]) -> dict[str, Any]:
    out = dict(vars_)
    for alias, source in _PROTOTYPE_VAR_ALIASES.items():
        if source in vars_:
            out[alias] = vars_[source]
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
        + "body,body[data-fidelity],button,input,select,textarea{font-family:var(--sl-sans)}"
        + "code,kbd,pre,samp{font-family:var(--sl-mono)}"
        + ".sl-prototype-brand{display:flex;align-items:center;gap:8px;margin:0 0 8px;"
        + "color:var(--muted);font:600 var(--t-sm)/1.2 var(--sl-sans)}"
        + ".sl-prototype-brand img{max-height:24px;max-width:160px;object-fit:contain}"
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


def _inject_design_system(html: str, concept: dict[str, Any], ctx: dict[str, Any]) -> str:
    head = _prototype_design_system_head(ctx)
    if "</head>" in html:
        html = html.replace("</head>", head + "</head>", 1)
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


def scaffold_artifact(slug: str, name: str, concept: dict[str, Any], type: str = "prototype",
                      tags: list[str] | None = None, template: str | None = None,
                      project_id: str | None = None, store: Store | None = None) -> dict[str, Any]:
    """Scaffold a real, runnable artifact of any TYPE. The renderer template is resolved from DATA
    (the artifact-type registry in suggestions/artifact_types.json) — there is no code template map
    and no fidelity enum. `tags` carry discriminators (e.g. a fidelity tag)."""
    from . import presentation as _pres
    store = store or Store()
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
        stored_path = str(out_dir.relative_to(ROOT))
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


def register_artifact(slug: str, name: str, path: str, entry: str = "index.html", run: str = "static",
                      run_cmd: str | None = None, version: str = "v0.1", project_id: str | None = None,
                      notes: str = "", type: str = "prototype", tags: list[str] | None = None,
                      created_at: str | None = None, store: Store | None = None) -> dict[str, Any]:
    store = store or Store()
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
        p["url"] = _PROCS.get(p["id"], {}).get("url")
    return out


def get_prototype(prototype_id: str, store: Store | None = None) -> dict[str, Any]:
    store = store or Store()
    p = store.get_prototype(prototype_id)
    if not p:
        raise PrototypeError("UNKNOWN_PROTOTYPE", f"No prototype '{prototype_id}'")
    p["running"] = p["id"] in _PROCS
    p["url"] = _PROCS.get(p["id"], {}).get("url")
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
    if p["id"] in _PROCS:
        return {"prototype_id": p["id"], "url": _PROCS[p["id"]]["url"], "pid": _PROCS[p["id"]]["proc"].pid,
                "already_running": True}
    app_dir = (ROOT / p["path"]).resolve()
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
