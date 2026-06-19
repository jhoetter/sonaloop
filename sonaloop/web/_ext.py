"""Extension seams for downstream private packages (sonaloop-cloud, sonaloop-research).

The public core stays FULLY runnable with zero extensions installed, and renders
bit-identically to before — every seam is additive and no-op when unused. Downstream
packages plug in WITHOUT the core ever importing them, via four seams:

  1. Routes  — entry_points(group="sonaloop.web.extensions"); each entry resolves to a
               callable invoked as `setup(app)` during create_app(), after core routes.
  2. Nav     — register_nav_section() / register_nav_item(); the sidebar iterates the
               registry. The core seeds its OWN defaults through the same API — there is
               no privileged path, so an extension's items sit beside the core's.
  3. Slots   — register_slot(name, fn); _layout() renders named insertion points
               ("head_extra", "sidebar_extra", "body_end"). fn(store) -> HTML string.
  4. Theme   — set_theme_overrides(mapping): a per-request contextvar for compiled CSS
               variables (mirrors the i18n _UI_LANG pattern). The canonical contract is
               sonaloop/theming.py's workspace_design_system.v2 validator/compiler:
               customer data is structured design-system data, then compiled into safe
               CSS variables, brand context, chart palettes and deck inputs. Pure SSR —
               no arbitrary CSS/JS or component replacement rides this seam.

Labels are `str | Callable[[], str]`: pass a literal, or a lambda that resolves the
label per request when it must (i18n) — e.g. one that returns t(<your-key>). Slot/route callables are trusted
code (they ship inside a private package), so their returned HTML is emitted as-is.
"""
from __future__ import annotations

import contextvars
from typing import Any, Callable

# CSS-injection guard, re-exported under its pre-existing import path: a key must be a
# custom property; a value a small, safe subset (colors / numeric tokens). No `;`, `{`,
# `}`, or `:` to break out of the declaration block. Canonical definitions live with the
# customer-theme contract (theming validates the SAME shapes loudly at persist time;
# this seam stays fail-soft at render time).
from ..theming import _VAL_RE, _VAR_RE  # noqa: F401

# ---------------------------------------------------------------------------
# Nav registry
# ---------------------------------------------------------------------------
# A nav section is a heading + an ordered group of items. label=None => no heading
# (the core's "workspace" group). Sections and items are sorted by `order`; ties keep
# insertion order (stable sort), so registration order is the tie-break.

_LabelLike = "str | Callable[[], str] | None"

_NAV_SECTIONS: list[dict[str, Any]] = []
_NAV_ITEMS: list[dict[str, Any]] = []


def register_nav_section(section_id: str, label: Any = None, order: int = 0) -> None:
    """Register (or update) a sidebar section. Idempotent by section_id."""
    for s in _NAV_SECTIONS:
        if s["id"] == section_id:
            s["label"], s["order"] = label, order
            return
    _NAV_SECTIONS.append({"id": section_id, "label": label, "order": order})


def register_nav_item(section: str, href: str, key: str, icon: str,
                      label: Any, order: int = 0) -> None:
    """Register (or replace) a sidebar link. Idempotent by href so a re-import or an
    extension overriding a core entry does not duplicate the row."""
    for it in _NAV_ITEMS:
        if it["href"] == href:
            it.update(section=section, key=key, icon=icon, label=label, order=order)
            return
    _NAV_ITEMS.append({"section": section, "href": href, "key": key,
                       "icon": icon, "label": label, "order": order})


def resolve_label(label: Any) -> str:
    return label() if callable(label) else (label or "")


def nav_model() -> list[tuple[dict[str, Any], list[dict[str, Any]]]]:
    """Ordered [(section, [items])] for the sidebar to render. Empty sections are
    dropped (a heading with no links would render as a dangling label)."""
    out: list[tuple[dict[str, Any], list[dict[str, Any]]]] = []
    for sec in sorted(_NAV_SECTIONS, key=lambda s: s["order"]):
        items = sorted((i for i in _NAV_ITEMS if i["section"] == sec["id"]),
                       key=lambda i: i["order"])
        if items:
            out.append((sec, items))
    return out


