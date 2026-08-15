from __future__ import annotations

import time
from typing import Any

from ..config import MEMORY_SCHEMA_VERSION

SERVER_VERSION = "0.2.0"

# Implicit decision DAG: each tool hints the natural next
# step so the host agent can route the simulate -> consolidate -> digest loop.
_NEXT: dict[str, dict[str, Any]] = {
    "brief_persona": {"name": "record_persona", "reason": "persist the profile JSON you authored"},
    "list_examples": {"name": "load_example", "reason": "load a shipped example project to explore a fully populated inspector"},
    # --- persona catalog (sonaloop-data): browse -> (recommend) -> pull into the store.
    #     list_personas and assess_coverage lead INTO the cluster, so an agent that needs
    #     a (better) cohort discovers the 300+ ready-made personas instead of authoring blind. ---
    "list_personas": {"name": "catalog_search", "reason": "cohort thin or empty? browse 300+ ready-made catalog personas before authoring new ones"},
    "assess_coverage": {"name": "catalog_recommend", "reason": "fill the detected gaps from the curated catalog (deterministic set recommendation)"},
    "catalog_search": {"name": "catalog_pull", "reason": "pull the chosen personas/pack into this store with provenance"},
    "catalog_recommend": {"name": "catalog_pull", "reason": "pull the recommended set by slug into this store"},
    "catalog_status": {"name": "catalog_pull", "reason": "refresh the behind personas (force=True for locally modified ones)"},
    "catalog_pull": {"name": "list_personas", "reason": "confirm what landed and pick the cohort"},
    "record_persona": {"name": "brief_day", "reason": "plan the persona's first day before simulating"},
    "brief_day": {"name": "record_day", "reason": "author day_plan + activities, then persist the whole day"},
    "record_day": {"name": "brief_consolidation", "reason": "consolidate the day into memory"},
    "put_day_plan": {"name": "record_day", "reason": "persist the authored day (plan + activities)"},
    "brief_consolidation": {"name": "record_memory_deltas", "reason": "persist the entities/facts/threads you extracted"},
    "record_memory_deltas": {"name": "evaluate_simulation", "reason": "check quality, or brief_digest to roll up"},
    "brief_period": {"name": "put_period_plan", "reason": "persist the period plan + its sample_days"},
    "put_period_plan": {"name": "record_month_bundle", "reason": "persist the authored sampled days as a month bundle"},
    "brief_digest": {"name": "put_digest", "reason": "persist the digest you authored"},
    "brief_persona_revision": {"name": "record_persona_revision", "reason": "persist the (usually small) identity drift"},
    "recall_memory": {"name": "get_project", "reason": "open the timeline of a project a hit pointed to"},
    "list_active_projects": {"name": "get_project", "reason": "open one project's full timeline"},
    "get_persona": {"name": "get_persona_memory", "reason": "see the rendered memory (active projects, threads)"},
    "brief_eval_critic": {"name": "record_eval_critic", "reason": "persist the semantic verdict you authored"},
    "record_eval_critic": {"name": "evaluate_simulation_full", "reason": "combined structural+semantic top verdict"},
    "brief_cohort_critic": {"name": "record_cohort_critic", "reason": "persist the cohort outlier verdict you authored"},
    "create_research_project": {"name": "start_run", "reason": "create the run object, then loop run_step"},
    "available_project_icons": {"name": "set_project_icon", "reason": "choose one of the existing icons for a project"},
    "set_project_icon": {"name": "get_project_graph", "reason": "inspect the project with its updated icon"},
    "generate_project_icon": {"name": "get_project_graph", "reason": "inspect the project with its generated custom icon"},
    "brief_synthesis_outline": {"name": "record_synthesis_outline", "reason": "persist the outline you derived from the graph"},
    "record_synthesis_outline": {"name": "brief_synthesis_section", "reason": "author each section grounded in its source studies"},
    "brief_synthesis_section": {"name": "record_synthesis_section", "reason": "persist the authored section + citations"},
    "record_synthesis_section": {"name": "export_synthesis", "reason": "render the assembled report (by report id)"},
    "brief_month": {"name": "record_month_bundle", "reason": "persist the authored month bundle through the loop"},
    "record_month_bundle": {"name": "brief_month", "reason": "continue with the next month"},
    "brief_evidence_check": {"name": "record_evidence_check", "reason": "persist provenance verdict (confirmed/contradicted)"},
    "brief_synthesis": {"name": "record_synthesis", "reason": "persist the cross-council synthesis you authored"},
    "record_synthesis": {"name": "export_synthesis", "reason": "render the stakeholder report"},
    "brief_council": {"name": "record_council", "reason": "author the turns + synthesis, then persist the council"},
    "suggest_stances": {"name": "record_council", "reason": "author every stance/vote with the canonical terms, then persist"},
    "suggest_finding_kinds": {"name": "record_council", "reason": "author the findings with a suggested (or invented) kind, then persist (or record_synthesis — findings are the one analysis shape in both)"},
    "record_council": {"name": "brief_synthesis", "reason": "fold this council into a synthesis when you have several"},
    # --- jobs = the taxonomy's JOB layer: presets + the sharpen-the-question helper ---
    "list_job_presets": {"name": "get_job_preset", "reason": "read one Job's full recipe card before seeding from it"},
    "get_job_preset": {"name": "start_job_study", "reason": "seed a study's plan from the preset (framework + formats + coverage)"},
    "sharpen_question": {"name": "start_job_study", "reason": "hand the ready study_spec into the matched preset (or start_project for off-menu)"},
    "start_job_study": {"name": "assess_coverage", "reason": "check the persona panel against the Job's declared coverage before running"},
    # --- methodologies = plan SEEDS; the runtime engine is the plan (spec/hx3-engine-collapse.md) ---
    "list_frameworks": {"name": "describe_framework", "reason": "read one Framework's plain-language shape before choosing it"},
    "describe_framework": {"name": "start_project", "reason": "start_project(methodology=<id>) runs the study through this Framework"},
    "list_methodologies": {"name": "get_methodology", "reason": "inspect a constellation's steps before starting"},
    "get_methodology": {"name": "start_project", "reason": "start_project(methodology=<key>) seeds the plan"},
    "register_methodology": {"name": "start_project", "reason": "start_project(methodology=<your key>) seeds a study's plan from the new constellation"},
    "admit_remote_screenshot": {"name": "run_step", "reason": "review the exact capture inventory before adding another screen or freezing the flow"},
    "record_reaction_test_capture_review": {"name": "run_step", "reason": "continue the same run for another capture or exact flow freeze"},
    "record_flow_manifest": {"name": "brief_product_understanding", "reason": "inspect and cover the exact manifest version before personas react"},
    "record_manifest_product_understanding": {"name": "run_step", "reason": "Product Understanding is checkpointed; continue the same governed run"},
    "select_reaction_test_cohort": {"name": "run_step", "reason": "cohort selection is a supporting write; continue the same open frame dispatch"},
    "set_project_methodology": {"name": "next_action", "reason": "load the next ready plan step fully"},
    "brief_next": {"name": "next_action", "reason": "load the ready task fully (grounding + participants + gate)"},
    "next_action": {"name": "complete_task", "reason": "author the step (frame/council/synthesis), persist, then complete"},
    "record_judgment": {"name": "complete_task", "reason": "complete the verify once its gate judgment is recorded"},
    "iterate_task": {"name": "next_action", "reason": "load the new round's first ready task fully"},
    "suggest_capabilities": {"name": "suggest_methodologies", "reason": "browse suggested step/whole-methodology templates"},
    # --- prototypes + harness ---
    "scaffold_prototype": {"name": "run_prototype", "reason": "start the generated app locally"},
    "run_prototype": {"name": "proto_open", "reason": "open the running app in a headless browser session"},
    "proto_open": {"name": "proto_act", "reason": "act on the snapshot (click/type), or proto_read"},
    "brief_prototype_session": {"name": "proto_open", "reason": "drive the app as the persona, then record the session"},
    "record_prototype_session": {"name": "brief_council", "reason": "fold the grounded reaction into a test council"},
    # --- surveys (the outbound instrument: author → send out → real responses back) ---
    "brief_survey": {"name": "record_survey", "reason": "author the questions (+ derived_from refs), then persist the instrument"},
    "record_survey": {"name": "export_survey", "reason": "render the sendable, self-contained HTML form"},
    "export_survey": {"name": "import_survey_responses", "reason": "when the real responses come back, ingest the batch"},
    "import_survey_responses": {"name": "survey_results", "reason": "aggregate per question — predicted-vs-actual for stance_mapped"},
    "survey_results": {"name": "attach_survey_evidence", "reason": "loop the real responses back onto a persona as calibration evidence"},
    # --- hypotheses (falsifiable predictions scored against reality) ---
    "brief_hypothesis": {"name": "record_hypothesis", "reason": "author the falsifiable statement + checkable prediction, then persist the open bet"},
    "record_hypothesis": {"name": "record_hypothesis_result", "reason": "when reality answers, attach the observation — the status derives from observed vs predicted"},
    "record_hypothesis_result": {"name": "eval_scorecard", "reason": "aggregate the hit-rate across resolved hypotheses into the calibration record"},
    # --- live walkthroughs (rung 3: policy-guarded real-SaaS sessions; one harness with proto_*) ---
    "walk_policy_defaults": {"name": "walk_open", "reason": "open the live walkthrough under the (possibly tweaked) safety policy"},
    "walk_open": {"name": "proto_act", "reason": "drive the live app on snapshot refs — policy refusals come back structured, never as crashes"},
    "walk_own": {"name": "proto_act", "reason": "drive the owned surface on snapshot refs; record with fidelity='live' + session_id so states verify"},
    "record_actuation_gate": {"name": "flow_funnel", "reason": "the gate is recorded — fold the winning rung's sessions into the funnel"},
    # --- usability sessions (the durable, replayable trace) ---
    "brief_usability_session": {"name": "record_usability_session", "reason": "author the per-step dual timeline, then persist the replayable trace"},
    "suggest_friction_levels": {"name": "record_usability_session", "reason": "author every step's friction with the canonical levels, then persist"},
    "record_usability_session": {"name": "get_session_funnel", "reason": "aggregate this subject's sessions into the step funnel"},
    "suggest_tech_comfort": {"name": "update_persona", "reason": "patch capabilities.tech_comfort with a canonical level (the hint is the behavioral contract)"},
    "preview_persona_update": {"name": "update_persona", "reason": "review the impact, then apply the exact patch/version and confirmation token when required"},
    "persona_readiness": {"name": "begin_persona_build", "reason": "resolve readiness gaps through one resumable governed lifecycle"},
    "brief_persona_memory_onboarding": {"name": "begin_persona_build", "reason": "start the resumable lifecycle with a stable operation_id"},
    "begin_persona_build": {"name": "persona_build_step", "reason": "after recording the returned dispatch output, re-assess and advance"},
    "persona_build_step": {"name": "persona_build_step", "reason": "execute this dispatch, then continue the same build"},
    "persona_task_readiness": {"name": "prepare_persona_for_task", "reason": "freeze the exact context when the task gate is acceptable"},
    "prepare_persona_for_task": {"name": "get_persona_context_snapshot", "reason": "re-open the frozen context later without re-running recall"},
    "validate_persona_output": {"name": "record_persona_voice_check", "reason": "author and persist the semantic voice verdict against this exact context"},
    "record_persona_voice_check": {"name": "prepare_persona_for_task", "reason": "use a green, context-bound voice gate for the actual assignment"},
    # --- lifecycle hooks (docs/lifecycle-hooks.md) ---
    "list_lifecycle_events": {"name": "register_hook", "reason": "subscribe a command/webhook to the event you picked"},
    "register_hook": {"name": "test_hook", "reason": "fire a sample envelope through the new hook to verify delivery"},
    # --- project assets: files/images/screenshots as evidence (docs/project-assets.md) ---
    "attach_asset": {"name": "view_asset", "reason": "look at what you just attached (images render as pixels) before citing it"},
    "attach_prototype_shot": {"name": "view_asset", "reason": "look at the captured shot before citing it"},
    "view_asset": {"name": "brief_council", "reason": "the evidence is in the room — councils ground reactions in it automatically"},
    # --- the queryable substrate (docs/substrate.md) ---
    "substrate_schema": {"name": "query_projects", "reason": "pin the contract, then page through the projects"},
    "query_projects": {"name": "get_study_result", "reason": "pull one project's full structured result (the automation shape)"},
    "chat_with_persona": {"name": "record_chat_turn", "reason": "author the in-character reply, then persist the exchange"},
    "brief_memory_from_chat": {"name": "record_memory_proposal", "reason": "author only a bounded conversation-continuity proposal"},
    "record_memory_proposal": {"name": "review_memory_proposal", "reason": "explicitly approve or reject before future chats may use it"},
    "review_memory_proposal": {"name": "chat_with_persona", "reason": "approved continuity is now available to a new chat without changing identity or facts"},
    # --- grounding in real material (docs/grounding.md) ---
    "ingest_corpus": {"name": "brief_grounding", "reason": "author a persona (or a patch) from the real chunks, with provenance"},
    "brief_grounding": {"name": "record_grounding", "reason": "persist the provenance (claim -> chunk ids) you authored (record_persona first for a NEW persona)"},
    "record_grounding": {"name": "prepare_persona_agent_context", "reason": "sessions now carry the grounded chunks — cite them as evidence refs"},
    # --- predicted behavior (the calibration substrate) ---
    "suggest_likelihood_levels": {"name": "record_usability_session", "reason": "author predicted_behaviors with the canonical likelihoods + evidence refs, then persist"},
    "aggregate_predictions": {"name": "brief_hypothesis", "reason": "promote a recurring predicted behavior into a falsifiable bet"},
    # --- the calibration backtest loop (docs/calibration.md) ---
    "record_prediction_outcome": {"name": "calibration_report", "reason": "measure the cohort's calibration with the new observation in"},
    "calibration_report": {"name": "brief_calibration", "reason": "gather the misses and author the corrections"},
    "brief_calibration": {"name": "record_calibration_round", "reason": "stamp the corrections you applied so the trend can judge them"},
    "record_calibration_round": {"name": "calibration_trend", "reason": "did the loop improve? the Brier delta answers"},
    # --- screenshot flows: walkthrough with drop-off (docs/flow-walkthrough.md) ---
    "define_flow": {"name": "brief_flow_walkthrough", "reason": "walk a persona through the flow's real screens (artifact-first, no browser)"},
    "brief_flow_walkthrough": {"name": "record_usability_session", "reason": "author the dual timeline you walked, then persist (same flow subject → the funnel aggregates)"},
    "flow_funnel": {"name": "brief_synthesis", "reason": "fold the drop-off story (steps, reasons, personas) into the answer"},
    "record_chat_turn": {"name": "chat_with_persona", "reason": "continue the conversation with full history (pass chat_id)"},
}


