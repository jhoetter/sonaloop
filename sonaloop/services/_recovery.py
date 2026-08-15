"""Canonical project health, safe run recovery, and project lineage.

The web inspector, MCP and CLI all consume this projector.  It deliberately
uses persisted run/plan/integrity records only: prose length, provider names,
and a host's generic error message are never promoted into research truth.
"""
from __future__ import annotations

import copy
from collections import Counter
import hashlib
from typing import Any

from ..config import utc_now_iso
from ..research_integrity import (
    artifact_posture_gaps,
    current_product_understanding,
    is_reaction_project,
    reaction_preflight_action,
    resolve_project_ref,
)
from ..cohort_integrity import current_cohort_preflight, preflight_satisfies_project
from ..run_activity import activity_deadline, is_inactive_for
from ..storage import Store
from .._project_locks import project_lifecycle_locks
from ..report_handoff import (
    report_handoff_state,
    report_provenance_state,
    terminal_synthesis_source_ids,
)


PROJECT_HEALTH_SCHEMA = "sonaloop.project_health.v2"
PROJECT_LINEAGE_SCHEMA = "sonaloop.project_lineage.v1"


def _opaque_operation_id(value: str, *, field: str = "operation_id") -> str:
    token = str(value or "").strip()
    if not 1 <= len(token) <= 200 or not token.isprintable():
        raise ValueError(f"{field} must be 1-200 printable characters")
    return token


