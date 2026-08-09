"""Versioned cohort-integrity preflight and remediation-plan write-back."""
from __future__ import annotations

import copy
from typing import Any

from .. import plan as _plan
from ..cohort_integrity import (
    COHORT_PREFLIGHT_SCHEMA,
    COHORT_POLICY_VERSION,
    DEFAULT_THRESHOLDS,
    current_cohort_preflight,
    digest as cohort_digest,
    evaluate_cohort,
    framed_research_inputs,
)
from ..config import utc_now_iso
from ..research_integrity import (
    IntegrityError,
    operation_fingerprint,
    project_policy,
    reaction_preflight_action,
)
from ..storage import Store

from ._common import *  # noqa: F401,F403  (stable_id, web_url)


def _required_project(store: Store, project_id: str) -> dict[str, Any]:
    project = store.get_research_project(project_id)
    if not project:
        raise IntegrityError("UNKNOWN_PROJECT", f"unknown research project: {project_id}")
    return project


def brief_cohort_preflight(project_id: str, hypotheses: list[str] | None = None,
                           store: Store | None = None) -> dict[str, Any]:
    """Gather the deterministic depth/leakage inputs before a governed council."""
    store = store or Store()
    project = _required_project(store, project_id)
    now = utc_now_iso()
    framed = framed_research_inputs(project_id, store)
    additional = [str(row).strip() for row in hypotheses or [] if str(row).strip()]
    effective = list(dict.fromkeys([
        *framed["questions"], *framed["hypotheses"], *additional,
    ]))
    preview = evaluate_cohort(project, effective, [], None, store, evaluated_at=now)
    _bind_frame_boundary(preview, framed, additional)
    return {
        "schema": COHORT_PREFLIGHT_SCHEMA,
        "policy_version": COHORT_POLICY_VERSION,
        "project_id": project_id,
        "current": current_cohort_preflight(project),
        "action": reaction_preflight_action(project_id, store),
        "preview": preview,
        "required_input": {
            "framed_research": {
                "frame_ids": framed["frame_ids"], "questions": framed["questions"],
                "hypotheses": framed["hypotheses"],
                "note": "server-owned input; it cannot be omitted or replaced by the host",
            },
            "hypotheses": "optional additional hypotheses; framed research and project stimulus are always included",
            "representation": {
                "shape": [{"persona_id": "…", "posture": "target|skeptical|indifferent|non_target",
                           "rationale": "…", "basis_quote": "verbatim independent context",
                           "evidence_refs": [{"kind": "fact|event|evidence", "id": "…"}]}],
                "minimum_countervoices": DEFAULT_THRESHOLDS["min_countervoices"],
                "countervoice_rule": (
                    "skeptical/indifferent/non_target declarations count only when basis_quote "
                    "matches a cited persona-owned fact/event/evidence record predating the project"
                ),
            },
            "semantic_feature": {
                "optional": True,
                "schema": "sonaloop.semantic_overlap.v1",
                "shape": {"feature_version": "…", "model_id": "…",
                          "scores": [{"persona_id": "…", "input_digest": "…", "score": 0.0}]},
                "input_digests": preview["leakage"]["semantic_inputs"],
                "note": "the server applies one provider-neutral threshold; lexical features always run",
            },
        },
        "instructions": (
            "Treat Product Understanding as external product stimulus and persona facts/events/evidence "
            "that predate project creation as independent target context. Declare at least one "
            "skeptical, indifferent or non-target cohort member with a concrete rationale, an exact "
            "basis_quote and its independent persona-owned evidence ref. Unverified declarations fail "
            "closed. Then call "
            "record_cohort_preflight with this dispatch_token. A pass auto-links/checkpoints. A thin "
            "or circular cohort records an immutable result and injects a required remediation task; "
            "deepen or reselect, then evaluate again on the next run_step dispatch. Overrides are "
            "allowed only with an explicit rationale and are copied into report limitations."
        ),
    }


