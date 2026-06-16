from __future__ import annotations

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
