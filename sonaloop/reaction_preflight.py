"""One-action Reaction-Test setup routing for minimal and remote hosts.

The router is deliberately independent from any browser or provider. A URL is
target identity only; every state transition is derived from persisted,
project-owned evidence and the current immutable integrity records.
"""
from __future__ import annotations

import hashlib
import re
from typing import Any

from .storage import Store


REACTION_PREFLIGHT_ACTION_SCHEMA = "sonaloop.reaction_preflight_action.v1"
_PUBLIC_URL_RE = re.compile(r"https?://[^\s<>'\"()]+", re.IGNORECASE)


def _project_target_url(project: dict[str, Any]) -> str:
    """Extract target identity from authored project text without dereferencing it."""
    for value in (project.get("goal"), project.get("description"), project.get("title")):
        match = _PUBLIC_URL_RE.search(str(value or ""))
        if match:
            return match.group(0).rstrip(".,;:!?]}")[:2_000]
    return ""


def _current_product_dispatch(project_id: str, store: Store) -> dict[str, Any] | None:
    """The one active Product Understanding dispatch, if it has been issued."""
    rows: list[dict[str, Any]] = []
    for run in store.list_runs(project_id):
        if str(run.get("status") or "") != "active":
            continue
        rows.extend(
            {**row, "run_id": run.get("run_id")}
            for row in (run.get("dispatches") or [])
            if str(row.get("task_id") or "") == "preflight__product_understanding"
            and str(row.get("status") or "") == "issued"
        )
    return max(rows, key=lambda row: (str(row.get("issued_at") or ""),
                                      str(row.get("dispatch_token") or "")), default=None)


def _candidate_personas(store: Store) -> list[dict[str, str]]:
    """Bounded workspace-local choices; selection remains host-authored."""
    candidates: list[dict[str, str]] = []
    for persona in store.list_personas():
        role = persona.get("role") or {}
        segment = persona.get("segment") or {}
        candidates.append({
            "id": str(persona.get("id") or ""),
            "display_name": str(persona.get("display_name") or persona.get("name") or ""),
            "role": str(role.get("title") or "") if isinstance(role, dict) else str(role),
            "segment": " · ".join(
                str(value) for value in (segment.values() if isinstance(segment, dict) else [])
                if str(value).strip()
            )[:240],
        })
    return sorted((row for row in candidates if row["id"]),
                  key=lambda row: (row["display_name"].casefold(), row["id"]))[:50]


def _remote_manifest_state(project: dict[str, Any]) -> tuple[
        list[dict[str, Any]], list[dict[str, Any]], dict[str, Any] | None]:
    """Return the current remote revision's screens and its exact matching manifest.

    A later admitted screen or target revision invalidates an older manifest.  We
    never silently interpret only the subset that happened to be frozen first.
    """
    remote = [
        row for row in (project.get("assets") or [])
        if ((row.get("admission") or {}).get("schema")
            == "sonaloop.remote_screenshot_admission.v1")
    ]
    if not remote:
        return [], [], None
    selected_revision = str((remote[-1].get("admission") or {}).get("target_revision") or "")
    selected = [
        row for row in remote
        if str((row.get("admission") or {}).get("target_revision") or "")
        == selected_revision
    ]
    expected_ids = [str(row.get("id") or "") for row in selected]
    matches = [
        manifest for manifest in (project.get("flow_manifests") or [])
        if str(manifest.get("target_revision") or "") == selected_revision
        and [str(step.get("asset_version_id") or "")
             for step in (manifest.get("steps") or [])] == expected_ids
    ]
    matching = max(matches, key=lambda row: (int(row.get("version") or 0),
                                              str(row.get("created_at") or "")), default=None)
    return remote, selected, matching


def _capture_operation_id(project_id: str, selected: list[dict[str, Any]]) -> str:
    basis = "|".join([project_id, *[str(row.get("id") or "") for row in selected]])
    return "reaction-screen:" + hashlib.sha256(basis.encode("utf-8")).hexdigest()[:24]


def _matching_capture_review(project: dict[str, Any], selected: list[dict[str, Any]]) \
        -> dict[str, Any] | None:
    exact = [{"asset_version_id": str(row.get("id") or ""),
              "content_digest": str(row.get("content_digest") or "")}
             for row in selected]
    matches = [row for row in (project.get("reaction_capture_reviews") or [])
               if row.get("assets") == exact]
    return max(matches, key=lambda row: (int(row.get("version") or 0),
                                         str(row.get("created_at") or "")), default=None)


