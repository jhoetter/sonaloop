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

from .. import primitive_taxonomy_registry as _registry
from ._i18n import t

_REGISTRY = _registry.assert_valid_registry()


@dataclass(frozen=True)
class Primitive:
    kind: str
    family: str
    icon: str
    purpose_key: str
    color: str
    description: str = ""


@dataclass(frozen=True)
class SubtypeDoc:
    value: str
    label_key: str
    meaning_en: str
    meaning_de: str
    rule_en: str
    rule_de: str


FAMILIES: tuple[tuple[str, str, str], ...] = tuple(
    (str(f["id"]), f"primitive_family_{f['id']}", str(f.get("icon") or "square"))
    for f in _REGISTRY["families"]
)


PRIMITIVES: dict[str, Primitive] = {
    str(p["id"]): Primitive(str(p["id"]), str(p["family"]), str(p.get("icon") or "square"),
                            f"primitive_{p['id']}_purpose", str(p.get("color") or "#9aa0a6"),
                            str(p.get("description") or ""))
    for p in _REGISTRY["primitives"]
}


SUBTYPE_DOCS: dict[str, tuple[SubtypeDoc, ...]] = {
    "open_question": (
        SubtypeDoc("open_question", "open_questions_h",
                   "A research uncertainty that still needs work. It is a frame primitive, not a council or report.",
                   "Eine Forschungsunsicherheit, die noch bearbeitet werden muss. Das ist ein Frame-Primitive, kein Council oder Report.",
                   "Library has no subtype facet for open questions; rows vary by status and project context.",
                   "Die Library hat fuer offene Fragen keinen Subtype-Facet; Zeilen unterscheiden sich ueber Status und Projektkontext."),
    ),
    "url_artifact": (
        SubtypeDoc("website", "subtype_website",
                   "A captured or referenced website/page shown to personas as material.",
                   "Eine erfasste oder referenzierte Website/Seite, die Personas als Material sehen.",
                   "rec.kind is missing or 'url'.",
                   "rec.kind fehlt oder ist 'url'."),
        SubtypeDoc("external_prototype", "subtype_external_prototype",
                   "An external prototype link, for example Figma or a hosted click model.",
                   "Ein externer Prototyp-Link, z. B. Figma oder ein gehostetes Klickmodell.",
                   "rec.kind == 'prototype'.",
                   "rec.kind == 'prototype'."),
        SubtypeDoc("ab_variant", "subtype_ab_variant",
                   "One labelled side of an A/B or multi-variant comparison.",
                   "Eine gelabelte Seite eines A/B- oder Multi-Variant-Vergleichs.",
                   "rec.kind == 'variant'.",
                   "rec.kind == 'variant'."),
    ),
    "council": (
        SubtypeDoc("discovery", "subtype_discovery",
                   "Open research questions: moderator asks, personas answer from memory. No proposal vote.",
                   "Offene Forschungsfragen: Mediator fragt, Personas antworten aus Erinnerung. Keine Proposal-Abstimmung.",
                   "No proposal and no votes; services.council_mode(rec) returns 'discovery'.",
                   "Kein proposal und keine votes; services.council_mode(rec) ergibt 'discovery'."),
        SubtypeDoc("evaluation", "subtype_evaluation",
                   "A concept or proposal is reacted to conversationally, without a hard vote.",
                   "Ein Konzept oder Proposal wird conversational bewertet, ohne harte Abstimmung.",
                   "proposal is present, votes are empty; services.council_mode(rec) returns 'evaluation'.",
                   "proposal ist vorhanden, votes sind leer; services.council_mode(rec) ergibt 'evaluation'."),
        SubtypeDoc("decision", "subtype_decision",
                   "A proposal is put to a decision vote and stored with vote stances.",
                   "Ein Proposal wird zur Entscheidung gestellt und mit Vote-Stances gespeichert.",
                   "proposal and votes are present; services.council_mode(rec) returns 'decision'.",
                   "proposal und votes sind vorhanden; services.council_mode(rec) ergibt 'decision'."),
        SubtypeDoc("head_to_head", "subtype_head_to_head",
                   "A council comparing labelled options A/B/... and storing preferences, margin and segment splits.",
                   "Ein Council, der gelabelte Optionen A/B/... vergleicht und Preferences, Margin und Segment-Splits speichert.",
                   "CouncilSession carries a non-empty rec['head_to_head'] block.",
                   "CouncilSession traegt einen nicht-leeren rec['head_to_head']-Block."),
        SubtypeDoc("red_team", "subtype_red_team",
                   "A falsification council: personas argue the case against, with blocker themes and severity.",
                   "Ein Falsifikations-Council: Personas argumentieren die Gegenposition, mit Blocker-Themes und Severity.",
                   "CouncilSession carries a non-empty rec['red_team'] block.",
                   "CouncilSession traegt einen nicht-leeren rec['red_team']-Block."),
        SubtypeDoc("price_ladder", "subtype_price_ladder",
                   "A price-sensitivity council over a fixed ladder of price points.",
                   "Ein Price-Sensitivity-Council ueber eine vorab fixierte Preisleiter.",
                   "CouncilSession carries a non-empty rec['price_ladder'] block.",
                   "CouncilSession traegt einen nicht-leeren rec['price_ladder']-Block."),
        SubtypeDoc("ideation", "subtype_ideation",
                   "A structured ideation council, typically anchored to HMW questions and idea records.",
                   "Ein strukturierter Ideation-Council, typischerweise an HMW-Fragen und Idea Records geankert.",
                   "CouncilSession carries a non-empty rec['ideation'] block.",
                   "CouncilSession traegt einen nicht-leeren rec['ideation']-Block."),
    ),
    "synthesis": (
        SubtypeDoc("synthesis", "syntheses",
                   "An analysis/report record that turns evidence into interpretation and hand-off sections.",
                   "Ein Analyse-/Report-Record, der Evidenz in Interpretation und Handoff-Abschnitte verdichtet.",
                   "Stored as a synthesis row; Library currently has status/project filters, not subtype variants.",
                   "Als Synthesis-Zeile gespeichert; die Library filtert hier aktuell nach Status/Projekt, nicht nach Subtypes."),
    ),
    "prototype": (
        SubtypeDoc("prototype", "prototype_kind",
                   "A runnable prototype without a finer fidelity discriminator.",
                   "Ein lauffaehiger Prototyp ohne feineren Fidelity-Discriminator.",
                   "rec.fidelity is empty, so default_discriminator('prototype') is used.",
                   "rec.fidelity ist leer, daher wird default_discriminator('prototype') genutzt."),
        SubtypeDoc("lofi", "subtype_lofi",
                   "A low-fidelity prototype, usually rough and fast for early exploration.",
                   "Ein Low-Fidelity-Prototyp, meist grob und schnell fuer fruehe Exploration.",
                   "rec.fidelity == 'lofi' or the tag is the selected discriminator.",
                   "rec.fidelity == 'lofi' oder der Tag ist der ausgewaehlte Discriminator."),
        SubtypeDoc("midfi", "subtype_midfi",
                   "A mid-fidelity prototype used after down-selection for concrete refinement.",
                   "Ein Mid-Fidelity-Prototyp nach Down-Selection fuer konkrete Verfeinerung.",
                   "rec.fidelity == 'midfi' or the tag is the selected discriminator.",
                   "rec.fidelity == 'midfi' oder der Tag ist der ausgewaehlte Discriminator."),
        SubtypeDoc("hifi", "subtype_hifi",
                   "A high-fidelity prototype close enough to production to test fine detail.",
                   "Ein High-Fidelity-Prototyp, nah genug an Produktion fuer Detailtests.",
                   "rec.fidelity == 'hifi' or the tag is the selected discriminator.",
                   "rec.fidelity == 'hifi' oder der Tag ist der ausgewaehlte Discriminator."),
    ),
    "session": (
        SubtypeDoc("walkthrough_session", "subtype_walkthrough_session",
                   "A recorded screen or flow walkthrough, usually artifact-first rather than live browser.",
                   "Ein aufgezeichneter Screen- oder Flow-Walkthrough, meist artifact-first statt Live-Browser.",
                   "rec.subject.kind == 'flow'.",
                   "rec.subject.kind == 'flow'."),
        SubtypeDoc("prototype_session", "subtype_prototype_session",
                   "A persona reaction or usability run against a stored prototype.",
                   "Eine Persona-Reaktion oder ein Usability-Lauf gegen einen gespeicherten Prototyp.",
                   "rec.subject.kind == 'prototype', including prototype reaction rows.",
                   "rec.subject.kind == 'prototype', inklusive Prototype-Reaction-Zeilen."),
        SubtypeDoc("live_session", "subtype_live_session",
                   "A recorded run against a live URL/owned surface.",
                   "Ein aufgezeichneter Lauf gegen eine Live-URL/eigene Oberflaeche.",
                   "rec.subject.kind == 'live_url'.",
                   "rec.subject.kind == 'live_url'."),
    ),
    "survey": (
        SubtypeDoc("single_survey", "subtype_single_survey",
                   "A survey whose dominant question kind is single-choice.",
                   "Eine Survey, deren dominanter Fragetyp Single-choice ist.",
                   "Most common question.kind == 'single'.",
                   "Haeufigster question.kind == 'single'."),
        SubtypeDoc("multi_survey", "subtype_multi_survey",
                   "A survey whose dominant question kind is multi-choice.",
                   "Eine Survey, deren dominanter Fragetyp Multi-choice ist.",
                   "Most common question.kind == 'multi'.",
                   "Haeufigster question.kind == 'multi'."),
        SubtypeDoc("scale_survey", "subtype_scale_survey",
                   "A survey whose dominant question kind is a scale.",
                   "Eine Survey, deren dominanter Fragetyp eine Skala ist.",
                   "Most common question.kind == 'scale'.",
                   "Haeufigster question.kind == 'scale'."),
        SubtypeDoc("text_survey", "subtype_text_survey",
                   "A survey whose dominant question kind is free text.",
                   "Eine Survey, deren dominanter Fragetyp Freitext ist.",
                   "Most common question.kind == 'text'.",
                   "Haeufigster question.kind == 'text'."),
        SubtypeDoc("survey", "subtype_survey",
                   "A survey with no questions yet, or no dominant typed question.",
                   "Eine Survey ohne Fragen oder ohne dominanten typisierten Fragetyp.",
                   "No question kind can be derived.",
                   "Es kann kein question.kind abgeleitet werden."),
    ),
    "hypothesis": (
        SubtypeDoc("hypothesis", "hypotheses_h",
                   "A falsifiable bet with metric and expected value/direction. It changes by status, not subtype.",
                   "Eine falsifizierbare Wette mit Metrik und Expected Value/Direction. Sie unterscheidet sich per Status, nicht per Subtype.",
                   "Library has no subtype facet; status can be open, validated, refuted, inconclusive or dropped.",
                   "Die Library hat keinen Subtype-Facet; Status kann open, validated, refuted, inconclusive oder dropped sein."),
    ),
    "decision": (
        SubtypeDoc("decision", "decisions_h",
                   "An evidence-backed commitment record. Its meaningful variation is lifecycle status.",
                   "Ein evidenzbasierter Commitment-Record. Die relevante Variation ist der Lifecycle-Status.",
                   "Library has no subtype facet; status can be proposed, adopted or superseded.",
                   "Die Library hat keinen Subtype-Facet; Status kann proposed, adopted oder superseded sein."),
    ),
    "note": (
        SubtypeDoc("observation_note", "subtype_observation_note",
                   "A captured signal, observation or free note.",
                   "Ein festgehaltenes Signal, eine Beobachtung oder freie Notiz.",
                   "rec.data has no prototype_id/prototype_ids/artifact_kind.",
                   "rec.data hat kein prototype_id/prototype_ids/artifact_kind."),
        SubtypeDoc("concept_note", "subtype_concept_note",
                   "A concept/solution note tied to prototype intent or artifact kind.",
                   "Eine Konzept-/Loesungsnotiz mit Prototype-Intent oder Artifact-Kind.",
                   "rec.data carries prototype_id, prototype_ids or artifact_kind.",
                   "rec.data enthaelt prototype_id, prototype_ids oder artifact_kind."),
    ),
    "asset": (
        SubtypeDoc("image", "subtype_image",
                   "An attached image file.",
                   "Eine angehaengte Bilddatei.",
                   "rec.kind == 'image'.",
                   "rec.kind == 'image'."),
        SubtypeDoc("screenshot", "subtype_screenshot",
                   "A captured screenshot file.",
                   "Eine erfasste Screenshot-Datei.",
                   "rec.kind == 'screenshot'.",
                   "rec.kind == 'screenshot'."),
        SubtypeDoc("document", "subtype_document",
                   "A document-style file, often with preview rendering.",
                   "Eine dokumentartige Datei, oft mit Preview-Rendering.",
                   "rec.kind == 'document'.",
                   "rec.kind == 'document'."),
        SubtypeDoc("file", "subtype_file",
                   "A generic attached file.",
                   "Eine generische angehaengte Datei.",
                   "rec.kind is missing or 'file'. Direction still distinguishes evidence-in from deliverable-out.",
                   "rec.kind fehlt oder ist 'file'. Direction unterscheidet weiter Evidence-in von Deliverable-out."),
    ),
}