def _bind_frame_boundary(result: dict[str, Any], framed: dict[str, Any],
                         additional: list[str]) -> None:
    boundary = result.setdefault("stimulus_boundary", {})
    boundary.update({
        "frame_ids": list(framed["frame_ids"]),
        "frame_questions_count": len(framed["questions"]),
        "frame_questions_digest": framed["questions_digest"],
        "frame_hypotheses_count": len(framed["hypotheses"]),
        "frame_hypotheses_digest": framed["hypotheses_digest"],
        "additional_hypotheses_digest": cohort_digest(additional),
    })


def _cohort_selection(project: dict[str, Any], persona_ids: list[str] | None,
                      selection_rationale: str, store: Store) -> dict[str, Any]:
    if persona_ids is None:
        return project
    selected = list(dict.fromkeys(str(pid).strip() for pid in persona_ids if str(pid).strip()))
    current = list(project.get("persona_ids") or [])
    if selected == current:
        return project
    rationale = str(selection_rationale or "").strip()
    if len(rationale) < 12:
        raise IntegrityError(
            "COHORT_SELECTION_RATIONALE_REQUIRED",
            "changing a governed cohort requires a concrete selection rationale",
        )
    unknown = [pid for pid in selected if not store.get_persona(pid)]
    if unknown:
        raise IntegrityError("UNKNOWN_PERSONA", f"selected cohort contains unknown personas: {unknown}")
    updated = copy.deepcopy(project)
    updated["persona_ids"] = selected
    updated.setdefault("cohort_revisions", []).append({
        "from": current, "to": selected, "rationale": rationale, "created_at": utc_now_iso(),
    })
    return updated


