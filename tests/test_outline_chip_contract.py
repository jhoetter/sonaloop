"""Project outline visual contract.

The outline is a structural timeline: phase grouping, row icon, title, avatar participation and
timestamp. Status/form/trace/count data stays available through filters and detail pages, but it
does not render as same-looking pills in every row.
"""
from __future__ import annotations

import re

import pytest
from starlette.testclient import TestClient

from sonaloop import plan as P
from sonaloop import prototypes, services, web
from sonaloop.web._graph_outline import _outline_html

_RKIND = re.compile(r'data-rkind="([^"]*)"')


def _client():
    return TestClient(web.create_app())


# --------------------------------------------------------------------- the contract machinery

def _row_chunks(html: str) -> list[str]:
    return ["class=\"olrow" + chunk for chunk in html.split('class="olrow')[1:]]


def _all_rkinds(html: str) -> set[str]:
    return set(_RKIND.findall(html))


def _assert_tag_free_outline(html: str) -> None:
    rows = _row_chunks(html)
    assert rows, "no outline rows rendered"
    for forbidden in (
        'class="ol-chips"', 'class="ol-ptag', 'class="ol-sds"', 'class="ol-funnel"',
        'class="olth-pills"', 'class="olth-dot"',
    ):
        assert forbidden not in html, f"outline resurfaced retired row chrome: {forbidden}"


# --------------------------------------------------------------------- seeding (every row kind)

def _steps(n=2, blocked_last=False):
    out = []
    for i in range(n):
        fr = "blocked" if (blocked_last and i == n - 1) else "none"
        out.append({"index": i,
                    "action": {"type": "click", "target": f"b{i}", "detail": f"clicked {i}"},
                    "monologue": "thinking", "state": {"screen": f"s{i}"},
                    "friction": {"level": fr, "note": "stuck" if fr != "none" else ""},
                    "verdict": {"would_continue": fr == "none", "reason": ""}})
    return out


def _record(store, pid, persona_id, subject, fidelity, key, completed=True):
    outcome = {"completed": completed, "dropoff_step": None if completed else 1,
               "summary": "walked", "predicted_behaviors": []}
    return services.record_usability_session(
        persona_id, subject, fidelity, "2026-06-10",
        _steps(blocked_last=not completed), outcome,
        project_id=pid, key=key, store=store)["usability_session"]


