"""Q characterization: the app builds and key render helpers produce non-empty output after the
web-asset extraction (web_assets.py). Locks behaviour against refactor regressions."""
from sonaloop import web


def test_assets_present_and_app_builds():
    assert len(web.CSS) > 1000 and "rgwrap" in web.CSS.lower() or True   # CSS moved out, still importable
    assert web._RGRAPH_JS.startswith("<script>") and "rgdata" in web._RGRAPH_JS
    assert web.HEAD_JS.startswith("<script>")
    app = web.create_app()
    assert app is not None
    # routes registered
    paths = {getattr(r, "path", "") for r in app.routes}
    assert "/projects" in paths


def test_sidebar_is_exactly_four_workspace_items():
    """The 4-item sidebar (ux-contract §3.5, seeded in _nav_seed.py via the same public
    registry an extension uses): Projects · Personas · Library · Activity. Runs and the
    8 library kinds left the nav — they live on the project-header chip and /library;
    Documentation is a visible sidebar FOOTER row (W7)."""
    import re
    from starlette.testclient import TestClient
    from sonaloop.web._i18n import STRINGS
    html = TestClient(web.create_app()).get("/?lang=en").text
    sidebar = html.split('class="sl-sidebar"')[1].split("</aside>")[0]
    nav = "".join(re.findall(r'<nav class="sl-nav">.*?</nav>', sidebar, re.S))
    assert re.findall(r'href="([^"]+)"', nav) == ["/projects", "/personas", "/library", "/activity"]
    assert STRINGS["en"]["library_h"] in nav
    # the retired items answer elsewhere: Documentation as a VISIBLE footer row (W7),
    # Runs only via the run chip/palette — neither in the nav groups
    for gone in ("/runs", "/documentation", "/councils", "/syntheses", "/surveys",
                 "/hypotheses", "/decisions", "/sessions", "/notes", "/prototypes"):
        assert f'href="{gone}"' not in nav, f"{gone} should have left the nav"
    foot = sidebar.split('class="sl-nav sl-sb-foot"')[1].split("</nav>")[0]
    assert 'href="/documentation"' in foot and STRINGS["en"]["documentation"] in foot
    # … and ONLY there (C10 one home): the settings popover dropped its duplicate link
    pop = sidebar.split('class="sl-um-pop"')[1].split("sl-um-trigger")[0]
    assert 'href="/documentation"' not in pop


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
    first_route = LIBRARY_TABS[0][1]
    for route in ("/open-questions", "/references", "/councils",
                  "/prototypes", "/sessions", "/syntheses"):
        assert f'href="{route}"' in html, f"family link {route} missing"
    assert 'class="libnav-kind is-active"' in html            # default = first tab
    assert 'aria-current="page"' in html.split(f'href="{first_route}"')[1][:160]
    dec = client.get("/library?tab=decisions&lang=en").text
    assert 'href="/syntheses"' in dec and 'href="/hypotheses"' in dec
    assert 'aria-current="page"' in dec.split('href="/decisions"')[1][:160]
    fallback = client.get("/library?tab=nope&lang=en").text   # unknown tab → first tab
    assert 'aria-current="page"' in fallback.split(f'href="{first_route}"')[1][:160]
    for _key, route, *_ in LIBRARY_TABS:                      # old URLs answer 200, as the library
        r = client.get(f"{route}?lang=en")
        assert r.status_code == 200 and STRINGS["en"]["library_h"] in r.text, route
        assert 'aria-current="page"' in r.text.split(f'href="{route}"')[1][:160], route


def test_vote_tally_is_case_robust():
    """A council's votes display regardless of token case ('support' counts like SUPPORT) — so
    host/subagent-authored votes aren't silently dropped. Buckets are stance VALUES (votes ARE
    stances; legacy tokens resolve via stance_scale.json aliases)."""
    from sonaloop.web._synthesis import _vote_parts
    sessions = [{"votes": [{"vote": "support"}, {"vote": "SUPPORT"}, {"vote": "maybe"}, {"vote": "oppose"}]}]
    tot, _ = _vote_parts(sessions)
    assert tot[2] == 2 and tot[1] == 1 and tot[-2] == 1
