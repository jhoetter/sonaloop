"""Q characterization: the app builds and key render helpers produce non-empty output after the
web-asset extraction (web_assets.py). Locks behaviour against refactor regressions."""
from sonaloop import web


def test_assets_present_and_app_builds():
    assert len(web.CSS) > 1000          # CSS extracted to web_assets.py, still importable
    assert web.HEAD_JS.startswith("<script>")
    app = web.create_app()
    assert app is not None
    # routes registered
    paths = {getattr(r, "path", "") for r in app.routes}
    assert "/projects" in paths


def test_spa_navigation_sets_url_before_running_page_scripts():
    """Hash-tab pages must see the destination hash during SPA swaps."""
    from sonaloop.web._drawer import SPA_JS

    assert SPA_JS.index("history.pushState({spa:1}, '', url);") < SPA_JS.index("runScripts(main);")


def test_sidebar_is_exactly_four_workspace_items():
    """The workspace sidebar (seeded in _nav_seed.py via the same public registry an
    extension uses): Jobs · Methodologies · Formats · Personas. Utilities live in
    the user menu."""
    import re
    from starlette.testclient import TestClient
    from sonaloop.web._i18n import STRINGS
    html = TestClient(web.create_app()).get("/?lang=en").text
    sidebar = html.split('class="sl-sidebar"')[1].split("</aside>")[0]
    nav = "".join(re.findall(r'<nav class="sl-nav">.*?</nav>', sidebar, re.S))
    assert re.findall(r'href="([^"]+)"', nav) == [
        "/projects", "/methodologies", "/library", "/personas",
    ]
    assert STRINGS["en"]["library_h"] in nav
    # the retired/utility items answer elsewhere: user menu/palette for utilities,
    # Runs only via the run chip/palette.
    for gone in ("/runs", "/documentation", "/councils", "/syntheses", "/surveys",
                 "/hypotheses", "/decisions", "/sessions", "/notes", "/prototypes",
                 "/activity"):
        assert f'href="{gone}"' not in nav, f"{gone} should have left the nav"
    assert 'class="sl-nav sl-sb-foot"' not in sidebar
    # Utility actions are grouped in one menu instead of duplicating footer rows.
    pop = sidebar.split('class="sl-um-pop"')[1].split("sl-um-trigger")[0]
    assert 'href="/activity"' in pop and STRINGS["en"]["activity_h"] in pop
    assert 'href="/documentation"' in pop and STRINGS["en"]["documentation"] in pop
    assert "data-fb-open" in pop and "data-tour-start" in pop and "data-km-open" in pop


def test_methodology_covers_are_static_assets_not_inline_payloads():
    from starlette.testclient import TestClient

    client = TestClient(web.create_app())
    r = client.get("/methodologies?lang=en")

    assert r.status_code == 200
    assert len(r.content) < 1_000_000
    assert "data:image/jpeg;base64" not in r.text
    assert "/web-assets/methodologies/" in r.text
    assert 'loading="lazy"' in r.text and 'decoding="async"' in r.text

    img = client.get("/web-assets/methodologies/double-diamond.jpg")
    assert img.status_code == 200
    assert img.headers["content-type"].startswith("image/jpeg")
    assert len(img.content) > 10_000


def test_methodologies_page_does_not_build_project_graphs_for_usage_counts(monkeypatch):
    from starlette.testclient import TestClient
    from sonaloop.web.pages import methodologies as meth_page

    def fail_full_project_list(*args, **kwargs):
        raise AssertionError("methodology usage counts must use lean project metadata")

    monkeypatch.setattr(meth_page.services, "list_research_projects", fail_full_project_list)
    r = TestClient(web.create_app()).get("/methodologies?lang=en")

    assert r.status_code == 200
    assert "/methodologies/double-diamond" in r.text


def test_user_menu_does_not_render_local_identity_placeholder():
    from sonaloop.web._components import _user_menu
    from sonaloop.web._ext import reset_identity, set_identity

    token = set_identity({"name": "Local User"})
    try:
        menu = _user_menu()
        assert "Local User" not in menu
        assert "sl-um-account" not in menu
    finally:
        reset_identity(token)

    token = set_identity({"name": "Jane Doe", "email": "jane@example.com",
                          "logout_href": "/logout", "plan": "Pro"})
    try:
        menu = _user_menu()
        assert "Jane Doe" in menu and "jane@example.com" in menu
        assert "Pro" in menu and 'href="/logout"' in menu
        assert "<img" not in menu and "JD" in menu
    finally:
        reset_identity(token)

    token = set_identity({"name": "Jane Doe", "email": "jane@example.com",
                          "picture": "https://lh3.googleusercontent.com/a/avatar"})
    try:
        menu = _user_menu()
        assert menu.count("<img") == 2
        assert 'src="https://lh3.googleusercontent.com/a/avatar"' in menu
        assert 'referrerpolicy="no-referrer"' in menu
        assert "sl-um-ava--initials" not in menu
    finally:
        reset_identity(token)

    token = set_identity({"name": "Jane Doe", "picture": "javascript:alert(1)"})
    try:
        menu = _user_menu()
        assert "<img" not in menu and "JD" in menu
    finally:
        reset_identity(token)


