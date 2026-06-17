from __future__ import annotations

from sonaloop import services
from sonaloop import primitive_taxonomy_registry as reg


def test_primitive_taxonomy_registry_is_valid():
    assert reg.registry_errors() == []


def test_registry_has_a_form_for_every_family():
    data = reg.load_registry()
    primitive_family = {p["id"]: p["family"] for p in data["primitives"]}
    families_with_forms = {primitive_family[f["primitive"]] for f in data["forms"]}
    assert {f["id"] for f in data["families"]} <= families_with_forms


def test_existing_hardcoded_aliases_resolve_to_structural_forms():
    expectations = {
        ("council", "discovery"): "open_discussion",
        ("council", "evaluation"): "proposal_reaction",
        ("council", "decision"): "vote",
        ("council", "head_to_head"): "option_comparison",
        ("council", "red_team"): "objection_review",
        ("council", "price_ladder"): "ladder_review",
        ("council", "ideation"): "idea_review",
        ("url_artifact", "website"): "web_reference",
        ("url_artifact", "external_prototype"): "prototype_reference",
        ("url_artifact", "ab_variant"): "variant_reference",
        ("session", "walkthrough_session"): "walkthrough",
        ("session", "prototype_session"): "prototype_use",
        ("session", "live_session"): "live_use",
        ("note", "observation_note"): "observation",
        ("note", "concept_note"): "concept",
        ("survey", "single_survey"): "choice",
        ("survey", "multi_survey"): "choice",
        ("survey", "scale_survey"): "scale",
        ("survey", "text_survey"): "text",
    }
    for (primitive, alias), target in expectations.items():
        form = reg.resolve_form(primitive, alias)
        assert form is not None, (primitive, alias)
        assert form["id"] == target


def test_orthogonal_values_are_not_forms():
    data = reg.load_registry()
    attrs = {a["id"]: a for a in data["orthogonal_attributes"]}
    assert attrs["prototype_fidelity"]["values"] == ["lofi", "midfi", "hifi"]
    assert reg.resolve_form("prototype", "midfi") is None
    assert reg.resolve_form("url_artifact", "A") is None
    assert reg.resolve_form("decision", "adopted") is None


def test_registry_rejects_unknown_custom_forms_by_default():
    data = reg.load_registry()
    assert data["custom_form_policy"]["default"] == "reject_unknown"
    assert reg.resolve_form("council", "totally_new_llm_format") is None


def test_web_taxonomy_helpers_are_registry_backed():
    from sonaloop.web._primitive_taxonomy import (
        FAMILIES,
        PRIMITIVES,
        form_value,
        primitive_family,
        primitive_subtypes,
        survey_question_form_values,
        subtype_label,
        subtype_value,
    )

    data = reg.load_registry()
    assert [f["id"] for f in data["families"]] == [f[0] for f in FAMILIES]
    assert set(reg.primitive_ids()) <= set(PRIMITIVES)
    assert primitive_family("prototype") == "material"

    prototype_forms = {doc.value for doc in primitive_subtypes("prototype")}
    assert {"prototype", "flow", "dashboard", "cards", "comparison", "model", "journey"} <= prototype_forms
    assert not {"lofi", "midfi", "hifi"} & prototype_forms
    assert subtype_value("prototype", {"type": "model", "fidelity": "midfi"}) == "model"
    assert subtype_label("model") == "Model prototype"

    survey_forms = {doc.value for doc in primitive_subtypes("survey")}
    assert {"single_survey", "multi_survey", "scale_survey", "text_survey", "ranking_survey"} <= survey_forms
    assert "survey" not in survey_forms
    mixed_survey = {
        "questions": [{"kind": "single"}, {"kind": "multi"}, {"kind": "scale"}, {"kind": "text"}]
    }
    assert survey_question_form_values(mixed_survey) == ["single", "multi", "scale", "text"]
    # The Library filter stays backwards-compatible and classifies by dominant question kind;
    # detail pages display the nested question forms instead of calling this the survey form.
    assert subtype_value("survey", {"questions": [{"kind": "single"}, {"kind": "multi"}]}) == "single_survey"
    assert subtype_value("survey", {"questions": [{"kind": "scale", "stance_mapped": True}]}) == "scale_survey"
    assert subtype_value("survey", {"questions": []}) == ""

    note_forms = {doc.value for doc in primitive_subtypes("note")}
    assert {"observation_note", "insight", "idea", "concept_note"} <= note_forms
    assert subtype_value("note", {"kind": "idea", "data": {}}) == "idea"
    assert subtype_value("note", {"kind": "note", "data": {"prototype_id": "p1"}}) == "concept_note"

    assert form_value("open_question", {"text": "How might we reduce shift handover loss?"}) == "how_might_we"
    assert form_value("open_question", {"text": "Where does handover fail?"}) == "open_question"
    assert form_value("synthesis", {"scope": "project"}) == "report"
    assert form_value("synthesis", {"scope": "convergence"}) == "synthesis"


