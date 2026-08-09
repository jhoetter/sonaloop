from __future__ import annotations

import time
from typing import Any, TypedDict

from .. import services
from ._env import _env


class ManifestScreenObservation(TypedDict):
    step_index: int
    visible_observation: str


def register_plan(mcp):
    # ============ Research-plan engine (plan-driven analyze/act/verify; spec/research-plan-engine.md) ===
    # The orchestrator's source of truth. A methodology seeds a plan; freeform starts from one frame.
    # brief_next + record_judgment (above) DISPATCH to the plan when a project has one.
    @mcp.tool()
    def start_project(title: str, goal: str, methodology: str | None = None,
                      persona_ids: list[str] | None = None, description: str = "",
                      icon: str | dict[str, Any] | None = None,
                      operation_id: str | None = None) -> dict[str, Any]:
        """THE ENTRY POINT. Create a project + seed its research plan (methodology -> analyze/act/verify
        scaffolding; none -> one dischargeable root frame task); the goal is the How-Might-We.
        `methodology` accepts either a stable key or its display name (for example `reaction_test`
        or `Reaction Test`) and is validated BEFORE anything is created. ALWAYS send one stable,
        opaque, non-sensitive caller-generated `operation_id` for the user's create intent and
        reuse it on transport retries;
        the same operation returns the same project instead of making duplicates.
        MANDATORY NEXT: start_run(project_id), then loop run_step(run_id) until kind=='done' — councils,
        syntheses and hypotheses MUST be produced THROUGH that loop (run_step dispatches each step), NOT
        by calling record_* directly: only inside the loop do the plan gates and assess_project stay
        honest (a project recorded past the loop reads as 0 evidence / 'stalled' and won't close). Read
        the `sonaloop://guide/research` resource for the full canonical path. (Personas should exist
        first — see list_personas; a thin cohort pulls from the 300+-persona catalog via
        catalog_search/catalog_recommend → catalog_pull.)"""
        t = time.perf_counter()
        return _env("start_project", services.start_project(title, goal, methodology, persona_ids,
                                                            description, icon=icon,
                                                            operation_id=operation_id), t)

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
                     hypotheses: list[str] | None = None, memory_refs: list[str] | None = None,
                     dispatch_token: str | None = None) -> dict[str, Any]:
        """Discharge an ANALYZE frame task: author research questions + hypotheses grounded in cited
        persona memory (>=1 question + >=1 memory_ref). For a governed run, pass the exact
        `dispatch_token` returned by run_step; the write is then linked and checkpointed atomically."""
        t = time.perf_counter()
        return _env("record_frame", services.record_frame(
            project_id, task_id, questions, hypotheses, memory_refs,
            dispatch_token=dispatch_token), t)

    @mcp.tool()
    def link_evidence(project_id: str, task_id: str, kind: str, evidence_id: str,
                      dispatch_token: str | None = None) -> dict[str, Any]:
        """Attach an evidence ref (kind=council|synthesis|artifact|session, id) to a task (usually the
        act task whose run-council/scaffold/session just produced it). Governed runs must pass their
        dispatch token; token-aware record_* tools normally do this automatically."""
        t = time.perf_counter()
        return _env("link_evidence", services.link_evidence(
            project_id, task_id, {"kind": kind, "id": evidence_id},
            dispatch_token=dispatch_token), t)

    @mcp.tool()
    def complete_task(project_id: str, task_id: str,
                      dispatch_token: str | None = None) -> dict[str, Any]:
        """Mark a ready task done. Verify tasks are gate-checked (breadth + gate judgment + artifacts/
        sessions) and rejected until satisfied. Governed runs must pass the issued dispatch token;
        token-aware output recorders normally complete and checkpoint automatically."""
        t = time.perf_counter()
        return _env("complete_task", services.complete_task(
            project_id, task_id, dispatch_token=dispatch_token), t)

    @mcp.tool()
    def brief_product_understanding(project_id: str) -> dict[str, Any]:
        """Gather the evidence-bound PRODUCT UNDERSTANDING preflight contract for a Reaction Test.
        Inspect and attach the actual app/screens first; do not fill unknowns with plausible guesses."""
        t = time.perf_counter()
        return _env("brief_product_understanding",
                    services.brief_product_understanding(project_id), t)

    @mcp.tool()
    def record_product_understanding(project_id: str, target: dict[str, Any],
                                     revision: str,
                                     routes: list[dict[str, Any]] | None = None,
                                     flows: list[dict[str, Any]] | None = None,
                                     states: list[dict[str, Any]] | None = None,
                                     capabilities: list[dict[str, Any]] | None = None,
                                     evidence_refs: list[dict[str, Any]] | None = None,
                                     stimulus_manifest: dict[str, Any] | None = None,
                                     coverage_checklist: list[dict[str, Any]] | None = None,
                                     observed_at: str | None = None,
                                     key: str | None = None,
                                     dispatch_token: str | None = None) -> dict[str, Any]:
        """Persist one immutable Product Understanding version. Every capability must declare one
        posture: observed_present|observed_absent|inferred|unknown. Observed/inferred claims cite
        project evidence; observed_absent additionally records a verification attempt. A remote
        screenshot flow must freeze stimulus_manifest {id, version, target_revision,
        manifest_digest} plus one inspected coverage_checklist entry per exact asset version. During a
        governed run pass run_step's dispatch_token: persistence, plan linking and checkpointing are
        replay-safe and automatic. A later version appends lineage; it never rewrites history."""
        t = time.perf_counter()
        return _env("record_product_understanding", services.record_product_understanding(
            project_id, target=target, revision=revision, routes=routes, flows=flows,
            states=states, capabilities=capabilities, evidence_refs=evidence_refs,
            stimulus_manifest=stimulus_manifest, coverage_checklist=coverage_checklist,
            observed_at=observed_at, key=key, dispatch_token=dispatch_token), t)

    @mcp.tool()
    def record_manifest_product_understanding(
            project_id: str, manifest_id: str,
            observations: list[ManifestScreenObservation],
            unknown_capabilities: list[str] | None = None,
            target_name: str = "", target_url: str = "",
            observed_at: str | None = None, key: str | None = None,
            dispatch_token: str | None = None) -> dict[str, Any]:
        """Weak-host-safe Reaction Test Product Understanding. First execute every serialized
        inspect_reaction_test_screen action returned by the same run. Then pass one flat observation
        {step_index, visible_observation} per manifest step plus honest unknown_capabilities. The server owns and
        freezes target revision, digest, evidence refs, state inventory and coverage; target_url is
        identity metadata only and is NEVER fetched or accepted as evidence. Reuse the same
        dispatch_token on retry; a successful call auto-links/checkpoints the Product Understanding
        dispatch. Missing exact served-to-host receipts fail before mutation. Strong hosts may still
        use record_product_understanding for richer postures."""
        t = time.perf_counter()
        return _env(
            "record_manifest_product_understanding",
            services.record_manifest_product_understanding(
                project_id, manifest_id, observations, unknown_capabilities,
                target_name, target_url, observed_at, key, dispatch_token,
            ),
            t,
        )

    @mcp.tool()
    def get_product_understanding(project_id: str,
                                  version_id: str | None = None) -> dict[str, Any]:
        """Read the current Product Understanding artifact, its immutable version history and
        capability posture counts. Pass version_id to inspect an older version."""
        t = time.perf_counter()
        return _env("get_product_understanding",
                    services.get_product_understanding(project_id, version_id), t)

    @mcp.tool()
    def brief_cohort_preflight(project_id: str,
                               hypotheses: list[str] | None = None) -> dict[str, Any]:
        """Gather the versioned server-owned cohort gate: per-persona memory/event/evidence depth,
        source/age provenance, deterministic hypothesis/profile lexical overlap, optional semantic
        feature input digests, and the required skeptical/indifferent/non-target declaration grounded
        by an exact quote from cited independent pre-project persona context."""
        t = time.perf_counter()
        return _env("brief_cohort_preflight",
                    services.brief_cohort_preflight(project_id, hypotheses), t)

    @mcp.tool()
    def select_reaction_test_cohort(
            project_id: str, persona_ids: list[str], selection_rationale: str,
            operation_id: str = "", dispatch_token: str | None = None) -> dict[str, Any]:
        """Repair an empty Reaction Test cohort with at least two EXISTING persona IDs. Use
        list_personas or catalog_search/catalog_recommend -> catalog_pull first. This is a supporting,
        retry-safe write on the current frame dispatch: it does NOT pass Cohort Integrity, complete or
        checkpoint the frame, create a new job, or create personas. Reuse operation_id and the exact
        arguments on retry; then continue the same run/frame dispatch."""
        t = time.perf_counter()
        return _env(
            "select_reaction_test_cohort",
            services.select_reaction_test_cohort(
                project_id, persona_ids, selection_rationale,
                operation_id, dispatch_token,
            ),
            t,
        )

    @mcp.tool()
    def record_cohort_preflight(project_id: str,
                                hypotheses: list[str] | None = None,
                                representation: list[dict[str, Any]] | None = None,
                                semantic_feature: dict[str, Any] | None = None,
                                override_rationale: str = "",
                                persona_ids: list[str] | None = None,
                                selection_rationale: str = "",
                                evaluated_at: str | None = None,
                                key: str | None = None,
                                dispatch_token: str | None = None) -> dict[str, Any]:
        """Persist an immutable cohort-integrity result. Status is exactly pass|needs_deepening|
        needs_reselection|overridden. Failed gates inject required plan work and block downstream
        reaction evidence; reselect/deepen, then call again on the next dispatch. A countervoice
        without a matching quote/ref from independent persona context fails closed. Changing the cohort requires a
        selection rationale. Override requires an explicit rationale and survives into report
        limitations. The optional semantic feature uses one provider-neutral schema/threshold."""
        t = time.perf_counter()
        return _env("record_cohort_preflight", services.record_cohort_preflight(
            project_id, hypotheses=hypotheses, representation=representation,
            semantic_feature=semantic_feature, override_rationale=override_rationale,
            persona_ids=persona_ids, selection_rationale=selection_rationale,
            evaluated_at=evaluated_at, key=key, dispatch_token=dispatch_token), t)

    @mcp.tool()
    def get_cohort_preflight(project_id: str,
                             version_id: str | None = None) -> dict[str, Any]:
        """Read the current or historical cohort gate, its thresholds/features, remediation lineage
        and any persisted report limitation caused by an explicit override."""
        t = time.perf_counter()
        return _env("get_cohort_preflight",
                    services.get_cohort_preflight(project_id, version_id), t)

    @mcp.tool()
    def project_health(project_id: str) -> dict[str, Any]:
        """Read the canonical Job health projection: running/stalled/engine-finished/unverified,
        the first unmet invariant, Product Understanding coverage, evidence posture/source counts,
        the last successful operation, one safe next action, and a redacted support trace reference.
        External-host-only prompts/reasoning/retries are explicitly marked unobservable, never guessed."""
        t = time.perf_counter()
        return _env("project_health", services.project_health(project_id), t)

    @mcp.tool()
    def resume_project_run(project_id: str, run_id: str,
                           operation_id: str = "") -> dict[str, Any]:
        """Resume exactly the named ACTIVE run. This never creates a project/run, reopens a terminal
        run, or marks anything finished. It verifies project/run/operation scope and returns the
        existing journal's safe `run_step(run_id)` continuation; retries are idempotent."""
        t = time.perf_counter()
        return _env("resume_project_run", services.resume_project_run(
            project_id, run_id, operation_id), t)

    @mcp.tool()
    def supersede_project(project_id: str, supersedes_project_id: str,
                          operation_id: str, reason: str) -> dict[str, Any]:
        """Explicitly declare that project_id supersedes another project in this workspace.
        Preserves every artifact, records old→new lineage, and marks only the predecessor obsolete.
        It never guesses from similar titles and never deletes evidence; reuse operation_id on retry."""
        t = time.perf_counter()
        return _env("supersede_project", services.supersede_project(
            project_id, supersedes_project_id, operation_id, reason), t)

    @mcp.tool()
    def archive_project(project_id: str, operation_id: str, reason: str) -> dict[str, Any]:
        """Explicitly archive one project without deleting evidence. Active runs fail closed; recover
        or stop them first. Reuse the same operation_id on transport retries."""
        t = time.perf_counter()
        return _env("archive_project", services.archive_project(
            project_id, operation_id, reason), t)

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
    def start_run(project_id: str, budget: int | None = None, run_id: str | None = None,
                  operation_id: str | None = None) -> dict[str, Any]:
        """Create (or resume) the run object — the SINGLE entry to the governed loop. Returns the run +
        its journal. For initial creation pass a stable operation_id and reuse it on transport retries;
        pass an existing run_id only to resume (a project flagged 'stalled' wants a resume, not a fresh
        run). A project cannot acquire a second active run: ACTIVE_RUN_EXISTS names the exact existing
        run_id; resume that id and never create a replacement. MANDATORY LOOP: repeatedly call
        run_step(run_id), execute each returned dispatch with
        its exact `dispatch_token`; token-aware recorders link and checkpoint automatically — until
        run_step returns kind=='done'. Do NOT record
        evidence outside this loop; gates passed != finished — only kind=='done' closes the project."""
        t = time.perf_counter()
        return _env("start_run", services.start_run(
            project_id, budget, run_id, operation_id=operation_id), t)

    @mcp.tool()
    def run_journal(run_id: str) -> dict[str, Any]:
        """The run's journal (steps + critic rounds + cursor + status) — the source of truth for resume."""
        t = time.perf_counter()
        return _env("run_journal", services.run_journal(run_id), t)

    @mcp.tool()
    def checkpoint_step(run_id: str, step: dict[str, Any]) -> dict[str, Any]:
        """Checkpoint a completed step (task_id, bucket, key, evidence ids, 1-line summary).
        Governed projects require the dispatch_token issued by run_step. Normally this is automatic
        when the output is persisted through a token-aware recorder; call manually only for a
        primitive that explicitly reports it is linked but not checkpointed.
        `key` must be the deterministic key returned by run_step; retrying an identical payload
        returns its original receipt, while different content under that key fails closed."""
        t = time.perf_counter()
        return _env("checkpoint_step", services.checkpoint_step(run_id, step), t)

    @mcp.tool()
    def record_critic_round(run_id: str, critic_report_id: str, key: str) -> dict[str, Any]:
        """Bind one persisted completeness-critic report to its deterministic run dispatch.
        Retry the same report id + key safely; passed/missing is derived from the report so one
        logical critic cannot be counted as two dry rounds."""
        t = time.perf_counter()
        return _env("record_critic_round", services.record_critic_round(
            run_id, critic_report_id, key), t)

    @mcp.tool()
    def finish_run(run_id: str, status: str = "finished") -> dict[str, Any]:
        """Stop/cap a run, or validate an already complete run. `finished` fails closed while plan,
        finish work, or the two persisted completeness-critic passes are missing. Normally do not call
        this directly: loop run_step until it returns kind=='done'; only the engine owns completion."""
        t = time.perf_counter()
        return _env("finish_run", services.finish_run(run_id, status), t)

    @mcp.tool()
    def run_step(run_id: str) -> dict[str, Any]:
        """The ESV driver's brain (deterministic). Returns the next dispatch to execute:
        {kind: analyze|act|verify, step_id, key, dispatch_token, next_action, directive} → spawn ONE
        authoring subagent and pass the token into its recorder (auto-link + auto-checkpoint);
        {kind: critic, brief} → spawn an INDEPENDENT critic then
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
