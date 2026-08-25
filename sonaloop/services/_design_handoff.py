"""Provider-neutral research-to-design hand-off for MCP hosts.

The hand-off is a bounded, read-only projection of evidence Sonaloop already owns.
It does not call Figma (or any other destination), invent design requirements, or
copy local filesystem paths.  A host with another design/canvas/code MCP can consume
the bundle and perform the destination-specific writes itself.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any

from ..storage import Store
from ._common import _require_research_project
from ._substrate import _guard


DESIGN_HANDOFF_SCHEMA = "sonaloop.design_handoff.v1"


def _clip(value: Any, limit: int = 1800) -> str:
    text = str(value or "").strip()
    return text if len(text) <= limit else text[:limit - 1].rstrip() + "…"


def _bounded(value: Any, *, depth: int = 0) -> Any:
    """Keep authored concept/session data useful without creating an unbounded MCP result."""
    if depth > 4:
        return None
    if isinstance(value, str):
        return _clip(value, 1200)
    if isinstance(value, list):
        return [_bounded(item, depth=depth + 1) for item in value[:24]]
    if isinstance(value, dict):
        return {str(key)[:80]: _bounded(item, depth=depth + 1)
                for key, item in list(value.items())[:30]}
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return _clip(value, 500)


def _ref(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    return {key: _clip(raw.get(key), 500) for key in (
        "kind", "id", "anchor", "role", "quote") if raw.get(key) not in (None, "")}


def _persona(persona: dict[str, Any]) -> dict[str, Any]:
    role = persona.get("role") or {}
    segment = persona.get("segment") or {}
    avatar_available = bool((persona.get("avatar") or {}).get("path"))
    return {
        "id": persona.get("id", ""),
        "display_name": persona.get("display_name", ""),
        "age_range": (persona.get("identity_traits") or {}).get("age_range", ""),
        "role": {key: _clip(role.get(key), 500) for key in ("title", "responsibilities")
                 if role.get(key)},
        "segment": {str(key): _clip(value, 300) for key, value in list(segment.items())[:20]
                    if value not in (None, "")},
        "avatar": ({
            "available": True,
            "access": {"tool": "view_persona_avatar", "arguments": {
                "persona_id": persona.get("id", ""),
            }},
        } if avatar_available else {"available": False}),
    }


def _finding(raw: dict[str, Any], synthesis: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(raw.get("id") or ""),
        "kind": str(raw.get("kind") or "finding"),
        "text": _clip(raw.get("text"), 1800),
        "score": _bounded(raw.get("score")),
        "refs": [ref for ref in (_ref(row) for row in (raw.get("refs") or [])[:12]) if ref],
        "meta": _bounded(raw.get("meta") or {}),
        "claim_posture": _bounded(raw.get("claim_posture") or {}),
        "source_synthesis": {
            "id": synthesis.get("id", ""), "title": synthesis.get("title", ""),
        },
    }


def _voice(raw: dict[str, Any], synthesis: dict[str, Any], store: Store) -> dict[str, Any]:
    persona = store.get_persona(str(raw.get("persona_id") or "")) or {}
    meta = raw.get("meta") or {}
    return {
        "id": str(raw.get("id") or ""),
        "persona_id": raw.get("persona_id", ""),
        "persona_name": meta.get("persona_name") or persona.get("display_name", ""),
        "segment": meta.get("segment") or (persona.get("segment") or {}),
        "text": _clip(raw.get("text"), 1800),
        "stance": _bounded(raw.get("stance") or {}),
        "relevance": _bounded(raw.get("relevance")),
        "refs": [ref for ref in (_ref(row) for row in (raw.get("refs") or [])[:12]) if ref],
        "source_synthesis": {
            "id": synthesis.get("id", ""), "title": synthesis.get("title", ""),
        },
    }


def _design_system_context() -> dict[str, Any]:
    from ..theming import active_runtime_design_system_context, runtime_design_system_context

    ctx = active_runtime_design_system_context() or runtime_design_system_context(surface="handoff")
    ds = ctx.get("design_system") or {}
    typography = ds.get("typography") or {}
    return {
        "source": "workspace" if ctx.get("workspace_id") else "default",
        "revision": {key: ctx.get(key, "") for key in (
            "workspace_id", "version_id", "compiled_hash", "spec_version") if ctx.get(key)},
        "brand": _bounded(ctx.get("brand") or {}),
        "tokens": {
            "colors": _bounded((ds.get("colors") or {}).get("light") or {}),
            "typography": _bounded({
                "fonts": typography.get("fonts") or {},
                "type_scale": typography.get("type_scale") or {},
            }),
            "layout": _bounded(ds.get("layout") or {}),
            "charts": _bounded(ds.get("charts") or {}),
        },
        "deck": _bounded({
            "master_asset_ref": (ds.get("deck") or {}).get("master_asset_ref") or "",
            "font_role": (ds.get("deck") or {}).get("font_role") or "",
        }),
    }


def _project_syntheses(project: dict[str, Any], graph: dict[str, Any], store: Store
                        ) -> list[dict[str, Any]]:
    ids: list[str] = []
    for node in graph.get("nodes") or []:
        if str(node.get("kind") or "") != "synthesis":
            continue
        raw = str(node.get("study_id") or "")
        sid = raw.split(":", 1)[1] if raw.startswith("synthesis:") else raw
        if sid and sid not in ids:
            ids.append(sid)
    for sid in project.get("study_ids") or []:
        if sid not in ids:
            ids.append(sid)
    for synthesis in store.list_syntheses():
        if synthesis.get("project_id") == project["id"] and synthesis["id"] not in ids:
            ids.append(synthesis["id"])
    rows = [row for row in (store.get_synthesis(sid) for sid in ids) if row]
    return sorted(rows, key=lambda row: (row.get("created_at", ""), row["id"]), reverse=True)


def _report_row(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": report.get("id", ""),
        "title": report.get("title", ""),
        "status": report.get("status", ""),
        "lead": _clip(report.get("lead"), 2500),
        "sections": [{
            "id": section.get("id", ""),
            "heading": section.get("heading", ""),
            "markdown": _clip(section.get("markdown"), 3500),
            "source_study_ids": list(section.get("source_study_ids") or [])[:20],
            "citations": _bounded(section.get("citations") or []),
            "figures": _bounded(section.get("figures") or []),
        } for section in (report.get("sections") or [])[:10]],
        # This is the same reviewed, format-neutral decision story used by the
        # stakeholder PDF and native PowerPoint export. Destination MCPs can use
        # it as frames/pages without reverse-engineering internal report phases.
        "delivery_story": _bounded(report.get("presentation_plan") or {}),
    }


def _plan_refs(slide: dict[str, Any]) -> list[dict[str, Any]]:
    return [{"kind": "evidence", "id": _clip(value, 500)}
            for value in (slide.get("evidence_refs") or [])[:12] if _clip(value, 500)]


def _delivery_findings(report: dict[str, Any]) -> list[dict[str, Any]]:
    """Project a reviewed delivery story into design-ready findings.

    Some governed reports predate the structured findings layer. A reviewed
    presentation plan still carries explicit evidence refs and must not become an
    empty Figma/code hand-off merely because its source report used legacy prose.
    """
    plan = report.get("presentation_plan") or {}
    out = []
    for slide in plan.get("slides") or []:
        if slide.get("kind") in {"cover", "agenda", "section", "closing"}:
            continue
        refs = _plan_refs(slide)
        if not refs:
            continue
        out.append({
            "id": f"delivery:{slide.get('id') or len(out) + 1}",
            "kind": str(slide.get("kind") or "finding"),
            "text": _clip(slide.get("headline"), 1800),
            "score": None,
            "refs": refs,
            "meta": {"delivery_slide_id": slide.get("id", ""),
                     "details": _bounded({key: slide.get(key) for key in (
                         "decision", "metrics", "rationale", "before", "after", "why", "steps"
                     ) if slide.get(key) not in (None, [], {})})},
            "claim_posture": {"posture": "evidence_linked_delivery_conclusion"},
            "source_synthesis": {"id": report.get("id", ""),
                                 "title": report.get("title", "")},
        })
    return out


def _delivery_voices(report: dict[str, Any], store: Store) -> list[dict[str, Any]]:
    out = []
    for slide in list((report.get("presentation_plan") or {}).get("slides") or []) + list(
            (report.get("presentation_plan") or {}).get("appendix") or []):
        rows = []
        if slide.get("kind") in {"persona_grid", "persona_detail"}:
            rows = list(slide.get("items") or [])
        elif slide.get("kind") == "preference_shift":
            rows = list(slide.get("switchers") or [])
        for row in rows:
            if not isinstance(row, dict):
                continue
            text = _clip(row.get("quote") or row.get("reason"), 1800)
            persona_id = str(row.get("persona_id") or row.get("id") or "")
            if not text or not persona_id:
                continue
            persona = store.get_persona(persona_id) or {}
            out.append({
                "id": f"delivery:{slide.get('id')}:{persona_id}",
                "persona_id": persona_id,
                "persona_name": persona.get("display_name", persona_id),
                "segment": _bounded(persona.get("segment") or {}),
                "text": text,
                "stance": {}, "relevance": None,
                "refs": _plan_refs(slide),
                "source_synthesis": {"id": report.get("id", ""),
                                     "title": report.get("title", "")},
            })
    return out


def _proposed_revisions(report: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for slide in (report.get("presentation_plan") or {}).get("slides") or []:
        if slide.get("kind") != "revision_mockup":
            continue
        rows.append({
            "id": str(slide.get("id") or ""),
            "headline": _clip(slide.get("headline"), 500),
            "current_asset_id": str(slide.get("asset_id") or slide.get("image_ref") or ""),
            "proposal": _bounded(slide.get("proposal") or {}),
            "rationale": _bounded(slide.get("why") or []),
            "refs": _plan_refs(slide),
        })
    return rows


def get_design_handoff(project_id: str, synthesis_id: str | None = None,
                       prototype_id: str | None = None, max_findings: int = 30,
                       max_voices: int = 24, store: Store | None = None) -> dict[str, Any]:
    """Build a bounded, provider-neutral design brief from one project's evidence.

    ``synthesis_id`` narrows the research result; ``prototype_id`` narrows existing
    design artifacts.  Neither option performs a destination write.
    """
    store = store or Store()
    project = _require_research_project(store, project_id)
    _guard("get_design_handoff", {"project_id": project["id"],
                                   "synthesis_id": synthesis_id,
                                   "prototype_id": prototype_id})
    max_findings = max(1, min(60, int(max_findings)))
    max_voices = max(1, min(48, int(max_voices)))
    graph = get_project_graph(project["id"], store=store)  # noqa: F821 (bound)
    syntheses = _project_syntheses(project, graph, store)
    reports = list(store.list_reports(project["id"]))
    allowed = {row["id"] for row in syntheses + reports}
    if synthesis_id and synthesis_id not in allowed:
        raise KeyError(f"Synthesis {synthesis_id!r} does not belong to project {project['id']}")
    if synthesis_id:
        selected = [row for row in syntheses
                    if row["id"] == synthesis_id and row.get("scope") != "project"]
        selected_reports = [row for row in reports if row["id"] == synthesis_id]
    else:
        selected = [row for row in syntheses if row.get("scope") != "project"][:8]
        selected_reports = reports[:1]

    findings: list[dict[str, Any]] = []
    voices: list[dict[str, Any]] = []
    seen_findings: set[tuple[str, str]] = set()
    seen_voices: set[tuple[str, str]] = set()
    for synthesis in selected + selected_reports:
        for raw in synthesis.get("findings") or []:
            key = (str(raw.get("kind") or ""), str(raw.get("text") or ""))
            if key in seen_findings or len(findings) >= max_findings:
                continue
            seen_findings.add(key)
            findings.append(_finding(raw, synthesis))
        for raw in synthesis.get("statements") or []:
            key = (str(raw.get("persona_id") or ""), str(raw.get("text") or ""))
            if key in seen_voices or len(voices) >= max_voices:
                continue
            seen_voices.add(key)
            voices.append(_voice(raw, synthesis, store))
    if selected_reports:
        for row in _delivery_findings(selected_reports[0]):
            key = (row["kind"], row["text"])
            if key not in seen_findings and len(findings) < max_findings:
                seen_findings.add(key)
                findings.append(row)
        for row in _delivery_voices(selected_reports[0], store):
            key = (row["persona_id"], row["text"])
            if key not in seen_voices and len(voices) < max_voices:
                seen_voices.add(key)
                voices.append(row)
    grouped: dict[str, list[str]] = defaultdict(list)
    for row in findings:
        grouped[row["kind"]].append(row["id"])

    prototypes = list_prototypes_artifacts(project["id"], store=store)  # noqa: F821 (bound)
    if prototype_id:
        prototypes = [row for row in prototypes
                      if prototype_id in {row.get("id"), row.get("slug")}]
        if not prototypes:
            raise KeyError(f"Prototype {prototype_id!r} does not belong to project {project['id']}")
    prototype_ids = {str(row.get("id") or "") for row in prototypes}
    concepts = []
    for note in list_notes(project["id"], store=store):  # noqa: F821 (bound)
        data = note.get("data") or {}
        linked = {str(data.get("prototype_id") or ""),
                  *(str(value) for value in (data.get("prototype_ids") or []))}
        if (data.get("artifact_kind") or data.get("concept") or data.get("screens")
                or data.get("frames") or prototype_ids.intersection(linked)):
            concepts.append({
                "id": note.get("id", ""), "title": note.get("title", ""),
                "text": _clip(note.get("text"), 1800), "kind": note.get("kind", "note"),
                "data": _bounded(data),
            })

    assets = []
    for asset in list_assets(project["id"], store=store)[:30]:  # noqa: F821 (bound)
        tool = "view_asset" if asset.get("kind") in {"image", "screenshot"} else "get_asset"
        assets.append({
            key: asset.get(key) for key in (
                "id", "title", "filename", "kind", "media_type", "direction", "notes", "source")
            if asset.get(key) not in (None, "")
        } | {"access": {"tool": tool, "arguments": {
            "project_id": project["id"], "asset_id": asset["id"],
        }}})

    flows = []
    for flow in list_flows(project["id"], store=store)[:12]:  # noqa: F821 (bound)
        detail = get_flow(project["id"], flow["id"], store=store)  # noqa: F821 (bound)
        flows.append({
            "id": detail["id"], "title": detail["title"],
            "steps": [{"index": step.get("index"), "asset_id": step.get("asset_id"),
                       "caption": _clip(step.get("caption"), 500)}
                      for step in (detail.get("steps") or [])[:30]],
        })

    sessions = []
    for session in list_usability_sessions(project_id=project["id"], store=store)[:20]:  # noqa: F821 (bound)
        sessions.append({
            "id": session.get("id", ""), "persona_id": session.get("persona_id", ""),
            "subject": _bounded(session.get("subject") or {}),
            "fidelity": session.get("fidelity", ""),
            "outcome": _bounded(session.get("outcome") or {}),
            "steps": [{
                "index": step.get("index"),
                "action": _bounded(step.get("action") or {}),
                "screen": _clip((step.get("state") or {}).get("screen"), 800),
                "friction": _bounded(step.get("friction") or {}),
                "verdict": _bounded(step.get("verdict") or {}),
            } for step in (session.get("steps") or [])[:30]],
        })

    cohort = [_persona(persona) for persona in
              (store.get_persona(pid) for pid in project.get("persona_ids") or []) if persona]
    decisions = [{
        "id": row.get("id", ""), "title": row.get("title", ""),
        "decision": _clip(row.get("decision"), 1800), "status": row.get("status", ""),
        "based_on": [_ref(ref) for ref in (row.get("based_on") or [])[:20]],
        "rejected": [_bounded(ref) for ref in (row.get("rejected") or [])[:20]],
    } for row in list_decisions(project["id"], store=store)[:20]]  # noqa: F821 (bound)

    source_rows = list({row["id"]: row for row in selected + selected_reports}.values())
    return {
        "schema": DESIGN_HANDOFF_SCHEMA,
        "provider_neutral": True,
        "project": {
            "id": project["id"], "title": project.get("title", ""),
            "goal": project.get("goal", ""), "description": project.get("description", ""),
            "methodology": project.get("methodology", ""),
        },
        "source_results": [{
            "id": row.get("id", ""), "title": row.get("title", ""),
            "scope": row.get("scope", "convergence"), "status": row.get("status", ""),
            "goal": row.get("goal", ""), "summary": _clip(row.get("gesamtbild"), 2500),
            "positioning": _clip(row.get("positionierung"), 2500),
        } for row in source_rows],
        "report": _report_row(selected_reports[0]) if selected_reports else None,
        "cohort": cohort,
        "research": {
            "findings": findings,
            "finding_groups": dict(sorted(grouped.items())),
            "voices": voices,
            "open_questions": _bounded(graph.get("open_questions") or []),
            "predictions": _bounded(aggregate_predictions(project["id"], store=store)),  # noqa: F821 (bound)
            "decisions": decisions,
            "proposed_revisions": _proposed_revisions(selected_reports[0])
            if selected_reports else [],
        },
        "design_context": _design_system_context(),
        "existing_design": {
            "concepts": concepts[:16],
            "prototypes": [{
                "id": row.get("id", ""), "slug": row.get("slug", ""),
                "name": row.get("name", ""), "version": row.get("version", ""),
                "type": row.get("type", "prototype"), "tags": row.get("tags") or [],
                "fidelity": row.get("fidelity", ""), "notes": _clip(row.get("notes"), 1000),
                "url": row.get("url", ""),
            } for row in prototypes[:16]],
            "flows": flows, "assets": assets, "usability_sessions": sessions,
        },
        "destination_contract": {
            "compatible_targets": ["design MCP", "canvas MCP", "code MCP", "document MCP"],
            "sequence": [
                "Read the research and preserve every evidence reference.",
                "Use report.delivery_story as the approved frame/page sequence when it is present.",
                "Fetch only the visual assets needed via each asset's access tool call.",
                "Fetch persona portraits only when the destination needs them, using cohort[].avatar.access.",
                "Create or update the artifact with the destination MCP selected by the user.",
                "Keep unresolved questions visible; do not turn hypotheses into observed facts.",
                "If the result has a shareable interactive URL, register it back in Sonaloop and test it with personas.",
            ],
            "register_interactive_result": {
                "tool": "register_remote_prototype",
                "arguments": {"slug": "<stable-slug>", "name": "<artifact-name>",
                              "url": "<destination-share-or-prototype-url>",
                              "project_id": project["id"], "fidelity": "hifi",
                              "notes": "Created from sonaloop.design_handoff.v1"},
            },
            "suggested_agent_request": (
                "Create or update the requested design in the connected destination tool from this "
                "Sonaloop hand-off. Preserve the workspace design tokens, cite the supplied research "
                "refs in your rationale, distinguish evidence from hypotheses, and report what you "
                "created plus any unresolved design decisions."
            ),
        },
    }
