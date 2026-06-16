"""Project presence CONTRACT — house gate (tracker: sonaloop/project-presence-contract).

User decision (2026-06-10): nothing project-scoped may be invisible on the DEFAULT project page.
Every artifact kind carrying a project_id declares its presence in the web/_presence REGISTRY
(outline row · nested child; hidden is forbidden — ALLOWED_HIDDEN is empty), and every
list_*(project_id=…) family on the services/storage surface must map to a registered kind. The
gate enumerates the real surface, so a NEW project-scoped kind fails here until it declares
where it shows. The rendering half proves the UX-P2 absorption (spec/ux-contract.md §3.4): open
questions, URL artifacts, assets and surveys are OUTLINE ROWS on the default view — no appendix
sections, no header jump-chips, and no chrome at all for empty kinds.
"""
from __future__ import annotations

import base64

from starlette.testclient import TestClient

from sonaloop import services, web
from sonaloop.web import _presence as PR

# The audited core inventory (the three tiers): everything project-scoped the default page shows.
CORE_KINDS = {
    "council", "synthesis", "report", "note", "prototype", "session", "section",
    "hypothesis", "decision", "open_question", "asset", "survey", "url_artifact",
}


def _client():
    return TestClient(web.create_app())


# --------------------------------------------------------------------------- the registry gate

def test_presence_gate_is_clean():
    """The single check: the live surface and the declarations agree, and nothing is hidden."""
    assert PR.presence_violations() == []


def test_every_core_kind_is_declared_visible():
    assert CORE_KINDS <= set(PR.REGISTRY), (
        f"core kinds missing from the presence registry: {sorted(CORE_KINDS - set(PR.REGISTRY))}")
    for kind, d in PR.REGISTRY.items():
        assert d.presence != PR.HIDDEN_WITH_REASON, f"{kind!r} may not register hidden"
        assert d.where, f"{kind!r} must name its affordance"
    assert not PR.ALLOWED_HIDDEN, "ALLOWED_HIDDEN must stay empty (user decision 2026-06-10)"


def test_presence_kinds_have_product_taxonomy():
    from sonaloop.web._primitive_taxonomy import PRIMITIVES
    missing = set(PR.REGISTRY) - set(PRIMITIVES)
    assert not missing, f"presence kinds missing product taxonomy entries: {sorted(missing)}"


def test_product_taxonomy_groups_match_user_model():
    from sonaloop.web._primitive_taxonomy import primitive_family
    assert primitive_family("open_question") == "frame"
    assert primitive_family("hypothesis") == "frame"
    assert primitive_family("asset") == "material"
    assert primitive_family("url_artifact") == "material"
    assert primitive_family("council") == "ask"
    assert primitive_family("survey") == "ask"
    assert primitive_family("prototype") == "test"
    assert primitive_family("session") == "test"
    assert primitive_family("note") == "capture"
    assert primitive_family("synthesis") == "conclude"
    assert primitive_family("decision") == "conclude"


def test_gate_fails_on_an_undeclared_fake_kind(monkeypatch):
    """The 'fails on a new kind' proof: a project-scoped list_* family nobody declared lands in
    the violations — a new artifact kind cannot ship without declaring where it shows."""
    def list_widgets(project_id: str | None = None, store=None):  # pragma: no cover - never called
        return []

    monkeypatch.setattr(services, "list_widgets", list_widgets, raising=False)
    violations = PR.presence_violations()
    assert any("list_widgets" in v for v in violations), violations


def test_gate_fails_on_a_hidden_registration(monkeypatch):
    """The 'fails on hidden' proof: registering a kind hidden (outside the empty ALLOWED_HIDDEN)
    is a violation even when it carries a reason."""
    monkeypatch.setitem(PR.REGISTRY, "martian",
                        PR.Declared(PR.HIDDEN_WITH_REASON, where="nowhere", reason="trust me"))
    violations = PR.presence_violations()
    assert any("martian" in v and "hidden" in v for v in violations), violations


