"""Project trace edges: provenance-backed relationships between project artifacts.

The web outline and the experimental graph view both need the same answer to:
"what did this node consume, and where did it flow next?"  This module is the
small shared substrate for those edges; rendering code should not invent its own
project-story relationships.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TraceEdgeType:
    type: str
    provenance: str
    source: str
    label: str


TRACE_EDGE_TYPES: dict[str, TraceEdgeType] = {
    "derived_from": TraceEdgeType("derived_from", "authored", "*.derived_from", "derived from"),
    "based_on": TraceEdgeType("based_on", "authored", "*.based_on", "based on"),
    "tested_in": TraceEdgeType("tested_in", "system", "session.subject", "tested in"),
    "uses_material": TraceEdgeType("uses_material", "authored", "*.refs", "uses material"),
    "task_consumes": TraceEdgeType("task_consumes", "system", "plan.task.consumes", "consumes"),
    "task_produces": TraceEdgeType("task_produces", "system", "plan.task.produces", "produces"),
    "judgment_evidence": TraceEdgeType(
        "judgment_evidence", "authored", "plan.judgment.evidence_refs", "used by gate"),
    "follow_up": TraceEdgeType("follow_up", "authored", "*.open_questions", "follow-up"),
    "parked": TraceEdgeType("parked", "authored", "*.parked_refs", "parked"),
}


def _node_id(kind: str, rid: str) -> str:
    return f"{kind}:{rid}"


def normalize_trace_ref(ref: Any, known_nodes: set[str]) -> str:
    """Resolve a loose project ref into the node id used by the visible graph.

    Plan judgments historically store refs as either `kind:id` strings or bare ids.
    The outline likewise has mixed ids for old rows (e.g. prototype rows use the raw
    prototype id, while graph nodes use `kind:id`).  Resolve against known nodes
    instead of trusting one spelling.
    """
    if isinstance(ref, dict):
        kind, rid = str(ref.get("kind") or ""), str(ref.get("id") or "")
    else:
        raw = str(ref or "").strip()
        kind, rid = raw.split(":", 1) if ":" in raw else ("", raw)
    if not rid:
        return ""
    cands: list[str] = []
    if kind:
        cands.append(_node_id(kind, rid))
        if kind == "artifact":
            cands.extend((_node_id("prototype", rid), _node_id("url_artifact", rid),
                          _node_id("asset", rid), rid))
        elif kind == "report":
            cands.append(_node_id("synthesis", rid))
        elif kind == "session":
            cands.append(_node_id("session", rid))
        cands.append(rid)
    else:
        cands.extend((rid, _node_id("council", rid), _node_id("synthesis", rid),
                      _node_id("survey", rid), _node_id("prototype", rid),
                      _node_id("session", rid), _node_id("hypothesis", rid),
                      _node_id("decision", rid), _node_id("asset", rid),
                      _node_id("url_artifact", rid)))
    return next((c for c in cands if c in known_nodes), "")


def plan_judgment_edges(plan: dict[str, Any] | None, known_nodes: set[str]) -> list[dict[str, Any]]:
    """Expose gate evidence citations as graph edges.

    A verify task's synthesis is the convergence artifact. If the gate judgment
    cites a survey/prototype/session/etc., that evidence should visibly feed the
    convergence artifact instead of appearing unused in the project outline.
    """
    if not plan:
        return []
    tasks = {str(t.get("id")): t for t in plan.get("tasks") or []}
    meta = TRACE_EDGE_TYPES["judgment_evidence"]
    out: list[dict[str, Any]] = []
    for j in plan.get("judgments") or []:
        task = tasks.get(str(j.get("task_id") or ""))
        if not task:
            continue
        targets = [normalize_trace_ref(r, known_nodes) for r in task.get("produces") or []]
        targets = [t for t in targets if t and not t.startswith("frame:")]
        synth_targets = [t for t in targets if t.startswith("synthesis:")]
        targets = synth_targets or targets
        if not targets:
            continue
        for raw in j.get("evidence_refs") or []:
            src = normalize_trace_ref(raw, known_nodes)
            if not src:
                continue
            for dst in targets:
                if src == dst:
                    continue
                out.append({"from_study": src, "to_study": dst, "type": meta.type,
                            "label": meta.label, "provenance": meta.provenance,
                            "source": meta.source, "task_id": task["id"],
                            "gate_tag": j.get("gate_tag", "")})
    return out


START_KINDS = {"note", "open_question", "url_artifact", "asset"}
TERMINAL_KINDS = {"decision"}


def _kind_of(node: dict[str, Any]) -> str:
    sid = str(node.get("study_id") or "")
    return str(node.get("kind") or (sid.split(":", 1)[0] if ":" in sid else ""))


def _plan_complete(plan: dict[str, Any] | None) -> bool:
    tasks = (plan or {}).get("tasks") or []
    return bool(tasks) and all(t.get("status") == "done" for t in tasks)


def _terminal_plan_nodes(plan: dict[str, Any] | None, known_nodes: set[str]) -> set[str]:
    """Synthesis outputs of terminal verify tasks are legitimate endpoints."""
    if not plan:
        return set()
    tasks = {str(t.get("id")): t for t in plan.get("tasks") or []}
    consumed = {c for t in tasks.values() for c in (t.get("consumes") or [])}
    out: set[str] = set()
    for tid, task in tasks.items():
        if task.get("bucket") != "verify" or tid in consumed:
            continue
        for ref in task.get("produces") or []:
            nid = normalize_trace_ref(ref, known_nodes)
            if nid:
                out.add(nid)
    return out


def trace_node_health(nodes: list[dict[str, Any]], edges: list[dict[str, Any]],
                      plan: dict[str, Any] | None = None) -> dict[str, str]:
    """Deterministic lifecycle state for visible project nodes.

    A node without outputs is acceptable while the plan is still open; after the
    plan is complete, middle/source evidence must either be consumed, terminal
    or explicitly parked (parked edges land in a later slice). This is the
    substrate for quiet UI warnings and assess_project gaps.
    """
    known = {str(n.get("study_id")) for n in nodes if n.get("study_id")}
    incoming: dict[str, int] = {nid: 0 for nid in known}
    outgoing: dict[str, int] = {nid: 0 for nid in known}
    for e in edges:
        a, b = str(e.get("from_study") or ""), str(e.get("to_study") or "")
        if a in known and b in known:
            outgoing[a] = outgoing.get(a, 0) + 1
            incoming[b] = incoming.get(b, 0) + 1
    terminal_nodes = _terminal_plan_nodes(plan, known)
    complete = _plan_complete(plan)
    out: dict[str, str] = {}
    for n in nodes:
        nid = str(n.get("study_id") or "")
        if not nid:
            continue
        kind = _kind_of(n)
        if outgoing.get(nid, 0):
            out[nid] = "source" if incoming.get(nid, 0) == 0 and kind in START_KINDS else "consumed"
        elif kind in TERMINAL_KINDS or nid in terminal_nodes:
            out[nid] = "terminal"
        elif complete:
            out[nid] = "orphaned"
        else:
            out[nid] = "active"
    return out
