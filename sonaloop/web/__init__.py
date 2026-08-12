from __future__ import annotations

import contextvars  # noqa: F401  (public surface preserved)
from datetime import date, timedelta  # noqa: F401  (public surface preserved)
from pathlib import Path

from ..config import DATA_DIR, load_env, postgres_row_tenancy_enabled, set_ui_language
from ..config import SUPPORTED_LANGUAGES, ui_language  # noqa: F401  (public surface preserved)
from ._i18n import (  # noqa: F401  (public surface preserved)
    STRINGS, _UI_LANG, _lang, t, _resolve_request_language,
)
from ._components import *  # noqa: F401,F403  (re-export render helpers / assets)
from ._components import (  # noqa: F401  (explicit names used by callers/tests)
    CSS, HEAD_JS,
    _esc, _icon, _avatar, _artifact_present, _proto_tags,
    _EDGE_COLORS, _theme_color,
)
from ._synthesis import *  # noqa: F401,F403  (re-export synthesis/voices/charts helpers)
from ._synthesis import (  # noqa: F401  (public surface preserved)
    _sentiment_section, _synthesis_html, _persona_voices_html,
)
from ._graph import _plan_html  # noqa: F401  (public surface preserved)
from .pages import (  # noqa: F401  (public surface preserved; routes split into web/pages/ — R2)
    register_pages, _projects_page, _calendar_tabs,
    _event_chip, _period_calendar_html, _memory_html,
)
from .pages import register_runs_section  # noqa: F401  (public /runs extension seam — see pages/runs.py)
from ._routes_api import register_api  # noqa: F401
from ._ext import (  # noqa: F401  (public extension surface for sonaloop-cloud / sonaloop-research)
    register_nav_section, register_nav_item, register_palette_item, register_slot,
    register_detail_extra, render_detail_extra,
    register_prototype_url_provider, prototype_file_url,
    set_theme_overrides, reset_theme_overrides, set_brand, load_extensions,
    set_runtime_brand, reset_runtime_brand,
    set_identity, reset_identity, current_identity,
)
from ._components import _layout as _layout  # noqa: F401  (wrapped publicly as render_page)


def render_page(title: str, body: str, store, *, crumbs=None, active: str = "",
                actions: str = "") -> str:
    """Render `body` inside the full core shell (sidebar, topbar, theme, command
    palette). The STABLE public entry point for downstream extension pages — use this
    instead of reaching into web._components. `body` is emitted as-is (extensions are
    trusted code); build it with the exported h()/raw()/fragment() helpers to get the
    same auto-escaping and component CSS as core pages."""
    return _layout(title, body, store, crumbs=crumbs, active=active, actions=actions)
from ._routes_lists import register_lists  # noqa: F401


