"""Provider-neutral, privacy-safe qualification over the real Core contracts.

The harness deliberately does not judge a provider from prose-shaped promises.
An adapter returns a versioned submission, the harness executes those decisions
through the public Sonaloop service functions, and the scorer reads the records
that Core actually persisted.  Evidence/completion gates are hard booleans;
human or calibrated-judge review can reject an otherwise valid run but can never
compensate for a failed contract.

No provider SDK is imported here.  CI uses recorded adapters and therefore makes
no live API calls.  A hosted integration can implement ``QualificationAdapter``
outside this package and receives the same immutable contract as every other
provider.
"""
from __future__ import annotations

import copy
import hashlib
import inspect
import json
from pathlib import Path
from typing import Any, Protocol

from . import services
from .config import utc_now_iso


FIXTURE_SCHEMA = "sonaloop.provider_qualification.fixture.v1"
SUBMISSION_SCHEMA = "sonaloop.provider_qualification.submission.v1"
CASE_RESULT_SCHEMA = "sonaloop.provider_qualification.case_result.v1"
REPORT_SCHEMA = "sonaloop.provider_qualification.report.v1"
REVIEW_SCHEMA = "sonaloop.provider_qualification.review.v1"
HARNESS_VERSION = "2026-08-08.1"
CONTEXT_VERSION = "sonaloop.provider_qualification.context.v1"

HARD_CHECKS = (
    "methodology_resolution",
    "duplicate_suppression",
    "state_machine_compliance",
    "product_understanding_stimulus",
    "cohort_integrity",
    "app_inventory_falsification",
    "claim_posture",
    "trace_linking",
    "critic_completion",
    "skeptical_indifferent_output",
)
FIXED_THRESHOLDS = {
    "contract_check_min": 1.0,
    "all_contract_checks_required": True,
    "review_dimension_min_0_to_5": 4,
    "all_review_dimensions_required": True,
    "required_distinct_critic_passes": 2,
}
REVIEW_DIMENSIONS = (
    "semantic_stance_fidelity",
    "product_inventory_accuracy",
    "circularity_resistance",
    "evidence_use",
)

_FIXTURE_DIR = Path(__file__).with_name("qualification_fixtures")
_TOOL_NAMES = (
    "start_project",
    "start_run",
    "run_step",
    "attach_asset",
    "record_product_understanding",
    "record_cohort_preflight",
    "record_frame",
    "record_council",
    "record_judgment",
    "record_synthesis",
    "record_completeness_critic",
    "record_critic_round",
    "run_journal",
)


