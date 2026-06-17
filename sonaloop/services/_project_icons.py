"""Project/job icons: existing icon selection + persisted custom SVGs.

The regular icon catalogue is vendored from sonaloop-design and must not be edited in
place. Custom project icons therefore live as runtime SVG files under the active data
partition and are referenced from the project JSON.
"""
from __future__ import annotations

import hashlib
import html
import random
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from .. import config
from .. import _icons
from ..config import partition_dir, utc_now_iso
from ..storage import Store
from ._common import _require_research_project, web_url


PROJECT_ICON_NAMES = (
    "projects", "folderOpen", "briefcase", "target", "compass", "pricingResearch",
    "positioning", "designThinkingHmw", "continuousDiscovery", "jtbd", "pressureTest",
    "analytics", "bulb", "messages", "prototype", "clipboard", "network", "wave",
    "rocket", "trend", "pieChart", "shield", "flag", "search", "sparkles",
)

_ALLOWED_TAGS = {"svg", "g", "path", "circle", "rect", "line", "polyline", "polygon", "ellipse", "title"}
_ALLOWED_ATTRS = {
    "class", "viewBox", "xmlns", "fill", "fill-opacity", "fill-rule", "stroke",
    "stroke-width", "stroke-opacity", "stroke-linecap", "stroke-linejoin", "d",
    "x", "y", "x1", "y1", "x2", "y2", "width", "height", "rx", "ry", "cx",
    "cy", "r", "points", "opacity", "aria-hidden", "role",
}
def available_project_icons() -> dict[str, Any]:
    """Icons suitable for Jobs/Projects, selected from the existing regular icon set."""
    names = [n for n in PROJECT_ICON_NAMES if n in _icons.names()]
    return {"icons": names, "default": "projects"}


def choose_project_icon(title: str = "", goal: str = "", *, seed: str = "") -> dict[str, Any]:
    """Pick one existing icon deterministically from title/goal/seed.

    This gives callers a stable "randomized" default without making tests or replayed
    imports non-deterministic.
    """
    names = available_project_icons()["icons"] or ["projects"]
    key = f"{title}\n{goal}\n{seed}".encode("utf-8")
    rng = random.Random(hashlib.sha256(key).hexdigest())
    return {"kind": "regular", "name": rng.choice(names)}


def normalize_project_icon(icon: Any, *, title: str = "", goal: str = "", seed: str = "") -> dict[str, Any]:
    """Normalize a caller-provided icon option.

    Accepts:
      - None / "" / "random" -> deterministic random regular icon
      - "projects" -> existing regular icon by name
      - {"kind": "regular", "name": "..."}
      - {"kind": "custom", "svg": "..."} -> sanitized custom icon payload
    """
    if icon is None or icon == "" or icon == "random":
        return choose_project_icon(title, goal, seed=seed)
    if isinstance(icon, str):
        if icon not in _icons.REGULAR:
            raise ValueError(f"unknown project icon '{icon}'")
        return {"kind": "regular", "name": icon}
    if isinstance(icon, dict):
        kind = icon.get("kind") or "regular"
        if kind == "regular":
            return normalize_project_icon(icon.get("name") or "random", title=title, goal=goal, seed=seed)
        if kind == "custom":
            svg = sanitize_project_svg(str(icon.get("svg") or ""))
            return {"kind": "custom", "svg": svg}
    raise ValueError("icon must be a regular icon name, 'random', or {kind:'custom', svg:'...'}")


def _icons_dir() -> Path:
    path = partition_dir() / "project-icons"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _icons_url_base() -> str:
    try:
        rel = _icons_dir().resolve().relative_to(Path(config.DATA_DIR).resolve())
        return "/data/" + rel.as_posix()
    except Exception:
        return "/data/project-icons"


