"""Result schemas: domain-neutral output contracts for Jobs and methodologies."""
from __future__ import annotations

import asyncio

from sonaloop import job_taxonomy as T
from sonaloop import methodology as M
from sonaloop import result_outcomes as O
from sonaloop import result_schemas as R
from sonaloop import services


def test_result_schema_registry_is_valid(store):
    assert R.registry_errors(store=store) == []
    ids = {s["id"] for s in R.schemas()}
    assert {
        "stimulus_reaction.v1",
        "ordered_ladder_sensitivity.v1",
        "option_comparison.v1",
        "threshold_gate.v1",
        "study_handoff.v1",
    } <= ids
    assert "price_sensitivity.v1" not in ids
    assert "blog_sentiment.v1" not in ids


def test_every_job_and_methodology_has_result_contract(store):
    assert {c["job_id"] for c in R.job_contracts()} == {j["id"] for j in T.jobs()}
    assert {c["methodology_key"] for c in R.methodology_contracts()} == {
        m["key"] for m in M.list_methodologies(store=store)
    }
    for contract in R.job_contracts() + R.methodology_contracts():
        assert contract["result_schemas"]
        for ref in contract["result_schemas"]:
            assert R.get_schema(ref["id"])["summary"]
            assert ref["role"]


def test_domain_jobs_map_to_neutral_result_schemas():
    pricing = R.contract_for_job("pricing")
    assert pricing["result_schemas"][0]["id"] == "ordered_ladder_sensitivity.v1"
    assert all("price_sensitivity" not in ref["id"] for ref in pricing["result_schemas"])

    reaction = R.contract_for_job("content_reaction")
    assert [ref["id"] for ref in reaction["result_schemas"][:2]] == [
        "stimulus_reaction.v1",
        "threshold_gate.v1",
    ]
    assert reaction["automation_gate"] == {
        "schema": "threshold_gate.v1",
        "metric": "sentiment_score",
        "operator": ">=",
        "threshold": 0.5,
    }


def test_methodology_schema_relationship_is_many_to_many():
    reaction = {ref["id"] for ref in R.contract_for_methodology("reaction_test")["result_schemas"]}
    assert reaction == {"stimulus_reaction.v1", "threshold_gate.v1"}

    double_diamond = {ref["id"] for ref in R.contract_for_methodology("double_diamond")["result_schemas"]}
    assert {"opportunity_map.v1", "concept_validation.v1", "study_handoff.v1"} <= double_diamond

    usage: dict[str, int] = {}
    for contract in R.methodology_contracts():
        for ref in contract["result_schemas"]:
            usage[ref["id"]] = usage.get(ref["id"], 0) + 1
    assert usage["concept_validation.v1"] > 1
    assert usage["option_comparison.v1"] > 1


def test_job_presets_expose_result_contracts(store):
    from sonaloop import job_presets as P

    preset = P.get_job_preset("content_reaction", store)
    assert preset["result_contract"]["job_id"] == "content_reaction"
    assert preset["result_contract"]["result_schemas"][0]["id"] == "stimulus_reaction.v1"

    listed = services.list_job_presets(store=store)["presets"]
    assert all(p["result_contract"]["result_schemas"] for p in listed)


def test_result_schema_services_and_cli_are_wired(store):
    assert services.list_result_schemas(store=store)["registry_errors"] == []
    assert services.get_result_schema("stimulus_reaction.v1")["result_kind"] == "score_plus_themes"
    assert services.result_contract_for_methodology("reaction_test")["result_schemas"][0]["id"] == \
        "stimulus_reaction.v1"

    from sonaloop.cli import build_parser

    assert build_parser().parse_args(["result-schema-list"]).command == "result-schema-list"
    assert build_parser().parse_args(["result-contract-job", "pricing"]).job_id == "pricing"


def test_result_schema_mcp_tools_registered():
    from sonaloop.mcp_server import build_server

    names = {t.name for t in asyncio.run(build_server().list_tools())}
    assert {
        "list_result_schemas",
        "get_result_schema",
        "list_result_contracts",
        "result_contract_for_job",
        "result_contract_for_methodology",
        "set_project_result_schemas",
        "record_job_outcome",
        "project_result_contract_state",
    } <= names


def test_methodologies_page_surfaces_result_schemas(store):
    from sonaloop.web.pages import methodologies as page

    html = str(page._methodologies_page(result_schema="stimulus_reaction.v1"))
    assert "Result schemas" in html
    assert "Stimulus Reaction" in html

    detail = str(page._methodology_detail("reaction-test"))
    assert "stimulus_reaction.v1" in detail
    assert "Threshold Gate" in detail
    assert "Expected fields" in detail
    assert "sentiment_score" in detail
    assert "Derived metrics" in detail
    assert "Done criteria" in detail