def _latest(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    return max(rows, key=lambda row: (str(row.get("updated_at") or ""),
                                      str(row.get("created_at") or ""),
                                      int(row.get("idx") or 0)), default=None)


def _ref_exists(project_id: str, ref: dict[str, Any], store: Store) -> bool:
    try:
        resolve_project_ref(project_id, ref, store)
        return True
    except Exception:
        return False


def _ref_identity(ref: Any) -> tuple[str, str, str]:
    """The existence identity of a claim reference.

    Claim posture often repeats the same evidence reference across many derived
    statements.  Existence is a property of the referenced record, not of the
    surrounding quote/role prose. Anchors are part of the resolvable address,
    however, so one health projection resolves each ``(kind, id, anchor)`` once.
    """
    if isinstance(ref, str):
        token = ref.strip()
        kind, rid = token.split(":", 1) if ":" in token else ("", token)
        return kind, rid, ""
    if not isinstance(ref, dict):
        # Legacy/corrupt JSON must remain a fail-closed issue, not take down the
        # entire health projection before `_ref_exists` can reject it.
        return "__invalid__", type(ref).__name__, repr(ref)
    row = ref
    return (str(row.get("kind") or "").strip(), str(row.get("id") or "").strip(),
            str(row.get("anchor") or "").strip())


def _artifact_rows(project_id: str, store: Store) -> list[tuple[str, dict[str, Any]]]:
    project = store.get_research_project(project_id) or {}
    rows: list[tuple[str, dict[str, Any]]] = []
    rows.extend((f"council:{row['id']}", row) for row in store.list_council_sessions()
                if str(row.get("project_id") or "") == project_id)
    rows.extend((f"synthesis:{row['id']}", row) for row in store.list_syntheses()
                if str(row.get("project_id") or "") == project_id)
    # Old project reports can predate project_id on synthesis records.  The
    # project's explicit study ids are authoritative membership, never title matching.
    known = {label for label, _ in rows}
    for raw in project.get("study_ids") or []:
        label = str(raw)
        if label in known or ":" not in label:
            continue
        kind, rid = label.split(":", 1)
        record = (store.get_council_session(rid) if kind == "council"
                  else store.get_synthesis(rid) if kind == "synthesis" else None)
        if record:
            rows.append((label, record))
    return rows


def _product_understanding_health(project: dict[str, Any]) -> dict[str, Any]:
    versions = list(project.get("product_understanding_versions") or [])
    current = current_product_understanding(project)
    counts = Counter(str(row.get("status") or "unknown")
                     for row in (current or {}).get("capabilities") or [])
    # A later observation legitimately supersedes an earlier one.  We expose
    # opposite observed postures as revision conflicts for inspection; we do
    # not decide which historical observation is "right".
    by_key: dict[str, set[str]] = {}
    for version in versions:
        for capability in version.get("capabilities") or []:
            key = str(capability.get("key") or capability.get("claim") or "")
            by_key.setdefault(key, set()).add(str(capability.get("status") or "unknown"))
    contradictory = sorted(key for key, values in by_key.items()
                           if {"observed_present", "observed_absent"} <= values)
    return {
        "required": bool((project.get("integrity") or {}).get("product_understanding_required")),
        "present": bool(current),
        "current_id": str((current or {}).get("id") or ""),
        "target": dict((current or {}).get("target") or {}),
        "revision": str((current or {}).get("revision") or ""),
        "observed_at": str((current or {}).get("observed_at") or ""),
        "version": int((current or {}).get("version") or 0),
        "capability_counts": {
            "observed_present": counts["observed_present"],
            "observed_absent": counts["observed_absent"],
            "inferred": counts["inferred"],
            "unknown": counts["unknown"],
        },
        "contradictory_capability_keys": contradictory,
    }


def _preflight_health(project: dict[str, Any], plan: dict[str, Any] | None,
                      store: Store) -> dict[str, Any]:
    """Project the one integrity preflight that currently blocks useful progress.

    Product Understanding precedes the research frame, and the Cohort Integrity
    gate consumes that frame.  Treating both missing future records as concurrent
    failures made a newly started Reaction Test look broken and, worse, left its
    active journal green.  This projection follows the persisted task DAG: a
    downstream missing cohort record is a blocker only once all of its inputs are
    done.  A previously recorded failing/stale cohort gate remains a blocker until
    it is repaired.
    """
    policy = project.get("integrity") or {}
    tasks = list((plan or {}).get("tasks") or [])
    by_id = {str(row.get("id") or ""): row for row in tasks}
    done = {str(row.get("id") or "") for row in tasks if row.get("status") == "done"}

    front_action = reaction_preflight_action(str(project.get("id") or ""), store)
    if front_action:
        kind = str(front_action.get("kind") or "preflight_required")
        product_kinds = {
            "stimulus_required", "capture_review_required", "flow_manifest_required",
            "product_understanding_required",
        }
        gate = "product_understanding" if kind in product_kinds else "cohort_selection"
        return {
            "state": "waiting", "gate": gate, "kind": kind,
            "task_id": ("preflight__product_understanding"
                        if gate == "product_understanding" else "frame__react"),
            "code": str(front_action.get("code") or "REACTION_PREFLIGHT_REQUIRED"),
            "message": str(front_action.get("message") or "A Reaction Test prerequisite is waiting."),
            "allowed_tools": list(front_action.get("allowed_tools") or []),
            "next_call": dict(front_action.get("next_call") or {}),
            "action": copy.deepcopy(front_action),
        }

    if not policy.get("cohort_preflight_required"):
        return {"state": "ready"}

    current = current_cohort_preflight(project)
    cohort_task = by_id.get("preflight__cohort_integrity")
    # A missing downstream record is not an error while its frame inputs are
    # still being authored.  Old/custom projects without the canonical task keep
    # the conservative visible gate instead of silently hiding it forever.
    actionable = (
        cohort_task is None
        or all(str(dep) in done for dep in (cohort_task.get("consumes") or []))
    )
    if current is None:
        if not actionable:
            return {"state": "pending", "gate": "cohort_integrity",
                    "task_id": "preflight__cohort_integrity"}
        return {
            "state": "waiting", "gate": "cohort_integrity",
            "task_id": "preflight__cohort_integrity",
            "code": "cohort_preflight_missing",
            "message": "The Reaction Test is waiting for its Cohort Integrity check.",
        }

    try:
        satisfied = preflight_satisfies_project(project, store)
    except Exception:  # an unreadable boundary is never promoted to a pass
        satisfied = False
    if satisfied:
        return {"state": "ready", "gate": "cohort_integrity",
                "task_id": "preflight__cohort_integrity",
                "status": str(current.get("status") or "")}

    status = str(current.get("status") or "needs_reselection")
    code = (
        "cohort_preflight_stale"
        if status in {"pass", "overridden"}
        else f"cohort_preflight_{status}"
    )
    messages = {
        "needs_deepening": "The cohort needs deeper independent context before the Reaction Test can continue.",
        "needs_reselection": "The cohort must be reselected before the Reaction Test can continue.",
    }
    return {
        "state": "waiting", "gate": "cohort_integrity",
        "task_id": "preflight__cohort_integrity", "status": status,
        "code": code,
        "message": messages.get(status, "The Cohort Integrity check is stale and must be rerun."),
    }


def _trace_ref(project: dict[str, Any], run: dict[str, Any] | None) -> dict[str, Any]:
    from ..correlation import workflow_trace_id
    ingress = dict(project.get("research_job_ingress") or {})
    operation_id = str(ingress.get("operation_id") or project.get("operation_id") or "")
    support_ref = workflow_trace_id(project)
    query = {"project_id": project.get("id")}
    if run:
        query["run_id"] = run.get("run_id")
    if operation_id:
        query["operation_id"] = operation_id
    return {
        "support_ref": support_ref,
        "workflow_trace_id": support_ref,
        "local_journal": "available" if run else "not_started",
        "cloud_trace_query": query,
        "external_host_visibility": "not_observable",
        "limitation": (
            "Sonaloop records its MCP boundary and local run journal. It cannot observe hidden "
            "provider prompts, reasoning, permission dialogs, internal retries, or host-only errors."
        ),
    }


def _required_placeholder_paths(value: Any, prefix: str = "arguments") -> list[str]:
    paths: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            paths.extend(_required_placeholder_paths(child, f"{prefix}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            paths.extend(_required_placeholder_paths(child, f"{prefix}[{index}]"))
    elif isinstance(value, str) and value.startswith("<") and value.endswith(">"):
        paths.append(prefix)
    return paths


def _hydrate_preflight_call(call: dict[str, Any], run: dict[str, Any],
                            dispatch: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(call)
    args = out.setdefault("arguments", {})
    if "run_id" in args:
        args["run_id"] = str(run.get("run_id") or "")
    if "dispatch_token" in args:
        args["dispatch_token"] = str(dispatch.get("dispatch_token") or "")
    if ("operation_id" in args and isinstance(args.get("operation_id"), str)
            and str(args["operation_id"]).startswith("<")):
        suffix = str(out.get("tool") or "preflight").replace("_", "-")
        args["operation_id"] = f"{dispatch.get('operation_id')}:{suffix}"
    return out


def project_health(project_id: str, store: Store | None = None,
                   stale_hours: int = 6, expire_hours: int = 24) -> dict[str, Any]:
    """Project one truthful, repair-oriented state from canonical persisted records."""
    from .. import plan as plan_mod
    from ..plan_assess import assess_project

    store = store or Store()
    project = store.get_research_project(project_id)
    if not project:
        raise KeyError(f"Unknown research project: {project_id}")
    plan = plan_mod.get_plan(project_id, store=store)
    runs = store.list_runs(project_id)
    active_runs = [row for row in runs if row.get("status") == "active"]
    finished_runs = [row for row in runs if row.get("status") == "finished"]
    run = _latest(active_runs) or _latest(runs)
    if expire_hours < stale_hours:
        raise ValueError("expire_hours must be greater than or equal to stale_hours")
    run_activity = str((run or {}).get("updated_at") or "")
    run_expired = bool(active_runs and is_inactive_for(run_activity, expire_hours))
    # The currently actionable run is authoritative.  A historical finished
    # journal must never upgrade a newer active attempt to "finished" while
    # the recovery action correctly says to resume that active attempt.
    authoritative_finished = bool(run and run.get("status") == "finished")
    tasks = list((plan or {}).get("tasks") or [])
    ready = [row["id"] for row in plan_mod.ready_tasks(plan)] if plan else []
    tasks_done = sum(1 for row in tasks if row.get("status") == "done")
    plan_complete = bool(plan and plan_mod.is_complete(plan))

    issues: list[dict[str, Any]] = []
    # A rich synthesis can carry hundreds of claim-level citations while only
    # referring to a small evidence set.  Resolving every duplicate separately
    # turns the read-only status chip into an N+1 query storm (and the global
    # run widget repeats that per project).  Keep this cache deliberately local
    # to one projection so writes in later calls can never be masked.
    ref_exists_cache: dict[tuple[str, str, str], bool] = {}

    def issue(code: str, message: str, *, target: str = "", severity: str = "blocking") -> None:
        row = {"code": code, "message": message, "severity": severity}
        if target:
            row["target"] = target
        if not any(x.get("code") == code and x.get("target") == target for x in issues):
            issues.append(row)

    if len(active_runs) > 1:
        issue("multiple_active_runs", "Multiple active runs exist; select an explicit run id before recovery.")

    pu = _product_understanding_health(project)
    preflight = _preflight_health(project, plan, store)
    if preflight.get("state") == "waiting":
        gate = str(preflight.get("gate") or "")
        target = (f"/jobs/{project_id}#product-understanding"
                  if gate == "product_understanding"
                  else f"/jobs/{project_id}#cohort-integrity"
                  if gate == "cohort_integrity"
                  else f"/jobs/{project_id}#cohort-selection")
        issue(str(preflight.get("code") or "preflight_waiting"),
              str(preflight.get("message") or "A required preflight is waiting."),
              target=target)

    linked = {(str(ref.get("kind") or ""), str(ref.get("id") or ""))
              for task in tasks for ref in (task.get("produces") or [])
              if ref.get("kind") and ref.get("id")}
    parked = {str(ref) for row in (plan or {}).get("parked_refs") or []
              for ref in (row.get("refs") or []) if str(ref)}
    artifact_rows = _artifact_rows(project_id, store)
    claim_contract_required = is_reaction_project(project, plan)
    for label, record in artifact_rows:
        kind, rid = label.split(":", 1)
        is_project_report = (str(record.get("scope") or "") == "project"
                             and str(record.get("project_id") or "") == project_id)
        aliases = {label, rid, f"{kind}:{rid}"}
        if is_project_report:
            aliases.add(f"report:{rid}")
        linked_alias = ((kind, rid) in linked
                        or (is_project_report and ("report", rid) in linked))
        # A project report is the terminal hand-off, not an intermediate plan
        # artifact that needs a downstream consumer. Explicitly parked evidence
        # is likewise intentional, not orphaned.
        if not is_project_report and not linked_alias and not (aliases & parked):
            issue("orphaned_evidence", f"{label} is not linked to a plan task.",
                  target=f"/{'councils' if kind == 'council' else 'syntheses'}/{rid}")
        if is_project_report:
            report_provenance = report_provenance_state(record)
            for gap in report_provenance["gaps"]:
                if gap["reason"] == "invalid_source_citations":
                    message = f"{label} contains citations outside its frozen report graph"
                else:
                    message = (f"{label} section {gap['heading']!r} contains authored prose "
                               "without a valid citation to one of its declared source studies")
                issue("claim_provenance_incomplete", message,
                      target=f"/syntheses/{rid}")
            for citation in report_provenance["invalid_citations"]:
                issue(
                    "invalid_evidence_ref",
                    f"{label} section {citation['heading']!r} cites a source study "
                    f"{citation['study_id']!r} missing from its frozen report graph.",
                    target=f"/syntheses/{rid}",
                )
        elif claim_contract_required or record.get("claim_posture"):
            for gap in artifact_posture_gaps(record, label):
                issue("claim_provenance_incomplete", gap,
                      target=f"/{'councils' if kind == 'council' else 'syntheses'}/{rid}#claim-health")
        envelope = record.get("claim_posture") or {}
        for claim in ([] if is_project_report else envelope.get("claims") or []):
            for ref in claim.get("refs") or []:
                ref_key = _ref_identity(ref)
                if ref_key not in ref_exists_cache:
                    ref_exists_cache[ref_key] = _ref_exists(project_id, ref, store)
                if not ref_exists_cache[ref_key]:
                    cid = str(claim.get("id") or "")
                    issue("invalid_evidence_ref", f"{label} claim {cid or 'unknown'} has an invalid reference.",
                          target=(f"/{'councils' if kind == 'council' else 'syntheses'}/{rid}"
                                  + (f"#{cid}" if cid else "#claim-health")))

    report_handoff = report_handoff_state(
        store.list_reports(project_id),
        required_source_ids=terminal_synthesis_source_ids(plan),
    )
    if report_handoff["exists"] and not report_handoff["complete"]:
        latest_report_id = str(report_handoff.get("latest_report_id") or "")
        stale = bool(report_handoff.get("latest_stale"))
        issue(
            "report_stale" if stale else "report_incomplete",
            ("The project report predates the current terminal synthesis; scaffold the current "
             "immutable hand-off before completion."
             if stale else
             "The project report is still a draft; every section needs an authored body before hand-off."),
            target=(f"/syntheses/{latest_report_id}" if latest_report_id else f"/jobs/{project_id}"),
        )

    latest_step = _latest(list((run or {}).get("steps") or []))
    incomplete_dispatches = [row for row in (run or {}).get("dispatches") or []
                             if row.get("status") == "issued"]
    incomplete_dispatch = _latest(incomplete_dispatches)
    if incomplete_dispatch:
        issue("dispatch_incomplete",
              f"Dispatch {incomplete_dispatch.get('step_id') or incomplete_dispatch.get('task_id')} "
              "was issued but has no checkpoint.")

    assessment: dict[str, Any] = {}
    if plan:
        try:
            assessment = assess_project(project_id, store=store)
        except Exception as exc:  # unknown integrity is never upgraded to verified
            issue("assessment_unavailable", f"Project assessment is unavailable: {type(exc).__name__}.")
    if plan_complete and assessment:
        finish = assessment.get("finish") or {}
        result_contract = assessment.get("result_contract") or {}
        if not result_contract.get("satisfied", True):
            missing = ", ".join(str(row.get("id") or "unknown")
                                for row in result_contract.get("missing") or [])
            issue("result_contract_missing",
                  "The completed plan is missing required structured job outcomes"
                  + (f": {missing}." if missing else "."),
                  target=f"/jobs/{project_id}#job-outcomes")
        if not finish.get("organized"):
            issue("expected_sections_missing",
                  "The completed plan has no required phase/theme organization yet.",
                  target=f"/jobs/{project_id}")
        if not finish.get("concluded"):
            issue("conclusion_missing", "The completed plan has no substantial terminal conclusion.",
                  target=f"/jobs/{project_id}")
        if not finish.get("handed_off"):
            if report_handoff["exists"]:
                stale = bool(report_handoff.get("latest_stale"))
                issue("report_stale" if stale else "report_incomplete",
                      ("The completed plan's report does not consume its current terminal synthesis."
                       if stale else
                       "The completed plan has a report draft, but its sections are not all authored."),
                      target=(f"/syntheses/{report_handoff['latest_report_id']}"
                              if report_handoff.get("latest_report_id") else f"/jobs/{project_id}"))
            else:
                issue("report_missing", "The completed plan has no project report hand-off.",
                      target=f"/jobs/{project_id}")

    dry_rounds = 0
    for row in reversed(list((run or {}).get("critic_rounds") or [])):
        if row.get("passed") and not row.get("missing"):
            dry_rounds += 1
        else:
            break
    if plan_complete and not authoritative_finished:
        if (assessment.get("finish") or {}).get("finished") and dry_rounds < 2:
            issue("critic_pending", f"Completeness critic needs 2 trailing passes; {dry_rounds} recorded.")
        else:
            issue("engine_completion_missing",
                  "The plan may be complete, but no run has reached engine-verified finished state.")

    integrity_unverified = preflight.get("state") == "waiting" or any(row["code"] in {
        "product_understanding_missing", "orphaned_evidence", "claim_provenance_incomplete",
        "invalid_evidence_ref", "assessment_unavailable", "engine_completion_missing",
        "expected_sections_missing", "conclusion_missing", "report_missing",
        "report_incomplete", "report_stale",
        "result_contract_missing", "cohort_preflight_missing", "cohort_preflight_stale",
        "cohort_preflight_needs_deepening", "cohort_preflight_needs_reselection",
    } for row in issues)
    lifecycle = str(project.get("status") or "active")
    if lifecycle in {"archived", "superseded"}:
        driver_state = lifecycle
        state = lifecycle
    elif active_runs:
        if run_expired:
            driver_state = ("expired_waiting_on_preflight"
                            if preflight.get("state") == "waiting" else "expired")
            state = "expired"
        elif preflight.get("state") == "waiting":
            # The journal is resumable but no useful research can proceed until
            # the current evidence/cohort gate is discharged.  "running" would
            # falsely imply autonomous background work.
            driver_state = "waiting_on_preflight"
            state = "waiting"
        else:
            quiet = is_inactive_for(str((run or {}).get("updated_at") or ""), stale_hours)
            driver_state = "stalled" if quiet else "running"
            state = driver_state
    elif authoritative_finished:
        driver_state = "engine_finished"
        state = "unverified" if integrity_unverified else "finished"
    elif plan_complete:
        driver_state = "not_engine_finished"
        state = "unverified"
    else:
        # A plan that has never acquired a run is actionable, but it is not an
        # interrupted run. A stopped/capped historical run is not resumable either.
        # Keep both in the attention lane while exposing the truthful lifecycle
        # distinction to UI and automation callers.
        driver_state = "not_started" if not runs else "stopped"
        state = "stalled"

    if state == "expired":
        issue(
            "run_expired",
            f"This unfinished run has had no recorded activity for more than {expire_hours} hours. "
            "Its journal is preserved and can be resumed safely.",
            severity="attention",
        )
    if state == "stalled" and not issues:
        if not runs:
            issue("run_not_started", "Open plan work has not started a governed run yet.")
        elif not active_runs:
            issue("run_inactive", "Open plan work has no active governed run.")
        else:
            issue("driver_missing", "Open plan work has no recently active governed driver.")

    last_success = ({"kind": "checkpoint", "key": latest_step.get("key", ""),
                     "task_id": latest_step.get("task_id", ""),
                     "summary": latest_step.get("summary", ""),
                     "at": str((run or {}).get("updated_at") or "")}
                    if latest_step else
                    {"kind": "run_created" if run else "project_created",
                     "key": str((run or {}).get("operation_id") or project.get("operation_id") or ""),
                     "at": str((run or project).get("created_at") or "")})

    safe_action: dict[str, Any]
    if lifecycle in {"archived", "superseded"}:
        safe_action = {"kind": "inspect", "tool": "project_health",
                       "arguments": {"project_id": project_id},
                       "reason": "Archived/superseded projects are preserved and not resumed automatically."}
    elif len(active_runs) > 1:
        safe_action = {"kind": "select_run", "tool": "resume_project_run", "arguments": {},
                       "reason": "Pass one explicit project_id and run_id; recovery never guesses."}
    elif (run and run.get("status") == "active"
          and preflight.get("state") == "waiting" and incomplete_dispatch
          and (preflight.get("next_call") or {}).get("tool")):
        call = _hydrate_preflight_call(
            dict(preflight.get("next_call") or {}), run, incomplete_dispatch,
        )
        safe_action = {
            "kind": "complete_preflight",
            "tool": str(call.get("tool") or ""),
            "arguments": dict(call.get("arguments") or {}),
            "required_input_paths": _required_placeholder_paths(call.get("arguments") or {}),
            "reason": str(preflight.get("message") or "Complete the current setup action."),
        }
    elif run and run.get("status") == "active":
        safe_action = {
            "kind": "resume_existing_run", "tool": "resume_project_run",
            "arguments": {"project_id": project_id, "run_id": run["run_id"],
                          "operation_id": str(run.get("operation_id") or "")},
            "then": {"tool": "run_step", "arguments": {"run_id": run["run_id"]}},
            "reason": ("Retry the existing deterministic dispatch and journal. This action cannot "
                       "mark the run finished."),
        }
    elif run and run.get("status") == "finished":
        safe_action = {"kind": "inspect_evidence", "tool": "project_health",
                       "arguments": {"project_id": project_id},
                       "reason": "The engine-finished journal is immutable; repair only explicit evidence findings."}
    else:
        run_operation_id = "recovery:" + hashlib.sha256(project_id.encode("utf-8")).hexdigest()
        safe_action = {"kind": "start_governed_run", "tool": "start_run",
                       "arguments": {"project_id": project_id, "operation_id": run_operation_id},
                       "reason": "No existing run can be resumed; the stable create intent prevents duplicates."}

    posture_counts: Counter[str] = Counter()
    source_counts: Counter[str] = Counter()
    for _label, record in artifact_rows:
        envelope = record.get("claim_posture") or {}
        posture_counts.update({key: int(value or 0)
                               for key, value in (envelope.get("counts") or {}).items()})
        for claim in envelope.get("claims") or []:
            source_counts.update(
                str(ref.get("kind") or "unknown") if isinstance(ref, dict) else "unknown"
                for ref in claim.get("refs") or [])

    completed_dispatch = next((row for row in reversed(list((run or {}).get("dispatches") or []))
                               if row.get("status") == "completed" and row.get("receipt")), None)
    recovery_signals = {
        "host_connection": "unknown",
        "host_connection_note": "No heartbeat contract exists; quiet activity is not proof of disconnect.",
        "retry_result": "available" if completed_dispatch else "not_observed",
        "retry_receipt": dict((completed_dispatch or {}).get("receipt") or {}),
        "dispatch": "incomplete" if incomplete_dispatch else "none_incomplete",
        "evidence": "missing" if preflight.get("state") == "waiting" or any(row["code"] in {
            "product_understanding_missing", "claim_provenance_incomplete", "invalid_evidence_ref",
            "orphaned_evidence", "expected_sections_missing", "conclusion_missing", "report_missing",
            "report_incomplete", "report_stale",
            "cohort_preflight_missing", "cohort_preflight_stale",
            "cohort_preflight_needs_deepening", "cohort_preflight_needs_reselection",
        } for row in issues) else "projected_complete",
        "critic": "pending" if any(row["code"] == "critic_pending" for row in issues) else "not_pending",
        "audit": "not_projected_in_core",
        "external_host_error": "unobservable",
    }
    return {
        "schema": PROJECT_HEALTH_SCHEMA,
        "project_id": project_id,
        "state": state,
        "driver_state": driver_state,
        "lifecycle": lifecycle,
        "engine_finished": authoritative_finished,
        "persisted_run_status": str((run or {}).get("status") or "not_started"),
        "run_inventory": {
            "active": len(active_runs),
            "historical_finished": len(finished_runs),
            "total": len(runs),
        },
        "unverified_output": state == "unverified",
        "activity_lifecycle": {
            "state": "expired" if run_expired else "current",
            "stale_after_hours": int(stale_hours),
            "expires_after_hours": int(expire_hours),
            "expires_at": activity_deadline(run_activity, expire_hours) if active_runs else "",
            "resumable": bool(active_runs),
            "note": (
                "Expiry is an inactivity projection only; the active journal remains resumable "
                "and no evidence is marked unverified."
                if run_expired else ""
            ),
        },
        "last_activity": max([str(project.get("updated_at") or "")]
                             + [str(row.get("updated_at") or "") for row in runs]),
        "run_id": str((run or {}).get("run_id") or ""),
        "run_operation_id": str((run or {}).get("operation_id") or ""),
        "project_operation_id": str(project.get("operation_id") or ""),
        "tasks": {"done": tasks_done, "total": len(tasks), "next_ready": ready},
        "last_successful_operation": last_success,
        "unmet_invariant": issues[0] if issues else None,
        "integrity_findings": issues,
        "evidence": {"posture_counts": dict(sorted(posture_counts.items())),
                     "source_counts": dict(sorted(source_counts.items())),
                     "orphaned": sum(1 for row in issues if row["code"] == "orphaned_evidence")},
        "report_handoff": report_handoff,
        "product_understanding": pu,
        "preflight": preflight,
        "safe_next_action": safe_action,
        "trace": _trace_ref(project, run),
        "recovery_signals": recovery_signals,
    }


def resume_project_run(project_id: str, run_id: str, operation_id: str = "",
                       store: Store | None = None) -> dict[str, Any]:
    """Return the existing active journal and its safe continuation; never mint/reopen/finish."""
    from ._engines import start_run

    store = store or Store()
    run = store.get_run(run_id)
    if not run or str(run.get("project_id") or "") != project_id:
        raise ValueError("RUN_SCOPE_MISMATCH: run_id does not belong to project_id")
    if run.get("status") != "active":
        raise ValueError("RUN_NOT_RESUMABLE: only an existing active run can be resumed")
    expected_operation = str(run.get("operation_id") or "")
    supplied = str(operation_id or "").strip()
    if supplied and supplied != expected_operation:
        raise ValueError("RUN_OPERATION_MISMATCH: operation_id does not match the existing run")
    resumed = start_run(project_id, run_id=run_id, store=store)
    health = project_health(project_id, store=store)
    return {
        "project_id": project_id, "run_id": run_id,
        "operation_id": expected_operation, "idempotent_replay": True,
        "cursor": resumed.get("cursor", 0), "status": resumed.get("status"),
        "safe_next_action": {"tool": "run_step", "arguments": {"run_id": run_id}},
        "unmet_invariant": health.get("unmet_invariant"),
        "trace": health["trace"],
    }


def _supersede_project_locked(project_id: str, supersedes_project_id: str, operation_id: str,
                              reason: str, store: Store | None = None) -> dict[str, Any]:
    """Explicitly preserve old→new lineage and mark the old project obsolete, never delete it."""
    store = store or Store()
    op = _opaque_operation_id(operation_id)
    reason = str(reason or "").strip()
    if not reason:
        raise ValueError("reason is required")
    if project_id == supersedes_project_id:
        raise ValueError("a project cannot supersede itself")
    newer = store.get_research_project(project_id)
    older = store.get_research_project(supersedes_project_id)
    if not newer or not older:
        raise KeyError("both project_id and supersedes_project_id must exist in this workspace")
    if any(row.get("status") == "active" for row in store.list_runs(supersedes_project_id)):
        raise ValueError(
            "ACTIVE_RUN_SUPERSEDE_BLOCKED: recover or explicitly stop the active run first"
        )

    # Follow explicit lineage only; title/goal similarity is never used.
    cursor, seen = older, {project_id}
    while cursor and cursor.get("supersedes_project_id"):
        next_id = str(cursor["supersedes_project_id"])
        if next_id in seen:
            raise ValueError("PROJECT_LINEAGE_CYCLE: superseding would create a cycle")
        seen.add(next_id)
        cursor = store.get_research_project(next_id)

    existing = dict(newer.get("lineage") or {})
    if existing.get("operation_id") == op:
        if str(newer.get("supersedes_project_id") or "") != supersedes_project_id:
            raise ValueError("PROJECT_LINEAGE_CONFLICT: operation_id already names another predecessor")
        if (str(older.get("superseded_by_project_id") or "") == project_id
                and str(older.get("status") or "") == "superseded"):
            return {"schema": PROJECT_LINEAGE_SCHEMA, "project_id": project_id,
                    "supersedes_project_id": supersedes_project_id, "operation_id": op,
                    "reason": str(existing.get("reason") or reason),
                    "evidence_deleted": False, "idempotent": True}
    elif newer.get("supersedes_project_id") and newer.get("supersedes_project_id") != supersedes_project_id:
        raise ValueError("PROJECT_LINEAGE_CONFLICT: project already supersedes another project")

    for _attempt in range(16):
        fresh = store.get_research_project(project_id) or {}
        updated = copy.deepcopy(fresh)
        updated["supersedes_project_id"] = supersedes_project_id
        updated["lineage"] = {"schema": PROJECT_LINEAGE_SCHEMA, "operation_id": op,
                              "reason": reason, "recorded_at": utc_now_iso()}
        updated["updated_at"] = utc_now_iso()
        if updated == fresh or store.compare_and_swap_research_project(fresh, updated):
            break
    else:
        raise RuntimeError("PROJECT_LINEAGE_CONTENTION: retry the same operation_id")

    # Compare-and-repair second half. A retry repairs an interrupted lineage write.
    for _attempt in range(16):
        fresh = store.get_research_project(supersedes_project_id) or {}
        prior_new = str(fresh.get("superseded_by_project_id") or "")
        if prior_new and prior_new != project_id:
            raise ValueError("PROJECT_LINEAGE_CONFLICT: predecessor is already superseded elsewhere")
        updated = copy.deepcopy(fresh)
        updated.setdefault("status_before_superseded", fresh.get("status") or "active")
        updated["status"] = "superseded"
        updated["superseded_by_project_id"] = project_id
        updated["updated_at"] = utc_now_iso()
        if updated == fresh or store.compare_and_swap_research_project(fresh, updated):
            break
    else:
        raise RuntimeError("PROJECT_LINEAGE_CONTENTION: retry the same operation_id")
    return {"schema": PROJECT_LINEAGE_SCHEMA, "project_id": project_id,
            "supersedes_project_id": supersedes_project_id, "operation_id": op,
            "reason": reason, "evidence_deleted": False, "idempotent": bool(existing)}


def supersede_project(project_id: str, supersedes_project_id: str, operation_id: str,
                      reason: str, store: Store | None = None) -> dict[str, Any]:
    """Serialize explicit lineage with run starts; preserved history is never raced closed."""
    store = store or Store()
    with project_lifecycle_locks(store, [project_id, supersedes_project_id]):
        return _supersede_project_locked(
            project_id, supersedes_project_id, operation_id, reason, store=store,
        )


def _archive_project_locked(project_id: str, operation_id: str, reason: str,
                            store: Store | None = None) -> dict[str, Any]:
    """Explicit non-destructive archive. Active runs must be recovered/stopped first."""
    store = store or Store()
    op = _opaque_operation_id(operation_id)
    reason = str(reason or "").strip()
    if not reason:
        raise ValueError("reason is required")
    if any(row.get("status") == "active" for row in store.list_runs(project_id)):
        raise ValueError("ACTIVE_RUN_ARCHIVE_BLOCKED: recover or explicitly stop the active run first")
    for _attempt in range(16):
        project = store.get_research_project(project_id)
        if not project:
            raise KeyError(f"Unknown research project: {project_id}")
        archive = dict(project.get("archive") or {})
        if archive.get("operation_id") == op:
            return {"project_id": project_id, "status": "archived", "operation_id": op,
                    "evidence_deleted": False, "idempotent": True}
        if project.get("status") == "archived":
            raise ValueError("ARCHIVE_CONFLICT: project was archived by another operation")
        updated = copy.deepcopy(project)
        updated["status_before_archive"] = project.get("status") or "active"
        updated["status"] = "archived"
        updated["archive"] = {"operation_id": op, "reason": reason, "archived_at": utc_now_iso()}
        updated["updated_at"] = utc_now_iso()
        if store.compare_and_swap_research_project(project, updated):
            return {"project_id": project_id, "status": "archived", "operation_id": op,
                    "evidence_deleted": False, "idempotent": False}
    raise RuntimeError("ARCHIVE_CONTENTION: retry the same operation_id")


def archive_project(project_id: str, operation_id: str, reason: str,
                    store: Store | None = None) -> dict[str, Any]:
    """Serialize archive with run starts and preserve all existing evidence."""
    store = store or Store()
    with project_lifecycle_locks(store, [project_id]):
        return _archive_project_locked(project_id, operation_id, reason, store=store)
