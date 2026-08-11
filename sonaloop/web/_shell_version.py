"""Release-safe version contract for the long-lived inspector browser shell.

The release component hashes the actual CSS/JS and static markup contract, independent of
package metadata or an optional build SHA. The context component binds that payload to
rendered chrome which survives fragment swaps (language, workspace favorites, branding,
navigation, command palette and theme/extension slots).
"""
from __future__ import annotations

import contextvars
import hashlib
import inspect
from functools import lru_cache


def _digest_parts(namespace: bytes, parts: tuple[str, ...]) -> str:
    digest = hashlib.sha256(namespace + b"\0")
    for part in parts:
        payload = part.encode("utf-8")
        digest.update(len(payload).to_bytes(8, "big"))
        digest.update(payload)
    return digest.hexdigest()


@lru_cache(maxsize=1)
def _shell_markup_contract_parts() -> tuple[str, ...]:
    """Source-address the route-independent markup retained across SPA swaps."""
    from . import _components as components
    from . import _nav_seed
    from ._ext import nav_model

    contracts = (
        components._layout,
        components._nav,
        components._sidebar_footer,
        components._user_menu,
        components.drawer_markup,
        components.palette_markup,
        components.live_markup,
        components.runs_widget_markup,
        components.keymap_markup,
        nav_model,
        _nav_seed,
    )
    return tuple(inspect.getsource(contract) for contract in contracts)


def shell_digest() -> str:
    """Content-address the deterministic CSS/JS shell shipped by this process."""
    # Lazy imports avoid a cycle: _components imports the token helpers, while every
    # asset below is fully initialized before a request can render a layout.
    from . import _components as components
    from ._html import collect_css

    return _digest_parts(b"sonaloop-web-shell-v1", (
        components.CSS,
        components.HEAD_JS,
        components.PALETTE_CSS,
        components.PALETTE_JS,
        components.LIVE_CSS,
        components.LIVE_JS,
        components.RUNS_WIDGET_CSS,
        components.RUNS_WIDGET_JS,
        components.KEYMAP_CSS,
        components.KEYMAP_JS,
        collect_css(),
        components.SHELL_JS,
        components.APP_JS,
        components.SPA_JS,
        components.DRAWER_JS,
        *_shell_markup_contract_parts(),
    ))


def ensure_no_store(cache_control: str) -> str:
    """Preserve existing cache directives while making storage unambiguously forbidden."""
    directives = [part.strip() for part in (cache_control or "").split(",") if part.strip()]
    if not any(part.lower() == "no-store" for part in directives):
        directives.append("no-store")
    return ", ".join(directives)


def make_shell_token(*, language: str, favorites_key: str | None,
                     brand: str, brand_logo_value: str, theme_css: str,
                     head_extra: str, body_end: str, sidebar_extra: str,
                     sidebar_footer: str, user_menu: str, nav_contract: str,
                     palette_contract: str, brand_logo_dark_value: str = "") -> str:
    """Return ``release.context`` for the exact persistent chrome rendered."""
    context_digest = _digest_parts(b"sonaloop-web-shell-context-v1", (
        language,
        favorites_key or "",
        brand,
        brand_logo_value,
        brand_logo_dark_value,
        theme_css,
        head_extra,
        body_end,
        sidebar_extra,
        sidebar_footer,
        user_menu,
        nav_contract,
        palette_contract,
    ))
    return f"{shell_digest()}.{context_digest}"


# A mutable holder survives Starlette's context copy into sync route worker threads. A
# renderer publishes into it; the outer middleware can stamp the response without parsing
# or buffering the body.
SHELL_RESPONSE_STATE: contextvars.ContextVar[dict[str, str] | None] = (
    contextvars.ContextVar("sonaloop_web_shell_response", default=None)
)


def publish_shell_token(token: str) -> None:
    state = SHELL_RESPONSE_STATE.get()
    if state is not None:
        state["token"] = token
