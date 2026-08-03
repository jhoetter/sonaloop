"""Research graph (R1–R3) + meta-report (R4): project container, typed edges,
theme tags, backfill of existing syntheses, and the outline→section→export
round-trip. Deterministic, no network."""
from __future__ import annotations

import pytest

from sonaloop import services
from conftest import create_persona


def _seed_studies(store, n=3):
    store.insert_council_session({"id": "c1", "created_at": "2026-06-01T00:00:00+00:00",
                                  "prompt": "P?", "persona_ids": ["p1"], "statements": [], "votes": [],
                                  "proposal": "", "summary": "", "exec_summary": "exec", "selection_reason": "x"})
    titles = ["Pains", "UX", "Pricing"][:n]
    for i, ttl in enumerate(titles):
        store.upsert_synthesis({
            "id": f"syn{i}", "title": ttl, "created_at": f"2026-06-0{i+1}T00:00:00+00:00",
            "council_ids": ["c1"], "gesamtbild": f"{ttl} big picture",
            "statements": [{"persona_id": "p1", "text": "k", "stance": {"value": 1}}],
            "findings": [{"text": f"open from {ttl}", "kind": "open_question"},
                         {"text": "do X", "kind": "recommendation", "score": {"effort": 3, "value": 5}}],
            "status": "done"})
    return [f"syn{i}" for i in range(n)]


def _project_with_studies(store, sids, title="MR"):
    """Create a project and attach study_ids directly (the constellation study-graph tools that used
    to do this are retired; the plan is the graph now). These tests cover the meta-report machinery,
    which still works over a project's study_ids."""
    proj = services.create_research_project(title, goal="g", store=store)
    p = store.get_research_project(proj["id"])
    p["study_ids"] = list(sids)
    store.upsert_research_project(p)
    store.conn.execute("DELETE FROM research_plans WHERE project_id=?", (proj["id"],))
    return proj["id"]


def test_report_round_trip(store):
    _seed_studies(store, 2)
    pid = _project_with_studies(store, ["syn0", "syn1"])

    brief = services.brief_synthesis_outline(pid, store=store)
    assert brief["study_ids"] == ["syn0", "syn1"] and "instructions" in brief

    outline = {"build_order_narrative": "pains then pricing",
               "sections": [{"heading": "Pains", "theme_tags": ["pains"], "source_study_ids": ["syn0"], "intent": "establish"},
                            {"heading": "Pricing", "theme_tags": ["pricing"], "source_study_ids": ["syn1"], "intent": "price"}]}
    report = services.record_synthesis_outline(pid, outline, store=store)
    # a report IS a project-scope synthesis; outline+sections merged into one `sections` list
    assert report["scope"] == "project"
    assert [s["id"] for s in report["sections"]] == ["sec1", "sec2"]

    sb = services.brief_synthesis_section(pid, "sec1", store=store)
    assert [s["title"] for s in sb["frame"]["studies"]] == ["Pains"]
    services.record_synthesis_section(pid, "sec1",
                                      {"markdown": "## Pains\nReconciliation is the core pain.",
                                       "citations": [{"study_id": "syn0", "council_id": "c1", "quote": "exec"}]}, store=store)

    md = services.export_report(pid, format="md", store=store)
    assert "pains then pricing" in md and "Reconciliation is the core pain." in md
    # unauthored section shows a marker, not fabricated content
    assert ("not yet authored" in md) or ("noch nicht verfasst" in md)


