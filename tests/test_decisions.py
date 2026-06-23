"""Decision records — what we decided, on which evidence, rejecting what (the ADR-style node
that closes the research loop).

Citation validation (no based_on → rejected; unresolvable based_on/rejected refs → rejected;
why-not notes kept per rejected ref), status transitions (proposed|adopted flips; superseded only
via the supersede flow), the supersede flow (both directions recorded, the old record demoted and
immutable afterwards), the resolvable `decision` Ref kind + backlinks ("informed decision <title>"),
the plan-export Decisions section with citations, and the project-page section (adopted / proposed
/ superseded groups with evidence chips).
"""
from __future__ import annotations

import pytest

from conftest import create_persona
from sonaloop import artifacts, services
from sonaloop import plan as P


def _project(store, title="Pension awareness"):
    return services.create_research_project(title, goal="How do people plan retirement?",
                                            store=store)


def _council(store, project_id, prompt="Would a digital pension check help?"):
    pid = create_persona(store, "Evi Dence")
    statements = [{"persona_id": pid, "text": "it would help me", "stance": {"value": 1}}]
    return services.record_council(project_id, prompt, [pid], statements=statements,
                                   summary="useful", store=store)


def _record(store, project_id, **kw):
    council = kw.pop("council", None) or _council(store, project_id)
    args = {"title": "Ship the pension check as a standalone tool",
            "decision": "We build the check as its own flow, not a bank-portal plugin.",
            "based_on": [{"kind": "council", "id": council["id"]}]}
    args.update(kw)
    return services.record_decision(project_id, store=store, **args)["decision"]


# --------------------------------------------------------------- record: citation validation

def test_record_get_roundtrip_and_list(store):
    proj = _project(store)
    dec = _record(store, proj["id"])
    got = services.get_decision(dec["id"], store=store)
    assert got["status"] == "proposed" and got["superseded_by"] is None
    assert got["based_on"][0]["role"] == "based_on"          # default role
    assert services.list_decisions(proj["id"], store=store)[0]["id"] == dec["id"]
    assert services.list_decisions(proj["id"], status="proposed", store=store)
    assert not services.list_decisions(proj["id"], status="adopted", store=store)
    with pytest.raises(ValueError, match="status"):
        services.list_decisions(proj["id"], status="maybe", store=store)
    with pytest.raises(KeyError):
        services.get_decision("dec_missing", store=store)
    with pytest.raises(KeyError):
        services.record_decision("rproject_missing", "t", "d", [], store=store)


def test_a_decision_must_cite_evidence_that_resolves(store):
    proj = _project(store)

    def rec(based_on, **kw):
        return services.record_decision(proj["id"], "Pick A", "we pick A", based_on,
                                        store=store, **kw)

    with pytest.raises(ValueError, match="at least one resolvable ref"):
        rec([])                                              # no evidence → no decision record
    with pytest.raises(ValueError, match="at least one resolvable ref"):
        rec(None)
    with pytest.raises(ValueError, match="does not resolve"):
        rec([{"kind": "council", "id": "council_missing"}])  # the whole point: refs must resolve
    with pytest.raises(ValueError, match="needs an id"):
        rec([{"kind": "external", "text": "gut feeling"}])   # a free string is not citable evidence
    with pytest.raises(ValueError, match=r"based_on\[0\] must be a Ref dict"):
        rec(["council_abc"])
    council = _council(store, proj["id"])
    with pytest.raises(ValueError, match="title is required"):
        services.record_decision(proj["id"], "  ", "d",
                                 [{"kind": "council", "id": council["id"]}], store=store)
    with pytest.raises(ValueError, match="decision is required"):
        services.record_decision(proj["id"], "t", "",
                                 [{"kind": "council", "id": council["id"]}], store=store)
    with pytest.raises(ValueError, match="proposed|adopted"):
        rec([{"kind": "council", "id": council["id"]}], status="superseded")
    # a synthesis (whole artifact or a finding anchor) is the natural evidence kind
    syn = services.record_synthesis("Key problems", "hmw", [council["id"]],
                                    {"findings": [{"kind": "key_problem", "text": "trust gap"}]},
                                    store=store)
    dec = rec([{"kind": "synthesis", "id": syn["id"], "anchor": "f1"}])["decision"]
    assert dec["based_on"][0]["anchor"] == "f1"
    with pytest.raises(ValueError, match="does not resolve"):
        rec([{"kind": "synthesis", "id": syn["id"], "anchor": "f99"}])   # broken part anchor


