"""Retry-safe project report writes and deterministic report scaffolding."""
from __future__ import annotations

from typing import Any

from ..config import content_language, utc_now_iso
from ..llm_simulation import (
    validate_synthesis_outline_payload,
    validate_synthesis_section_payload,
)
from ..models import Synthesis
from ..report_handoff import report_handoff_state, terminal_synthesis_source_ids
from ..storage import Store
from .._project_locks import project_lifecycle_locks
from ._common import *  # noqa: F401,F403  (shared helpers + constants)


def _report_operation_id(value: str | None) -> str:
    operation_id = str(value or "").strip()
    if operation_id and (len(operation_id) > 200 or not operation_id.isprintable()):
        raise ValueError("operation_id must be at most 200 printable characters")
    return operation_id


def _outline_fingerprint(project_id: str, data: dict[str, Any]) -> str:
    return canonical_payload_fingerprint({"project_id": project_id, "outline": data})


def _outline_claims(report: dict[str, Any]) -> list[dict[str, Any]]:
    claims = [dict(row) for row in (report.get("outline_operations") or [])
              if isinstance(row, dict) and str(row.get("operation_id") or "")]
    legacy_id = str(report.get("outline_operation_id") or "")
    if legacy_id and not any(str(row.get("operation_id") or "") == legacy_id for row in claims):
        claims.append({"operation_id": legacy_id,
                       "payload_fingerprint": str(report.get("outline_payload_fingerprint") or "")})
    return claims


def _graph_source_ids(graph: dict[str, Any]) -> list[str]:
    """The canonical source universe exposed by a live or frozen project graph."""
    values = [str(value) for value in (graph.get("build_order") or []) if str(value)]
    values.extend(str(node.get("study_id") or "") for node in (graph.get("nodes") or [])
                  if str(node.get("study_id") or ""))
    return list(dict.fromkeys(values))


def _report_covers_sources(report: dict[str, Any], required: list[str]) -> bool:
    if not required:
        return True
    state = report_handoff_state(report, required_source_ids=required)
    return not bool(state["reports"][0]["source_coverage_missing"])


def _project_report_handoff(project_id: str, reports: Any, store: Store) -> dict[str, Any]:
    plan = store.get_research_plan(project_id) or {}
    return report_handoff_state(
        reports,
        required_source_ids=terminal_synthesis_source_ids(plan),
    )


def _report_has_authored_body(report: dict[str, Any]) -> bool:
    return any(str(section.get("markdown") or "").strip()
               for section in (report.get("sections") or []))


def _outline_structure(sections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{key: section.get(key) for key in (
                "id", "heading", "theme_tags", "source_study_ids", "intent")}
            for section in sections]


def _report_dispatch_result(ctx: dict[str, Any], report: dict[str, Any],
                            store: Store) -> dict[str, Any]:
    project_id = str(report.get("project_id") or ctx.get("project_id") or "")
    state = _project_report_handoff(project_id, report, store)
    if state["complete"]:
        return bind_dispatch_output(  # noqa: F821 (bound)
            ctx, {"kind": "report", "id": report["id"]},
            "authored complete project report hand-off", store,
        )
    if ctx.get("dispatch_token"):
        current = state["reports"][0]
        source_gaps = list(current.get("source_coverage_missing") or [])
        return {"state": "progress", "checkpointed": False,
                "task_id": str(ctx.get("task_id") or ""),
                "report_id": report["id"],
                "lead_missing": bool(current["lead_missing"]),
                "incomplete_section_ids": list(
                    current["incomplete_section_ids"]),
                "source_coverage_missing": source_gaps,
                "needs": (
                    "report is stale; call scaffold_synthesis with this dispatch token to create "
                    "the deterministic current hand-off"
                    if source_gaps else
                    "author the report lead and every section before the hand-off can checkpoint"
                )}
    return {"state": ctx.get("state", "outside_run"), "checkpointed": False,
            "provenance": "not governed by an active dispatch"}


