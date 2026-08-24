"""Compile a stored presentation plan into the neutral native-PPTX slide model."""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from .. import config
from ..storage import Store
from ._project_assets import get_asset


def _asset_path(project_id: str, value, store: Store) -> str:
    """Resolve only project-bound assets; persisted plans never become a filesystem read seam."""
    asset_id = str((value.get("asset_id") or value.get("id"))
                   if isinstance(value, dict) else (value or ""))
    if not asset_id:
        return ""
    try:
        record = get_asset(project_id, asset_id, store=store)
    except (KeyError, ValueError):
        return ""
    path = config.partition_dir() / "assets" / Path(record.get("asset_path", "")).name
    return str(path) if path.is_file() else ""


def _persona_item(raw, store: Store) -> dict:
    item = dict(raw) if isinstance(raw, dict) else {"persona_id": str(raw or "")}
    persona_id = str(item.get("persona_id") or item.get("id") or "")
    persona = store.get_persona(persona_id) or {}
    role = persona.get("role") or {}
    segment = persona.get("segment") or {}
    lens = str(item.get("lens") or item.get("detail") or role.get("title") or "")
    if not lens and segment:
        lens = " · ".join(str(value) for value in list(segment.values())[:2] if value)
    avatar = ""
    avatar_path = (persona.get("avatar") or {}).get("path")
    if avatar_path:
        try:
            from ._snapshots import _avatar_disk_path
            candidate = _avatar_disk_path(avatar_path)
            avatar = str(candidate) if candidate.exists() else ""
        except (KeyError, TypeError, ValueError):
            avatar = ""
    return {
        **item,
        "persona_id": persona_id,
        "name": str(item.get("name") or persona.get("display_name") or persona_id),
        "role": str(item.get("role") or role.get("title") or ""),
        "lens": lens,
        "avatar": avatar,
    }


def _support(slide: dict, strip_md: Callable[[str], str]) -> list[str]:
    values = slide.get("support") or slide.get("items") or []
    out = []
    for value in values:
        text = (value.get("text") or value.get("title") or value.get("label")) \
            if isinstance(value, dict) else value
        if str(text or "").strip():
            out.append(strip_md(str(text)))
    return out