def test_user_menu_icons_are_animation_enabled():
    import re
    from starlette.testclient import TestClient

    html = TestClient(web.create_app()).get("/?lang=en").text
    sidebar = html.split('class="sl-sidebar"')[1].split("</aside>")[0]
    menu_html = sidebar.split('class="sl-um-pop"')[1].split('class="sl-um-trigger')[0]
    trigger_html = sidebar.split('class="sl-um-trigger')[1].split("</button>")[0]
    classes = re.findall(r'<svg class="([^"]+)"', menu_html + trigger_html)
    assert classes
    assert all("pi-animate" in cls for cls in classes), classes


def test_icon_animation_css_references_existing_keyframes():
    import re
    from sonaloop._icons import HIFI_ANIM_CSS

    referenced = set(re.findall(r"animation:\s*([A-Za-z_][\w-]*)", HIFI_ANIM_CSS))
    defined = set(re.findall(r"@keyframes\s+([A-Za-z_][\w-]*)", HIFI_ANIM_CSS))
    assert referenced
    assert referenced <= defined


def test_library_browser_tabs_and_old_routes(store):
    """The Library is ONE browser (ux-contract §3.5): /library groups primitives by
    family, scopes the second-level tabs to that family, and every old list route
    still answers 200 rendering the library with ITS tab active — no redirects."""
    from starlette.testclient import TestClient
    from sonaloop.web._i18n import STRINGS
    from sonaloop.web.pages.library import LIBRARY_TABS
    client = TestClient(web.create_app())
    html = client.get("/library?lang=en").text
    assert STRINGS["en"]["library_h"] in html
    assert STRINGS["en"]["library_lead"] in html
    first_route = LIBRARY_TABS[0][1]
    for route in ("/open-questions", "/references", "/councils",
                  "/sessions", "/notes", "/syntheses"):
        assert f'href="{route}"' in html, f"family link {route} missing"
    assert 'class="sl-taxo-pill sl-taxo-pill--primitive sl-is-active"' in html    # default = first tab
    assert 'aria-current="page"' in html.split(f'href="{first_route}"')[1][:160]
    hyp = client.get("/hypotheses?lang=en").text
    assert "Frame" in hyp and 'href="/open-questions"' in hyp
    assert 'aria-current="page"' in hyp.split('href="/hypotheses"')[1][:160]
    sess = client.get("/sessions?lang=en").text
    assert "Test" in sess and 'href="/sessions"' in sess
    assert 'aria-current="page"' in sess.split('href="/sessions"')[1][:160]
    ask = client.get("/library?family=ask&lang=en").text
    assert STRINGS["en"]["library_lead"] in ask
    assert STRINGS["en"]["councils_lead"] not in ask
    assert "Ask" in ask and 'href="/councils"' in ask and 'href="/surveys"' in ask
    assert 'aria-current="page"' in ask.split('href="/councils"')[1][:160]
    dec = client.get("/library?tab=decisions&lang=en").text
    assert STRINGS["en"]["library_lead"] in dec
    assert "Conclude" in dec and 'href="/syntheses"' in dec
    assert 'aria-current="page"' in dec.split('href="/decisions"')[1][:160]
    fallback = client.get("/library?tab=nope&lang=en").text   # unknown tab → first tab
    assert 'aria-current="page"' in fallback.split(f'href="{first_route}"')[1][:160]
    for _key, route, *_ in LIBRARY_TABS:                      # old URLs answer 200, as the library
        r = client.get(f"{route}?lang=en")
        assert r.status_code == 200 and STRINGS["en"]["library_h"] in r.text, route
        assert 'aria-current="page"' in r.text.split(f'href="{route}"')[1][:160], route


def test_library_ignores_orphan_project_trace_rows(store):
    """Rows from pre-cascade deletes may carry a missing project_id. The Library should
    remain browsable and simply omit project-local trace annotation."""
    from starlette.testclient import TestClient
    store.insert_council_session({
        "id": "c_orphan", "project_id": "rproject_missing",
        "created_at": "2026-06-16T00:00:00+00:00", "prompt": "Orphan council?",
        "persona_ids": [], "statements": [], "votes": [], "proposal": "",
        "summary": "", "exec_summary": "", "selection_reason": "",
    })
    r = TestClient(web.create_app()).get("/library?family=ask&lang=en")
    assert r.status_code == 200
    assert "Orphan council?" in r.text


def test_vote_tally_is_case_robust():
    """A council's votes display regardless of token case ('support' counts like SUPPORT) — so
    host/subagent-authored votes aren't silently dropped. Buckets are stance VALUES (votes ARE
    stances; legacy tokens resolve via stance_scale.json aliases)."""
    from sonaloop.web._synthesis import _vote_parts
    sessions = [{"votes": [{"vote": "support"}, {"vote": "SUPPORT"}, {"vote": "maybe"}, {"vote": "oppose"}]}]
    tot, _ = _vote_parts(sessions)
    assert tot[2] == 2 and tot[1] == 1 and tot[-2] == 1
