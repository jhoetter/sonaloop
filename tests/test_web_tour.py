"""Opt-in product tour (web/_tour.py): chrome presence, the quiet footer offer,
i18n'd copy, and THE CANARY — every artifact-tour selector must keep existing on
the page it claims to explain."""
from __future__ import annotations

import re

from starlette.testclient import TestClient

from sonaloop import services, web
from sonaloop.web._i18n import STRINGS, _UI_LANG
from sonaloop.web._tour import SHOWCASE_SLUG, tour_steps


def _client():
    return TestClient(web.create_app())


def test_tour_chrome_is_injected_on_every_page(store):
    client = _client()
    for path in ("/?lang=en", "/personas", "/documentation"):
        html = client.get(path).text
        assert 'id="tourov"' in html, f"tour overlay missing on {path}"
        assert 'id="tour-cfg"' in html, f"tour config missing on {path}"
        assert "data-tour-start" in html, f"no tour trigger on {path}"


def test_tour_offer_is_in_sidebar_footer_not_a_toast(store):
    """The floating offer toast retired; the quiet always-available offer is one row
    in the sidebar footer — and the tour still never auto-starts."""
    first = _client().get("/?lang=en")
    assert 'id="tour-offer"' not in first.text                   # the toast is gone …
    assert "tour-offer" not in first.headers.get("set-cookie", "")  # … and so is its cookie
    foot = first.text.split('class="sl-nav sl-sb-foot"')[1].split("sl-usermenu")[0]
    assert STRINGS["en"]["tour_take"] in foot and "data-tour-start" in foot
    assert 'href="/activity"' in foot and STRINGS["en"]["activity_h"] in foot
    # never auto-start: the overlay ships hidden; only [data-tour-start] opens it
    assert re.search(r'id="tourov"[^>]*hidden', first.text)


def test_tour_has_localized_artifact_steps():
    steps = tour_steps()
    assert len(steps) >= 10
    assert all("Gate:" not in s["title"] and "Gate:" not in s["body"] for s in steps)
    opened = [s for s in steps if s.get("open")]
    assert {s["sel"] for s in opened} == {
        '.olrow[data-rkind="council"]',
        '.olrow[data-rkind="session"]',
        '.olrow[data-rkind="synthesis"]',
        '.olrow[data-rkind="decision"]',
    }
    assert next(s for s in opened if 'council' in s["sel"])["focus"] == "#stimmen"
    urls = {s["url"] for s in steps}
    assert len(urls) == 1                              # no slow page-hop tour
    rkinds = set()
    for s in steps:
        if m := re.search(r'data-rkind="([^"]+)"', s["sel"]):
            rkinds.add(f'data-rkind="{m.group(1)}"')
    assert {f'data-rkind="{k}"' for k in ("open_question", "url_artifact", "council", "survey",
                                          "synthesis", "prototype", "session",
                                          "hypothesis", "decision", "note", "asset")} <= rkinds
    open_steps = [s for s in steps if s.get("open")]
    assert 1 <= len(open_steps) <= 4                    # only detail-rich stops open drawers
    assert len(open_steps) < len(steps) / 2             # keeps Back/Next local and fast
    for lang in ("de", "en"):
        token = _UI_LANG.set(lang)
        try:
            for s in tour_steps():
                assert s["title"].strip() and s["body"].strip()
                assert s["url"].strip() and s["sel"].strip()
                # localized through the catalog, not raw keys leaking into the UI
                assert not s["title"].startswith("tour_") and not s["body"].startswith("tour_")
        finally:
            _UI_LANG.reset(token)
    de = dict((s["sel"], s["title"]) for s in _steps_in("de"))
    en = dict((s["sel"], s["title"]) for s in _steps_in("en"))
    assert de.keys() == en.keys() and de != en                   # same steps, different copy


def _steps_in(lang: str):
    token = _UI_LANG.set(lang)
    try:
        return tour_steps()
    finally:
        _UI_LANG.reset(token)


def _selector_present(selector: str, html: str) -> bool:
    for part in selector.split(","):
        part = part.strip()
        if "data-rkind=" in part:
            m = re.search(r'data-rkind="([^"]+)"', part)
            assert m, f"unsupported selector shape: {selector}"
            if f'data-rkind="{m.group(1)}"' in html:
                return True
        elif part.startswith("."):
            cls = part[1:]
            assert re.fullmatch(r"[a-z0-9_-]+", cls), f"unsupported selector shape: {selector}"
            if cls in html:
                return True
        else:
            assert False, f"unsupported selector shape: {selector}"
    return False


def test_canary_every_step_selector_exists_on_its_destination_page(store):
    """THE CANARY: each tour step has a URL and selector that resolves after the
    onboarding showcase is loaded. Fails naming the dead step when a page or class
    changes — fix the step, don't let it rot."""
    services.load_example(SHOWCASE_SLUG, store=store)
    client = _client()
    dead = []
    for s in tour_steps():
        html = client.get(s["url"] + ("&lang=en" if "?" in s["url"] else "?lang=en")).text
        if not _selector_present(s["sel"], html):
            dead.append((s["url"], s["sel"]))
    assert not dead, f"tour steps point at pages/selectors that no longer render: {dead}"


def test_tour_config_knows_whether_showcase_is_loaded(store):
    client = _client()
    html = client.get("/?lang=en").text
    assert '"slug": "onboarding-showcase"' in html
    assert '"loaded": false' in html
    services.load_example(SHOWCASE_SLUG, store=store)
    html = client.get("/?lang=en").text
    assert '"loaded": true' in html


def test_take_the_tour_link_on_home_both_states(store):
    client = _client()
    # empty DB: prominent on the first-steps card, beside the example loader
    empty = client.get("/?lang=en").text
    assert STRINGS["en"]["first_steps_h"] in empty
    assert STRINGS["en"]["tour_take"] in empty and "data-tour-start" in empty
    # populated home (projects list): the persistent entry point is the user-menu row;
    # the old floating link under the list is gone.
    services.create_research_project("Tour link", goal="g", store=store)
    home = client.get("/?lang=en").text
    assert "tour-take-row" not in home
    assert STRINGS["en"]["tour_take"] in home and "data-tour-start" in home