def test_purge_clears_research_graph(store):
    persona_id = create_persona(store, "Purge Pat")
    _seed_studies(store, 2)
    pid = _project_with_studies(store, ["syn0", "syn1"], title="Wipe me")
    services.record_open_questions(pid, ["q?"], store=store)
    survey = services.record_survey(pid, "Wipe survey",
                                    [{"id": "q1", "kind": "single", "text": "Pick", "options": ["A", "B"]}],
                                    key="wipe-survey", store=store)["survey"]
    services.import_survey_responses(
        survey["id"],
        responses=[{"respondent_key": "r1", "answers": [{"question_id": "q1", "value": "A"}]}],
        store=store)
    services.record_hypothesis(pid, "Wipe bet",
                               {"metric": "completion", "expected_direction": "increase"},
                               store=store)
    services.record_decision(pid, "Wipe decision", "Stop stale rows",
                             [{"kind": "council", "id": "c1"}],
                             key="wipe-decision", store=store)
    proto = services.register_prototype("wipe-proto", "Wipe proto", ".",
                                        project_id=pid, store=store)
    services.record_usability_session(
        persona_id, {"kind": "prototype", "id": proto["id"], "label": "Wipe proto"},
        "artifact", "2026-06-16",
        [{"index": 0, "action": {"type": "look", "target": "home"},
          "state": {"screen": "Home"}, "friction": {"level": "none", "note": ""},
          "verdict": {"would_continue": True, "reason": "clear"}}],
        {"completed": True, "summary": "done", "predicted_behaviors": []},
        project_id=pid, key="wipe-usession", store=store)
    assert services.list_research_projects(store=store)
    services.purge_runtime_data(remove_files=False, store=store)
    assert services.list_research_projects(store=store) == []
    assert store.list_reports(pid) == []
    assert store.list_open_questions(pid) == []
    assert store.list_surveys() == []
    assert store.count_survey_responses(survey["id"]) == 0
    assert store.list_hypotheses() == []
    assert store.list_decisions() == []
    assert store.list_prototypes() == []
    assert store.list_usability_sessions() == []
    assert store.list_personas() == []


def test_deletes_cascade_and_detach(store):
    _seed_studies(store, 2)
    pid = _project_with_studies(store, ["syn0", "syn1"], title="Del")
    # delete a synthesis -> also detaches from the project graph
    services.delete_synthesis("syn0", store=store)
    assert store.get_synthesis("syn0") is None
    assert "syn0" not in services.get_research_project(pid, store=store)["study_ids"]
    # delete the project container
    services.delete_research_project(pid, store=store)
    assert services.list_research_projects(store=store) == []
    # delete a council
    services.delete_council("c1", store=store)
    assert store.get_council_session("c1") is None


def test_delete_research_project_cascades_project_scoped_outputs(store):
    persona_id = create_persona(store, "Cascade Casey")
    proj = services.start_project("Cascade", "How might we remove stale rows?", "double_diamond",
                                  persona_ids=[persona_id], store=store)
    pid = proj["id"]
    council = services.record_council(pid, "What is risky?", [persona_id], key="cascade-council",
                                      statements=[{"persona_id": persona_id, "text": "Risky.",
                                                   "stance": {"value": -1}}],
                                      store=store)
    synthesis = services.record_synthesis("Cascade report", "trace", [council["id"]], project_id=pid,
                                          key="cascade-report", store=store)
    services.record_survey(pid, "Cascade survey",
                           [{"id": "q1", "kind": "single", "text": "Pick", "options": ["A", "B"]}],
                           key="cascade-survey", store=store)
    services.record_hypothesis(pid, "Cascade bet",
                               {"metric": "completion", "expected_direction": "increase"},
                               store=store)
    services.record_decision(pid, "Cascade decision", "Stop stale rows",
                             [{"kind": "council", "id": council["id"]}],
                             key="cascade-decision", store=store)
    proto = services.register_prototype("cascade-proto", "Cascade proto", ".",
                                        project_id=pid, store=store)
    services.record_usability_session(
        persona_id, {"kind": "prototype", "id": proto["id"], "label": "Cascade proto"},
        "artifact", "2026-06-16",
        [{"index": 0, "action": {"type": "look", "target": "home"},
          "state": {"screen": "Home"}, "friction": {"level": "none", "note": ""},
          "verdict": {"would_continue": True, "reason": "clear"}}],
        {"completed": True, "summary": "done", "predicted_behaviors": []},
        project_id=pid, key="cascade-usession", store=store)
    store.insert_prediction_outcome({
        "id": "pbout-cascade", "project_id": pid,
        "created_at": "2026-06-16T12:00:00+00:00", "observed": 1.0,
    })
    # A project delete must clear its transient Activity/SSE rows without touching
    # workspace-level persona activity.
    global_event_id = store.append_event(
        "2026-06-16T12:01:00+00:00", "persona.updated", "persona", persona_id,
        None, {"url": f"/personas/{persona_id}"})
    legacy_synthesis_event_id = store.append_event(
        "2026-06-16T12:02:00+00:00", "synthesis.recorded", "synthesis", synthesis["id"],
        None, {"url": f"/syntheses/{synthesis['id']}"})
    project_events_before = [e for e in store.list_recent_events() if e.get("project_id") == pid]
    assert project_events_before
    assert any(e["event"] == "synthesis.recorded" and e["entity_id"] == synthesis["id"]
               for e in project_events_before)

    out = services.delete_research_project(pid, store=store)
    assert out["deleted"]["research_projects"] == 1
    assert out["deleted"]["prediction_outcomes"] == 1
    assert out["deleted"]["events"] == len(project_events_before) + 1
    assert services.list_research_projects(store=store) == []
    assert [c for c in store.list_council_sessions() if c.get("project_id") == pid] == []
    assert [s for s in store.list_syntheses() if s.get("project_id") == pid] == []
    assert store.list_surveys(pid) == []
    assert store.list_hypotheses(pid) == []
    assert store.list_decisions(pid) == []
    assert store.list_prototypes(pid) == []
    assert store.list_usability_sessions(project_id=pid) == []
    assert store.list_prediction_outcomes(pid) == []
    remaining_events = store.list_recent_events()
    assert all(e.get("project_id") != pid for e in remaining_events)
    assert all(e["id"] != legacy_synthesis_event_id for e in remaining_events)
    assert any(e["id"] == global_event_id for e in remaining_events)


