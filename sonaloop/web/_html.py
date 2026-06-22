"""Tiny auto-escaping element builder — the foundation of the component-based SSR layer.

spec/component-ssr-architecture.md (C1). Zero dependencies. HTML is a TREE, not a string:
text children/attrs are escaped by default; trusted HTML is opt-in via raw(). Components built with
h() never hand-escape again.

    h("a", {"class": "row", "href": url}, h("span", {"class": "t"}, title), badge)
    -> '<a class="row" href="...">...'    # title escaped, badge (a Safe) kept verbatim
"""
from __future__ import annotations

import html
import re
from typing import Any, Iterable

# void (self-closing) elements — no closing tag, no children
_VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input",
         "link", "meta", "param", "source", "track", "wbr"}


class Safe(str):
    """A string already safe to emit as HTML — h()/esc()/raw() return this, and h() will NOT
    re-escape a Safe child. Any plain str reaching a child/attr slot IS escaped."""
    __slots__ = ()


def esc(value: Any) -> Safe:
    """Escape arbitrary text to Safe HTML. Idempotent on Safe (never double-escapes)."""
    if isinstance(value, Safe):
        return value
    return Safe(html.escape("" if value is None else str(value)))


def raw(value: Any) -> Safe:
    """Mark already-HTML (markdown render, inline SVG icon, a compatibility f-string component) as trusted.
    Use only for HTML you control — the whole point of Safe is that everything else is escaped."""
    return Safe("" if value is None else str(value))


def _attrs(attrs: dict | None) -> str:
    if not attrs:
        return ""
    out = []
    for key, val in attrs.items():
        if val is None or val is False:
            continue                                  # skip absent attrs
        name = "class" if key == "class_" else key.replace("_", "-")
        if val is True:
            out.append(f" {name}")                     # bare boolean attr
        else:
            out.append(f' {name}="{html.escape(str(val), quote=True)}"')
    return "".join(out)


def _children(nodes: Iterable[Any]) -> str:
    parts: list[str] = []
    for node in nodes:
        if node is None or node is False:
            continue
        if isinstance(node, Safe):
            parts.append(node)
        elif isinstance(node, (list, tuple)) or (hasattr(node, "__iter__") and not isinstance(node, (str, bytes))):
            parts.append(_children(node))              # flatten iterables of children
        else:
            parts.append(esc(node))                    # plain str / number / etc → escaped
    return "".join(parts)


def h(tag: str, attrs: dict | None = None, *children: Any) -> Safe:
    """Build one element. attrs: dict (None/False skip; True = bare attr; class_ → class; _ → -).
    children: Safe (kept), str/number (escaped), iterable (flattened), None/False (skipped)."""
    open_tag = f"<{tag}{_attrs(attrs)}>"
    if tag in _VOID:
        return Safe(open_tag)
    return Safe(f"{open_tag}{_children(children)}</{tag}>")


def fragment(*children: Any) -> Safe:
    """A parent-less group of children (escaped/kept per the same rules) — no wrapping element."""
    return Safe(_children(children))


# ---- CSS co-location (spec C2): a component registers its own rules; _layout collects them ----
_CSS_FRAGMENTS: list[str] = []
_CSS_MINIFIED_CACHE: dict[str, str] = {}

_CSS_COMMENT_RE = re.compile(r'/\*.*?\*/', re.DOTALL)
_CSS_WS_RE = re.compile(r'\s+')
_CSS_COLLAPSE_RE = re.compile(r'\s*([{};:,>])\s*')
_CSS_SEMI_RE = re.compile(r';+\}')


def _minify_css(css: str) -> str:
    if css in _CSS_MINIFIED_CACHE:
        return _CSS_MINIFIED_CACHE[css]
    out = _CSS_COMMENT_RE.sub('', css)
    out = _CSS_COLLAPSE_RE.sub(r'\1', out)
    out = _CSS_WS_RE.sub(' ', out).strip()
    out = _CSS_SEMI_RE.sub('}', out)
    _CSS_MINIFIED_CACHE[css] = out
    return out


def register_css(css: str) -> str:
    """Register a component's CSS fragment (deduped, order-preserving). Call at module import; the
    layout emits collect_css() once. Lets a component own its styles instead of a global blob."""
    if css and css not in _CSS_FRAGMENTS:
        _CSS_FRAGMENTS.append(css)
    return css


def collect_css() -> str:
    return "".join(_minify_css(f) for f in _CSS_FRAGMENTS)
