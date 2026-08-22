from __future__ import annotations

import time
from typing import Any

from .. import services
from ._env import _env


def register_handoff(mcp):
    @mcp.tool()
    def get_design_handoff(project_id: str, synthesis_id: str | None = None,
                           prototype_id: str | None = None, max_findings: int = 30,
                           max_voices: int = 24) -> dict[str, Any]:
        """Read a provider-neutral research-to-design bundle for Figma, canvas, code or document
        MCPs: evidence-linked findings/voices, decisions, concepts, mockups, screens, test outcomes
        and workspace design tokens. This tool never contacts or writes to the destination."""
        t = time.perf_counter()
        return _env("get_design_handoff", services.get_design_handoff(
            project_id, synthesis_id, prototype_id, max_findings, max_voices), t)

    @mcp.tool()
    def brief_presentation(synthesis_id: str, audience: str = "stakeholder",
                           duration_minutes: int = 10) -> dict[str, Any]:
        """Gather the report, cohort, evidence, visuals, result schemas and the selected
        methodology's data-authored deck profile. Author a presentation_plan.v1 from this brief;
        do not summarize report sections mechanically."""
        t = time.perf_counter()
        return _env("brief_presentation", services.brief_presentation(
            synthesis_id, audience, duration_minutes), t)

    @mcp.tool()
    def record_presentation_plan(synthesis_id: str, plan: dict[str, Any],
                                 operation_id: str | None = None) -> dict[str, Any]:
        """Persist an evidence-linked, brand-neutral presentation plan with core slides,
        appendix and speaker notes. The deterministic PPTX export reuses this reviewed plan
        in the workspace's active PowerPoint master."""
        t = time.perf_counter()
        return _env("record_presentation_plan", services.record_presentation_plan(
            synthesis_id, plan, operation_id), t)
