"""Product-understanding write/read service.

The artifact is stored as immutable versions on its research project.  Project
JSON is updated with compare-and-swap so two observers cannot silently erase
one another; a dispatch/key retry resolves to the same version and repairs the
plan link/checkpoint if a process died between those writes.
"""
from __future__ import annotations

import copy
from typing import Any
from urllib.parse import urlparse

from ..config import utc_now_iso
from ..research_integrity import (
    IntegrityError,
    PRODUCT_UNDERSTANDING_SCHEMA,
    current_product_understanding,
    operation_fingerprint,
    product_understanding_payload,
    reaction_preflight_action,
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
    action = reaction_preflight_action(project_id, store)
    return {
        "schema": PRODUCT_UNDERSTANDING_SCHEMA,
        "project_id": project["id"],
        "goal": project.get("goal", ""),
        "current": current,
        "action": action,
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


def record_manifest_product_understanding(
    project_id: str,
    manifest_id: str,
    observations: list[dict[str, Any]],
    unknown_capabilities: list[str] | None = None,
    target_name: str = "",
    target_url: str = "",
    observed_at: str | None = None,
    key: str | None = None,
    dispatch_token: str | None = None,
    store: Store | None = None,
) -> dict[str, Any]:
    """Record a remote-manifest Product Understanding through a bounded contract.

    The host supplies only visible per-screen observations and honest unknowns.
    The server owns manifest revision/digest, inventory refs and exact coverage;
    it never fetches ``target_url`` or treats it as evidence.
    """
    store = store or Store()
    project = _require_research_project(store, project_id)  # noqa: F821
    manifest_id = str(manifest_id or "").strip()
    manifest = next((row for row in project.get("flow_manifests") or []
                     if str(row.get("id") or "") == manifest_id), None)
    if not manifest:
        raise IntegrityError(
            "STIMULUS_MANIFEST_BAD_REF",
            "manifest_id must name an admitted immutable flow manifest; safe retry: call "
            "brief_product_understanding and use action.manifest.id",
        )
    steps = list(manifest.get("steps") or [])
    if not isinstance(observations, list) or not observations:
        raise IntegrityError(
            "STIMULUS_OBSERVATION_INCOMPLETE",
            "observations must contain {step_index, claim} for every manifest step; safe retry: "
            "view each action.manifest.steps asset, then call record_manifest_product_understanding",
        )
    if len(observations) > 200:
        raise IntegrityError("STIMULUS_OBSERVATION_BAD_INPUT",
                             "observations may contain at most 200 rows")
    claims: list[dict[str, Any]] = []
    covered: set[int] = set()
    for index, raw in enumerate(observations):
        if not isinstance(raw, dict):
            raise IntegrityError(
                "STIMULUS_OBSERVATION_BAD_INPUT",
                f"observations[{index}] must be an object with step_index and claim",
            )
        step_index = raw.get("step_index")
        if not isinstance(step_index, int) or isinstance(step_index, bool):
            raise IntegrityError(
                "STIMULUS_OBSERVATION_BAD_INPUT",
                f"observations[{index}].step_index must be an integer",
            )
        if not 0 <= step_index < len(steps):
            raise IntegrityError(
                "STIMULUS_OBSERVATION_BAD_INPUT",
                f"observations[{index}].step_index {step_index} is outside 0..{len(steps) - 1}",
            )
        claim = str(raw.get("claim") or "").strip()
        if not claim:
            raise IntegrityError(
                "STIMULUS_OBSERVATION_BAD_INPUT",
                f"observations[{index}].claim is required",
            )
        if len(claim) > 1_000:
            raise IntegrityError(
                "STIMULUS_OBSERVATION_BAD_INPUT",
                f"observations[{index}].claim may contain at most 1000 characters",
            )
        step = steps[step_index]
        ref = {"kind": "asset", "id": str(step.get("asset_version_id") or "")}
        clean = {"claim": claim, "status": "observed_present", "evidence_refs": [ref]}
        if clean not in claims:
            claims.append(clean)
        covered.add(step_index)
    missing = sorted(set(range(len(steps))) - covered)
    if missing:
        raise IntegrityError(
            "STIMULUS_OBSERVATION_INCOMPLETE",
            f"observations are missing manifest step indexes {missing}; safe retry the same "
            "record_manifest_product_understanding call after viewing those exact assets",
        )
    if unknown_capabilities is not None and not isinstance(unknown_capabilities, list):
        raise IntegrityError("STIMULUS_OBSERVATION_BAD_INPUT",
                             "unknown_capabilities must be a list of strings")
    if len(unknown_capabilities or []) > 100:
        raise IntegrityError("STIMULUS_OBSERVATION_BAD_INPUT",
                             "unknown_capabilities may contain at most 100 entries")
    unknowns: list[str] = []
    for index, raw in enumerate(unknown_capabilities or []):
        value = str(raw or "").strip()
        if not value:
            continue
        if len(value) > 1_000:
            raise IntegrityError(
                "STIMULUS_OBSERVATION_BAD_INPUT",
                f"unknown_capabilities[{index}] may contain at most 1000 characters",
            )
        if value not in unknowns:
            unknowns.append(value)
    claims.extend({"claim": value, "status": "unknown", "evidence_refs": []}
                  for value in unknowns)

    url = str(target_url or "").strip()
    if url:
        if len(url) > 2_000:
            raise IntegrityError("BAD_PRODUCT_UNDERSTANDING",
                                 "target_url may contain at most 2000 characters")
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise IntegrityError(
                "BAD_PRODUCT_UNDERSTANDING",
                "target_url is identity metadata only and must be an absolute http(s) URL",
            )
    name = str(target_name or project.get("title") or "").strip()
    if len(name) > 500:
        raise IntegrityError("BAD_PRODUCT_UNDERSTANDING",
                             "target_name may contain at most 500 characters")
    target = {"name": name or url or "Unknown target"}
    if url:
        target["url"] = url
    flow_ref = {"kind": "flow", "id": manifest_id}
    states = [
        {"state": str(step.get("label") or f"Screen {index + 1}"),
         "evidence_refs": [{"kind": "asset", "id": step.get("asset_version_id")}]}
        for index, step in enumerate(steps)
    ]
    coverage = [
        {"step_index": index, "status": "inspected",
         "evidence_refs": [{"kind": "asset", "id": step.get("asset_version_id")}],
         "notes": "Bound to a concrete host-authored visible-screen observation."}
        for index, step in enumerate(steps)
    ]
    result = record_product_understanding(
        project_id,
        target=target,
        revision=str(manifest.get("target_revision") or "unknown"),
        routes=[],
        flows=[{"name": str(manifest.get("title") or "Admitted stimulus flow"),
                "evidence_refs": [flow_ref]}],
        states=states,
        capabilities=claims,
        evidence_refs=[flow_ref],
        stimulus_manifest={
            "id": manifest_id,
            "version": manifest.get("version"),
            "target_revision": manifest.get("target_revision"),
            "manifest_digest": manifest.get("manifest_digest"),
        },
        coverage_checklist=coverage,
        # The immutable manifest timestamp is the deterministic default; retries
        # therefore cannot conflict merely because wall time advanced.
        observed_at=observed_at or str(manifest.get("captured_at") or utc_now_iso()),
        key=key,
        dispatch_token=dispatch_token,
        store=store,
    )
    result["bounded_authoring"] = {
        "schema": "sonaloop.manifest_observations.v1",
        "manifest_id": manifest_id,
        "observed_steps": sorted(covered),
        "url_role": "target_identity_only",
    }
    return result


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
