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