def test_delete_persona(store):
    from conftest import create_persona
    pid = create_persona(store, "Doomed")
    assert any(p["id"] == pid for p in services.list_personas(store=store))
    out = services.delete_persona(pid, store=store)
    assert out["deleted"]["personas"] == 1
    assert all(p["id"] != pid for p in services.list_personas(store=store))


def test_note_form_classifies_ideas_insights_and_concepts(store):
    pid = services.create_research_project("Notes", goal="g", store=store)["id"]
    obs = services.create_note(pid, "raw signal", "Obs", store=store)
    idea = services.create_note(pid, "try a guided handoff", "Idea", kind="idea", store=store)
    insight = services.create_note(pid, "handoffs fail at exceptions", "Insight", kind="insight", store=store)
    concept = services.create_note(
        pid, "guided handoff concept", "Concept",
        data={"prototype_id": "proto_1", "artifact_kind": "journey"}, store=store)
    assert services.note_form(obs) == "observation"
    assert services.note_form(idea) == "idea"
    assert services.note_form(insight) == "insight"
    assert services.note_form(concept) == "concept"
    assert services.note_form_definition(concept)["id"] == "concept"


def test_invalid_outline_rejected(store):
    _seed_studies(store, 1)
    pid = _project_with_studies(store, ["syn0"], title="X")
    with pytest.raises(ValueError):
        services.record_synthesis_outline(pid, {"sections": []}, store=store)


