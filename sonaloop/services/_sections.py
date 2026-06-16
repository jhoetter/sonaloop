"""Sections — methodology-INDEPENDENT overlay groupings of graph nodes.

A Section references nodes by id (explicit, set-based, overlap allowed) and is a VIEW, never a
container: it never owns/moves/mutates nodes, and deleting it never deletes nodes. Geometry is
derived at render time. `kind` is an OPEN tag resolved for display via presentation/suggestions.
Spec: spec/sections-and-composable-graph.md. Cross-module helpers (get_project_graph,
_require_research_project, stable_id, utc_now_iso, Store) are bound into this module's globals by
the services package __init__ (same shared-namespace mechanism as the rest of the split).
"""
from __future__ import annotations

from typing import Any

from ..config import utc_now_iso
from ..models import Section
from ..storage import Store


def _valid_node_ids(project_id: str, store) -> set[str]:
    """Every node id a section may reference in this project's graph (+ prototype slugs)."""
    g = get_project_graph(project_id, store=store)  # noqa: F821 (bound by package __init__)
    ids = {n["study_id"] for n in g.get("nodes", [])}
    for p in (g.get("prototypes") or []):
        ids.add(p["id"])
        if p.get("slug"):
            ids.add(p["slug"])
    return ids


def _sections(project: dict) -> list[dict]:
    secs = project.get("sections")
    if not isinstance(secs, list):
        secs = []
        project["sections"] = secs
    return secs


def _find(store, section_id: str) -> tuple[dict, dict]:
    """Locate (project, section) by section id across projects."""
    for project in store.list_research_projects():
        for s in _sections(project):
            if s.get("id") == section_id:
                return project, s
    raise KeyError(f"Unknown section: {section_id}")


def _validate_members(project_id: str, member_ids: list[str], store) -> list[str]:
    ids = [str(m).strip() for m in (member_ids or []) if str(m).strip()]
    valid = _valid_node_ids(project_id, store)
    unknown = [m for m in ids if m not in valid]
    if unknown:
        raise ValueError(f"section member_ids not present as nodes in project {project_id}: {unknown}")
    # de-dupe, preserve order
    return list(dict.fromkeys(ids))


def create_section(project_id: str, title: str, kind: str = "theme", member_ids: list[str] | None = None,
                   parent_id: str | None = None, order: int | None = None,
                   presentation: dict[str, Any] | None = None, note: str = "",
                   store=None) -> dict[str, Any]:
    """Create a labeled overlay grouping of graph nodes. `member_ids` must reference real nodes.
    `kind` is a free tag (theme|phase|invented). A section is a view; it never owns nodes."""
    store = store or Store()  # noqa: F821
    project = _require_research_project(store, project_id)  # noqa: F821
    if not str(title).strip():
        raise ValueError("a section needs a non-empty title")
    members = _validate_members(project["id"], member_ids or [], store)
    secs = _sections(project)
    now = utc_now_iso()  # noqa: F821
    sec = Section(
        id=stable_id("section", project["id"], title, now),  # noqa: F821
        project_id=project["id"], title=str(title).strip()[:160], kind=str(kind).strip() or "theme",
        member_ids=members, parent_id=(parent_id or None),
        order=(order if order is not None else len(secs)),
        presentation=presentation or None, note=str(note or "")[:2000],
        created_at=now, updated_at=now,
    ).to_dict()
    secs.append(sec)
    project["updated_at"] = now
    store.upsert_research_project(project)
    return sec


def update_section(section_id: str, patch: dict[str, Any], store=None) -> dict[str, Any]:
    store = store or Store()  # noqa: F821
    project, sec = _find(store, section_id)
    for k in ("title", "kind", "parent_id", "note"):
        if k in patch and patch[k] is not None:
            sec[k] = str(patch[k])[:2000] if k in ("note",) else str(patch[k])[:160]
    if "order" in patch and patch["order"] is not None:
        sec["order"] = int(patch["order"])
    if "presentation" in patch:
        sec["presentation"] = patch["presentation"] or None
    if "member_ids" in patch and patch["member_ids"] is not None:
        sec["member_ids"] = _validate_members(project["id"], patch["member_ids"], store)
    sec["updated_at"] = utc_now_iso()  # noqa: F821
    project["updated_at"] = sec["updated_at"]
    store.upsert_research_project(project)
    return sec


