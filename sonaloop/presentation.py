"""Presentation-from-data resolver and evidence-linked report deck plans.

The existing resolver keeps methodology/artifact presentation data-driven. The
deck-plan contract below adds a second, compatible concern: an MCP host authors
the story, visible claims, source refs and speaker notes once; PPTX export then
compiles the reviewed plan into any workspace master without model improvisation.
"""
from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from .config import suggestions_dir
from ._pptx_preview import render_first_slide  # noqa: F401, E402


# Presentation-from-data resolver (spec/methodology-presentation-from-data.md).
PALETTE = ["#6b7cff", "#34a853", "#f29900", "#a142f4", "#ea4335", "#00897b", "#5f6368", "#d81b60"]
FAN_GLYPH, WAIST_GLYPH = "◇", "◆"
GLYPH_ICON: dict[str, str] = {
    "◇": "diamond", "◆": "diamondFilled",
    "▢": "square", "▣": "squareSplit", "▤": "squareRows", "▧": "squareSplit",
    "▥": "squareCols", "▦": "squareGrid", "▭": "rectangle",
    "⇄": "exchange", "∿": "wave", "❯∿": "wave",
    "⌕": "search", "✎": "pencil", "➤": "caretRight",
}
DEFAULT_ARTIFACT_TYPE = "prototype"


def glyph_icon(glyph: str | None) -> str:
    if not glyph:
        return ""
    return GLYPH_ICON.get(glyph, "square")


def hash_color(tag: str, palette: list[str] | None = None) -> str:
    pal = palette or PALETTE
    if not tag:
        return "#9aa0a6"
    return pal[sum(ord(c) for c in tag) % len(pal)]