class QualificationError(ValueError):
    """A stable, fail-closed fixture/submission contract error."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


class QualificationAdapter(Protocol):
    """Provider adapter seam; implementations receive no scorer expectations."""

    def run_case(self, contract: dict[str, Any]) -> dict[str, Any]: ...


class RecordedQualificationAdapter:
    """Offline adapter backed by already captured, versioned submissions."""

    def __init__(self, submissions: list[dict[str, Any]] | dict[str, Any]) -> None:
        if isinstance(submissions, dict) and "submissions" in submissions:
            submissions = submissions["submissions"]
        if isinstance(submissions, dict):
            submissions = [submissions]
        self._by_fixture = {
            str(row.get("fixture_id") or ""): copy.deepcopy(row)
            for row in (submissions or []) if isinstance(row, dict)
        }

    @classmethod
    def from_path(cls, path: str | Path) -> "RecordedQualificationAdapter":
        return cls(json.loads(Path(path).read_text(encoding="utf-8")))

    def run_case(self, contract: dict[str, Any]) -> dict[str, Any]:
        fixture_id = str(contract.get("fixture_id") or "")
        if fixture_id not in self._by_fixture:
            raise QualificationError(
                "MISSING_FIXTURE_SUBMISSION",
                f"recorded adapter has no submission for {fixture_id!r}",
            )
        return copy.deepcopy(self._by_fixture[fixture_id])


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _opaque(kind: str, raw: str) -> str:
    return f"{kind}_{hashlib.sha256((kind + '|' + raw).encode()).hexdigest()[:16]}"


def list_qualification_fixtures() -> list[dict[str, Any]]:
    out = []
    for path in sorted(_FIXTURE_DIR.glob("*.json")):
        fixture = _load_fixture_path(path)
        out.append({
            "fixture_id": fixture["fixture_id"],
            "revision": fixture["revision"],
            "holdout_group": fixture.get("holdout_group", ""),
            "privacy": fixture["privacy"],
        })
    return out


def _load_fixture_path(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if raw.get("schema") != FIXTURE_SCHEMA:
        raise QualificationError("BAD_FIXTURE_SCHEMA", f"{path.name} must use {FIXTURE_SCHEMA}")
    for key in ("fixture_id", "revision", "privacy", "task", "assets", "chronology", "expected"):
        if key not in raw:
            raise QualificationError("BAD_FIXTURE", f"{path.name} is missing {key!r}")
    privacy = raw.get("privacy") or {}
    if (privacy.get("classification") != "synthetic"
            or privacy.get("contains_customer_authored_text") is not False
            or privacy.get("contains_production_identifiers") is not False):
        raise QualificationError("UNSAFE_FIXTURE", f"{path.name} is not explicitly privacy-safe")
    event_ids = [str(row.get("event_id") or "") for row in raw.get("chronology") or []]
    if not event_ids or not all(event_ids) or len(set(event_ids)) != len(event_ids):
        raise QualificationError("BAD_FIXTURE", f"{path.name} needs unique chronology event ids")
    return raw


def load_qualification_fixture(fixture_id: str) -> dict[str, Any]:
    for path in sorted(_FIXTURE_DIR.glob("*.json")):
        fixture = _load_fixture_path(path)
        if fixture["fixture_id"] == fixture_id:
            return fixture
    raise QualificationError("UNKNOWN_FIXTURE", f"unknown fixture {fixture_id!r}")


def _tool_contract() -> list[dict[str, Any]]:
    """Derive the adapter-visible tool shape from the live Core functions."""
    rows = []
    for name in _TOOL_NAMES:
        fn = getattr(services, name, None)
        if fn is None:
            raise QualificationError("CORE_TOOL_MISSING", f"Core no longer exposes {name}")
        params = []
        for parameter in inspect.signature(fn).parameters.values():
            if parameter.name == "store":
                continue
            params.append({
                "name": parameter.name,
                "kind": parameter.kind.name.lower(),
                "required": parameter.default is inspect.Parameter.empty,
            })
        rows.append({"name": name, "parameters": params})
    return rows


def qualification_contract(fixture_id: str) -> dict[str, Any]:
    """Return the exact immutable input every adapter receives for one case.

    The private ``expected`` block and correction answer are excluded.  Asset
    bytes are synthetic and included identically for hosted and external runs.
    """
    fixture = load_qualification_fixture(fixture_id)
    task = copy.deepcopy(fixture["task"])
    for capability in task.get("capabilities") or []:
        capability.pop("expected_initial_status", None)
    visible = {
        "schema": CONTEXT_VERSION,
        "harness_version": HARNESS_VERSION,
        "fixture_id": fixture["fixture_id"],
        "fixture_revision": fixture["revision"],
        "system_context": (
            "Use one stable operation identity per logical request, resolve the declared methodology "
            "before research, follow run_step dispatches with their exact dispatch tokens, inspect "
            "real stimulus before persona reaction, keep untested capabilities unknown, declare claim "
            "posture and evidence refs, include ordinary skepticism/indifference, and continue until "
            "the deterministic engine returns done after independent critic completion."
        ),
        "task": task,
        "assets": copy.deepcopy(fixture["assets"]),
        "chronology": copy.deepcopy(fixture["chronology"]),
        **({"cohort_risk": copy.deepcopy(fixture["cohort_risk"])}
           if fixture.get("cohort_risk") else {}),
        "tools": _tool_contract(),
        "budget": {"max_run_steps": 24, "max_critic_rounds": 4, "max_tool_calls": 80},
        "fixed_thresholds": copy.deepcopy(FIXED_THRESHOLDS),
    }
    return {**visible, "contract_digest": _digest(visible)}


def qualification_contracts(fixture_ids: list[str] | None = None) -> list[dict[str, Any]]:
    ids = fixture_ids or [row["fixture_id"] for row in list_qualification_fixtures()]
    return [qualification_contract(fid) for fid in ids]


def _required_text(value: Any, label: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise QualificationError("BAD_SUBMISSION", f"{label} is required")
    return text


def _validate_review(review: Any) -> dict[str, Any] | None:
    if review in (None, {}):
        return None
    if not isinstance(review, dict) or review.get("schema") != REVIEW_SCHEMA:
        raise QualificationError("BAD_REVIEW", f"review must use {REVIEW_SCHEMA}")
    evaluator = review.get("evaluator") or {}
    if evaluator.get("kind") not in {"human", "calibrated_judge"}:
        raise QualificationError("BAD_REVIEW", "review evaluator.kind must be human or calibrated_judge")
    for key in ("id", "version"):
        _required_text(evaluator.get(key), f"review.evaluator.{key}")
    if review.get("calibrated") is not True:
        raise QualificationError("BAD_REVIEW", "review must explicitly be calibrated")
    scores = review.get("scores") or {}
    clean_scores: dict[str, int] = {}
    for dimension in REVIEW_DIMENSIONS:
        value = scores.get(dimension)
        if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 5:
            raise QualificationError("BAD_REVIEW", f"review score {dimension!r} must be an integer 0..5")
        clean_scores[dimension] = value
    return {"schema": REVIEW_SCHEMA, "evaluator": dict(evaluator), "calibrated": True,
            "scores": clean_scores, "reviewed_at": _required_text(
                review.get("reviewed_at"), "review.reviewed_at")}


def validate_qualification_submission(submission: dict[str, Any],
                                      contract: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(submission, dict) or submission.get("schema") != SUBMISSION_SCHEMA:
        raise QualificationError("BAD_SUBMISSION_SCHEMA", f"submission must use {SUBMISSION_SCHEMA}")
    if submission.get("fixture_id") != contract["fixture_id"]:
        raise QualificationError("SUBMISSION_FIXTURE_MISMATCH", "submission fixture_id does not match")
    if submission.get("fixture_revision") != contract["fixture_revision"]:
        raise QualificationError("SUBMISSION_REVISION_MISMATCH", "submission fixture revision does not match")
    if submission.get("contract_digest") != contract["contract_digest"]:
        raise QualificationError("CONTRACT_DIGEST_MISMATCH", "adapter did not use the issued context/tools/assets/budget")

    provider = submission.get("provider") or {}
    for key in ("name", "model", "version", "adapter_version", "run_at"):
        _required_text(provider.get(key), f"provider.{key}")
    surface = submission.get("surface") or {}
    kind = surface.get("kind")
    visibility = surface.get("visibility") or {}
    if kind not in {"hosted", "external_mcp"}:
        raise QualificationError("BAD_SURFACE", "surface.kind must be hosted or external_mcp")
    if visibility.get("tool_boundary") != "observed":
        raise QualificationError("BAD_SURFACE", "Sonaloop tool-boundary visibility must be observed")
    metrics = submission.get("metrics") or {}
    latency = metrics.get("latency_ms")
    if not isinstance(latency, (int, float)) or isinstance(latency, bool) or latency < 0:
        raise QualificationError("BAD_METRICS", "metrics.latency_ms must be non-negative")
    if kind == "external_mcp":
        if (visibility.get("host_turns") != "unavailable_external_host"
                or visibility.get("generation") != "unavailable_external_host"):
            raise QualificationError(
                "EXTERNAL_BLIND_SPOT_MISREPRESENTED",
                "external MCP must declare host turns and generations unavailable",
            )
        for field in ("input_tokens", "output_tokens", "cost_usd"):
            if metrics.get(field) is not None:
                raise QualificationError(
                    "FABRICATED_EXTERNAL_METRIC",
                    f"external MCP result cannot claim unobserved {field}",
                )
    else:
        if visibility.get("generation") != "observed" or visibility.get("host_turns") != "observed":
            raise QualificationError("HOSTED_VISIBILITY_REQUIRED", "hosted adapters must observe generation and turns")
        for field in ("input_tokens", "output_tokens"):
            if not isinstance(metrics.get(field), int) or isinstance(metrics.get(field), bool) or metrics[field] < 0:
                raise QualificationError("BAD_METRICS", f"hosted metrics.{field} must be a non-negative integer")
        if (not isinstance(metrics.get("cost_usd"), (int, float))
                or isinstance(metrics.get("cost_usd"), bool) or metrics["cost_usd"] < 0):
            raise QualificationError("BAD_METRICS", "hosted metrics.cost_usd must be non-negative")

    protocol = submission.get("protocol") or {}
    chronology_ids = {row["event_id"] for row in contract["chronology"]}
    for mapping_name in ("operation_ids", "run_operation_ids"):
        mapping = protocol.get(mapping_name)
        if not isinstance(mapping, dict) or set(mapping) != chronology_ids:
            raise QualificationError("BAD_SUBMISSION", f"protocol.{mapping_name} must cover every chronology event exactly")
        for event_id, value in mapping.items():
            _required_text(value, f"protocol.{mapping_name}.{event_id}")
    if protocol.get("methodology") is not None:
        _required_text(protocol.get("methodology"), "protocol.methodology")
    for field in ("use_dispatch_tokens", "include_evidence_refs", "link_gate_evidence",
                  "manual_finish_before_done", "explicit_claim_inventory"):
        if not isinstance(protocol.get(field), bool):
            raise QualificationError("BAD_SUBMISSION", f"protocol.{field} must be boolean")
    if protocol.get("cohort_strategy") not in {"reselect_independent", "override_circular"}:
        raise QualificationError(
            "BAD_SUBMISSION",
            "protocol.cohort_strategy must be reselect_independent or override_circular",
        )
    capability_statuses = protocol.get("capability_statuses")
    if not isinstance(capability_statuses, dict):
        raise QualificationError("BAD_SUBMISSION", "protocol.capability_statuses must be an object")
    voices = protocol.get("voices")
    if not isinstance(voices, list) or not voices:
        raise QualificationError("BAD_SUBMISSION", "protocol.voices must not be empty")
    for index, voice in enumerate(voices):
        if not isinstance(voice, dict) or voice.get("stance") not in {
                "supportive", "skeptical", "indifferent", "rejecting"}:
            raise QualificationError("BAD_SUBMISSION", f"protocol.voices[{index}] has invalid stance")
        _required_text(voice.get("voice_id"), f"protocol.voices[{index}].voice_id")
        _required_text(voice.get("text"), f"protocol.voices[{index}].text")
    critic_passes = protocol.get("critic_passes")
    if not isinstance(critic_passes, int) or isinstance(critic_passes, bool) or not 0 <= critic_passes <= 4:
        raise QualificationError("BAD_SUBMISSION", "protocol.critic_passes must be an integer 0..4")
    report = protocol.get("report") or {}
    for key in ("arc_narrative", "gesamtbild", "positionierung", "claim"):
        _required_text(report.get(key), f"protocol.report.{key}")
    clean = copy.deepcopy(submission)
    clean["review"] = _validate_review(submission.get("review"))
    return clean


# Imported after the public constants/errors above: the private runtime reads
# those symbols while this module remains the stable adapter-facing facade.
from ._qualification_runtime import _ephemeral_store, _execute_case, _score_case


def _review_result(review: dict[str, Any] | None) -> dict[str, Any]:
    if not review:
        return {"status": "required", "passed": False, "score": None,
                "threshold": FIXED_THRESHOLDS["review_dimension_min_0_to_5"],
                "dimensions": list(REVIEW_DIMENSIONS)}
    scores = review["scores"]
    threshold = int(FIXED_THRESHOLDS["review_dimension_min_0_to_5"])
    passed = all(scores[key] >= threshold for key in REVIEW_DIMENSIONS)
    return {"status": "passed" if passed else "failed", "passed": passed,
            "score": round(sum(scores.values()) / (5 * len(REVIEW_DIMENSIONS)), 4),
            "threshold": threshold, "scores": scores, "evaluator": review["evaluator"],
            "reviewed_at": review["reviewed_at"]}


def run_qualification_case(adapter: QualificationAdapter, fixture_id: str) -> dict[str, Any]:
    contract = qualification_contract(fixture_id)
    submission = validate_qualification_submission(adapter.run_case(copy.deepcopy(contract)), contract)
    fixture = load_qualification_fixture(fixture_id)
    with _ephemeral_store() as store:
        state = _execute_case(fixture, submission, store)
        checks, metrics = _score_case(fixture, submission, state, store)
        object_refs = {
            "projects": sorted(_opaque("project", row["project_id"])
                               for row in state["frontdoor"]),
            "runs": sorted(_opaque("run", row["run_id"])
                           for row in state["frontdoor"]),
        }
    # Dedupe opaque retry refs in the public result without concealing counts.
    object_refs = {key: sorted(set(values)) for key, values in object_refs.items()}
    deterministic_score = round(sum(row["score"] for row in checks) / len(checks), 4)
    contract_passed = all(row["passed"] for row in checks)
    review = _review_result(submission.get("review"))
    combined = (round(min(deterministic_score, review["score"]), 4)
                if review["score"] is not None else None)
    if not contract_passed:
        status = "failed_contract"
    elif review["status"] == "required":
        status = "review_required"
    elif not review["passed"]:
        status = "failed_review"
    else:
        status = "qualified"
    return {
        "schema": CASE_RESULT_SCHEMA,
        "harness_version": HARNESS_VERSION,
        "fixture_id": fixture_id,
        "fixture_revision": contract["fixture_revision"],
        "contract_digest": contract["contract_digest"],
        "provider": submission["provider"],
        "surface": submission["surface"],
        "status": status,
        "qualified": status == "qualified",
        "contract_passed": contract_passed,
        "deterministic_score": deterministic_score,
        "review": review,
        "combined_score": combined,
        "checks": checks,
        "metrics": metrics,
        "objects": object_refs,
        "blind_spots": (
            ["provider host turns", "provider system prompt", "hidden reasoning",
             "provider retries before an MCP request", "provider-owned permission dialogs",
             "generation tokens and cost"]
            if submission["surface"]["kind"] == "external_mcp" else []),
        "routing": {
            "action": ("none" if status == "qualified" else "stronger_model_or_human_review"),
            "contract_gates_relaxed": False,
        },
    }


def run_provider_qualification(adapters: list[QualificationAdapter],
                               fixture_ids: list[str] | None = None) -> dict[str, Any]:
    """Run one or more adapters under identical per-fixture contracts."""
    if not adapters:
        raise QualificationError("NO_ADAPTERS", "at least one qualification adapter is required")
    ids = fixture_ids or [row["fixture_id"] for row in list_qualification_fixtures()]
    results = [run_qualification_case(adapter, fixture_id)
               for adapter in adapters for fixture_id in ids]
    digest_by_fixture: dict[str, set[str]] = {}
    for row in results:
        digest_by_fixture.setdefault(row["fixture_id"], set()).add(row["contract_digest"])
    if any(len(values) != 1 for values in digest_by_fixture.values()):  # pragma: no cover
        raise QualificationError("NON_INVARIANT_CONTRACT", "providers received different fixture contracts")
    return {
        "schema": REPORT_SCHEMA,
        "harness_version": HARNESS_VERSION,
        "generated_at": utc_now_iso(),
        "fixed_thresholds": copy.deepcopy(FIXED_THRESHOLDS),
        "thresholds_digest": _digest(FIXED_THRESHOLDS),
        "fixtures": ids,
        "results": results,
        "summary": {
            "qualified": sum(row["qualified"] for row in results),
            "review_required": sum(row["status"] == "review_required" for row in results),
            "failed": sum(row["status"].startswith("failed") for row in results),
            "total": len(results),
        },
    }


def write_qualification_report(report: dict[str, Any], path: str | Path) -> str:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return str(target)
