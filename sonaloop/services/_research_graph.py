"""Research-graph node helpers — the per-evidence node shapes and prototype/report enrichment the
project-graph builders (get_project_graph / plan_graph in _research) compose into the navigation graph.

Split out of sonaloop/services/_research.py (behavior-preserving) to keep both modules under the LOC
bar (spec/refactor-plan.md). Cross-module bare-name references (council_mode, note_graph_nodes,
list_usability_sessions, list_prototypes_artifacts, _plan, …) are bound at import time by
services/__init__.py, exactly as in the original single-module file."""

from __future__ import annotations

from typing import Any

from ..storage import Store
from .. import artifacts as _A


def _persona_stubs(store: Store, pids: list[str]) -> list[dict[str, Any]]:
    """The ≤4 resolved avatar stubs a row's crew cluster renders (the council-node shape)."""
    out = []
    for pid in pids[:4]:
        pr = store.get_persona(pid) or {}
        out.append({"id": pid, "display_name": pr.get("display_name", "?"),
                    "avatar": pr.get("avatar")})
    return out


def _study_node(store: Store, study_id: str) -> dict[str, Any] | None:
    """A graph node for a synthesis (study) — used by the plan-less / report study_ids path."""
    syn = store.get_synthesis(study_id)
    if not syn:
        return None
    sentiment = _A.synthesis_sentiment_counts(syn, store)   # aggregated over the REAL council voices
    # the voices' personas (the synthesis's OWN statements) — the row avatar cluster (§10 W11)
    spids: list[str] = []
    for st in syn.get("statements") or []:
        pid = st.get("persona_id") or ""
        if pid and pid not in spids:
            spids.append(pid)
    return {
        "study_id": study_id, "kind": "synthesis", "title": syn.get("title", study_id),
        "status": syn.get("status", "done"), "created_at": syn.get("created_at", ""),
        "goal": syn.get("goal", ""), "council_count": len(syn.get("council_ids", [])),
        "voices": len(spids) or sum(sentiment.values()), "sentiment": sentiment,
        "personas": _persona_stubs(store, spids),
        "recommendations": len(_A.synthesis_recommendations(syn)),
        "n_findings": len(syn.get("findings") or []),
        "phase": syn.get("phase", ""), "mode": syn.get("mode", ""), "role": syn.get("role", ""),
    }


def prototype_participation(proto: dict, store: Store | None = None) -> dict[str, Any]:
    """Persona participation riding a prototype's DATA (ux-contract §10 W11): the personas who
    drove its sessions — BOTH kinds (recorded prototype reactions + usability walks whose
    subject is this prototype, matched by id or slug). Returns the crew enrichment every row
    surface shares: `n_sessions` (honest combined count), `voices` (distinct drivers) and
    `personas` (≤4 resolved avatar stubs, first-seen order)."""
    store = store or Store()
    pids: list[str] = []
    n = 0
    for s in store.list_prototype_sessions(prototype_id=proto["id"]):
        n += 1
        pid = s.get("persona_id") or ""
        if pid and pid not in pids:
            pids.append(pid)
    seen: set[str] = set()
    for key in (proto.get("id"), proto.get("slug")):
        for s in (list_usability_sessions(subject=key, store=store) if key else []):  # noqa: F821 (bound)
            if s["id"] in seen:
                continue
            seen.add(s["id"])
            n += 1
            pid = s.get("persona_id") or ""
            if pid and pid not in pids:
                pids.append(pid)
    return {"n_sessions": n, "voices": len(pids), "personas": _persona_stubs(store, pids)}


def _protos_with_session_counts(project_id: str, store: Store) -> list[dict]:
    """The project's prototypes, each enriched with `n_sessions` — recorded persona reactions
    (prototype sessions) PLUS usability walks whose subject is this prototype — and the session
    drivers' crew (`personas`/`voices`, ux-contract §10 W11). Feeds the outline row's
    sessions-count chip + avatar cluster (§3.2) so both are honest by construction."""
    protos = list_prototypes_artifacts(project_id, store=store)  # noqa: F821 (bound)
    for p in protos:
        p.update(prototype_participation(p, store))
    return protos


def _attach_reports(g: dict, project_id: str, store: Store) -> dict:
    """Reports (project-scope syntheses) are first-class project artifacts — expose them on the graph so
    the outline lists them inline (among the methodology rows), not just as a top-bar button."""
    existing_synthesis_ids = {
        str(n.get("study_id", "")).split(":", 1)[-1]
        for n in g.get("nodes") or []
        if str(n.get("study_id", "")).startswith("synthesis:")
    }
    g["reports"] = [{"id": r["id"], "title": r.get("title", ""), "created_at": r.get("created_at", ""),
                     "n_sections": len(r.get("sections") or [])}
                    for r in store.list_reports(project_id)
                    if r["id"] not in existing_synthesis_ids]
    project = store.get_research_project(project_id) or {}
    g["job_outcomes"] = [{
        "id": str(o.get("id", "")),
        "schema_id": o.get("schema_id", ""),
        "title": o.get("name") or o.get("schema_id", ""),
        "created_at": o.get("created_at", ""),
        "result_kind": o.get("result_kind", ""),
    } for o in sorted((project.get("job_outcomes") or []), key=lambda x: x.get("created_at", ""))
        if o.get("id")]
    return g


