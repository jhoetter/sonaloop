"""Domain-neutral result schemas and job/methodology output contracts.

Result schemas answer: "what output shape must exist before this job can be considered done?"
They deliberately sit above domain vocabulary. A pricing job, for example, uses
`ordered_ladder_sensitivity.v1`; the schema itself does not know about money.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from typing import Any

from .config import PACKAGE_DIR

REGISTRY_SCHEMA = "sonaloop.result_schema.registry"
_SCHEMA_ID = re.compile(r"^[a-z][a-z0-9_]*\.v[0-9]+$")


def registry_path():
    return PACKAGE_DIR / "result_schemas.json"


@lru_cache(maxsize=1)
def load_registry() -> dict[str, Any]:
    return json.loads(registry_path().read_text(encoding="utf-8"))


def schemas() -> list[dict[str, Any]]:
    return load_registry()["schemas"]


def get_schema(schema_id: str) -> dict[str, Any]:
    for row in schemas():
        if row["id"] == schema_id:
            return row
    raise KeyError(f"No result schema '{schema_id}'")


def job_contracts() -> list[dict[str, Any]]:
    return load_registry()["job_contracts"]


def methodology_contracts() -> list[dict[str, Any]]:
    return load_registry()["methodology_contracts"]


def contract_for_job(job_id: str) -> dict[str, Any]:
    for row in job_contracts():
        if row["job_id"] == job_id:
            return row
    raise KeyError(f"No result contract for job '{job_id}'")


def contract_for_methodology(methodology_key: str) -> dict[str, Any]:
    for row in methodology_contracts():
        if row["methodology_key"] == methodology_key:
            return row
    raise KeyError(f"No result contract for methodology '{methodology_key}'")


def schemas_for_job(job_id: str) -> list[dict[str, Any]]:
    contract = contract_for_job(job_id)
    return [_with_role(ref) for ref in contract.get("result_schemas") or []]


def schemas_for_methodology(methodology_key: str) -> list[dict[str, Any]]:
    contract = contract_for_methodology(methodology_key)
    return [_with_role(ref) for ref in contract.get("result_schemas") or []]


def _with_role(ref: dict[str, Any]) -> dict[str, Any]:
    schema = dict(get_schema(ref["id"]))
    schema["role"] = ref.get("role", "")
    return schema


def registry_errors(registry: dict[str, Any] | None = None, store: Any | None = None) -> list[str]:
    """Structural lint for result_schemas.json.

    Cross-checks the result contracts against the canonical job taxonomy and live methodology registry
    when those sources are available. Returns problems instead of raising so tests and CLI can report
    the full list at once.
    """
    reg = registry or load_registry()
    errors: list[str] = []
    if reg.get("schema") != REGISTRY_SCHEMA:
        errors.append(f"schema must be {REGISTRY_SCHEMA!r}")
    if not isinstance(reg.get("version"), int) or reg.get("version", 0) < 1:
        errors.append("version must be an integer >= 1")

    schema_ids: set[str] = set()
    for row in reg.get("schemas") or []:
        sid = str(row.get("id") or "")
        where = f"schema {sid!r}"
        if not _SCHEMA_ID.match(sid):
            errors.append(f"{where}: id must be versioned lower_snake_case, e.g. stimulus_reaction.v1")
        if sid in schema_ids:
            errors.append(f"{where}: duplicate id")
        schema_ids.add(sid)
        for field in ("name", "summary", "result_kind"):
            if not str(row.get(field) or "").strip():
                errors.append(f"{where}: missing {field}")
        if not row.get("fields"):
            errors.append(f"{where}: fields must be non-empty")
        for field in row.get("fields") or []:
            if not str(field.get("id") or "").strip() or not str(field.get("type") or "").strip():
                errors.append(f"{where}: every field needs id + type")
        if not row.get("done_when"):
            errors.append(f"{where}: done_when must be non-empty")

    def check_refs(owner: str, refs: list[dict[str, Any]]) -> None:
        if not refs:
            errors.append(f"{owner}: result_schemas must be non-empty")
            return
        seen: set[str] = set()
        for ref in refs:
            sid = ref.get("id")
            if sid not in schema_ids:
                errors.append(f"{owner}: unknown schema {sid!r}")
            if sid in seen:
                errors.append(f"{owner}: duplicate schema ref {sid!r}")
            seen.add(sid)
            if not str(ref.get("role") or "").strip():
                errors.append(f"{owner}: schema {sid!r} needs role")

    job_ids: set[str] | None = None
    meth_keys: set[str] | None = None
    try:
        from . import job_taxonomy as _jobs
        job_ids = {j["id"] for j in _jobs.jobs()}
    except Exception:
        pass
    try:
        from . import methodology as _meth
        # Result contracts are required for packaged methodologies. User-defined methodologies are
        # allowed to be off-menu until they carry their own contract extension.
        meth_keys = {m["key"] for m in _meth.list_methodologies(store=store)}
    except Exception:
        pass

    seen_jobs: set[str] = set()
    for contract in reg.get("job_contracts") or []:
        jid = str(contract.get("job_id") or "")
        owner = f"job_contract {jid!r}"
        if job_ids is not None and jid not in job_ids:
            errors.append(f"{owner}: unknown taxonomy job")
        if jid in seen_jobs:
            errors.append(f"{owner}: duplicate")
        seen_jobs.add(jid)
        check_refs(owner, contract.get("result_schemas") or [])
        if not str(contract.get("done_summary") or "").strip():
            errors.append(f"{owner}: done_summary is missing")
    if job_ids is not None and seen_jobs != job_ids:
        missing = sorted(job_ids - seen_jobs)
        extra = sorted(seen_jobs - job_ids)
        if missing:
            errors.append(f"job_contracts: missing contracts for {missing}")
        if extra:
            errors.append(f"job_contracts: unknown contracts for {extra}")

    seen_methods: set[str] = set()
    for contract in reg.get("methodology_contracts") or []:
        key = str(contract.get("methodology_key") or "")
        owner = f"methodology_contract {key!r}"
        if meth_keys is not None and key not in meth_keys:
            errors.append(f"{owner}: unknown methodology")
        if key in seen_methods:
            errors.append(f"{owner}: duplicate")
        seen_methods.add(key)
        check_refs(owner, contract.get("result_schemas") or [])
        if not str(contract.get("done_summary") or "").strip():
            errors.append(f"{owner}: done_summary is missing")
    if meth_keys is not None and seen_methods != meth_keys:
        missing = sorted(meth_keys - seen_methods)
        if missing:
            errors.append(f"methodology_contracts: missing contracts for {missing}")
    return errors


def assert_valid_registry(registry: dict[str, Any] | None = None, store: Any | None = None) -> dict[str, Any]:
    reg = registry or load_registry()
    errors = registry_errors(reg, store=store)
    if errors:
        raise ValueError("Invalid result schema registry:\n- " + "\n- ".join(errors))
    return reg
