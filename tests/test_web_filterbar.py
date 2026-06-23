"""The Linear-grade FilterBar (UX U10, spec/ux-contract.md §8.5).

Contract under test: filter state lives in the URL and round-trips (?kind=…&phase=…&persona=…
&status=… on the project outline; ?project=…&status=…[&direction=…] on the Library tabs);
comma = OR within a facet, params AND across facets; the facet menu carries honest per-value
counts over the unfiltered set (no dead options); rows/groups that filter to zero disappear
and group counts stay true; an active filter that matches nothing renders the teaching empty
state (C8/F1) with a Clear way out.
"""
from __future__ import annotations

import base64

from starlette.testclient import TestClient

from sonaloop import services, web
from sonaloop.web._filterbar import filter_url, parse_multi
from conftest import create_persona


def _client():
    return TestClient(web.create_app())


def _seed(store) -> dict:
    """One PLAN-based project carrying a filterable mix: a council (with a persona, at the
    discover phase), a decision (proposed), two hypotheses (open), an open question, a
    survey (draft) and an evidence asset."""
    pid_p = create_persona(store, "Frida Filter")
    proj = services.start_project("Filterable", "why do users churn?", "double_diamond",
                                  persona_ids=[pid_p], store=store)
    pid = proj["id"]
    services.record_frame(pid, "frame__discover", ["why churn?"], memory_refs=["m1"], store=store)
    council = services.record_council(pid, "Would you pay for this?", [pid_p], statements=[
        {"persona_id": pid_p, "text": "Probably not at that price.", "stance": {"value": 1}}],
        summary="mixed", store=store)
    task = services.add_task(pid, "act", "explore", "Pain council",
                             consumes=["frame__discover"], store=store)
    services.link_evidence(pid, task["id"], {"kind": "council", "id": council["id"]}, store=store)
    services.record_decision(pid, "Pick A", "we pick A",
                             [{"kind": "council", "id": council["id"]}], store=store)
    for text in ("Users abandon at the price reveal", "Setup takes under five minutes"):
        services.record_hypothesis(pid, text, {"metric": "abandon_rate",
                                               "expected_direction": "down"}, store=store)
    services.record_open_questions(pid, ["What about pricing?"], store=store)
    services.record_survey(pid, "Pricing survey",
                           [{"id": "q1", "kind": "text", "text": "Why this price?"}], store=store)
    services.attach_asset(pid, content_base64=base64.b64encode(b"field note").decode(),
                          filename="note.txt", title="Field note", store=store)
    return {"project_id": pid, "persona_id": pid_p}


def _rkinds(html: str) -> set[str]:
    import re
    return set(re.findall(r'data-rkind="([a-z_]+)"', html))


# ----------------------------------------------------------------------- URL grammar units

def test_parse_multi_and_filter_url_round_trip():
    assert parse_multi("council,decision") == ["council", "decision"]
    assert parse_multi("") == [] and parse_multi(None) == []
    url = filter_url("/jobs/p1", {"kind": ["council", "decision"], "status": []})
    assert url == "/jobs/p1?kind=council,decision"
    assert filter_url("/formats?tab=assets", {"direction": ["in"]}) \
        == "/formats?tab=assets&direction=in"
    assert filter_url("/jobs/p1", {"kind": []}) == "/jobs/p1"


# -------------------------------------------------------------------------- project outline

def test_outline_kind_filter_round_trips_and_hides_other_rows(store):
    ids = _seed(store)
    pid = ids["project_id"]
    client = _client()
    full = client.get(f"/jobs/{pid}?lang=en").text
    assert {"council", "decision", "hypothesis", "survey", "asset"} <= _rkinds(full)
    html = client.get(f"/jobs/{pid}?kind=decision&lang=en").text
    assert _rkinds(html) == {"decision"}                       # rows filter server-side
    assert "Pick A" in html
    # the active chip + the Clear action render; the URL is the state
    assert "sl-filter-chip" in html and f'href="/jobs/{pid}"' in html


def test_outline_or_within_a_facet_and_across_facets(store):
    ids = _seed(store)
    pid = ids["project_id"]
    client = _client()
    html = client.get(f"/jobs/{pid}?kind=decision,hypothesis&lang=en").text
    assert _rkinds(html) == {"decision", "hypothesis"}          # comma = OR
    # AND across facets: hypotheses are status=open, decisions are proposed — combining
    # kind=decision with status=open matches nothing of the decision kind
    html = client.get(f"/jobs/{pid}?kind=decision&status=open&lang=en").text
    assert "decision" not in _rkinds(html)