# ---------------------------------------------------------------------------
# Layout slots
# ---------------------------------------------------------------------------

_SLOTS: dict[str, list[Callable[[Any], str]]] = {}


def register_slot(name: str, fn: Callable[[Any], str]) -> None:
    """Register a render function for a named layout slot. Multiple registrations
    accumulate (rendered in registration order)."""
    _SLOTS.setdefault(name, []).append(fn)


def render_slot(name: str, store: Any) -> str:
    fns = _SLOTS.get(name)
    if not fns:
        return ""
    return "".join(fn(store) for fn in fns)


# ---------------------------------------------------------------------------
# Detail-page extras (entity-scoped insertion points)
# ---------------------------------------------------------------------------
# Slots above are global shell points (head/sidebar/body) that see only the store.
# A detail extra is scoped to ONE artifact kind and is handed that record, so an
# extension can render record-specific chrome inside the Properties aside — e.g.
# sonaloop-cloud's survey share link. No-op (returns "") when nothing is registered,
# so the public core renders the aside bit-identically to before.

_DETAIL_EXTRAS: dict[str, list[Callable[[Any, Any], str]]] = {}


def register_detail_extra(kind: str, fn: Callable[[Any, Any], str]) -> None:
    """Register a render function for a detail page's aside, scoped to one artifact
    `kind` ("survey", "council", …). fn(store, entity) -> HTML string; registrations
    accumulate (rendered in registration order). Idempotent by fn identity (like
    register_nav_item by href), so re-running an extension's setup() — e.g. a second
    create_app() in a test process — never double-renders the block."""
    fns = _DETAIL_EXTRAS.setdefault(kind, [])
    if fn not in fns:
        fns.append(fn)


def render_detail_extra(kind: str, store: Any, entity: Any) -> str:
    fns = _DETAIL_EXTRAS.get(kind)
    if not fns:
        return ""
    return "".join(fn(store, entity) for fn in fns)


# ---------------------------------------------------------------------------
# Authenticated identity (multi-user extensions)
# ---------------------------------------------------------------------------
# Core renders a per-user menu (sidebar foot) when an extension provides the
# authenticated principal of the current request; local single-user mode never
# sets one, so the plain Settings menu stays. Mirrors the theme-override seam:
# a contextvar the extension's auth middleware sets/resets around call_next.

_IDENTITY: contextvars.ContextVar[dict[str, Any] | None] = contextvars.ContextVar(
    "sonaloop_identity", default=None)


def set_identity(principal: dict[str, Any] | None) -> contextvars.Token:
    """Set the authenticated identity for this request — {sub, email, name} plus
    optional `logout_href` (rendered as the sign-out action when present) and an
    avatar URL (`picture`, `avatar_url`, `image`, `photo_url`, ...). Returns a token;
    pass it to reset_identity() in a finally block."""
    return _IDENTITY.set(dict(principal) if principal else None)


def reset_identity(token: contextvars.Token) -> None:
    _IDENTITY.reset(token)


def current_identity() -> dict[str, Any] | None:
    """The authenticated user of the current request, or None (local mode)."""
    return _IDENTITY.get()


# ---------------------------------------------------------------------------
# Per-request theme overrides (design-system-per-tenant/project)
# ---------------------------------------------------------------------------

_THEME_OVERRIDES: contextvars.ContextVar[dict[str, str] | None] = contextvars.ContextVar(
    "theme_overrides", default=None)

def set_theme_overrides(mapping: dict[str, str] | None) -> contextvars.Token:
    """Set per-request CSS custom-property overrides (e.g. {'--accent': '#0a7'}).
    Returns a token; pass it to reset_theme_overrides() in a finally block. Designed
    to be called from middleware once the active tenant/project is known."""
    return _THEME_OVERRIDES.set(dict(mapping) if mapping else None)


def reset_theme_overrides(token: contextvars.Token) -> None:
    _THEME_OVERRIDES.reset(token)