def add_to_section(section_id: str, node_ids: list[str], store=None) -> dict[str, Any]:
    store = store or Store()  # noqa: F821
    project, sec = _find(store, section_id)
    add = _validate_members(project["id"], node_ids, store)
    sec["member_ids"] = list(dict.fromkeys(list(sec.get("member_ids", [])) + add))
    sec["updated_at"] = utc_now_iso()  # noqa: F821
    store.upsert_research_project(project)
    return sec


def remove_from_section(section_id: str, node_ids: list[str], store=None) -> dict[str, Any]:
    store = store or Store()  # noqa: F821
    project, sec = _find(store, section_id)
    drop = {str(n).strip() for n in (node_ids or [])}
    sec["member_ids"] = [m for m in sec.get("member_ids", []) if m not in drop]
    sec["updated_at"] = utc_now_iso()  # noqa: F821
    store.upsert_research_project(project)
    return sec


def set_section_members(section_id: str, node_ids: list[str], store=None) -> dict[str, Any]:
    """Bulk-set membership (the 'promote this cluster into a named section' affordance)."""
    return update_section(section_id, {"member_ids": node_ids}, store=store)


def reorder_sections(project_id: str, ordered_ids: list[str], store=None) -> dict[str, Any]:
    store = store or Store()  # noqa: F821
    project = _require_research_project(store, project_id)  # noqa: F821
    rank = {sid: i for i, sid in enumerate(ordered_ids)}
    for s in _sections(project):
        if s["id"] in rank:
            s["order"] = rank[s["id"]]
    project["updated_at"] = utc_now_iso()  # noqa: F821
    store.upsert_research_project(project)
    return {"project_id": project["id"], "sections": list_sections(project["id"], store=store)}


def list_sections(project_id: str, store=None) -> list[dict[str, Any]]:
    store = store or Store()  # noqa: F821
    project = _require_research_project(store, project_id)  # noqa: F821
    return sorted(_sections(project), key=lambda s: (s.get("order", 0), s.get("created_at", "")))


def get_section(section_id: str, store=None) -> dict[str, Any]:
    store = store or Store()  # noqa: F821
    _project, sec = _find(store, section_id)
    return sec


def delete_section(section_id: str, store=None) -> dict[str, Any]:
    """Delete the section only — its member nodes are untouched (reference, not containment)."""
    store = store or Store()  # noqa: F821
    project, sec = _find(store, section_id)
    project["sections"] = [s for s in _sections(project) if s["id"] != section_id]
    project["updated_at"] = utc_now_iso()  # noqa: F821
    store.upsert_research_project(project)
    return {"deleted": section_id, "nodes_kept": len(sec.get("member_ids", []))}


# --------------------------------------------------------------- Note nodes (composable primitive)
# A `note` is a lightweight, first-class observation node creatable WITHOUT any methodology — the
# atomic unit for affinity work. It appears in the graph (study_id "note:<id>") and can be grouped
# into sections and linked by edges, just like any other node.

def _notes(project: dict) -> list[dict]:
    ns = project.get("notes")
    if not isinstance(ns, list):
        ns = []
        project["notes"] = ns
    return ns


def note_form(note: dict[str, Any]) -> str:
    """Classify a note through the primitive form registry.

    `kind` may carry authored lightweight forms such as `idea` or `insight`.
    Prototype/artifact linkage in `data` upgrades the row to a `concept`; all
    other rows are observations.
    """
    from .. import primitive_taxonomy_registry as _taxonomy_registry

    data = note.get("data") or {}
    if data.get("prototype_id") or data.get("prototype_ids") or data.get("artifact_kind"):
        alias = "concept_note"
    else:
        raw = str(note.get("kind") or "note").strip().lower()
        alias = {"idea": "idea", "insight": "insight", "concept": "concept_note",
                 "observation": "observation_note", "note": "observation_note"}.get(raw, raw)
    form = _taxonomy_registry.resolve_form("note", alias)
    return str((form or {}).get("id") or alias)


