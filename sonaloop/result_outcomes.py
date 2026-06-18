"""Project-owned job result outcomes.

Result schemas define the output contract for a job. Outcomes are completion
milestones on the project itself, not sections of a synthesis. A synthesis, council,
session or asset can be cited as evidence, but none of them owns the outcome.
"""
from __future__ import annotations

import hashlib
from typing import Any

from . import result_schemas as _schemas
from .config import utc_now_iso
from .storage import Store


def _stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"


def _ref(r: dict[str, Any]) -> dict[str, str]:
    return {"kind": str((r or {}).get("kind", "")), "id": str((r or {}).get("id", ""))}


def _normalize_schema_ref(ref: dict[str, Any] | str) -> dict[str, str]:
    if isinstance(ref, str):
        return {"id": ref, "role": "target"}
    return {"id": str(ref.get("id") or ""), "role": str(ref.get("role") or "target")}


def expected_schema_refs(store: Store, project_id: str) -> list[dict[str, str]]:
    """The explicit output contract for this project.

    Runtime enforcement is project-scoped: `expected_result_schemas` wins. Job
    presets populate it from the job contract. Methodology contracts remain useful
    documentation unless a project explicitly adopts them as expected outputs.
    """
    project = store.get_research_project(project_id) or {}
    raw = project.get("expected_result_schemas") or []
    if not raw:
        try:
            plan = store.get_research_plan(project_id) or {}
        except Exception:
            plan = {}
        job_id = str(project.get("job") or plan.get("job") or "")
        if job_id:
            try:
                raw = _schemas.contract_for_job(job_id).get("result_schemas") or []
            except Exception:
                raw = []
    refs = [_normalize_schema_ref(r) for r in raw]
    return [r for r in refs if r["id"]]


def set_expected_schema_refs(store: Store, project_id: str, refs: list[dict[str, Any] | str],
                             source: str = "") -> dict[str, Any]:
    project = store.get_research_project(project_id)
    if not project:
        raise KeyError(f"Unknown research project: {project_id}")
    clean = [_normalize_schema_ref(r) for r in refs]
    for r in clean:
        _schemas.get_schema(r["id"])
    project["expected_result_schemas"] = clean
    if source:
        project["expected_result_schema_source"] = source
    project["updated_at"] = utc_now_iso()
    store.upsert_research_project(project)
    return {"project_id": project_id, "expected_result_schemas": clean}


def _validate_result(schema: dict[str, Any], result: dict[str, Any]) -> None:
    if not isinstance(result, dict):
        raise ValueError("result must be an object")
    missing: list[str] = []
    for field in schema.get("fields") or []:
        if not field.get("required"):
            continue
        fid = str(field.get("id") or "")
        value = result.get(fid)
        if value is None or value == "" or value == [] or value == {}:
            missing.append(fid)
    if missing:
        raise ValueError(f"result for {schema['id']} misses required field(s): {', '.join(missing)}")


def record_project_schema_outcome(store: Store, project_id: str, schema_id: str,
                                  result: dict[str, Any], evidence_refs: list[dict[str, Any]] | None = None,
                                  key: str | None = None, source_task_id: str = "") -> dict[str, Any]:
    """Persist one project-owned schema outcome.

    The id is stable per project+schema unless a key is provided. Re-recording updates
    the same milestone, which is what a resumable run wants.
    """
    project = store.get_research_project(project_id)
    if not project:
        raise KeyError(f"Unknown research project: {project_id}")
    schema = _schemas.get_schema(schema_id)
    _validate_result(schema, result)
    now = utc_now_iso()
    oid = _stable_id("joboutcome", key) if key else _stable_id("joboutcome", project_id, schema_id)
    refs = [_ref(r) for r in (evidence_refs or []) if _ref(r)["kind"] and _ref(r)["id"]]
    outcome = {
        "id": oid,
        "kind": "job_outcome",
        "project_id": project_id,
        "schema_id": schema_id,
        "name": schema.get("name") or schema_id,
        "result_kind": schema.get("result_kind", ""),
        "result": result,
        "evidence_refs": refs,
        "source": {"kind": "job_completion", "task_id": source_task_id},
        "created_at": now,
        "updated_at": now,
    }
    existing = list(project.get("job_outcomes") or [])
    kept = [o for o in existing if o.get("id") != oid and o.get("schema_id") != schema_id]
    prior = next((o for o in existing if o.get("id") == oid or o.get("schema_id") == schema_id), None)
    if prior and prior.get("created_at"):
        outcome["created_at"] = prior["created_at"]
    kept.append(outcome)
    project["job_outcomes"] = kept
    project["updated_at"] = now
    store.upsert_research_project(project)
    return normalize_outcome(outcome)


def normalize_outcome(outcome: dict[str, Any]) -> dict[str, Any]:
    schema_id = str(outcome.get("schema_id") or "")
    try:
        schema = _schemas.get_schema(schema_id)
    except Exception:
        schema = {"id": schema_id, "name": schema_id, "fields": []}
    out = dict(outcome)
    out["kind"] = "job_outcome"
    out["schema"] = schema
    out["name"] = out.get("name") or schema.get("name") or schema_id
    out["result_kind"] = out.get("result_kind") or schema.get("result_kind", "")
    return out


def project_schema_outcomes(store: Store, project_id: str) -> list[dict[str, Any]]:
    project = store.get_research_project(project_id) or {}
    return sorted(
        [normalize_outcome(o) for o in (project.get("job_outcomes") or [])],
        key=lambda o: (o.get("created_at", ""), o.get("schema_id", "")),
    )


def get_project_schema_outcome(store: Store, project_id: str, outcome_id: str) -> dict[str, Any] | None:
    for outcome in project_schema_outcomes(store, project_id):
        if outcome.get("id") == outcome_id or outcome.get("schema_id") == outcome_id:
            return outcome
    return None


def project_result_contract_state(store: Store, project_id: str) -> dict[str, Any]:
    expected = expected_schema_refs(store, project_id)
    outcomes = project_schema_outcomes(store, project_id)
    recorded = {o.get("schema_id") for o in outcomes}
    missing = [r for r in expected if r["id"] not in recorded]
    return {
        "expected": expected,
        "recorded": [{"id": o.get("id"), "schema_id": o.get("schema_id")} for o in outcomes],
        "missing": missing,
        "satisfied": not missing,
    }