def test_synthesis_preserves_structured_blocks_and_warns_when_thin(store):
    """GAP-3 (spec/exploration-depth-and-prototype-variety): a methodology's converge output —
    clusters / key_problems / ranking / shortlist — must survive record_synthesis and render in the
    web view + export; a near-empty synthesis returns a SYNTHESIS_THIN soft-warning."""
    from sonaloop import web
    from sonaloop import artifacts as A
    # primitives-only authoring: the converge output is FINDINGS (kind = cluster/key_problem/ranking/shortlist)
    payload = {
        "gesamtbild": "Der Kern: nicht alle fuer LV begeistern.",
        "findings": [
            {"text": "Sprachbarriere", "kind": "cluster", "meta": {"detail": "Das Wort ist die Huerde."}},
            {"text": "LV ist fuer 4/6 ein struktureller Non-Fit", "kind": "key_problem"},
            {"text": "proto_a", "kind": "ranking", "meta": {"detail": "ehrlichster Pfad"}},
            {"text": "proto_a", "kind": "shortlist"},
        ],
    }
    rec = services.record_synthesis("Define POV", "hmw", ["c1"], payload, store=store)
    got = services.get_synthesis(rec["id"], store=store)
    by_kind = {f["kind"]: f for f in got["findings"]}
    assert by_kind["cluster"]["text"] == "Sprachbarriere"
    assert A.finding_texts(got, "key_problem") == ["LV ist fuer 4/6 ein struktureller Non-Fit"]
    assert by_kind["ranking"]["text"] == "proto_a" and A.finding_texts(got, "shortlist") == ["proto_a"]
    # web + export surface the structured content
    html, toc = web._synthesis_html(store, got)
    assert "Sprachbarriere" in html and "Shortlist" in html and "proto_a" in html
    assert toc and all(len(item) == 2 for item in toc)
    md = services.export_synthesis(got["id"], "md", store=store)
    assert "Sprachbarriere" in md and "proto_a" in md
    # a truly empty synthesis warns (soft, non-blocking)
    thin = services.record_synthesis("Empty", "hmw", [], {}, store=store)
    assert any("SYNTHESIS_THIN" in w for w in thin.get("warnings", []))


def test_derive_sections_and_scaffold_synthesis_finish_by_construction(store):
    """ESV1: derive_sections organizes a completed methodology project (phase + prototype + deliver +
    run-journal sections, idempotent) and scaffold_synthesis seeds a project report — together flipping
    assess_project.finish to organized + handed-off, so a finished run is organized BY CONSTRUCTION."""
    proj = services.start_project("ESV1", "hmw?", "double_diamond", persona_ids=["p1"], store=store)
    pid = proj["id"]
    services.record_frame(pid, "frame__discover", ["q?"], memory_refs=["m1"], store=store)
    for cid in ("c1", "c2"):
        store.insert_council_session({"id": cid, "created_at": "2026-06-05T00:00:00+00:00", "prompt": "p",
            "persona_ids": ["p1"], "turns": [], "votes": [], "proposal": "", "summary": "",
            "exec_summary": "e", "selection_reason": "x"})
        a = services.add_task(pid, "act", "explore", f"angle {cid}", consumes=["frame__discover"], store=store)
        services.link_evidence(pid, a["id"], {"kind": "council", "id": cid}, store=store)
    services.record_judgment(pid, "verify__define", "divergence_complete", True, "ok", evidence_refs=["c1", "c2"], store=store)
    syn = services.record_synthesis("Define POV", "hmw", ["c1", "c2"],
                                    {"gesamtbild": "G" * 250, "positionierung": "P" * 250}, key="t:define", store=store)
    services.link_evidence(pid, "verify__define", {"kind": "synthesis", "id": syn["id"]}, store=store)
    services.complete_task(pid, "verify__define", store=store)
    assert services.assess_project(pid, store=store)["finish"]["organized"] is False
    out = services.derive_sections(pid, store=store)
    assert "Discover" in out["created"] and "Deliver — Conclusion" in out["created"]
    report = services.scaffold_synthesis(pid, store=store)
    assert report["lead"] and "Auto-seeded outline" not in report["lead"]
    f = services.assess_project(pid, store=store)["finish"]
    assert f["organized"] is True and f["handed_off"] is True
    # idempotent: re-deriving doesn't duplicate
    n1 = len(services.list_sections(pid, store=store))
    services.derive_sections(pid, store=store)
    assert len(services.list_sections(pid, store=store)) == n1
    assert services.scaffold_synthesis(pid, store=store)["id"]  # returns existing, no error

    # Existing ESV reports from before the copy fix are repaired in place; customer-authored
    # leads keep winning and graph/run references remain stable.
    legacy = store.get_synthesis(report["id"])
    legacy["lead"] = "Auto-seeded outline for ESV1."
    store.upsert_synthesis(legacy)
    repaired = services.scaffold_synthesis(pid, store=store)
    assert repaired["id"] == report["id"] and "Auto-seeded outline" not in repaired["lead"]
    repaired["lead"] = "Authored customer lead."
    store.upsert_synthesis(repaired)
    assert services.scaffold_synthesis(pid, store=store)["lead"] == "Authored customer lead."