def test_outline_status_persona_and_phase_facets_are_honest(store):
    ids = _seed(store)
    pid = ids["project_id"]
    client = _client()
    html = client.get(f"/jobs/{pid}?status=open&lang=en").text
    assert {"hypothesis", "open_question"} <= _rkinds(html)     # both carry status=open
    assert "decision" not in _rkinds(html)
    html = client.get(f'/jobs/{pid}?persona={ids["persona_id"]}&lang=en').text
    assert "council" in _rkinds(html)                           # the persona debated here
    assert "decision" not in _rkinds(html)
    html = client.get(f"/jobs/{pid}?phase=frame__discover&lang=en").text
    assert "council" in _rkinds(html)                           # the discover-phase council


def test_outline_trace_facet_filters_consumed_rows(store):
    ids = _seed(store)
    pid = ids["project_id"]
    client = _client()
    full = client.get(f"/jobs/{pid}?lang=en").text
    assert "Trace" in full and "used" in full                    # the trace facet is advertised
    html = client.get(f"/jobs/{pid}?trace=consumed&lang=en").text
    assert "council" in _rkinds(html)                            # council feeds the decision
    assert "Pick A" not in html                                  # terminal decision is not consumed
    assert "sl-filter-chip" in html and "Trace" in html


def test_outline_trace_facet_filters_orphaned_rows(store):
    proj = services.create_research_project("Trace filter", goal="g", store=store)
    services.record_survey(
        proj["id"], "Unconsumed survey",
        [{"id": "q1", "text": "Still useful?", "kind": "single", "options": ["yes", "no"]}],
        status="open", store=store)
    services.record_frame(proj["id"], "frame__root", ["What needs tracing?"],
                          memory_refs=["note:seed"], store=store)
    html = _client().get(f'/jobs/{proj["id"]}?trace=orphaned&lang=en').text
    assert _rkinds(html) == {"survey"}
    assert "Unconsumed survey" in html and "unused" in html


def test_library_trace_facet_uses_project_trace_states(store):
    ids = _seed(store)
    pid = ids["project_id"]
    client = _client()
    full = client.get(f"/councils?project={pid}&lang=en").text
    assert "Trace" in full and "used" in full
    html = client.get(f"/councils?project={pid}&trace=consumed&lang=en").text
    assert "Would you pay for this?" in html
    html = client.get(f"/decisions?project={pid}&trace=terminal&lang=en").text
    assert "Pick A" in html
    html = client.get(f"/surveys?project={pid}&trace=consumed&lang=en").text
    assert "Nothing matches these filters" in html


def test_outline_facet_menu_carries_counts_over_the_unfiltered_set(store):
    ids = _seed(store)
    pid = ids["project_id"]
    html = _client().get(f"/jobs/{pid}?kind=decision&lang=en").text
    # the menu still offers the other kinds, with their true counts (2 hypotheses)
    assert "sl-menu-item__count" in html
    assert 'kind=decision,hypothesis' in html                   # toggling adds to the OR set
    assert ">2<" in html                                        # the hypotheses count


def test_outline_empty_filter_result_teaches(store):
    ids = _seed(store)
    pid = ids["project_id"]
    html = _client().get(f"/jobs/{pid}?kind=session&lang=en").text  # no sessions recorded
    assert "Nothing matches these filters" in html
    assert f'href="/jobs/{pid}"' in html                    # the Clear way out


# --------------------------------------------------------------------------------- library

def test_library_project_filter_round_trips(store):
    ids = _seed(store)
    pid_b = create_persona(store, "Otto Other")
    other = services.create_research_project("Other", persona_ids=[pid_b], store=store)
    council_b = services.record_council(other["id"], "Option B?", [pid_b], statements=[
        {"persona_id": pid_b, "text": "B works.", "stance": {"value": 1}}],
        summary="b", store=store)
    services.record_decision(other["id"], "Pick B", "we pick B",
                             [{"kind": "council", "id": council_b["id"]}], store=store)
    client = _client()
    full = client.get("/decisions?lang=en").text
    assert "Pick A" in full and "Pick B" in full
    html = client.get(f'/decisions?project={ids["project_id"]}&lang=en').text
    assert "Pick A" in html and "Pick B" not in html
    assert "sl-filter-chip" in html and 'href="/decisions"' in html


