"""Immutable, versioned manifests over securely admitted remote screenshots."""
from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

from ..config import utc_now_iso
from ..research_integrity import IntegrityError, operation_fingerprint
from ..storage import Store

from ._common import *  # noqa: F401,F403  (stable_id, dispatch helpers, project guard)
from ._remote_assets import (
    FLOW_MANIFEST_SCHEMA,
    REMOTE_SCREENSHOT_SCHEMA,
    STIMULUS_BINDING_SCHEMA,
    _bound_dispatch,
    _remote_workspace,
    _required_text,
    _timestamp,
)

MAX_FLOW_MANIFEST_STEPS = 50


def _manifest_operation(project: dict[str, Any], operation_id: str) -> dict[str, Any] | None:
    return next((m for m in (project.get("flow_manifests") or [])
                 if str(m.get("operation_id") or "") == operation_id), None)


def record_flow_manifest(
    project_id: str,
    run_id: str,
    operation_id: str,
    flow_key: str,
    title: str,
    steps: list[dict[str, Any]],
    expected_task: str,
    target_revision: str,
    captured_at: str,
    dispatch_token: str = "",
    store: Store | None = None,
) -> dict[str, Any]:
    """Append an immutable, ordered manifest of admitted screenshot versions."""
    store = store or Store()
    workspace_id = _remote_workspace()
    project = _require_research_project(store, project_id)  # noqa: F821
    run_id = _required_text(run_id, "run_id")
    operation_id = _required_text(operation_id, "operation_id")
    flow_key = _required_text(flow_key, "flow_key")
    title = _required_text(title, "title")
    expected_task = _required_text(expected_task, "expected_task", maximum=1_000)
    target_revision = _required_text(target_revision, "target_revision")
    captured_at = _timestamp(captured_at, "captured_at")
    _run, dispatch_ctx = _bound_dispatch(project["id"], run_id, dispatch_token, "flow", store)
    if not isinstance(steps, list) or not steps:
        raise IntegrityError("FLOW_MANIFEST_BAD_INPUT", "steps must contain ordered admitted asset versions")
    if len(steps) > MAX_FLOW_MANIFEST_STEPS:
        raise IntegrityError("FLOW_MANIFEST_BAD_INPUT", "a flow manifest may contain at most 50 steps")

    raw_steps = []
    for index, raw in enumerate(steps):
        if not isinstance(raw, dict):
            raise IntegrityError("FLOW_MANIFEST_BAD_INPUT", f"steps[{index}] must be an object")
        asset_version_id = _required_text(raw.get("asset_version_id"), f"steps[{index}].asset_version_id")
        label = _required_text(raw.get("label"), f"steps[{index}].label")
        raw_steps.append({"asset_version_id": asset_version_id, "label": label})
    if len({row["asset_version_id"] for row in raw_steps}) != len(raw_steps):
        raise IntegrityError("FLOW_MANIFEST_BAD_INPUT", "a screenshot version may appear only once per manifest")

    intent = {
        "schema": FLOW_MANIFEST_SCHEMA,
        "workspace_id": workspace_id,
        "project_id": project["id"],
        "run_id": run_id,
        "operation_id": operation_id,
        "flow_key": flow_key,
        "title": title,
        "steps": raw_steps,
        "expected_task": expected_task,
        "target_revision": target_revision,
        "captured_at": captured_at,
    }
    fingerprint = operation_fingerprint(intent)
    manifest: dict[str, Any] | None = None
    replay = False
    for _attempt in range(16):
        current = store.get_research_project(project["id"])
        if not current:
            raise IntegrityError("UNKNOWN_PROJECT", f"unknown research project: {project_id}")
        existing = _manifest_operation(current, operation_id)
        if existing:
            if str(existing.get("operation_fingerprint") or "") != fingerprint:
                raise IntegrityError(
                    "FLOW_MANIFEST_IDEMPOTENCY_CONFLICT",
                    "operation_id was already used for a different flow manifest",
                )
            manifest, replay = existing, True
            break
        assets = {str(a.get("id") or ""): a for a in (current.get("assets") or [])}
        resolved_steps = []
        for index, raw in enumerate(raw_steps):
            asset = assets.get(raw["asset_version_id"])
            admission = (asset or {}).get("admission") or {}
            if (not asset or admission.get("schema") != REMOTE_SCREENSHOT_SCHEMA
                    or str(admission.get("workspace_id") or "") != workspace_id
                    or str(admission.get("project_id") or "") != project["id"]
                    or str(admission.get("run_id") or "") != run_id):
                raise IntegrityError(
                    "FLOW_MANIFEST_UNADMITTED_ASSET",
                    f"steps[{index}] is not a screenshot version admitted for this workspace/project/run",
                )
            if str(admission.get("target_revision") or "") != target_revision:
                raise IntegrityError(
                    "FLOW_MANIFEST_REVISION_MISMATCH",
                    f"steps[{index}] targets {admission.get('target_revision')!r}, not {target_revision!r}",
                )
            resolved_steps.append({
                "index": index,
                "asset_id": asset["id"],
                "asset_version_id": asset["id"],
                "content_digest": asset["content_digest"],
                "label": raw["label"],
                "caption": raw["label"],
                "url": asset.get("url", ""),
                "captured_at": admission["captured_at"],
            })
        lineage = [m for m in (current.get("flow_manifests") or [])
                   if str(m.get("flow_key") or "") == flow_key]
        version = max((int(m.get("version") or 0) for m in lineage), default=0) + 1
        previous = max(lineage, key=lambda m: int(m.get("version") or 0), default=None)
        manifest_id = stable_id(  # noqa: F821
            "flow", workspace_id, project["id"], run_id, flow_key, operation_id,
        )
        now = utc_now_iso()
        manifest = {
            **intent,
            "id": manifest_id,
            "version": version,
            "steps": resolved_steps,
            "operation_fingerprint": fingerprint,
            "supersedes": str((previous or {}).get("id") or ""),
            "created_at": now,
            "dispatch_provenance": {
                "state": "governed", "dispatch_token": dispatch_ctx["dispatch_token"],
                "run_id": run_id, "task_id": dispatch_ctx["task_id"],
            },
        }
        digest_payload = {k: v for k, v in manifest.items()
                          if k not in {"manifest_digest", "created_at", "dispatch_provenance"}}
        manifest["manifest_digest"] = "sha256:" + hashlib.sha256(
            json.dumps(digest_payload, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        updated = copy.deepcopy(current)
        updated.setdefault("flow_manifests", []).append(manifest)
        # Existing walkthrough readers consume project.flows.  Each projection
        # is itself immutable and carries the exact manifest id/version/digest.
        updated.setdefault("flows", []).append(copy.deepcopy(manifest))
        updated["updated_at"] = now
        if store.compare_and_swap_research_project(current, updated):
            break
        manifest = None
    if manifest is None:
        raise IntegrityError(
            "FLOW_MANIFEST_CONTENTION", "project changed repeatedly; retry the same operation_id",
        )
    dispatch = bind_dispatch_output(  # noqa: F821
        dispatch_ctx, {"kind": "flow", "id": manifest["id"]},
        "recorded immutable admitted screenshot flow manifest", store, complete=False,
    )
    return {**manifest, "idempotent_replay": replay, "dispatch": dispatch}


def list_flow_manifests(project_id: str, store: Store | None = None) -> list[dict[str, Any]]:
    store = store or Store()
    _remote_workspace()
    project = _require_research_project(store, project_id)  # noqa: F821
    rows = sorted(project.get("flow_manifests") or [],
                  key=lambda row: (str(row.get("flow_key") or ""), int(row.get("version") or 0)))
    # Lean index: exact full steps stay behind get_flow_manifest(id/version).
    return [{"id": row.get("id"), "flow_key": row.get("flow_key"),
             "title": row.get("title"), "version": row.get("version"),
             "manifest_digest": row.get("manifest_digest"),
             "target_revision": row.get("target_revision"),
             "captured_at": row.get("captured_at"),
             "steps": len(row.get("steps") or [])}
            for row in rows[-100:]]


def get_flow_manifest(project_id: str, manifest_id: str = "", flow_key: str = "",
                      version: int | None = None,
                      store: Store | None = None) -> dict[str, Any]:
    store = store or Store()
    _remote_workspace()
    project = _require_research_project(store, project_id)  # noqa: F821
    rows = list(project.get("flow_manifests") or [])
    if manifest_id:
        found = next((m for m in rows if str(m.get("id") or "") == manifest_id), None)
    elif flow_key and version is not None:
        found = next((m for m in rows if str(m.get("flow_key") or "") == flow_key
                      and int(m.get("version") or 0) == int(version)), None)
    else:
        raise IntegrityError(
            "FLOW_MANIFEST_BAD_INPUT", "pass manifest_id or the exact flow_key + version",
        )
    if not found:
        raise KeyError(f"Unknown flow manifest in project {project_id}")
    return {k: v for k, v in found.items() if k != "operation_fingerprint"}


def validate_product_understanding_manifest_binding(
    project: dict[str, Any],
    product_understanding: dict[str, Any],
    stimulus_manifest: dict[str, Any] | None,
    coverage_checklist: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    """Freeze one exact manifest/revision/coverage join into Product Understanding."""
    cited_flow_ids = {
        str(ref.get("id") or "")
        for group in (
            product_understanding.get("evidence_refs") or [],
            *[row.get("evidence_refs") or [] for row in product_understanding.get("routes") or []],
            *[row.get("evidence_refs") or [] for row in product_understanding.get("flows") or []],
            *[row.get("evidence_refs") or [] for row in product_understanding.get("states") or []],
            *[row.get("evidence_refs") or [] for row in product_understanding.get("capabilities") or []],
        )
        for ref in group
        if str(ref.get("kind") or "") == "flow"
    }
    cited_asset_ids = {
        str(ref.get("id") or "")
        for group in (
            product_understanding.get("evidence_refs") or [],
            *[row.get("evidence_refs") or [] for row in product_understanding.get("routes") or []],
            *[row.get("evidence_refs") or [] for row in product_understanding.get("flows") or []],
            *[row.get("evidence_refs") or [] for row in product_understanding.get("states") or []],
            *[row.get("evidence_refs") or [] for row in product_understanding.get("capabilities") or []],
        )
        for ref in group
        if str(ref.get("kind") or "") == "asset"
    }
    remote_citations = [m for m in (project.get("flow_manifests") or [])
                        if str(m.get("id") or "") in cited_flow_ids]
    remote_asset_citations = [
        asset for asset in (project.get("assets") or [])
        if str(asset.get("id") or "") in cited_asset_ids
        and ((asset.get("admission") or {}).get("schema") == REMOTE_SCREENSHOT_SCHEMA)
    ]
    if not stimulus_manifest:
        if remote_citations or remote_asset_citations:
            raise IntegrityError(
                "STIMULUS_MANIFEST_REQUIRED",
                "Product Understanding cites remote screenshots/flow and must freeze its exact manifest binding",
            )
        if coverage_checklist:
            raise IntegrityError("STIMULUS_MANIFEST_REQUIRED", "coverage_checklist requires a manifest")
        return {}
    if not isinstance(stimulus_manifest, dict):
        raise IntegrityError("STIMULUS_MANIFEST_BAD_REF", "stimulus_manifest must be an object")
    manifest_id = _required_text(stimulus_manifest.get("id"), "stimulus_manifest.id")
    try:
        version = int(stimulus_manifest.get("version"))
    except (TypeError, ValueError):
        raise IntegrityError("STIMULUS_MANIFEST_BAD_REF", "stimulus_manifest.version must be an integer") from None
    stored = next((m for m in (project.get("flow_manifests") or [])
                   if str(m.get("id") or "") == manifest_id
                   and int(m.get("version") or 0) == version), None)
    if not stored:
        raise IntegrityError(
            "STIMULUS_MANIFEST_VERSION_MISMATCH",
            "the exact stimulus manifest id/version is not admitted on this project",
        )
    declared_revision = _required_text(
        stimulus_manifest.get("target_revision"), "stimulus_manifest.target_revision",
    )
    declared_digest = _required_text(
        stimulus_manifest.get("manifest_digest"), "stimulus_manifest.manifest_digest",
    )
    if (declared_revision != str(stored.get("target_revision") or "")
            or declared_digest != str(stored.get("manifest_digest") or "")):
        raise IntegrityError(
            "STIMULUS_MANIFEST_VERSION_MISMATCH",
            "manifest revision/digest does not match the immutable admitted version",
        )
    if str(product_understanding.get("revision") or "") != declared_revision:
        raise IntegrityError(
            "PRODUCT_REVISION_MISMATCH",
            "Product Understanding revision must equal the frozen manifest target_revision",
        )
    if manifest_id not in cited_flow_ids:
        raise IntegrityError(
            "STIMULUS_MANIFEST_EVIDENCE_REQUIRED",
            "routes/flows/states/root evidence must cite the exact flow manifest id",
        )
    checklist = coverage_checklist or []
    if len(checklist) != len(stored.get("steps") or []):
        raise IntegrityError(
            "STIMULUS_COVERAGE_INCOMPLETE",
            "coverage_checklist must contain exactly one inspected entry per manifest step",
        )
    normalized: list[dict[str, Any]] = []
    seen: set[int] = set()
    for index, raw in enumerate(checklist):
        if not isinstance(raw, dict):
            raise IntegrityError("STIMULUS_COVERAGE_INCOMPLETE", f"coverage[{index}] must be an object")
        try:
            step_index = int(raw.get("step_index"))
        except (TypeError, ValueError):
            raise IntegrityError("STIMULUS_COVERAGE_INCOMPLETE", "coverage step_index must be an integer") from None
        if step_index in seen or not 0 <= step_index < len(stored["steps"]):
            raise IntegrityError("STIMULUS_COVERAGE_INCOMPLETE", "coverage step indexes must be exact and unique")
        seen.add(step_index)
        if str(raw.get("status") or "") != "inspected":
            raise IntegrityError(
                "STIMULUS_COVERAGE_INCOMPLETE",
                "every remote screenshot must be explicitly marked inspected before Reaction Test",
            )
        step = stored["steps"][step_index]
        refs = raw.get("evidence_refs") or []
        exact_ref = {"kind": "asset", "id": step["asset_version_id"]}
        if exact_ref not in [{"kind": str(r.get("kind") or ""), "id": str(r.get("id") or "")}
                             for r in refs if isinstance(r, dict)]:
            raise IntegrityError(
                "STIMULUS_COVERAGE_INCOMPLETE",
                f"coverage step {step_index} must cite exact asset version {step['asset_version_id']}",
            )
        normalized.append({
            "step_index": step_index,
            "status": "inspected",
            "label": step["label"],
            "asset_version_id": step["asset_version_id"],
            "content_digest": step["content_digest"],
            "evidence_refs": [exact_ref],
            "notes": str(raw.get("notes") or "").strip(),
        })
    normalized.sort(key=lambda row: row["step_index"])
    return {
        "schema": STIMULUS_BINDING_SCHEMA,
        "manifest_id": stored["id"],
        "manifest_version": stored["version"],
        "manifest_digest": stored["manifest_digest"],
        "target_revision": stored["target_revision"],
        "expected_task": stored["expected_task"],
        "captured_at": stored["captured_at"],
        "coverage_checklist": normalized,
    }