def note_form_definition(note: dict[str, Any]) -> dict[str, Any]:
    from .. import primitive_taxonomy_registry as _taxonomy_registry

    form_id = note_form(note)
    form = _taxonomy_registry.resolve_form("note", form_id)
    if form is None:
        raise KeyError(f"No registered note form '{form_id}'")
    return form


def create_note(project_id: str, text: str, title: str = "", kind: str = "note",
                data: dict[str, Any] | None = None, created_at: str | None = None, store=None) -> dict[str, Any]:
    """Create a lightweight note node in the project graph (no methodology required) — the ONE note
    entity (the former 'concept' is merged in). A note that gets BUILT carries structured `data`
    {lens, artifact_kind, prototype_ids:[...]} so the layout pairs it with its prototype(s) + the
    completeness critic can reason over the solution space. `kind` is normalized to 'note'. `data` is a
    small free dict (capped). `created_at` overrides the timestamp (e.g. seeding a real timeline)."""
    store = store or Store()  # noqa: F821
    project = _require_research_project(store, project_id)  # noqa: F821
    if not str(text).strip():
        raise ValueError("a note needs non-empty text")
    kind = "note" if (str(kind or "note").strip().lower() in ("note", "concept")) else str(kind).strip()[:40]
    now = created_at or utc_now_iso()  # noqa: F821
    note = {"id": stable_id("note", project["id"], text, now),  # noqa: F821
            "title": (str(title).strip() or str(text).strip()[:60])[:120],
            "text": str(text).strip()[:2000], "kind": kind,
            "data": dict(list((data or {}).items())[:20]), "created_at": now}
    _notes(project).append(note)
    project["updated_at"] = now
    store.upsert_research_project(project)
    return note


def update_note(note_id: str, patch: dict[str, Any], store=None) -> dict[str, Any]:
    """Patch a note's authored fields (title/text). Structured `data` keeps its own
    path (set_note_data); `kind` stays as recorded. Same caps as create_note."""
    store = store or Store()  # noqa: F821
    for project in store.list_research_projects():
        for n in _notes(project):
            if n.get("id") == note_id:
                if "text" in patch and patch["text"] is not None:
                    text = str(patch["text"]).strip()
                    if not text:
                        raise ValueError("a note needs non-empty text")
                    n["text"] = text[:2000]
                if "title" in patch and patch["title"] is not None:
                    n["title"] = (str(patch["title"]).strip() or n["text"][:60])[:120]
                project["updated_at"] = utc_now_iso()  # noqa: F821
                store.upsert_research_project(project)
                return n
    raise KeyError(f"Unknown note: {note_id}")


def set_note_data(note_id: str, patch: dict[str, Any], store=None) -> dict[str, Any]:
    """Merge keys into a note's `data` (e.g. set a concept note's prototype_id once built), so the
    completeness critic stops flagging that concept as un-prototyped (ESV/OD-3)."""
    store = store or Store()  # noqa: F821
    for project in store.list_research_projects():  # noqa: F821
        for n in _notes(project):
            if n.get("id") == note_id:
                n["data"] = {**(n.get("data") or {}), **dict(list((patch or {}).items())[:20])}
                project["updated_at"] = utc_now_iso()  # noqa: F821
                store.upsert_research_project(project)
                return n
    raise KeyError(f"Unknown note: {note_id}")


def list_notes(project_id: str, store=None) -> list[dict[str, Any]]:
    store = store or Store()  # noqa: F821
    return list(_notes(_require_research_project(store, project_id)))  # noqa: F821


def get_note(note_id: str, store=None) -> dict[str, Any]:
    """Find a note (+ its project) by id across projects, for rendering/inspection."""
    store = store or Store()  # noqa: F821
    for project in store.list_research_projects():
        for n in _notes(project):
            if n.get("id") == note_id:
                return {"note": n, "project": {"id": project["id"], "slug": project["slug"], "title": project["title"]}}
    raise KeyError(f"Unknown note: {note_id}")


