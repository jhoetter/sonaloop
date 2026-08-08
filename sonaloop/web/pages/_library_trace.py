"""Project-graph trace projection for the cross-project Library."""

from __future__ import annotations

from ... import services
from ...storage import Store
from ...project_trace import trace_node_health
from .._graph_outline_sessions import outline_session_groups
from .._project_graph_view import augment_project_graph


def entry_trace_keys(entry: dict) -> set[str]:
    record = entry.get("rec") or {}
    kind = str(entry.get("kind") or "")
    record_id = str(record.get("id") or "")
    if not kind or not record_id:
        return set()
    keys = {record_id, f"{kind}:{record_id}"}
    if kind == ("synth" + "esis"):
        keys.add(f"report:{record_id}")
    if kind == "url_artifact":
        keys.add(f"artifact:{record_id}")
    return keys


def library_trace_lookup(store: Store, project_ids: set[str]) -> dict[str, dict[str, str]]:
    """Return project-outline trace states keyed for flat Library rows."""
    if not project_ids:
        return {}
    out: dict[str, dict[str, str]] = {}
    for project_id in project_ids:
        try:
            graph = services.get_project_graph(project_id, store=store)
        except KeyError:
            # Keep the global Library browsable when a historical row references
            # a project that has since been deleted.
            continue
        prototype_ids = {p.get("id") for p in graph.get("prototypes") or []}
        prototype_sessions = [
            session for session in store.list_prototype_sessions()
            if session.get("prototype_id") in prototype_ids
        ]
        sessions = outline_session_groups(
            services.list_usability_sessions(project_id=project_id, store=store),
            store,
            prototype_sessions=prototype_sessions,
        )
        full_graph = augment_project_graph(
            graph,
            sessions=sessions,
            decisions=services.list_decisions(project_id, store=store),
            hypotheses=services.list_hypotheses(project_id, store=store),
            surveys=services.list_surveys(project_id=project_id, store=store),
            assets=services.list_assets(project_id, store=store),
        )
        health = trace_node_health(full_graph["nodes"], full_graph["edges"], graph.get("plan"))
        by_key: dict[str, str] = {}
        for node in full_graph["nodes"]:
            study_id = str(node.get("study_id") or "")
            if not study_id:
                continue
            state = health.get(study_id, "")
            if not state:
                continue
            by_key[study_id] = state
            kind, record_id = study_id.split(":", 1) if ":" in study_id else ("", study_id)
            by_key.setdefault(record_id, state)
            if kind == "report":
                by_key.setdefault(f"synthesis:{record_id}", state)
            if kind == "url_artifact":
                by_key.setdefault(f"artifact:{record_id}", state)
        out[project_id] = by_key
    return out


def annotate_library_trace(entries: list[dict], store: Store) -> list[dict]:
    lookup = library_trace_lookup(
        store,
        {entry["project_id"] for entry in entries if entry.get("project_id")},
    )
    annotated = []
    for entry in entries:
        project_trace = lookup.get(entry.get("project_id", ""), {})
        state = next(
            (project_trace.get(key) for key in entry_trace_keys(entry) if project_trace.get(key)),
            "",
        )
        if not state:
            annotated.append(entry)
            continue
        record = {**(entry.get("rec") or {}), "trace_health": state}
        annotated.append({**entry, "rec": record, "trace_health": state})
    return annotated
