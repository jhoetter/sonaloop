from __future__ import annotations

import time
from typing import Any

from .. import services
from ._env import _env


def register_plan(mcp):
    # ============ Research-plan engine (plan-driven analyze/act/verify; spec/research-plan-engine.md) ===
    # The orchestrator's source of truth. A methodology seeds a plan; freeform starts from one frame.
    # brief_next + record_judgment (above) DISPATCH to the plan when a project has one.
    @mcp.tool()
    def start_project(title: str, goal: str, methodology: str | None = None,
                      persona_ids: list[str] | None = None, description: str = "",
                      icon: str | dict[str, Any] | None = None) -> dict[str, Any]:
        """THE ENTRY POINT. Create a project + seed its research plan (methodology -> analyze/act/verify
        scaffolding; none -> one dischargeable root frame task); the goal is the How-Might-We.
        MANDATORY NEXT: start_run(project_id), then loop run_step(run_id) until kind=='done' — councils,
        syntheses and hypotheses MUST be produced THROUGH that loop (run_step dispatches each step), NOT
        by calling record_* directly: only inside the loop do the plan gates and assess_project stay
        honest (a project recorded past the loop reads as 0 evidence / 'stalled' and won't close). Read
        the `sonaloop://guide/research` resource for the full canonical path. (Personas should exist
        first — see list_personas; a thin cohort pulls from the 300+-persona catalog via
        catalog_search/catalog_recommend → catalog_pull.)"""
        t = time.perf_counter()
        return _env("start_project", services.start_project(title, goal, methodology, persona_ids,
                                                            description, icon=icon), t)

    @mcp.tool()
    def get_plan(project_id: str) -> dict[str, Any]:
        """The project's research plan (analyze/act/verify task DAG + evidence refs + judgments)."""
        t = time.perf_counter()
        return _env("get_plan", services.get_plan(project_id), t)

    @mcp.tool()
    def export_plan_md(project_id: str) -> dict[str, Any]:
        """Render the plan as a human-readable, bucketed plan.md (analyze/act/verify + status + gates)."""
        t = time.perf_counter()
        return _env("export_plan_md", {"markdown": services.export_plan_md(project_id)}, t)

    @mcp.tool()
    def add_task(project_id: str, bucket: str, capability: str, title: str, intent: str = "",
                 consumes: list[str] | None = None, requires: dict[str, Any] | None = None,
                 step: str = "", plan_note: str = "") -> dict[str, Any]:
        """Insert a task into the plan (shape the breadth): bucket analyze|act|verify, a capability
        tag, consumes (DAG edges), optional gates. Returns the created task."""
        t = time.perf_counter()
        return _env("add_task", services.add_task(project_id, bucket, capability, title, intent,
                                                  consumes, requires, step, plan_note), t)

    @mcp.tool()
    def record_frame(project_id: str, task_id: str, questions: list[str],
                     hypotheses: list[str] | None = None, memory_refs: list[str] | None = None) -> dict[str, Any]:
        """Discharge an ANALYZE frame task: author research questions + hypotheses grounded in cited
        persona memory (>=1 question + >=1 memory_ref). Understand before concluding."""
        t = time.perf_counter()
        return _env("record_frame", services.record_frame(project_id, task_id, questions, hypotheses, memory_refs), t)

    @mcp.tool()
    def link_evidence(project_id: str, task_id: str, kind: str, evidence_id: str) -> dict[str, Any]:
        """Attach an evidence ref (kind=council|synthesis|artifact|session, id) to a task (usually the
        act task whose run-council/scaffold/session just produced it)."""
        t = time.perf_counter()
        return _env("link_evidence", services.link_evidence(project_id, task_id, {"kind": kind, "id": evidence_id}), t)

    @mcp.tool()
    def complete_task(project_id: str, task_id: str) -> dict[str, Any]:
        """Mark a ready task done. Verify tasks are gate-checked (breadth + gate judgment + artifacts/
        sessions) and rejected until satisfied."""
        t = time.perf_counter()
        return _env("complete_task", services.complete_task(project_id, task_id), t)

    @mcp.tool()
    def iterate_task(project_id: str, task_id: str, note: str = "") -> dict[str, Any]:
        """Open the NEXT iteration round on a done-or-ready task with a `loop_back` target (HOST-judged
        — the engine never loops on its own): clones the loop-back subgraph as fresh `__r<n>` tasks
        (statuses todo, evidence/frames not carried over, gates preserved), with the new round's entry
        consuming the looping task so ordering holds. Returns the iteration record + cloned tasks."""
        t = time.perf_counter()
        return _env("iterate_task", services.iterate_task(project_id, task_id, note), t)

    @mcp.tool()
    def assess_progress(project_id: str, task_id: str, rationale: str, evidence_refs: list[str],
                        delta: str = "") -> dict[str, Any]:
        """Record an evidence-backed assessment of progress toward the HMW goal. `delta` is a free
        host judgment (never a number); a non-binding coverage snapshot is attached."""
        t = time.perf_counter()
        return _env("assess_progress", services.assess_progress(project_id, task_id, rationale, evidence_refs, delta), t)

    @mcp.tool()
    def next_action(project_id: str) -> dict[str, Any]:
        """The ready task FULLY loaded for a lean autonomous loop: analyze→grounding (prior
        syntheses + open questions); act→the consumed frame's framed questions + segment-diverse
        suggested participants; verify→the fan + gate. Carries the project recommendation. Use this
        as the single per-iteration call: next_action → author via a subagent → persist."""
        t = time.perf_counter()
        return _env("next_action", services.next_action(project_id), t)

    @mcp.tool()
    def assess_project(project_id: str) -> dict[str, Any]:
        """Project-level meta-assessment (read-only, computed — no LLM verdict): coverage, open
        evidence gates, open questions, a saturation hint, structural gaps, and a computed
        continue/converge/complete/blocked recommendation. Call this every iteration of a long run
        to stay purposeful and to decide when to stop."""
        t = time.perf_counter()
        return _env("assess_project", services.assess_project(project_id), t)

    # ----- ESV §A: the resumable run object (driver journal) -----
    @mcp.tool()
    def start_run(project_id: str, budget: int | None = None, run_id: str | None = None) -> dict[str, Any]:
        """Create (or resume) the run object — the SINGLE entry to the governed loop. Returns the run +
        its journal; pass an existing run_id to resume (idempotent — a project flagged 'stalled' wants
        a resume, not a fresh run). MANDATORY LOOP: repeatedly call run_step(run_id), execute each
        returned dispatch, then checkpoint_step — until run_step returns kind=='done'. Do NOT record
        evidence outside this loop; gates passed != finished — only kind=='done' closes the project."""
        t = time.perf_counter()
        return _env("start_run", services.start_run(project_id, budget, run_id), t)

    @mcp.tool()
    def run_journal(run_id: str) -> dict[str, Any]:
        """The run's journal (steps + critic rounds + cursor + status) — the source of truth for resume."""
        t = time.perf_counter()
        return _env("run_journal", services.run_journal(run_id), t)

    @mcp.tool()
    def checkpoint_step(run_id: str, step: dict[str, Any]) -> dict[str, Any]:
        """Append a completed step (task_id, bucket, key, evidence ids, 1-line summary) to the journal."""
        t = time.perf_counter()
        return _env("checkpoint_step", services.checkpoint_step(run_id, step), t)

    @mcp.tool()
    def record_critic_round(run_id: str, passed: bool, missing_count: int) -> dict[str, Any]:
        """Log one completeness-critic round on the run (loop-until-dry observability)."""
        t = time.perf_counter()
        return _env("record_critic_round", services.record_critic_round(run_id, passed, missing_count), t)

    @mcp.tool()
    def finish_run(run_id: str, status: str = "finished") -> dict[str, Any]:
        """Mark the run finished/stopped."""
        t = time.perf_counter()
        return _env("finish_run", services.finish_run(run_id, status), t)

    @mcp.tool()
    def run_step(run_id: str) -> dict[str, Any]:
        """The ESV driver's brain (deterministic). Returns the next dispatch to execute:
        {kind: analyze|act|verify, step_id, key, next_action, directive} → spawn ONE authoring subagent
        then checkpoint_step; {kind: critic, brief} → spawn an INDEPENDENT critic then
        record_completeness_critic + record_critic_round; {kind: done, status, summary} → stop.
        Loop run_step until kind=='done'. Resumable: it reads the live plan state."""
        t = time.perf_counter()
        return _env("run_step", services.run_step(run_id), t)

    @mcp.tool()
    def inject_work(project_id: str, missing: dict[str, Any]) -> dict[str, Any]:
        """Turn one critic `missing` item {kind, what, ...} into a real plan task/open-question (the
        driver does this automatically; exposed for manual gap-filling)."""
        t = time.perf_counter()
        return _env("inject_work", {"injected": services.inject_work(project_id, missing)}, t)