def test_notes_are_one_entity_built_notes_carry_prototype(store):
    """ONE note entity (concepts merged in): every note is note_kind='note' (no 'concept' kind), and a
    note that was BUILT carries data.prototype_ids so the graph/outline pairs it with its prototype(s) —
    a concept can become several fidelity versions, so the node exposes a LIST (single input is lifted)."""
    proj = services.start_project("CN", "hmw?", "double_diamond_deep", persona_ids=["p1"], store=store)
    pid = proj["id"]
    services.create_note(pid, "a bold idea built twice", "Dark-horse",
                         data={"lens": "reversal", "prototype_ids": ["proto_x", "proto_y"]}, store=store)
    services.create_note(pid, "a single-build idea", "Single",
                         data={"prototype_id": "proto_z"}, store=store)              # single input still works
    services.create_note(pid, "a raw observation", "Obs", store=store)
    g = services.get_project_graph(pid, store=store)
    note_nodes = [n for n in g["nodes"] if str(n["study_id"]).startswith("note:")]
    assert len(note_nodes) == 3 and all(n.get("note_kind") == "note" for n in note_nodes)  # no concept kind
    assert all(n["href"].startswith("/notes/") for n in note_nodes)                          # one list/route
    multi = next(n for n in note_nodes if len(n.get("prototype_ids") or []) == 2)
    assert multi["prototype_ids"] == ["proto_x", "proto_y"]                                   # concept → versions
    assert any(n.get("prototype_ids") == ["proto_z"] for n in note_nodes)                     # single lifted to list


def test_project_graph_request_cache_reuses_computed_graph_and_isolates_callers(store, monkeypatch):
    from sonaloop.services import _research

    pid = services.start_project("Cached graph", "hmw?", store=store)["id"]
    calls = 0
    original = _research.plan_graph

    def counted(project_id, store=None):
        nonlocal calls
        calls += 1
        return original(project_id, store=store)

    monkeypatch.setattr(_research, "plan_graph", counted)
    token = _research.begin_project_graph_cache()
    try:
        first = services.get_project_graph(pid, store=store)
        first["nodes"].append({"study_id": "mutated", "kind": "note"})
        second = services.get_project_graph(pid, store=store)
    finally:
        _research.end_project_graph_cache(token)

    assert calls == 1
    assert "mutated" not in {n.get("study_id") for n in second["nodes"]}

    services.get_project_graph(pid, store=store)
    assert calls == 2


def test_council_modes_discovery_evaluation_decision(store):
    """Q1/Q2: a council's shape is DERIVED — discovery (open `questions`, no proposal/votes),
    evaluation (a proposal reacted to), decision (proposal + votes). `questions` is stored first-class."""
    pid = services.start_project("M", "hmw?", None, persona_ids=[], store=store)["id"]
    disc = services.record_council(pid, "Geldgewohnheiten", [], [{"persona_id": "p1", "text": "Ich spare per ETF"}],
                                   questions=["Wie sparst du gerade?", "Welche Versicherungen hast du?"],
                                   store=store, key="d")
    assert disc["questions"] == ["Wie sparst du gerade?", "Welche Versicherungen hast du?"]
    assert services.council_mode(disc) == "discovery"
    dec = services.record_council(pid, "Bauen?", [], [{"persona_id": "p1", "text": "ja"}], proposal="Wir bauen X",
                                  votes=[{"vote": "SUPPORT"}], store=store, key="x")
    assert services.council_mode(dec) == "decision"
    ev = services.record_council(pid, "Reaktion", [], [{"persona_id": "p1", "text": "gut"}], proposal="Das Konzept",
                                 store=store, key="e")
    assert services.council_mode(ev) == "evaluation"