def select_reaction_test_cohort(
    project_id: str,
    persona_ids: list[str],
    selection_rationale: str,
    operation_id: str = "",
    dispatch_token: str | None = None,
    store: Store | None = None,
) -> dict[str, Any]:
    """Select a bounded Reaction-Test cohort without pretending the gate passed.

    This supporting mutation is intentionally separate from
    :func:`record_cohort_preflight`: it lets a minimal host repair an empty
    cohort on the frame dispatch, after Product Understanding and before the
    frame is authored. The later server-owned gate still evaluates depth,
    leakage and grounded countervoice representation.
    """
    store = store or Store()
    project = _required_project(store, project_id)
    plan = _plan.get_plan(project_id, store=store) or {}
    if not project_policy(project, plan).get("cohort_preflight_required"):
        raise IntegrityError(
            "COHORT_SELECTION_NOT_APPLICABLE",
            "select_reaction_test_cohort is only available on a cohort-governed project",
        )
    selected = list(dict.fromkeys(str(pid).strip() for pid in persona_ids or []
                                  if str(pid).strip()))
    if len(selected) > 100:
        raise IntegrityError("COHORT_SELECTION_BAD_INPUT",
                             "persona_ids may contain at most 100 unique personas")
    if len(selected) < int(DEFAULT_THRESHOLDS["min_personas"]):
        raise IntegrityError(
            "COHORT_MISSING_OR_TOO_SMALL",
            f"persona_ids must contain at least {DEFAULT_THRESHOLDS['min_personas']} existing "
            "personas; safe retry: catalog_recommend/catalog_pull, then repeat the exact "
            "select_reaction_test_cohort call",
        )
    rationale = str(selection_rationale or "").strip()
    if len(rationale) < 12:
        raise IntegrityError(
            "COHORT_SELECTION_RATIONALE_REQUIRED",
            "selection_rationale must contain at least 12 characters explaining the independent contrast",
        )
    if len(rationale) > 2_000:
        raise IntegrityError("COHORT_SELECTION_RATIONALE_REQUIRED",
                             "selection_rationale may contain at most 2000 characters")
    unknown = [pid for pid in selected if not store.get_persona(pid)]
    if unknown:
        raise IntegrityError(
            "UNKNOWN_PERSONA",
            f"persona_ids contains unknown personas {unknown}; safe retry after catalog_pull or use "
            "IDs returned by list_personas",
        )
    op = str(operation_id or dispatch_token or "").strip()
    if op and (len(op) > 200 or not op.isprintable()):
        raise IntegrityError("COHORT_SELECTION_BAD_INPUT",
                             "operation_id must contain 1-200 printable characters")
    authored = {"persona_ids": selected, "selection_rationale": rationale}
    fingerprint = operation_fingerprint(authored)
    ctx = prepare_dispatch_write(  # noqa: F821 (bound by services package)
        project_id, dispatch_token, None, "cohort_selection", store,
        allowed_buckets={"analyze"}, payload_fingerprint=fingerprint,
    )

    replay = False
    revision: dict[str, Any] | None = None
    for _attempt in range(16):
        current = _required_project(store, project_id)
        if op:
            previous = next((row for row in current.get("cohort_revisions") or []
                             if str(row.get("operation_id") or "") == op), None)
            if previous:
                if str(previous.get("operation_fingerprint") or "") != fingerprint:
                    raise IntegrityError(
                        "COHORT_SELECTION_IDEMPOTENCY_CONFLICT",
                        "operation_id was already used for a different cohort selection",
                    )
                revision, replay = previous, True
                break
        before = list(current.get("persona_ids") or [])
        if before == selected:
            revision = {
                "from": before, "to": selected, "rationale": rationale,
                "operation_id": op, "operation_fingerprint": fingerprint,
                "created_at": str(current.get("updated_at") or current.get("created_at") or utc_now_iso()),
            }
            replay = True
            break
        revision = {
            "from": before, "to": selected, "rationale": rationale,
            "operation_id": op, "operation_fingerprint": fingerprint,
            "created_at": utc_now_iso(),
        }
        updated = copy.deepcopy(current)
        updated["persona_ids"] = selected
        updated.setdefault("cohort_revisions", []).append(revision)
        updated["updated_at"] = utc_now_iso()
        if store.compare_and_swap_research_project(current, updated):
            break
        revision = None
    if revision is None:
        raise IntegrityError(
            "COHORT_SELECTION_CONTENTION",
            "the project changed repeatedly; retry the same operation_id and arguments",
        )
    return {
        "schema": "sonaloop.reaction_cohort_selection.v1",
        "project_id": project_id,
        "persona_ids": selected,
        "minimum_personas": int(DEFAULT_THRESHOLDS["min_personas"]),
        "selection_rationale": rationale,
        "operation_id": op,
        "idempotent_replay": replay,
        "gate_passed": False,
        "next": {
            "tool": "run_step",
            "arguments": {"run_id": str(ctx.get("run_id") or "<active run id>")},
            "note": "The same frame dispatch remains open; run_step returns its updated one-action contract.",
        },
        "dispatch": {
            "state": "supporting_write" if ctx.get("dispatch_token") else ctx.get("state"),
            "checkpointed": False,
            "dispatch_token": str(ctx.get("dispatch_token") or ""),
            "task_id": str(ctx.get("task_id") or ""),
        },
    }


def _remediation_task(project_id: str, task_id: str, record: dict[str, Any],
                      store: Store) -> str:
    """Insert one required next preflight and put it between this task and all consumers."""
    plan = _plan.get_plan(project_id, store=store)
    if not plan:
        raise IntegrityError("NO_PLAN", f"project {project_id} has no research plan")
    remediation_id = f"preflight__cohort_remediation_v{record['version']}"
    if any(t.get("id") == remediation_id for t in plan.get("tasks") or []):
        return remediation_id
    current = next((t for t in plan.get("tasks") or [] if t.get("id") == task_id), None)
    if not current:
        raise IntegrityError("BAD_COHORT_DISPATCH", f"cohort task {task_id!r} no longer exists")
    for task in plan["tasks"]:
        if task.get("id") == task_id:
            continue
        task["consumes"] = [remediation_id if ref == task_id else ref
                            for ref in task.get("consumes") or []]
    codes = [str(row.get("code") or "") for row in record.get("required_work") or []]
    plan["tasks"].append({
        "id": remediation_id,
        "title": "Preflight · Cohort remediation",
        "bucket": "analyze",
        "capability": "cohort_integrity",
        "step": "__preflight__",
        "consumes": [task_id],
        "intent": (
            f"Resolve the server-owned cohort gate ({record['raw_status']}): "
            f"{', '.join(codes)}. Execute the structured required_work using catalog/deepening/"
            "grounding tools, then call record_cohort_preflight with this dispatch token."
        ),
        "plan_note": f"cohort_preflight:{record['id']}",
        "produces": [],
    })
    plan["updated_at"] = utc_now_iso()
    _plan.save_plan(plan, store=store)
    return remediation_id


