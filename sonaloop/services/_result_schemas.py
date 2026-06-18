from __future__ import annotations

from typing import Any

from ..storage import Store
from .. import result_outcomes as _outcomes
from .. import result_schemas as _schemas


def list_result_schemas(store: Store | None = None) -> dict[str, Any]:
    store = store or Store()
    return {
        "schemas": _schemas.schemas(),
        "registry_errors": _schemas.registry_errors(store=store),
    }


def get_result_schema(schema_id: str, store: Store | None = None) -> dict[str, Any]:
    return _schemas.get_schema(schema_id)


def list_result_contracts(store: Store | None = None) -> dict[str, Any]:
    return {
        "job_contracts": _schemas.job_contracts(),
        "methodology_contracts": _schemas.methodology_contracts(),
        "registry_errors": _schemas.registry_errors(store=store),
    }


def result_contract_for_job(job_id: str, store: Store | None = None) -> dict[str, Any]:
    return _schemas.contract_for_job(job_id)


def result_contract_for_methodology(methodology_key: str, store: Store | None = None) -> dict[str, Any]:
    return _schemas.contract_for_methodology(methodology_key)


def set_project_result_schemas(project_id: str, refs: list[dict[str, Any] | str],
                               source: str = "", store: Store | None = None) -> dict[str, Any]:
    store = store or Store()
    return _outcomes.set_expected_schema_refs(store, project_id, refs, source=source)


def record_job_outcome(project_id: str, schema_id: str, result: dict[str, Any],
                       evidence_refs: list[dict[str, Any]] | None = None,
                       key: str | None = None, source_task_id: str = "",
                       store: Store | None = None) -> dict[str, Any]:
    store = store or Store()
    return _outcomes.record_project_schema_outcome(
        store, project_id, schema_id, result, evidence_refs=evidence_refs,
        key=key, source_task_id=source_task_id,
    )


def project_result_contract_state(project_id: str, store: Store | None = None) -> dict[str, Any]:
    store = store or Store()
    return _outcomes.project_result_contract_state(store, project_id)
