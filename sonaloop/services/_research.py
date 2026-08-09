"""Research graph: projects, typed study edges, themes, open questions, frontier, plan graph.

Split out of the original sonaloop/services.py (behavior-preserving).
Cross-module function references are bound at import time by services/__init__.py."""

from __future__ import annotations

import csv
import contextvars
import copy
import hashlib
import json
import random
import re
import uuid
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any

from ..config import (
    utc_now_iso, content_language, ensure_content_language, language_instruction,
    critic_threshold, critic_sample_k, current_request_actor,
)
from ..models import (
    CalendarEvent,
    CouncilSession,
    DailySummary,
    Evidence,
    ExperienceEvent,
    OpenQuestion,
    PainPointObservation,
    Persona,
    PrototypeSession,
    Reflection,
    ResearchProject,
    SimulationResult,
    Synthesis,
)
from ..storage import Store
from .. import artifacts as _A
from ..taxonomy import GENERIC_TOOLS, normalized_tool_ids, normalized_tools
from .. import memory as memory_mod
from .. import evaluation as evaluation_mod
from ..llm_simulation import (
    build_cohort_critic_prompt,
    build_consolidation_prompt,
    build_synthesis_outline_prompt,
    build_synthesis_section_prompt,
    validate_synthesis_outline_payload,
    validate_synthesis_section_payload,
    build_digest_prompt,
    build_eval_critic_prompt,
    build_evidence_check_prompt,
    build_persona_revision_prompt,
    build_plan_prompt,
    build_profile_prompt,
    build_synthesis_prompt,
    validate_activity_payload,
    validate_cohort_critic_payload,
    validate_digest_payload,
    validate_eval_critic_payload,
    validate_evidence_check_payload,
    validate_memory_deltas_payload,
    validate_persona_revision_payload,
    validate_plan_payload,
    validate_profile_payload,
    validate_synthesis_payload,
)


from ._common import *  # noqa: F401,F403  (shared helpers + constants)
from .._project_locks import project_lifecycle_locks


_PROJECT_GRAPH_CACHE: contextvars.ContextVar[dict[tuple[int, str], dict[str, Any]] | None] = \
    contextvars.ContextVar("sonaloop_project_graph_cache", default=None)


def begin_project_graph_cache() -> contextvars.Token:
    return _PROJECT_GRAPH_CACHE.set({})


def end_project_graph_cache(token: contextvars.Token) -> None:
    _PROJECT_GRAPH_CACHE.reset(token)


def _cached_project_graph(cache: dict[tuple[int, str], dict[str, Any]] | None,
                          key: tuple[int, str]) -> dict[str, Any] | None:
    if cache is None or key not in cache:
        return None
    return copy.deepcopy(cache[key])


def _store_project_graph_cache(cache: dict[tuple[int, str], dict[str, Any]] | None,
                               key: tuple[int, str], graph: dict[str, Any]) -> dict[str, Any]:
    if cache is not None:
        cache[key] = copy.deepcopy(graph)
    return graph


def create_research_project(title: str, goal: str = "", persona_ids: list[str] | None = None,
                            description: str = "", store: Store | None = None,
                            icon: Any | None = None, project_id: str | None = None,
                            operation_id: str | None = None,
                            operation_fingerprint: str | None = None) -> dict[str, Any]:
    store = store or Store()
    if project_id:
        existing = store.get_research_project(project_id)
        if existing:
            from ._common import web_url
            return {**existing, "url": web_url(f"/jobs/{existing['id']}"),
                    "_operation_claimed": False}
    now = utc_now_iso()
    pid = project_id or stable_id("rproject", title, now)
    base = slugify(title)
    slug, n = base, 2
    while store.get_research_project(slug) is not None:
        slug, n = f"{base}-{n}", n + 1
    creator = current_request_actor()
    project = ResearchProject(
        id=pid, slug=slug, title=title, goal=goal, description=description,
        persona_ids=persona_ids or [], study_ids=[], study_tags={}, themes=[],
        status="active", created_at=now, updated_at=now, council_ids=[],
        created_by=creator,
    ).to_dict()
    if creator is None:
        # Keep local/unbound and pre-attribution projects indistinguishable: absence is honest and
        # must never be backfilled from a later editor or retrying request.
        project.pop("created_by", None)
    if operation_id:
        project["operation_id"] = operation_id
        project["operation_fingerprint"] = operation_fingerprint or ""
        project["operation_state"] = "creating"
    project["icon"] = normalize_project_icon(icon or "random", title=title, goal=goal, seed=pid)  # noqa: F821 (bound)
    operation_claimed: bool | None = None
    if operation_id:
        operation_claimed = store.insert_research_project_if_absent(project)
        if not operation_claimed:
            existing = store.get_research_project(pid)
            if not existing:  # pragma: no cover - a committed conflict row must be readable
                raise RuntimeError("project operation claim lost without an existing project")
            from ._common import web_url
            return {**existing, "url": web_url(f"/jobs/{existing['id']}"),
                    "_operation_claimed": False}
    else:
        store.upsert_research_project(project)
    root = {"id": "frame__root", "title": "Frame the inquiry", "bucket": "analyze",
            "capability": "frame", "consumes": [],
            "intent": "Understand before concluding: read persona memory + author the research "
                      "questions/hypotheses this inquiry needs before any council runs."}
    _plan.save_plan(_plan.new_plan(pid, goal, "", [root]), store=store)
    # The answer to "where can I look at this?" rides every creation result —
    # remote hosts (MCP connectors) surface it to the user.
    from ._common import web_url
    out = {**project, "url": web_url(f"/jobs/{pid}")}
    if operation_claimed is not None:
        out["_operation_claimed"] = operation_claimed
    return out


