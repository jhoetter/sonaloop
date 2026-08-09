"""Canonical project health, safe run recovery, and project lineage.

The web inspector, MCP and CLI all consume this projector.  It deliberately
uses persisted run/plan/integrity records only: prose length, provider names,
and a host's generic error message are never promoted into research truth.
"""
from __future__ import annotations

import copy
from collections import Counter
from datetime import datetime, timedelta, timezone
import hashlib
from typing import Any

from ..config import utc_now_iso
from ..research_integrity import (
    artifact_posture_gaps,
    current_product_understanding,
    is_reaction_project,
    resolve_project_ref,
)
from ..storage import Store
from .._project_locks import project_lifecycle_locks


PROJECT_HEALTH_SCHEMA = "sonaloop.project_health.v1"
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


def _is_quiet(timestamp: str, stale_hours: int) -> bool:
    try:
        value = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) - value > timedelta(hours=stale_hours)
    except (TypeError, ValueError):
        return False


def _ref_exists(project_id: str, ref: dict[str, Any], store: Store) -> bool:
    try:
        resolve_project_ref(project_id, ref, store)
        return True
    except Exception:
        return False


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


def _trace_ref(project: dict[str, Any], run: dict[str, Any] | None) -> dict[str, Any]:
    ingress = dict(project.get("research_job_ingress") or {})
    operation_id = str(ingress.get("operation_id") or project.get("operation_id") or "")
    raw = "|".join((str(project.get("id") or ""), str((run or {}).get("run_id") or ""),
                    operation_id))
    support_ref = "sltrace_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]
    query = {"project_id": project.get("id")}
    if run:
        query["run_id"] = run.get("run_id")
    if operation_id:
        query["operation_id"] = operation_id
    return {
        "support_ref": support_ref,
        "local_journal": "available" if run else "not_started",
        "cloud_trace_query": query,
        "external_host_visibility": "not_observable",
        "limitation": (
            "Sonaloop records its MCP boundary and local run journal. It cannot observe hidden "
            "provider prompts, reasoning, permission dialogs, internal retries, or host-only errors."
        ),
    }


def project_health(project_id: str, store: Store | None = None,
                   stale_hours: int = 6) -> dict[str, Any]:
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
    # The currently actionable run is authoritative.  A historical finished
    # journal must never upgrade a newer active attempt to "finished" while
    # the recovery action correctly says to resume that active attempt.
    authoritative_finished = bool(run and run.get("status") == "finished")
    tasks = list((plan or {}).get("tasks") or [])
    ready = [row["id"] for row in plan_mod.ready_tasks(plan)] if plan else []
    tasks_done = sum(1 for row in tasks if row.get("status") == "done")
    plan_complete = bool(plan and plan_mod.is_complete(plan))

    issues: list[dict[str, Any]] = []

    def issue(code: str, message: str, *, target: str = "", severity: str = "blocking") -> None:
        row = {"code": code, "message": message, "severity": severity}
        if target:
            row["target"] = target
        if not any(x.get("code") == code and x.get("target") == target for x in issues):
            issues.append(row)

    if len(active_runs) > 1:
        issue("multiple_active_runs", "Multiple active runs exist; select an explicit run id before recovery.")

    pu = _product_understanding_health(project)
    if pu["required"] and not pu["present"]:
        issue("product_understanding_missing",
              "The mandatory evidence-bound Product Understanding preflight is missing.",
              target=f"/jobs/{project_id}#product-understanding")

    linked = {(str(ref.get("kind") or ""), str(ref.get("id") or ""))
              for task in tasks for ref in (task.get("produces") or [])
              if ref.get("kind") and ref.get("id")}
    artifact_rows = _artifact_rows(project_id, store)
    claim_contract_required = is_reaction_project(project, plan)
    for label, record in artifact_rows:
        kind, rid = label.split(":", 1)
        if (kind, rid) not in linked:
            issue("orphaned_evidence", f"{label} is not linked to a plan task.",
                  target=f"/{'councils' if kind == 'council' else 'syntheses'}/{rid}")
        if claim_contract_required or record.get("claim_posture"):
            for gap in artifact_posture_gaps(record, label):
                issue("claim_provenance_incomplete", gap,
                      target=f"/{'councils' if kind == 'council' else 'syntheses'}/{rid}#claim-health")
        envelope = record.get("claim_posture") or {}
        for claim in envelope.get("claims") or []:
            for ref in claim.get("refs") or []:
                if not _ref_exists(project_id, ref, store):
                    cid = str(claim.get("id") or "")
                    issue("invalid_evidence_ref", f"{label} claim {cid or 'unknown'} has an invalid reference.",
                          target=(f"/{'councils' if kind == 'council' else 'syntheses'}/{rid}"
                                  + (f"#{cid}" if cid else "#claim-health")))

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

    unverified = any(row["code"] in {
        "product_understanding_missing", "orphaned_evidence", "claim_provenance_incomplete",
        "invalid_evidence_ref", "assessment_unavailable", "engine_completion_missing",
        "expected_sections_missing", "conclusion_missing", "report_missing",
        "result_contract_missing",
    } for row in issues)
    lifecycle = str(project.get("status") or "active")
    if lifecycle in {"archived", "superseded"}:
        driver_state = lifecycle
        state = lifecycle
    elif active_runs:
        quiet = _is_quiet(str((run or {}).get("updated_at") or ""), stale_hours)
        driver_state = "stalled" if quiet else "running"
        state = driver_state
    elif authoritative_finished:
        driver_state = "engine_finished"
        state = "unverified" if unverified else "finished"
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
            source_counts.update(str(ref.get("kind") or "unknown")
                                 for ref in claim.get("refs") or [])

    completed_dispatch = next((row for row in reversed(list((run or {}).get("dispatches") or []))
                               if row.get("status") == "completed" and row.get("receipt")), None)
    recovery_signals = {
        "host_connection": "unknown",
        "host_connection_note": "No heartbeat contract exists; quiet activity is not proof of disconnect.",
        "retry_result": "available" if completed_dispatch else "not_observed",
        "retry_receipt": dict((completed_dispatch or {}).get("receipt") or {}),
        "dispatch": "incomplete" if incomplete_dispatch else "none_incomplete",
        "evidence": "missing" if any(row["code"] in {
            "product_understanding_missing", "claim_provenance_incomplete", "invalid_evidence_ref",
            "orphaned_evidence", "expected_sections_missing", "conclusion_missing", "report_missing",
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
        "run_inventory": {
            "active": len(active_runs),
            "historical_finished": len(finished_runs),
            "total": len(runs),
        },
        "unverified_output": unverified,
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
        "product_understanding": pu,
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