def test_rejected_alternatives_resolve_and_keep_their_why_not_notes(store):
    proj = _project(store)
    keep = _council(store, proj["id"])
    alt = _council(store, proj["id"], prompt="Embed it in the bank portal instead?")
    with pytest.raises(ValueError, match=r"rejected\[0\] does not resolve"):
        _record(store, proj["id"], council=keep,
                rejected=[{"kind": "council", "id": "council_missing", "note": "too slow"}])
    dec = _record(store, proj["id"], council=keep,
                  rejected=[{"kind": "council", "id": alt["id"],
                             "note": "banks gatekeep the audience"}])
    assert dec["rejected"][0]["role"] == "rejected"          # default role
    assert dec["rejected"][0]["note"] == "banks gatekeep the audience"
    assert artifacts.resolve_ref(dec["rejected"][0], store)["exists"] is True


def test_stable_key_upserts_but_a_superseded_record_is_immutable(store):
    proj = _project(store)
    council = _council(store, proj["id"])
    d1 = _record(store, proj["id"], council=council, key="dec-1")
    d2 = _record(store, proj["id"], council=council, key="dec-1", title="Sharper title")
    assert d2["id"] == d1["id"] and d2["created_at"] == d1["created_at"]
    assert len(services.list_decisions(proj["id"], store=store)) == 1
    succ = _record(store, proj["id"], council=council, key="dec-2", title="The successor")
    services.update_decision(d1["id"], superseded_by=succ["id"], store=store)
    with pytest.raises(ValueError, match="superseded"):      # the record is the audit trail
        _record(store, proj["id"], council=council, key="dec-1")


# --------------------------------------------------------------- status transitions

def test_status_transitions(store):
    proj = _project(store)
    dec = _record(store, proj["id"])
    assert services.update_decision(dec["id"], status="adopted",
                                    store=store)["decision"]["status"] == "adopted"
    assert services.update_decision(dec["id"], status="proposed",
                                    store=store)["decision"]["status"] == "proposed"
    with pytest.raises(ValueError, match="status must be one of"):
        services.update_decision(dec["id"], status="abandoned", store=store)
    with pytest.raises(ValueError, match="superseded_by"):    # superseded needs the successor link
        services.update_decision(dec["id"], status="superseded", store=store)
    with pytest.raises(ValueError, match="nothing to update"):
        services.update_decision(dec["id"], store=store)
    with pytest.raises(KeyError):
        services.update_decision("dec_missing", status="adopted", store=store)
    # recording directly as adopted is fine — superseded is the only birth status rejected
    adopted = _record(store, proj["id"], key="adopted", status="adopted")
    assert adopted["status"] == "adopted"


def test_supersede_links_both_records_and_demotes_the_old_one(store):
    proj = _project(store)
    council = _council(store, proj["id"])
    old = _record(store, proj["id"], council=council, key="old", status="adopted")
    new = _record(store, proj["id"], council=council, key="new", title="Pivot to B2B2C",
                  status="adopted")
    out = services.update_decision(old["id"], superseded_by=new["id"], store=store)
    assert out["decision"]["status"] == "superseded"
    assert out["decision"]["superseded_by"] == new["id"]      # forward link
    assert out["successor"]["supersedes"] == old["id"]        # backward link — both directions
    assert services.get_decision(new["id"], store=store)["supersedes"] == old["id"]
    # a superseded record is frozen: no flips, no second supersede
    with pytest.raises(ValueError, match="already superseded"):
        services.update_decision(old["id"], status="adopted", store=store)
    with pytest.raises(ValueError, match="already superseded"):
        services.update_decision(old["id"], superseded_by=new["id"], store=store)
    # supersede guards: self-reference, unknown successor, cross-project
    with pytest.raises(ValueError, match="cannot supersede itself"):
        services.update_decision(new["id"], superseded_by=new["id"], store=store)
    with pytest.raises(KeyError):
        services.update_decision(new["id"], superseded_by="dec_missing", store=store)
    with pytest.raises(ValueError, match="cannot also flip"):
        services.update_decision(new["id"], status="adopted", superseded_by=old["id"], store=store)
    other = _project(store, "Other study")
    foreign = _record(store, other["id"], key="foreign")
    with pytest.raises(ValueError, match="same project"):
        services.update_decision(new["id"], superseded_by=foreign["id"], store=store)


# --------------------------------------------------------------- graph: ref kind + backlinks

