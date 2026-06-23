"""Predicted behavior, aggregated (ticket behavioral-prediction-output).

Opinions are cheap; predicted behavior is the product. The `predicted_behavior`
primitive (artifacts.py) lives wherever a persona speaks — usability-session
outcomes, councils, syntheses — with a canonical likelihood (the numeric value
calibration scores against) and an evidence-ref layer. This module is the
SEGMENT view: `aggregate_predictions` rolls every prediction in a project up by
(action, step, subject) — "3 of 5 personas abandon at the price reveal,
mean likelihood 0.7" — the shape syntheses/reports surface and the hypothesis
flow promotes into falsifiable bets."""

from __future__ import annotations

import re
from typing import Any

from ..storage import Store
from .. import artifacts as _A

from ._common import *  # noqa: F401,F403  (_require_research_project, …)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _collect(project: dict[str, Any], store: Store) -> list[dict[str, Any]]:
    """Every prediction recorded in the project, each stamped with its persona and
    its source artifact ({kind, id} — a resolvable Ref)."""
    rows: list[dict[str, Any]] = []
    for sess in store.list_usability_sessions(project_id=project["id"]):
        for p in (sess.get("outcome") or {}).get("predicted_behaviors") or []:
            rows.append({**p, "persona_id": p.get("persona_id") or sess.get("persona_id", ""),
                         "subject": p.get("subject") or (sess.get("subject") or {}).get("label", ""),
                         "source": {"kind": "session", "id": sess["id"], "anchor": p.get("id")}})
    for cid in project.get("council_ids") or []:
        c = store.get_council_session(cid)
        for p in (c or {}).get("predictions") or []:
            rows.append({**p, "source": {"kind": "council", "id": cid, "anchor": p.get("id")}})
    graph = get_project_graph(project["id"], store=store)  # noqa: F821 (bound)
    syn_ids = [str(n["study_id"]).split(":", 1)[1] for n in graph["nodes"]
               if str(n["study_id"]).startswith("synthesis:")]
    for sid in dict.fromkeys(syn_ids):
        syn = store.get_synthesis(sid)
        for p in (syn or {}).get("predictions") or []:
            rows.append({**p, "source": {"kind": "synthesis", "id": sid, "anchor": p.get("id")}})
    return rows


def aggregate_predictions(project_id: str, store: Store | None = None) -> dict[str, Any]:
    """The segment roll-up of every predicted behavior in a project: grouped by
    (action, step, subject) with persona attribution, mean likelihood, the evidence
    refs, and a by-step funnel. This is what reports surface and what the
    calibration loop scores cohort-level — the output schema is stable
    (see substrate get_study_result, which carries it)."""
    store = store or Store()
    project = _require_research_project(store, project_id)  # noqa: F821 (bound)
    rows = _collect(project, store)
    groups: dict[tuple, dict[str, Any]] = {}
    for r in rows:
        key = (_norm(r.get("action", "")), r.get("step"), _norm(r.get("subject", "")))
        g = groups.setdefault(key, {"action": r.get("action", ""), "step": r.get("step"),
                                    "subject": r.get("subject", ""), "count": 0, "personas": [],
                                    "likelihoods": [], "triggers": [], "refs": [], "sources": []})
        g["count"] += 1
        pid = r.get("persona_id") or ""
        if pid and pid not in g["personas"]:
            g["personas"].append(pid)
        lk = r.get("likelihood")
        if isinstance(lk, dict):                         # canonical {value, label}
            lk = lk.get("value")
        elif isinstance(lk, str):                        # compatibility free token: resolve if it's on scale
            lk = (_A.resolve_likelihood(lk) or {}).get("value")
        if isinstance(lk, (int, float)) and not isinstance(lk, bool):
            g["likelihoods"].append(float(lk))
        if r.get("trigger") and r["trigger"] not in g["triggers"]:
            g["triggers"].append(r["trigger"])
        g["refs"] = (g["refs"] + list(r.get("refs") or []))[:5]
        g["sources"].append(r["source"])
    out_groups = []
    for g in groups.values():
        lks = g.pop("likelihoods")
        g["likelihood_mean"] = round(sum(lks) / len(lks), 3) if lks else None
        out_groups.append(g)
    out_groups.sort(key=lambda g: (-g["count"], -(g["likelihood_mean"] or 0), g["action"]))
    by_step: dict[str, int] = {}
    for r in rows:
        if r.get("step") is not None:
            by_step[str(r["step"])] = by_step.get(str(r["step"]), 0) + 1
    return {"project_id": project["id"], "total": len(rows),
            "personas": len({r.get("persona_id") for r in rows if r.get("persona_id")}),
            "groups": out_groups, "by_step": by_step,
            "likelihood_scale": [t["term"] for t in _A.likelihood_terms()]}
