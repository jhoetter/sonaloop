from __future__ import annotations

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
        primitive_family,
        primitive_subtypes,
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
