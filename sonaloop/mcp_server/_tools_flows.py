from __future__ import annotations

import time
from typing import Any, TypedDict

from .. import services
from ._env import _env


class ReactionScreenRole(TypedDict):
    asset_version_id: str
    role: str


def register_flows(mcp):
    # == Screenshot flows: walkthrough with drop-off, artifact-first (docs/flow-walkthrough.md) ==
    @mcp.tool()
    def record_reaction_test_capture_review(
            project_id: str, capture_complete: bool,
            screen_roles: list[ReactionScreenRole], known_missing: list[str] | None,
            rationale: str, operation_id: str, dispatch_token: str) -> dict[str, Any]:
        """Review the exact currently admitted Reaction-Test screen inventory before a flow is
        frozen. Set capture_complete=false and name concrete known_missing routes/states to request
        another screenshot; set it true only when the inventory is sufficient for the user's task.
        screen_roles must cover every returned asset id exactly once and in order. The decision is
        immutable, bound to the exact byte digests and dispatch, and retry-safe by operation_id."""
        t = time.perf_counter()
        return _env(
            "record_reaction_test_capture_review",
            services.record_reaction_test_capture_review(
                project_id, capture_complete, screen_roles, known_missing,
                rationale, operation_id, dispatch_token,
            ),
            t,
        )

    @mcp.tool()
    def record_flow_manifest(project_id: str, run_id: str, operation_id: str,
                             flow_key: str, title: str, steps: list[dict[str, Any]],
                             expected_task: str, target_revision: str, captured_at: str,
                             dispatch_token: str = "") -> dict[str, Any]:
        """Append one immutable, versioned Remote-MCP screenshot-flow manifest. `steps` is
        ordered and each entry is {asset_version_id, label}; every id must be a screenshot
        admitted by admit_remote_screenshot for this authenticated workspace/project/run and
        exact target_revision. Reuse operation_id unchanged on retry. The returned id/version/
        manifest_digest is what Product Understanding must freeze and cover before personas react."""
        t = time.perf_counter()
        return _env("record_flow_manifest", services.record_flow_manifest(
            project_id=project_id, run_id=run_id, operation_id=operation_id,
            flow_key=flow_key, title=title, steps=steps, expected_task=expected_task,
            target_revision=target_revision, captured_at=captured_at,
            dispatch_token=dispatch_token), t)

    @mcp.tool()
    def list_flow_manifests(project_id: str) -> dict[str, Any]:
        """List immutable admitted screenshot-flow versions in the active workspace/project."""
        t = time.perf_counter()
        return _env("list_flow_manifests", services.list_flow_manifests(project_id), t)

    @mcp.tool()
    def get_flow_manifest(project_id: str, manifest_id: str = "", flow_key: str = "",
                          version: int | None = None) -> dict[str, Any]:
        """Read one exact flow-manifest version by manifest_id or flow_key + version."""
        t = time.perf_counter()
        return _env("get_flow_manifest", services.get_flow_manifest(
            project_id, manifest_id, flow_key, version), t)

    @mcp.tool()
    def define_flow(project_id: str, title: str, steps: list[dict[str, Any]],
                    key: str | None = None,
                    dispatch_token: str | None = None) -> dict[str, Any]:
        """Define an ORDERED flow from the project's screenshot assets — each step is
        {asset_id, caption?} (attach the screenshots first via attach_asset /
        attach_prototype_shot). The flow is what personas walk; no live browser anywhere.
        A stable `key` makes re-definition an idempotent upsert. In a governed run pass the issued
        dispatch_token; the flow is automatically linked to its task."""
        t = time.perf_counter()
        return _env("define_flow", services.define_flow(
            project_id, title, steps, key, dispatch_token=dispatch_token), t)

    @mcp.tool()
    def list_flows(project_id: str) -> dict[str, Any]:
        """Every defined flow on a project (id, title, step count)."""
        t = time.perf_counter()
        return _env("list_flows", services.list_flows(project_id), t)

    @mcp.tool()
    def brief_flow_walkthrough(persona_id: str, project_id: str, flow_id: str) -> dict[str, Any]:
        """GATHER one persona's artifact walkthrough: loaded persona context + the ordered
        screens (view_asset each — real pixels) + the authoring contract. YOU walk the flow
        as the persona and record the dual timeline with record_usability_session
        (subject={kind:'flow', id}, fidelity='artifact') — honest friction, the drop-off
        step with its reason, predicted_behaviors with canonical likelihoods."""
        t = time.perf_counter()
        return _env("brief_flow_walkthrough",
                    services.brief_flow_walkthrough(persona_id, project_id, flow_id), t)

    @mcp.tool()
    def flow_funnel(project_id: str, flow_id: str) -> dict[str, Any]:
        """The segment funnel of one flow: per step entered/continued/dropped with the drop
        reasons, the dropping personas and the step captions — where the cohort abandons
        and why, plus the biggest_dropoff headline."""
        t = time.perf_counter()
        return _env("flow_funnel", services.flow_funnel(project_id, flow_id), t)