def test_plan_graph_absorbs_unplanned_project_evidence(store):
    """Remote MCP hosts record councils/syntheses OUTSIDE the governed loop (no run_step/
    checkpoint_step ever ran) — the project still owns that evidence, so the graph, the
    outline and every derived count must show it instead of silently dropping it."""
    pid = services.start_project("Remote study", "what lands?", store=store)["id"]
    council = services.record_council(pid, "what would make you notice?", [],
                                      [{"persona_id": "p1", "text": "a trigger event"}],
                                      store=store, key="rc")
    syn = services.record_synthesis("Awareness report", "arc",
                                    council_ids=[council["id"]], store=store)

    g = services.get_project_graph(pid, store=store)
    nodes = {n["study_id"]: n for n in g["nodes"]}
    assert f'council:{council["id"]}' in nodes
    assert f'synthesis:{syn["id"]}' in nodes        # cites only owned councils → absorbed
    # absorbed evidence sits in a REAL phase (the frame active at creation) — phase-less
    # rows are dropped by the outline, which is exactly the bug this guards against
    assert nodes[f'council:{council["id"]}']["phase"]
    assert nodes[f'synthesis:{syn["id"]}']["phase"]
    assert {"from_study": f'council:{council["id"]}', "to_study": f'synthesis:{syn["id"]}',
            "type": "refines", "rationale": ""} in g["edges"]
    listed = next(p for p in services.list_research_projects(store=store) if p["id"] == pid)
    assert listed["councils"] == 1 and listed["studies"] == 1


def test_synthesis_absorption_does_not_leak_across_projects(store):
    """A synthesis citing ANOTHER project's councils (or nothing at all) stays off this
    project's graph; project-scope reports keep riding _attach_reports, never the node list."""
    pid_a = services.start_project("A", "?", store=store)["id"]
    pid_b = services.start_project("B", "?", store=store)["id"]
    ca = services.record_council(pid_a, "Q-A", [], [{"persona_id": "p1", "text": "x"}],
                                 store=store, key="ca")
    services.record_synthesis("Cites A", "arc", council_ids=[ca["id"]], store=store)
    services.record_synthesis("Cites nothing", "arc", store=store)

    gb = services.get_project_graph(pid_b, store=store)
    assert not any(n["kind"] == "synthesis" for n in gb["nodes"])
    assert not any(n["kind"] == "council" for n in gb["nodes"])


def test_record_synthesis_project_id_links_and_validates(store):
    pid = services.start_project("Linked", "goal?", store=store)["id"]
    syn = services.record_synthesis("Standalone", "arc", project_id=pid, store=store)
    assert syn["project_id"] == pid
    g = services.get_project_graph(pid, store=store)
    assert f'synthesis:{syn["id"]}' in {n["study_id"] for n in g["nodes"]}
    # update in place keeps the link when project_id is omitted
    again = services.record_synthesis("Standalone v2", "arc", synthesis_id=syn["id"], store=store)
    assert again["project_id"] == pid
    with pytest.raises(KeyError):
        services.record_synthesis("Bad", "arc", project_id="rproject_missing", store=store)


def test_citing_synthesis_resolves_its_owning_project(store):
    """The claude.ai session's exact deliverable gap: the synthesis carried no project_id
    (the old tool had no such param), so its PPTX export attached nowhere ('0 files').
    owning_project_of_synthesis applies the absorption rule — declared project_id first,
    else citing only one project's owned councils is ownership enough. The breadcrumb
    resolver (parent_project_of_synthesis) stays strict so a citing synthesis's DETAIL
    page keeps library-rooted (round-5 council/synthesis page contract)."""
    pid = services.start_project("Own", "?", store=store)["id"]
    c = services.record_council(pid, "Q", [], [{"persona_id": "p1", "text": "x"}],
                                store=store, key="own-c")
    syn = services.record_synthesis("Report", "arc", council_ids=[c["id"]], store=store)
    assert services.owning_project_of_synthesis(syn["id"], store=store)["id"] == pid
    assert services.parent_project_of_synthesis(syn["id"], store=store) is None  # breadcrumb stays strict
    declared = services.record_synthesis("Declared", "arc", project_id=pid, store=store)
    assert services.parent_project_of_synthesis(declared["id"], store=store)["id"] == pid
    assert services.owning_project_of_synthesis(declared["id"], store=store)["id"] == pid
