"""Minimal-host Reaction Test preflight: one bounded action at a time."""
from __future__ import annotations

import asyncio
import base64
from contextlib import contextmanager
from io import BytesIO

import pytest
from PIL import Image

from sonaloop import config, services
from sonaloop.mcp_server import build_server
from sonaloop.research_integrity import IntegrityError


@contextmanager
def _workspace():
    token = config.set_request_tenant_scope(["ws_weak_host"], "ws_weak_host")
    try:
        yield
    finally:
        config.reset_request_tenant_scope(token)


def _png() -> str:
    out = BytesIO()
    Image.new("RGB", (32, 20), (40, 90, 140)).save(out, format="PNG")
    return base64.b64encode(out.getvalue()).decode("ascii")


def _profile(name: str, role: str) -> dict:
    return {
        "display_name": name,
        "identity_traits": {key: "unspecified" for key in (
            "gender_presentation", "gender_confidence", "age_range",
            "appearance_notes", "avatar_profile", "avatar_constraints")},
        "segment": {"customer_type": "operations", "market": "synthetic",
                    "region": "DACH", "firm_size": "20"},
        "demographics": {"age": 42},
        "role": {"title": role, "responsibilities": "ordinary service handoffs",
                 "seniority": "experienced", "decision_power": "shared"},
        "company_context": {"industry": "services", "size": "small",
                            "stack": "ordinary office tools", "operating_model": "team"},
        "goals": ["finish weekly work reliably"], "constraints": ["limited time"],
        "tool_ids": ["e_mail"], "tools": ["E-Mail"],
        "relationships": [{"name": "Team", "type": "colleague", "friction": "handoffs"}],
        "personality": {"working_style": "pragmatic", "communication_style": "direct",
                        "risk_tolerance": "medium", "character_notes": "questions assumptions"},
        "pain_points": ["routine coordination"], "success_criteria": ["clear handoff"],
    }


def _deep_persona(store, name: str, role: str, prefix: str) -> str:
    row = services.record_persona(f"Independent {name} work history", _profile(name, role), store=store)
    persona = store.get_persona(row["id"])
    persona["created_at"] = "2026-01-01T08:00:00Z"
    persona["updated_at"] = "2026-01-01T08:00:00Z"
    persona.setdefault("provenance", {})["grounding"] = "independent interview + diary"
    store.upsert_persona(persona, reason="independent fixture")
    for index in range(3):
        event_id = f"event_{prefix}_{index}"
        timestamp = f"2026-01-0{index + 2}T09:00:00Z"
        store.insert_experience_event({
            "id": event_id, "persona_id": row["id"], "timestamp": timestamp,
            "event_type": "ordinary_work",
            "summary": f"Handled an ordinary supplier handoff {index}",
        })
        store.insert_entity_fact({
            "id": f"fact_{prefix}_{index}", "persona_id": row["id"],
            "entity_id": f"entity_{prefix}", "fact": f"routine context {index}",
            "status": "active", "t_valid": timestamp, "t_invalid": None,
            "importance": 2, "source_event_id": event_id, "created_at": timestamp,
        })
    store.insert_evidence({
        "id": f"evidence_{prefix}", "persona_id": row["id"],
        "source_type": "independent_fixture",
        "content_or_path": "The existing manual checklist is sufficient; this is not a priority.",
        "notes": "independent disconfirming context", "created_at": "2026-01-02T08:00:00Z",
    })
    return row["id"]


def _url_only(store):
    project = services.start_project(
        "SHKB URL-only Reaction Test",
        "Mach einen Reaction Test zu https://www.shkb.ch/295-anlegen. Leg direkt los.",
        methodology="Reaction Test", persona_ids=[], operation_id="weak:project", store=store,
    )
    run = services.start_run(project["id"], operation_id="weak:run", store=store)
    return project, run