def test_decision_is_a_resolvable_ref_kind(store):
    proj = _project(store)
    dec = _record(store, proj["id"])
    ref = {"kind": "decision", "id": dec["id"]}
    assert artifacts.ref_href(ref) == f'/decisions/{dec["id"]}'
    res = artifacts.resolve_ref(ref, store)
    assert res["exists"] is True and res["title"] == dec["title"]
    assert artifacts.resolve_ref({"kind": "decision", "id": "dec_missing"}, store)["exists"] is False


def test_backlinks_show_the_decision_a_synthesis_informed(store):
    proj = _project(store)
    council = _council(store, proj["id"])
    syn = services.record_synthesis("Key problems", "hmw", [council["id"]],
                                    {"gesamtbild": "the picture"}, store=store)
    alt = _council(store, proj["id"], prompt="The rejected alternative")
    dec = _record(store, proj["id"],
                  based_on=[{"kind": "synthesis", "id": syn["id"]}],
                  rejected=[{"kind": "council", "id": alt["id"], "note": "too narrow"}])
    idx = services.ref_backlinks(proj["id"], store=store)
    back = idx[artifacts.part_address("synthesis", syn["id"])]
    assert back == [{"href": f'/decisions/{dec["id"]}', "label": dec["title"], "role": "based_on"}]
    rej = idx[artifacts.part_address("council", alt["id"])]
    assert {"href": f'/decisions/{dec["id"]}', "label": dec["title"], "role": "rejected"} in rej


# --------------------------------------------------------------- exports: the Decisions section

def test_plan_export_gains_a_decisions_section_with_citations(store):
    proj = _project(store)
    P.save_plan(P.new_plan(proj["id"], goal="g", tasks=[
        {"id": "frame1", "title": "Frame", "bucket": "analyze", "capability": "frame"}]),
        store=store)
    md0 = services.export_plan_md(proj["id"], store=store)
    assert "## Decisions" not in md0                          # no decisions → no empty chrome
    council = _council(store, proj["id"])
    alt = _council(store, proj["id"], prompt="Bank-portal plugin?")
    old = _record(store, proj["id"], council=council, key="old", status="adopted",
                  rejected=[{"kind": "council", "id": alt["id"], "note": "banks gatekeep"}])
    new = _record(store, proj["id"], council=council, key="new", title="Pivot to B2B2C")
    services.update_decision(old["id"], superseded_by=new["id"], store=store)
    md = services.export_plan_md(proj["id"], store=store)
    assert "## Decisions" in md
    assert old["title"] in md and new["title"] in md and old["decision"] in md
    assert f'based on: {council["prompt"]} (council:{council["id"]})' in md   # live-resolved citation
    assert f'rejected: {alt["prompt"]} (council:{alt["id"]}) — banks gatekeep' in md
    assert f'superseded by: {new["title"]} (decision:{new["id"]})' in md
    assert "`superseded`" in md and "`proposed`" in md


# ------------------------------------------ inspector: project rows + the decision slide-over