def test_material_boundary_keeps_stimuli_separate_from_results():
    data = reg.load_registry()
    primitives = {p["id"]: p for p in data["primitives"]}
    variant = reg.resolve_form("url_artifact", "ab_variant")
    external = reg.resolve_form("url_artifact", "external_prototype")
    assert primitives["url_artifact"]["family"] == "material"
    assert primitives["prototype"]["family"] == "material"
    assert variant and "stimulus" in variant["description"]
    assert variant and "result lives in an ask/test form" in variant["description"]
    assert external and "stays a reference" in external["description"]
    assert reg.resolve_form("prototype", "midfi") is None


def test_council_forms_document_classifiers_and_renderers():
    data = reg.load_registry()
    council_forms = [f for f in data["forms"] if f["primitive"] == "council"]
    by_id = {f["id"]: f for f in council_forms}
    assert set(by_id) == {
        "open_discussion", "proposal_reaction", "vote", "option_comparison",
        "objection_review", "ladder_review", "idea_review",
    }
    expected_aliases = {
        "open_discussion": "discovery",
        "proposal_reaction": "evaluation",
        "vote": "decision",
        "option_comparison": "head_to_head",
        "objection_review": "red_team",
        "ladder_review": "price_ladder",
        "idea_review": "ideation",
    }
    for form_id, alias in expected_aliases.items():
        form = by_id[form_id]
        assert alias in form["aliases"]
        assert form["classifier"]["mode_alias"] == alias
        assert form["renderer"]["requires"]


def test_session_forms_document_classifiers_and_renderers():
    data = reg.load_registry()
    by_id = {f["id"]: f for f in data["forms"] if f["primitive"] == "session"}
    assert set(by_id) == {"walkthrough", "prototype_use", "live_use", "variant_test"}
    assert by_id["walkthrough"]["classifier"]["subject_kind"] == "flow"
    assert by_id["prototype_use"]["classifier"]["subject_kind"] == "prototype"
    assert "prototype_id" in by_id["prototype_use"]["classifier"]["compat_fields"]
    assert by_id["live_use"]["classifier"]["subject_kind"] == "live_url"
    assert by_id["variant_test"]["classifier"]["subject_kind"] == "variant"
    assert {"variants", "assignment", "order_shown"} <= set(by_id["variant_test"]["classifier"]["compat_fields"])
    for form in by_id.values():
        assert form["renderer"]["requires"]


def test_survey_forms_are_registry_backed_without_mixed_pseudoform():
    data = reg.load_registry()
    by_id = {f["id"]: f for f in data["forms"] if f["primitive"] == "survey"}
    assert set(by_id) == {"choice", "scale", "text", "ranking"}
    assert reg.resolve_form("survey", "single_survey")["id"] == "choice"
    assert reg.resolve_form("survey", "multi_survey")["id"] == "choice"
    assert reg.resolve_form("survey", "scale_survey")["id"] == "scale"
    assert reg.resolve_form("survey", "text_survey")["id"] == "text"
    assert reg.resolve_form("survey", "ranking_survey")["id"] == "ranking"
    assert reg.resolve_form("survey", "mixed_survey") is None


def test_note_and_conclude_forms_keep_statuses_orthogonal():
    data = reg.load_registry()
    by_primitive = {}
    for form in data["forms"]:
        by_primitive.setdefault(form["primitive"], set()).add(form["id"])
    assert {"observation", "insight", "idea", "concept"} <= by_primitive["note"]
    assert by_primitive["synthesis"] == {"synthesis", "brief"}
    assert by_primitive["report"] == {"report"}
    assert by_primitive["decision"] == {"decision"}
    assert by_primitive["hypothesis"] == {"hypothesis"}

    attrs = {a["id"]: a for a in data["orthogonal_attributes"]}
    assert attrs["decision_status"]["kind"] == "status"
    assert attrs["hypothesis_status"]["kind"] == "status"
    assert attrs["synthesis_status"]["kind"] == "status"
    assert reg.resolve_form("decision", "adopted") is None
    assert reg.resolve_form("hypothesis", "validated") is None


def test_taxonomy_read_services_expose_shapes_and_aliases():
    primitives = services.list_primitives()
    assert any(p["id"] == "council" for p in primitives)
    council_forms = services.list_forms("council")
    assert any(f["id"] == "option_comparison" for f in council_forms)
    form = services.get_form("council", "head_to_head")
    assert form["id"] == "option_comparison"
    assert form["schema"]["required"] == ["options", "preferences"]
    assert form["renderer"]["requires"] == ["option_comparison"]
    suggested = services.suggest_forms("session")
    assert suggested["primitive"]["id"] == "session"
    assert any(f["id"] == "prototype_use" for f in suggested["forms"])
    assert suggested["custom_form_policy"]["default"] == "reject_unknown"


def test_taxonomy_cli_commands_are_wired():
    from sonaloop.cli import build_parser

    assert build_parser().parse_args(["primitive-list"]).command == "primitive-list"
    args = build_parser().parse_args(["form-list", "--primitive", "council"])
    assert args.command == "form-list" and args.primitive == "council"
    args = build_parser().parse_args(["form-get", "council", "head_to_head"])
    assert args.command == "form-get" and args.form_id == "head_to_head"
    args = build_parser().parse_args(["forms-suggest", "survey"])
    assert args.command == "forms-suggest" and args.primitive == "survey"
