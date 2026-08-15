"""Stable cross-request workflow correlation for research jobs and outputs."""
from __future__ import annotations

import base64
import time

import pytest

from sonaloop import services
from sonaloop.correlation import (
    WORKFLOW_TRACE_SCHEMA,
    validate_workflow_trace_id,
    workflow_trace_id,
    workflow_trace_ref,
)
from sonaloop.mcp_server._env import _env


def test_project_run_asset_and_mcp_envelope_share_one_workflow_trace(store):
    project = services.start_project(
        "Traceable job", "Can we reconstruct this work?",
        operation_id="traceable:create", store=store)
    expected = workflow_trace_id(project["id"])
    asset = services.attach_asset(
        project["id"], content_base64=base64.b64encode(b"screen").decode(),
        filename="screen.png", kind="screenshot", title="Screen", store=store)
    run = services.start_run(
        project["id"], operation_id="traceable:run", store=store)

    assert expected.startswith("sltrace_") and len(expected) == 32
    assert project["workflow_trace_id"] == expected
    assert run["workflow_trace_id"] == expected
    assert asset["workflow_trace_id"] == expected
    assert services.get_research_project(project["id"], store=store)["workflow_trace_id"] == expected
    assert services.query_projects(store=store)["items"][0]["workflow_trace_id"] == expected

    envelope = _env("project_health", {"project_id": project["id"]}, time.perf_counter())
    assert envelope["_meta"]["workflow_trace_id"] == expected
    nested = _env("attach_asset", {"asset": asset}, time.perf_counter())
    assert nested["_meta"]["workflow_trace_id"] == expected
    assert workflow_trace_ref(project, run_id=run["run_id"]) == {
        "schema": WORKFLOW_TRACE_SCHEMA,
        "workflow_trace_id": expected,
        "project_id": project["id"],
        "run_id": run["run_id"],
    }


def test_legacy_project_derives_same_trace_without_persisted_field(store):
    project = services.start_project("Legacy trace", "q", store=store)
    raw = store.get_research_project(project["id"])
    raw.pop("workflow_trace_id", None)
    store.upsert_research_project(raw)

    restored = services.get_research_project(project["id"], store=store)

    assert restored["workflow_trace_id"] == workflow_trace_id(project["id"])


def test_workflow_trace_input_validation_is_bounded():
    expected = workflow_trace_id("project_known")
    assert validate_workflow_trace_id(expected.upper()) == expected
    with pytest.raises(ValueError, match="workflow_trace_id"):
        validate_workflow_trace_id("sltrace_not-a-trace")
