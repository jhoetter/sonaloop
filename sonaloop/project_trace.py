"""Project trace edges: provenance-backed relationships between project artifacts.

The web outline and the experimental graph view both need the same answer to:
"what did this node consume, and where did it flow next?"  This module is the
small shared substrate for those edges; rendering code should not invent its own
project-story relationships.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse


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
    "refines": TraceEdgeType("refines", "authored", "study.edge.refines", "refines"),
    "informs": TraceEdgeType("informs", "system", "plan.verify_spine", "informs"),
    "task_consumes": TraceEdgeType("task_consumes", "system", "plan.task.consumes", "consumes"),
    "task_produces": TraceEdgeType("task_produces", "system", "plan.task.produces", "produces"),
    "judgment_evidence": TraceEdgeType(
        "judgment_evidence", "authored", "plan.judgment.evidence_refs", "used by gate"),
    "follow_up": TraceEdgeType("follow_up", "authored", "*.open_questions", "follow-up"),
    "parked": TraceEdgeType("parked", "authored", "*.parked_refs", "parked"),
}


def trace_edge(from_study: str, to_study: str, edge_type: str, **overrides: Any) -> dict[str, Any]:
    """Build a visible trace edge from the registry.

    Rendering code should not mint ad-hoc edge vocabulary. When a relation needs a new
    type, it has to be declared in TRACE_EDGE_TYPES first so provenance and labels stay
    inspectable.
    """
    meta = TRACE_EDGE_TYPES.get(edge_type)
    if not meta:
        raise ValueError(f"Unknown project trace edge type: {edge_type}")
    edge = {"from_study": from_study, "to_study": to_study, "type": meta.type,
            "label": meta.label, "provenance": meta.provenance, "source": meta.source}
    edge.update({k: v for k, v in overrides.items() if v is not None and v != ""})
    return edge


def _node_id(kind: str, rid: str) -> str:
    return f"{kind}:{rid}"


def _ref_node_id(ref: dict[str, Any], known: set[str]) -> str:
    kind, rid = str(ref.get("kind") or ""), str(ref.get("id") or "")
    if not kind or not rid:
        return ""
    cands = [_node_id(kind, rid), rid]
    if kind == "report":
        cands.append(_node_id("synthesis", rid))
    if kind == "artifact":
        cands.extend((_node_id("prototype", rid), _node_id("url_artifact", rid), _node_id("asset", rid)))
    return next((c for c in cands if c in known), "")


def _host(url: str) -> str:
    try:
        return urlparse(url).netloc.lower().removeprefix("www.")
    except Exception:
        return ""


def _tokens(*values: object) -> set[str]:
    import re
    out: set[str] = set()
    for value in values:
        out.update(t for t in re.findall(r"[a-z0-9]+", str(value or "").lower()) if len(t) > 2)
    return out


def collect_project_trace_edges(graph: dict[str, Any], nodes: list[dict[str, Any]], *,
                                sessions: dict[str, dict[str, Any]] | None = None,
                                decisions: list[dict[str, Any]] | None = None,
                                hypotheses: list[dict[str, Any]] | None = None,
                                surveys: list[dict[str, Any]] | None = None,
                                assets: list[dict[str, Any]] | None = None,
                                base_edges: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """Return all visible project trace edges for the already assembled project nodes.

    This is the single edge collection service used by the outline/detail graph adapters. It
    accepts project records because node construction is still presentation-specific, but every
    emitted edge goes through `trace_edge`, so provenance/type vocabulary stays centralized.
    """
    seen = {str(n.get("study_id")) for n in nodes if n.get("study_id")}
    edges = list(base_edges or [])

    def edge_key(value: Any) -> Any:
        """Hash the JSON-shaped edge without changing dict-equality semantics.

        Trace metadata is JSON-shaped, but a few adapters add lists/dicts.  A
        recursive immutable key keeps duplicate checks O(1) without restricting
        those extensions to scalar values.
        """
        if isinstance(value, dict):
            return ("dict", tuple(sorted((str(k), edge_key(v)) for k, v in value.items())))
        if isinstance(value, list):
            return ("list", tuple(edge_key(v) for v in value))
        if isinstance(value, tuple):
            return ("tuple", tuple(edge_key(v) for v in value))
        if isinstance(value, set):
            return ("set", tuple(sorted((edge_key(v) for v in value), key=repr)))
        try:
            hash(value)
        except TypeError:
            return ("repr", repr(value))
        return ("scalar", value)

    edge_keys = {edge_key(row) for row in edges}
    incident_nodes = {
        str(node_id)
        for row in edges
        for node_id in (row.get("from_study"), row.get("to_study"))
        if node_id
    }

    def edge(a: str, b: str, typ: str, label: str = "",
             extra: dict[str, Any] | None = None) -> None:
        if a and b and a != b and a in seen and b in seen:
            extra_clean = {k: v for k, v in (extra or {}).items()
                           if k not in {"from_study", "to_study", "type", "label"}}
            e = trace_edge(a, b, typ, label=label, **extra_clean)
            key = edge_key(e)
            if key not in edge_keys:
                edges.append(e)
                edge_keys.add(key)
                incident_nodes.update((a, b))

    for p in graph.get("prototypes") or []:
        pid = _node_id("prototype", p.get("id", ""))
        for n in nodes:
            if p.get("id") in (n.get("prototype_ids") or []):
                edge(str(n.get("study_id")), pid, "derived_from", "builds",
                     {"source": "prototype.prototype_ids"})

    for s in surveys or []:
        sid = _node_id("survey", s.get("id", ""))
        for ref in s.get("derived_from") or []:
            edge(_ref_node_id(ref, seen), sid, "derived_from", "derived from")

    for h in hypotheses or []:
        hid = _node_id("hypothesis", h.get("id", ""))
        for ref in h.get("derived_from") or []:
            edge(_ref_node_id(ref, seen), hid, "derived_from", "derived from")

    for d in decisions or []:
        did = _node_id("decision", d.get("id", ""))
        for ref in d.get("based_on") or []:
            edge(_ref_node_id(ref, seen), did, "based_on", "based on")

    # A project report is a terminal hand-off over its section-level, frozen provenance.
    # It is attached to the graph outside the plan's convergence nodes, so derive this
    # visible edge from the authored report sources rather than guessing from chronology.
    for report in graph.get("reports") or []:
        rid = _node_id("report", report.get("id", ""))
        for ref in report.get("source_study_ids") or []:
            edge(normalize_trace_ref(ref, seen), rid, "based_on", "source",
                 {"source": "report.sections.source_study_ids"})
        for ref in report.get("legacy_citation_study_ids") or []:
            edge(normalize_trace_ref(ref, seen), rid, "based_on", "source",
                 {"source": "report.sections.citations"})

    artifact_nodes: dict[str, str] = {}
    artifact_hosts: dict[str, str] = {}
    for a in graph.get("artifacts") or []:
        aid = _node_id("url_artifact", a.get("id", ""))
        if aid in seen:
            artifact_nodes[a.get("id", "")] = aid
            artifact_hosts[aid] = _host(a.get("url", ""))

    asset_token_map: dict[str, set[str]] = {}
    for a in assets or []:
        aid = _node_id("asset", a.get("id", ""))
        if aid in seen:
            asset_token_map[aid] = _tokens(a.get("title"), a.get("filename"),
                                           a.get("notes"), a.get("source"))

    proto_keys = {p.get("id"): _node_id("prototype", p["id"]) for p in graph.get("prototypes") or []}
    proto_keys.update({p.get("slug"): _node_id("prototype", p["id"])
                       for p in graph.get("prototypes") or [] if p.get("slug")})
    for grp in (sessions or {}).values():
        subj = grp.get("subject") or {}
        subj_node = proto_keys.get(subj.get("id")) if subj.get("kind") == "prototype" else ""
        for s in grp.get("sessions") or []:
            sid = _node_id("session", s.get("id", ""))
            edge(subj_node, sid, "tested_in", "tested in")
            if subj.get("kind") == "live_url":
                shost = _host(subj.get("url", ""))
                for anid, ahost in artifact_hosts.items():
                    if shost and ahost and shost == ahost:
                        edge(anid, sid, "tested_in", "tested in")
            elif subj.get("kind") == "flow":
                session_tokens = _tokens(subj.get("label"), subj.get("id"))
                for step in s.get("steps") or []:
                    action = step.get("action") or {}
                    state = step.get("state") or {}
                    session_tokens |= _tokens(action.get("target"), action.get("detail"),
                                              state.get("screen"), state.get("title"), step.get("monologue"))
                for aid, toks in asset_token_map.items():
                    if session_tokens & toks:
                        edge(aid, sid, "uses_material", "screen used", {"source": "session.steps"})

    for te in plan_judgment_edges(graph.get("plan"), seen):
        edge(te["from_study"], te["to_study"], te["type"], te.get("label", ""), te)
    for te in plan_task_flow_edges(graph.get("plan"), seen):
        edge(te["from_study"], te["to_study"], te["type"], te.get("label", ""), te)

    parked_nodes = {
        normalize_trace_ref(ref, seen)
        for rec in (graph.get("plan") or {}).get("parked_refs") or []
        for ref in rec.get("refs") or []
    }
    parked_nodes.discard("")

    council_ids = [n["study_id"] for n in sorted(nodes, key=lambda n: n.get("created_at", ""))
                   if str(n.get("study_id", "")).startswith("council:")]
    first_council = council_ids[0] if council_ids else ""
    if first_council:
        for aid in artifact_nodes.values():
            if aid in parked_nodes:
                continue
            if aid not in incident_nodes:
                edge(aid, first_council, "uses_material", "material",
                     {"provenance": "inferred", "source": "outline.material_fallback"})

    study_kinds = set(("coun" + "cil", "survey", "hypothesis", "session", "report", "decision"))
    first_study = next((n["study_id"] for n in sorted(nodes, key=lambda n: n.get("created_at", ""))
                        if str(n.get("study_id", "")).split(":", 1)[0] in study_kinds), "")
    if first_study:
        for o in graph.get("open_questions") or []:
            oid = _node_id("open_question", o["id"])
            if oid in parked_nodes:
                continue
            if oid not in incident_nodes:
                edge(oid, first_study, "derived_from", "frames",
                     {"provenance": "inferred", "source": "outline.open_question_fallback"})

    return edges


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
                out.append(trace_edge(src, dst, meta.type, task_id=task["id"],
                                      gate_tag=j.get("gate_tag", "")))
    return out


def plan_task_flow_edges(plan: dict[str, Any] | None, known_nodes: set[str]) -> list[dict[str, Any]]:
    """Expose plan task consumption as evidence-to-evidence trace edges.

    The plan DAG often routes work through frame tasks, which are not visible outline nodes.
    A prototype produced by an act task that consumes `frame__develop` should still show the
    upstream define synthesis as its input. Resolve those frame hops recursively so generated
    artifacts do not look like they appeared without prior evidence.
    """
    if not plan:
        return []
    tasks = {str(t.get("id")): t for t in plan.get("tasks") or []}
    meta = TRACE_EDGE_TYPES["task_consumes"]

    def direct_outputs(task: dict[str, Any]) -> list[str]:
        out: list[str] = []
        for ref in task.get("produces") or []:
            if ref.get("kind") == "frame":
                continue
            nid = normalize_trace_ref(ref, known_nodes)
            if nid and nid not in out:
                out.append(nid)
        return out

    memo: dict[str, list[str]] = {}

    def visible_outputs(task_id: str, visiting: set[str] | None = None) -> list[str]:
        if task_id in memo:
            return memo[task_id]
        visiting = visiting or set()
        if task_id in visiting:
            return []
        task = tasks.get(task_id)
        if not task:
            return []
        direct = direct_outputs(task)
        if direct:
            memo[task_id] = direct
            return direct
        visiting = {*visiting, task_id}
        inherited: list[str] = []
        for consumed_id in task.get("consumes") or []:
            for nid in visible_outputs(str(consumed_id), visiting):
                if nid not in inherited:
                    inherited.append(nid)
        memo[task_id] = inherited
        return inherited

    out: list[dict[str, Any]] = []
    seen_pairs: set[tuple[str, str, str]] = set()
    for task_id, task in tasks.items():
        targets = direct_outputs(task)
        if not targets:
            continue
        sources: list[str] = []
        for consumed_id in task.get("consumes") or []:
            for nid in visible_outputs(str(consumed_id)):
                if nid not in sources:
                    sources.append(nid)
        for src in sources:
            for dst in targets:
                key = (src, dst, meta.type)
                if src == dst or key in seen_pairs:
                    continue
                seen_pairs.add(key)
                out.append(trace_edge(src, dst, meta.type, label="input", task_id=task_id))
    return out


START_KINDS = {"note", "open_question", "url_artifact", "asset"}
TERMINAL_KINDS = {"decision", "report"}


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


def _parked_plan_nodes(plan: dict[str, Any] | None, known_nodes: set[str]) -> set[str]:
    out: set[str] = set()
    for rec in (plan or {}).get("parked_refs") or []:
        for ref in rec.get("refs") or []:
            nid = normalize_trace_ref(ref, known_nodes)
            if nid:
                out.add(nid)
    return out


def trace_node_health(nodes: list[dict[str, Any]], edges: list[dict[str, Any]],
                      plan: dict[str, Any] | None = None) -> dict[str, str]:
    """Deterministic lifecycle state for visible project nodes.

    A node without outputs is acceptable while the plan is still open; after the
    plan is complete, middle/source evidence must either be consumed, terminal
    or explicitly parked. This is the substrate for quiet UI warnings and
    assess_project gaps.
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
    parked_nodes = _parked_plan_nodes(plan, known)
    complete = _plan_complete(plan)
    out: dict[str, str] = {}
    for n in nodes:
        nid = str(n.get("study_id") or "")
        if not nid:
            continue
        kind = _kind_of(n)
        if outgoing.get(nid, 0):
            out[nid] = "source" if incoming.get(nid, 0) == 0 and kind in START_KINDS else "consumed"
        elif nid in parked_nodes:
            out[nid] = "parked"
        elif kind in TERMINAL_KINDS or nid in terminal_nodes:
            out[nid] = "terminal"
        elif complete:
            out[nid] = "orphaned"
        else:
            out[nid] = "active"
    return out
