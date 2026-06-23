"""The persona-attribution contract (spec/ux-contract.md §10 W11) — ONE rule app-wide.

Wherever an artifact's DATA carries persona participation (council participants, report/synthesis
voices, survey persona-respondents, session subjects, prototype session drivers, a project's
cohort), the ROW and the DETAIL HEADER render the persona avatar-group — identical anatomy
everywhere (`.sl-avatar-group`, max 4 avatars, one `.sl-avatar-group__more` "+n" overflow chip,
via web/ui.avatar_group).

NEGATIVE rule, pinned here so it cannot drift: decision / hypothesis / note / asset records carry
NO direct persona participation (their persona link is indirect, via the evidence they cite) —
their rows and detail pages never render an avatar group.

This test seeds every kind WITH participation data, walks the same row builders the app uses
(library._tab_entries → ui.primitive_row) plus the live detail routes, and asserts:
participation present ⇒ avatar-group in the row html AND on the detail page; absent ⇒ none.
"""
from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from conftest import create_persona
from sonaloop import prototypes, services, web
from sonaloop.web import ui
from sonaloop.web.pages.library import _tab_entries

# Assert on MARKUP, not on the inlined stylesheet (the vendored CSS always names the
# selectors): the rendered group/overflow carry these literal class attributes.
GROUP = 'class="sl-avatar-group"'
MORE = 'class="sl-avatar-group__more"'


def _questions():
    return [{"id": "q1", "text": "Would this help you?", "kind": "single",
             "options": ["Yes", "No"]}]


def _steps():
    return [{"index": 0,
             "action": {"type": "click", "target": "start", "detail": "clicked start"},
             "monologue": "thinking aloud", "state": {"screen": "s0"},
             "friction": {"level": "none", "note": ""},
             "verdict": {"would_continue": True, "reason": "clear"}}]


def _reaction():
    return {"summary": "walked it", "verdict": "Works for me.",
            "liked": ["the flow"], "friction": [], "steps": _steps(),
            "predicted_behaviors": [], "observed_state_refs": ["s0"]}


@pytest.fixture
def seeded(store):
    """One project, every kind seeded — five participants so the overflow chip is exercised."""
    pids = [create_persona(store, f"Crew Member {i}") for i in range(5)]
    proj = services.create_research_project("Attribution study", goal="who shows up where?",
                                            persona_ids=pids, store=store)
    council = services.record_council(
        proj["id"], "Does attribution read consistently?", pids,
        statements=[{"persona_id": p, "text": f"voice {i}", "stance": {"value": 1}}
                    for i, p in enumerate(pids)],
        summary="aligned", store=store, key="attr-c")
    synthesis = services.record_synthesis(
        "Attribution synthesis", "start", council_ids=[council["id"]], store=store, key="attr-s",
        payload={"gesamtbild": "One rule everywhere.",
                 "statements": [{"persona_id": p, "text": f"distilled {i}"}
                                for i, p in enumerate(pids[:2])]})
    survey = services.record_survey(proj["id"], "Attribution survey", _questions(), store=store)["survey"]
    services.import_survey_responses(
        survey["id"],
        [{"respondent_key": f"persona:{pids[0]}", "submitted_at": "2026-06-10T10:00:00Z",
          "answers": [{"question_id": "q1", "value": "Yes"}], "source": "test"}],
        store=store)
    proto = prototypes.register_prototype("attr-proto", "Attribution prototype", "prototypes/attr",
                                          project_id=proj["id"], store=store)
    psess = services.record_prototype_session(
        pids[0], proto["id"], "psession_attr", "2026-06-11", _reaction(),
        key="attr-ps", store=store)["prototype_session"]
    usess = services.record_usability_session(
        pids[1], {"kind": "prototype", "id": proto["id"], "label": "Attribution prototype"},
        "prototype", "2026-06-11", _steps(),
        {"completed": True, "dropoff_step": None, "summary": "done", "predicted_behaviors": []},
        project_id=proj["id"], store=store, key="attr-us")["usability_session"]
    # ---- the NEGATIVE kinds: no direct persona participation in their data ----
    decision = services.record_decision(proj["id"], "Ship it", "We ship.",
                                        [{"kind": "council", "id": council["id"]}],
                                        store=store)["decision"]
    hypothesis = services.record_hypothesis(
        proj["id"], "Attribution increases trust",
        {"metric": "trust", "expected_direction": "up"}, store=store)["hypothesis"]
    note = services.create_note(proj["id"], "An observation without a speaker.", store=store)
    asset = services.attach_asset(proj["id"], content_base64="UEsDBA==", filename="evidence.pptx",
                                  title="Evidence deck", store=store)
    return {"store": store, "pids": pids, "project": proj, "council": council,
            "synthesis": synthesis, "survey": survey, "proto": proto, "psess": psess,
            "usess": usess, "decision": decision, "hypothesis": hypothesis,
            "note": note["note"] if "note" in note else note, "asset": asset}


