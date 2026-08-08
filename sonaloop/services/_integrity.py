"""Product-understanding write/read service.

The artifact is stored as immutable versions on its research project.  Project
JSON is updated with compare-and-swap so two observers cannot silently erase
one another; a dispatch/key retry resolves to the same version and repairs the
plan link/checkpoint if a process died between those writes.
"""
from __future__ import annotations

import copy
from typing import Any

from ..config import utc_now_iso
from ..research_integrity import (
    IntegrityError,
    PRODUCT_UNDERSTANDING_SCHEMA,
    current_product_understanding,
    operation_fingerprint,
    product_understanding_payload,
    render_product_understanding_context,
)
from ..storage import Store

from ._flow_manifests import validate_product_understanding_manifest_binding

from ._common import *  # noqa: F401,F403  (stable_id, web_url)


def brief_product_understanding(project_id: str, store: Store | None = None) -> dict[str, Any]:
    """Gather the target/stimulus inventory for the mandatory product preflight."""
    store = store or Store()
    project = _require_research_project(store, project_id)  # noqa: F821 (bound)
    current = current_product_understanding(project)
    return {
        "schema": PRODUCT_UNDERSTANDING_SCHEMA,
        "project_id": project["id"],
        "goal": project.get("goal", ""),
        "current": current,
        "available_evidence": {
            "assets": [{"kind": "asset", "id": a.get("id"), "title": a.get("title", ""),
                        "direction": a.get("direction") or "in"}
                       for a in project.get("assets") or []],
            "artifacts": [{"kind": "artifact", "id": a.get("id"), "title": a.get("title", ""),
                           "captured": bool((a.get("snapshot") or {}).get("ok"))}
                          for a in project.get("artifacts") or []],
            "flows": [{"kind": "flow", "id": f.get("id"), "title": f.get("title", ""),
                       "steps": len(f.get("steps") or [])}
                      for f in project.get("flows") or []],
            "flow_manifests": [{"kind": "flow", "id": f.get("id"),
                                "flow_key": f.get("flow_key", ""),
                                "version": f.get("version"),
                                "manifest_digest": f.get("manifest_digest", ""),
                                "target_revision": f.get("target_revision", ""),
                                "steps": len(f.get("steps") or [])}
                               for f in project.get("flow_manifests") or []],
        },
        "instructions": (
            "Inspect the actual product material before personas react. Author one immutable "
            "Product Understanding version with: target identity; explicit revision (or 'unknown'); "
            "observed_at; routes, flows and states; and capability claims. Claim status is exactly "
            "observed_present, observed_absent, inferred or unknown. Every observed/inferred claim "
            "cites project evidence; observed_absent also documents the verification attempt. Keep "
            "uncertain capabilities unknown until a real observation changes them. When using a "
            "remote flow, freeze its exact id/version/digest/target_revision in stimulus_manifest "
            "and supply one inspected coverage_checklist entry citing each exact asset version. "
            "Pass the current "
            "run_step dispatch_token to record_product_understanding; it auto-links and checkpoints "
            "the preflight. The artifact is external stimulus and is never written into persona memory."
        ),
    }


