"""Execution and deterministic scoring for provider qualification.

Private split from :mod:`sonaloop.qualification` to keep the public contract
small. Every mutation still goes through the real Core service layer.
"""
from __future__ import annotations

import base64
import copy
import tempfile
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from . import config, services
from .research_integrity import (
    CLAIM_POSTURE_SCHEMA,
    PRODUCT_UNDERSTANDING_SCHEMA,
    admitted_stimuli,
    current_product_understanding,
)
from .cohort_integrity import COHORT_PREFLIGHT_SCHEMA, current_cohort_preflight
from .storage import Store
from .qualification import FIXED_THRESHOLDS, QualificationError


_WORKSPACE_LOCK = threading.RLock()


@contextmanager
def _ephemeral_store():
    """Run fixture writes in an isolated DB and asset partition, then erase both."""
    with tempfile.TemporaryDirectory(prefix="sonaloop-provider-qualification-") as raw:
        root = Path(raw)
        with _WORKSPACE_LOCK:
            old_data, old_root = config.DATA_DIR, config.ROOT
            config.DATA_DIR, config.ROOT = root / "data", root
            config.DATA_DIR.mkdir(parents=True, exist_ok=True)
            try:
                with Store(path=root / "qualification.db") as store:
                    yield store
            finally:
                config.DATA_DIR, config.ROOT = old_data, old_root


def _error_code(exc: Exception) -> str:
    return str(getattr(exc, "code", "") or type(exc).__name__)


def _capture_error(state: dict[str, Any], phase: str, exc: Exception) -> None:
    state["errors"].append({"phase": phase, "code": _error_code(exc)})


def _token(protocol: dict[str, Any], dispatch: dict[str, Any]) -> str | None:
    return dispatch.get("dispatch_token") if protocol["use_dispatch_tokens"] else None


def _asset_ref(asset: dict[str, Any]) -> dict[str, str]:
    return {"kind": "asset", "id": str(asset["id"])}


def _fixture_profile(name: str, claim: str) -> dict[str, Any]:
    return {
        "display_name": name,
        "identity_traits": {key: "unspecified" for key in (
            "gender_presentation", "gender_confidence", "age_range", "appearance_notes",
            "avatar_profile", "avatar_constraints")},
        "segment": {"customer_type": "synthetic operations", "market": "fixture",
                    "region": "DACH", "firm_size": "20"},
        "demographics": {"age": 40},
        "role": {"title": "Operations lead", "responsibilities": claim,
                 "seniority": "lead", "decision_power": "shared"},
        "company_context": {"industry": "services", "size": "small",
                            "stack": "ordinary office tools", "operating_model": "team"},
        "goals": [claim], "constraints": ["limited time"],
        "tool_ids": ["e_mail"], "tools": ["E-Mail"],
        "relationships": [{"name": "Team", "type": "colleague", "friction": "handoffs"}],
        "personality": {"working_style": "pragmatic", "communication_style": "direct",
                        "risk_tolerance": "medium", "character_notes": "questions assumptions"},
        "pain_points": [claim], "success_criteria": [claim],
    }


def _fixture_persona(store: Store, name: str, claim: str, *, deep: bool,
                     suffix: str) -> str:
    persona = services.record_persona(
        f"privacy-safe qualification {suffix}: {claim}", _fixture_profile(name, claim), store=store)
    pid = persona["id"]
    if not deep:
        return pid
    persona = store.get_persona(pid) or persona
    persona["created_at"] = "2026-01-01T08:00:00Z"
    persona["updated_at"] = "2026-01-01T08:00:00Z"
    persona.setdefault("provenance", {})["grounding"] = "privacy-safe qualification diary"
    store.upsert_persona(persona, reason="qualification independent cohort")
    for index in range(3):
        stamp = f"2026-01-0{index + 2}T09:00:00Z"
        store.insert_experience_event({
            "id": f"qualification_event_{suffix}_{index}", "persona_id": pid,
            "timestamp": stamp, "event_type": "ordinary_work",
            "summary": f"routine independent work event {index}",
        })
        store.insert_entity_fact({
            "id": f"qualification_fact_{suffix}_{index}", "persona_id": pid,
            "entity_id": f"qualification_entity_{suffix}", "fact": f"ordinary context {index}",
            "status": "active", "t_valid": stamp, "t_invalid": None, "importance": 2,
            "source_event_id": f"qualification_event_{suffix}_{index}", "created_at": stamp,
        })
    services.attach_evidence(
        pid, "synthetic_interview_fixture",
        "The existing manual routine is sufficient; this product is not an established need.",
        "privacy-safe independent disconfirming evidence", store=store)
    return pid


