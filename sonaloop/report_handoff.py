"""Truthful completion state for project-scope report hand-offs.

A report outline is only a draft.  The hand-off exists when at least one
project report has one or more sections and every section has an authored body.
Persisted ``status`` fields are intentionally not trusted for this decision so
legacy reports that were incorrectly stored as ``done`` while empty remain
visible as incomplete, while fully-authored legacy reports continue to work.
"""
from __future__ import annotations

from collections.abc import Iterable
from typing import Any


def terminal_synthesis_source_ids(plan_or_graph: dict[str, Any] | None) -> list[str]:
    """Return the latest verify-produced synthesis as a report source id.

    Callers may pass either a plan directly or a project graph containing ``plan``. Keeping this
    derivation beside the hand-off contract prevents assessment, recovery and report writes from
    disagreeing about which conclusion the final report must consume.
    """
    value = dict(plan_or_graph or {})
    plan = dict(value.get("plan") or {}) if "plan" in value else value
    for task in reversed(list(plan.get("tasks") or [])):
        if str(task.get("bucket") or "") != "verify":
            continue
        for ref in reversed(list(task.get("produces") or [])):
            if str(ref.get("kind") or "") == "synthesis" and str(ref.get("id") or ""):
                return [f"synthesis:{ref['id']}"]
    return []


def _report_source_coverage(report: dict[str, Any]) -> tuple[set[str], set[str]]:
    """Return the frozen source universe and the sources the report actually declares.

    A report only covers evidence that was both present in its immutable graph snapshot and
    explicitly named by a section.  Historical sections without ``source_study_ids`` may use their
    snapshot-valid citations as the compatibility source, matching the visible-lineage contract.
    """
    snapshot = dict(report.get("graph_snapshot") or {})
    known = {str(value) for value in (snapshot.get("build_order") or []) if str(value)}
    known.update(str(node.get("study_id") or "") for node in (snapshot.get("nodes") or [])
                 if str(node.get("study_id") or ""))
    declared: set[str] = set()
    for section in report.get("sections") or []:
        sources = {str(value) for value in (section.get("source_study_ids") or []) if str(value)}
        if sources:
            declared.update(sources & known)
            continue
        declared.update(
            str(citation.get("study_id") or "")
            for citation in (section.get("citations") or [])
            if isinstance(citation, dict)
            and str(citation.get("study_id") or "") in known
        )
    return known, declared


def _report_state(report: dict[str, Any], required_source_ids: set[str] | None = None) -> dict[str, Any]:
    sections = list(report.get("sections") or [])
    lead_missing = not bool(str(report.get("lead") or "").strip())
    authored = [
        str(section.get("id") or "")
        for section in sections
        if str(section.get("markdown") or "").strip()
    ]
    incomplete = [
        str(section.get("id") or "")
        for section in sections
        if not str(section.get("markdown") or "").strip()
    ]
    content_complete = not lead_missing and bool(sections) and not incomplete
    required = set(required_source_ids or ())
    known, declared = _report_source_coverage(report)
    source_coverage_missing = sorted(required - (known & declared))
    complete = content_complete and not source_coverage_missing
    return {
        "report_id": str(report.get("id") or ""),
        "status": "done" if complete else "in_progress",
        "complete": complete,
        "section_count": len(sections),
        "authored_section_count": len(authored),
        "authored_section_ids": authored,
        "incomplete_section_ids": incomplete,
        "body_empty": not authored,
        "lead_missing": lead_missing,
        "content_complete": content_complete,
        "required_source_ids": sorted(required),
        "source_coverage_missing": source_coverage_missing,
    }


def report_handoff_state(
    reports: dict[str, Any] | Iterable[dict[str, Any]] | None,
    *,
    required_source_ids: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Return one shared, content-derived project report hand-off state.

    ``Store.list_reports`` is newest-first; callers passing another iterable
    should preserve the order they want exposed as ``latest_report_id``.  Any
    fully-authored report satisfies the durable hand-off unless ``required_source_ids`` names a
    current terminal source it does not cover. Unfinished or stale additional drafts remain listed
    for health/repair surfaces.
    """
    if reports is None:
        rows: list[dict[str, Any]] = []
    elif isinstance(reports, dict):
        rows = [reports]
    else:
        rows = list(reports)
    required = {str(value) for value in (required_source_ids or []) if str(value)}
    states = [_report_state(report, required) for report in rows]
    completed = [state for state in states if state["complete"]]
    incomplete = [state for state in states if not state["complete"]]
    stale = [state for state in states
             if state["content_complete"] and state["source_coverage_missing"]]
    latest = states[0] if states else None
    latest_stale = bool(
        latest
        and latest.get("content_complete")
        and latest.get("source_coverage_missing")
    )
    return {
        "exists": bool(states),
        "complete": bool(completed),
        "handed_off": bool(completed),
        "latest_report_id": str((latest or {}).get("report_id") or ""),
        "latest_complete": bool((latest or {}).get("complete")),
        "lead_missing": bool((latest or {}).get("lead_missing")) if latest else False,
        "completed_report_ids": [state["report_id"] for state in completed],
        "incomplete_report_ids": [state["report_id"] for state in incomplete],
        "stale_report_ids": [state["report_id"] for state in stale],
        "latest_stale": latest_stale,
        "required_source_ids": sorted(required),
        "reports": states,
    }


def report_provenance_state(report: dict[str, Any]) -> dict[str, Any]:
    """Validate a report's section-level provenance without a generic claim envelope.

    Report prose has its own contract: every authored section must cite one of
    that section's frozen source studies, while additional cross-phase citations
    may reference any study in the report's immutable graph snapshot.  This is
    narrower and more truthful than requiring the council/synthesis
    ``claim_posture`` envelope on the report container, while still refusing to
    treat uncited or foreign-source prose as verified.
    """
    snapshot = dict(report.get("graph_snapshot") or {})
    known = {str(value) for value in (snapshot.get("build_order") or []) if str(value)}
    known.update(str(node.get("study_id") or "") for node in (snapshot.get("nodes") or [])
                 if str(node.get("study_id") or ""))
    gaps: list[dict[str, str]] = []
    invalid: list[dict[str, str]] = []
    authored = 0
    for section in report.get("sections") or []:
        if not str(section.get("markdown") or "").strip():
            continue
        authored += 1
        section_id = str(section.get("id") or "")
        heading = str(section.get("heading") or section_id or "section")
        sources = {str(value) for value in (section.get("source_study_ids") or []) if str(value)}
        citations = [row for row in (section.get("citations") or []) if isinstance(row, dict)]
        anchored = 0
        for citation in citations:
            study_id = str(citation.get("study_id") or "")
            # Current outlines declare exact per-section sources. Legacy
            # structural/preflight sections may have an empty list; only for
            # those rows, fall back to the immutable graph snapshot rather
            # than making otherwise real citations impossible to verify.
            if not study_id or study_id not in known:
                invalid.append({"section_id": section_id, "heading": heading,
                                "study_id": study_id})
                continue
            # The section list is its mandatory phase anchor, not a ban on
            # cross-phase synthesis. Every other citation still has to remain
            # inside the same frozen report graph.
            if not sources or study_id in sources:
                anchored += 1
        if not anchored:
            gaps.append({"section_id": section_id, "heading": heading,
                         "reason": "no_valid_source_citation"})
    if invalid:
        gaps.append({"section_id": "", "heading": "",
                     "reason": "invalid_source_citations"})
    complete = report_handoff_state(report)["complete"]
    return {
        "verified": bool(complete and authored and not gaps),
        "authored_section_count": authored,
        "gaps": gaps,
        "invalid_citations": invalid,
    }
