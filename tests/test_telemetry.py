from datetime import datetime, timezone

import pytest

from sonaloop import config, services, telemetry


@pytest.fixture(autouse=True)
def _clear_sink():
    for name in telemetry.product_telemetry_sink_names():
        telemetry.unregister_product_telemetry_sink(name)
    yield
    for name in telemetry.product_telemetry_sink_names():
        telemetry.unregister_product_telemetry_sink(name)


def _capture(**kwargs):
    scope = config.set_request_tenant_scope(["ws_test"], "ws_test")
    actor = config.set_request_actor({
        "kind": "user", "id": "sub_private", "label": "Private User",
        "role": "editor", "channel": "web",
    })
    try:
        return telemetry.capture_product_event("job_viewed", **kwargs)
    finally:
        config.reset_request_actor(actor)
        config.reset_request_tenant_scope(scope)


def test_provider_neutral_sink_receives_request_context_and_structural_metadata():
    events = []
    telemetry.register_product_telemetry_sink("test", events.append)

    result = _capture(
        project_id="project_private", subject_kind="job", subject_id="project_private",
        properties={"view_mode": "page", "persona_count": 8, "has_search": False},
        idempotency_key="view-window-1",
        occurred_at=datetime(2026, 8, 12, 12, tzinfo=timezone.utc),
    )

    assert result["accepted"] == 1
    assert events[0]["schema"] == telemetry.EVENT_SCHEMA
    assert events[0]["workspace_id"] == "ws_test"
    assert events[0]["actor"] == {
        "kind": "user", "id": "sub_private", "role": "editor", "channel": "web",
    }
    assert events[0]["subject"] == {"kind": "job", "id": "project_private"}
    assert events[0]["properties"]["persona_count"] == 8


def test_authored_property_values_are_reduced_to_an_enum_without_leaking():
    events = []
    telemetry.register_product_telemetry_sink("test", events.append)

    _capture(properties={"segment": "Private customer description with spaces"})

    assert events[0]["properties"] == {"segment": "unknown"}


def test_unbound_open_core_capture_is_a_noop():
    events = []
    telemetry.register_product_telemetry_sink("test", events.append)
    assert telemetry.capture_product_event("job_viewed") == {
        "accepted": 0, "ignored": "unbound_request",
    }
    assert events == []


def test_sink_registration_replaces_by_name_and_failures_are_soft():
    first, second = [], []
    telemetry.register_product_telemetry_sink("destination", first.append)
    telemetry.register_product_telemetry_sink("destination", second.append)
    telemetry.register_product_telemetry_sink(
        "broken", lambda _event: (_ for _ in ()).throw(RuntimeError("offline")))

    result = _capture()

    assert first == [] and len(second) == 1
    assert result["accepted"] == 1 and result["failed_sinks"] == ["broken"]


def test_core_product_functions_emit_semantic_events_after_success(store):
    events = []
    telemetry.register_product_telemetry_sink("test", events.append)
    scope = config.set_request_tenant_scope(["ws_test"], "ws_test")
    actor = config.set_request_actor({
        "kind": "user", "id": "sub_private", "label": "Private User",
        "role": "editor", "channel": "mcp",
    })
    try:
        project = services.start_project(
            "Private title", "Private goal", operation_id="telemetry-create", store=store,
        )
        replay = services.start_project(
            "Private title", "Private goal", operation_id="telemetry-create", store=store,
        )
        services.update_research_project(project["id"], {"status": "active"}, store=store)
        services.start_run(project["id"], operation_id="telemetry-run", store=store)
    finally:
        config.reset_request_actor(actor)
        config.reset_request_tenant_scope(scope)

    assert replay["idempotent_replay"] is True
    assert [event["name"] for event in events] == [
        "job_created", "job_updated", "run_started",
    ]
    assert all("Private" not in str(event["properties"]) for event in events)


def test_persona_survey_and_prototype_boundaries_emit_structural_events(
    store, tmp_path, monkeypatch,
):
    from tests.conftest import make_profile
    from sonaloop import prototypes

    events = []
    telemetry.register_product_telemetry_sink("test", events.append)
    scope = config.set_request_tenant_scope(["ws_test"], "ws_test")
    actor = config.set_request_actor({
        "kind": "user", "id": "sub_private", "label": "Private User",
        "role": "editor", "channel": "web",
    })
    monkeypatch.setattr(prototypes, "prototypes_dir", lambda: tmp_path)
    try:
        project = services.start_project(
            "Private title", "Private goal", operation_id="telemetry-breadth", store=store,
        )
        persona = services.record_persona(
            "Private persona evidence", make_profile("Private Persona"), store=store,
        )
        services.update_persona(persona["id"], {"goals": ["Private goal"]}, "edit", store=store)
        survey = services.record_survey(
            project["id"], "Private survey", [
                {"id": "q1", "text": "Private question", "kind": "single",
                 "options": ["Private A", "Private B"]},
            ], store=store,
        )["survey"]
        services.import_survey_responses(survey["id"], [{
            "respondent_key": "private-respondent",
            "answers": [{"question_id": "q1", "value": "Private A"}],
        }], store=store)
        prototype = services.scaffold_prototype(
            "private-prototype", "Private prototype", {
                "title": "Private prototype", "start": "home", "screens": [{
                    "id": "home", "title": "Private screen", "elements": [{
                        "id": "copy", "kind": "text", "label": "Private copy",
                    }],
                }],
            }, project_id=project["id"], fidelity="hifi", store=store,
        )
        services.delete_prototype_artifact(prototype["id"], store=store)
        services.delete_persona(persona["id"], store=store)
    finally:
        config.reset_request_actor(actor)
        config.reset_request_tenant_scope(scope)

    assert {
        "persona_created", "persona_updated", "persona_deleted",
        "survey_recorded", "survey_responses_imported",
        "prototype_registered", "prototype_deleted",
    } <= {event["name"] for event in events}
    assert all("Private" not in str(event["properties"]) for event in events)


@pytest.mark.parametrize("properties", [
    {"query": "private search"},
    {"report_title": "private title"},
    {"nested": {"content": "private"}},
    {"too_long": "x" * 121},
])
def test_content_shaped_or_unbounded_properties_are_rejected(properties):
    with pytest.raises((TypeError, ValueError)):
        _capture(properties=properties)