def _every_kind_project(store) -> str:
    """One project whose outline emits every visible row kind: plan-based council + synthesis,
    notes, prototypes, sessions against prototype/live-url/flow subjects, a report, and the
    UX-P2 absorbed kinds (decision, survey, hypothesis, open question, evidence assets)."""
    proj = services.create_research_project("Chip contract", goal="g", store=store)
    pid = proj["id"]
    P.save_plan(P.new_plan(pid, goal="hmw?", methodology="double_diamond_deep", tasks=[
        {"id": "frame1", "title": "Frame · Discover", "bucket": "analyze", "capability": "frame"},
        {"id": "act1", "title": "Council", "bucket": "act", "capability": "explore",
         "consumes": ["frame1"], "produces": [{"kind": "council", "id": "cA"}]},
        {"id": "v1", "title": "Define", "bucket": "verify", "capability": "synthesize",
         "consumes": ["act1"], "produces": [{"kind": "synthesis", "id": "sA"}]},
    ]), store=store)
    # decision-mode council (proposal + votes) with two statements
    store.insert_council_session({
        "id": "cA", "created_at": "2026-06-01T09:00:00+00:00", "prompt": "Adopt the new flow?",
        "persona_ids": ["p1", "p2"], "proposal": "We adopt the new flow.",
        "statements": [{"persona_id": "p1", "text": "yes", "stance": {"value": 1}},
                       {"persona_id": "p2", "text": "no", "stance": {"value": -1}}],
        "votes": [{"persona_id": "p1", "vote": "dafür", "reason": "works"}],
        "summary": "s", "exec_summary": "e", "selection_reason": "x"})
    # in-progress synthesis with three findings
    store.upsert_synthesis({
        "id": "sA", "title": "Key problems", "created_at": "2026-06-02T09:00:00+00:00",
        "council_ids": ["cA"], "gesamtbild": "big picture", "statements": [],
        "findings": [{"text": "f1", "kind": "cluster"}, {"text": "f2", "kind": "key_problem"},
                     {"text": "f3", "kind": "recommendation"}],
        "status": "in_progress"})
    # notes: a plain observation + a concept note built into a prototype
    services.create_note(pid, "a plain observation",
                         created_at="2026-06-03T09:00:00+00:00", store=store)
    built = prototypes.register_prototype("built-proto", "Paired proto", "prototypes/built",
                                          project_id=pid, fidelity="lofi", store=store)
    services.create_note(pid, "a concept that got real", title="Concept",
                         data={"artifact_kind": "comparison", "prototype_ids": [built["id"]]},
                         created_at="2026-06-03T10:00:00+00:00", store=store)
    # a standalone prototype with two walks; the count is available from the detail/session views,
    # not as a parent-row funnel chip.
    solo = prototypes.register_prototype("solo-proto", "Solo proto", "prototypes/solo",
                                         project_id=pid, store=store)
    subj = {"kind": "prototype", "id": solo["id"], "label": "Solo proto"}
    _record(store, pid, "p1", subj, "prototype", key="walkA")
    _record(store, pid, "p2", subj, "prototype", key="walkB", completed=False)
    # live_url + scripted-path subjects render as top-level SESSION rows, not as new artifact kinds
    _record(store, pid, "p1", {"kind": "live_url", "url": "https://example.test/x",
                               "label": "Live x"}, "live", key="walkL")
    _record(store, pid, "p2", {"kind": "flow", "id": "flow-1", "label": "Signup flow"},
            "artifact", key="walkF")
    # the report (a project-scope synthesis) with two sections
    services.record_synthesis_outline(pid, {"build_order_narrative": "n",
                                            "sections": [{"heading": "A"}, {"heading": "B"}]},
                                      store=store)
    # a URL artifact (council-pool A/B capture) — an outline row on the DEFAULT view.
    services.add_artifact(pid, "https://example.test/landing", kind="url", title="Landing A",
                          capture=False, store=store)
    # the UX-P2 absorbed kinds — every one an outline row (§3.4):
    services.record_decision(pid, "Adopt the new flow", "We adopt it.",
                             based_on=[{"kind": "council", "id": "cA"}],
                             key="d1", status="adopted", store=store)
    services.record_survey(pid, "Pricing survey",
                           [{"id": "q1", "kind": "text", "text": "Why this price?"}], store=store)
    services.record_hypothesis(pid, "Half would pay",
                               {"metric": "conversion", "expected_direction": "increase"},
                               key="h1", store=store)
    services.record_open_questions(pid, ["What about pricing?"], store=store)
    import base64
    services.attach_asset(pid, content_base64=base64.b64encode(b"field note").decode(),
                          filename="note.txt", title="Field note", store=store)
    services.attach_asset(pid, content_base64=base64.b64encode(b"deck bytes").decode(),
                          filename="final.pptx", title="Final deck", direction="out", store=store)
    return pid


# ----------------------------------------------------------------------------- the house gate

def test_project_outline_rows_are_tag_free_but_keep_every_kind(store):
    pid = _every_kind_project(store)
    html = _client().get(f"/projects/{pid}?lang=en").text
    _assert_tag_free_outline(html)
    assert {
        "council", "synthesis", "note", "prototype", "session", "report", "url_artifact",
        "decision", "survey", "hypothesis", "open_question", "asset",
    } <= _all_rkinds(html)
    assert 'class="ol-ico"' in html
    row_html = "\n".join(_row_chunks(html))
    for retired in ("3 findings", "2 sections", "Draft</span>", "Open</span>",
                    "not captured — reference only", "2 sessions ·"):
        assert retired not in row_html


def test_unknown_outline_kind_still_renders_tag_free(store):
    pid = _every_kind_project(store)
    graph = services.get_project_graph(pid, store=store)
    for n in graph["nodes"]:
        if n.get("kind") == "council":
            n["kind"] = "martian"
    html = _outline_html(graph)
    assert 'data-rkind="martian"' in html
    _assert_tag_free_outline(html)


def test_freeform_project_synthesis_rows_stay_tag_free(store):
    """A project-bound synthesis row renders in the same quiet row vocabulary even when the project
    only has the default freeform frame plan."""
    proj = services.create_research_project("Freeform", store=store)
    services.record_synthesis(
        "Pains", "What hurts?", project_id=proj["id"], synthesis_id="syn0",
        payload={"status": "done", "gesamtbild": "big picture",
                 "findings": [{"text": "f1", "kind": "cluster"},
                              {"text": "f2", "kind": "key_problem"}]},
        store=store)
    html = _client().get(f'/projects/{proj["id"]}?lang=en').text
    _assert_tag_free_outline(html)
    assert 'data-rkind="synthesis"' in html and "Pains" in html and "2 findings" not in html