def _seed_cohorts(fixture: dict[str, Any], protocol: dict[str, Any],
                  store: Store) -> dict[str, Any]:
    deep_map, circular_map = {}, {}
    for index, voice in enumerate(protocol["voices"]):
        voice_id = str(voice["voice_id"])
        deep_map[voice_id] = _fixture_persona(
            store, f"Independent voice {index + 1}",
            f"Coordinates ordinary supplier and support workstream {index + 1}",
            deep=True, suffix=f"{fixture['fixture_id']}_deep_{index}")
        if fixture.get("cohort_risk"):
            circular_map[voice_id] = _fixture_persona(
                store, f"Circular voice {index + 1}", fixture["task"]["goal"],
                deep=False, suffix=f"{fixture['fixture_id']}_circular_{index}")
    initial_map = circular_map or deep_map
    return {"initial_map": initial_map, "deep_map": deep_map,
            "initial_ids": list(initial_map.values()), "deep_ids": list(deep_map.values())}


def _representation(protocol: dict[str, Any], persona_map: dict[str, str],
                    store: Store) -> list[dict[str, Any]]:
    posture_map = {"supportive": "target", "skeptical": "skeptical",
                   "indifferent": "indifferent", "rejecting": "non_target"}
    rows = []
    for voice in protocol["voices"]:
        pid = persona_map[voice["voice_id"]]
        row = {"persona_id": pid, "posture": posture_map[voice["stance"]],
               "rationale": f"qualification-declared {voice['stance']} counterposition"}
        if row["posture"] != "target":
            evidence = store.list_evidence(pid)
            if evidence:
                row["basis_quote"] = "existing manual routine is sufficient"
                row["evidence_refs"] = [{"kind": "evidence", "id": evidence[0]["id"]}]
        rows.append(row)
    return rows


def _capabilities(fixture: dict[str, Any], protocol: dict[str, Any], ref: dict[str, str],
                  *, corrected: bool = False) -> list[dict[str, Any]]:
    out = []
    correction = fixture.get("correction") or {}
    for capability in fixture["task"].get("capabilities") or []:
        key = str(capability["key"])
        status = (protocol.get("correction_status") if corrected and key == correction.get("capability_key")
                  else protocol.get("capability_statuses", {}).get(key, ""))
        row: dict[str, Any] = {"key": key, "claim": capability["claim"], "status": status}
        if status in {"observed_present", "observed_absent", "inferred"}:
            row["evidence_refs"] = [ref]
        if status == "observed_absent" and protocol.get("absence_verification_attempt"):
            row["verification_attempt"] = copy.deepcopy(protocol["absence_verification_attempt"])
        if corrected and key == correction.get("capability_key"):
            row["revision_reason"] = "later synthetic observation"
        out.append(row)
    return out


def _record_understanding(fixture: dict[str, Any], protocol: dict[str, Any], project_id: str,
                          ref: dict[str, str], store: Store, *, token: str | None,
                          corrected: bool = False) -> dict[str, Any]:
    inventory = fixture["task"]["inventory"]
    stamp = lambda rows: [{**dict(row), "evidence_refs": [ref]} for row in rows]
    correction = fixture.get("correction") or {}
    return services.record_product_understanding(
        project_id,
        target=fixture["task"]["target"],
        revision=(correction.get("revision") if corrected else fixture["task"]["revision"]),
        routes=stamp(inventory.get("routes") or []),
        flows=stamp(inventory.get("flows") or []),
        states=stamp(inventory.get("states") or []),
        capabilities=_capabilities(fixture, protocol, ref, corrected=corrected),
        evidence_refs=[ref],
        observed_at=("2026-08-08T11:00:00Z" if corrected else "2026-08-08T10:00:00Z"),
        key=(f"qualification:{fixture['fixture_id']}:correction" if corrected else None),
        dispatch_token=token,
        store=store,
    )