def test_library_status_filter_and_composition_with_tab(store):
    _seed(store)
    client = _client()
    html = client.get("/formats?tab=hypotheses&status=open&lang=en").text
    assert "Users abandon at the price reveal" in html
    html = client.get("/formats?tab=hypotheses&status=validated&lang=en").text
    assert "Nothing matches these filters" in html              # honest: nothing validated yet
    assert 'href="/formats?tab=hypotheses"' in html             # Clear keeps the tab


def test_assets_tab_gains_the_direction_facet(store):
    ids = _seed(store)
    services.attach_asset(ids["project_id"], content_base64="UEsDBA==",
                          filename="report.pptx", title="Report out", direction="out",
                          store=store)
    client = _client()
    html = client.get("/assets?direction=out&lang=en").text
    assert "Report out" in html and "Field note" not in html
    html = client.get("/assets?direction=in&lang=en").text
    assert "Field note" in html and "Report out" not in html


def test_library_filter_menu_counts_per_value(store):
    ids = _seed(store)
    html = _client().get("/hypotheses?lang=en").text
    assert "sl-menu-item__count" in html and ">2<" in html      # 2 open hypotheses
    assert f'href="/hypotheses?project={ids["project_id"]}"' in html


def test_library_subtype_filter_separates_reference_kinds(store):
    ids = _seed(store)
    pid = ids["project_id"]
    services.add_artifact(pid, "https://example.test", kind="url",
                          title="Marketing site", capture=False, store=store)
    services.add_artifact(pid, "https://figma.test/proto", kind="prototype",
                          title="External click model", capture=False, store=store)
    html = _client().get("/references?subtype=external_prototype&lang=en").text
    assert "External click model" in html and "Marketing site" not in html
    assert "Format" in html and "External prototype" in html
    assert 'href="/references"' in html                         # Clear keeps canonical route


def test_library_subtype_filter_separates_council_formats(store):
    ids = _seed(store)
    pid = ids["project_id"]
    p = ids["persona_id"]
    services.record_red_team(pid, "What breaks this?", persona_ids=[p],
                             objections=[{"persona_id": p, "theme": "Trust",
                                           "text": "I would not trust it.", "severity": "high"}],
                             store=store)
    html = _client().get("/councils?subtype=red_team&lang=en").text
    assert "What breaks this?" in html and "Would you pay for this?" not in html
    assert "Red-team" in html


def test_compatibility_subtype_filter_values_keep_resolving_to_registry_forms(store):
    ids = _seed(store)
    pid = ids["project_id"]
    p = ids["persona_id"]
    services.add_artifact(pid, "https://example.test/a", kind="variant",
                          label="A", title="Compatibility A/B stimulus", capture=False, store=store)
    services.record_head_to_head(pid, "Compatibility option comparison?", ["A", "B"], key="compatibility-h2h", store=store)
    services.record_survey(pid, "Compatibility choice survey",
                           [{"id": "q1", "kind": "single", "text": "Pick one", "options": ["A", "B"]}],
                           store=store)
    proto = services.register_prototype("compatibility-filter-proto", "Compatibility prototype", ".",
                                        project_id=pid, store=store)
    services.record_usability_session(
        p, {"kind": "prototype", "id": proto["id"], "label": "Compatibility prototype"},
        "artifact", "2026-06-16",
        [{"index": 0, "action": {"type": "look", "target": "home"},
          "state": {"screen": "Home"}, "friction": {"level": "none", "note": ""},
          "verdict": {"would_continue": True, "reason": "clear"}}],
        {"completed": True, "summary": "completed", "predicted_behaviors": []},
        project_id=pid, key="compatibility-proto-session", store=store)

    client = _client()
    cases = [
        ("/references?subtype=ab_variant&lang=en", "Compatibility A/B stimulus", "Marketing site"),
        ("/councils?subtype=head_to_head&lang=en", "Compatibility option comparison?", "Would you pay for this?"),
        ("/surveys?subtype=single_survey&lang=en", "Compatibility choice survey", "Pricing survey"),
        ("/sessions?subtype=prototype_session&lang=en", "Compatibility prototype", "No sessions yet"),
    ]
    for path, present, absent in cases:
        html = client.get(path).text
        assert present in html, path
        assert absent not in html, path


