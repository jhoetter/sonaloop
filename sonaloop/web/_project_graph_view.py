"""Experimental full project graph adapter.

This module is intentionally removable: /jobs still owns the canonical list view, while this
adapter only translates the same project primitives into graph nodes so we can judge whether a
spatial view is useful enough to keep.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from ..project_trace import collect_project_trace_edges
from ._i18n import t
from ._primitive_taxonomy import primitive_color, subtype_label, subtype_value


def _node_id(kind: str, rid: str) -> str:
    return f"{kind}:{rid}"


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

    for n in list(nodes):
        if n.get("kind") and not n.get("color"):
            n["color"] = primitive_color(str(n["kind"]))

    for r in out.get("reports") or []:
        _add(nodes, seen, kind="report", rid=r["id"], title=r.get("title", ""),
             created_at=r.get("created_at", ""), href=f'/syntheses/{r["id"]}',
             phase=_phase(out, r.get("created_at", "")),
             extra={"n_sections": r.get("n_sections", 0)})

    for p in out.get("prototypes") or []:
        _add(nodes, seen, kind="prototype", rid=p["id"], title=p.get("name", ""),
             created_at=p.get("created_at", ""), href=f'/prototypes/{p.get("slug", p["id"])}',
             subtype=subtype_value("prototype", p),
             phase=_phase(out, p.get("created_at", "")))

    for a in out.get("artifacts") or []:
        _add(nodes, seen, kind="url_artifact", rid=a["id"], title=a.get("title") or a.get("url", ""),
             created_at=a.get("created_at", ""), href=f'/references/{a["id"]}',
             subtype=subtype_value("url_artifact", a), phase=_phase(out, a.get("created_at", "")),
             extra={"url": a.get("url", ""), "variant": a.get("label", "")})

    for a in assets:
        _add(nodes, seen, kind="asset", rid=a["id"], title=a.get("title") or a.get("filename", ""),
             created_at=a.get("created_at", ""), href=f'/assets/{a["id"]}',
             subtype=subtype_value("asset", a), phase=_phase(out, a.get("created_at", "")),
             extra={"direction": a.get("direction", "in")})

    for o in out.get("open_questions") or []:
        _add(nodes, seen, kind="open_question", rid=o["id"], title=o.get("text", ""),
             created_at=o.get("created_at", ""), href=f'/open-questions/{o["id"]}',
             phase=_phase(out, o.get("created_at", "")), extra={"status": o.get("status", "open")})

    for s in surveys:
        _add(nodes, seen, kind="survey", rid=s["id"], title=s.get("title", ""),
             created_at=s.get("created_at", ""), href=f'/surveys/{s["id"]}',
             subtype=subtype_value("survey", s), phase=_phase(out, s.get("created_at", "")),
             extra={"status": s.get("status", "draft")})

    for hyp in hypotheses:
        _add(nodes, seen, kind="hypothesis", rid=hyp["id"], title=hyp.get("text", ""),
             created_at=hyp.get("created_at", ""), href=f'/hypotheses/{hyp["id"]}',
             phase=_phase(out, hyp.get("created_at", "")), extra={"status": hyp.get("status", "open")})

    for d in decisions:
        _add(nodes, seen, kind="decision", rid=d["id"], title=d.get("title", ""),
             created_at=d.get("created_at", ""), href=f'/decisions/{d["id"]}',
             phase=_phase(out, d.get("created_at", "")), extra={"status": d.get("status", "proposed")})

    for grp in sessions.values():
        subj = grp.get("subject") or {}
        for s in grp.get("sessions") or []:
            _add(nodes, seen, kind="session", rid=s["id"], title=subj.get("label") or s.get("id", ""),
                 created_at=s.get("created_at", ""), href=f'/sessions/{s["id"]}',
                 subtype=subtype_value("session", s), phase=_phase(out, s.get("created_at", "")),
                 extra={"persona_id": s.get("persona_id", ""), "subject": subj})

    out["nodes"] = sorted(nodes, key=lambda n: (n.get("created_at", ""), n.get("study_id", "")))
    out["edges"] = collect_project_trace_edges(
        out, nodes, sessions=sessions, decisions=decisions, hypotheses=hypotheses,
        surveys=surveys, assets=assets, base_edges=out.get("edges") or [],
    )
    out["prototypes"] = []  # prototypes are explicit nodes in this experimental full graph.
    out["reports"] = []
    out["experimental_full_graph"] = True
    return out