def create_app():
    load_env()
    try:
        from fastapi import FastAPI, HTTPException, Query  # noqa: F401
        from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response  # noqa: F401
        from fastapi.staticfiles import StaticFiles
    except ImportError as exc:
        raise RuntimeError("Install web dependencies first: uv sync") from exc

    DATA_DIR.mkdir(parents=True, exist_ok=True)   # cold start: create the whole chain on first touch
    app = FastAPI(title="Sonaloop")
    tenant_runtime_files_blocked = postgres_row_tenancy_enabled()

    @app.middleware("http")
    async def _tenant_runtime_file_guard(request, call_next):
        """Never expose a process-global runtime path from the shared RLS deployment.

        Database RLS cannot authorize files. Until cloud has a workspace-aware blob/download
        route, fail closed for every runtime-file surface (404 avoids revealing existence).
        Keep this guard even though the mounts below are omitted in tenant mode: it also protects
        against a downstream extension accidentally registering one of these paths.
        """
        blocked_prefixes = ("/data", "/proto-files", "/sessions-files")
        path = request.url.path
        if tenant_runtime_files_blocked and any(
                path == prefix or path.startswith(prefix + "/") for prefix in blocked_prefixes):
            return Response(status_code=404, headers={"Cache-Control": "no-store"})
        return await call_next(request)

    if not tenant_runtime_files_blocked:
        # Absolute path (not cwd-relative "data"): downstream apps
        # call create_app() from their own working directory, so the mount must not depend on cwd.
        app.mount("/data", StaticFiles(directory=str(DATA_DIR)), name="data")
    # Bundled inspector assets (methodology covers, etc.) are served as files instead
    # of being embedded into SSR HTML. Project/user assets keep using /data and /assets.
    _web_assets = Path(__file__).resolve().parent / "assets"
    app.mount("/web-assets", StaticFiles(directory=str(_web_assets)), name="web-assets")
    if not tenant_runtime_files_blocked:
        # Local/single-tenant prototype apps can be viewed directly in the inspector.
        from ..config import prototypes_dir as _proto_dir
        _pd = _proto_dir()
        _pd.mkdir(parents=True, exist_ok=True)

        @app.get("/proto-files/{slug}", response_class=FileResponse, include_in_schema=False)
        def _prototype_entry_file(slug: str):
            return _prototype_static_file(slug, "index.html")

        @app.get("/proto-files/{slug}/{asset_path:path}", response_class=FileResponse,
                 include_in_schema=False)
        def _prototype_static_file(slug: str, asset_path: str):
            from .. import services
            from ..storage import Store
            root = _pd.resolve()
            target = (root / slug / (asset_path or "index.html")).resolve()
            try:
                target.relative_to(root)
            except ValueError:
                raise HTTPException(404, "prototype file not found") from None
            store = Store()
            try:
                p = services.get_prototype_artifact(slug, store=store)
            except Exception:
                p = None
            if p and (asset_path or "index.html") == p.get("entry", "index.html"):
                try:
                    services.refresh_prototype_design_system(p["id"], store=store)
                except Exception:
                    pass
            if target.is_dir():
                target = (target / "index.html").resolve()
                try:
                    target.relative_to(root)
                except ValueError:
                    raise HTTPException(404, "prototype file not found") from None
            if not target.exists() or not target.is_file():
                raise HTTPException(404, "prototype file not found")
            return FileResponse(str(target))

        app.mount("/proto-files", StaticFiles(directory=str(_pd), html=True), name="proto-files")

    from urllib.parse import urlencode

    from ._shell_version import SHELL_RESPONSE_STATE, ensure_no_store, shell_digest
    from ._slide import _REQ_PATH, _SLIDE, _SPA, _SSR_DRAWER, fetch_slide_fragment, valid_detail_path

    @app.middleware("http")
    async def _ui_language_middleware(request, call_next):
        """Resolve the UI language per request (?lang= -> cookie -> setting), expose
        it to the render helpers via the contextvar, and persist an explicit choice.
        The same hook resolves `?slide=1` (the slide-over fragment variant, §8.1) and
        `?d=<detail path>` (the context URL, §8.6 / UX U11): a valid local `d` gets its
        `?slide=1` fragment rendered in-process up front, so `_layout` can SSR the page
        with the slide-over already open — reload of a context URL reproduces the click
        view with no fetch flash. Invalid/unknown `d` -> the background renders alone."""
        from ..services import _research as _research_services
        from ..plan import begin_plan_cache, end_plan_cache
        from ._runs_widget import begin_run_states_cache, end_run_states_cache
        graph_cache_token = _research_services.begin_project_graph_cache()
        plan_cache_token = begin_plan_cache()
        run_states_token = begin_run_states_cache()
        lang, persist = _resolve_request_language(
            request.query_params.get("lang"), request.cookies.get("ui_lang"))
        token = _UI_LANG.set(lang)
        path_token = _REQ_PATH.set(request.url.path)   # the recents-beacon seam (UX V6)
        slide = request.query_params.get("slide") in ("1", "true")
        slide_token = _SLIDE.set(slide)
        requested_with = request.headers.get("x-requested-with", "").lower()
        spa = requested_with == "spa"
        protected_fragment = requested_with in {"spa", "drawer"}
        spa_token = _SPA.set(spa)
        server_release = shell_digest() if protected_fragment else ""
        request_shell = request.headers.get("x-sonaloop-shell", "")
        request_release = request_shell.partition(".")[0]
        shell_mismatch = protected_fragment and request_release != server_release
        shell_state: dict[str, str] = {}
        shell_state_token = SHELL_RESPONSE_STATE.set(shell_state)
        ssr_token = None
        d = request.query_params.get("d")
        if d and not shell_mismatch and not slide and request.method == "GET" and valid_detail_path(d):
            # Forms middleware is outermost and may have minted a CSRF token for this
            # first request before its Set-Cookie can reach the browser. Carry that exact
            # token into the in-process slide render; otherwise the nested middleware
            # mints a second token and freshly shared ?d= links contain invalid forms.
            from ._forms import CSRF_COOKIE, current_csrf_token
            fragment_cookie = request.headers.get("cookie", "")
            csrf_token = current_csrf_token()
            if csrf_token and request.cookies.get(CSRF_COOKIE) != csrf_token:
                fragment_cookie += ("; " if fragment_cookie else "") + f"{CSRF_COOKIE}={csrf_token}"
            frag_html = await fetch_slide_fragment(
                request.app, d, fragment_cookie)
            if frag_html is not None:
                # the no-JS scrim/close target: this URL with ?d= dropped (param order kept)
                rest = [(k, v) for k, v in request.query_params.multi_items() if k != "d"]
                close_href = request.url.path + (f"?{urlencode(rest)}" if rest else "")
                ssr_token = _SSR_DRAWER.set((d, frag_html, close_href))
        try:
            if shell_mismatch:
                # Reject clients from before the handshake shipped as well as stale
                # current clients. Both SPA and drawer clients already turn a non-2xx
                # fragment response into an honest full navigation, so no mismatched
                # markup reaches the DOM.
                response = Response(
                    "browser shell changed; reload required",
                    status_code=409,
                    media_type="text/plain",
                )
            else:
                response = await call_next(request)
        finally:
            _research_services.end_project_graph_cache(graph_cache_token)
            end_plan_cache(plan_cache_token)
            end_run_states_cache(run_states_token)
            _UI_LANG.reset(token)
            _REQ_PATH.reset(path_token)
            _SLIDE.reset(slide_token)
            _SPA.reset(spa_token)
            SHELL_RESPONSE_STATE.reset(shell_state_token)
            if ssr_token is not None:
                _SSR_DRAWER.reset(ssr_token)
        if persist:
            response.set_cookie("ui_lang", lang, max_age=60 * 60 * 24 * 365, samesite="lax")
            set_ui_language(lang)
        # Cache-Control for static assets (StaticFiles doesn't set it by default).
        # /web-assets/ are immutable bundled files; /data/ and /proto-files/ are
        # user/prototype assets that can change — short cache + revalidation.
        rpath = request.url.path
        if rpath.startswith("/web-assets/"):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        elif not tenant_runtime_files_blocked and (
                rpath.startswith("/data/") or rpath.startswith("/proto-files/")):
            response.headers["Cache-Control"] = "public, max-age=3600"
        is_html = response.headers.get("content-type", "").lower().startswith("text/html")
        if protected_fragment:
            # Never let a proxy replay a fragment across releases. The response token
            # also catches a transition between request routing and DOM parsing.
            response.headers["X-Sonaloop-Shell"] = shell_state.get("token", server_release)
        if protected_fragment or is_html:
            # A full reload must not resurrect an old document from browser/proxy storage;
            # keep any stricter existing directives and add the non-storage invariant.
            response.headers["Cache-Control"] = ensure_no_store(
                response.headers.get("Cache-Control", ""))
            # Full documents and fragments share URLs but never cache representations.
            # Preserve middleware/proxy additions (notably Accept-Encoding) while making
            # both request dimensions explicit and case-insensitively deduplicated.
            vary = [item.strip() for item in response.headers.get("Vary", "").split(",")
                    if item.strip()]
            seen = {item.lower() for item in vary}
            for item in ("X-Requested-With", "X-Sonaloop-Shell"):
                if item.lower() not in seen:
                    vary.append(item)
                    seen.add(item.lower())
            response.headers["Vary"] = ", ".join(vary)
        return response

    # Write-path support (web CRUD): the double-submit CSRF cookie middleware. The
    # form/validation helpers live in web/_forms.py; routes in web/pages/edit.py.
    from ._forms import install_forms
    install_forms(app)

    # Opt-in product tour (web/_tour.py): the chrome rides the public body_end slot
    # (registered on import); the quiet offer is in the sidebar footer.
    from . import _tour  # noqa: F401

    # Feedback button (web/_feedback.py): modal POST + thanks + the read-only
    # /feedback admin list; the trigger is in the sidebar footer, the modal rides body_end.
    from ._feedback import register_feedback
    register_feedback(app)

    register_pages(app)
    register_lists(app)
    register_api(app)
    # Discover installed web extensions (sonaloop-cloud / sonaloop-research). No-op when
    # none are installed, so the public core stays fully runnable on its own.
    load_extensions(app)
    # Gzip compression — outermost middleware so every response is compressed.
    # 77% transfer reduction on HTML pages (485 KB -> 111 KB measured).
    from starlette.middleware.gzip import GZipMiddleware
    app.add_middleware(GZipMiddleware, minimum_size=1024)
    return app


def main() -> None:
    import os
    import uvicorn

    host = os.getenv("PERSONA_COUNCIL_WEB_HOST", "127.0.0.1")
    try:
        port = int(os.getenv("PERSONA_COUNCIL_WEB_PORT", "8787"))
    except ValueError:
        port = 8787
    url = f"http://{host}:{port}"
    print(
        "\n" + "─" * 56 + "\n"
        "  Sonaloop inspector is ready.\n"
        f"  → Open {url} in your browser.\n"
        + "─" * 56 + "\n",
        flush=True,
    )
    uvicorn.run(create_app(), host=host, port=port)


if __name__ == "__main__":
    main()
