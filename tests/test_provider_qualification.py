"""Held-out provider qualification: real Core execution, no provider/network calls."""
from __future__ import annotations

import copy
import json

import pytest

from sonaloop import cli
from sonaloop.qualification import (
    FIXED_THRESHOLDS,
    REVIEW_DIMENSIONS,
    REVIEW_SCHEMA,
    SUBMISSION_SCHEMA,
    QualificationError,
    list_qualification_fixtures,
    load_qualification_fixture,
    qualification_contract,
    run_provider_qualification,
)


class StaticAdapter:
    def __init__(self, mutate=None, *, external: bool = False, review: bool = True):
        self.mutate = mutate
        self.external = external
        self.review = review

    def run_case(self, contract):
        fixture = load_qualification_fixture(contract["fixture_id"])
        operations = {
            row["event_id"]: f"fixture-intent:{row['logical_request_id']}"
            for row in contract["chronology"]
        }
        run_operations = {
            row["event_id"]: f"fixture-run-intent:{row['logical_request_id']}"
            for row in contract["chronology"]
        }
        expected_statuses = fixture["expected"]["initial_capability_statuses"]
        body = (
            "This synthetic result is bounded to the admitted stimulus and does not claim observed "
            "behavior or product approval. A skeptical voice asks for independent evidence, while "
            "an indifferent voice reports no relevance to an ordinary task. " * 4
        )
        surface = ({
            "kind": "external_mcp",
            "visibility": {"tool_boundary": "observed", "host_turns": "unavailable_external_host",
                           "generation": "unavailable_external_host"},
        } if self.external else {
            "kind": "hosted",
            "visibility": {"tool_boundary": "observed", "host_turns": "observed",
                           "generation": "observed"},
        })
        metrics = ({"latency_ms": 25, "input_tokens": None, "output_tokens": None, "cost_usd": None}
                   if self.external else
                   {"latency_ms": 25, "input_tokens": 120, "output_tokens": 80, "cost_usd": 0.01})
        submission = {
            "schema": SUBMISSION_SCHEMA,
            "fixture_id": contract["fixture_id"],
            "fixture_revision": contract["fixture_revision"],
            "contract_digest": contract["contract_digest"],
            "provider": {"name": "offline-fixture", "model": "recorded-reference",
                         "version": "2026-08-08", "adapter_version": "v1",
                         "run_at": "2026-08-08T12:00:00Z"},
            "surface": surface,
            "metrics": metrics,
            "protocol": {
                "methodology": "Reaction Test",
                "operation_ids": operations,
                "run_operation_ids": run_operations,
                "use_dispatch_tokens": True,
                "include_evidence_refs": True,
                "link_gate_evidence": True,
                "manual_finish_before_done": False,
                "explicit_claim_inventory": True,
                "cohort_strategy": "reselect_independent",
                "capability_statuses": copy.deepcopy(expected_statuses),
                "correction_status": "observed_present",
                "voices": [
                    {"voice_id": "skeptical-context", "stance": "skeptical",
                     "text": "I need independent evidence before I would rely on this."},
                    {"voice_id": "ordinary-nontarget", "stance": "indifferent",
                     "text": "This does not change my ordinary task."},
                ],
                "claim_posture": "simulated",
                "synthesis_claim_posture": "inferred",
                "critic_passes": 2,
                "report": {"arc_narrative": body, "gesamtbild": body,
                           "positionierung": body,
                           "claim": "The synthetic councils support only a bounded inferred contrast."},
            },
        }
        if self.review:
            submission["review"] = {
                "schema": REVIEW_SCHEMA,
                "evaluator": {"kind": "human", "id": "fixture-reviewer", "version": "rubric-v1"},
                "calibrated": True,
                "reviewed_at": "2026-08-08T12:30:00Z",
                "scores": {key: 5 for key in REVIEW_DIMENSIONS},
            }
        if self.mutate:
            self.mutate(submission, contract)
        return submission


def _check(result, name):
    return next(row for row in result["checks"] if row["name"] == name)


def test_fixtures_are_versioned_private_and_adapter_contract_hides_answers():
    rows = list_qualification_fixtures()
    assert {row["fixture_id"] for row in rows} == {
        "shkb-retry-chronology-v1", "fink-false-absence-circular-persona-v1"}
    for row in rows:
        assert row["privacy"] == {
            "classification": "synthetic",
            "contains_customer_authored_text": False,
            "contains_production_identifiers": False,
            "provenance": row["privacy"]["provenance"],
        }
        contract = qualification_contract(row["fixture_id"])
        assert contract["schema"].endswith("context.v1")
        assert len(contract["contract_digest"]) == 64
        assert "expected" not in contract and "correction" not in contract
        assert all("expected_initial_status" not in capability
                   for capability in contract["task"]["capabilities"])
        assert {tool["name"] for tool in contract["tools"]} >= {
            "start_project", "run_step", "record_product_understanding",
            "record_cohort_preflight", "record_council", "record_synthesis",
            "record_critic_round"}
        assert "add_task" not in {tool["name"] for tool in contract["tools"]}
        assert contract["fixed_thresholds"] == FIXED_THRESHOLDS