# --- First-contact orientation (ticket one-sentence-mcp-install) -------------------------
# After a cold one-liner install the host's first call is usually a list/next tool on an EMPTY
# database. Instead of a bare empty list, those entry tools carry ONE short "you're new here"
# note (what to create first: project → personas → council, plus where the guide lives). The
# note appears only while the DB has neither projects nor personas, so it never repeats once
# real work exists — and only on this entry set, so brief_*/record_* chains stay clean.
_ENTRY_TOOLS = {
    "list_personas", "list_research_projects", "list_active_projects", "list_councils",
    "list_syntheses", "list_methodologies", "list_frameworks", "list_job_presets",
    "query_projects", "substrate_schema", "next_action", "brief_next",
}

_ORIENTATION = (
    "You're new here — the database is empty. First steps: 1) create a research project "
    "(start_project(title, goal) — the front door for any research question), 2) get a cohort: "
    "the curated catalog has 300+ ready-made personas with lived memory — catalog_search / "
    "catalog_recommend → catalog_pull — and authoring from scratch (brief_persona → you write "
    "the profile JSON → record_persona) is for what the catalog lacks, 3) run a first "
    "council (brief_council → author each statement in character → record_council). The full "
    "operating contract + first-run recipe is the sonaloop://guide/catalogue resource (or "
    "`sonaloop guide`); start `sonaloop-web` so the user can watch at http://127.0.0.1:8787."
)