def test_project_page_rows_and_decision_slideover(store):
    """UX P2 (spec/ux-contract.md §3.4) + U6/U7 (§8.1/§8.2): a decision is an outline ROW
    (status pill + evidence count) whose data-drawer carries its CANONICAL detail URL — the
    slide-over renders the FULL detail content via the route's ?slide=1 fragment variant;
    the same Ref route serves the full page, which keeps the row's anchor as the secondary
    link."""
    from starlette.testclient import TestClient
    from sonaloop import web
    from sonaloop.web._i18n import STRINGS
    proj = _project(store)
    council = _council(store, proj["id"])
    alt = _council(store, proj["id"], prompt="The alternative considered")
    adopted = _record(store, proj["id"], council=council, key="a", status="adopted",
                      rejected=[{"kind": "council", "id": alt["id"], "note": "banks gatekeep"}])
    proposed = _record(store, proj["id"], council=council, key="p",
                       title="Offer a paper fallback")
    succ = _record(store, proj["id"], council=council, key="s", title="The successor",
                   status="adopted")
    services.update_decision(adopted["id"], superseded_by=succ["id"], store=store)
    client = TestClient(web.create_app())
    html = client.get(f'/jobs/{proj["id"]}?lang=en').text
    for key in ("dec_status_adopted", "dec_status_proposed", "dec_status_superseded"):
        assert STRINGS["en"][key] in html                     # the three lifecycle pills, on rows
    assert adopted["title"] in html and proposed["title"] in html and succ["title"] in html
    assert html.count('data-rkind="decision"') == 3           # rows, not a wall of text (C6)
    assert adopted["decision"] not in html                    # the ADR body lives behind the row
    assert f'id="dec-{adopted["id"]}"' in html                # the row IS the anchor target
    # the row's drawer URL IS the canonical detail URL (§8.1 — pushState makes it the address)
    assert f'data-drawer="/decisions/{adopted["id"]}"' in html
    # the slide-over fragment = the SAME detail renderer, content only: full ADR body,
    # evidence + rejected chips, supersede links — and no app shell around it
    slide = client.get(f'/decisions/{adopted["id"]}?slide=1&lang=en').text
    assert slide.startswith('<div class="sl-slide">') and "sl-sidebar" not in slide
    assert adopted["decision"] in slide
    assert f'/councils/{council["id"]}' in slide              # evidence chip via render_ref
    assert f'/councils/{alt["id"]}' in slide                  # rejected chip deep-links too
    assert "banks gatekeep" in slide                          # the why-not note
    assert STRINGS["en"]["dec_superseded_by"] in slide
    assert client.get("/decisions/nope?slide=1").status_code == 200  # honest empty state, no 500
    # the Ref route serves a REAL detail page on the shared anatomy (UX U7, §8.2): kind
    # eyebrow + status pill + the full ADR record + the secondary view-in-project anchor link
    r = client.get(f'/decisions/{adopted["id"]}?lang=en')
    assert r.status_code == 200
    detail = r.text
    assert STRINGS["en"]["decision_kind"] in detail           # the kind eyebrow
    # the supersede flow demoted this record — the header pill says so honestly
    assert STRINGS["en"]["dec_status_superseded"] in detail
    assert adopted["title"] in detail and adopted["decision"] in detail
    assert f'/councils/{council["id"]}' in detail             # evidence chip resolved
    assert f'/councils/{alt["id"]}' in detail and "banks gatekeep" in detail
    assert f'/decisions/{succ["id"]}' in detail               # supersede → the sibling DETAIL page
    # the rail's Project link lands ON the deciding row (round-2 audit: the old
    # "View in project" meta-line link retired — no other kind carried one)
    assert f'/jobs/{proj["id"]}#dec-{adopted["id"]}' in detail
    assert STRINGS["en"]["runtime_maybe_cleared"] in client.get("/decisions/nope?lang=en").text
    # a project without decisions shows no decision rows (and no empty chrome)
    other = _project(store, "Quiet study")
    assert 'data-rkind="decision"' not in client.get(f'/jobs/{other["id"]}?lang=en').text


def test_global_decisions_list_renders_empty_and_populated(store):
    from starlette.testclient import TestClient
    from sonaloop import web
    from sonaloop.web._i18n import STRINGS
    client = TestClient(web.create_app())
    empty = client.get("/decisions?lang=en")                  # honest empty state, no chrome
    assert empty.status_code == 200 and STRINGS["en"]["no_decisions"] in empty.text
    pa, pb = _project(store, "Project A"), _project(store, "Project B")
    council = _council(store, pa["id"])
    alt = _council(store, pa["id"], prompt="The alternative considered")
    adopted = _record(store, pa["id"], council=council, key="a", status="adopted",
                      rejected=[{"kind": "council", "id": alt["id"], "note": "banks gatekeep"}])
    proposed = _record(store, pb["id"], key="p", title="Offer a paper fallback")
    page = client.get("/decisions?lang=en")
    assert page.status_code == 200
    html = page.text
    # the URL stays canonical; the content is the LIBRARY with the Decisions tab active
    # (ux-contract §3.5) — status-pilled rows, slide-over on click, no redirect
    assert STRINGS["en"]["library_h"] in html
    assert STRINGS["en"]["dec_status_adopted"] in html and STRINGS["en"]["dec_status_proposed"] in html
    assert adopted["title"] in html and proposed["title"] in html
    # each row's href IS the canonical detail URL (§8.1) and doubles as its slide-over target
    assert f'href="/decisions/{adopted["id"]}"' in html
    assert f'href="/decisions/{proposed["id"]}"' in html
    assert "Project A" in html and "Project B" in html        # the owning project, as the desc line
    assert f'data-drawer="/decisions/{adopted["id"]}"' in html
    # the slide-over fragment carries the full record (evidence + rejected chips, why-not note)
    slide = client.get(f'/decisions/{adopted["id"]}?slide=1&lang=en').text
    assert f'/councils/{council["id"]}' in slide and f'/councils/{alt["id"]}' in slide
    assert "banks gatekeep" in slide
    # the list route does not shadow the canonical /decisions/{id} DETAIL page (UX U7)
    r = client.get(f'/decisions/{adopted["id"]}?lang=en')
    assert r.status_code == 200 and adopted["decision"] in r.text
    assert f'/jobs/{pa["id"]}#dec-{adopted["id"]}' in r.text   # secondary view-in-project link


