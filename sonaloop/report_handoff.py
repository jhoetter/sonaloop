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


def _report_state(report: dict[str, Any]) -> dict[str, Any]:
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
    complete = not lead_missing and bool(sections) and not incomplete
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
    }


def report_handoff_state(
    reports: dict[str, Any] | Iterable[dict[str, Any]] | None,
) -> dict[str, Any]:
    """Return one shared, content-derived project report hand-off state.

    ``Store.list_reports`` is newest-first; callers passing another iterable
    should preserve the order they want exposed as ``latest_report_id``.  Any
    fully-authored report satisfies the durable hand-off, while unfinished
    additional drafts remain listed for health/repair surfaces.
    """
    if reports is None:
        rows: list[dict[str, Any]] = []
    elif isinstance(reports, dict):
        rows = [reports]
    else:
        rows = list(reports)
    states = [_report_state(report) for report in rows]
    completed = [state for state in states if state["complete"]]
    incomplete = [state for state in states if not state["complete"]]
    latest = states[0] if states else None
    return {
        "exists": bool(states),
        "complete": bool(completed),
        "handed_off": bool(completed),
        "latest_report_id": str((latest or {}).get("report_id") or ""),
        "latest_complete": bool((latest or {}).get("complete")),
        "lead_missing": bool((latest or {}).get("lead_missing")) if latest else False,
        "completed_report_ids": [state["report_id"] for state in completed],
        "incomplete_report_ids": [state["report_id"] for state in incomplete],
        "reports": states,
    }


def report_provenance_state(report: dict[str, Any]) -> dict[str, Any]:
    """Validate a report's section-level provenance without a generic claim envelope.

    Report prose has its own contract: every authored section must cite one of
    that section's frozen source studies.  This is narrower and more truthful
    than requiring the council/synthesis ``claim_posture`` envelope on the
    report container, while still refusing to treat uncited prose as verified.
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
        valid = 0
        for citation in citations:
            study_id = str(citation.get("study_id") or "")
            # Current outlines declare exact per-section sources. Legacy
            # structural/preflight sections may have an empty list; only for
            # those rows, fall back to the immutable graph snapshot rather
            # than making otherwise real citations impossible to verify.
            declared = not sources or study_id in sources
            if study_id and declared and study_id in known:
                valid += 1
            else:
                invalid.append({"section_id": section_id, "heading": heading,
                                "study_id": study_id})
        if not valid:
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
