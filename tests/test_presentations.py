"""Evidence-linked presentation plans: gather → author → persist."""
from __future__ import annotations

import pytest

from sonaloop import services
from sonaloop.models import Synthesis
from sonaloop.presentation import (
    PRESENTATION_PLAN_SCHEMA,
    presentation_plan_qa,
    validate_presentation_plan,
)


def _report(store):
    project = services.start_project(
        "Reaction deck", "Which stimulus should ship?", methodology="Reaction Test",
        operation_id="presentation-test-project", store=store,
    )
    report = Synthesis(
        id="report_presentation_test", title="Reaction deck — Report", start_input="",
        council_ids=[], arc_narrative="", gesamtbild="", positionierung="", references=[],
        created_at="2026-08-22T00:00:00+00:00",
        scope="project", project_id=project["id"], status="done",
        lead="Use B after one important revision.",
        sections=[{
            "id": "decision", "heading": "Decision", "markdown": "Use B, then revise.",
            "source_study_ids": [], "citations": [], "figures": [], "status": "done",
        }],
    ).to_dict()
    store.upsert_synthesis(report)
    return project, report


def _plan():
    notes = {"talk_track": "Explain the evidence behind this slide.",
             "caveats": ["Synthetic cohort, not observed customer behavior."]}
    return {
        "schema": PRESENTATION_PLAN_SCHEMA,
        "title": "Reaction decision", "audience": "stakeholder",
        "objective": "Choose the next action", "duration_minutes": 8,
        "slides": [
            {"id": "cover", "kind": "cover", "headline": "B is the stronger base",
             "speaker_notes": notes},
            {"id": "result", "kind": "stats", "headline": "Preference moves from 6/8 to 8/8",
             "items": [{"label": "Blind", "value": "6/8"},
                       {"label": "With context", "value": "8/8"}],
             "evidence_refs": ["synthesis:decision"], "speaker_notes": notes},
        ],
        "appendix": [
            {"id": "sources", "kind": "source_index", "headline": "Sources",
             "speaker_notes": {"talk_track": "Use this for questions."}},
        ],
    }


def test_methodology_exposes_data_authored_deck_profile(store):
    profile = services.get_methodology("reaction_test", store=store)["presentation"]["deck"]
    assert profile["purpose"]
    assert {row["role"] for row in profile["story_beats"]} >= {
        "decision", "stimulus", "cohort", "reaction", "revision",
    }
    assert "persona details" in profile["appendix"]


def test_presentation_plan_validation_and_qa():
    plan = validate_presentation_plan(_plan())
    assert plan["slides"][1]["speaker_notes"]["takeaway"] == \
        "Preference moves from 6/8 to 8/8"
    qa = presentation_plan_qa(plan)
    assert qa["speaker_notes_count"] == 3
    assert qa["core_slide_count"] == 2
    broken = _plan()
    broken["slides"][1]["evidence_refs"] = []
    with pytest.raises(ValueError, match="evidence_refs"):
        validate_presentation_plan(broken)


def test_brief_and_retry_safe_record(store):
    project, report = _report(store)
    brief = services.brief_presentation(report["id"], duration_minutes=12, store=store)
    assert brief["project_id"] == project["id"]
    assert brief["methodology"]["deck_profile"]["story_beats"]
    assert brief["methodology"]["result_contract"]["schemas"][0]["id"] == \
        "stimulus_reaction.v1"
    assert brief["output_contract"]["schema"] == PRESENTATION_PLAN_SCHEMA

    first = services.record_presentation_plan(
        report["id"], _plan(), operation_id="deck-v1", store=store)
    replay = services.record_presentation_plan(
        report["id"], _plan(), operation_id="deck-v1", store=store)
    assert first["presentation_plan_revision"] == 1
    assert replay["idempotent_replay"] is True
    changed = _plan()
    changed["title"] = "Different"
    with pytest.raises(ValueError, match="PRESENTATION_OPERATION_CONFLICT"):
        services.record_presentation_plan(
            report["id"], changed, operation_id="deck-v1", store=store)


def test_every_packaged_methodology_has_a_deck_prompt_profile(store):
    for row in services.list_methodologies(store=store):
        profile = services.get_methodology(row["key"], store=store).get("presentation", {}).get("deck")
        assert profile and profile["story_beats"], row["key"]
        assert profile["required_visuals"] and profile["appendix"] and profile["avoid"]
