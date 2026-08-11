"""Resolve typed project-graph refs into report-authoring source material."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from .. import artifacts as _A
from ..storage import Store


def _source_record(store: Store, source_id: str) -> tuple[str, str, dict[str, Any]]:
    raw = str(source_id or "")
    kind, rid = raw.split(":", 1) if ":" in raw else ("", raw)
    if kind == "council":
        return kind, rid, store.get_council_session(rid) or {}
    if kind in {"synthesis", "report"}:
        return kind, rid, store.get_synthesis(rid) or {}
    if kind == "note":
        for project in store.list_research_projects():
            note = next((row for row in (project.get("notes") or [])
                         if str(row.get("id") or "") == rid), None)
            if note:
                return kind, rid, note
        return kind, rid, {}
    # A typed graph ref is authoritative. Never reinterpret an unknown or
    # unsupported type as a synthesis/council with a coincidentally equal id.
    if kind:
        return kind, rid, {}
    # Backward compatibility for report outlines recorded before graph refs were
    # typed. Only genuinely bare ids may use the historical lookup order.
    synthesis = store.get_synthesis(rid)
    if synthesis:
        return "synthesis", rid, synthesis
    council = store.get_council_session(rid)
    return ("council", rid, council) if council else (kind, rid, {})


def report_source_compact(store: Store, source_id: str, tags: list[str]) -> dict[str, Any]:
    kind, _rid, record = _source_record(store, source_id)
    if kind == "note":
        return {
            "study_id": source_id, "kind": kind,
            "title": record.get("title", source_id), "goal": "",
            "theme_tags": tags, "gesamtbild": record.get("text", ""),
            "positionierung": "", "top_recommendations": [],
            "created_at": record.get("created_at", ""), "source_data": record.get("data", {}),
            "missing": not bool(record),
        }
    if kind == "council":
        return {
            "study_id": source_id, "kind": kind,
            "title": record.get("prompt", source_id), "goal": record.get("prompt", ""),
            "theme_tags": tags, "gesamtbild": record.get("exec_summary") or record.get("summary", ""),
            "positionierung": record.get("proposal", ""), "top_recommendations": [],
            "created_at": record.get("created_at", ""), "missing": not bool(record),
        }
    return {
        "study_id": source_id, "kind": kind or "synthesis",
        "title": record.get("title", source_id), "goal": record.get("goal", ""),
        "theme_tags": tags, "gesamtbild": record.get("gesamtbild", ""),
        "positionierung": record.get("positionierung", ""),
        "top_recommendations": [text for text, _effort, _value
                                in _A.synthesis_recommendations(record)[:3]],
        "created_at": record.get("created_at", ""), "missing": not bool(record),
    }


def report_source_full(store: Store, source_id: str) -> dict[str, Any]:
    kind, rid, record = _source_record(store, source_id)
    if kind == "note":
        return {
            "study_id": source_id, "kind": kind, "title": record.get("title", source_id),
            "goal": "", "arc_narrative": "", "gesamtbild": record.get("text", ""),
            "positionierung": "", "pain_solvers": [], "handlungsempfehlungen": [],
            "voices": [], "offene_fragen": [], "councils": [],
            "source_data": record.get("data", {}), "missing": not bool(record),
        }
    if kind == "council":
        voices = [{
            "persona_id": statement.get("persona_id"),
            "sentiment": _A._STANCE_SENTIMENT.get(
                (statement.get("stance") or {}).get("value"), "neutral"),
            "key_argument": statement.get("text"),
        } for statement in _A.council_statements(record)]
        summary = record.get("exec_summary") or record.get("summary", "")
        return {
            "study_id": source_id, "kind": kind, "title": record.get("prompt", source_id),
            "goal": record.get("prompt", ""), "arc_narrative": record.get("summary", ""),
            "gesamtbild": summary, "positionierung": record.get("proposal", ""),
            "pain_solvers": [], "handlungsempfehlungen": [], "voices": voices,
            "offene_fragen": list(record.get("questions") or []),
            "councils": [{"council_id": rid, "prompt": record.get("prompt", ""),
                          "exec_summary": summary}], "missing": not bool(record),
        }
    councils = []
    for council_id in record.get("council_ids") or []:
        council = store.get_council_session(council_id) or {}
        councils.append({"council_id": council_id, "prompt": council.get("prompt", ""),
                         "exec_summary": council.get("exec_summary", "")})
    return {
        "study_id": source_id, "kind": kind or "synthesis",
        "title": record.get("title", source_id), "goal": record.get("goal", ""),
        "arc_narrative": record.get("arc_narrative", ""), "gesamtbild": record.get("gesamtbild", ""),
        "positionierung": record.get("positionierung", ""),
        "pain_solvers": _A.finding_texts(record, "pain_solver"),
        "handlungsempfehlungen": [{"text": text, "aufwand": effort, "nutzen": value}
                                  for text, effort, value in _A.synthesis_recommendations(record)],
        "voices": [{"persona_id": voice.get("persona_id"),
                    "sentiment": _A._STANCE_SENTIMENT.get(
                        (voice.get("stance") or {}).get("value"), "neutral"),
                    "key_argument": voice.get("text")}
                   for voice in _A.synthesis_statements(record)],
        "offene_fragen": _A.finding_texts(record, "open_question"), "councils": councils,
        "missing": not bool(record),
    }


_PRESERVE_TEXT_KEYS = {"study_id", "council_id", "persona_id", "report_id", "kind"}


def _payload_chars(value: Any) -> int:
    """Measure the pretty JSON embedded verbatim in authoring prompts."""
    return len(json.dumps(value, indent=2, ensure_ascii=False, default=str))


def _structure_fields(value: Any) -> int:
    if isinstance(value, dict):
        return len(value) + sum(_structure_fields(child) for child in value.values())
    if isinstance(value, list):
        return sum(_structure_fields(child) for child in value)
    return 0


def _clip_source_value(value: Any, *, text_limit: int, list_limit: int,
                       key: str = "") -> tuple[Any, int, int]:
    """Bound prose/list payloads while keeping ids exact and reporting every omission."""
    if isinstance(value, dict):
        clipped: dict[str, Any] = {}
        truncated_chars = omitted_items = 0
        for child_key, child_value in value.items():
            child, chars, items = _clip_source_value(
                child_value, text_limit=text_limit, list_limit=list_limit, key=str(child_key))
            clipped[child_key] = child
            truncated_chars += chars
            omitted_items += items
        return clipped, truncated_chars, omitted_items
    if isinstance(value, list):
        clipped_items = []
        truncated_chars = 0
        omitted_items = max(0, len(value) - list_limit)
        for item in value[:list_limit]:
            child, chars, items = _clip_source_value(
                item, text_limit=text_limit, list_limit=list_limit)
            clipped_items.append(child)
            truncated_chars += chars
            omitted_items += items
        return clipped_items, truncated_chars, omitted_items
    if isinstance(value, str) and key not in _PRESERVE_TEXT_KEYS and not key.endswith("_id"):
        if len(value) > text_limit:
            omitted = len(value) - text_limit
            return f"{value[:text_limit]}… [truncated {omitted} chars]", omitted, 0
    return value, 0, 0


def bound_report_sources(studies: list[dict[str, Any]], max_chars: int = 24_000,
                         pinned_source_ids: list[str] | None = None
                         ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Keep the section authoring frame comfortably below the MCP output ceiling.

    The frame is returned twice to MCP clients (structured data and inside the
    authoring prompt), so the source slice receives a conservative 24k budget.
    Truncation is explicit in-band; source ids are never clipped or retyped.
    """
    pinned = {str(value) for value in (pinned_source_ids or []) if str(value)}
    original_chars = _payload_chars(studies)
    if original_chars <= max_chars:
        return studies, {
            "limit_chars": max_chars, "original_chars": original_chars,
            "returned_chars": original_chars, "truncated": False,
            "truncated_chars": 0, "omitted_serialized_chars": 0,
            "omitted_items": 0, "omitted_fields": 0, "omitted_sources": 0,
        }

    best: tuple[list[dict[str, Any]], int, int] | None = None
    for text_limit, list_limit in ((4000, 16), (2000, 12), (1000, 8), (500, 6),
                                   (250, 4), (120, 3), (80, 2)):
        candidate = []
        chars = items = 0
        for study in studies:
            clipped, source_chars, source_items = _clip_source_value(
                study, text_limit=text_limit, list_limit=list_limit)
            candidate.append(clipped)
            chars += source_chars
            items += source_items
        best = candidate, chars, items
        if _payload_chars(candidate) <= max_chars:
            break

    assert best is not None
    bounded, truncated_chars, omitted_items = best
    omitted_fields = 0
    omitted_sources = 0
    returned_chars = _payload_chars(bounded)
    if returned_chars > max_chars:
        # Pathological sections may name hundreds of sources. Preserve as many
        # typed identities as fit, and describe the remainder rather than
        # silently overflowing or fabricating absence.
        skeletons = [{
            "study_id": row.get("study_id", ""), "kind": row.get("kind", ""),
            "title": str(row.get("title") or row.get("study_id") or "")[:80],
            "missing": bool(row.get("missing")),
        } for row in bounded]
        omitted_fields = max(0, _structure_fields(bounded) - _structure_fields(skeletons))
        selected = {index for index, row in enumerate(skeletons)
                    if str(row.get("study_id") or "") in pinned}
        if _payload_chars([skeletons[index] for index in sorted(selected)]) > max_chars:
            raise ValueError("REPORT_SOURCE_BUDGET: pinned report sources exceed the source budget")
        for index in range(len(skeletons)):
            if index in selected:
                continue
            trial_indexes = sorted(selected | {index})
            if _payload_chars([skeletons[item] for item in trial_indexes]) <= max_chars:
                selected.add(index)
        bounded = [skeletons[index] for index in sorted(selected)]
        omitted_sources = len(skeletons) - len(bounded)
        omitted_items += omitted_sources
        returned_chars = _payload_chars(bounded)

    source_ids = [str(row.get("study_id") or "") for row in studies]
    return bounded, {
        "limit_chars": max_chars, "original_chars": original_chars,
        "returned_chars": returned_chars, "truncated": True,
        "truncated_chars": truncated_chars,
        "omitted_serialized_chars": max(0, original_chars - returned_chars),
        "omitted_items": omitted_items, "omitted_fields": omitted_fields,
        "omitted_sources": omitted_sources,
        "all_source_count": len(studies),
        "pinned_source_ids": sorted(pinned),
        "all_source_ids_sha256": hashlib.sha256("\n".join(source_ids).encode()).hexdigest(),
        "note": ("Source prose/lists were bounded for MCP transport. Treat omitted material as "
                 "unknown, not absent; split the section or fetch the named source for full detail."),
    }