def test_gate_fails_on_a_stale_mapping(monkeypatch):
    """A LIST_SOURCES entry whose function left the surface is flagged — the mapping stays an
    inventory of the REAL surface in both directions."""
    monkeypatch.setitem(PR.LIST_SOURCES, "list_unicorns", "unicorn")
    violations = PR.presence_violations()
    assert any("list_unicorns" in v for v in violations), violations


# ------------------------------------------------------------------- the tier-3 rescue renders

def _seed_tier3(store) -> str:
    """A project carrying one of each formerly-invisible kind: an open question, a URL artifact
    (uncaptured A/B reference), a text evidence asset, and a draft survey."""
    proj = services.create_research_project("Presence", goal="map the flows", store=store)
    pid = proj["id"]
    services.record_open_questions(pid, ["What about pricing?"], store=store)
    services.add_artifact(pid, "https://example.test/landing", kind="url", title="Landing A",
                          capture=False, store=store)
    services.attach_asset(pid, content_base64=base64.b64encode(b"field note").decode(),
                          filename="note.txt", title="Field note", store=store)
    services.record_survey(pid, "Pricing survey",
                           [{"id": "q1", "kind": "text", "text": "Why this price?"}], store=store)
    return pid


def test_absorbed_kinds_are_outline_rows_on_the_default_view(store):
    pid = _seed_tier3(store)
    html = _client().get(f"/projects/{pid}?lang=en").text   # the DEFAULT view — no ?view=graph
    # open questions: an outline row with the open/resolved pill
    assert 'data-rkind="open_question"' in html and "What about pricing?" in html
    # URL artifacts: an outline row (chip contract kind) with the capture-status chip
    assert 'data-rkind="url_artifact"' in html and "Landing A" in html
    assert "not captured — reference only" in html
    # evidence assets: an outline row with the direction pill
    assert 'data-rkind="asset"' in html and "Field note" in html and "Evidence" in html
    # surveys: an outline row deep-linking to the survey detail, lifecycle pill
    assert 'data-rkind="survey"' in html and "Pricing survey" in html
    assert "/surveys/" in html and "Draft" in html
    # the appendix is GONE (ux-contract §3.4): no sections, no header jump-chips
    assert "projsection" not in html and "projjump" not in html
    for anchor in ("#open-questions", "#assets", "#surveys"):
        assert f'href="{anchor}"' not in html, f"retired jump-chip {anchor} resurfaced"
    # absorbed rows with a detail page open it as a slide-over (§8.1: drawer URL = canonical
    # href); the artifact-inventory audit made questions/references/assets first-class details.
    assert 'data-drawer="/surveys/' in html, "survey row lost its slide-over"
    for kind in ("open_question", "url_artifact"):
        armed = False
        for chunk in html.split('class="olrow')[1:]:
            head = chunk.split(">", 1)[0]
            if f'data-rkind="{kind}"' in head:
                armed = "data-drawer=" in head
                break
        assert armed, f"{kind} row lost its detail slide-over"
    assert 'data-drawer="/assets/' in html, "asset row lost its detail slide-over"


def test_empty_kinds_render_no_chrome(store):
    proj = services.create_research_project("Empty", goal="g", store=store)
    html = _client().get(f'/projects/{proj["id"]}?lang=en').text
    for kind in ("hypothesis", "decision", "open_question", "asset", "survey"):
        assert f'data-rkind="{kind}"' not in html, f"empty kind {kind} rendered a row"
    for anchor in ("#hypotheses", "#decisions", "#open-questions", "#assets", "#surveys"):
        assert f'href="{anchor}"' not in html, f"empty kind grew a jump-chip {anchor}"


def test_survey_row_counts_questions_and_responses(store):
    pid = _seed_tier3(store)
    sv = services.list_surveys(project_id=pid, store=store)[0]
    services.import_survey_responses(
        sv["id"], [{"respondent_key": "r1", "answers": [{"question_id": "q1", "value": "too high"}]}],
        store=store)
    html = _client().get(f"/projects/{pid}?lang=en").text
    # the survey row's honest count (C8, V2 row truth ≤2 chips): the RESPONSE count is the
    # row's signal; the question count lives on the detail page
    assert "1 responses" in html and "1 questions" not in html