def test_synthesis_page_shows_informed_decisions(store):
    from starlette.testclient import TestClient
    from sonaloop import web
    from sonaloop.web._i18n import STRINGS
    proj = _project(store)
    council = _council(store, proj["id"])
    syn = services.record_synthesis("Key problems", "hmw", [council["id"]],
                                    {"gesamtbild": "the picture"}, store=store)
    html_before = TestClient(web.create_app()).get(f'/syntheses/{syn["id"]}?lang=en').text
    assert STRINGS["en"]["dec_informed_h"] not in html_before
    dec = _record(store, proj["id"], based_on=[{"kind": "synthesis", "id": syn["id"]}])
    html = TestClient(web.create_app()).get(f'/syntheses/{syn["id"]}?lang=en').text
    assert STRINGS["en"]["dec_informed_h"] in html            # "informed decision <title>"
    assert dec["title"] in html and f'/decisions/{dec["id"]}' in html


# --------------------------------------------------------------- review fixes (audit-trail integrity)

def test_key_hash_is_project_scoped(store):
    pa, pb = _project(store, "Project A"), _project(store, "Project B")
    da = _record(store, pa["id"], key="q3-pivot")
    db = _record(store, pb["id"], key="q3-pivot", title="B's own call on the same key")
    assert da["id"] != db["id"]
    assert [x["id"] for x in services.list_decisions(pa["id"], store=store)] == [da["id"]]
    assert services.get_decision(da["id"], store=store)["title"].startswith("Ship the pension")


def test_a_superseded_record_cannot_become_a_successor(store):
    proj = _project(store)
    d1, d2, d3 = (_record(store, proj["id"], key=k) for k in ("k1", "k2", "k3"))
    services.update_decision(d1["id"], superseded_by=d2["id"], store=store)
    with pytest.raises(ValueError, match="itself superseded"):
        services.update_decision(d2["id"], superseded_by=d1["id"], store=store)  # the A→B→A cycle
    with pytest.raises(ValueError, match="itself superseded"):
        services.update_decision(d3["id"], superseded_by=d1["id"], store=store)
    kept = services.get_decision(d1["id"], store=store)
    assert kept["status"] == "superseded" and kept["superseded_by"] == d2["id"]
    assert kept.get("supersedes") in (None, "")              # the frozen record was never mutated


def test_one_successor_supersedes_one_predecessor(store):
    proj = _project(store)
    x1, x2, succ = (_record(store, proj["id"], key=k) for k in ("x1", "x2", "succ"))
    services.update_decision(x1["id"], superseded_by=succ["id"], store=store)
    with pytest.raises(ValueError, match="already supersedes"):
        services.update_decision(x2["id"], superseded_by=succ["id"], store=store)
    assert services.get_decision(succ["id"], store=store)["supersedes"] == x1["id"]
    assert services.get_decision(x2["id"], store=store)["status"] != "superseded"


def test_export_flattens_multiline_host_text(store):
    proj = _project(store)
    _record(store, proj["id"],
            title="Honest title\n## Injected heading\n- **fake** — `adopted`",
            decision="line one\n# another forged heading")
    md = services.decisions_section_md(proj["id"], store=store)
    # The hostile text survives as inline content but no LINE starts with it — structure defused.
    assert not any(ln.startswith(("## Injected", "# another", "- **fake**"))
                   for ln in md.splitlines())
    assert "Honest title ## Injected heading" in md


def test_decision_rows_replace_the_header_jump_chips(store):
    """UX P2: the appendix + header jump-chips retired — decisions are outline rows; the group
    headers carry the honest counts (C8) instead of anchor-jump chips."""
    from starlette.testclient import TestClient
    from sonaloop import web
    proj = _project(store)
    council = _council(store, proj["id"])
    _record(store, proj["id"], council=council, key="a", status="adopted")
    _record(store, proj["id"], council=council, key="b")
    client = TestClient(web.create_app())
    html = client.get(f'/jobs/{proj["id"]}?lang=en').text
    assert html.count('data-rkind="decision"') == 2      # both decisions are rows
    assert 'href="#decisions"' not in html and "projjump" not in html
    assert 'id="decisions"' not in html                  # the appendix section is gone
    # ... and a project without decisions shows no decision chrome at all
    other = _project(store, "Quiet study")
    other_html = client.get(f'/jobs/{other["id"]}?lang=en').text
    assert 'data-rkind="decision"' not in other_html and 'href="#decisions"' not in other_html
