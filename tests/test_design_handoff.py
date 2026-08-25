"""The provider-neutral Sonaloop → design/canvas/code MCP bridge."""
from __future__ import annotations

import pytest

from sonaloop import services
from sonaloop.models import Synthesis
from sonaloop.services import _design_handoff, _hooks, _substrate

from conftest import create_persona


@pytest.fixture(autouse=True)
def _clean_seams(monkeypatch):
    monkeypatch.setattr(_hooks, "_HANDLERS", {})
    monkeypatch.setattr(_hooks, "_ENTRY_POINTS_LOADED", True)
    monkeypatch.setattr(_substrate, "_ACCESS_GUARDS", [])


def _seed(store):
    persona_id = create_persona(store, "Ann Example")
    project = services.start_project(
        "Mobile banking", "Make the migration understandable", persona_ids=[persona_id], store=store)
    synthesis = services.record_synthesis(
        "Migration findings", "Make the migration understandable", project_id=project["id"],
        payload={
            "gesamtbild": "The next action is useful but the authentication change is unclear.",
            "findings": [{"kind": "recommendation", "text": "Explain the two changes separately."}],
            "statements": [{"persona_id": persona_id, "text": "I do not know what changes first.",
                            "stance": {"value": -1, "label": "skeptical"}, "refs": []}],
        }, store=store)
    return project, synthesis, persona_id


def test_design_handoff_is_evidence_linked_provider_neutral_and_bounded(store):
    project, synthesis, persona_id = _seed(store)

    handoff = services.get_design_handoff(project["id"], store=store)

    assert handoff["schema"] == _design_handoff.DESIGN_HANDOFF_SCHEMA
    assert handoff["provider_neutral"] is True
    assert handoff["project"]["id"] == project["id"]
    assert handoff["source_results"][0]["id"] == synthesis["id"]
    assert handoff["research"]["findings"][0]["text"].startswith("Explain")
    assert handoff["research"]["voices"][0]["persona_id"] == persona_id
    assert handoff["cohort"][0]["display_name"] == "Ann Example"
    assert handoff["design_context"]["tokens"]["colors"]
    assert handoff["destination_contract"]["register_interactive_result"]["tool"] == (
        "register_remote_prototype")
    assert "figma" not in str(handoff["destination_contract"]).casefold()


def test_design_handoff_rejects_cross_project_narrowing_and_obeys_access_guard(store):
    project, synthesis, _persona_id = _seed(store)
    other = services.start_project("Other", "Other goal", store=store)

    with pytest.raises(KeyError):
        services.get_design_handoff(other["id"], synthesis_id=synthesis["id"], store=store)

    def guard(operation, resource):
        if operation == "get_design_handoff":
            raise PermissionError(resource["project_id"])

    services.register_access_guard(guard)
    with pytest.raises(PermissionError):
        services.get_design_handoff(project["id"], store=store)


def test_design_handoff_reuses_delivery_story_for_destination_mcps(store):
    project, _synthesis, persona_id = _seed(store)
    report = Synthesis(
        id="report_design_delivery", title="Mobile banking — Report", start_input="",
        council_ids=[], arc_narrative="", gesamtbild="", positionierung="", references=[],
        created_at="2026-08-25T00:00:00+00:00", scope="project", project_id=project["id"],
        status="done", sections=[],
    ).to_dict()
    store.upsert_synthesis(report)
    notes = {"talk_track": "Explain the evidence.", "caveats": ["Synthetic cohort."]}
    services.record_presentation_plan(report["id"], {
        "title": "Migration decision", "audience": "project team",
        "objective": "Choose the revision", "duration_minutes": 5,
        "slides": [
            {"id": "cover", "kind": "cover", "headline": "Mobile banking migration test",
             "speaker_notes": notes},
            {"id": "shift", "kind": "preference_shift",
             "headline": "Context resolves the concern",
             "before": {"value": 1, "total": 2}, "after": {"value": 2, "total": 2},
             "switchers": [{"persona_id": persona_id, "reason": "Now I understand the order."}],
             "evidence_refs": ["council:round-2"], "speaker_notes": notes},
            {"id": "revision", "kind": "revision_mockup",
             "headline": "Separate the two changes", "asset_id": "asset_current",
             "proposal": {"headline": "First move the app", "body": "Then change login."},
             "why": ["Clarifies sequence"], "evidence_refs": ["council:round-2"],
             "speaker_notes": notes},
        ],
    }, store=store)

    handoff = services.get_design_handoff(project["id"], store=store)
    assert handoff["report"]["delivery_story"]["title"] == "Migration decision"
    assert any(row["id"] == "delivery:shift" for row in handoff["research"]["findings"])
    assert any(row["text"] == "Now I understand the order."
               for row in handoff["research"]["voices"])
    assert handoff["research"]["proposed_revisions"][0]["proposal"]["headline"] == \
        "First move the app"
    assert handoff["cohort"][0]["avatar"]["available"] is False
    assert "approved frame/page sequence" in " ".join(
        handoff["destination_contract"]["sequence"])
