"""Item 1 (part B): an end-to-end gather→author→write-back round-trip through the
service layer the MCP tools wrap — persona → council → synthesis (with evidence
provenance + citations) → evidence check → cohort critic. No network; the host
authoring steps are supplied inline as JSON, exactly as an MCP host would."""
from __future__ import annotations

from sonaloop import services
from conftest import create_persona


def test_full_round_trip(store):
    # --- persona create (host-authored profile) ---
    a = create_persona(store, "Alpha")
    b = create_persona(store, "Beta", customer_type="Property developer", title="Acquisitions",
                       pains=["deal risk", "owners stall"], goals=["close deals"], tools=["Excel", "Phone"])
    personas = {p["id"] for p in services.list_personas(store=store)}
    assert {a, b} <= personas

    # --- attached evidence feeds provenance later ---
    services.attach_evidence(a, "interview", "Customer confirmed pain alpha costs ~2h/week.",
                             notes="interview-01", store=store)

    # --- council: a council is scoped to a research project (personas are global) ---
    project = services.create_research_project("Diff view study", goal="value of a diff view",
                                               persona_ids=[a, b], store=store)
    pid = project["id"]
    # gather then host-authored write-back
    gathered = services.brief_council(pid, "Would a diff/freigabe view help?", [a, b], store=store)
    assert "instructions" in gathered and gathered["project_id"] == pid
    assert "PERSONA VOICE BOUNDARY" in gathered["instructions"]
    assert all("PERSONA VOICE BOUNDARY" in p["agent_context"]
               for p in gathered["participants"])
    statements = [
        {"persona_id": a, "text": "Could help, but only with provenance.", "stance": {"value": 1}},
        {"persona_id": b, "text": "I want a range, not a model.", "stance": {"value": 1}},
    ]
    votes = [{"persona_id": a, "persona_name": "Alpha", "vote": "MAYBE"},
             {"persona_id": b, "persona_name": "Beta", "vote": "MAYBE"}]
    council = services.record_council(pid, "Would a diff/freigabe view help?", [a, b], statements, votes=votes,
                                      summary="conditional", store=store)
    cid = council["id"]
    assert council["project_id"] == pid
    # the council is owned by the project directly (even before a synthesis cites it)
    assert cid in services.get_research_project(pid, store=store)["council_ids"]

    # --- synthesis: gather surfaces provenance (attached evidence), then author ---
    brief = services.brief_synthesis([cid], title="Diff view", start_input="seed", goal="value of a diff view", store=store)
    assert "provenance" in brief["frame"]
    ev_refs = [e["ref"] for e in brief["frame"]["provenance"]["evidence"]]
    assert ev_refs, "attached evidence should be surfaced as citable provenance"

    payload = {
        "arc_narrative": "one council, conditional interest",
        "gesamtbild": "diff view is conditionally valuable",
        "positionierung": "a traceable diff",
        "findings": [
            {"text": "build the diff view", "kind": "recommendation", "score": {"effort": 4, "value": 5}},
            {"text": "who-computes-on-stale", "kind": "pain_solver"},
            {"text": "coordination", "kind": "segment", "meta": {"detail": "daily pain", "stance": {"value": 1}}},
            {"text": "integration?", "kind": "open_question"},
        ],
        "statements": [{"persona_id": a, "text": "needs provenance", "stance": {"value": 1}, "relevance": "stark",
                        "refs": [{"kind": "council", "id": cid, "role": "derived_from"}]}],
        "references": [{"council_id": cid, "role": "seed council"}],
        "citations": [{"kind": "evidence", "ref": ev_refs[0], "quote": "costs ~2h/week"},
                      {"kind": "council", "ref": cid, "quote": "only with provenance"}],
        "status": "done", "stop_reason": "goal reached",
    }
    syn = services.record_synthesis("Diff view", "seed", [cid], payload, goal="value of a diff view", store=store)
    assert syn["citations"] and syn["citations"][0]["ref"] == ev_refs[0]

    # citations surface in the rendered report
    md = services.export_synthesis(syn["id"], "md", store=store)
    assert "Citations" in md and ev_refs[0] in md

    # --- evidence check: gather then author ---
    evb = services.brief_evidence_check(a, store=store)
    assert evb["evidence_count"] >= 1
    evr = services.record_evidence_check(a, {"confirmed": ["pain alpha"], "contradicted": [],
                                             "unsupported": [], "notes": "ok"}, store=store)
    assert evr["green"] is True

    # --- cohort critic: gather then author (no outliers) ---
    cb = services.brief_cohort_critic(store=store)
    assert cb["cohort_size"] == 2 and "instructions" in cb
    cr = services.record_cohort_critic({"outliers": [], "cohort_note": "balanced"}, store=store)
    assert cr["green"] is True
    # an outlier verdict persists an anomaly against that persona
    cr2 = services.record_cohort_critic(
        {"outliers": [{"persona_id": b, "dimension": "distinctiveness", "severity": 4, "reason": "thin"}],
         "cohort_note": "one outlier"}, store=store)
    assert cr2["green"] is False
    anomalies = store.list_anomalies(b)
    assert any(x["kind"].startswith("cohort_critic") for x in anomalies)