# ------------------------------------------------------------ slide-over universality (§8.1)

def test_every_row_kind_opens_a_resolving_slideover(store):
    """'Click a row → its FULL detail page slides over the outline' must be universally true
    for every kind that HAS a detail page (spec/ux-contract.md §8.1, superseding §3.3's
    essence-peek): each armed row's data-drawer URL IS its canonical href, and that URL's
    ?slide=1 fragment variant resolves as a bare content fragment (no app shell) — so
    pushState always lands on a REAL address. Assets included since UX U8 (/assets/{id};
    the row's download chip keeps the file one click away). External/synthesized rows
    (url_artifact) and inline open questions legitimately carry none."""
    import re as _re
    pid = _every_kind_project(store)
    client = _client()
    html = client.get(f"/projects/{pid}?lang=en").text
    rows = _re.findall(r'<a class="olrow[^>]*>|<a class="ol-stretch[^>]*>|<a class="sl-file__open[^>]*>', html)
    armed = {}
    for row in rows:
        m = _re.search(r'data-drawer="([^"]+)"', row)
        href = _re.search(r'href="([^"]+)"', row)
        if m:
            armed[m.group(1)] = href.group(1) if href else None
    # every kind with a detail page is armed — the registry lives in _graph_outline_extras
    from sonaloop.web._graph_outline_extras import DRAWER_KINDS
    rkinds = set()
    for chunk in html.split('class="olrow')[1:]:    # chunk = one row up to the next olrow start
        mk = _RKIND.search(chunk.split(">", 1)[0])
        if mk and 'data-drawer="' in chunk:         # normal rows arm the tag; chip rows the stretch link
            rkinds.add(mk.group(1))
    # asset rows are `.sl-file--row` FILE rows since V9 — the stretched body link arms the drawer
    for chunk in html.split('class="sl-file ')[1:]:
        mk = _RKIND.search(chunk.split(">", 1)[0])
        if mk and 'data-drawer="' in chunk:
            rkinds.add(mk.group(1))
    assert DRAWER_KINDS <= rkinds, f"kinds missing their slide-over arming: {DRAWER_KINDS - rkinds}"
    assert armed, "no slide-over-armed rows rendered"
    for url, href in armed.items():
        assert url == href, f"drawer URL {url!r} must BE the row's canonical href {href!r} (§8.1)"
        r = client.get(f"{url}{'&' if '?' in url else '?'}slide=1")
        assert r.status_code == 200, f"slide variant of {url} did not resolve"
        assert r.text.startswith('<div class="sl-slide">'), f"{url}?slide=1 is not a fragment"
        assert "sl-sidebar" not in r.text, f"{url}?slide=1 leaked the app shell"


# ------------------------------------------------ context URLs: ?d= SSR-open (§8.6, UX U11)

def _first_drawer_url(html: str) -> str:
    import re as _re
    m = _re.search(r'data-drawer="([^"]+)"', html)
    assert m, "no slide-over-armed row rendered"
    return m.group(1)


def test_context_url_ssr_opens_the_slideover(store):
    """Reload semantics (§8.6): a `?d=<urlencoded detail path>` URL server-renders the
    BACKGROUND page (full shell, outline behind) WITH the slide-over already open and the
    detail fragment inside — no fetch flash — and the no-JS close (scrim link) is the same
    URL with ?d= dropped while expand links the canonical detail URL."""
    from urllib.parse import quote
    pid = _every_kind_project(store)
    client = _client()
    detail = _first_drawer_url(client.get(f"/projects/{pid}?lang=en").text)
    r = client.get(f"/projects/{pid}?lang=en&d={quote(detail, safe='')}")
    assert r.status_code == 200
    assert 'class="sl-drawer sl-drawer--wide is-open"' in r.text, "panel not SSR-opened"
    assert '<div class="sl-slide">' in r.text, "detail fragment missing from the panel"
    assert "sl-sidebar" in r.text and 'class="olrow' in r.text, "background page missing"
    import html as _h
    assert f'data-ssr="{_h.escape(detail, quote=True)}"' in r.text
    assert f'data-drawer-close href="/projects/{pid}?lang=en"' in r.text, "no-JS close must drop ?d="
    assert f'data-drawer-expand href="{_h.escape(detail, quote=True)}"' in r.text


