from __future__ import annotations

import time
from typing import Any

from .. import services
from ._env import _env


def register_jobs(mcp):
    # ============ Jobs: presets + the "sharpen the question" helper (the taxonomy's JOB layer) ============
    # A Job preset is a thin RECIPE CARD derived from the canonical taxonomy (taxonomy.json via
    # job_taxonomy — one preset per website Job): it seeds a plan with the Framework, the suggested
    # Formats and the declared persona coverage. Presets are starting recipes, never constraints —
    # start_project still runs anything off-menu. See sonaloop/job_presets.py.
    @mcp.tool()
    def list_job_presets() -> dict[str, Any]:
        """The Job presets — one per named research Job (positioning, pricing, jtbd_demand, ideation_hmw,
        continuous_discovery, churn_reasons), each a recipe card that seeds a plan: the default Framework
        (plain-language description), the suggested Formats with their brief/record tools, and the declared
        persona coverage. Derived live from the canonical taxonomy; swappable and never enforced."""
        t = time.perf_counter()
        return _env("list_job_presets", services.list_job_presets(), t)

    @mcp.tool()
    def get_job_preset(job_id: str) -> dict[str, Any]:
        """One Job preset by stable taxonomy id (e.g. 'positioning'): framework + framework_options +
        formats (each with its brief/record tools) + coverage. A starting recipe — swap anything."""
        t = time.perf_counter()
        return _env("get_job_preset", services.get_job_preset(job_id), t)

    @mcp.tool()
    def sharpen_question(goal: str, answers: dict[str, str] | None = None,
                         job: str | None = None) -> dict[str, Any]:
        """Turn a FUZZY goal into a well-formed study — deterministically (no server-side text-LLM).
        Returns the well-formed-study checklist (decision at stake, audience, comparator, success signal)
        with per-field answer/hints/status, targeted clarifying_questions for the missing pieces, likely
        Job-preset matches (transparent keyword signals; override with `job=`), and a structured study_spec.
        YOU do the language work: ask the user the clarifying questions, then call again with
        answers={field_id: answer} until `ready` — then hand off via start_job_study (or start_project for
        an off-menu study)."""
        t = time.perf_counter()
        return _env("sharpen_question", services.sharpen_question(goal, answers, job), t)

    @mcp.tool()
    def start_job_study(job_id: str, title: str, goal: str, framework: str | None = None,
                        persona_ids: list[str] | None = None,
                        icon: str | dict[str, Any] | None = None) -> dict[str, Any]:
        """Start a study FROM a Job preset: seeds the plan through the preset's default Framework (or any
        `framework` override — presets never constrain) and stamps the Job on the project + plan so
        assess_coverage(job=...) and the inspector know the declared coverage. A convenience over
        start_project; drive the plan with the usual plan tools afterwards."""
        t = time.perf_counter()
        return _env("start_job_study", services.start_job_study(job_id, title, goal, framework,
                                                               persona_ids, icon=icon), t)
