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
import html
import json
import re

from starlette.testclient import TestClient

from sonaloop import prototypes, services, web
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
    from sonaloop.web._primitive_taxonomy import primitive_color, primitive_family
    assert primitive_family("open_question") == "frame"
    assert primitive_family("hypothesis") == "frame"
    assert primitive_family("asset") == "material"
    assert primitive_family("url_artifact") == "material"
    assert primitive_family("council") == "ask"
    assert primitive_family("survey") == "ask"
    assert primitive_family("prototype") == "material"
    assert primitive_family("session") == "test"
    assert primitive_family("note") == "capture"
    assert primitive_family("synthesis") == "conclude"
    assert primitive_family("decision") == "conclude"
    assert primitive_color("open_question") != "#9aa0a6"
    assert primitive_color("session") != "#9aa0a6"


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
    html = _client().get(f"/projects/{pid}?lang=en").text   # the project outline (graph view retired)
    # open questions: an outline row
    assert 'data-rkind="open_question"' in html and "What about pricing?" in html
    # URL artifacts: an outline row without capture/status pills
    assert 'data-rkind="url_artifact"' in html and "Landing A" in html
    assert "not captured — reference only" not in html
    # evidence assets: an outline row
    assert 'data-rkind="asset"' in html and "Field note" in html
    # surveys: an outline row deep-linking to the survey detail
    assert 'data-rkind="survey"' in html and "Pricing survey" in html
    survey_row = next(chunk for chunk in html.split('class="olrow')[1:]
                      if 'data-rkind="survey"' in chunk.split(">", 1)[0])
    assert "/surveys/" in survey_row and "Draft</span>" not in survey_row
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


def test_freeform_project_outline_uses_its_plan_not_fake_lanes(store):
    pid = _seed_tier3(store)
    council = services.record_council(pid, "Review landing context", [], store=store)
    services.record_hypothesis(pid, "If pricing is clear, support increases",
                               {"metric": "support", "expected_direction": "increase"}, store=store)
    services.record_decision(pid, "Ship A", "Ship the small pilot",
                             [{"kind": "council", "id": council["id"]}],
                             store=store)

    html = _client().get(f"/projects/{pid}?lang=en").text
    assert 'class="ol-flat"' not in html
    topbar_actions = html.split('<span class="sl-tb-actions">', 1)[1].split('</span></header>', 1)[0]
    assert 'class="sl-toolbtn tour-plan-chip"' in topbar_actions
    assert "freeform</a>" in topbar_actions
    assert "Methodology · freeform" not in html
    assert services.get_plan(pid, store=store)["tasks"][0]["id"] == "frame__root"
    for fake in (">Input<", ">Ask<", ">Test<", ">Conclude<"):
        assert fake not in html
    for kind in ("url_artifact", "survey", "hypothesis", "decision"):
        assert f'data-rkind="{kind}"' in html


def test_project_header_surfaces_applied_methodology(store):
    free = services.start_project("Freeform study", "Understand this", store=store)
    dd = services.start_project("DD study", "Understand this", methodology="double_diamond", store=store)
    client = _client()
    html = client.get(f'/projects/{free["id"]}?lang=en').text
    topbar_actions = html.split('<span class="sl-tb-actions">', 1)[1].split('</span></header>', 1)[0]
    assert 'class="sl-toolbtn tour-plan-chip"' in topbar_actions
    assert "freeform</a>" in topbar_actions
    html = client.get(f'/projects/{dd["id"]}?lang=en').text
    topbar_actions = html.split('<span class="sl-tb-actions">', 1)[1].split('</span></header>', 1)[0]
    assert 'class="sl-toolbtn tour-plan-chip"' in topbar_actions
    assert "Double Diamond</a>" in topbar_actions
    assert "Methodology · Double Diamond" not in html