def update_research_project(project_id: str, patch: dict[str, Any],
                            store: Store | None = None) -> dict[str, Any]:
    """Patch a project's STRUCTURAL metadata (title/goal/description/status) — the
    container fields only, never graph contents or authored study text. Unknown
    patch keys are ignored; the slug stays stable (it's a durable handle)."""
    store = store or Store()
    project = _require_research_project(store, project_id)
    if "title" in patch and patch["title"] is not None:
        title = str(patch["title"]).strip()
        if not title:
            raise ValueError("a project needs a non-empty title")
        project["title"] = title[:200]
    for key in ("goal", "description"):
        if key in patch and patch[key] is not None:
            project[key] = str(patch[key]).strip()[:2000]
    if patch.get("status"):
        project["status"] = str(patch["status"]).strip()[:40]
    if "icon" in patch and patch["icon"] is not None:
        project["icon"] = normalize_project_icon(patch["icon"], title=project.get("title", ""),
                                                 goal=project.get("goal", ""), seed=project["id"])  # noqa: F821
    project["updated_at"] = utc_now_iso()
    store.upsert_research_project(project)
    emit_lifecycle_event("project.updated",  # noqa: F821 (bound)
                         {"project_id": project["id"], "title": project["title"]}, store)
    return project


def _public_creator_projection(value: Any) -> dict[str, str] | None:
    """Return the deliberately tiny creator shape allowed on public list surfaces.

    The persisted request-actor snapshot also contains an opaque subject id, role,
    channel and capture timestamp.  Those fields are useful for server-side audit and
    portable snapshots, but a cross-workspace project listing needs only the immutable
    display label.  Revalidate imported/legacy rows here instead of assuming every
    stored mapping passed through the current request-boundary normalizer.
    """
    if not isinstance(value, dict):
        return None
    label = value.get("label")
    if not isinstance(label, str):
        return None
    label = label.strip()
    if not label or len(label) > 160 or not label.isprintable():
        return None
    return {"label": label}


def list_research_project_summaries(store: Store | None = None) -> list[dict[str, Any]]:
    """Lean project metadata for list pages — NO graph builds, NO run-state, NO counts.
    Returns id/slug/title/goal/status/icon/persona_ids/themes plus the immutable
    public creator display label when one was captured. Opaque actor ids,
    roles, channels and audit timestamps remain server-side. The list page
    paginates this lean list, then enriches only the visible page with
    `enrich_research_project` (graph counts, run state)."""
    store = store or Store()
    return [
        {"id": p["id"], "slug": p["slug"], "title": p["title"], "goal": p.get("goal", ""),
         "status": p.get("status", "active"),
         "icon": p.get("icon") or {"kind": "regular", "name": "projects"},
         "url": web_url(f"/jobs/{p['id']}"),  # noqa: F821 (bound)
         "persona_ids": list(p.get("persona_ids") or []),
         "themes": p.get("themes", []),
         **({"created_by": public_creator}
            if (public_creator := _public_creator_projection(p.get("created_by"))) else {})}
        for p in store.list_research_projects()
    ]