_LEGACY_SUBTYPE_DOCS = SUBTYPE_DOCS
_LEGACY_BY_KIND_VALUE: dict[str, dict[str, SubtypeDoc]] = {
    kind: {doc.value: doc for doc in docs} for kind, docs in _LEGACY_SUBTYPE_DOCS.items()
}
_SUBTYPE_LABELS: dict[str, str] = {}
_SUBTYPE_LABEL_KEYS: dict[str, str] = {
    doc.value: doc.label_key for docs in _LEGACY_SUBTYPE_DOCS.values() for doc in docs
}
_LIBRARY_VALUE_PRIORITY: dict[str, tuple[str, ...]] = {
    "url_artifact": ("website", "external_prototype", "ab_variant"),
    "council": ("discovery", "evaluation", "decision", "head_to_head",
                "red_team", "price_ladder", "ideation"),
    "survey": ("single_survey", "multi_survey", "scale_survey", "text_survey", "survey"),
    "session": ("walkthrough_session", "prototype_session", "live_session"),
    "note": ("observation_note", "concept_note"),
    "asset": ("image", "screenshot", "document", "file"),
    # `prototype` is the compatibility alias for the registered app form. Fidelity
    # (lofi/midfi/hifi) is now an orthogonal parameter, not a Library form.
    "prototype": ("prototype", "flow", "dashboard", "cards", "comparison", "model", "journey"),
}