def _db_is_empty() -> bool:
    """True only when the runtime DB has neither personas nor research projects.
    Fail-soft by contract: any storage hiccup means 'not empty' (no note, no error)."""
    try:
        from ..storage import Store

        store = Store()
        try:
            for table in ("personas", "research_projects"):
                if store.conn.execute(f"SELECT 1 FROM {table} LIMIT 1").fetchone():
                    return False
        finally:
            store.close()
        return True
    except Exception:
        return False


def _env(tool: str, data: Any, started: float) -> dict[str, Any]:
    nxt = _NEXT.get(tool)
    # Ungoverned-loop override: when the engine flags `run_state` (open multi-task plan, no active
    # run), the natural next step is start_run — for EVERY host, including ones that read neither
    # skills nor prompts. The static DAG hint yields to this dynamic one.
    if isinstance(data, dict):
        action = data.get("blocking_action") or data.get("action")
        next_call = action.get("next_call") if isinstance(action, dict) else None
        if isinstance(next_call, dict) and next_call.get("tool"):
            nxt = {"name": str(next_call["tool"]),
                   "reason": str(action.get("message") or "execute the one server-owned remediation")}
        rs = data.get("run_state")
        if isinstance(rs, dict) and rs.get("active_run") is False:
            nxt = {"name": "start_run",
                   "reason": rs.get("note") or "no active run — govern the loop before continuing"}
        trace_nudge = data.get("trace_nudge")
        if isinstance(trace_nudge, dict) and trace_nudge.get("next_tool"):
            nxt = {"name": trace_nudge["next_tool"],
                   "reason": trace_nudge.get("message") or "repair the task's trace link before continuing"}
        elif data.get("must_link_before_complete"):
            nxt = {"name": "link_evidence",
                   "reason": "after recording the task output, link it to this task before complete_task"}
    meta: dict[str, Any] = {
        "tool": tool,
        "latency_ms": round((time.perf_counter() - started) * 1000, 1),
        "server_version": SERVER_VERSION,
        "schema_version": MEMORY_SCHEMA_VERSION,
    }
    if isinstance(data, dict):
        from ..correlation import workflow_trace_from_payload
        trace = workflow_trace_from_payload(data)
        if trace:
            meta["workflow_trace_id"] = trace
    env: dict[str, Any] = {
        "ok": True,
        "data": data,
        "next_recommended_tool": nxt,
        "_meta": meta,
    }
    if tool in _ENTRY_TOOLS and _db_is_empty():
        env["orientation"] = _ORIENTATION
    return env
