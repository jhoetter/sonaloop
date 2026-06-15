"""Canonical product taxonomy for primitives and their subtypes.

This module is deliberately product-facing: it separates the stable Library
primitives from lower-level subtypes/formats. Service code may keep historic
field names such as `artifact` or open methodology tags; the UI should present
the model through this layer so the vocabulary does not fragment again.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any

from ._i18n import t


@dataclass(frozen=True)
class Primitive:
    kind: str
    family: str
    icon: str
    purpose_key: str


FAMILIES: tuple[tuple[str, str, str], ...] = (
    ("frame", "primitive_family_frame", "help"),
    ("material", "primitive_family_material", "file"),
    ("ask", "primitive_family_ask", "councils"),
    ("test", "primitive_family_test", "prototype"),
    ("capture", "primitive_family_capture", "panel"),
    ("conclude", "primitive_family_conclude", "syntheses"),
    ("structure", "primitive_family_structure", "squareGrid"),
)


PRIMITIVES: dict[str, Primitive] = {
    "open_question": Primitive("open_question", "frame", "help", "primitive_open_question_purpose"),
    "hypothesis": Primitive("hypothesis", "frame", "target", "primitive_hypothesis_purpose"),
    "url_artifact": Primitive("url_artifact", "material", "link", "primitive_url_artifact_purpose"),
    "asset": Primitive("asset", "material", "file", "primitive_asset_purpose"),
    "council": Primitive("council", "ask", "councils", "primitive_council_purpose"),
    "survey": Primitive("survey", "ask", "plan", "primitive_survey_purpose"),
    "prototype": Primitive("prototype", "test", "prototype", "primitive_prototype_purpose"),
    "flow": Primitive("flow", "test", "compass", "primitive_flow_purpose"),
    "session": Primitive("session", "test", "activity", "primitive_session_purpose"),
    "note": Primitive("note", "capture", "panel", "primitive_note_purpose"),
    "synthesis": Primitive("synthesis", "conclude", "syntheses", "primitive_synthesis_purpose"),
    "report": Primitive("report", "conclude", "syntheses", "primitive_report_purpose"),
    "decision": Primitive("decision", "conclude", "flag", "primitive_decision_purpose"),
    "section": Primitive("section", "structure", "squareGrid", "primitive_section_purpose"),
}


def family_label(family: str) -> str:
    if family not in {value for value, _label, _icon in FAMILIES}:
        return family
    return t("primitive_family_" + family)


def family_icon(family: str) -> str:
    return next((icon for value, _label, icon in FAMILIES if value == family), "square")


def primitive_family(kind: str) -> str:
    return PRIMITIVES.get(kind, Primitive(kind, "structure", "square", "")).family


def primitive_purpose(kind: str) -> str:
    p = PRIMITIVES.get(kind)
    return t("primitive_" + p.kind + "_purpose") if p and p.purpose_key else ""


def subtype_value(kind: str, rec: dict[str, Any]) -> str:
    """Return the product subtype/format value for a row, or ``""`` when the kind
    has no useful subtype facet. The values are stable URL query tokens."""
    rec = rec or {}
    if kind == "url_artifact":
        raw = rec.get("kind") or "url"
        return {"url": "website", "prototype": "external_prototype",
                "variant": "ab_variant"}.get(str(raw), "website")
    if kind == "asset":
        return str(rec.get("kind") or "file")
    if kind == "council":
        for marker, value in (
            ("head_to_head", "head_to_head"),
            ("red_team", "red_team"),
            ("price_ladder", "price_ladder"),
            ("ideation", "ideation"),
        ):
            if rec.get(marker):
                return value
        return str(rec.get("mode") or "discovery")
    if kind == "prototype":
        return str(rec.get("fidelity") or "midfi")
    if kind == "flow":
        return "screen_walkthrough"
    if kind == "session":
        subject = rec.get("subject") or {}
        sk = subject.get("kind") or ""
        return {"flow": "walkthrough_session", "prototype": "prototype_session",
                "live_url": "live_session"}.get(str(sk), str(sk))
    if kind == "survey":
        questions = rec.get("questions") or []
        if questions:
            kinds = Counter(q.get("kind") for q in questions if q.get("kind"))
            if kinds:
                return f"{kinds.most_common(1)[0][0]}_survey"
        return "survey"
    if kind == "note":
        data = rec.get("data") or {}
        if data.get("prototype_id") or data.get("prototype_ids") or data.get("artifact_kind"):
            return "concept_note"
        return "observation_note"
    return ""


def subtype_label(value: str) -> str:
    if not value:
        return ""
    label = t("subtype_" + value)
    return value.replace("_", " ").title() if label == "subtype_" + value else label