def record_product_understanding(
    project_id: str,
    target: dict[str, Any],
    revision: str,
    routes: list[Any],
    flows: list[Any],
    states: list[Any],
    capabilities: list[dict[str, Any]],
    evidence_refs: list[Any] | None = None,
    stimulus_manifest: dict[str, Any] | None = None,
    coverage_checklist: list[dict[str, Any]] | None = None,
    observed_at: str | None = None,
    key: str | None = None,
    dispatch_token: str | None = None,
    store: Store | None = None,
) -> dict[str, Any]:
    """Append a validated Product Understanding version and bind it to its dispatch.

    ``key`` or ``dispatch_token`` is the idempotency identity. Reusing it with
    different authored content fails before mutation. A later observation uses a
    new key and appends lineage; history is never overwritten.
    """
    store = store or Store()
    ctx = prepare_dispatch_write(  # noqa: F821 (bound after services package import)
        project_id, dispatch_token, key, "product_understanding", store,
        allowed_buckets={"analyze"}, required_capability="product_understanding",
    )
    operation_id = str(ctx.get("operation_id") or key or "").strip()
    authored = {
        "target": target,
        "revision": revision,
        "routes": routes or [],
        "flows": flows or [],
        "states": states or [],
        "capabilities": capabilities or [],
        "evidence_refs": evidence_refs or [],
        "stimulus_manifest": stimulus_manifest or {},
        "coverage_checklist": coverage_checklist or [],
        "observed_at": observed_at or "",
    }
    fingerprint = operation_fingerprint(authored)

    record: dict[str, Any] | None = None
    replay = False
    for _attempt in range(16):
        current_project = store.get_research_project(project_id)
        if not current_project:
            raise IntegrityError("UNKNOWN_PROJECT", f"unknown research project: {project_id}")
        versions = current_project.get("product_understanding_versions") or []
        if operation_id:
            existing = next((v for v in versions
                             if str(v.get("operation_id") or "") == operation_id), None)
            if existing:
                if str(existing.get("operation_fingerprint") or "") != fingerprint:
                    raise IntegrityError(
                        "PRODUCT_UNDERSTANDING_IDEMPOTENCY_CONFLICT",
                        "the Product Understanding operation key was reused with different content",
                    )
                record = existing
                replay = True
                break
        previous = current_product_understanding(current_project)
        now = observed_at or utc_now_iso()
        record_id = (stable_id("product_understanding", project_id, operation_id)  # noqa: F821
                     if operation_id else stable_id("product_understanding", project_id, now))  # noqa: F821
        record = product_understanding_payload(
            project_id, target, revision, routes or [], flows or [], states or [],
            capabilities or [], evidence_refs or [], store, observed_at=now,
            record_id=record_id, version=len(versions) + 1,
            supersedes=str((previous or {}).get("id") or ""), prior=previous,
        )
        binding = validate_product_understanding_manifest_binding(
            current_project, record, stimulus_manifest, coverage_checklist,
        )
        if binding:
            record["stimulus_manifest"] = {k: v for k, v in binding.items()
                                           if k != "coverage_checklist"}
            record["coverage_checklist"] = binding["coverage_checklist"]
        if operation_id:
            record["operation_id"] = operation_id
            record["operation_fingerprint"] = fingerprint
        updated = copy.deepcopy(current_project)
        updated.setdefault("product_understanding_versions", []).append(record)
        updated["product_understanding_current_id"] = record["id"]
        updated["updated_at"] = utc_now_iso()
        if store.compare_and_swap_research_project(current_project, updated):
            break
        record = None
    if record is None:
        raise IntegrityError(
            "PRODUCT_UNDERSTANDING_CONTENTION",
            "the project changed repeatedly; retry the same operation key",
        )

    dispatch = bind_dispatch_output(  # noqa: F821 (bound)
        ctx, {"kind": "product_understanding", "id": record["id"]},
        "recorded evidence-backed Product Understanding preflight", store,
    )
    return {
        **record,
        "idempotent_replay": replay,
        "dispatch": dispatch,
        "project_url": web_url(f"/jobs/{project_id}"),  # noqa: F821 (bound)
    }


def get_product_understanding(project_id: str, version_id: str | None = None,
                              store: Store | None = None) -> dict[str, Any]:
    """Read the current version or one immutable historical version with lineage."""
    store = store or Store()
    project = _require_research_project(store, project_id)  # noqa: F821 (bound)
    versions = project.get("product_understanding_versions") or []
    if version_id:
        record = next((v for v in versions if str(v.get("id") or "") == version_id), None)
    else:
        record = current_product_understanding(project)
    if not record:
        raise KeyError(f"No Product Understanding version for project {project_id}")
    return {**record, "history": [{"id": v.get("id"), "version": v.get("version"),
                                    "revision": v.get("revision"), "observed_at": v.get("observed_at"),
                                    "supersedes": v.get("supersedes", "")}
                                   for v in versions],
            "context": render_product_understanding_context(record)}