def test_library_explains_primitives_and_subforms(store):
    html = _client().get("/formats?tab=councils&lang=en").text
    assert "Family" in html and "Primitive" in html and "Form" in html
    assert "sl-taxonomy" in html
    assert "sl-taxo-pill" in html
    assert "Red-team" in html and "red_team" in html
    assert "Head-to-head" in html and "head_to_head" in html
    assert "Format primitives and their real subforms" not in html


def test_every_library_tab_has_subtype_documentation():
    from sonaloop.web._primitive_taxonomy import primitive_subtypes
    from sonaloop.web.pages.library import LIBRARY_TABS, TAB_KIND

    missing = [key for key, *_ in LIBRARY_TABS if not primitive_subtypes(TAB_KIND[key])]
    assert missing == []


# ------------------------------------------------------------------- V1: search + theme facet

def test_outline_search_slot_renders_inside_the_bar(store):
    """The FilterBar always carries the leading search slot (V1: 'filter + suche immer'),
    and an active query keeps its value in the input (URL round-trip)."""
    ids = _seed(store)
    pid = ids["project_id"]
    client = _client()
    html = client.get(f"/jobs/{pid}?lang=en").text
    assert "sl-filter-search" in html and 'name="q"' in html
    html = client.get(f"/jobs/{pid}?q=pricing&lang=en").text
    assert 'value="pricing"' in html


def test_outline_text_search_filters_rows_server_side(store):
    ids = _seed(store)
    pid = ids["project_id"]
    client = _client()
    html = client.get(f"/jobs/{pid}?q=pricing&lang=en").text
    kinds = _rkinds(html)
    assert "survey" in kinds and "open_question" in kinds       # both carry "pricing"
    assert "decision" not in kinds                              # "Pick A" does not
    # case- AND diacritic-insensitive ("Prícing" folds to "pricing")
    html = client.get(f"/jobs/{pid}?q=Pr%C3%ADcing&lang=en").text
    assert "survey" in _rkinds(html)
    # status is a facet, not hidden search text.
    html = client.get(f"/jobs/{pid}?q=proposed&lang=en").text
    assert "decision" not in _rkinds(html)


def test_outline_search_composes_with_facets(store):
    ids = _seed(store)
    pid = ids["project_id"]
    client = _client()
    html = client.get(f"/jobs/{pid}?q=pricing&kind=survey&lang=en").text
    assert _rkinds(html) == {"survey"}                          # q AND kind
    html = client.get(f"/jobs/{pid}?q=zzz-no-match&lang=en").text
    assert "Nothing matches these filters" in html              # the teaching empty state


def test_outline_theme_facet_replaces_the_chip_row(store):
    """Themes are a facet (?theme=<section id>), not visible row tags."""
    ids = _seed(store)
    pid = ids["project_id"]
    g = services.get_project_graph(pid, store=store)
    council_oid = next(n["study_id"] for n in g["nodes"] if n.get("kind") == "council")
    sec = services.create_section(pid, "Pricing pains", kind="theme",
                                  member_ids=[council_oid], store=store)
    client = _client()
    full = client.get(f"/jobs/{pid}?lang=en").text
    assert "olthemes" not in full and "olth-chip" not in full   # the chip row is gone
    assert "olth-dot" not in full
    assert "Pricing pains" in full                              # the facet menu offers it
    html = client.get(f'/jobs/{pid}?theme={sec["id"]}&lang=en').text
    assert _rkinds(html) == {"council"}                         # membership filters rows


def test_library_text_search_per_tab(store):
    ids = _seed(store)
    client = _client()
    html = client.get("/formats?tab=hypotheses&q=abandon&lang=en").text
    assert "Users abandon at the price reveal" in html
    assert "Setup takes under five minutes" not in html
    assert 'value="abandon"' in html                            # the input keeps its value
    # canonical kind routes share the grammar; q composes with the project facet
    html = client.get(f'/hypotheses?q=abandon&project={ids["project_id"]}&lang=en').text
    assert "Users abandon at the price reveal" in html
    html = client.get("/hypotheses?q=zzz-no-match&lang=en").text
    assert "Nothing matches these filters" in html
