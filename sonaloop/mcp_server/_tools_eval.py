from __future__ import annotations

import time
from typing import Any

from .. import services
from ._env import _env


def register_eval(mcp):
    # ================= World, evolution, anomalies, eval =================
    @mcp.tool()
    def set_world_context(items: list[dict[str, Any]]) -> dict[str, Any]:
        """Set exogenous backdrop facts (season, regulation, market...). Not shared persona knowledge."""
        t = time.perf_counter()
        return _env("set_world_context", services.set_world_context(items), t)

    @mcp.tool()
    def get_world_context(as_of: str | None = None) -> dict[str, Any]:
        """The shared world context (macro facts personas live in) valid at a given date."""
        t = time.perf_counter()
        return _env("get_world_context", services.get_world_context(as_of), t)

    @mcp.tool()
    def get_language() -> dict[str, Any]:
        """Read the active content language (host-authored text) and UI language."""
        from ..config import content_language, ui_language
        t = time.perf_counter()
        return _env("get_language", {"content_language": content_language(), "ui_language": ui_language()}, t)

    @mcp.tool()
    def set_language(content_language: str | None = None, ui_language: str | None = None) -> dict[str, Any]:
        """Set the content language (de|en) for generated text and/or the web UI
        language. By default content is authored in the language the user writes in;
        use this to override. Returns the resulting settings."""
        from .. import config as _cfg
        t = time.perf_counter()
        if content_language:
            _cfg.set_content_language(content_language, also_ui=ui_language is None)
        if ui_language:
            _cfg.set_ui_language(ui_language)
        return _env("set_language", {"content_language": _cfg.content_language(), "ui_language": _cfg.ui_language()}, t)

    @mcp.tool()
    def brief_persona_revision(persona_id: str, date: str | None = None) -> dict[str, Any]:
        """GATHER evidence (digests/facts) to propose SLOW identity drift. Change is the exception."""
        t = time.perf_counter()
        return _env("brief_persona_revision", services.brief_persona_revision(persona_id, date), t)

    @mcp.tool()
    def record_persona_revision(persona_id: str, revision: dict[str, Any]) -> dict[str, Any]:
        """Persist evidence-backed identity drift (re-renders SOUL); source identity preserved."""
        t = time.perf_counter()
        return _env("record_persona_revision", services.record_persona_revision(persona_id, revision), t)

    @mcp.tool()
    def list_persona_revisions(persona_id: str) -> dict[str, Any]:
        """The history of evidence-backed identity revisions for a persona."""
        t = time.perf_counter()
        return _env("list_persona_revisions", services.list_persona_revisions(persona_id), t)

    @mcp.tool()
    def list_memory_anomalies(persona_id: str | None = None) -> dict[str, Any]:
        """Flagged memory anomalies (contradictions / integrity issues), optionally per persona."""
        t = time.perf_counter()
        return _env("list_memory_anomalies", services.list_memory_anomalies(persona_id), t)

    @mcp.tool()
    def evaluate_simulation(persona_id: str | None = None, start: str | None = None, end: str | None = None) -> dict[str, Any]:
        """Run the quality harness (uniformity, repetition, continuity, project movement,
        consistency, anti-steering). Returns green/warn/red — the measurable 'top' bar."""
        t = time.perf_counter()
        return _env("evaluate_simulation", services.evaluate_simulation(persona_id, start, end), t)

    # ----- F2 LLM critic (semantic eval) -----
    @mcp.tool()
    def brief_eval_critic(persona_id: str, start: str | None = None, end: str | None = None, sample_k: int | None = None) -> dict[str, Any]:
        """GATHER source+SOUL+sampled activities+arcs for a semantic critique. Author a
        verdict (anti_steering/in_character/dialogue/arc/mundane 0-5 + flags) then record.
        sample_k/threshold default from config (PERSONA_COUNCIL_CRITIC_SAMPLE_K / _THRESHOLD)."""
        t = time.perf_counter()
        return _env("brief_eval_critic", services.brief_eval_critic(persona_id, start, end, sample_k), t)

    @mcp.tool()
    def record_eval_critic(persona_id: str, verdict: dict[str, Any], start: str | None = None, end: str | None = None) -> dict[str, Any]:
        """Persist the host-authored critic verdict; flags low dimensions + items as anomalies."""
        t = time.perf_counter()
        return _env("record_eval_critic", services.record_eval_critic(persona_id, verdict, start, end), t)

    @mcp.tool()
    def evaluate_simulation_full(persona_id: str, start: str | None = None, end: str | None = None) -> dict[str, Any]:
        """Combined 'top' verdict: structural harness + latest LLM critic (definition v2)."""
        t = time.perf_counter()
        return _env("evaluate_simulation_full", services.evaluate_simulation_full(persona_id, start, end), t)

    # ----- Cohort quality: diversity gate + cross-persona critic -----
    @mcp.tool()
    def evaluate_cohort_diversity(persona_ids: list[str] | None = None) -> dict[str, Any]:
        """Structural bulk-generation gate: flag near-duplicate personas and implausibly
        uniform cohorts (Jaccard over segment/role/pains/goals/tools). No authoring needed."""
        t = time.perf_counter()
        return _env("evaluate_cohort_diversity", services.evaluate_cohort_diversity(persona_ids), t)

    @mcp.tool()
    def brief_cohort_critic(persona_ids: list[str] | None = None, start: str | None = None, end: str | None = None) -> dict[str, Any]:
        """GATHER compact per-persona records across the cohort so you can judge which
        personas fall OUT of the cohort's range (relative outliers / clones). Then record."""
        t = time.perf_counter()
        return _env("brief_cohort_critic", services.brief_cohort_critic(persona_ids, start, end), t)

    @mcp.tool()
    def record_cohort_critic(verdict: dict[str, Any]) -> dict[str, Any]:
        """Persist the host-authored cohort critique (outliers + cohort_note) as an eval
        report + an anomaly per flagged outlier persona."""
        t = time.perf_counter()
        return _env("record_cohort_critic", services.record_cohort_critic(verdict), t)

    # ----- ESV §B: adversarial completeness/quality critic (gates "done") -----
    @mcp.tool()
    def brief_completeness_critic(project_id: str) -> dict[str, Any]:
        """GATHER a computed exhaustiveness snapshot for an INDEPENDENT critic: coverage + the
        generative breadth_candidates (segments/angles/concepts/risks/fidelity-rungs missing) + novelty
        + groundedness + finish + the rubric. The critic scores each dimension + lists concrete `missing`
        work; the driver turns each into real work and re-runs until dry."""
        t = time.perf_counter()
        return _env("brief_completeness_critic", services.brief_completeness_critic(project_id), t)

    @mcp.tool()
    def record_completeness_critic(project_id: str, verdict: dict[str, Any],
                                   run_id: str, operation_id: str) -> dict[str, Any]:
        """Persist the independent critic verdict {scores, passed, missing[{kind,what,why,
        suggested_action}], rationale, evidence_refs}. Bind it to the run and reuse the deterministic
        operation_id returned by the critic dispatch on retries. Honesty gate: cannot be passed=true
        while `missing` is non-empty or a rubric dimension is below threshold."""
        t = time.perf_counter()
        return _env("record_completeness_critic", services.record_completeness_critic(
            project_id, verdict, run_id, operation_id), t)

    # ----- ESV §D: memory depth + the eval (quality) harness -----
    @mcp.tool()
    def cohort_memory_depth(persona_ids: list[str] | None = None) -> dict[str, Any]:
        """How deep is the cohort's simulated memory (avg facts+events/persona)? A thin cohort should be
        deepened (simulate-cohort) before a run so councils are grounded in rich lived experience."""
        t = time.perf_counter()
        return _env("cohort_memory_depth", services.cohort_memory_depth(persona_ids), t)

    @mcp.tool()
    def score_run(project_id: str) -> dict[str, Any]:
        """Persist a RunScore (critic rubric scores + finish + novelty + groundedness + memory depth) so
        output quality is tracked over time — a regression signal for the methodology itself."""
        t = time.perf_counter()
        return _env("score_run", services.score_run(project_id), t)

    # ----- F5 evidence integration (provenance) — relocated here (M3) -----
    @mcp.tool()
    def brief_evidence_check(persona_id: str) -> dict[str, Any]:
        """GATHER profile claims + attached evidence to validate synthesis against reality."""
        t = time.perf_counter()
        return _env("brief_evidence_check", services.brief_evidence_check(persona_id), t)

    @mcp.tool()
    def record_evidence_check(persona_id: str, result: dict[str, Any]) -> dict[str, Any]:
        """Persist provenance verdict: confirmed/contradicted/unsupported; flags contradictions."""
        t = time.perf_counter()
        return _env("record_evidence_check", services.record_evidence_check(persona_id, result), t)
