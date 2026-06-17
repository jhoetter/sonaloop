from __future__ import annotations

import time
from typing import Any

from ..config import MEMORY_SCHEMA_VERSION, load_env
from .. import services
from ..avatar import generate_persona_avatar
from ._env import _NEXT, SERVER_VERSION, _env
from ._catalogue import catalogue_data  # public: API-docs / tool-reference generation

#: Public alias for the MCP tool-response envelope builder, used by extension tools
#: (sonaloop-cloud) to wrap their tool results the same way the core tools do.
tool_response = _env
from ._tools_personas import register_personas
from ._tools_catalog import register_catalog
from ._tools_taxonomy import register_taxonomy
from ._tools_simulation import register_simulation
from ._tools_eval import register_eval
from ._tools_research import register_research
from ._tools_methodology import register_methodologies
from ._tools_jobs import register_jobs
from ._tools_plan import register_plan
from ._tools_prototypes import register_prototypes
from ._tools_surveys import register_surveys
from ._tools_hypotheses import register_hypotheses
from ._tools_decisions import register_decisions
from ._tools_usability import register_usability
from ._tools_walkthrough import register_walkthrough
from ._tools_council import register_council
from ._tools_ideation import register_ideation
from ._tools_sections import register_sections
from ._tools_hooks import register_hooks
from ._tools_assets import register_assets
from ._tools_substrate import register_substrate
from ._tools_grounding import register_grounding
from ._tools_predictions import register_predictions
from ._tools_calibration import register_calibration
from ._tools_flows import register_flows
from ._tools_examples import register_examples
from ._tools_retrieval import register_retrieval


def _load_tool_extensions(mcp) -> int:
    """The MCP counterpart of the web-extension and hooks seams: discover the
    `sonaloop.mcp.tools` entry-point group and run each `register(mcp)`, so private
    packages (sonaloop-cloud, sonaloop-research) put their tools on the SAME server
    without the core importing them. A broken extension is logged and skipped."""
    import logging
    loaded = 0
    try:
        from importlib.metadata import entry_points
        for ep in entry_points(group="sonaloop.mcp.tools"):
            try:
                ep.load()(mcp)
                loaded += 1
            except Exception as exc:
                logging.getLogger("sonaloop.mcp").warning(
                    "MCP tool extension %r failed to load: %s", ep.name, exc)
    except Exception as exc:
        logging.getLogger("sonaloop.mcp").warning("MCP tool entry-point discovery failed: %s", exc)
    return loaded


def build_server():
    from mcp.server.fastmcp import FastMCP
    from ._prompts import SERVER_INSTRUCTIONS, register_prompts

    # `instructions` rides the initialize response so EVERY host (Claude, Cursor, ChatGPT, …) gets the
    # operating contract — the provider-agnostic counterpart to the Claude-only claude-skills/.
    mcp = FastMCP("sonaloop", instructions=SERVER_INSTRUCTIONS)

    register_personas(mcp)
    register_catalog(mcp)
    register_taxonomy(mcp)
    register_simulation(mcp)
    register_eval(mcp)
    register_research(mcp)
    register_methodologies(mcp)
    register_jobs(mcp)
    register_plan(mcp)
    register_prototypes(mcp)
    register_surveys(mcp)
    register_hypotheses(mcp)
    register_decisions(mcp)
    register_usability(mcp)
    register_walkthrough(mcp)
    register_council(mcp)
    register_ideation(mcp)
    register_sections(mcp)
    register_hooks(mcp)
    register_assets(mcp)
    register_substrate(mcp)
    register_grounding(mcp)
    register_predictions(mcp)
    register_calibration(mcp)
    register_flows(mcp)
    register_examples(mcp)
    register_retrieval(mcp)

    # Directory gate: every core tool gets its title + read-only/destructive/open-world
    # hints from the central registry (one place, CI-linted by tests/test_mcp_annotations.py).
    from ._annotations import apply_annotations
    apply_annotations(mcp)

    register_prompts(mcp)
    _load_tool_extensions(mcp)

    from ._catalogue import catalogue_md

    @mcp.resource("sonaloop://guide/catalogue")
    def catalogue_guide() -> str:
        """A browsable, by-domain index of EVERY tool (auto-generated from the live modules)."""
        return catalogue_md()

    return mcp


def main() -> None:
    load_env()
    try:
        mcp = build_server()
    except ImportError as exc:
        raise SystemExit("Install MCP dependencies first: uv sync") from exc
    mcp.run()


if __name__ == "__main__":
    main()