def test_project_outline_rows_expose_real_hover_relations(store):
    project = services.start_project("Related rows", "How might we prove the value?",
                                     methodology="double_diamond", store=store)
    council = services.record_council(project["id"], "What matters?", [], store=store)
    synthesis = services.record_synthesis("Evidence summary", "What matters?",
                                           council_ids=[council["id"]],
                                           project_id=project["id"], store=store)
    decision = services.record_decision(project["id"], "Use the evidence", "Proceed from the report.",
                                        based_on=[{"kind": "synthesis", "id": synthesis["id"]}],
                                        status="adopted", store=store)["decision"]
    html = _client().get(f'/projects/{project["id"]}?lang=en').text
    assert 'class="ol-rel-svg"' in html and "data-relgraph" in html
    assert f'data-oid="council:{council["id"]}"' in html
    assert f'data-rel-out="synthesis:{synthesis["id"]}"' in html
    assert f'data-oid="synthesis:{synthesis["id"]}"' in html
    assert f'data-rel-in="council:{council["id"]}"' in html
    assert f'data-rel-out="{decision["id"]}"' in html
    assert f'data-oid="{decision["id"]}"' in html
    assert f'data-rel-in="synthesis:{synthesis["id"]}"' in html


def test_project_outline_surfaces_plan_judgment_trace_edges(store):
    project = services.start_project("Trace rows", "How might we keep evidence connected?",
                                     methodology="double_diamond", store=store)
    council = services.record_council(project["id"], "What evidence matters?", [], store=store)
    survey = services.record_survey(
        project["id"], "Evidence survey",
        [{"id": "q1", "text": "Which signal matters most?", "kind": "single",
          "options": ["A", "B"]}],
        derived_from=[{"kind": "council", "id": council["id"]}], status="open", store=store)["survey"]
    define_syn = services.record_synthesis("Define synthesis", "What matters?",
                                            council_ids=[council["id"]],
                                            project_id=project["id"], store=store)
    services.link_evidence(project["id"], "verify__define",
                           {"kind": "synthesis", "id": define_syn["id"]}, store=store)
    services.record_judgment(project["id"], "verify__define", "divergence_complete", True,
                             "Survey and council evidence converged.",
                             evidence_refs=[f"survey:{survey['id']}", f"synthesis:{define_syn['id']}"],
                             store=store)

    proto = prototypes.register_prototype("trace-proto", "Trace prototype", "prototypes/trace",
                                          project_id=project["id"], store=store)
    sess = services.record_prototype_session(
        "persona_trace", proto["id"], "trace-browser-session", "2026-06-16",
        {"persona": "Trace Persona", "summary": "Tested the prototype.",
         "liked": ["clear next action"], "friction": ["owner ambiguity"],
         "verdict": "continue with pilot", "observed_state_refs": ["prototype screen"]},
        key="trace-proto-session", store=store)["prototype_session"]
    deliver_syn = services.record_synthesis("Deliver synthesis", "Prototype result",
                                             council_ids=[council["id"]],
                                             project_id=project["id"], store=store)
    services.link_evidence(project["id"], "verify__deliver",
                           {"kind": "synthesis", "id": deliver_syn["id"]}, store=store)
    services.record_judgment(project["id"], "verify__deliver", "divergence_complete", True,
                             "Prototype and session evidence are sufficient.",
                             evidence_refs=[f"artifact:{proto['id']}", f"session:{sess['id']}",
                                            f"synthesis:{deliver_syn['id']}"],
                             store=store)

    page = _client().get(f'/projects/{project["id"]}?lang=en').text

    def rel_out(oid: str) -> str:
        m = re.search(rf'data-oid="{re.escape(oid)}"[^>]*data-rel-out="([^"]*)"', page)
        assert m, f"missing outline row for {oid}"
        return html.unescape(m.group(1))

    assert f"synthesis:{define_syn['id']}" in rel_out(survey["id"])
    assert f"synthesis:{deliver_syn['id']}" in rel_out(proto["id"])
    assert f"synthesis:{deliver_syn['id']}" in rel_out(sess["id"])