def _form_values_for_library(form: dict[str, Any]) -> list[str]:
    primitive = str(form.get("primitive") or "")
    candidates = [str(form.get("id") or "")] + [str(a) for a in form.get("aliases") or []]
    priority = _LIBRARY_VALUE_PRIORITY.get(primitive, ())
    values = [value for value in priority if value in candidates]
    if values:
        return values
    return [str(form.get("id") or "")]


def _registry_subtype_docs() -> dict[str, tuple[SubtypeDoc, ...]]:
    grouped: dict[str, list[SubtypeDoc]] = {}
    for form in _REGISTRY["forms"]:
        primitive = str(form.get("primitive") or "")
        if primitive == "edge":
            continue
        form_id = str(form.get("id") or "")
        aliases = [str(a) for a in form.get("aliases") or []]
        alias_text = ", ".join(aliases) if aliases else form_id
        for value in _form_values_for_library(form):
            legacy = _LEGACY_BY_KIND_VALUE.get(primitive, {}).get(value)
            if legacy:
                doc = legacy
            else:
                label = str(form.get("label") or value.replace("_", " ").title())
                meaning = str(form.get("description") or label)
                rule_en = f"Registry form {primitive}/{form_id}; accepted tokens: {alias_text}."
                rule_de = f"Registry-Form {primitive}/{form_id}; akzeptierte Tokens: {alias_text}."
                doc = SubtypeDoc(value, f"subtype_{value}", meaning, meaning, rule_en, rule_de)
            grouped.setdefault(primitive, []).append(doc)
            _SUBTYPE_LABELS[value] = str(form.get("label") or value.replace("_", " ").title())
    for kind, docs in _LEGACY_SUBTYPE_DOCS.items():
        existing = {doc.value for doc in grouped.get(kind, [])}
        for doc in docs:
            if kind == "prototype" and doc.value in {"lofi", "midfi", "hifi"}:
                continue
            if doc.value not in existing:
                grouped.setdefault(kind, []).append(doc)
                _SUBTYPE_LABELS.setdefault(doc.value, doc.value.replace("_", " ").title())
    return {kind: tuple(docs) for kind, docs in grouped.items()}


