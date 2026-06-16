"""Experimental full project graph adapter.

This module is intentionally removable: /projects still owns the canonical list view, while this
adapter only translates the same project primitives into graph nodes so we can judge whether a
spatial view is useful enough to keep.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any
from urllib.parse import urlparse

from ..project_trace import plan_judgment_edges
from ._i18n import t
from ._primitive_taxonomy import primitive_color, subtype_label, subtype_value


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


def _phase(graph: dict, created_at: str) -> str:
    steps = ((graph.get("methodology_state") or {}).get("steps") or [])
    if not steps:
        return ""
    nodes = sorted((n for n in graph.get("nodes") or [] if n.get("phase")),
                   key=lambda n: n.get("created_at", ""))
    current = steps[0].get("key", "")
    for n in nodes:
        if n.get("created_at", "") <= created_at:
            current = n.get("phase") or current
    return current


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


def _add(nodes: list[dict], seen: set[str], *, kind: str, rid: str, title: str,
         created_at: str = "", href: str = "", subtype: str = "", phase: str = "",
         extra: dict | None = None) -> str:
    nid = _node_id(kind, rid)
    if not rid or nid in seen:
        return nid
    seen.add(nid)
    label = {
        "url_artifact": t("reference_kind"),
        "asset": t("asset_kind"),
        "open_question": t("open_question_kind"),
        "hypothesis": t("hypothesis_kind"),
        "decision": t("decision_kind"),
        "survey": t("survey_kind"),
        "prototype": t("prototype_kind"),
        "session": t("session_kind"),
        "report": t("synthesis_kind"),
    }.get(kind, kind)
    node = {"study_id": nid, "kind": kind, "kind_label": label, "title": title or rid,
            "created_at": created_at, "phase": phase, "href": href,
            "color": primitive_color(kind), "theme_tags": [subtype] if subtype else []}
    if subtype:
        node["format_label"] = subtype_label(subtype)
    if extra:
        node.update(extra)
    nodes.append(node)
    return nid


def augment_project_graph(graph: dict, *, sessions: dict[str, dict], decisions: list[dict],
                          hypotheses: list[dict], surveys: list[dict], assets: list[dict]) -> dict:
    """Return a project graph whose nodes/edges cover every primitive visible in the outline."""
    out = deepcopy(graph)
    base_nodes = out.get("nodes") or []
    nodes = list(base_nodes)
    seen = {str(n.get("study_id")) for n in nodes if n.get("study_id")}
    edges = list(out.get("edges") or [])

    def edge(a: str, b: str, typ: str = "informs", label: str = "",
             extra: dict[str, Any] | None = None) -> None:
        if a and b and a != b and a in seen and b in seen:
            e = {"from_study": a, "to_study": b, "type": typ}
            if label:
                e["label"] = label
            if extra:
                e.update(extra)
            if e not in edges:
                edges.append(e)

    for n in list(nodes):
        if n.get("kind") and not n.get("color"):
            n["color"] = primitive_color(str(n["kind"]))

    for r in out.get("reports") or []:
        _add(nodes, seen, kind="report", rid=r["id"], title=r.get("title", ""),
             created_at=r.get("created_at", ""), href=f'/syntheses/{r["id"]}',
             phase=_phase(out, r.get("created_at", "")),
             extra={"n_sections": r.get("n_sections", 0)})

    for p in out.get("prototypes") or []:
        pid = _add(nodes, seen, kind="prototype", rid=p["id"], title=p.get("name", ""),
                   created_at=p.get("created_at", ""), href=f'/prototypes/{p.get("slug", p["id"])}',
                   subtype=str(p.get("fidelity") or "midfi"), phase=_phase(out, p.get("created_at", "")))
        for n in nodes:
            if p["id"] in (n.get("prototype_ids") or []):
                edge(str(n.get("study_id")), pid, "informs", "builds")

    artifact_nodes: dict[str, str] = {}
    artifact_hosts: dict[str, str] = {}
    for a in out.get("artifacts") or []:
        aid = _add(nodes, seen, kind="url_artifact", rid=a["id"], title=a.get("title") or a.get("url", ""),
             created_at=a.get("created_at", ""), href=f'/references/{a["id"]}',
             subtype=subtype_value("url_artifact", a), phase=_phase(out, a.get("created_at", "")),
        extra={"url": a.get("url", ""), "variant": a.get("label", "")})
        artifact_nodes[a["id"]] = aid
        artifact_hosts[aid] = _host(a.get("url", ""))

    asset_token_map: dict[str, set[str]] = {}
    for a in assets:
        aid = _add(nodes, seen, kind="asset", rid=a["id"], title=a.get("title") or a.get("filename", ""),
             created_at=a.get("created_at", ""), href=f'/assets/{a["id"]}',
             subtype=subtype_value("asset", a), phase=_phase(out, a.get("created_at", "")),
             extra={"direction": a.get("direction", "in")})
        asset_token_map[aid] = _tokens(a.get("title"), a.get("filename"), a.get("notes"), a.get("source"))

    for o in out.get("open_questions") or []:
        _add(nodes, seen, kind="open_question", rid=o["id"], title=o.get("text", ""),
             created_at=o.get("created_at", ""), href=f'/open-questions/{o["id"]}',
             phase=_phase(out, o.get("created_at", "")), extra={"status": o.get("status", "open")})

    for s in surveys:
        sid = _add(nodes, seen, kind="survey", rid=s["id"], title=s.get("title", ""),
                   created_at=s.get("created_at", ""), href=f'/surveys/{s["id"]}',
                   subtype=subtype_value("survey", s), phase=_phase(out, s.get("created_at", "")),
                   extra={"status": s.get("status", "draft")})
        for ref in s.get("derived_from") or []:
            edge(_ref_node_id(ref, seen), sid, "informs", "derives")

    for h in hypotheses:
        hid = _add(nodes, seen, kind="hypothesis", rid=h["id"], title=h.get("text", ""),
                   created_at=h.get("created_at", ""), href=f'/hypotheses/{h["id"]}',
                   phase=_phase(out, h.get("created_at", "")), extra={"status": h.get("status", "open")})
        for ref in h.get("derived_from") or []:
            edge(_ref_node_id(ref, seen), hid, "informs", "derives")

    for d in decisions:
        did = _add(nodes, seen, kind="decision", rid=d["id"], title=d.get("title", ""),
                   created_at=d.get("created_at", ""), href=f'/decisions/{d["id"]}',
                   phase=_phase(out, d.get("created_at", "")), extra={"status": d.get("status", "proposed")})
        for ref in d.get("based_on") or []:
            edge(_ref_node_id(ref, seen), did, "answers", "based on")

    proto_keys = {p.get("id"): _node_id("prototype", p["id"]) for p in out.get("prototypes") or []}
    proto_keys.update({p.get("slug"): _node_id("prototype", p["id"]) for p in out.get("prototypes") or [] if p.get("slug")})
    for grp in sessions.values():
        subj = grp.get("subject") or {}
        subj_node = proto_keys.get(subj.get("id")) if subj.get("kind") == "prototype" else ""
        for s in grp.get("sessions") or []:
            sid = _add(nodes, seen, kind="session", rid=s["id"], title=subj.get("label") or s.get("id", ""),
                       created_at=s.get("created_at", ""), href=f'/sessions/{s["id"]}',
                       subtype=subtype_value("session", s), phase=_phase(out, s.get("created_at", "")),
                       extra={"persona_id": s.get("persona_id", ""), "subject": subj})
            edge(subj_node, sid, "informs", "tested in")
            if subj.get("kind") == "live_url":
                shost = _host(subj.get("url", ""))
                for anid, ahost in artifact_hosts.items():
                    if shost and ahost and shost == ahost:
                        edge(anid, sid, "informs", "tested in")
            elif subj.get("kind") == "flow":
                session_tokens = _tokens(subj.get("label"), subj.get("id"))
                for step in s.get("steps") or []:
                    action = step.get("action") or {}
                    state = step.get("state") or {}
                    session_tokens |= _tokens(action.get("target"), action.get("detail"),
                                              state.get("screen"), state.get("title"), step.get("monologue"))
                for aid, toks in asset_token_map.items():
                    if session_tokens & toks:
                        edge(aid, sid, "informs", "screen used")

    for te in plan_judgment_edges(out.get("plan"), seen):
        edge(te["from_study"], te["to_study"], te["type"], te.get("label", ""), te)

    # References are explicitly the council material pool. When no narrower ref edge exists,
    # connect them to the first recorded council as weak context so material does not appear as
    # random debris while still avoiding a fake chronological chain.
    council_ids = [n["study_id"] for n in sorted(nodes, key=lambda n: n.get("created_at", ""))
                   if str(n.get("study_id", "")).startswith("council:")]
    first_council = council_ids[0] if council_ids else ""
    if first_council:
        for aid in artifact_nodes.values():
            if not any(e.get("from_study") == aid or e.get("to_study") == aid for e in edges):
                edge(aid, first_council, "informs", "material")
    # Open questions frame the early research. Link unanswered questions to the first study node
    # when they are not already cited by surveys/hypotheses/decisions.
    first_study = next((n["study_id"] for n in sorted(nodes, key=lambda n: n.get("created_at", ""))
                        if str(n.get("study_id", "")).split(":", 1)[0]
                        in {"council", "survey", "hypothesis", "session", "report", "decision"}), "")
    if first_study:
        for o in out.get("open_questions") or []:
            oid = _node_id("open_question", o["id"])
            if not any(e.get("from_study") == oid or e.get("to_study") == oid for e in edges):
                edge(oid, first_study, "informs", "frames")

    out["nodes"] = sorted(nodes, key=lambda n: (n.get("created_at", ""), n.get("study_id", "")))
    out["edges"] = edges
    out["prototypes"] = []  # prototypes are explicit nodes in this experimental full graph.
    out["reports"] = []
    out["experimental_full_graph"] = True
    return out


def project_graph_view_data(graph: dict, *, sessions: dict[str, dict], decisions: list[dict],
                            hypotheses: list[dict], surveys: list[dict], assets: list[dict]) -> dict:
    """Return the payload consumed by the removable spatial graph view."""
    return augment_project_graph(graph, sessions=sessions, decisions=decisions, hypotheses=hypotheses,
                                 surveys=surveys, assets=assets)