def _record_synthesis_outline_locked(
    project_id: str,
    outline: dict[str, Any],
    *,
    report_id: str | None,
    operation_id: str | None,
    dispatch_ctx: dict[str, Any] | None,
    store: Store,
    force_new: bool = False,
) -> dict[str, Any]:
    project = _require_research_project(store, project_id)  # noqa: F821 (bound)
    operation_id = _report_operation_id(operation_id)
    reports = store.list_reports(project["id"])
    claimed = [(report, row) for report in reports for row in _outline_claims(report)
               if operation_id and str(row.get("operation_id") or "") == operation_id]

    target: dict[str, Any] | None = None
    if report_id:
        target = store.get_report(report_id)
        if not target:
            raise KeyError(f"Unknown report: {report_id}")
        if str(target.get("project_id") or "") != project["id"]:
            raise ValueError("REPORT_SCOPE_MISMATCH: report does not belong to project")
    elif claimed:
        target = claimed[0][0]
    elif not force_new:
        target = next((report for report in reports
                       if not report_handoff_state(report)["complete"]
                       and not _report_has_authored_body(report)), None)

    # The outline is authored against a graph, not the legacy project.study_ids list.  A report
    # repair stays inside its immutable snapshot; a new report uses the complete current graph.
    source_graph = dict((target or {}).get("graph_snapshot") or {})
    if not source_graph:
        source_graph = get_project_graph(project["id"], store=store)  # noqa: F821 (bound)
    data = validate_synthesis_outline_payload(
        outline, study_ids=_graph_source_ids(source_graph))
    fingerprint = _outline_fingerprint(project["id"], data)

    if operation_id:
        if claimed:
            report, claim = claimed[0]
            if report_id and report["id"] != report_id:
                raise ValueError(
                    "REPORT_OUTLINE_OPERATION_CONFLICT: operation_id belongs to another report")
            if str(claim.get("payload_fingerprint") or "") != fingerprint:
                raise ValueError(
                    "REPORT_OUTLINE_OPERATION_CONFLICT: operation_id was reused with a different outline")
            out = dict(report)
            out["idempotent_replay"] = True
            out["handoff"] = _project_report_handoff(project["id"], report, store)
            out["dispatch"] = _report_dispatch_result(dispatch_ctx or {}, report, store)
            return out

    if target and _report_has_authored_body(target):
        if str(target.get("outline_payload_fingerprint") or "") == fingerprint:
            out = dict(target)
            out["idempotent_replay"] = True
            out["handoff"] = _project_report_handoff(project["id"], target, store)
            out["dispatch"] = _report_dispatch_result(dispatch_ctx or {}, target, store)
            return out
        if report_id and _outline_structure(list(target.get("sections") or [])) == \
                _outline_structure(data["sections"]):
            now = utc_now_iso()
            report = dict(target)
            report["title"] = data.get("title") or f"{project['title']} — Report"
            report["lead"] = data["build_order_narrative"]
            report["outline_payload_fingerprint"] = fingerprint
            report["updated_at"] = now
            # The body was authored against the outline-time graph. A lead-only
            # repair must never widen that immutable evidence boundary to newer
            # project studies.
            claims = _outline_claims(report)
            if operation_id:
                claims.append({"operation_id": operation_id,
                               "payload_fingerprint": fingerprint,
                               "recorded_at": now})
                report["outline_operations"] = claims
            if (dispatch_ctx or {}).get("dispatch_token"):
                report["dispatch_provenance"] = {
                    "state": "governed", "dispatch_token": dispatch_ctx["dispatch_token"],
                    "run_id": dispatch_ctx["run_id"], "task_id": dispatch_ctx["task_id"],
                    "operation_id": dispatch_ctx.get("operation_id") or operation_id or "",
                }
            state = _project_report_handoff(project["id"], report, store)
            report["status"] = "done" if state["complete"] else "in_progress"
            store.upsert_synthesis(report)
            out = dict(report)
            out["idempotent_replay"] = False
            out["handoff"] = _project_report_handoff(project["id"], report, store)
            out["dispatch"] = _report_dispatch_result(dispatch_ctx or {}, report, store)
            return out
        raise ValueError(
            "REPORT_OUTLINE_LOCKED: an authored report's section structure cannot be replaced; "
            "omit report_id or use a new operation_id to create a second report")

    now = utc_now_iso()
    created_at = str((target or {}).get("created_at") or now)
    report_key = operation_id or now
    rid = str((target or {}).get("id") or stable_id("report", project["id"], report_key))
    sections = [
        {**section, "markdown": "", "citations": [], "figures": [],
         "status": "pending", "created_at": now, "updated_at": now}
        for section in data["sections"]
    ]
    if target:
        report = dict(target)
        report.update({
            "title": data.get("title") or f"{project['title']} — Report",
            "lead": data["build_order_narrative"], "sections": sections,
            "status": "in_progress", "updated_at": now,
            "graph_snapshot": get_project_graph(project["id"], store=store),  # noqa: F821 (bound)
            "limitations": list(project.get("research_limitations") or []),
            "outline_payload_fingerprint": fingerprint,
        })
    else:
        report = Synthesis(
            id=rid, title=data.get("title") or f"{project['title']} — Report",
            start_input="", council_ids=[], arc_narrative="", gesamtbild="",
            positionierung="", references=[], created_at=created_at,
            status="in_progress", scope="project", project_id=project["id"],
            lead=data["build_order_narrative"], sections=sections,
            graph_snapshot=get_project_graph(project["id"], store=store),  # noqa: F821 (bound)
        ).to_dict()
        report.update({
            "updated_at": now,
            "limitations": list(project.get("research_limitations") or []),
            "outline_payload_fingerprint": fingerprint,
        })
    claims = _outline_claims(report)
    if operation_id:
        claims.append({"operation_id": operation_id, "payload_fingerprint": fingerprint,
                       "recorded_at": now})
        report["outline_operations"] = claims
    if (dispatch_ctx or {}).get("dispatch_token"):
        report["dispatch_provenance"] = {
            "state": "governed", "dispatch_token": dispatch_ctx["dispatch_token"],
            "run_id": dispatch_ctx["run_id"], "task_id": dispatch_ctx["task_id"],
            "operation_id": dispatch_ctx.get("operation_id") or operation_id or "",
        }
    store.upsert_synthesis(report)
    out = dict(report)
    out["idempotent_replay"] = False
    out["handoff"] = _project_report_handoff(project["id"], report, store)
    out["dispatch"] = _report_dispatch_result(dispatch_ctx or {}, report, store)
    return out