def test_url_is_identity_only_and_first_run_step_has_one_real_stimulus_call(store):
    with _workspace():
        project, run = _url_only(store)
        dispatch = services.run_step(run["run_id"], store=store)
        action = dispatch["blocking_action"]
        assert action["kind"] == "stimulus_required"
        assert action["target"] == {
            "url": "https://www.shkb.ch/295-anlegen",
            "role": "target_identity_only",
            "is_evidence": False,
            "server_fetch_authorized": False,
        }
        assert action["allowed_tools"] == ["admit_remote_screenshot"]
        assert action["next_call"]["tool"] == "admit_remote_screenshot"
        assert action["next_call"]["arguments"]["run_id"] == run["run_id"]
        assert action["next_call"]["arguments"]["dispatch_token"] == dispatch["dispatch_token"]
        assert action["pending_blockers"]["cohort_too_small"] is True
        stored = store.get_research_project(project["id"])
        assert not stored.get("assets") and not stored.get("product_understanding_versions")
        assert [row for row in store.list_council_sessions()
                if row.get("project_id") == project["id"]] == []

        brief = services.brief_product_understanding(project["id"], store=store)
        assert brief["action"]["kind"] == "stimulus_required"


def test_minimal_host_repairs_same_run_and_reaches_both_owned_council_dispatches(store):
    with _workspace():
        p1 = _deep_persona(store, "Mara", "Operations lead", "mara_weak")
        p2 = _deep_persona(store, "Ozan", "Support lead", "ozan_weak")
        project, run = _url_only(store)

        first = services.run_step(run["run_id"], store=store)
        screen = services.admit_remote_screenshot(
            project["id"], run["run_id"], "weak:screen", _png(), "screen.png", "image/png",
            "2026-08-09T14:40:00Z", "release:shkb:1", label="Anlegen overview",
            dispatch_token=first["dispatch_token"], store=store,
        )
        flow_action = services.run_step(run["run_id"], store=store)["blocking_action"]
        assert flow_action["kind"] == "flow_manifest_required"
        manifest = services.record_flow_manifest(
            project["id"], run["run_id"], "weak:manifest", "primary", "Anlegen flow",
            [{"asset_version_id": screen["id"], "label": "Anlegen overview"}],
            "Understand the exact page", "release:shkb:1", "2026-08-09T14:40:00Z",
            dispatch_token=first["dispatch_token"], store=store,
        )

        product_dispatch = services.run_step(run["run_id"], store=store)
        assert product_dispatch["blocking_action"]["kind"] == "product_understanding_required"
        assert product_dispatch["blocking_action"]["next_call"]["tool"] == \
            "record_manifest_product_understanding"
        with pytest.raises(IntegrityError) as incomplete:
            services.record_manifest_product_understanding(
                project["id"], manifest["id"], observations=[],
                dispatch_token=product_dispatch["dispatch_token"], store=store,
            )
        assert incomplete.value.code == "STIMULUS_OBSERVATION_INCOMPLETE"
        assert "safe retry" in incomplete.value.message
        assert not store.get_research_project(project["id"]).get("product_understanding_versions")

        understanding = services.record_manifest_product_understanding(
            project["id"], manifest["id"],
            observations=[{"step_index": 0,
                           "claim": "The captured screen visibly presents an investment overview."}],
            unknown_capabilities=["Behavior after selecting a product is not visible."],
            target_name="SHKB", target_url="https://www.shkb.ch/295-anlegen",
            dispatch_token=product_dispatch["dispatch_token"], store=store,
        )
        assert understanding["dispatch"]["checkpointed"] is True
        assert understanding["stimulus_manifest"]["manifest_id"] == manifest["id"]
        assert understanding["bounded_authoring"]["url_role"] == "target_identity_only"
        understanding_replay = services.record_manifest_product_understanding(
            project["id"], manifest["id"],
            observations=[{"step_index": 0,
                           "claim": "The captured screen visibly presents an investment overview."}],
            unknown_capabilities=["Behavior after selecting a product is not visible."],
            target_name="SHKB", target_url="https://www.shkb.ch/295-anlegen",
            dispatch_token=product_dispatch["dispatch_token"], store=store,
        )
        assert understanding_replay["id"] == understanding["id"]
        assert understanding_replay["idempotent_replay"] is True

        frame_dispatch = services.run_step(run["run_id"], store=store)
        assert frame_dispatch["step_id"] == "frame__react"
        assert frame_dispatch["blocking_action"]["kind"] == "cohort_selection_required"
        with pytest.raises(IntegrityError) as too_small:
            services.select_reaction_test_cohort(
                project["id"], [p1], "Only one persona is not enough",
                operation_id="weak:too-small", dispatch_token=frame_dispatch["dispatch_token"],
                store=store,
            )
        assert too_small.value.code == "COHORT_MISSING_OR_TOO_SMALL"
        assert store.get_research_project(project["id"])["persona_ids"] == []
        selected = services.select_reaction_test_cohort(
            project["id"], [p1, p2], "Independent operational target and skeptical contrast",
            operation_id="weak:cohort", dispatch_token=frame_dispatch["dispatch_token"], store=store,
        )
        replay = services.select_reaction_test_cohort(
            project["id"], [p1, p2], "Independent operational target and skeptical contrast",
            operation_id="weak:cohort", dispatch_token=frame_dispatch["dispatch_token"], store=store,
        )
        assert selected["gate_passed"] is False and selected["dispatch"]["checkpointed"] is False
        assert replay["idempotent_replay"] is True
        assert "blocking_action" not in services.run_step(run["run_id"], store=store)
        services.record_frame(
            project["id"], "frame__react",
            ["What do independent people understand and distrust on first inspection?"],
            hypotheses=["The visible overview may still leave action consequences unclear."],
            memory_refs=[f"evidence:evidence_ozan_weak"],
            dispatch_token=frame_dispatch["dispatch_token"], store=store,
        )

        cohort_dispatch = services.run_step(run["run_id"], store=store)
        assert cohort_dispatch["step_id"] == "preflight__cohort_integrity"
        gate = services.record_cohort_preflight(
            project["id"], representation=[
                {"persona_id": p1, "posture": "target",
                 "rationale": "owns an adjacent operational workflow"},
                {"persona_id": p2, "posture": "skeptical",
                 "rationale": "independent context questions whether this deserves action",
                 "basis_quote": "existing manual checklist is sufficient",
                 "evidence_refs": [{"kind": "evidence", "id": "evidence_ozan_weak"}]},
            ], dispatch_token=cohort_dispatch["dispatch_token"], store=store,
        )
        assert gate["status"] == "pass"

        first_council = services.run_step(run["run_id"], store=store)
        assert first_council["step_id"] == "act__react__comprehension"
        stimulus = {"kind": "flow", "id": manifest["id"]}
        services.record_council(
            project["id"], "What lands on first inspection?", [p1, p2],
            statements=[
                {"persona_id": p1, "text": "The overview is legible.",
                 "stance": {"value": 1}, "refs": [stimulus]},
                {"persona_id": p2, "text": "I cannot infer the consequence of acting.",
                 "stance": {"value": -1}, "refs": [stimulus]},
            ],
            summary="The visible state is legible but action consequences remain unclear.",
            claims=[{"text": "The simulated reactions identify an action-consequence gap.",
                     "posture": "simulated", "refs": [stimulus]}],
            dispatch_token=first_council["dispatch_token"], store=store,
        )
        second_council = services.run_step(run["run_id"], store=store)
        assert second_council["step_id"] == "act__react__trust_action"


def test_mcp_exposes_only_bounded_manifest_observations_and_explicit_selector():
    tools = {row.name: row for row in asyncio.run(build_server().list_tools())}
    assert {"record_manifest_product_understanding", "select_reaction_test_cohort"} <= tools.keys()
    manifest = tools["record_manifest_product_understanding"].inputSchema["properties"]
    assert {"manifest_id", "observations", "unknown_capabilities", "dispatch_token"} <= manifest.keys()
    assert "routes" not in manifest and "states" not in manifest and "stimulus_manifest" not in manifest
    selector = tools["select_reaction_test_cohort"].inputSchema["properties"]
    assert {"persona_ids", "selection_rationale", "operation_id", "dispatch_token"} <= selector.keys()