@lru_cache(maxsize=1)
def _hints() -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    directory = suggestions_dir()
    if not directory.exists():
        return out
    for path in sorted(directory.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if data.get("kind") == "ideation_lenses":
            continue
        for item in data.get("items", []) or []:
            tag = item.get("tag")
            if not tag:
                continue
            entry = dict(item.get("presentation") or {})
            for key in ("renderer", "default_template", "_note"):
                if item.get(key):
                    entry[key] = item[key]
            out.setdefault(tag, {}).update(entry)
            for discriminator in item.get("discriminators", []) or []:
                discriminator_tag = discriminator.get("tag")
                if not discriminator_tag:
                    continue
                discriminator_entry = dict(discriminator.get("presentation") or {})
                if discriminator.get("template"):
                    discriminator_entry["template"] = discriminator["template"]
                discriminator_entry["_parent"] = tag
                out.setdefault(discriminator_tag, {}).update(discriminator_entry)
    return out


def reload_hints() -> None:
    _hints.cache_clear()


def present(tag: str, own: dict[str, Any] | None = None) -> dict[str, Any]:
    hint = _hints().get(tag, {})
    merged = {**hint, **(own or {})}
    label = merged.get("label") or (tag or "")
    return {
        "label": label,
        "short": merged.get("short") or label,
        "color": merged.get("color") or hash_color(tag),
        "icon": merged.get("icon") or "",
        "glyph": merged.get("glyph") or "",
    }


def step_glyph(is_fan: bool, own: dict[str, Any] | None = None) -> str:
    return (own or {}).get("glyph") or (FAN_GLYPH if is_fan else WAIST_GLYPH)


def artifact_type_meta(type_tag: str) -> dict[str, Any]:
    return _hints().get(type_tag, {})


def default_discriminator(type_tag: str) -> str:
    default_template = (_hints().get(type_tag) or {}).get("default_template")
    fallback = ""
    for tag, meta in _hints().items():
        if meta.get("_parent") != type_tag:
            continue
        fallback = fallback or tag
        if default_template and meta.get("template") == default_template:
            return tag
    return fallback


def discriminator_tags(type_tag: str) -> list[str]:
    return [tag for tag, value in _hints().items() if value.get("_parent") == type_tag]


@lru_cache(maxsize=1)
def edge_colors() -> dict[str, str]:
    path = suggestions_dir() / "edge_types.json"
    out: dict[str, str] = {}
    if not path.exists():
        return out
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return out
    for item in data.get("items", []) or []:
        if item.get("tag"):
            out[item["tag"]] = (item.get("presentation") or {}).get("color") or "#9aa0a6"
    return out


@lru_cache(maxsize=1)
def ideation_lenses() -> list[dict[str, Any]]:
    path = suggestions_dir() / "ideation_lenses.json"
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    return [{"tag": item.get("tag", ""), "label": item.get("label", ""),
             "prompt": item.get("prompt", "")}
            for item in data.get("items", []) or [] if item.get("prompt")]


def artifact_palette() -> list[dict[str, Any]]:
    out = [{"tag": tag, "label": value.get("label") or tag,
            "note": value.get("_note", "")}
           for tag, value in _hints().items()
           if value.get("default_template") and not value.get("_parent")]
    return sorted(out, key=lambda item: item["tag"])


def resolve_template(type_tag: str, tags: list[str] | None = None,
                     explicit: str | None = None) -> str | None:
    if explicit:
        return explicit
    hints = _hints()
    for tag in tags or []:
        hint = hints.get(tag) or {}
        if hint.get("template") and hint.get("_parent") == type_tag:
            return hint["template"]
    own_default = (hints.get(type_tag) or {}).get("default_template")
    if own_default:
        return own_default
    for tag in tags or []:
        template = (hints.get(tag) or {}).get("template")
        if template:
            return template
    return None


PRESENTATION_PLAN_SCHEMA = "sonaloop.presentation_plan.v1"

# Presentation vocabulary, not methodology vocabulary. Methodology specs choose
# among these generic visual forms through data-authored deck profiles.
PRESENTATION_KINDS = (
    "cover", "decision", "decision_dashboard", "agenda", "section", "summary", "stats",
    "stimulus_comparison", "persona_grid", "persona_detail",
    "preference_shift", "annotated_screen", "revision_mockup", "insight", "quote",
    "recommendation", "risk", "pillars", "voices", "comparison", "timeline",
    "chart", "charts", "table",
    "image", "next_steps", "source_index", "closing", "content",
)

_NON_EVIDENCE_KINDS = {"cover", "agenda", "section", "closing", "source_index"}


def _strings(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)
    elif isinstance(value, dict):
        for key, item in value.items():
            if key not in {"speaker_notes", "evidence_refs", "source_refs"}:
                yield from _strings(item)


def visible_word_count(slide: dict[str, Any]) -> int:
    """Approximate visible copy, excluding notes and machine/source references."""
    return sum(len(text.split()) for text in _strings(slide))


def validate_presentation_plan(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize one authored presentation plan.

    Methodology-specific requirements stay in the methodology's
    ``presentation.deck`` data. This validator enforces only the stable delivery
    contract shared by every deck.
    """
    if not isinstance(payload, dict):
        raise ValueError("presentation plan must be an object")
    schema = str(payload.get("schema") or PRESENTATION_PLAN_SCHEMA)
    if schema != PRESENTATION_PLAN_SCHEMA:
        raise ValueError(f"presentation plan schema must be {PRESENTATION_PLAN_SCHEMA!r}")
    for field in ("title", "audience", "objective"):
        if not str(payload.get(field) or "").strip():
            raise ValueError(f"presentation plan needs non-empty {field!r}")
    try:
        duration = int(payload.get("duration_minutes") or 10)
    except (TypeError, ValueError) as exc:
        raise ValueError("duration_minutes must be an integer") from exc
    if duration < 1 or duration > 180:
        raise ValueError("duration_minutes must be between 1 and 180")

    core = list(payload.get("slides") or [])
    appendix = list(payload.get("appendix") or [])
    if len(core) < 2 or len(core) > 18:
        raise ValueError("presentation plan needs 2..18 core slides")
    if len(appendix) > 40:
        raise ValueError("presentation appendix may contain at most 40 slides")

    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for appendix_flag, rows in ((False, core), (True, appendix)):
        for index, raw in enumerate(rows, 1):
            if not isinstance(raw, dict):
                raise ValueError("every presentation slide must be an object")
            slide = dict(raw)
            sid = str(slide.get("id") or
                      f"{'appendix' if appendix_flag else 'slide'}_{index}").strip()
            if sid in seen:
                raise ValueError(f"duplicate presentation slide id {sid!r}")
            seen.add(sid)
            kind = str(slide.get("kind") or "content").strip()
            if kind not in PRESENTATION_KINDS:
                raise ValueError(
                    f"unsupported presentation kind {kind!r}; use one of {PRESENTATION_KINDS}")
            headline = str(slide.get("headline") or slide.get("title") or "").strip()
            if not headline:
                raise ValueError(f"presentation slide {sid!r} needs a headline")
            if len(headline) > 180:
                raise ValueError(f"presentation slide {sid!r} headline exceeds 180 characters")
            notes = dict(slide.get("speaker_notes") or {})
            if not str(notes.get("talk_track") or "").strip():
                raise ValueError(f"presentation slide {sid!r} needs speaker_notes.talk_track")
            refs = [str(value).strip() for value in (slide.get("evidence_refs") or [])
                    if str(value).strip()]
            if not appendix_flag and kind not in _NON_EVIDENCE_KINDS and not refs:
                raise ValueError(f"presentation slide {sid!r} needs evidence_refs")
            normalized.append({
                **slide,
                "id": sid,
                "kind": kind,
                "headline": headline,
                "evidence_refs": list(dict.fromkeys(refs)),
                "speaker_notes": {
                    "takeaway": str(notes.get("takeaway") or headline).strip(),
                    "talk_track": str(notes.get("talk_track") or "").strip(),
                    "evidence": [str(value).strip() for value in
                                 (notes.get("evidence") or refs) if str(value).strip()],
                    "caveats": [str(value).strip() for value in
                                (notes.get("caveats") or []) if str(value).strip()],
                    "transition": str(notes.get("transition") or "").strip(),
                    "backup": [str(value).strip() for value in
                               (notes.get("backup") or []) if str(value).strip()],
                    "timing_seconds": max(0, min(900, int(notes.get("timing_seconds") or 0))),
                },
                "appendix": appendix_flag,
            })

    split = len(core)
    out = {
        **payload,
        "schema": PRESENTATION_PLAN_SCHEMA,
        "version": int(payload.get("version") or 1),
        "duration_minutes": duration,
        "slides": normalized[:split],
        "appendix": normalized[split:],
    }
    return out


def presentation_plan_qa(plan: dict[str, Any]) -> dict[str, Any]:
    """Content-design checks that remain useful independently of the master."""
    core = list(plan.get("slides") or [])
    warnings: list[dict[str, Any]] = []
    visual_kinds = {
        "stats", "stimulus_comparison", "persona_grid", "persona_detail",
        "preference_shift", "annotated_screen", "revision_mockup", "comparison", "timeline",
        "chart", "charts", "table", "image", "pillars", "voices", "decision",
        "decision_dashboard", "insight", "recommendation", "risk", "next_steps",
    }
    visual_count = sum(str(slide.get("kind") or "") in visual_kinds for slide in core)
    for slide in core:
        words = visible_word_count(slide)
        if words > 70 and slide.get("kind") not in {"table", "source_index"}:
            warnings.append({"code": "visible_copy_dense", "slide_id": slide["id"],
                             "words": words})
        notes = slide.get("speaker_notes") or {}
        if slide.get("kind") not in _NON_EVIDENCE_KINDS and not notes.get("caveats"):
            warnings.append({"code": "speaker_caveat_missing", "slide_id": slide["id"]})
    if len(core) < 10 and any(slide.get("kind") == "agenda" for slide in core):
        warnings.append({"code": "agenda_unnecessary_for_short_deck"})
    duration = max(1, int(plan.get("duration_minutes") or 10))
    max_core = max(4, min(18, round(duration * 0.8)))
    if len(core) > max_core:
        warnings.append({"code": "too_many_core_slides_for_duration",
                         "slides": len(core), "duration_minutes": duration,
                         "recommended_max": max_core})
    appendix_count = len(plan.get("appendix") or [])
    if appendix_count > max(5, len(core)):
        warnings.append({"code": "appendix_overbuilt", "slides": appendix_count})
    if core and core[-1].get("kind") == "closing" and not any(
            core[-1].get(key) for key in ("items", "steps", "decision", "next_action")):
        warnings.append({"code": "generic_closing_without_action",
                         "slide_id": core[-1]["id"]})
    ratio = visual_count / max(1, len(core))
    if ratio < 0.6:
        warnings.append({"code": "too_few_visual_slides", "ratio": round(ratio, 2)})
    return {
        "status": "pass" if not warnings else "review",
        "core_slide_count": len(core),
        "appendix_slide_count": len(plan.get("appendix") or []),
        "visual_slide_ratio": round(ratio, 2),
        "speaker_notes_count": sum(bool(slide.get("speaker_notes", {}).get("talk_track"))
                                   for slide in core + list(plan.get("appendix") or [])),
        "warnings": warnings,
    }