def test_project_trace_edges_are_registered(store):
    from sonaloop.project_trace import TRACE_EDGE_TYPES, collect_project_trace_edges
    from sonaloop.web._graph_outline_sessions import outline_session_groups
    from sonaloop.web._project_graph_view import augment_project_graph

    project = services.start_project("Registered trace", "How might we keep edge types fixed?",
                                     methodology="double_diamond", store=store)
    council = services.record_council(project["id"], "What matters?", [], store=store)
    survey = services.record_survey(
        project["id"], "Evidence survey",
        [{"id": "q1", "text": "Which signal matters most?", "kind": "single",
          "options": ["A", "B"]}],
        derived_from=[{"kind": "council", "id": council["id"]}], status="open", store=store)["survey"]
    synthesis = services.record_synthesis("Evidence summary", "What matters?",
                                           council_ids=[council["id"]],
                                           project_id=project["id"], store=store)
    services.record_decision(project["id"], "Use evidence", "Proceed.",
                             based_on=[{"kind": "synthesis", "id": synthesis["id"]}],
                             status="adopted", store=store)
    services.record_judgment(project["id"], "verify__define", "trace_closed", True,
                             "Survey evidence converged.",
                             evidence_refs=[f"survey:{survey['id']}"], store=store)
    graph = services.get_project_graph(project["id"], store=store)
    sessions = outline_session_groups([], store)
    decisions = services.list_decisions(project["id"], store=store)
    hypotheses = services.list_hypotheses(project["id"], store=store)
    surveys = services.list_surveys(project_id=project["id"], store=store)
    assets = services.list_assets(project["id"], store=store)
    full_graph = augment_project_graph(
        graph, sessions=sessions, decisions=decisions, hypotheses=hypotheses,
        surveys=surveys, assets=assets,
    )
    central_edges = collect_project_trace_edges(
        graph, full_graph["nodes"], sessions=sessions, decisions=decisions,
        hypotheses=hypotheses, surveys=surveys, assets=assets,
        base_edges=graph.get("edges") or [],
    )
    emitted = {e.get("type") for e in full_graph["edges"]}
    assert emitted <= set(TRACE_EDGE_TYPES), emitted - set(TRACE_EDGE_TYPES)

    def as_sorted_json(rows):
        return sorted(json.dumps(r, sort_keys=True) for r in rows)

    assert as_sorted_json(full_graph["edges"]) == as_sorted_json(central_edges)


def test_project_outline_marks_orphaned_trace_nodes_after_plan_completion(store):
    project = services.create_research_project("Trace health", goal="Understand orphaned evidence",
                                               store=store)
    services.record_survey(
        project["id"], "Unconsumed survey",
        [{"id": "q1", "text": "Still useful?", "kind": "single", "options": ["yes", "no"]}],
        status="open", store=store)
    page = _client().get(f'/projects/{project["id"]}?lang=en').text
    assert "unused after phase close" not in page

    services.record_frame(project["id"], "frame__root", ["What needs tracing?"],
                          memory_refs=["note:seed"], store=store)
    page = _client().get(f'/projects/{project["id"]}?lang=en').text
    assert "Unconsumed survey" in page
    assert "trace=orphaned" in page
    filtered = _client().get(f'/projects/{project["id"]}?trace=orphaned&lang=en').text
    assert "Unconsumed survey" in filtered


def test_empty_kinds_render_no_chrome(store):
    proj = services.create_research_project("Empty", goal="g", store=store)
    html = _client().get(f'/projects/{proj["id"]}?lang=en').text
    for kind in ("hypothesis", "decision", "open_question", "asset", "survey"):
        assert f'data-rkind="{kind}"' not in html, f"empty kind {kind} rendered a row"
    for anchor in ("#hypotheses", "#decisions", "#open-questions", "#assets", "#surveys"):
        assert f'href="{anchor}"' not in html, f"empty kind grew a jump-chip {anchor}"


def test_survey_row_keeps_counts_on_detail_not_outline(store):
    pid = _seed_tier3(store)
    sv = services.list_surveys(project_id=pid, store=store)[0]
    services.import_survey_responses(
        sv["id"], [{"respondent_key": "r1", "answers": [{"question_id": "q1", "value": "too high"}]}],
        store=store)
    html = _client().get(f"/projects/{pid}?lang=en").text
    # Counts live on the survey detail header/sections, not as project-outline pills.
    assert "1 responses" not in html and "1 questions" not in html