def _strip_ns(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _clean_attr_value(value: str) -> str:
    value = (value or "").strip()
    if "javascript:" in value.lower() or "<" in value or ">" in value:
        raise ValueError("unsafe SVG attribute value")
    return value[:5000]


def _serialize(el: ET.Element) -> str:
    tag = _strip_ns(el.tag)
    if tag not in _ALLOWED_TAGS:
        raise ValueError(f"unsupported SVG tag <{tag}>")
    attrs: list[str] = []
    for raw_k, raw_v in el.attrib.items():
        k = _strip_ns(raw_k)
        if k.startswith("on") or k not in _ALLOWED_ATTRS:
            continue
        v = _clean_attr_value(str(raw_v))
        if k in {"width", "height"} and tag == "svg":
            continue
        attrs.append(f'{k}="{html.escape(v, quote=True)}"')
    if tag == "svg":
        if not any(a.startswith("viewBox=") for a in attrs):
            attrs.append('viewBox="0 0 24 24"')
        if not any(a.startswith("class=") for a in attrs):
            attrs.append('class="ic project-custom-icon"')
        attrs.append('aria-hidden="true"')
    text = html.escape((el.text or "").strip()) if tag == "title" else ""
    children = "".join(_serialize(c) for c in list(el))
    return f"<{tag}{(' ' + ' '.join(attrs)) if attrs else ''}>{text}{children}</{tag}>"


def sanitize_project_svg(svg: str) -> str:
    """Strictly sanitize a 24x24-ish inline SVG for safe inspector rendering."""
    svg = (svg or "").strip()
    if not svg:
        raise ValueError("custom project icon SVG is empty")
    if len(svg) > 20000:
        raise ValueError("custom project icon SVG is too large")
    try:
        root = ET.fromstring(svg)
    except ET.ParseError as exc:
        raise ValueError(f"custom project icon SVG is not valid XML: {exc}") from exc
    if _strip_ns(root.tag) != "svg":
        raise ValueError("custom project icon must be an <svg>")
    out = _serialize(root)
    if "<script" in out.lower():
        raise ValueError("custom project icon SVG may not contain script")
    return out


def _write_custom_icon(project_id: str, svg: str) -> dict[str, str]:
    digest = hashlib.sha256(svg.encode("utf-8")).hexdigest()[:16]
    filename = f"{project_id}-{digest}.svg"
    path = _icons_dir() / filename
    path.write_text(svg, encoding="utf-8")
    return {
        "svg_path": f"data/project-icons/{filename}",
        "url": web_url(f"{_icons_url_base()}/{filename}"),
    }


def _generated_svg(project: dict[str, Any], prompt: str = "") -> str:
    """Generate a small deterministic SVG from project text.

    The host may still author and pass a custom SVG directly. This fallback gives MCP
    clients a no-LLM way to create a fitting, persisted mark during initialization.
    """
    text = " ".join([project.get("title", ""), project.get("goal", ""), prompt]).lower()
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    shape = int(digest[0], 16) % 5
    paths = [
        '<path d="M5 18V6h14v12z"/><path d="M8 10h8M8 14h5"/>',
        '<circle cx="12" cy="12" r="7.5"/><path d="M12 7v5l3.5 2"/>',
        '<path d="M12 4l8 8-8 8-8-8z"/><path d="M8.5 12h7"/>',
        '<path d="M4 17l5-5 3 3 7-8"/><path d="M15 7h4v4"/>',
        '<circle cx="7" cy="12" r="2.3"/><circle cx="17" cy="7" r="2.3"/><circle cx="17" cy="17" r="2.3"/><path d="M9.2 11l5.6-3M9.2 13l5.6 3"/>',
    ][shape]
    if any(term in text for term in ("price", "pricing", "charge", "pay", "preis")):
        paths = '<path d="M12.8 4.5H6.5A1.5 1.5 0 0 0 5 6v6.2l6.2 6.2a1.7 1.7 0 0 0 2.4 0l4.8-4.8a1.7 1.7 0 0 0 0-2.4z"/><circle cx="8.7" cy="7.8" r="1.2"/><path d="M5 21h14"/>'
    elif any(term in text for term in ("position", "message", "brand", "markt")):
        paths = '<path d="M12 21s6-5.7 6-10.5A6 6 0 0 0 6 10.5C6 15.3 12 21 12 21z"/><circle cx="12" cy="10.5" r="2.2"/>'
    elif any(term in text for term in ("churn", "cancel", "retention", "künd")):
        paths = '<path d="M4 12a8 8 0 0 1 13.7-5.6"/><path d="M18 4v4h-4"/><path d="M20 12a8 8 0 0 1-13.7 5.6"/><path d="M6 20v-4h4"/>'
    return f'<svg class="ic project-custom-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round">{paths}</svg>'


def generate_project_icon(project_id: str, prompt: str = "", store: Store | None = None) -> dict[str, Any]:
    """Generate, save and assign a deterministic custom SVG icon for a project."""
    store = store or Store()
    project = _require_research_project(store, project_id)
    svg = sanitize_project_svg(_generated_svg(project, prompt))
    file_ref = _write_custom_icon(project["id"], svg)
    icon = {"kind": "custom", "svg": svg, **file_ref, "prompt": prompt, "generated_at": utc_now_iso()}
    project["icon"] = icon
    project["updated_at"] = utc_now_iso()
    store.upsert_research_project(project)
    return {"project_id": project["id"], "icon": icon}


def set_project_icon(project_id: str, icon: str | None = None, *,
                     svg: str | None = None, randomize: bool = False,
                     store: Store | None = None) -> dict[str, Any]:
    """Assign an existing regular icon, a random regular icon, or a custom SVG."""
    store = store or Store()
    project = _require_research_project(store, project_id)
    if svg is not None:
        clean = sanitize_project_svg(svg)
        file_ref = _write_custom_icon(project["id"], clean)
        spec = {"kind": "custom", "svg": clean, **file_ref, "updated_at": utc_now_iso()}
    else:
        spec = normalize_project_icon("random" if randomize else (icon or "projects"),
                                      title=project.get("title", ""), goal=project.get("goal", ""),
                                      seed=project["id"])
    project["icon"] = spec
    project["updated_at"] = utc_now_iso()
    store.upsert_research_project(project)
    return {"project_id": project["id"], "icon": spec}


def project_icon_svg(project_or_icon: dict[str, Any] | None, *, cls: str = "") -> str:
    """Render a stored project icon spec as inline SVG."""
    data = project_or_icon or {}
    spec = data.get("icon") if "icon" in data else data
    if not isinstance(spec, dict):
        spec = {"kind": "regular", "name": spec or "projects"}
    if spec.get("kind") == "custom":
        svg = spec.get("svg") or ""
        if not svg and spec.get("svg_path"):
            path = partition_dir() / "project-icons" / Path(str(spec["svg_path"])).name
            if path.exists():
                svg = path.read_text(encoding="utf-8")
        try:
            clean = sanitize_project_svg(svg)
        except ValueError:
            return _icons.icon("projects", cls=cls)
        return clean.replace('class="ic project-custom-icon"', f'class="ic project-custom-icon {cls}"' if cls else 'class="ic project-custom-icon"', 1)
    name = str(spec.get("name") or "projects")
    return _icons.icon(name if name in _icons.REGULAR else "projects", cls=cls)