def bound_report_outline_frame(graph: dict[str, Any], studies: list[dict[str, Any]],
                               source_budget: dict[str, Any],
                               pinned_source_ids: list[str] | None = None
                               ) -> tuple[dict[str, Any], list[str]]:
    """Return a bounded, self-describing graph slice for outline authoring.

    ``study_ids`` and ``build_order`` intentionally expose the same visible slice;
    totals and hashes make any omitted tail explicit without repeating an unbounded
    id array three times across the MCP response and embedded prompt.
    """
    all_build_order = [str(value) for value in (graph.get("build_order") or [])]
    all_edges = list(graph.get("edges") or [])
    all_questions = [row for row in (graph.get("open_questions") or [])
                     if row.get("status") == "open"]
    raw_project = graph.get("project") or {}
    source_rows = list(studies)
    pinned = {str(value) for value in (pinned_source_ids or []) if str(value)}
    edge_limit, question_limit, theme_limit, goal_limit = 20, 8, 8, 1_000
    frame_limit = 28_000

    def _project_slice() -> dict[str, Any]:
        limits = {"slug": 160, "title": 240, "goal": goal_limit, "status": 80,
                  "methodology": 120, "phase": 120}
        out = {"id": raw_project.get("id")} if raw_project.get("id") else {}
        for key, limit in limits.items():
            value = raw_project.get(key)
            if value not in (None, ""):
                out[key] = str(value)[:limit]
        themes = [str(value)[:80] for value in (raw_project.get("themes") or [])[:theme_limit]]
        if themes:
            out["themes"] = themes
        return out

    def _compose() -> tuple[dict[str, Any], list[str]]:
        visible_ids = [str(row.get("study_id") or "") for row in source_rows
                       if str(row.get("study_id") or "")]
        visible = set(visible_ids)
        eligible_edges = [edge for edge in all_edges
                          if str(edge.get("from_study") or "") in visible
                          and str(edge.get("to_study") or "") in visible]
        edges = [{
            "from_study": str(edge.get("from_study") or ""),
            "to_study": str(edge.get("to_study") or ""),
            "type": str(edge.get("type") or ""),
            "rationale": str(edge.get("rationale") or "")[:80],
        } for edge in eligible_edges[:edge_limit]]
        questions = []
        for row in all_questions[:question_limit]:
            clipped, _chars, _items = _clip_source_value(
                row, text_limit=160, list_limit=4)
            questions.append(clipped)

        source_meta = dict(source_budget)
        source_meta.setdefault("all_source_count", len(all_build_order))
        source_meta.setdefault("all_source_ids_sha256", hashlib.sha256(
            "\n".join(all_build_order).encode()).hexdigest())
        source_meta["pinned_source_ids"] = sorted(pinned)
        source_meta["returned_chars"] = _payload_chars(source_rows)
        source_meta["omitted_sources"] = max(0, len(all_build_order) - len(source_rows))
        if source_meta["omitted_sources"]:
            source_meta["truncated"] = True
            source_meta["omitted_serialized_chars"] = max(
                0, int(source_meta.get("original_chars") or 0) - source_meta["returned_chars"])

        raw_themes = list(raw_project.get("themes") or [])
        project = _project_slice()
        project_truncated = (
            len(raw_themes) > len(project.get("themes") or [])
            or any(len(str(raw)) > len(str(returned))
                   for raw, returned in zip(raw_themes, project.get("themes") or []))
            or any(len(str(raw_project.get(key) or "")) > len(str(project.get(key) or ""))
                   for key in ("slug", "title", "goal", "status", "methodology", "phase")))
        graph_budget = {
            "frame_limit_chars": frame_limit,
            "truncated": (len(visible_ids) < len(all_build_order)
                          or len(edges) < len(all_edges)
                          or len(questions) < len(all_questions)
                          or project_truncated),
            "build_order_total": len(all_build_order),
            "build_order_returned": len(visible_ids),
            "build_order_omitted": max(0, len(all_build_order) - len(visible_ids)),
            "build_order_sha256": hashlib.sha256(
                "\n".join(all_build_order).encode()).hexdigest(),
            "edges_total": len(all_edges), "edges_returned": len(edges),
            "edges_omitted": max(0, len(all_edges) - len(edges)),
            "open_questions_total": len(all_questions),
            "open_questions_returned": len(questions),
            "open_questions_omitted": max(0, len(all_questions) - len(questions)),
            "project_truncated": project_truncated,
            "project_themes_total": len(raw_themes),
            "project_themes_returned": len(project.get("themes") or []),
            "project_goal_chars_total": len(str(raw_project.get("goal") or "")),
            "project_goal_chars_returned": len(str(project.get("goal") or "")),
            "pinned_source_ids": sorted(pinned),
            "note": ("Bounded outline slice; omitted graph items are unknown, not absent. "
                     "Totals and the build-order digest describe the frozen full graph."),
        }
        return {
            "project": project, "build_order": visible_ids, "edges": edges,
            "open_questions": questions, "studies": source_rows,
            "source_budget": source_meta, "graph_budget": graph_budget,
        }, visible_ids

    # Enforce one aggregate ceiling on the exact pretty JSON embedded in the
    # prompt. Prefer retaining evidence sources over contextual graph detail.
    while True:
        frame, visible_ids = _compose()
        if _payload_chars(frame) <= frame_limit - 500:
            break
        if question_limit:
            question_limit -= 1
        elif edge_limit:
            edge_limit -= 1
        elif theme_limit:
            theme_limit -= 1
        elif goal_limit > 160:
            goal_limit = max(160, goal_limit // 2)
        elif any(str(row.get("study_id") or "") not in pinned for row in source_rows):
            removable = next(index for index in range(len(source_rows) - 1, -1, -1)
                             if str(source_rows[index].get("study_id") or "") not in pinned)
            source_rows.pop(removable)
        else:
            break
    for _ in range(3):
        frame["graph_budget"]["frame_pretty_chars"] = _payload_chars(frame)
    if _payload_chars(frame) > frame_limit:
        raise ValueError("REPORT_OUTLINE_BUDGET: unable to bound the outline authoring frame")
    return frame, visible_ids