def reaction_preflight_action(project_id: str, store: Store) -> dict[str, Any] | None:
    """Return exactly one deterministic Reaction-Test remediation."""
    # Lazy import keeps the compatibility re-export in research_integrity free
    # of an import cycle while leaving all evidence semantics in one authority.
    from .research_integrity import (
        admitted_stimuli,
        current_product_understanding,
        is_reaction_project,
    )

    project = store.get_research_project(project_id) or {}
    plan = store.get_research_plan(project_id) or {}
    if not project or not is_reaction_project(project, plan):
        return None
    target_url = _project_target_url(project)
    target = {
        "url": target_url,
        "role": "target_identity_only",
        "is_evidence": False,
        "server_fetch_authorized": False,
    }
    stimuli = admitted_stimuli(project_id, store)
    base = {
        "schema": REACTION_PREFLIGHT_ACTION_SCHEMA,
        "project_id": project_id,
        "blocked": True,
        "target": target,
        "pending_blockers": {
            "stimulus_missing": not bool(stimuli),
            "cohort_too_small": len(project.get("persona_ids") or []) < 2,
        },
    }
    if not stimuli:
        return {
            **base,
            "kind": "stimulus_required",
            "code": "REACTION_STIMULUS_REQUIRED",
            "message": (
                "The URL identifies the target but is not screenshot, route, state or observed-use "
                "evidence. Upload real screenshot bytes; Sonaloop will not fetch the URL."
            ),
            "allowed_tools": ["admit_remote_screenshot"],
            "next_call": {
                "tool": "admit_remote_screenshot",
                "arguments": {
                    "project_id": project_id,
                    "run_id": "<run_step.run_id>",
                    "operation_id": _capture_operation_id(project_id, []),
                    "content_base64": "<actual PNG/JPEG/WebP screenshot bytes>",
                    "filename": "<original .png/.jpg/.webp filename matching the bytes>",
                    "media_type": "<image/png|image/jpeg|image/webp matching the bytes>",
                    "captured_at": "<ISO-8601 capture time>",
                    "target_revision": "<release/hash or explicit unknown>",
                    "label": "<what this exact screen shows>",
                    "dispatch_token": "<run_step.dispatch_token>",
                },
            },
        }

    remote_assets, selected_assets, current_manifest = _remote_manifest_state(project)
    capture_review = _matching_capture_review(project, selected_assets)
    if remote_assets and capture_review is None:
        return {
            **base,
            "kind": "capture_review_required",
            "code": "REACTION_CAPTURE_REVIEW_REQUIRED",
            "message": (
                "Review the current screen inventory before freezing it. Default to capture_more "
                "unless it covers the task's meaningful entry, interaction and outcome/error states."
            ),
            "allowed_tools": ["record_reaction_test_capture_review"],
            "admitted_screens": [
                {"asset_version_id": row.get("id"),
                 "label": row.get("label") or row.get("title")}
                for row in selected_assets
            ],
            "next_call": {
                "tool": "record_reaction_test_capture_review",
                "arguments": {
                    "project_id": project_id,
                    "capture_complete": "<true only if this inventory is sufficient; otherwise false>",
                    "screen_roles": [
                        {"asset_version_id": row.get("id"),
                         "role": "<what task state this exact screen covers>"}
                        for row in selected_assets
                    ],
                    "known_missing": [],
                    "rationale": "<why to capture more or why this exact inventory is sufficient>",
                    "operation_id": "capture-review:" + hashlib.sha256(
                        "|".join(str(row.get("id") or "") for row in selected_assets)
                        .encode("utf-8")
                    ).hexdigest()[:24],
                    "dispatch_token": "<run_step.dispatch_token>",
                },
            },
        }
    if remote_assets and str((capture_review or {}).get("status") or "") == "capture_more":
        return {
            **base,
            "kind": "stimulus_required",
            "stage": "capture_more",
            "code": "REACTION_ADDITIONAL_STIMULUS_REQUIRED",
            "message": "Capture the next missing route/state from the reviewed inventory.",
            "known_missing": list((capture_review or {}).get("known_missing") or []),
            "allowed_tools": ["admit_remote_screenshot"],
            "next_call": {
                "tool": "admit_remote_screenshot",
                "arguments": {
                    "project_id": project_id,
                    "run_id": "<run_step.run_id>",
                    "operation_id": _capture_operation_id(project_id, selected_assets),
                    "content_base64": "<actual PNG/JPEG/WebP screenshot bytes>",
                    "filename": "<original .png/.jpg/.webp filename matching the bytes>",
                    "media_type": "<image/png|image/jpeg|image/webp matching the bytes>",
                    "captured_at": "<ISO-8601 capture time>",
                    "target_revision": str((selected_assets[-1].get("admission") or {}).get(
                        "target_revision") or "<release/hash or explicit unknown>"),
                    "label": "<what this exact screen shows>",
                    "dispatch_token": "<run_step.dispatch_token>",
                },
            },
        }
    if remote_assets and current_manifest is None:
        revisions = sorted({str((row.get("admission") or {}).get("target_revision") or "")
                            for row in remote_assets})
        selected_revision = str((selected_assets[-1].get("admission") or {}).get(
            "target_revision") or "")
        selected_captured_at = max(
            (str((row.get("admission") or {}).get("captured_at") or "")
             for row in selected_assets),
            default="",
        )
        return {
            **base,
            "kind": "flow_manifest_required",
            "code": "REACTION_FLOW_MANIFEST_REQUIRED",
            "message": "Freeze the ordered admitted screenshot versions before interpreting them.",
            "allowed_tools": ["record_flow_manifest"],
            "admitted_screens": [
                {"asset_version_id": row.get("id"), "label": row.get("label") or row.get("title")}
                for row in selected_assets
            ],
            "target_revisions": revisions,
            "selected_target_revision": selected_revision,
            "excluded_other_revision_asset_ids": [
                row.get("id") for row in remote_assets if row not in selected_assets
            ],
            "next_call": {
                "tool": "record_flow_manifest",
                "arguments": {
                    "project_id": project_id,
                    "run_id": "<run_step.run_id>",
                    "operation_id": "<stable flow intent; reuse on retry>",
                    "flow_key": "primary-stimulus",
                    "title": "Primary stimulus flow",
                    "steps": [
                        {"asset_version_id": row.get("id"),
                         "label": row.get("label") or row.get("title")}
                        for row in selected_assets
                    ],
                    "expected_task": str(project.get("goal") or "Reaction Test"),
                    "target_revision": selected_revision,
                    "captured_at": selected_captured_at,
                    "dispatch_token": "<run_step.dispatch_token>",
                },
            },
        }

    understanding = current_product_understanding(project)
    if not understanding and current_manifest:
        manifest = current_manifest
        dispatch = _current_product_dispatch(project_id, store) or {}
        receipts = dict(dispatch.get("progress_receipts") or {})
        served: set[tuple[str, int, str]] = set()
        for step in manifest.get("steps") or []:
            asset_id = str(step.get("asset_version_id") or "")
            asset = next((row for row in selected_assets
                          if str(row.get("id") or "") == asset_id), {})
            key = f"reaction-screen:{manifest.get('id')}:{int(step.get('index') or 0)}"
            receipt = dict(receipts.get(key) or {})
            if (receipt.get("kind") == "reaction_screen_served"
                    and str(receipt.get("result_digest") or "")
                    == str(asset.get("content_digest") or "")):
                served.add((str(manifest.get("id") or ""),
                            int(step.get("index") or 0), asset_id))
        pending_step: dict[str, Any] | None = None
        for step in manifest.get("steps") or []:
            asset_id = str(step.get("asset_version_id") or "")
            receipt_key = (str(manifest.get("id") or ""),
                           int(step.get("index") or 0), asset_id)
            if receipt_key not in served:
                pending_step = step
                break
        if pending_step is not None:
            return {
                **base,
                "kind": "product_understanding_required",
                "stage": "inspect_screen",
                "code": "REACTION_SCREEN_INSPECTION_REQUIRED",
                "message": "Inspect the next exact manifest screen; the server records a version-bound receipt.",
                "allowed_tools": ["inspect_reaction_test_screen"],
                "manifest": {
                    "id": manifest.get("id"), "version": manifest.get("version"),
                    "target_revision": manifest.get("target_revision"),
                    "manifest_digest": manifest.get("manifest_digest"),
                    "steps_total": len(manifest.get("steps") or []),
                    "steps_served": len(served),
                },
                "next_call": {
                    "tool": "inspect_reaction_test_screen",
                    "arguments": {
                        "project_id": project_id,
                        "manifest_id": manifest.get("id"),
                        "step_index": pending_step.get("index"),
                        "asset_id": pending_step.get("asset_version_id"),
                        "dispatch_token": "<run_step.dispatch_token>",
                    },
                },
            }
        return {
            **base,
            "kind": "product_understanding_required",
            "stage": "record_observations",
            "code": "REACTION_PRODUCT_UNDERSTANDING_REQUIRED",
            "message": (
                "Every exact screenshot now has a server receipt. Submit one flat visible-state "
                "observation per manifest step; the server builds the immutable artifact."
            ),
            "allowed_tools": ["record_manifest_product_understanding"],
            "manifest": {
                "id": manifest.get("id"), "version": manifest.get("version"),
                "target_revision": manifest.get("target_revision"),
                "manifest_digest": manifest.get("manifest_digest"),
                "steps": [{"step_index": row.get("index"),
                           "asset_version_id": row.get("asset_version_id"),
                           "label": row.get("label")} for row in manifest.get("steps") or []],
            },
            "next_call": {
                "tool": "record_manifest_product_understanding",
                "arguments": {
                    "project_id": project_id,
                    "manifest_id": manifest.get("id"),
                    "observations": [
                        {"step_index": row.get("index"),
                         "visible_observation":
                             f"<what is visibly present on {row.get('label') or 'this screen'}>"}
                        for row in manifest.get("steps") or []
                    ],
                    "unknown_capabilities": ["<important capability not verifiable from these screens>"],
                    "target_name": str(project.get("title") or ""),
                    "target_url": target_url,
                    "dispatch_token": "<run_step.dispatch_token>",
                },
            },
        }

    if not understanding:
        return {
            **base,
            "kind": "product_understanding_required",
            "code": "REACTION_PRODUCT_UNDERSTANDING_REQUIRED",
            "message": "Inspect the admitted project evidence and record an honest Product Understanding.",
            "allowed_tools": ["brief_product_understanding"],
            "next_call": {"tool": "brief_product_understanding",
                          "arguments": {"project_id": project_id}},
            "note": (
                "This is the executable compatibility path for admitted non-remote evidence; "
                "the brief returns the complete rich recorder contract."
            ),
        }

    # Product truth is now frozen and its dispatch is complete. Selection is a
    # supporting write on the following frame dispatch; the cohort gate itself
    # remains in its methodology-declared position after that frame.
    if len(project.get("persona_ids") or []) < 2:
        candidates = _candidate_personas(store)
        if len(candidates) < 2:
            return {
                **base,
                "kind": "cohort_catalog_required",
                "code": "REACTION_COHORT_CATALOG_REQUIRED",
                "message": "Fewer than two existing workspace personas are available; find candidates first.",
                "allowed_tools": ["catalog_search"],
                "candidate_personas": candidates,
                "next_call": {
                    "tool": "catalog_search",
                    "arguments": {"query": str(project.get("goal") or project.get("title") or "")[:500]},
                },
            }
        return {
            **base,
            "kind": "cohort_selection_required",
            "code": "REACTION_COHORT_REQUIRED",
            "message": "Select at least two existing, independent personas before framing reactions.",
            "allowed_tools": [
                "catalog_search", "catalog_recommend", "catalog_pull",
                "select_reaction_test_cohort",
            ],
            "minimum_personas": 2,
            "candidate_personas": candidates,
            "authoring_contract": {
                "persona_ids": "Choose at least two IDs only from candidate_personas.",
                "selection_rationale": "Explain the independent contrast in at least 12 characters.",
            },
            "next_call": {
                "tool": "select_reaction_test_cohort",
                "arguments": {
                    "project_id": project_id,
                    "persona_ids": [],
                    "selection_rationale": "",
                    "operation_id": "<stable selection intent; reuse on retry>",
                    "dispatch_token": "<run_step.dispatch_token>",
                },
            },
        }
    return None
