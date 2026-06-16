from __future__ import annotations

import pytest

from sonaloop import services


def test_council_form_classifies_base_modes_through_registry():
    assert services.council_form({"prompt": "q", "statements": []}) == "open_discussion"
    assert services.council_form({"prompt": "q", "proposal": "Build it", "statements": []}) \
        == "proposal_reaction"
    assert services.council_form({"prompt": "q", "proposal": "Build it", "votes": [{"vote": "yes"}]}) \
        == "vote"


def test_council_form_classifies_specialized_blocks_through_registry():
    cases = {
        "head_to_head": "option_comparison",
        "red_team": "objection_review",
        "price_ladder": "ladder_review",
        "ideation": "idea_review",
    }
    for block, form_id in cases.items():
        assert services.council_form({"prompt": "q", block: {"present": True}}) == form_id
        definition = services.council_form_definition({"prompt": "q", block: {"present": True}})
        assert definition["id"] == form_id


def test_record_council_form_records_builtin_open_discussion(store):
    project = services.create_research_project("Council forms", goal="g", store=store)
    out = services.record_council_form(
        project["id"], "open_discussion",
        {"questions": ["What breaks?", "What helps?"], "statements": [
            {"persona_id": "p1", "text": "The handoff breaks at exceptions.",
             "about": {"kind": "prompt", "id": "q0"}}
        ]},
        ["p1"], prompt="Where does handoff fail?", key="generic-open", store=store)
    stored = services.get_council(out["id"], store=store)
    assert stored["form"]["id"] == "open_discussion"
    assert stored["form_payload"]["questions"] == ["What breaks?", "What helps?"]
    assert stored["questions"] == ["What breaks?", "What helps?"]
    assert services.council_form(stored) == "open_discussion"


def test_record_council_form_preserves_specialized_blocks(store):
    project = services.create_research_project("Compare", goal="g", store=store)
    out = services.record_council_form(
        project["id"], "option_comparison",
        {"options": [{"label": "A", "text": "Plain"}, {"label": "B", "text": "Guided"}],
         "preferences": [{"persona_id": "p1", "choice": "B", "reason": "clearer"}],
         "statements": []},
        ["p1"], prompt="A or B?", key="generic-h2h", store=store)
    stored = services.get_council(out["id"], store=store)
    assert stored["form"]["id"] == "option_comparison"
    assert stored["head_to_head"]["preferences"][0]["choice"] == "B"
    assert services.council_form(stored) == "option_comparison"


def test_record_council_form_validates_registry_payload(store):
    project = services.create_research_project("Bad payload", goal="g", store=store)
    with pytest.raises(KeyError):
        services.record_council_form(project["id"], "made_up_form", {}, [], store=store)
    with pytest.raises(ValueError, match="missing required fields"):
        services.record_council_form(project["id"], "option_comparison", {"options": []}, [], store=store)
