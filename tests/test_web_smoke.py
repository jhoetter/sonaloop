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


def test_sidebar_is_exactly_five_workspace_items():
    """The 5-item sidebar (ux-contract §3.5, seeded in _nav_seed.py via the same public
    registry an extension uses): Projects · Methodologies · Personas · Library · Activity. Runs and the
    8 library kinds left the nav — they live on the project-header chip and /library;
    Documentation is a visible sidebar FOOTER row (W7)."""
    import re
    from starlette.testclient import TestClient
    from sonaloop.web._i18n import STRINGS
    html = TestClient(web.create_app()).get("/?lang=en").text
    sidebar = html.split('class="sl-sidebar"')[1].split("</aside>")[0]
    nav = "".join(re.findall(r'<nav class="sl-nav">.*?</nav>', sidebar, re.S))
    assert re.findall(r'href="([^"]+)"', nav) == [
        "/projects", "/methodologies", "/personas", "/library", "/activity",
    ]
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
                  "/prototypes", "/notes", "/syntheses"):
        assert f'href="{route}"' in html, f"family link {route} missing"
    assert 'class="sl-libnav-kind sl-is-active"' in html      # default = first tab
    assert 'aria-current="page"' in html.split(f'href="{first_route}"')[1][:160]
    hyp = client.get("/hypotheses?lang=en").text
    assert "Frame" in hyp and 'href="/open-questions"' in hyp
    assert 'aria-current="page"' in hyp.split('href="/hypotheses"')[1][:160]
    sess = client.get("/sessions?lang=en").text
    assert "Test" in sess and 'href="/prototypes"' in sess and 'href="/sessions"' in sess
    assert 'aria-current="page"' in sess.split('href="/sessions"')[1][:160]
    ask = client.get("/library?family=ask&lang=en").text
    assert "Ask" in ask and 'href="/councils"' in ask and 'href="/surveys"' in ask
    assert 'aria-current="page"' in ask.split('href="/councils"')[1][:160]
    dec = client.get("/library?tab=decisions&lang=en").text
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