def _rows(store, tab: str) -> str:
    """Render the tab's rows exactly the way the Library does (ui.primitive_row over
    _tab_entries) and return the concatenated html."""
    return "".join(str(ui.primitive_row(x["kind"], x["rec"], store, href=x["href"]))
                   for x in _tab_entries(tab, store))


# --------------------------------------------------------------- rows: the positive kinds

def test_rows_with_participation_render_the_avatar_group(seeded):
    store = seeded["store"]
    for tab in ("councils", "reports", "surveys", "sessions", "prototypes"):
        html = _rows(store, tab)
        assert GROUP in html, f"{tab} rows must carry the participation avatar-group (W11)"
    # 5 participants ⇒ max 4 avatars + the "+1" overflow chip, identical anatomy to the detail
    councils = _rows(store, "councils")
    assert MORE in councils and ">+1<" in councils


def test_rows_without_participation_render_none(seeded):
    store = seeded["store"]
    for tab in ("decisions", "hypotheses", "notes", "assets"):
        html = _rows(store, tab)
        assert GROUP not in html, (
            f"{tab} rows must NOT render an avatar group — decision/hypothesis/note/asset "
            "carry no direct persona participation (the W11 negative rule)")


def test_projects_list_rows_render_the_cohort_group(seeded):
    html = TestClient(web.create_app()).get("/jobs?lang=en").text
    assert GROUP in html and MORE in html        # 5-persona cohort ⇒ 4 avatars + "+1"


def test_project_outline_prototype_row_renders_the_drivers(seeded):
    html = TestClient(web.create_app()).get(f'/jobs/{seeded["project"]["id"]}?lang=en').text
    # the prototype outline row (data-oid = prototype id) carries the crew cluster
    row = html.split(f'data-oid="{seeded["proto"]["id"]}"', 1)[1].split("</a>", 1)[0]
    assert GROUP in row, "the outline prototype row must show its session drivers (W11)"


# --------------------------------------------------------------- detail pages

def _header_region(html: str) -> str:
    """The detail page's header region: everything before the first content section. The hero
    sub / report cover / council participants opener all render before the first `sec-`/block
    anchor, so the group must appear here — not buried somewhere in the body."""
    cut = len(html)
    for marker in ('class="sec"', 'class="block"', 'class="sl-prose'):
        i = html.find(marker)
        if i != -1:
            cut = min(cut, i)
    return html[:cut]


def test_detail_headers_with_participation_render_the_avatar_group(seeded):
    client = TestClient(web.create_app())
    pages = {
        "council": f'/councils/{seeded["council"]["id"]}',
        "synthesis": f'/syntheses/{seeded["synthesis"]["id"]}',
        "survey": f'/surveys/{seeded["survey"]["id"]}',
        "prototype": f'/prototypes/{seeded["proto"]["slug"]}',
        "prototype session": f'/sessions/{seeded["psess"]["id"]}',
        "usability session": f'/sessions/{seeded["usess"]["id"]}',
    }
    for kind, url in pages.items():
        html = client.get(url + "?lang=en").text
        assert GROUP in _header_region(html), (
            f"the {kind} detail header must carry the participation avatar-group (W11): {url}")


def test_detail_pages_without_participation_render_none(seeded):
    client = TestClient(web.create_app())
    pages = {
        "decision": f'/decisions/{seeded["decision"]["id"]}',
        "hypothesis": f'/hypotheses/{seeded["hypothesis"]["id"]}',
        "note": f'/notes/{seeded["note"]["id"]}',
        "asset": f'/assets/{seeded["asset"]["id"]}',
    }
    for kind, url in pages.items():
        html = client.get(url + "?lang=en").text
        assert GROUP not in html, (
            f"the {kind} detail page must NOT render an avatar group (W11 negative rule): {url}")