def _voice_statement(voice: dict[str, Any], persona_id: str,
                     ref: dict[str, str] | None, posture: str) -> dict[str, Any]:
    stance_value = {"rejecting": -2, "skeptical": -1, "indifferent": 0, "supportive": 1}[voice["stance"]]
    return {
        "persona_id": persona_id,
        "text": voice["text"],
        "stance": {"value": stance_value},
        "refs": [ref] if ref else [],
        "meta": {"qualification_stance": voice["stance"], "claim_posture": posture},
    }


def _drive_job(fixture: dict[str, Any], protocol: dict[str, Any], project_id: str,
               run_id: str, store: Store, state: dict[str, Any]) -> None:
    if protocol["manual_finish_before_done"]:
        state["violations"].append("manual_finish_before_done")
        try:
            services.finish_run(run_id, "finished", store=store)
        except Exception as exc:
            state["guardrail_receipts"].append({"phase": "early_finish", "code": _error_code(exc)})

    try:
        dispatch = services.run_step(run_id, store=store)
        if dispatch.get("step_id") != "preflight__product_understanding":
            raise QualificationError("BAD_FRONTIER", "Reaction Test did not begin with Product Understanding")
        correction_asset = str((fixture.get("correction") or {}).get("asset_id") or "")
        initial_asset_spec = next(
            row for row in fixture["assets"] if row.get("asset_id") != correction_asset)
        asset = services.attach_asset(
            project_id,
            content_base64=base64.b64encode(initial_asset_spec["content"].encode()).decode(),
            filename=initial_asset_spec["filename"], kind=initial_asset_spec.get("kind"),
            title=initial_asset_spec["asset_id"], dispatch_token=_token(protocol, dispatch), store=store)
        ref = _asset_ref(asset)
        _record_understanding(
            fixture, protocol, project_id, ref, store,
            token=_token(protocol, dispatch), corrected=False)
        state["initial_asset_refs"][project_id] = ref
    except Exception as exc:
        _capture_error(state, "product_understanding", exc)
        return

    try:
        dispatch = services.run_step(run_id, store=store)
        services.record_frame(
            project_id, dispatch["step_id"],
            ["What is understood, doubted, rejected, or irrelevant in this bounded stimulus?"],
            hypotheses=["Seeded product claims remain hypotheses, not independent findings."],
            memory_refs=["memory:qualification:synthetic-context"],
            dispatch_token=_token(protocol, dispatch), store=store)
        frame_id = dispatch["step_id"]
    except Exception as exc:
        _capture_error(state, "frame", exc)
        return

    try:
        dispatch = services.run_step(run_id, store=store)
        cohort = state["cohorts"]
        initial_map = cohort["initial_map"]
        gate = services.record_cohort_preflight(
            project_id,
            representation=_representation(protocol, initial_map, store),
            dispatch_token=_token(protocol, dispatch), store=store)
        if gate["status"] in {"needs_deepening", "needs_reselection"}:
            dispatch = services.run_step(run_id, store=store)
            if protocol["cohort_strategy"] == "reselect_independent":
                active_map = cohort["deep_map"]
                gate = services.record_cohort_preflight(
                    project_id, persona_ids=cohort["deep_ids"],
                    selection_rationale="replace circular/thin fixture profiles with independent diary cohort",
                    representation=_representation(protocol, active_map, store),
                    dispatch_token=_token(protocol, dispatch), store=store)
            else:
                active_map = initial_map
                gate = services.record_cohort_preflight(
                    project_id, representation=_representation(protocol, active_map, store),
                    override_rationale=("Qualification adapter explicitly accepts a circular/thin "
                                        "cohort; this must remain a report limitation."),
                    dispatch_token=_token(protocol, dispatch), store=store)
        else:
            active_map = initial_map
        state["cohort_results"][project_id] = gate
        state["project_persona_maps"][project_id] = active_map
    except Exception as exc:
        _capture_error(state, "cohort_integrity", exc)
        return

    try:
        council_ids = []
        for index in range(2):
            dispatch = services.run_step(run_id, store=store)
            evidence_ref = ref if protocol["include_evidence_refs"] else None
            persona_map = state["project_persona_maps"][project_id]
            statements = [_voice_statement(
                v, persona_map[v["voice_id"]], evidence_ref,
                str(protocol.get("claim_posture") or ""))
                          for v in protocol["voices"]]
            claims = ([{
                "text": "Synthetic participants expressed bounded, mixed reactions.",
                "posture": str(protocol.get("claim_posture") or ""),
                "refs": [ref] if evidence_ref else [],
            }] if protocol["explicit_claim_inventory"] else [])
            council = services.record_council(
                project_id, f"Synthetic bounded reaction {index + 1}",
                [persona_map[v["voice_id"]] for v in protocol["voices"]], statements=statements,
                claims=claims, dispatch_token=_token(protocol, dispatch), store=store)
            council_ids.append(council["id"])
        state["council_ids"][project_id] = council_ids
    except Exception as exc:
        _capture_error(state, "councils", exc)
        return

    try:
        dispatch = services.run_step(run_id, store=store)
        gate_refs = ([f"council:{cid}" for cid in council_ids]
                     if protocol["link_gate_evidence"] else [])
        services.record_judgment(
            project_id, dispatch["step_id"], "reaction_complete", True,
            "Two bounded synthetic contrasts are available.", gate_refs,
            dispatch_token=_token(protocol, dispatch), store=store)
        report = protocol["report"]
        evidence_ref = ref if protocol["include_evidence_refs"] else None
        claims = ([{
            "text": report["claim"],
            "posture": str(protocol.get("synthesis_claim_posture") or ""),
            "refs": [ref] if evidence_ref else [],
        }] if protocol["explicit_claim_inventory"] else [])
        synthesis = services.record_synthesis(
            "Synthetic qualification report", fixture["task"]["goal"], council_ids,
            payload={
                "arc_narrative": report["arc_narrative"],
                "gesamtbild": report["gesamtbild"],
                "positionierung": report["positionierung"],
                "claims": claims,
                "findings": [{
                    "text": "Treat the result as a bounded hypothesis, not observed behavior.",
                    "kind": "recommendation", "refs": [ref] if evidence_ref else [],
                    "meta": {"claim_posture": str(protocol.get("synthesis_claim_posture") or "")},
                }],
            },
            project_id=project_id, dispatch_token=_token(protocol, dispatch), store=store)
        state["synthesis_ids"][project_id] = [synthesis["id"]]
    except Exception as exc:
        _capture_error(state, "synthesis_gate", exc)
        return

    for round_index in range(5):
        try:
            dispatch = services.run_step(run_id, store=store)
        except Exception as exc:
            _capture_error(state, "run_step", exc)
            return
        if dispatch.get("step_id") == "__report_handoff__":
            report_copy = protocol["report"]
            bodies = [report_copy["arc_narrative"], report_copy["gesamtbild"],
                      report_copy["positionierung"]]
            try:
                for index, section_id in enumerate(dispatch.get("incomplete_section_ids") or []):
                    services.brief_synthesis_section(
                        project_id, section_id, report_id=dispatch["report_id"], store=store)
                    services.record_synthesis_section(
                        project_id, section_id,
                        {"markdown": bodies[index % len(bodies)], "citations": []},
                        report_id=dispatch["report_id"],
                        dispatch_token=_token(protocol, dispatch), store=store)
                dispatch = services.run_step(run_id, store=store)
            except Exception as exc:
                _capture_error(state, "report_handoff", exc)
                return
        if dispatch.get("kind") == "done":
            return
        if dispatch.get("kind") != "critic":
            state["errors"].append({"phase": "run_loop", "code": "UNEXPECTED_DISPATCH"})
            return
        if round_index >= int(protocol["critic_passes"]):
            return
        scores = {row["key"]: 5 for row in dispatch["brief"]["frame"]["rubric"]}
        verdict = {"passed": True, "missing": [], "scores": scores,
                   "rationale": "The fixed synthetic scope is complete and trace-linked."}
        try:
            critic = services.record_completeness_critic(
                project_id, verdict, run_id, dispatch["operation_id"], store=store)
            services.record_critic_round(run_id, critic["id"], dispatch["key"], store=store)
        except Exception as exc:
            _capture_error(state, "critic", exc)
            return


