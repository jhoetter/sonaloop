from __future__ import annotations

import time
from typing import Any

from .. import services
from ._env import _env


def register_research(mcp):
    # ----- Research graph: Project container + typed study edges + theme tags -----
    @mcp.tool()
    def create_research_project(title: str, goal: str = "", persona_ids: list[str] | None = None,
                                description: str = "",
                                icon: str | dict[str, Any] | None = None) -> dict[str, Any]:
        """Create a research Project: a themed GRAPH of studies (syntheses). Distinct from
        the memory get_project (a persona's own work project). `icon` may be an existing icon
        name, 'random', or {kind:'custom', svg:'...'}."""
        t = time.perf_counter()
        return _env("create_research_project",
                    services.create_research_project(title, goal, persona_ids, description,
                                                     icon=icon), t)

    @mcp.tool()
    def list_research_projects() -> dict[str, Any]:
        """List research projects (graph containers) with study/edge/theme counts."""
        t = time.perf_counter()
        return _env("list_research_projects", services.list_research_projects(), t)

    @mcp.tool()
    def available_project_icons() -> dict[str, Any]:
        """Existing regular icons that Projects/Jobs can choose at initialization or edit time."""
        t = time.perf_counter()
        return _env("available_project_icons", services.available_project_icons(), t)

    @mcp.tool()
    def set_project_icon(project_id: str, icon: str | None = None, svg: str | None = None,
                         randomize: bool = False) -> dict[str, Any]:
        """Replace a Project/Job icon. Use `icon=<existing name>`, `randomize=True`, or pass a
        custom `svg` string; custom SVGs are sanitized, saved under data/project-icons, and
        assigned to the project."""
        t = time.perf_counter()
        return _env("set_project_icon",
                    services.set_project_icon(project_id, icon, svg=svg, randomize=randomize), t)

    @mcp.tool()
    def generate_project_icon(project_id: str, prompt: str = "") -> dict[str, Any]:
        """Create a fitting custom SVG icon for a Project/Job from its title/goal plus an optional
        prompt, save it as an SVG file, and assign it."""
        t = time.perf_counter()
        return _env("generate_project_icon", services.generate_project_icon(project_id, prompt), t)

    @mcp.tool()
    def get_project_graph(project_id: str) -> dict[str, Any]:
        """The core navigation call: nodes (studies + theme tags + sentiment), typed edges,
        themes, build order, and open questions for one research project."""
        t = time.perf_counter()
        return _env("get_project_graph", services.get_project_graph(project_id), t)

    # M1 — the pre-HX3 constellation study-graph tools (add_study_to_project / set_study_themes /
    # link_studies) are RETIRED from the agent surface: the plan engine (add_task / link_evidence /
    # record_frame) is the single graph-building path. The service fns remain for internal callers +
    # the CLI (spec/mcp-surface-cleanup.md M1).

    @mcp.tool()
    def record_open_questions(project_id: str, questions: list[str], study_id: str | None = None) -> dict[str, Any]:
        """Promote open questions raised by a study into first-class graph nodes."""
        t = time.perf_counter()
        return _env("record_open_questions", {"open_questions": services.record_open_questions(project_id, questions, study_id)}, t)

    @mcp.tool()
    def get_research_frontier(project_id: str) -> dict[str, Any]:
        """The anti-explosion surface: the project's still-open questions + structural notes."""
        t = time.perf_counter()
        return _env("get_research_frontier", services.get_research_frontier(project_id), t)

    # backfill_project_from_syntheses fully RETIRED (a one-time study-graph migration).

    # ----- Project REPORT: a project-scope synthesis over the whole graph (one concept; export via
    #       export_synthesis(report_id)). A report is short or exhaustive — just block count, not a type.
    @mcp.tool()
    def brief_synthesis_outline(project_id: str) -> dict[str, Any]:
        """GATHER the whole project graph + study content so you can author the project REPORT outline."""
        t = time.perf_counter()
        return _env("brief_synthesis_outline", services.brief_synthesis_outline(project_id), t)

    @mcp.tool()
    def record_synthesis_outline(project_id: str, outline: dict[str, Any],
                                 report_id: str | None = None,
                                 operation_id: str | None = None,
                                 dispatch_token: str | None = None) -> dict[str, Any]:
        """Persist the host-authored report outline (sections derived from the graph). A body-empty
        scaffold is reused; pass report_id to target a draft, reuse operation_id on transport retries,
        and pass the governed hand-off dispatch_token. The outline does not checkpoint until every
        section is authored."""
        t = time.perf_counter()
        return _env("record_synthesis_outline", services.record_synthesis_outline(
            project_id, outline, report_id=report_id, operation_id=operation_id,
            dispatch_token=dispatch_token), t)

    @mcp.tool()
    def brief_synthesis_section(project_id: str, section_id: str, report_id: str | None = None) -> dict[str, Any]:
        """GATHER one section's source studies (+ councils) so you can author it with citations."""
        t = time.perf_counter()
        return _env("brief_synthesis_section", services.brief_synthesis_section(project_id, section_id, report_id), t)

    @mcp.tool()
    def suggest_chart_kinds() -> dict[str, Any]:
        """Which report CHART to use when (bar, pie, stacked_bar, diverging_bar, gauge, dot_plot,
        heatmap, line, effort_impact) + each one's author payload shape — so you can pick the chart
        that fits the point before attaching it as a section figure. Recommendations, not constraints."""
        t = time.perf_counter()
        return _env("suggest_chart_kinds", services.suggest_chart_kinds(), t)

    @mcp.tool()
    def record_synthesis_section(project_id: str, section_id: str, content: dict[str, Any],
                                 report_id: str | None = None,
                                 dispatch_token: str | None = None) -> dict[str, Any]:
        """Persist one authored report section. `content`: {markdown, citations:[{study_id|council_id}],
        figures:[…]}. Figures can embed a chart — {kind:'chart', of:'<of>', series:[…], caption?} — to
        visualize the point; call suggest_chart_kinds for which `of` fits and its series shape."""
        t = time.perf_counter()
        return _env("record_synthesis_section", services.record_synthesis_section(
            project_id, section_id, content, report_id, dispatch_token=dispatch_token), t)

    # ----- Deletes (CRUD complete; MCP/CLI-only, never the read-only UI). Relocated here (M3): these
    # are research-artifact deletions (project/synthesis/council/persona), not prototype tools. -----
    @mcp.tool()
    def delete_research_project(project_id: str) -> dict[str, Any]:
        """Delete a project and its project-scoped outputs; personas and their memory remain."""
        t = time.perf_counter()
        return _env("delete_research_project", services.delete_research_project(project_id), t)

    @mcp.tool()
    def delete_synthesis(synthesis_id: str) -> dict[str, Any]:
        """Delete a synthesis (study) and detach it from any project graphs."""
        t = time.perf_counter()
        return _env("delete_synthesis", services.delete_synthesis(synthesis_id), t)

    @mcp.tool()
    def delete_council(session_id: str) -> dict[str, Any]:
        """Delete a council session."""
        t = time.perf_counter()
        return _env("delete_council", services.delete_council(session_id), t)

    @mcp.tool()
    def delete_persona(persona_id: str) -> dict[str, Any]:
        """Delete a persona + all its persona-scoped rows and rendered SOUL/avatar files."""
        t = time.perf_counter()
        return _env("delete_persona", services.delete_persona(persona_id), t)