def _sync_report_limitation(store: Store, project_id: str,
                            limitation: dict[str, Any]) -> None:
    for report in store.list_reports(project_id):
        rows = list(report.get("limitations") or [])
        if not any(row.get("id") == limitation["id"] for row in rows):
            rows.append(copy.deepcopy(limitation))
            report["limitations"] = rows
            report["updated_at"] = utc_now_iso()
            store.upsert_synthesis(report)


def record_cohort_preflight(
    project_id: str,
    hypotheses: list[str] | None = None,
    representation: list[dict[str, Any]] | None = None,
    semantic_feature: dict[str, Any] | None = None,
    override_rationale: str = "",
    persona_ids: list[str] | None = None,
    selection_rationale: str = "",
    evaluated_at: str | None = None,
    key: str | None = None,
    dispatch_token: str | None = None,
    store: Store | None = None,
) -> dict[str, Any]:
    """Evaluate, persist and bind one immutable cohort-integrity version.

    Failed versions are completed as evidence of the failed gate and inject a
    new, required remediation task.  This lets the deterministic run journal
    explain every attempt while preventing the product-reaction frame from
    becoming ready.  A rationale-bearing override is explicit, never inferred.
    """
    store = store or Store()
    ctx = prepare_dispatch_write(  # noqa: F821 (bound by services package)
        project_id, dispatch_token, key, "cohort_preflight", store,
        allowed_buckets={"analyze"}, required_capability="cohort_integrity",
    )
    operation_id = str(ctx.get("operation_id") or key or "").strip()
    stamp = str(evaluated_at or utc_now_iso())
    additional_hypotheses = [str(row).strip() for row in hypotheses or [] if str(row).strip()]
    framed = framed_research_inputs(project_id, store)
    clean_hypotheses = list(dict.fromkeys([
        *framed["questions"], *framed["hypotheses"], *additional_hypotheses,
    ]))
    override = str(override_rationale or "").strip()

    record: dict[str, Any] | None = None
    replay = False
    limitation: dict[str, Any] | None = None
    for _attempt in range(16):
        current_project = _required_project(store, project_id)
        working = _cohort_selection(current_project, persona_ids, selection_rationale, store)
        selected = list(working.get("persona_ids") or [])
        authored = {
            "hypotheses": clean_hypotheses,
            "frame_questions_digest": framed["questions_digest"],
            "frame_hypotheses_digest": framed["hypotheses_digest"],
            "representation": representation or [],
            "semantic_feature": semantic_feature or {},
            "override_rationale": override,
            "persona_ids": selected,
            "selection_rationale": str(selection_rationale or "").strip(),
        }
        fingerprint = operation_fingerprint(authored)
        versions = current_project.get("cohort_preflight_versions") or []
        if operation_id:
            existing = next((row for row in versions
                             if str(row.get("operation_id") or "") == operation_id), None)
            if existing:
                if str(existing.get("operation_fingerprint") or "") != fingerprint:
                    raise IntegrityError(
                        "COHORT_PREFLIGHT_IDEMPOTENCY_CONFLICT",
                        "the cohort-preflight operation key was reused with different content",
                    )
                record, replay = existing, True
                break

        result = evaluate_cohort(working, clean_hypotheses, representation,
                                 semantic_feature, store, evaluated_at=stamp)
        _bind_frame_boundary(result, framed, additional_hypotheses)
        raw_status = str(result["status"])
        if override:
            if raw_status == "pass":
                raise IntegrityError("UNNECESSARY_COHORT_OVERRIDE",
                                     "a passing cohort must not be labelled overridden")
            if len(override) < 20:
                raise IntegrityError("COHORT_OVERRIDE_RATIONALE_REQUIRED",
                                     "override rationale must be at least 20 characters")
            result["status"] = "overridden"
            result["override"] = {
                "rationale": override, "original_status": raw_status,
                "accepted_at": stamp,
            }
        version = len(versions) + 1
        record_id = (stable_id("cohort_preflight", project_id, operation_id)  # noqa: F821
                     if operation_id else stable_id("cohort_preflight", project_id, stamp))  # noqa: F821
        record = {
            **result, "id": record_id, "project_id": project_id,
            "version": version, "raw_status": raw_status,
            "supersedes": str((current_cohort_preflight(current_project) or {}).get("id") or ""),
            "operation_id": operation_id,
            "operation_fingerprint": fingerprint,
        }
        updated = copy.deepcopy(working)
        updated.setdefault("cohort_preflight_versions", []).append(record)
        updated["cohort_preflight_current_id"] = record_id
        updated["updated_at"] = utc_now_iso()
        if result["status"] == "overridden":
            limitation = {
                "id": stable_id("limitation", record_id),  # noqa: F821
                "schema": "sonaloop.report_limitation.v1",
                "kind": "cohort_integrity_override",
                "cohort_preflight_id": record_id,
                "original_status": raw_status,
                "rationale": override,
                "created_at": stamp,
            }
            updated.setdefault("research_limitations", []).append(limitation)
        if store.compare_and_swap_research_project(current_project, updated):
            break
        record = None
    if record is None:
        raise IntegrityError("COHORT_PREFLIGHT_CONTENTION",
                             "project changed repeatedly; retry the same operation key")

    if not replay and record["status"] in {"needs_deepening", "needs_reselection"}:
        record["remediation_task_id"] = _remediation_task(
            project_id, str(ctx.get("task_id") or ""), record, store)
        # Persist the task id on the immutable version as a repairable projection.
        project = _required_project(store, project_id)
        for row in project.get("cohort_preflight_versions") or []:
            if row.get("id") == record["id"]:
                row["remediation_task_id"] = record["remediation_task_id"]
        store.upsert_research_project(project)
    elif replay and record["status"] in {"needs_deepening", "needs_reselection"}:
        _remediation_task(project_id, str(ctx.get("task_id") or ""), record, store)
    # A retry after the project version was committed but before report syncing
    # must repair the same limitation projection, not silently skip it.
    if record["status"] == "overridden":
        project = _required_project(store, project_id)
        limitation = next((row for row in project.get("research_limitations") or []
                           if row.get("cohort_preflight_id") == record["id"]), limitation)
    if limitation:
        _sync_report_limitation(store, project_id, limitation)

    dispatch = bind_dispatch_output(  # noqa: F821 (bound)
        ctx, {"kind": "cohort_preflight", "id": record["id"]},
        f"recorded cohort gate {record['status']}", store,
    )
    return {
        **record,
        "idempotent_replay": replay,
        "dispatch": dispatch,
        "project_url": web_url(f"/jobs/{project_id}"),  # noqa: F821
    }


def get_cohort_preflight(project_id: str, version_id: str | None = None,
                         store: Store | None = None) -> dict[str, Any]:
    store = store or Store()
    project = _required_project(store, project_id)
    versions = project.get("cohort_preflight_versions") or []
    record = (next((row for row in versions if str(row.get("id") or "") == version_id), None)
              if version_id else current_cohort_preflight(project))
    if not record:
        raise KeyError(f"No cohort preflight for project {project_id}")
    return {
        **record,
        "history": [{"id": row.get("id"), "version": row.get("version"),
                     "status": row.get("status"), "raw_status": row.get("raw_status"),
                     "evaluated_at": row.get("evaluated_at"),
                     "supersedes": row.get("supersedes", "")}
                    for row in versions],
        "limitations": [row for row in project.get("research_limitations") or []
                        if row.get("cohort_preflight_id") == record.get("id")],
    }


def report_limitations(project_id: str, store: Store | None = None) -> list[dict[str, Any]]:
    """Canonical project limitations copied into every project-scope report."""
    store = store or Store()
    return list((_required_project(store, project_id).get("research_limitations") or []))