def _apply_correction(fixture: dict[str, Any], protocol: dict[str, Any], project_id: str,
                      store: Store, state: dict[str, Any]) -> None:
    correction = fixture.get("correction") or {}
    if not correction:
        return
    try:
        asset_spec = next(row for row in fixture["assets"] if row["asset_id"] == correction["asset_id"])
        asset = services.attach_asset(
            project_id,
            content_base64=base64.b64encode(asset_spec["content"].encode()).decode(),
            filename=asset_spec["filename"], kind=asset_spec.get("kind"), title=asset_spec["asset_id"],
            store=store)
        _record_understanding(
            fixture, protocol, project_id, _asset_ref(asset), store,
            token=None, corrected=True)
    except Exception as exc:
        _capture_error(state, "product_understanding_correction", exc)


def _execute_case(fixture: dict[str, Any], submission: dict[str, Any], store: Store) -> dict[str, Any]:
    protocol = submission["protocol"]
    cohorts = _seed_cohorts(fixture, protocol, store)
    state: dict[str, Any] = {
        "errors": [], "violations": [], "guardrail_receipts": [], "frontdoor": [],
        "initial_asset_refs": {}, "council_ids": {}, "synthesis_ids": {},
        "cohorts": cohorts, "cohort_results": {}, "project_persona_maps": {},
    }
    logical_pairs: dict[str, tuple[str, str]] = {}
    for event in fixture["chronology"]:
        event_id, logical_id = event["event_id"], event["logical_request_id"]
        try:
            project = services.start_project(
                f"{fixture['task']['title']} · {logical_id}",
                f"{fixture['task']['goal']} [logical request {logical_id}]",
                methodology=protocol.get("methodology"),
                persona_ids=cohorts["initial_ids"],
                operation_id=protocol["operation_ids"][event_id], store=store)
            run = services.start_run(
                project["id"], budget=24,
                operation_id=protocol["run_operation_ids"][event_id], store=store)
            state["frontdoor"].append({
                "event_id": event_id, "logical_request_id": logical_id,
                "project_id": project["id"], "run_id": run["run_id"],
                "project_replay": bool(project.get("idempotent_replay")),
                "run_replay": bool(run.get("idempotent_replay")),
            })
            logical_pairs.setdefault(logical_id, (project["id"], run["run_id"]))
        except Exception as exc:
            _capture_error(state, f"frontdoor:{event_id}", exc)

    driven: set[tuple[str, str]] = set()
    for project_id, run_id in logical_pairs.values():
        if (project_id, run_id) in driven:
            continue
        driven.add((project_id, run_id))
        _drive_job(fixture, protocol, project_id, run_id, store, state)
    for project_id, _run_id in driven:
        _apply_correction(fixture, protocol, project_id, store, state)
    state["logical_pairs"] = logical_pairs
    return state


