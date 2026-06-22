"""Slide-over render modes (spec/ux-contract.md §8.1 + §8.6 — UX U6/U11, Notion-style peek v2).

Two per-request seams, both resolved by the middleware in `web/__init__.create_app` (the
`?lang=` contextvar pattern), so no route declares a parameter:

- `?slide=1` — any page answers with ONLY its content (no sidebar/topbar shell): the drawer
  fetches that fragment; the flag only switches what `_layout` wraps (and lets `detail_page`
  re-place the properties rail for the narrow panel). ONE source of truth: the same route +
  the same renderer serve both variants.
- `?d=<detail path>` — the CONTEXT URL (§8.6): the address a click pushes is the BACKGROUND
  page + the open panel as a param. On a direct load/reload the middleware sub-requests the
  detail's `?slide=1` fragment in-process and `_layout` renders the page with the slide-over
  ALREADY open (SSR — no fetch flash; reload reproduces the click view). `valid_detail_path`
  guards the param: only rooted local paths (no scheme/host/backslash — nothing an attacker
  could point off-origin), and an unknown path simply renders the background with no panel.
"""
from __future__ import annotations

import contextvars
from urllib.parse import parse_qs, quote

_SLIDE: contextvars.ContextVar[bool] = contextvars.ContextVar("slide_mode", default=False)

# SPA fragment mode: when the SPA router fetches a page with `X-Requested-With: spa`,
# the server returns only the #main content (no sidebar/topbar/CSS/JS shell). The
# client's `swap()` extracts `#main` via DOMParser — this skips ~465 KB of redundant
# shell transfer per navigation.
_SPA: contextvars.ContextVar[bool] = contextvars.ContextVar("spa_mode", default=False)

# The current request's URL path (set by the same middleware). The palette's recents
# beacon (web/_palette.visit_marker, UX V6) reads it to stamp WHICH detail is being
# rendered — correct in all three render modes (full page, ?slide=1 fragment, and the
# ?d= SSR sub-request, which runs through the middleware again with the detail path).
_REQ_PATH: contextvars.ContextVar[str] = contextvars.ContextVar("req_path", default="")


def request_path() -> str:
    """URL path of the request currently being rendered ("" outside a request)."""
    return _REQ_PATH.get()

# (detail_path, fragment_html, close_href) while SSR-rendering a `?d=` context URL — or None.
_SSR_DRAWER: contextvars.ContextVar[tuple[str, str, str] | None] = contextvars.ContextVar(
    "ssr_drawer", default=None)


def slide_mode() -> bool:
    """True while rendering the `?slide=1` fragment variant of the current request."""
    return _SLIDE.get()


def spa_mode() -> bool:
    """True while rendering the SPA fragment variant (X-Requested-With: spa)."""
    return _SPA.get()


def ssr_drawer() -> tuple[str, str, str] | None:
    """(detail path, slide fragment html, no-JS close href) while the current request is a
    `?d=` context URL whose detail resolved — `_layout` renders the drawer pre-open with it."""
    return _SSR_DRAWER.get()


def valid_detail_path(d: str) -> bool:
    """Accept ONLY local detail paths for `?d=` (§8.6 guard): rooted (`/…`), never
    scheme/host-shaped (`//host`, `http:…` can't start with `/`), no backslash or control
    characters (browser path-normalization tricks), and no nested `d`/`slide` params
    (no recursion, no fragment-of-a-fragment). Unknown-but-valid paths are fine — the
    sub-request 404s and the page renders without a panel."""
    if not d or not d.startswith("/") or d.startswith("//"):
        return False
    if "\\" in d or any(ord(c) < 32 for c in d):
        return False
    inner = parse_qs(d.partition("?")[2])
    return not ({"d", "slide"} & inner.keys())


async def fetch_slide_fragment(app, d: str, cookie: str = "") -> str | None:
    """Render `<d>?slide=1` through the SAME app in-process (a minimal ASGI sub-request —
    same routes, same renderer, the caller's cookies so language/theme match) and return the
    fragment html, or None unless it answered 200 with a real `.sl-slide` fragment."""
    path, _, query = d.partition("?")
    query = (query + "&" if query else "") + "slide=1"
    headers = [(b"accept", b"text/html")]
    if cookie:
        headers.append((b"cookie", cookie.encode("latin-1", "ignore")))
    scope = {
        "type": "http", "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1", "method": "GET", "scheme": "http",
        "path": path, "raw_path": quote(path).encode(), "query_string": query.encode(),
        "root_path": "", "headers": headers,
        "client": ("127.0.0.1", 0), "server": ("127.0.0.1", 0),
    }
    status, chunks = 0, []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        nonlocal status
        if message["type"] == "http.response.start":
            status = message["status"]
        elif message["type"] == "http.response.body":
            chunks.append(message.get("body", b""))

    try:
        await app(scope, receive, send)
    except Exception:                      # any route failure -> no panel, never a 500 (§8.6)
        return None
    if status != 200:
        return None
    html = b"".join(chunks).decode("utf-8", "replace")
    return html if html.startswith('<div class="sl-slide">') else None