def compile_presentation_plan_slides(report: dict, store: Store, title: str,
                                     de: bool, strip_md: Callable[[str], str]) -> list[dict]:
    """Compile generic presentation semantics; the renderer applies brand/layout afterwards."""
    plan = dict(report.get("presentation_plan") or {})
    project_id = str(report.get("project_id") or "")

    def compile_one(raw: dict) -> dict:
        slide = dict(raw)
        kind = str(slide.get("kind") or "content")
        headline = strip_md(str(slide.get("headline") or slide.get("title") or ""))
        common = {
            "speaker_notes": dict(slide.get("speaker_notes") or {}),
            "evidence_refs": list(slide.get("evidence_refs") or []),
        }
        if kind == "cover":
            return {**common, "kind": "cover", "logo": True, "canvas": "dawn",
                    "eyebrow": str(slide.get("eyebrow") or "Research presentation"),
                    "title": headline,
                    "subtitle": strip_md(str(slide.get("subheadline") or
                                              slide.get("subtitle") or plan.get("objective") or "")),
                    "meta": str(slide.get("meta") or
                                f"{plan.get('audience', '')} · {plan.get('duration_minutes', 10)} min"),
                    "native_meta": str(slide.get("native_meta") or slide.get("eyebrow") or ""),
                    "date": str(slide.get("date") or report.get("created_at", "")[:10]),
                    "image": _asset_path(
                        project_id, slide.get("asset_id") or slide.get("image_ref"), store)}
        if kind in {"decision", "insight", "recommendation", "risk"}:
            tone = ("recommendation" if kind in {"decision", "recommendation"}
                    else "risk" if kind == "risk" else "insight")
            eyebrow = (("Entscheidung" if de else "Decision")
                       if kind == "decision" else kind)
            return {**common, "kind": tone, "tone": tone,
                    "eyebrow": str(slide.get("eyebrow") or eyebrow),
                    "statement": headline, "support": _support(slide, strip_md),
                    "meta": str(slide.get("meta") or "")}
        if kind == "decision_dashboard":
            decision = dict(slide.get("decision") or {})
            if not decision:
                decision = {"text": headline}
            return {
                **common, "kind": kind, "heading": headline,
                "decision": decision,
                "metrics": list(slide.get("metrics") or []),
                "rationale": list(slide.get("rationale") or slide.get("items") or []),
            }
        if kind in {"persona_grid", "persona_detail"}:
            rows = slide.get("items") or slide.get("personas") or slide.get("persona_ids") or []
            return {**common, "kind": kind, "heading": headline,
                    "items": [_persona_item(row, store) for row in rows],
                    "footnote": str(slide.get("footnote") or "")}
        if kind == "stimulus_comparison":
            panels = []
            for raw_panel in (slide.get("left") or {}, slide.get("right") or {}):
                panel = dict(raw_panel)
                panel["image"] = _asset_path(
                    project_id,
                    panel.get("asset_id") or panel.get("image_ref") or panel.get("image"), store)
                panels.append(panel)
            return {**common, "kind": kind, "heading": headline,
                    "left": panels[0], "right": panels[1]}
        if kind == "preference_shift":
            return {**common, "kind": kind, "heading": headline,
                    "before": dict(slide.get("before") or {}),
                    "after": dict(slide.get("after") or {}),
                    "switchers": [_persona_item(row, store)
                                  for row in (slide.get("switchers") or [])],
                    "switch_label": str(slide.get("switch_label") or
                                        ("Gewechselt" if de else "Changed"))}
        if kind == "annotated_screen":
            return {**common, "kind": kind, "heading": headline,
                    "image": _asset_path(
                        project_id,
                        slide.get("asset_id") or slide.get("image_ref") or slide.get("image"), store),
                    "annotations": list(slide.get("annotations") or [])}
        if kind == "revision_mockup":
            return {
                **common, "kind": kind, "heading": headline,
                "image": _asset_path(
                    project_id,
                    slide.get("asset_id") or slide.get("image_ref") or slide.get("image"), store),
                "source_label": str(slide.get("source_label") or
                                    ("Heute" if de else "Current")),
                "proposal_label": str(slide.get("proposal_label") or
                                      ("Vorschlag" if de else "Proposed")),
                "proposal": dict(slide.get("proposal") or {}),
                "why": list(slide.get("why") or []),
            }
        if kind in {"next_steps", "timeline"}:
            return {**common, "kind": "timeline", "heading": headline,
                    "steps": list(slide.get("steps") or slide.get("items") or [])}
        if kind == "source_index":
            return {**common, "kind": "table", "heading": headline,
                    "columns": list(slide.get("columns") or
                                    (["Quelle", "Beitrag"] if de else ["Source", "Contribution"])),
                    "rows": list(slide.get("rows") or [])}
        if kind == "image":
            return {**common, "kind": "image", "heading": headline,
                    "image": _asset_path(
                        project_id,
                        slide.get("asset_id") or slide.get("image_ref") or slide.get("image"), store),
                    "caption": str(slide.get("caption") or "")}
        if kind == "quote":
            return {**common, "kind": "quote", "text": str(slide.get("text") or headline),
                    "attribution": str(slide.get("attribution") or ""),
                    "role": str(slide.get("role") or "")}
        if kind in {"stats", "summary", "pillars", "voices", "comparison", "table",
                    "chart", "charts", "agenda", "section", "closing"}:
            compiled = {**slide, **common, "kind": kind}
            if kind in {"stats", "summary", "pillars", "voices", "comparison", "table",
                        "chart", "charts", "agenda"}:
                compiled["heading"] = headline
            else:
                compiled["title"] = headline
            return compiled
        blocks = list(slide.get("blocks") or [])
        if not blocks:
            blocks = [{"type": "li", "text": text} for text in _support(slide, strip_md)]
        return {**common, "kind": "content", "heading": headline, "blocks": blocks}

    slides = [compile_one(slide) for slide in (plan.get("slides") or [])]
    appendix = list(plan.get("appendix") or [])
    if appendix:
        slides.append({
            "kind": "section", "num": "A", "title": "Anhang" if de else "Appendix",
            "subtitle": "Evidenz, Methode und Quellen" if de else
                        "Evidence, method and sources",
            "speaker_notes": {"takeaway": "Appendix", "talk_track":
                              "Use the following slides for questions and evidence detail."},
        })
        slides.extend(compile_one(slide) for slide in appendix)
    return slides