def _check(name: str, passed: bool, **detail: Any) -> dict[str, Any]:
    return {"name": name, "score": 1.0 if passed else 0.0,
            "threshold": FIXED_THRESHOLDS["contract_check_min"], "passed": bool(passed),
            "detail": detail}


def _capability_map(record: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    return {str(row.get("key") or ""): row for row in (record or {}).get("capabilities") or []}


def _score_case(fixture: dict[str, Any], submission: dict[str, Any], state: dict[str, Any],
                store: Store) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    frontdoor = state["frontdoor"]
    project_ids = sorted({row["project_id"] for row in frontdoor})
    run_ids = sorted({row["run_id"] for row in frontdoor})
    projects = [store.get_research_project(pid) or {} for pid in project_ids]
    runs = [store.get_run(rid) or {} for rid in run_ids]
    expected_jobs = int(fixture["expected"]["logical_jobs"])

    method_ok = len(projects) == expected_jobs and all(
        p.get("methodology") == "reaction_test"
        and (store.get_research_plan(p.get("id", "")) or {}).get("methodology") == "reaction_test"
        for p in projects)

    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in frontdoor:
        grouped.setdefault(row["logical_request_id"], []).append(row)
    duplicate_ok = (
        len(projects) == len(runs) == expected_jobs == len(grouped)
        and all(len({r["project_id"] for r in rows}) == 1
                and len({r["run_id"] for r in rows}) == 1 for rows in grouped.values())
        and len({next(iter({r["project_id"] for r in rows})) for rows in grouped.values()}) == expected_jobs
        and len(frontdoor) == len(fixture["chronology"])
    )

    journals = [services.run_journal(rid, store=store) for rid in run_ids]
    state_ok = (
        not state["errors"] and not state["violations"] and len(runs) == expected_jobs
        and all(run.get("status") == "finished" for run in runs)
        and all(j.get("cursor") == len(j.get("steps") or [])
                and all(step.get("dispatch_token") for step in j.get("steps") or [])
                for j in journals)
    )

    expected_initial = fixture["expected"].get("initial_capability_statuses") or {}
    pu_ok = len(projects) == expected_jobs
    falsification_ok = len(projects) == expected_jobs
    for project in projects:
        history = project.get("product_understanding_versions") or []
        current = current_product_understanding(project)
        pu_ok = pu_ok and bool(current) and bool(admitted_stimuli(project["id"], store))
        if not history:
            falsification_ok = False
            continue
        initial_map = _capability_map(history[0])
        falsification_ok = falsification_ok and all(
            (initial_map.get(key) or {}).get("status") == status
            for key, status in expected_initial.items())
        correction = fixture.get("correction") or {}
        if correction:
            latest = _capability_map(current)
            corrected = latest.get(correction["capability_key"]) or {}
            falsification_ok = (
                falsification_ok and len(history) >= 2
                and corrected.get("status") == correction["expected_status"]
                and bool(corrected.get("supersedes"))
            )
        else:
            falsification_ok = falsification_ok and all(
                row.get("status") != "observed_absent" for row in initial_map.values()
                if expected_initial.get(str(row.get("key") or "")) == "unknown")

    cohort_ok = len(projects) == expected_jobs
    cohort_details = []
    for project in projects:
        history = project.get("cohort_preflight_versions") or []
        current_gate = current_cohort_preflight(project)
        risk = bool(fixture.get("cohort_risk"))
        initial_triggered = bool(
            history and history[0].get("raw_status") == "needs_reselection"
            and "HYPOTHESIS_PROFILE_LEAKAGE" in {
                row.get("code") for row in history[0].get("required_work") or []}
        )
        passed = bool(current_gate and current_gate.get("status") == "pass")
        cohort_ok = cohort_ok and passed and (initial_triggered if risk else True)
        cohort_details.append({"project_id": project.get("id"), "versions": len(history),
                               "current_status": (current_gate or {}).get("status"),
                               "initial_leakage_triggered": initial_triggered})

    councils = [row for row in store.list_council_sessions()
                if row.get("project_id") in project_ids]
    # Score provider-authored, dispatch-bound answers. ``run_step`` also creates a
    # deterministic report scaffold during finish work; that structural shell is
    # not an authored claim artifact and must not be miscounted as unsupported.
    authored_synthesis_ids = {
        sid for ids in state.get("synthesis_ids", {}).values() for sid in ids
    }
    syntheses = [row for row in store.list_syntheses()
                 if row.get("project_id") in project_ids and row.get("id") in authored_synthesis_ids]
    postured = councils + syntheses
    posture_ok = bool(postured) and all(
        (row.get("claim_posture") or {}).get("schema") == CLAIM_POSTURE_SCHEMA
        and (row.get("claim_posture") or {}).get("verified") is True
        and int(((row.get("claim_posture") or {}).get("counts") or {}).get("unsupported") or 0) == 0
        for row in postured)

    trace_ok = len(projects) == expected_jobs
    for project in projects:
        plan = store.get_research_plan(project["id"]) or {}
        relevant = [task for task in plan.get("tasks") or []
                    if task.get("bucket") in {"act", "verify"}
                    or task.get("capability") in {"product_understanding", "cohort_integrity"}]
        judgments = plan.get("judgments") or []
        cited = {str(ref) for row in judgments for ref in row.get("evidence_refs") or []}
        project_councils = [c for c in councils if c.get("project_id") == project["id"]]
        trace_ok = (
            trace_ok and bool(relevant)
            and all(task.get("status") == "done" and task.get("produces") for task in relevant)
            and all(f"council:{c['id']}" in cited for c in project_councils)
        )
    trace_ok = trace_ok and all(
        all(step.get("produced_refs") for step in journal.get("steps") or []) for journal in journals)

    required_critics = int(fixture["expected"].get("required_critic_passes") or 2)
    critic_ok = len(journals) == expected_jobs and all(
        len({row.get("critic_report_id") for row in journal.get("critic_rounds") or []
             if row.get("passed") and not row.get("missing")}) >= required_critics
        and journal.get("status") == "finished"
        for journal in journals)

    actual_stances = {
        str((statement.get("meta") or {}).get("qualification_stance") or "")
        for council in councils for statement in council.get("statements") or []
    }
    required_stances = set(fixture["expected"].get("required_stances") or [])
    stance_ok = required_stances <= actual_stances and bool(councils)

    checks = [
        _check("methodology_resolution", method_ok, canonical="reaction_test",
               projects=len(projects)),
        _check("duplicate_suppression", duplicate_ok, logical_jobs=len(grouped),
               projects=len(projects), runs=len(runs), chronology_events=len(frontdoor)),
        _check("state_machine_compliance", state_ok, errors=state["errors"],
               violations=state["violations"], finished=sum(r.get("status") == "finished" for r in runs)),
        _check("product_understanding_stimulus", pu_ok, schema=PRODUCT_UNDERSTANDING_SCHEMA,
               projects_with_preflight=sum(bool(current_product_understanding(p)) for p in projects)),
        _check("cohort_integrity", cohort_ok, schema=COHORT_PREFLIGHT_SCHEMA,
               projects=cohort_details, strategy=submission["protocol"].get("cohort_strategy")),
        _check("app_inventory_falsification", falsification_ok,
               expected_initial_statuses=expected_initial,
               correction_required=bool(fixture.get("correction"))),
        _check("claim_posture", posture_ok, artifacts=len(postured), schema=CLAIM_POSTURE_SCHEMA,
               unsupported=sum(int(((r.get("claim_posture") or {}).get("counts") or {}).get("unsupported") or 0)
                               for r in postured)),
        _check("trace_linking", trace_ok, journals=len(journals)),
        _check("critic_completion", critic_ok, required_distinct_passes=required_critics,
               passes=[len(j.get("critic_rounds") or []) for j in journals]),
        _check("skeptical_indifferent_output", stance_ok,
               required=sorted(required_stances), actual=sorted(actual_stances)),
    ]
    verified_artifacts = sum(bool((row.get("claim_posture") or {}).get("verified")) for row in postured)
    metrics = {
        "completion": {"finished_jobs": sum(r.get("status") == "finished" for r in runs),
                       "expected_jobs": expected_jobs},
        "groundedness": {"verified_posture_artifacts": verified_artifacts,
                         "postured_artifacts": len(postured)},
        "unsupported_claims": sum(
            int(((row.get("claim_posture") or {}).get("counts") or {}).get("unsupported") or 0)
            for row in postured),
        "retries": sum(row.get("kind") == "resume" for row in fixture["chronology"]),
        "tool_errors": len(state["errors"]),
        "latency_ms": submission["metrics"]["latency_ms"],
        "input_tokens": submission["metrics"].get("input_tokens"),
        "output_tokens": submission["metrics"].get("output_tokens"),
        "cost_usd": submission["metrics"].get("cost_usd"),
    }
    return checks, metrics