def delete_note(project_id: str, note_id: str, store=None) -> dict[str, Any]:
    store = store or Store()  # noqa: F821
    project = _require_research_project(store, project_id)  # noqa: F821
    project["notes"] = [n for n in _notes(project) if n["id"] != note_id]
    project["updated_at"] = utc_now_iso()  # noqa: F821
    store.upsert_research_project(project)
    return {"deleted": note_id}


def section_members(section_id: str, store=None) -> dict[str, Any]:
    """Resolve a section's member node ids into {kind,title,summary,href} records (a section-scoped
    view over the graph)."""
    store = store or Store()  # noqa: F821
    project, sec = _find(store, section_id)
    notes = {n["id"]: n for n in _notes(project)}
    out = []
    for mid in sec.get("member_ids", []):
        if mid.startswith("council:"):
            c = store.get_council_session(mid.split(":", 1)[1]) or {}
            out.append({"id": mid, "kind": "council", "title": c.get("prompt", mid),
                        "summary": c.get("exec_summary") or c.get("summary", ""), "href": f"/councils/{mid.split(':',1)[1]}"})
        elif mid.startswith("synthesis:"):
            syn = store.get_synthesis(mid.split(":", 1)[1]) or {}
            out.append({"id": mid, "kind": "synthesis", "title": syn.get("title", mid),
                        "summary": syn.get("gesamtbild") or syn.get("positionierung", ""), "href": f"/syntheses/{mid.split(':',1)[1]}"})
        elif mid.startswith("note:"):
            nnid = mid.split(":", 1)[1]
            n = notes.get(nnid, {})
            out.append({"id": mid, "kind": "note", "title": n.get("title", mid),
                        "summary": n.get("text", ""), "href": f"/notes/{nnid}"})
        else:
            pr = store.get_prototype(mid) or {}
            out.append({"id": mid, "kind": "prototype", "title": pr.get("name", mid),
                        "summary": pr.get("notes", ""), "href": f"/prototypes/{pr.get('slug', mid)}"})
    return {"section": sec, "project": {"id": project["id"], "slug": project["slug"], "title": project["title"]},
            "members": out}


def export_section(section_id: str, format: str = "md", store=None):
    """A SELF-CONTAINED export of a section (md|json) — its title + every member node's summary,
    to hand to a downstream agent (mirrors export_synthesis)."""
    data = section_members(section_id, store=store)
    sec, members = data["section"], data["members"]
    if format == "json":
        return data
    lines = [f"# Section · {sec['title']}",
             f"_{sec.get('kind','theme')} · {len(members)} Knoten · Projekt: {data['project']['title']}_", ""]
    if sec.get("note"):
        lines += [sec["note"], ""]
    for m in members:
        lines += [f"## {m['title']}", f"*{m['kind']}*", "", (m["summary"] or "—"), ""]
    return "\n".join(lines)


def note_graph_nodes(project: dict) -> list[dict[str, Any]]:
    """Graph node dicts for a project's notes (study_id 'note:<id>', kind 'note'). Used by the
    graph builders so notes are first-class nodes (section members / edge endpoints)."""
    from .. import presentation as _pres
    pres = _pres.present("note")
    out = []
    for n in _notes(project):
        title = n.get("title") or n.get("text", "")[:60]
        data = n.get("data") or {}
        # ONE note entity (concepts merged in): a note that was BUILT links to its prototype(s) — a concept
        # can become several fidelity versions, so this is a LIST (data.prototype_ids, or a single
        # prototype_id). That note→prototype(s) pairing is the only former "concept" behaviour that remains.
        proto_ids = list(data.get("prototype_ids") or ([data["prototype_id"]] if data.get("prototype_id") else []))
        out.append({"study_id": f"note:{n['id']}", "kind": "note", "note_kind": "note",
                    "prototype_ids": proto_ids, "lens": data.get("lens", ""),
                    "artifact_kind": data.get("artifact_kind", ""),
                    "title": title, "phase": "", "bucket": "", "created_at": n.get("created_at", ""),
                    "council_count": 0, "voices": 0, "sentiment": {}, "recommendations": 0, "role": "", "mode": "",
                    "theme_tags": ["note"], "color": pres["color"], "kind_label": pres["label"],
                    "href": f"/notes/{n['id']}"})
    return out