def enrich_research_project(
    summary: dict[str, Any], store: Store,
    _batch: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Add graph counts, run state, and per-project counts to a lean summary.
    `_batch` is an optional pre-loaded batch from `_project_count_batch(store)` —
    pass it when enriching multiple projects to avoid re-loading per project."""
    pid = summary["id"]
    graph = get_project_graph(pid, store=store)
    protos = graph.get("prototypes") or []
    proto_ids = {pr.get("id") for pr in protos}
    b = _batch or _project_count_batch(store)
    proto_sessions = [s for mid in proto_ids for s in b["proto_sessions_by_proto"].get(mid, [])]
    try:
        rs = _plan.project_run_state(pid, store=store)
    except Exception:
        rs = None
    return {**summary,
            **({"run_state": rs} if rs else {}),
            "studies": sum(1 for n in graph["nodes"] if n.get("kind") == "synthesis"),
            "councils": sum(1 for n in graph["nodes"] if n.get("kind") == "council"),
            "notes": sum(1 for n in graph["nodes"] if n.get("kind") == "note"),
            "prototypes": len(protos),
            "sessions": len(b["usability_by_proj"].get(pid, [])) + len(proto_sessions),
            "surveys": len(b["surveys_by_proj"].get(pid, [])),
            "hypotheses": len(b["hyp_by_proj"].get(pid, [])),
            "decisions": len(b["dec_by_proj"].get(pid, [])),
            "open_questions": len(graph.get("open_questions") or []),
            "references": len(graph.get("artifacts") or []),
            "assets": len(graph.get("assets") or []),
            "edges": graph["counts"].get("edges", 0)}


def _project_count_batch(store: Store) -> dict[str, Any]:
    """Batch-load all per-project count tables once, grouped by project_id/prototype_id."""
    proto_sessions_by_proto: dict[str, list[dict]] = {}
    for s in store.list_prototype_sessions():
        proto_sessions_by_proto.setdefault(s.get("prototype_id", ""), []).append(s)
    surveys_by_proj: dict[str, list[dict]] = {}
    for s in store.list_surveys():
        surveys_by_proj.setdefault(s.get("project_id", ""), []).append(s)
    hyp_by_proj: dict[str, list[dict]] = {}
    for h in store.list_hypotheses():
        hyp_by_proj.setdefault(h.get("project_id", ""), []).append(h)
    dec_by_proj: dict[str, list[dict]] = {}
    for d in store.list_decisions():
        dec_by_proj.setdefault(d.get("project_id", ""), []).append(d)
    usability_by_proj: dict[str, list[dict]] = {}
    for u in store.list_usability_sessions():
        usability_by_proj.setdefault(u.get("project_id", ""), []).append(u)
    return {"proto_sessions_by_proto": proto_sessions_by_proto,
            "surveys_by_proj": surveys_by_proj,
            "hyp_by_proj": hyp_by_proj,
            "dec_by_proj": dec_by_proj,
            "usability_by_proj": usability_by_proj}


def list_research_projects(store: Store | None = None) -> list[dict[str, Any]]:
    """Project summaries for the inspector list. Counts come from the project GRAPH —
    the plan-evidence graph is the source of truth, and `study_ids` is empty for
    plan-based projects, so a raw len(study_ids) would read 0. `studies` counts
    synthesis nodes (matching the list's label); `edges` is the build-order count.

    Batch-loads all list tables once and groups in Python to avoid N+1 queries
    (prototype_sessions was a full table scan per project — N x full-scan).

    For paginated list pages, prefer `list_research_project_summaries` + enrich only
    the visible page with `enrich_research_project` — this avoids building N graphs
    when only 25 rows are visible."""
    store = store or Store()
    summaries = list_research_project_summaries(store=store)
    batch = _project_count_batch(store)
    return [enrich_research_project(s, store, _batch=batch) for s in summaries]


def get_research_project(project_id: str, store: Store | None = None) -> dict[str, Any]:
    store = store or Store()
    return _require_research_project(store, project_id)


def parent_project_of_study(study_id: str, store: Store | None = None) -> dict[str, Any] | None:
    """Reverse lookup: which research project contains this synthesis (study)?
    Powers the Project > Synthesis > Council hierarchy/breadcrumbs."""
    store = store or Store()
    for p in store.list_research_projects():
        if study_id in (p.get("study_ids") or []):
            return {"id": p["id"], "slug": p["slug"], "title": p["title"]}
    return None


def parent_study_of_council(council_id: str, store: Store | None = None) -> dict[str, Any] | None:
    """Reverse lookup: which synthesis (study) folds in this council?"""
    store = store or Store()
    for s in store.list_syntheses():
        if council_id in (s.get("council_ids") or []):
            return {"id": s["id"], "title": s["title"]}
    return None



def parent_project_of_council(council_id: str, store: Store | None = None) -> dict[str, Any] | None:
    """Reverse lookup: which research project OWNS this council? Councils are scoped to a
    project at creation; this is the direct link (independent of whether a synthesis cites it)."""
    store = store or Store()
    council = store.get_council_session(council_id)
    pid = (council or {}).get("project_id")
    if pid:
        p = store.get_research_project(pid)
        if p:
            return {"id": p["id"], "slug": p["slug"], "title": p["title"]}
    # Fallback for projects that track the council in their list (e.g. compatibility/migrated data).
    for p in store.list_research_projects():
        if council_id in (p.get("council_ids") or []):
            return {"id": p["id"], "slug": p["slug"], "title": p["title"]}
    return None


def parent_project_of_synthesis(synthesis_id: str, store: Store | None = None) -> dict[str, Any] | None:
    """Which project owns this synthesis? Robust for PLAN-based projects (the synthesis is produced by
    a plan verify task, not listed in the old `study_ids`) and for ones that DECLARE their project_id
    (record_synthesis project_id). Powers correct breadcrumbs. For a deliverable's asset attach the
    export path additionally falls back to the citation rule (owning_project_of_synthesis)."""
    store = store or Store()
    syn = store.get_synthesis(synthesis_id) or {}
    declared = store.get_research_project(syn["project_id"]) if syn.get("project_id") else None
    if declared:
        return {"id": declared["id"], "slug": declared["slug"], "title": declared["title"]}
    p = parent_project_of_study(synthesis_id, store=store)        # compatibility/constellation path
    if p:
        return p
    for proj in store.list_research_projects():                   # plan path: a task produces it
        plan = _plan.get_plan(proj["id"], store=store) or {}
        for task in plan.get("tasks", []):
            if any(r.get("kind") == "synthesis" and r.get("id") == synthesis_id
                   for r in task.get("produces", [])):
                return {"id": proj["id"], "slug": proj["slug"], "title": proj["title"]}
    return None


def owning_project_of_synthesis(synthesis_id: str, store: Store | None = None) -> dict[str, Any] | None:
    """parent_project_of_synthesis + the absorption fallback: a synthesis that declares no project
    but cites ONLY one project's owned councils is owned by it. For SIDE EFFECTS (the deliverable
    export's asset attach) — off the breadcrumb resolver so a citing synthesis stays library-rooted."""
    store = store or Store()
    p = parent_project_of_synthesis(synthesis_id, store=store)
    if p:
        return p
    cited = list((store.get_synthesis(synthesis_id) or {}).get("council_ids") or [])
    if cited:
        for proj in store.list_research_projects():
            owned = set(proj.get("council_ids") or [])
            if owned and all(c in owned for c in cited):
                return {"id": proj["id"], "slug": proj["slug"], "title": proj["title"]}
    return None



# M-cleanup: the constellation study-graph service (add_study_to_project / set_study_themes /
# link_studies + _apply_themes/_study_node) is RETIRED — the plan engine is the single graph (HX3).


def record_open_questions(project_id: str, questions: list[str], study_id: str | None = None,
                          store: Store | None = None) -> list[dict[str, Any]]:
    store = store or Store()
    project = _require_research_project(store, project_id)
    now = utc_now_iso()
    out = []
    for q in questions:
        text = str(q).strip()
        if not text:
            continue
        oq = OpenQuestion(id=stable_id("oq", project["id"], text), project_id=project["id"],
                          study_id=study_id, text=text[:600], status="open", created_at=now).to_dict()
        store.upsert_open_question(oq)
        out.append(oq)
    return out






def ref_backlinks(project_id: str, store: Store | None = None) -> dict[str, list[dict[str, Any]]]:
    """Reverse cross-reference index for a project (spec/artifact-cross-references.md §4): for every
    addressed part, who points AT it. Returns {address: [{href, label, role}]}. Built by scanning every
    artifact's outgoing refs — so a council statement learns it is 'cited by' the synthesis that derives
    from it (the bidirectional knowledge graph), without any data duplication."""
    store = store or Store()
    proj = _require_research_project(store, project_id)
    idx: dict[str, list[dict[str, Any]]] = {}

    def add(target: dict, label: str, href: str):
        if not (target and target.get("id")):
            return
        addr = _A.part_address(target["kind"], target["id"], target.get("anchor"))
        idx.setdefault(addr, []).append({"href": href, "label": label, "role": target.get("role")})

    syns = store.list_syntheses()
    councils = {c["id"]: c for c in store.list_council_sessions(project_id=proj["id"])}
    for syn in syns:
        if not any(cid in councils for cid in (syn.get("council_ids") or [])) and \
           syn["id"] not in (proj.get("study_ids") or []):
            continue
        for f in (syn.get("findings") or []):
            for r in (f.get("refs") or []):
                add(r, syn.get("title", ""), f'/syntheses/{syn["id"]}#{f.get("id", "")}')
    # councils referencing each other / earlier parts
    for c in councils.values():
        for s in (c.get("statements") or []):
            for r in (s.get("refs") or []):
                if r.get("kind") in ("council", "synthesis", "note"):
                    add(r, c.get("prompt", ""), f'/councils/{c["id"]}#{s.get("id", "")}')
    # decisions citing evidence (based_on) and naming alternatives (rejected) — so a synthesis
    # learns it "informed decision <title>" (ticket decision-record-artifact)
    for d in store.list_decisions(proj["id"]):
        for r in (d.get("based_on") or []) + (d.get("rejected") or []):
            add(r, d.get("title", ""), f'/decisions/{d["id"]}')
    return idx


def get_project_graph(project_id: str, store: Store | None = None) -> dict[str, Any]:
    """The core navigation call: nodes (studies + tags/sentiment), typed edges,
    themes, build order, and open questions for one research project. When the project has a
    research PLAN with recorded evidence, the graph is the heterogeneous plan-evidence graph
    (councils/syntheses/artifacts/frames as first-class nodes)."""
    store = store or Store()
    cache = _PROJECT_GRAPH_CACHE.get()
    cache_key = (id(store), project_id)
    cached = _cached_project_graph(cache, cache_key)
    if cached is not None:
        return cached
    plan = _plan.get_plan(project_id, store=store)
    if plan is not None:                       # the plan engine is the single source of truth (HX3)
        g = _attach_reports(plan_graph(project_id, store=store), project_id, store)
        g["project"]["url"] = web_url(f"/jobs/{project_id}")  # noqa: F821 (bound) — the link to hand the user
        return _store_project_graph_cache(cache, cache_key, g)
    # Plan-less fallback (start_project always seeds a plan, so this is only hit by hand-built data /
    # the study_ids-based report path): nodes from the project's councils/studies + notes — NO
    # study-edge layer (retired), so no edges.
    project = _require_research_project(store, project_id)
    tags = project.get("study_tags", {})
    nodes = []
    for cid in project.get("council_ids", []):
        c = store.get_council_session(cid)
        if c:
            nodes.append(_evidence_node("council", cid, c.get("prompt", cid), {}, store))
    for sid in project.get("study_ids", []):
        node = _study_node(store, sid)
        if node:
            node["theme_tags"] = tags.get(sid, [])
            nodes.append(node)
    nodes.extend(note_graph_nodes(project))
    nodes.sort(key=lambda n: n.get("created_at", ""))
    oqs = store.list_open_questions(project["id"])
    g = {
        "project": {"id": project["id"], "slug": project["slug"], "title": project["title"],
                    "goal": project.get("goal", ""), "status": project.get("status", "active"),
                    "persona_ids": project.get("persona_ids", []), "themes": project.get("themes", []),
                    "methodology": project.get("methodology", ""), "phase": project.get("phase", ""),
                    "integrity": project.get("integrity") or {},
                    "product_understanding_current_id": project.get("product_understanding_current_id", ""),
                    "product_understanding_versions": project.get("product_understanding_versions") or [],
                    "supersedes_project_id": project.get("supersedes_project_id", ""),
                    "superseded_by_project_id": project.get("superseded_by_project_id", ""),
                    "lineage": project.get("lineage") or {}, "archive": project.get("archive") or {},
                    "icon": project.get("icon") or {"kind": "regular", "name": "projects"},
                    "url": web_url(f"/jobs/{project['id']}")},  # noqa: F821 (bound)
        "methodology_state": None,
        "prototypes": _protos_with_session_counts(project["id"], store),
        "artifacts": list(project.get("artifacts") or []),
        "assets": list(project.get("assets") or []),
        "sections": list(project.get("sections") or []),
        "nodes": nodes,
        "edges": [],
        "open_questions": oqs,
        "build_order": [n["study_id"] for n in nodes],
        "counts": {"studies": len(nodes), "edges": 0,
                   "open_questions": sum(1 for o in oqs if o.get("status") == "open"),
                   "themes": len(project.get("themes", []))},
    }
    return _store_project_graph_cache(cache, cache_key, _attach_reports(g, project_id, store))



def plan_graph(project_id: str, store: Store | None = None) -> dict[str, Any]:
    """Heterogeneous evidence graph for a plan-based project: councils/syntheses/frames as
    first-class nodes (artifacts via the prototypes list), edges from the act fan to its verify
    synthesis, diamonds laid out over act->verify via the plan's constellation."""
    store = store or Store()
    project = _require_research_project(store, project_id)
    plan = _plan.get_plan(project_id, store=store)
    nodes: list[dict[str, Any]] = []
    seen: set[str] = set()

    def _title(kind: str, eid: str, t: dict) -> str:
        if kind == "council":
            return (store.get_council_session(eid) or {}).get("prompt", eid)
        if kind == "synthesis":
            return (store.get_synthesis(eid) or {}).get("title", eid)
        if kind == "frame":
            return f"Frame · {t.get('title', eid)}"
        return eid

    for t in plan["tasks"]:
        for r in t["produces"]:
            kind, eid = r["kind"], r["id"]
            if kind not in ("council", "synthesis"):  # artifacts render via the prototypes list;
                continue                              # sessions live on their prototype; frames stay plan-internal
            nid = f"{kind}:{eid}"
            if nid in seen:
                continue
            seen.add(nid)
            nodes.append(_evidence_node(kind, eid, _title(kind, eid, t), t, store))
    # Absorb project-owned evidence the plan never produced: remote MCP hosts demonstrably
    # record_council/record_synthesis OUTSIDE the governed run loop, and a council the project
    # owns (record_council appends every one to project.council_ids) must not vanish from the
    # graph, the page and every count just because no task checkpointed it. Placement mirrors
    # the web outline's honest fallback: the phase active at created_at, else the first frame.
    plan_bound = sorted(nodes, key=lambda n: n.get("created_at", ""))
    first_frame = next((t["id"] for t in plan["tasks"] if t["bucket"] == "analyze"), "")

    def _phase_at(ts: str) -> str:
        best = ""
        for n in plan_bound:
            if (n.get("created_at") or "") <= (ts or ""):
                best = n.get("phase", "")
            else:
                break
        return best or first_frame

    for cid in project.get("council_ids") or []:
        nid = f"council:{cid}"
        c = store.get_council_session(cid)
        if nid in seen or not c:
            continue
        seen.add(nid)
        stub = {"bucket": "act", "consumes": [_phase_at(c.get("created_at", ""))]}
        nodes.append(_evidence_node("council", cid, c.get("prompt", cid), stub, store))
    owned = {nid.split(":", 1)[1] for nid in seen if nid.startswith("council:")}
    absorbed_syntheses: list[tuple[str, list[str]]] = []
    for syn in store.list_syntheses():
        sid, nid = syn["id"], f"synthesis:{syn['id']}"
        cited = list(syn.get("council_ids") or [])
        if syn.get("scope") == "project":  # reports already ride the graph via _attach_reports
            continue
        if nid in seen or not (syn.get("project_id") == project_id
                               or (cited and all(c in owned for c in cited))):
            continue
        seen.add(nid)
        stub = {"bucket": "act", "consumes": [_phase_at(syn.get("created_at", ""))]}
        nodes.append(_evidence_node("synthesis", sid, syn.get("title", sid), stub, store))
        absorbed_syntheses.append((sid, cited))
    nodes.extend(note_graph_nodes(project))  # note nodes are first-class (composable primitive)
    nodes.sort(key=lambda n: n.get("created_at", ""))
    # edges: each verify task's synthesis consolidates its act fan's councils (refines)
    edges: list[dict[str, Any]] = []
    node_ids = {n["study_id"] for n in nodes}
    # An absorbed synthesis still declares its evidence: cited councils that are graph nodes
    # connect with the same `refines` semantics the verify-fan edges carry.
    for sid, cited in absorbed_syntheses:
        for cid in cited:
            if f"council:{cid}" in node_ids:
                edges.append({"from_study": f"council:{cid}", "to_study": f"synthesis:{sid}",
                              "type": "refines", "rationale": ""})
    for t in plan["tasks"]:
        if t["bucket"] != "verify":
            continue
        syn_refs = [r for r in t["produces"] if r["kind"] == "synthesis"]
        fan = _plan._fan_evidence(plan, t)
        for syn in syn_refs:
            for fr in fan:
                if fr["kind"] in ("council", "synthesis"):
                    edges.append({"from_study": f"{fr['kind']}:{fr['id']}",
                                  "to_study": f"synthesis:{syn['id']}", "type": "refines", "rationale": ""})
    # SPINE (GAP-6): connect each diamond's converging synthesis to the upstream diamonds' syntheses
    # that feed it, so the full double-diamond reads as ONE connected flow (Define→Select→Deliver→…)
    # rather than isolated, edge-less diamonds. Without this, a diamond whose fan is prototypes/sessions
    # (not councils) has no incoming edge and floats disconnected ("no lines").
    syn_of_verify = {t["id"]: next((r["id"] for r in t["produces"] if r["kind"] == "synthesis"), None)
                     for t in plan["tasks"] if t["bucket"] == "verify"}

    def _upstream_verifies(task_id: str, acc: set[str]) -> None:
        ct = _plan.task(plan, task_id)
        for c in (ct.get("consumes") or []) if ct else []:
            cc = _plan.task(plan, c)
            if not cc:
                continue
            if cc["bucket"] == "verify":
                acc.add(cc["id"])
            else:
                _upstream_verifies(c, acc)

    for t in plan["tasks"]:
        if t["bucket"] != "verify" or not syn_of_verify.get(t["id"]):
            continue
        ups: set[str] = set()
        _upstream_verifies(t["id"], ups)
        for up in ups:
            up_syn, this_syn = syn_of_verify.get(up), syn_of_verify[t["id"]]
            if up_syn and up_syn != this_syn and f"synthesis:{up_syn}" in node_ids:
                edges.append({"from_study": f"synthesis:{up_syn}", "to_study": f"synthesis:{this_syn}",
                              "type": "informs", "rationale": ""})
    # ONE note entity: a BUILT note (data.prototype_id) routes through its prototype (the layout draws
    # note→prototype→tested-synthesis); a plain note is a standalone observation. No concept-kind edge.
    ms = _plan_methodology_state(project, plan, store)
    if ms:
        step_tags = {s["key"]: list(s.get("tags") or []) for s in ms["steps"]}
        for n in nodes:
            extra = step_tags.get(n.get("phase", ""), [])
            if extra:
                n["theme_tags"] = list(dict.fromkeys((n.get("theme_tags") or []) + extra))
    oqs = store.list_open_questions(project["id"])
    return {
        "project": {"id": project["id"], "slug": project["slug"], "title": project["title"],
                    "goal": project.get("goal", ""), "status": project.get("status", "active"),
                    "persona_ids": project.get("persona_ids", []), "themes": project.get("themes", []),
                    "methodology": plan.get("methodology", ""), "phase": "",
                    "integrity": project.get("integrity") or plan.get("integrity") or {},
                    "product_understanding_current_id": project.get("product_understanding_current_id", ""),
                    "product_understanding_versions": project.get("product_understanding_versions") or [],
                    "supersedes_project_id": project.get("supersedes_project_id", ""),
                    "superseded_by_project_id": project.get("superseded_by_project_id", ""),
                    "lineage": project.get("lineage") or {}, "archive": project.get("archive") or {},
                    "icon": project.get("icon") or {"kind": "regular", "name": "projects"}},
        "methodology_state": ms,
        "prototypes": _protos_with_session_counts(project["id"], store),
        "artifacts": list(project.get("artifacts") or []),
        "assets": list(project.get("assets") or []),
        "sections": list(project.get("sections") or []),
        "nodes": nodes, "edges": edges, "open_questions": oqs,
        "build_order": [n["study_id"] for n in nodes],
        "counts": {"studies": len(nodes), "edges": len(edges),
                   "open_questions": sum(1 for o in oqs if o.get("status") == "open"),
                   "themes": len(project.get("themes", []))},
        "plan": plan,
    }



def derive_sections(project_id: str, store: Store | None = None) -> dict[str, Any]:
    """ESV1 — auto-organization: derive persisted SECTION overlays from the plan so a finished run is
    organized BY CONSTRUCTION (not agent-dependent). One section per methodology phase (a fan + its
    converging waist synthesis; label from the step name — no hardcoded vocabulary), a Prototype-ladder
    section, a Deliver/Conclusion section (the terminal verify synthesis), and a Run-Journal section
    (note nodes). Idempotent by title (re-run updates members). Makes assess_project.finish.organized
    flip true. (spec/exhaustive-self-verifying-runs.md §D.1)"""
    store = store or Store()
    graph = get_project_graph(project_id, store=store)
    nodes = graph["nodes"]
    steps = (graph.get("methodology_state") or {}).get("steps") or []
    by_phase: dict[str, list[str]] = {}
    for n in nodes:
        by_phase.setdefault(n.get("phase", ""), []).append(n["study_id"])
    waist_consumes = {s["key"]: s.get("consumes", []) for s in steps if not s.get("is_fan")}
    existing = {x["title"]: x for x in list_sections(project_id, store=store)}
    created: list[str] = []

    def _upsert(title: str, kind: str, members: list[str], note: str = "") -> None:
        members = [m for m in dict.fromkeys(members) if m]   # dedupe, preserve order
        if not members:
            return
        if title in existing:
            set_section_members(existing[title]["id"], members, store=store)
        else:
            create_section(project_id, title, kind=kind, member_ids=members, note=note, store=store)
            created.append(title)

    for fs in [s for s in steps if s.get("is_fan")]:
        members = list(by_phase.get(fs["key"], []))
        for wkey, cons in waist_consumes.items():
            if fs["key"] in cons:
                members += by_phase.get(wkey, [])
        label = (fs.get("name") or fs["key"]).split("·")[-1].strip() or fs["key"]
        _upsert(label, "phase", members, note=f"Phase: {label}")
    protos = [p["id"] for p in graph.get("prototypes") or []]
    _upsert("Prototypen-Leiter", "theme", protos, note="Prototypen Lo-Fi → Mid-Fi → Hi-Fi")
    verify_syns = [n["study_id"] for n in nodes
                   if n.get("bucket") == "verify" and str(n["study_id"]).startswith("synthesis:")]
    if verify_syns:
        _upsert("Deliver — Conclusion", "deliver", [verify_syns[-1]], note="Lösungspräsentation / buildbare Antwort")
    # Built notes (data.prototype_id) — the ideas that became prototypes (former "concepts").
    built_ids = [n["study_id"] for n in nodes if str(n["study_id"]).startswith("note:") and n.get("prototype_ids")]
    _upsert("Gebaute Ideen", "theme", built_ids, note="Notizen, die zu Prototypen wurden")
    journal_ids = [n["study_id"] for n in nodes if str(n["study_id"]).startswith("note:")]
    _upsert("Run-Journal", "invented", journal_ids, note="Plan-Rationale + Iterations-Journal")
    return {"project_id": project_id, "created": created,
            "sections": len(list_sections(project_id, store=store))}


def scaffold_synthesis(project_id: str, store: Store | None = None) -> dict[str, Any]:
    """ESV1 — seed a project REPORT outline from the project's phases so the conclusion hand-off is one
    author step (brief_synthesis_section → record_synthesis_section), not authored from scratch. Makes
    assess_project.finish.handed_off flip true. Idempotent: returns the existing report if one exists."""
    store = store or Store()
    existing = store.list_reports(project_id)
    if existing:
        report = existing[0]
        # ESV originally exposed its internal scaffolding note as the customer-facing cover
        # lead ("Auto-seeded outline for …"). Repair only that exact legacy placeholder;
        # authored leads are never overwritten and the report keeps its stable id/trace links.
        if str(report.get("lead") or "").startswith("Auto-seeded outline for "):
            report["lead"] = (
                "Dieser Bericht führt die Evidenz entlang der Forschungsphasen von der "
                "Ausgangsfrage bis zu den priorisierten Schlussfolgerungen zusammen."
                if content_language() == "de"
                else "This report traces the evidence through the research phases from the "
                "initial question to the prioritized conclusions."
            )
            report["updated_at"] = utc_now_iso()
            store.upsert_synthesis(report)
        return report
    graph = get_project_graph(project_id, store=store)
    nodes = graph["nodes"]
    steps = (graph.get("methodology_state") or {}).get("steps") or []
    by_phase: dict[str, list[str]] = {}
    for n in nodes:
        by_phase.setdefault(n.get("phase", ""), []).append(n["study_id"])
    # one section PER PHASE in order (fans AND verifies) — Discover/Define/Ideate/Down-Select/Refine/
    # Deliver — so the outline tells the WHOLE story, not just the diverge phases.
    sections = []
    for s in steps:
        srcs = [x for x in dict.fromkeys(by_phase.get(s["key"], [])) if x]
        label = (s.get("name") or s["key"]).split("·")[-1].strip() or s["key"]
        role = "diverge" if s.get("is_fan") else "converge"
        sections.append({"heading": label, "theme_tags": [], "source_study_ids": srcs,
                         "intent": f"Author the {label} phase ({role}) grounded in its evidence + what it produced."})
    if not sections:                                  # freeform / no methodology: one catch-all section
        sections = [{"heading": "Findings", "intent": "Author the project's findings + conclusion.",
                     "theme_tags": [], "source_study_ids": graph.get("build_order", [])}]
    outline = {"build_order_narrative": (
                   "Dieser Bericht führt die Evidenz entlang der Forschungsphasen von der "
                   "Ausgangsfrage bis zu den priorisierten Schlussfolgerungen zusammen."
                   if content_language() == "de"
                   else "This report traces the evidence through the research phases from the "
                        "initial question to the prioritized conclusions."),
               "sections": sections}
    return record_synthesis_outline(project_id, outline, store=store)


def get_research_frontier(project_id: str, store: Store | None = None) -> dict[str, Any]:
    """The anti-explosion surface: the project's still-open questions."""
    store = store or Store()
    project = _require_research_project(store, project_id)
    open_qs = [o for o in store.list_open_questions(project["id"]) if o.get("status") == "open"]
    notes = []
    if not open_qs:
        notes.append("no open questions tracked — the frontier looks closed (or unrecorded).")
    return {"project_id": project["id"], "open_questions": open_qs,
            "open_question_count": len(open_qs), "notes": notes}



# M-cleanup: backfill_project_from_syntheses RETIRED (a one-time study-graph migration).


# --- Deletes (D in CRUD; reachable from MCP/CLI and the web's structural
#     write routes — docs/web-mutations.md documents the boundary) -------------



def delete_research_project(project_id: str, store: Store | None = None) -> dict[str, Any]:
    """Delete a project container and every project-scoped artifact row.

    Personas and their memory remain global; project outputs do not.
    """
    store = store or Store()
    # Destructive references may arrive as an id or legacy slug. Resolve once to the
    # canonical id before choosing the lock, then re-read under that exact lock. Otherwise
    # delete(slug) and start_run(id) would protect different identities for the same row.
    candidate = store.get_research_project_for_active_workspace(project_id)
    if not candidate:
        raise KeyError(f"Unknown research project: {project_id}")
    canonical_id = str(candidate["id"])
    # Deletion is structural. Serialize the entire decision with start/archive/supersede.
    # A project that ever acquired a run is
    # durable research history: hard deletion would race in-flight dispatch/output writers,
    # so it must be preserved through archive_project instead. Hard delete remains available
    # only for a never-started duplicate container.
    with project_lifecycle_locks(store, [canonical_id]):
        p = store.get_research_project_for_active_workspace(canonical_id)
        if not p:
            raise KeyError(f"Unknown research project: {canonical_id}")
        runs = store._list_runs_for_active_workspace(p["id"])
        if runs:
            raise ValueError(
                "PROJECT_DELETE_RUN_HISTORY_BLOCKED: this project has governed run history; "
                "preserve it with archive_project(project_id, operation_id, reason) instead"
            )
        return {"deleted": store.delete_research_project(p["id"]), "project_id": p["id"]}



# M-cleanup: remove_study_from_project / unlink_studies RETIRED (study-edge graph).