def test_offline_reference_passes_every_core_contract_and_review(monkeypatch):
    # Any accidental provider/network call fails the test. SQLite/file writes do not use sockets.
    import socket
    monkeypatch.setattr(socket.socket, "connect", lambda *_a, **_k: (_ for _ in ()).throw(
        AssertionError("qualification CI must not call the network")))

    report = run_provider_qualification([StaticAdapter()])
    assert report["summary"] == {"qualified": 2, "review_required": 0, "failed": 0, "total": 2}
    assert report["fixed_thresholds"] == FIXED_THRESHOLDS
    assert len({result["contract_digest"] for result in report["results"]}) == 2
    for result in report["results"]:
        assert result["qualified"] is True and result["deterministic_score"] == 1.0
        assert result["combined_score"] == 1.0
        assert all(row["passed"] for row in result["checks"])
        assert result["routing"]["contract_gates_relaxed"] is False
    shkb = next(row for row in report["results"] if row["fixture_id"].startswith("shkb"))
    assert _check(shkb, "duplicate_suppression")["detail"] == {
        "logical_jobs": 2, "projects": 2, "runs": 2, "chronology_events": 5}
    assert shkb["metrics"]["retries"] == 3


def test_hard_contract_can_pass_but_never_self_qualifies_without_review():
    report = run_provider_qualification(
        [StaticAdapter(review=False)], ["shkb-retry-chronology-v1"])
    result = report["results"][0]
    assert result["contract_passed"] is True and result["status"] == "review_required"
    assert result["qualified"] is False and result["combined_score"] is None


def test_attempt_scoped_retry_ids_reproduce_multiplication_and_fail_fixed_gate():
    def break_ids(submission, contract):
        submission["protocol"]["operation_ids"] = {
            row["event_id"]: f"attempt:{row['event_id']}" for row in contract["chronology"]}
        submission["protocol"]["run_operation_ids"] = {
            row["event_id"]: f"run-attempt:{row['event_id']}" for row in contract["chronology"]}

    result = run_provider_qualification(
        [StaticAdapter(break_ids)], ["shkb-retry-chronology-v1"])["results"][0]
    duplicate = _check(result, "duplicate_suppression")
    assert duplicate["passed"] is False
    assert duplicate["detail"]["projects"] == duplicate["detail"]["runs"] == 5
    assert result["status"] == "failed_contract" and result["routing"]["contract_gates_relaxed"] is False


def test_false_absence_is_rejected_by_real_product_understanding_guardrail():
    def false_absence(submission, _contract):
        submission["protocol"]["capability_statuses"]["completion-control"] = "observed_absent"
        submission["protocol"].pop("absence_verification_attempt", None)

    result = run_provider_qualification(
        [StaticAdapter(false_absence)],
        ["fink-false-absence-circular-persona-v1"])["results"][0]
    assert _check(result, "product_understanding_stimulus")["passed"] is False
    assert _check(result, "app_inventory_falsification")["passed"] is False
    errors = _check(result, "state_machine_compliance")["detail"]["errors"]
    assert {row["code"] for row in errors} >= {"ABSENCE_VERIFICATION_REQUIRED"}


def test_missing_critic_and_ordinary_countervoices_fail_independent_checks():
    def weaken(submission, _contract):
        submission["protocol"]["critic_passes"] = 1
        submission["protocol"]["voices"] = [
            {"voice_id": "product-shaped", "stance": "supportive",
             "text": "The seeded problem sounds correct."}]

    result = run_provider_qualification(
        [StaticAdapter(weaken)], ["fink-false-absence-circular-persona-v1"])["results"][0]
    assert _check(result, "critic_completion")["passed"] is False
    assert _check(result, "skeptical_indifferent_output")["passed"] is False
    assert result["qualified"] is False


def test_circular_cohort_override_remains_a_hard_provider_failure():
    def override_instead_of_reselecting(submission, _contract):
        submission["protocol"]["cohort_strategy"] = "override_circular"

    result = run_provider_qualification(
        [StaticAdapter(override_instead_of_reselecting)],
        ["fink-false-absence-circular-persona-v1"])["results"][0]
    gate = _check(result, "cohort_integrity")
    assert gate["passed"] is False
    assert gate["detail"]["projects"][0]["current_status"] == "overridden"
    assert result["status"] == "failed_contract"


def test_external_mcp_declares_blind_spots_and_cannot_fabricate_generation_metrics():
    report = run_provider_qualification(
        [StaticAdapter(external=True, review=False)], ["shkb-retry-chronology-v1"])
    result = report["results"][0]
    assert result["status"] == "review_required"
    assert "generation tokens and cost" in result["blind_spots"]
    assert result["metrics"]["input_tokens"] is None

    def fabricate(submission, _contract):
        submission["metrics"]["input_tokens"] = 99

    with pytest.raises(QualificationError) as exc:
        run_provider_qualification(
            [StaticAdapter(fabricate, external=True)], ["shkb-retry-chronology-v1"])
    assert exc.value.code == "FABRICATED_EXTERNAL_METRIC"


def test_contract_digest_tamper_fails_before_any_core_write():
    def tamper(submission, _contract):
        submission["contract_digest"] = "0" * 64

    with pytest.raises(QualificationError) as exc:
        run_provider_qualification([StaticAdapter(tamper)], ["shkb-retry-chronology-v1"])
    assert exc.value.code == "CONTRACT_DIGEST_MISMATCH"


def test_cli_surfaces_fixture_and_contract_json(capsys):
    assert cli.main(["qualification-fixtures"]) == 0
    listed = json.loads(capsys.readouterr().out)
    assert len(listed["fixtures"]) == 2
    assert cli.main(["qualification-contract", "--fixture", "shkb-retry-chronology-v1"]) == 0
    contract = json.loads(capsys.readouterr().out)["contracts"][0]
    assert contract["fixture_id"] == "shkb-retry-chronology-v1"
    assert contract["budget"] == {"max_run_steps": 24, "max_critic_rounds": 4,
                                  "max_tool_calls": 80}