def record_synthesis_outline(
    project_id: str,
    outline: dict[str, Any],
    store: Store | None = None,
    report_id: str | None = None,
    operation_id: str | None = None,
    dispatch_token: str | None = None,
) -> dict[str, Any]:
    """Persist a retry-safe project report outline."""
    store = store or Store()
    with project_lifecycle_locks(store, [project_id]):
        project = _require_research_project(store, project_id)  # noqa: F821 (bound)
        operation_id = _report_operation_id(operation_id)
        dispatch_ctx = prepare_dispatch_write(  # noqa: F821 (bound)
            project["id"], dispatch_token, operation_id or None, "report", store,
            allowed_buckets={"verify"},
        )
        return _record_synthesis_outline_locked(
            project["id"], outline, report_id=report_id, operation_id=operation_id,
            dispatch_ctx=dispatch_ctx, store=store,
        )


def record_synthesis_section(project_id: str, section_id: str, content: dict[str, Any],
                             report_id: str | None = None, store: Store | None = None,
                             dispatch_token: str | None = None) -> dict[str, Any]:
    """Author one section and checkpoint only when the report is complete."""
    store = store or Store()
    with project_lifecycle_locks(store, [project_id]):
        project = _require_research_project(store, project_id)  # noqa: F821 (bound)
        report = _latest_report(store, project["id"], report_id)  # noqa: F821 (bound)
        dispatch_ctx = prepare_dispatch_write(  # noqa: F821 (bound)
            project["id"], dispatch_token, None, "report", store,
            allowed_buckets={"verify"},
        )
        sec = next((s for s in report.get("sections", []) if s.get("id") == section_id), None)
        if not sec:
            raise KeyError(f"Unknown section {section_id} in report {report['id']}")
        data = validate_synthesis_section_payload(content)
        same = (
            str(sec.get("markdown") or "") == data["markdown"]
            and list(sec.get("citations") or []) == data["citations"]
            and list(sec.get("figures") or []) == data.get("figures", [])
        )
        if report_handoff_state(report)["complete"] and not same:
            raise ValueError(
                "REPORT_FINALIZED_CONFLICT: a completed report cannot be revised in place; "
                "create a second report with record_synthesis_outline")
        now = utc_now_iso()
        if not same or not sec.get("status") or not sec.get("updated_at"):
            sec["markdown"] = data["markdown"]
            sec["citations"] = data["citations"]
            sec["figures"] = data.get("figures", [])
            sec["status"] = "done" if data["markdown"] else "pending"
            sec.setdefault("created_at", now)
            sec["updated_at"] = now
            state = _project_report_handoff(project["id"], report, store)
            report["status"] = "done" if state["complete"] else "in_progress"
            report["updated_at"] = now
            if dispatch_ctx.get("dispatch_token"):
                report["dispatch_provenance"] = {
                    "state": "governed", "dispatch_token": dispatch_ctx["dispatch_token"],
                    "run_id": dispatch_ctx["run_id"], "task_id": dispatch_ctx["task_id"],
                    "operation_id": dispatch_ctx.get("operation_id") or "",
                }
            store.upsert_synthesis(report)
        out = dict(report)
        out["idempotent_replay"] = same
        out["handoff"] = _project_report_handoff(project["id"], report, store)
        out["dispatch"] = _report_dispatch_result(dispatch_ctx, report, store)
        return out