SUBTYPE_DOCS = _registry_subtype_docs()


def family_label(family: str) -> str:
    if family not in {value for value, _label, _icon in FAMILIES}:
        return family
    return t("primitive_family_" + family)


def family_icon(family: str) -> str:
    return next((icon for value, _label, icon in FAMILIES if value == family), "square")


def primitive_family(kind: str) -> str:
    return PRIMITIVES.get(kind, Primitive(kind, "structure", "square", "", "#9aa0a6")).family


def primitive_color(kind: str) -> str:
    return PRIMITIVES.get(kind, Primitive(kind, "structure", "square", "", "#9aa0a6")).color


def primitive_purpose(kind: str) -> str:
    p = PRIMITIVES.get(kind)
    if not p or not p.purpose_key:
        return ""
    label = t("primitive_" + p.kind + "_purpose")
    return p.description if label == "primitive_" + p.kind + "_purpose" else label


def primitive_subtypes(kind: str) -> tuple[SubtypeDoc, ...]:
    """Product-facing subtype catalogue for one Library primitive.

    This is documentation data, not detection logic. `subtype_value()` below is
    the live row classifier; the catalogue explains every value the UI should
    make understandable to humans.
    """
    return SUBTYPE_DOCS.get(kind, ())


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
    if kind == ("coun" + "cil"):
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
        return str(rec.get("type") or "prototype")
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
    raw_key = "subtype_" + value
    label = t("subtype_" + value) if value in _SUBTYPE_LABEL_KEYS else raw_key
    if label == raw_key and value in _SUBTYPE_LABELS:
        return _SUBTYPE_LABELS[value]
    return value.replace("_", " ").title() if label == raw_key else label