def test_context_param_composes_with_existing_params(store):
    """URL grammar (§8.6): ?d= JOINS the background's own params (filters, tabs, views) —
    the SSR view keeps the filtered outline behind the panel, and the no-JS close href
    drops ONLY ?d=, preserving the rest."""
    from urllib.parse import quote
    pid = _every_kind_project(store)
    client = _client()
    detail = _first_drawer_url(client.get(f"/projects/{pid}?lang=en").text)
    r = client.get(f"/projects/{pid}?lang=en&kind=decision&d={quote(detail, safe='')}")
    assert r.status_code == 200
    assert 'class="sl-drawer sl-drawer--wide is-open"' in r.text
    body = r.text.split('id="drawer"')[0]                  # the background, before the panel
    kinds = {m for m in _RKIND.findall(body)}
    assert kinds == {"decision"}, f"filter not applied behind the panel: {kinds}"
    assert f'data-drawer-close href="/projects/{pid}?lang=en&amp;kind=decision"' in r.text


@pytest.mark.parametrize("bad", [
    "https://evil.example/phish",        # absolute URL (scheme)
    "//evil.example/phish",              # protocol-relative host
    "/\\evil.example/phish",             # backslash normalization trick
    "councils/x",                        # not rooted
    "/projects/x?d=%2Fy",                # nested ?d= (recursion)
    "/nope/unknown-route",               # valid shape, unknown path -> 404 fragment
    "/data/assets",                      # static mount: no .sl-slide fragment
])
def test_invalid_context_param_renders_background_only(store, bad):
    """Guard (§8.6): a hostile or unknown ?d= NEVER 500s and never opens a panel — the
    background page renders normally (and only local detail paths are ever sub-requested,
    so ?d= cannot become an open-redirect/IFRAME-style injection vector)."""
    pid = _every_kind_project(store)
    from urllib.parse import quote
    r = _client().get(f"/projects/{pid}?lang=en&d={quote(bad, safe='')}")
    assert r.status_code == 200
    assert 'class="sl-drawer sl-drawer--wide is-open"' not in r.text
    assert "data-ssr=" not in r.text
    assert 'class="olrow' in r.text                        # the background rendered fine


def test_slide_fragment_variant_ignores_context_param(store):
    """A ?slide=1 fragment request never SSR-nests another drawer (?d= is meaningful only
    on full-page loads)."""
    from urllib.parse import quote
    pid = _every_kind_project(store)
    client = _client()
    detail = _first_drawer_url(client.get(f"/projects/{pid}?lang=en").text)
    r = client.get(f"/projects/{pid}?lang=en&slide=1&d={quote(detail, safe='')}")
    assert r.status_code == 200
    assert r.text.startswith('<div class="sl-slide">') and "sl-drawer" not in r.text


# ------------------------------------------------------------------- tag-free rows

def test_seeded_outline_suppresses_counts_statuses_and_stance_tags(store):
    pid = _every_kind_project(store)
    html = _client().get(f"/projects/{pid}?lang=en").text
    _assert_tag_free_outline(html)
    for retired in (
        "2 statements", "3 findings", "running</span>", "2 sections", "Observation</span>",
        "built</span>", "Completed</span>", "Dropped at step 1", "1× friction", "2 steps",
        "2 sessions ·",
    ):
        assert retired not in html


def test_only_prototype_sessions_are_outline_children(store):
    """Prototype sessions nest under the prototype. Flow/live-url subjects render directly as
    session rows, so the outline never invents walkthrough/live-surface row kinds."""
    pid = _every_kind_project(store)
    html = _client().get(f"/projects/{pid}?lang=en").text
    top_level_session = child_seen = False
    assert 'data-rkind="flow"' not in html
    assert 'data-rkind="live_url"' not in html
    assert "WALKTHROUGH" not in html and "LIVE SURFACE" not in html
    for chunk in html.split('class="olrow')[1:]:
        if 'data-rkind="session"' in chunk.split(">", 1)[0]:
            assert 'title="Session"' in chunk.split('<span class="ol-title"', 1)[0]
            assert 'class="sl-avatar-group"' not in chunk.split('<span class="ol-title"', 1)[0]
            if chunk.startswith(' ol-tw'):
                assert 'class="ol-kind"' not in chunk
                child_seen = True
            else:
                top_level_session = True
    assert top_level_session and child_seen


def test_outline_uses_icons_not_type_text_columns(store):
    pid = _every_kind_project(store)
    html = _client().get(f"/projects/{pid}?lang=en").text
    assert 'class="ol-ptag' not in html
    assert 'class="ol-ico"' in html