def theme_override_css() -> str:
    """A `<style>` block re-declaring the active overrides on :root, or "" when none.
    Emitted by _layout() AFTER the base stylesheet so it wins by cascade order."""
    ov = _THEME_OVERRIDES.get() or {}
    decls = [f"{k}:{v}" for k, v in ov.items()
             if _VAR_RE.match(str(k)) and _VAL_RE.match(str(v))]
    if not decls:
        return ""
    return '<style id="theme-overrides">:root{' + ";".join(decls) + "}</style>"


# ---------------------------------------------------------------------------
# Brand / product identity
# ---------------------------------------------------------------------------
# A per-process wordmark shown in the sidebar and (via title_brand()) the page <title>.
# Defaults to "Sonaloop" (the public core); an extension calls set_brand() in setup() to
# distinguish e.g. "Sonaloop Cloud" / "Sonaloop Research". Process-global, not per-request:
# each app runs in its own process, so this is set once at startup.

_BRAND = "Sonaloop"
_BRAND_LOGO: str | None = None


def set_brand(name: str, logo: str | None = None) -> None:
    """Override the product wordmark (page <title> suffix + sidebar). No-op on empty.
    `logo` (optional) replaces the sidebar lockup with a customer image — pass a value
    that passed theming.validate_customer_theme (a data: image URI or a DATA_DIR
    path); _layout() renders it where the wordmark renders today."""
    global _BRAND, _BRAND_LOGO
    if name and name.strip():
        _BRAND = name.strip()
    if logo and logo.strip():
        _BRAND_LOGO = logo.strip()


def brand_name() -> str:
    return _BRAND


def brand_logo() -> str | None:
    return _BRAND_LOGO


def title_brand() -> str:
    """The page-<title> form of the brand, for quick tab disambiguation across the
    sonaloop repos. Every surface leads with a short "Name | sonaloop": the core app
    is "App | sonaloop", and products map their wordmark — "Sonaloop Cloud" ->
    "Cloud | sonaloop", "Sonaloop Research" -> "Research | sonaloop". (The marketing
    website keeps bare "Sonaloop" branding, as the customer-facing face.) The visual
    sidebar wordmark still uses brand_name()."""
    bn = _BRAND.strip()
    if bn.lower() == "sonaloop":
        return "App | sonaloop"
    if bn.lower().startswith("sonaloop "):
        return f"{bn[len('sonaloop '):].strip()} | sonaloop"
    return bn


# ---------------------------------------------------------------------------
# Entry-point loader
# ---------------------------------------------------------------------------

def load_extensions(app: Any) -> list[str]:
    """Discover and run installed web extensions. Each entry in the
    `sonaloop.web.extensions` group resolves to a callable run as `setup(app)`.
    A broken extension is skipped (logged) rather than taking down the core —
    EXCEPT extensions named in SONALOOP_REQUIRED_EXTENSIONS (comma list): those
    are security-bearing (auth/tenancy middleware), and serving without them
    would fail OPEN. A required extension that fails (or is absent) raises, so
    the process dies loudly instead of running unprotected."""
    import os
    from importlib.metadata import entry_points

    required = {n.strip() for n in
                (os.getenv("SONALOOP_REQUIRED_EXTENSIONS") or "").split(",") if n.strip()}
    loaded: list[str] = []
    try:
        eps = entry_points(group="sonaloop.web.extensions")
    except TypeError:  # pragma: no cover - Python <3.10 selectable-API shim
        eps = entry_points().get("sonaloop.web.extensions", [])
    for ep in eps:
        try:
            ep.load()(app)
            loaded.append(ep.name)
        except Exception as exc:  # noqa: BLE001 - never let one OPTIONAL extension break boot
            if ep.name in required:
                raise RuntimeError(
                    f"required extension {ep.name!r} failed to load — refusing to "
                    f"serve without it (fail closed): {exc}") from exc
            import logging
            logging.getLogger("sonaloop.web").warning(
                "extension %r failed to load: %s", ep.name, exc)
    missing = required - set(loaded)
    if missing:
        raise RuntimeError(
            f"required extension(s) {sorted(missing)} not installed — refusing to "
            "serve without them (fail closed)")
    return loaded
