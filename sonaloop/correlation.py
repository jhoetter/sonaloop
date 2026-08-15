"""Stable, content-free workflow correlation for a research job and its outputs.

Transport traces answer "what happened in this HTTP/MCP request?".  A workflow
trace answers the longer-lived product question: "which calls, run, sessions,
reports and exports belong to this research job?"  It is derived from the
project id, so retries and legacy rows converge without a write-on-read migration.
"""
from __future__ import annotations

import hashlib
import re
from typing import Any, Mapping


WORKFLOW_TRACE_SCHEMA = "sonaloop.workflow_trace.v1"
_TRACE_RE = re.compile(r"^sltrace_[a-f0-9]{24}$")


def validate_workflow_trace_id(value: Any) -> str:
    """Return one normalized workflow trace id or reject malformed input."""
    trace_id = str(value or "").strip().lower()
    if not _TRACE_RE.fullmatch(trace_id):
        raise ValueError("workflow_trace_id must match sltrace_ followed by 24 lowercase hex chars")
    return trace_id


def workflow_trace_id(project: str | Mapping[str, Any]) -> str:
    """Return the canonical stable workflow trace id for one project."""
    if isinstance(project, Mapping):
        existing = str(project.get("workflow_trace_id") or "").strip().lower()
        project_id = str(project.get("id") or project.get("project_id") or "").strip()
        if not project_id and _TRACE_RE.fullmatch(existing):
            return existing
    else:
        project_id = str(project or "").strip()
    if not project_id:
        return ""
    digest = hashlib.sha256(
        f"sonaloop-workflow-trace:v1:{project_id}".encode("utf-8")
    ).hexdigest()[:24]
    return f"sltrace_{digest}"


def stamp_workflow_trace(record: dict[str, Any], project: str | Mapping[str, Any]) -> str:
    """Stamp a mutable record and return the trace id; no-op without a project."""
    trace_id = workflow_trace_id(project)
    if trace_id:
        record["workflow_trace_id"] = trace_id
    return trace_id


def workflow_trace_from_payload(value: Any, *, max_depth: int = 4) -> str:
    """Find or derive the first workflow trace in one bounded result envelope."""
    if max_depth < 0:
        return ""
    if isinstance(value, Mapping):
        trace_id = str(value.get("workflow_trace_id") or "").strip().lower()
        if _TRACE_RE.fullmatch(trace_id):
            return trace_id
        project_id = str(value.get("project_id") or value.get("job_id") or "").strip()
        if project_id:
            return workflow_trace_id(project_id)
        for child in value.values():
            found = workflow_trace_from_payload(child, max_depth=max_depth - 1)
            if found:
                return found
    elif isinstance(value, (list, tuple)):
        for child in value[:50]:
            found = workflow_trace_from_payload(child, max_depth=max_depth - 1)
            if found:
                return found
    return ""


def workflow_trace_ref(
    project: str | Mapping[str, Any], *, run_id: str = "", operation_id: str = "",
) -> dict[str, Any]:
    """Small provider-neutral correlation object for MCP/support surfaces."""
    trace_id = workflow_trace_id(project)
    project_id = (
        str(project.get("id") or project.get("project_id") or "")
        if isinstance(project, Mapping) else str(project or "")
    )
    return {
        "schema": WORKFLOW_TRACE_SCHEMA,
        "workflow_trace_id": trace_id,
        "project_id": project_id,
        **({"run_id": str(run_id)} if run_id else {}),
        **({"operation_id": str(operation_id)} if operation_id else {}),
    }