def _record_reaction_outcome_fixture(store):
    project = services.start_project("Reaction fixture", "Should this message launch?", store=store)
    pid = project["id"]
    services.set_project_result_schemas(pid, [
        {"id": "stimulus_reaction.v1", "role": "primary"},
        {"id": "threshold_gate.v1", "role": "gate"},
    ], source="test", store=store)
    c1 = services.record_council(pid, "React to the message", ["persona_a", "persona_b"],
                                 statements=[
                                     {"persona_id": "persona_a", "text": "Clear enough.",
                                      "stance": {"value": 1}},
                                     {"persona_id": "persona_b", "text": "It needs proof.",
                                      "stance": {"value": 0}},
                                 ], store=store)
    c2 = services.record_council(pid, "Diagnose confusion", ["persona_a", "persona_b"],
                                 statements=[
                                     {"persona_id": "persona_a", "text": "The claim is too broad.",
                                      "stance": {"value": -1}},
                                 ], store=store)
    syn = services.record_synthesis(
        "Reaction outcome", "Draft message", [c1["id"], c2["id"]],
        {"gesamtbild": "The message is close but needs proof.",
         "findings": [
             {"kind": "metric", "text": "sentiment 0.58", "score": 0.58,
              "meta": {"schema": "stimulus_reaction.v1", "field": "sentiment_score",
                       "observed_value": 0.58}},
             {"kind": "metric", "text": "comprehension 0.71", "score": 0.71,
              "meta": {"schema": "stimulus_reaction.v1", "field": "comprehension_score",
                       "observed_value": 0.71}},
             {"kind": "key_problem", "text": "The main claim needs earlier proof.",
              "meta": {"schema": "stimulus_reaction.v1", "field": "confusion_points"}},
             {"kind": "recommendation", "text": "Add a proof point before the comparison.",
              "score": 0.8,
              "meta": {"schema": "stimulus_reaction.v1", "field": "revision_recommendations"}},
             {"kind": "decision", "text": "Gate passes.",
              "meta": {"schema": "threshold_gate.v1", "metric": "sentiment_score",
                       "observed_value": 0.58, "operator": ">", "threshold": 0.5,
                       "verdict": "pass",
                       "evidence_refs": [{"kind": "council", "id": c1["id"]}]}},
         ]},
        store=store)
    assert syn.get("project_id", "") == ""
    reaction = services.record_job_outcome(
        pid,
        "stimulus_reaction.v1",
        {
            "stimulus_ref": "Draft message",
            "cohort_summary": {"participants": 2, "personas": ["persona_a", "persona_b"], "councils": 2},
            "sentiment_score": 0.58,
            "comprehension_score": 0.71,
            "confusion_points": ["The main claim needs earlier proof."],
            "revision_recommendations": ["Add a proof point before the comparison."],
        },
        evidence_refs=[{"kind": "council", "id": c1["id"]}, {"kind": "synthesis", "id": syn["id"]}],
        store=store,
    )
    gate = services.record_job_outcome(
        pid,
        "threshold_gate.v1",
        {
            "metric": "sentiment_score",
            "observed_value": 0.58,
            "operator": ">",
            "threshold": 0.5,
            "verdict": "pass",
            "evidence_refs": [{"kind": "council", "id": c1["id"]}],
        },
        evidence_refs=[{"kind": "council", "id": c1["id"]}],
        store=store,
    )
    assert reaction["id"].startswith("joboutcome_") and gate["id"].startswith("joboutcome_")
    return pid, syn


def test_project_schema_outcomes_are_project_owned_not_synthesis_derived(store):
    pid, syn = _record_reaction_outcome_fixture(store)
    outcomes = O.project_schema_outcomes(store, pid)
    by_schema = {o["schema_id"]: o for o in outcomes}
    assert {"stimulus_reaction.v1", "threshold_gate.v1"} <= set(by_schema)
    assert by_schema["stimulus_reaction.v1"]["source"]["kind"] == "job_completion"
    assert by_schema["stimulus_reaction.v1"]["evidence_refs"][1] == {"kind": "synthesis", "id": syn["id"]}
    assert by_schema["stimulus_reaction.v1"]["result"]["sentiment_score"] == 0.58
    assert by_schema["threshold_gate.v1"]["result"]["verdict"] == "pass"


def test_project_page_renders_job_outcome_not_synthesis_schema_section(store):
    from starlette.testclient import TestClient
    from sonaloop import web
    from sonaloop.web._synthesis import _synthesis_html

    pid, syn = _record_reaction_outcome_fixture(store)
    client = TestClient(web.create_app())
    html = client.get(f"/jobs/{pid}?lang=en").text
    assert "Job outcome" in html
    assert "Stimulus Reaction" in html
    assert "Threshold Gate" in html
    assert 'data-rkind="job_outcome"' in html
    outcome = O.get_project_schema_outcome(store, pid, "stimulus_reaction.v1")
    assert outcome
    assert f'/jobs/{pid}/outcomes/{outcome["id"]}' in html

    detail = client.get(f'/jobs/{pid}/outcomes/{outcome["id"]}?slide=1&lang=en').text
    assert "Stimulus Reaction" in detail
    assert "Score plus themes" in detail
    assert "sentiment_score" in detail
    assert "0.58" in detail

    report_html, _ = _synthesis_html(store, syn)
    assert "Schema outcome" not in report_html


def test_project_completion_waits_for_expected_job_outcomes(store):
    project = services.start_project("Outcome gated", "Question?", store=store)
    pid = project["id"]
    services.set_project_result_schemas(pid, ["stimulus_reaction.v1"], source="test", store=store)
    services.record_frame(pid, "frame__root", ["q?"], memory_refs=["m"], store=store)

    a = services.assess_project(pid, store=store)
    assert a["tasks_complete"] is True
    assert a["complete"] is False
    assert a["recommendation"] == "finish"
    assert a["result_contract"]["missing"][0]["id"] == "stimulus_reaction.v1"
    missing = services.project_run_state(pid, store=store)
    assert missing["state"] == "unverified"
    assert missing["engine_finished"] is False

    services.record_job_outcome(pid, "stimulus_reaction.v1", {
        "stimulus_ref": "Draft",
        "cohort_summary": {"participants": 1},
        "sentiment_score": 0.6,
        "confusion_points": ["none"],
    }, evidence_refs=[{"kind": "council", "id": "c1"}], store=store)
    assert services.assess_project(pid, store=store)["complete"] is True
    completed = services.project_run_state(pid, store=store)
    assert completed["state"] == "unverified"
    assert completed["engine_finished"] is False