def _plan_methodology_state(project: dict, plan: dict, store: Store) -> dict[str, Any] | None:
    """A layout-ready step state derived from the PLAN's real analyze→act→verify DAG: each frame
    (analyze) task is a fan/diverge step and each verify task is a waist/converge step, wired along
    the task `consumes` graph. Build steps (frames whose act tasks produced artifacts) declare the
    artifact_type + the fidelity discriminators built under them, so prototypes place in — and route
    out of — the right diamond. Reflects the actual constellation, not a static spec."""
    tasks = plan.get("tasks", [])
    if not tasks:
        return None
    builds_under: dict[str, set] = {}   # frame id -> fidelity tags of artifacts built from it
    syn_of_verify: dict[str, str] = {}  # verify id -> its synthesis node id (the convergence node)
    for t in tasks:
        if t["bucket"] == "act":
            for p in t.get("produces", []):
                if p.get("kind") in {"artifact", "prototype"}:
                    proto = store.get_prototype(p["id"]) or {}
                    fids = {x for x in (proto.get("tags") or []) if x and x != "prototype"} or {"prototype"}
                    for c in t.get("consumes", []):
                        builds_under.setdefault(c, set()).update(fids)
        elif t["bucket"] == "verify":
            syn = next((p["id"] for p in t.get("produces", []) if p["kind"] == "synthesis"), None)
            if syn:
                syn_of_verify[t["id"]] = f"synthesis:{syn}"
    steps = []
    for t in tasks:
        if t["bucket"] not in ("analyze", "verify"):
            continue
        is_fan = t["bucket"] == "analyze"
        produces: dict[str, Any] = {"role": t.get("capability", "")}
        if t["id"] in builds_under:
            produces["artifact_type"] = "prototype"
            produces["more_tags"] = sorted(builds_under[t["id"]])
        steps.append({"key": t["id"], "name": t.get("title", t["id"]),
                      "mode": "diverge" if is_fan else "converge", "is_fan": is_fan,
                      "role": t.get("capability", ""), "presentation": t.get("presentation") or {},
                      "tags": [t.get("capability", "")] if t.get("capability") else [],
                      "consumes": list(t.get("consumes", [])), "produces": produces,
                      "requires": t.get("requires", {}) or {},
                      "status": "done" if t.get("status") == "done" else "pending",
                      "exploration_count": 0, "convergence_node": syn_of_verify.get(t["id"]),
                      "judgments": []})
    return {"project_id": project["id"], "methodology": plan.get("methodology", ""), "phase": "",
            "complete": _plan.is_complete(plan), "steps": steps, "phases": steps}  # noqa: F821 (bound)


def _evidence_node(kind: str, eid: str, title: str, prod_task: dict, store: Store) -> dict[str, Any]:
    """A heterogeneous graph node for one evidence item. Color/label come from data (present(kind))."""
    from .. import presentation as _pres
    pres = _pres.present(kind)
    # Bind the node to a layout column: a verify task's synthesis sits in that verify STEP (a waist);
    # an act task's evidence fans from the FRAME it consumes (the diverge step) — so diamonds emerge
    # from the plan's real analyze→act→verify DAG, not from a static spec.
    if prod_task.get("bucket") == "verify":
        step = prod_task.get("id", "")
    else:
        cons = prod_task.get("consumes") or []
        step = cons[0] if cons else prod_task.get("step", "")
    created = ""
    council_count = 0
    voices = 0
    personas: list[dict] = []
    stance_counts: dict[int, int] = {}
    mode = ""
    n_statements = 0
    n_findings = 0
    status = ""
    if kind == "council":
        c = store.get_council_session(eid) or {}
        created = c.get("created_at", "")
        council_count = 1
        # The same council mode/count metadata that detail pages and filters may need rides the node.
        mode = council_mode(c)  # noqa: F821 (bound)
        n_statements = len(c.get("statements") or [])
        # Persona presence feeds the row's avatar cluster; stance counts remain graph metadata for
        # richer detail/report surfaces, not row chrome.
        pids: list[str] = []
        for st in c.get("statements") or []:
            pid = st.get("persona_id") or ""
            if pid and pid not in pids:
                pids.append(pid)
            val = (st.get("stance") or {}).get("value")
            if val is not None:
                stance_counts[int(val)] = stance_counts.get(int(val), 0) + 1
        voices = len(pids)
        personas = _persona_stubs(store, pids)
    elif kind == "synthesis":
        s = store.get_synthesis(eid) or {}
        created = s.get("created_at", "")
        council_count = len(s.get("council_ids", []))
        n_findings = len(s.get("findings") or [])
        status = s.get("status", "done")
        # WHO speaks in the report — the voices' personas (statements), so the outline row
        # carries the same avatar cluster as the council rows (ux-contract §10 W11).
        spids: list[str] = []
        for st in s.get("statements") or []:
            pid = st.get("persona_id") or ""
            if pid and pid not in spids:
                spids.append(pid)
        voices = len(spids)
        personas = _persona_stubs(store, spids)
    href = {"council": f"/councils/{eid}", "synthesis": f"/syntheses/{eid}"}.get(kind, "")
    tags = [kind] + list(prod_task.get("presentation", {}).get("tags") or [])
    return {"study_id": f"{kind}:{eid}", "kind": kind, "title": title, "phase": step,
            "bucket": prod_task.get("bucket", ""), "created_at": created, "council_count": council_count,
            "voices": voices, "sentiment": {}, "stance_counts": stance_counts,
            "personas": personas, "recommendations": 0, "role": prod_task.get("capability", ""),
            "mode": mode, "n_statements": n_statements, "n_findings": n_findings, "status": status,
            "theme_tags": tags, "color": pres["color"], "kind_label": pres["label"],
            "href": href}