def scaffold_synthesis(project_id: str, store: Store | None = None,
                       operation_id: str | None = None,
                       dispatch_token: str | None = None) -> dict[str, Any]:
    """Seed or recover the truthful project report hand-off outline."""
    store = store or Store()
    with project_lifecycle_locks(store, [project_id]):
        _require_research_project(store, project_id)  # noqa: F821 (bound)
        dispatch_ctx = prepare_dispatch_write(  # noqa: F821 (bound)
            project_id, dispatch_token, operation_id, "report", store,
            allowed_buckets={"verify"},
        )
        graph = get_project_graph(project_id, store=store)  # noqa: F821 (bound)
        required_sources = terminal_synthesis_source_ids(graph)
        require_fresh = bool(required_sources)
        existing = store.list_reports(project_id)
        requested_operation_id = _report_operation_id(
            operation_id or dispatch_ctx.get("operation_id"))
        implicit_default_operation = not bool(requested_operation_id)
        effective_operation_id = requested_operation_id or "sonaloop:scaffold-report:v1"
        refresh_derived = False
        if effective_operation_id:
            replay_report = next((
                report for report in existing
                if any(str(claim.get("operation_id") or "") == effective_operation_id
                       for claim in _outline_claims(report))
            ), None)
            # A pre-terminal report may carry the same legacy operation claim. Never widen its
            # frozen snapshot in place; derive one stable refresh intent from the current terminal
            # synthesis so every retry converges on the same replacement report.
            if replay_report and require_fresh and not _report_covers_sources(
                    replay_report, required_sources):
                effective_operation_id = stable_id(  # noqa: F821 (bound)
                    "report_refresh", project_id, effective_operation_id, *required_sources)
                refresh_derived = True
                replay_report = next((
                    report for report in existing
                    if any(str(claim.get("operation_id") or "") == effective_operation_id
                           for claim in _outline_claims(report))
                ), None)
            # The implicit default scaffold doubles as a repair operation for
            # legacy generated leads/status. Let the eligible-report path do
            # that maintenance; explicit/dispatch and derived refresh intents
            # retain strict idempotent replay semantics.
            if replay_report and (not implicit_default_operation or refresh_derived):
                out = dict(replay_report)
                out["idempotent_replay"] = True
                out["handoff"] = _project_report_handoff(project_id, replay_report, store)
                out["dispatch"] = _report_dispatch_result(dispatch_ctx, replay_report, store)
                return out
        eligible = [report for report in existing
                    if not require_fresh or _report_covers_sources(report, required_sources)]
        if eligible:
            report = eligible[0]
            now = utc_now_iso()
            changed = False
            if str(report.get("lead") or "").startswith("Auto-seeded outline for "):
                report["lead"] = (
                    "Dieser Bericht führt die Evidenz entlang der Forschungsphasen von der "
                    "Ausgangsfrage bis zu den priorisierten Schlussfolgerungen zusammen."
                    if content_language() == "de"
                    else "This report traces the evidence through the research phases from the "
                         "initial question to the prioritized conclusions."
                )
                changed = True
            state = _project_report_handoff(project_id, report, store)
            truthful_status = "done" if state["complete"] else "in_progress"
            if report.get("status") != truthful_status:
                report["status"] = truthful_status
                changed = True
            for section in report.get("sections") or []:
                section_status = "done" if str(section.get("markdown") or "").strip() else "pending"
                if section.get("status") != section_status:
                    section["status"] = section_status
                    changed = True
                if not section.get("created_at"):
                    section["created_at"] = str(report.get("created_at") or now)
                    changed = True
                if not section.get("updated_at"):
                    section["updated_at"] = str(
                        report.get("updated_at") or report.get("created_at") or now)
                    changed = True
            if (effective_operation_id
                    and not any(str(claim.get("operation_id") or "") == effective_operation_id
                                for claim in _outline_claims(report))):
                report["outline_operations"] = [
                    *_outline_claims(report),
                    {"operation_id": effective_operation_id,
                     "payload_fingerprint": str(report.get("outline_payload_fingerprint") or ""),
                     "recorded_at": now},
                ]
                changed = True
            if changed:
                report["updated_at"] = now
                store.upsert_synthesis(report)
            out = dict(report)
            out["idempotent_replay"] = not changed
            out["handoff"] = _project_report_handoff(project_id, report, store)
            out["dispatch"] = _report_dispatch_result(dispatch_ctx, report, store)
            return out
        nodes = graph["nodes"]
        steps = (graph.get("methodology_state") or {}).get("steps") or []
        by_phase: dict[str, list[str]] = {}
        for node in nodes:
            by_phase.setdefault(node.get("phase", ""), []).append(node["study_id"])
        graph_sources = [value for value in dict.fromkeys(graph.get("build_order") or []) if value]
        sections = []
        for step in steps:
            srcs = [x for x in dict.fromkeys(by_phase.get(step["key"], [])) if x]
            # Structural methodology phases (notably Product/Cohort preflight)
            # can have no node of their own. Freeze the whole current graph as
            # their declared source set so later section prose remains citable.
            if not srcs:
                srcs = list(graph_sources)
            label = (step.get("name") or step["key"]).split("·")[-1].strip() or step["key"]
            role = "diverge" if step.get("is_fan") else "converge"
            sections.append({"heading": label, "theme_tags": [], "source_study_ids": srcs,
                             "intent": f"Author the {label} phase ({role}) grounded in its evidence + what it produced."})
        if not sections:
            sections = [{"heading": "Findings", "intent": "Author the project's findings + conclusion.",
                         "theme_tags": [], "source_study_ids": graph_sources}]
        outline = {"build_order_narrative": (
                       "Dieser Bericht führt die Evidenz entlang der Forschungsphasen von der "
                       "Ausgangsfrage bis zu den priorisierten Schlussfolgerungen zusammen."
                       if content_language() == "de"
                       else "This report traces the evidence through the research phases from the "
                            "initial question to the prioritized conclusions."),
                   "sections": sections}
        return _record_synthesis_outline_locked(
            project_id, outline, report_id=None,
            operation_id=effective_operation_id,
            dispatch_ctx=dispatch_ctx, store=store,
            force_new=bool(require_fresh and existing),
        )
