"""MCP ToolAnnotations for every core tool — the ONE place titles + hints live.

Directory gate (ticket mcp-tool-annotations): every tool ships `title`,
`readOnlyHint`, `destructiveHint` and an explicit `openWorldHint`
(`idempotentHint` only where it is obviously true). `apply_annotations` is
called once from `build_server()` after the core `register_*` calls; the
registry below is keyed by tool name, and tests/test_mcp_annotations.py keeps
it in exact sync with the registered surface (a bare new tool fails CI).

Classification rules (be correct over fast — a wrong readOnlyHint=True on a
writing tool is the worst outcome, the cloud entitlement gate trusts these):
- R: pure read — touches no store row and writes no file.
- W: ordinary write/upsert (incl. exports that WRITE files, e.g. export_survey,
  and `get_persona_memory`, which renders MEMORY.md to disk).
- D: genuinely destructive (delete_*/remove_*/drop_*/unregister_* — data loss).
- open_world=True: the tool itself talks to the outside world — catalog HTTP,
  live URL capture, avatar provider API, webhook delivery, browser sessions.
  (Fail-soft embedding enrichment inside memory writes does NOT count.)
"""
from __future__ import annotations

from typing import Any


def _spec(title: str, *, read_only: bool, destructive: bool,
          open_world: bool, idempotent: bool | None) -> dict[str, Any]:
    out: dict[str, Any] = {"title": title, "readOnlyHint": read_only,
                           "destructiveHint": destructive, "openWorldHint": open_world}
    if idempotent is not None:
        out["idempotentHint"] = idempotent
    return out


def R(title: str, *, open_world: bool = False, idempotent: bool | None = None) -> dict[str, Any]:
    """A pure read — no store mutation, no file written."""
    return _spec(title, read_only=True, destructive=False, open_world=open_world, idempotent=idempotent)


def W(title: str, *, open_world: bool = False, idempotent: bool | None = None) -> dict[str, Any]:
    """An ordinary (non-destructive) write."""
    return _spec(title, read_only=False, destructive=False, open_world=open_world, idempotent=idempotent)


def D(title: str, *, open_world: bool = False, idempotent: bool | None = None) -> dict[str, Any]:
    """A genuinely destructive operation (deletes/discards data)."""
    return _spec(title, read_only=False, destructive=True, open_world=open_world, idempotent=idempotent)


TOOL_ANNOTATIONS: dict[str, dict[str, Any]] = {
    # ---- assets (_tools_assets) ----
    "attach_asset": W("Attach project asset", idempotent=True),  # idempotent on content (stable id)
    "attach_prototype_shot": W("Attach prototype screenshot", open_world=True),  # Playwright capture
    "list_assets": R("List project assets"),
    "get_asset": R("Get asset"),
    "view_asset": R("View asset content"),
    "inspect_reaction_test_screen": W("Inspect Reaction Test screen", idempotent=True),
    "remove_asset": D("Remove project asset"),

    # ---- calibration (_tools_calibration) ----
    "record_prediction_outcome": W("Record prediction outcome"),
    "calibration_report": W("Snapshot calibration report"),  # NOT read-only: persists the snapshot
    "calibration_trend": R("Get calibration trend"),
    "brief_calibration": R("Brief calibration corrections"),
    "record_calibration_round": W("Record calibration round"),

    # ---- catalog (_tools_catalog) — remote index over HTTP ----
    "catalog_search": R("Search persona catalog", open_world=True),
    "catalog_recommend": R("Recommend catalog personas", open_world=True),
    "catalog_status": R("Check catalog sync status", open_world=True),
    "catalog_pull": W("Pull catalog personas", open_world=True),

    # ---- primitive/form taxonomy (_tools_taxonomy) ----
    "list_primitives": R("List primitive taxonomy"),
    "list_forms": R("List primitive forms"),
    "get_form": R("Get primitive form"),
    "suggest_forms": R("Suggest primitive forms"),

    # ---- councils & reports (_tools_council) ----
    "add_artifact": W("Add artifact", open_world=True),  # captures a live URL snapshot
    "list_artifacts": R("List artifacts"),
    "get_artifact": R("Get artifact"),
    "delete_artifact": D("Delete artifact"),
    "suggest_stances": R("Suggest stances"),
    "suggest_finding_kinds": R("Suggest finding kinds"),
    "brief_council": R("Brief council"),
    "brief_ask": R("Brief persona ask"),
    "record_council": W("Record council session"),
    "get_council": R("Get council session"),
    "brief_head_to_head": R("Brief head-to-head"),
    "record_head_to_head": W("Record head-to-head"),
    "get_head_to_head": R("Get head-to-head"),
    "brief_price_ladder": R("Brief price ladder"),
    "record_price_ladder": W("Record price ladder"),
    "get_price_ladder": R("Get price ladder"),
    "price_ladder_analysis": R("Analyze price ladder"),
    "brief_red_team": R("Brief red team"),
    "record_red_team": W("Record red team"),
    "get_red_team": R("Get red team"),
    "list_councils": R("List council sessions"),
    "export_council_session": R("Export council session"),  # returns the document inline
    "brief_synthesis": R("Brief synthesis"),
    "record_synthesis": W("Record synthesis"),
    "get_synthesis": R("Get synthesis"),
    "list_syntheses": R("List syntheses"),
    "export_synthesis": W("Export synthesis"),  # pdf/pptx/out_path write files + record an asset
    "export_synthesis_html": W("Export synthesis HTML bundle"),  # writes the share bundle

    # ---- decisions (_tools_decisions) ----
    "record_decision": W("Record decision"),
    "update_decision": W("Update decision", idempotent=True),
    "get_decision": R("Get decision"),
    "list_decisions": R("List decisions"),

    # ---- world/eval (_tools_eval) ----
    "set_world_context": W("Set world context", idempotent=True),  # stable-id upsert
    "get_world_context": R("Get world context"),
    "get_language": R("Get language settings"),
    "set_language": W("Set language", idempotent=True),
    "brief_persona_revision": R("Brief persona revision"),
    "record_persona_revision": W("Record persona revision"),
    "list_persona_revisions": R("List persona revisions"),
    "list_memory_anomalies": R("List memory anomalies"),
    "evaluate_simulation": W("Evaluate simulation quality"),  # persists the eval record
    "brief_eval_critic": R("Brief eval critic"),
    "record_eval_critic": W("Record eval critic verdict"),
    "evaluate_simulation_full": W("Evaluate simulation (full)"),  # persists via evaluate_simulation
    "evaluate_cohort_diversity": W("Evaluate cohort diversity"),  # persists the eval record
    "brief_cohort_critic": R("Brief cohort critic"),
    "record_cohort_critic": W("Record cohort critique"),
    "brief_completeness_critic": R("Brief completeness critic"),
    "record_completeness_critic": W("Record completeness verdict"),
    "cohort_memory_depth": R("Measure cohort memory depth"),
    "brief_cohort_preflight": R("Brief cohort integrity preflight"),
    "select_reaction_test_cohort": W("Select Reaction Test cohort", idempotent=True),
    "record_cohort_preflight": W("Record cohort integrity preflight", idempotent=True),
    "get_cohort_preflight": R("Get cohort integrity preflight"),
    "score_run": W("Score run"),
    "brief_evidence_check": R("Brief evidence check"),
    "record_evidence_check": W("Record evidence check"),

    # ---- examples (_tools_examples) ----
    "list_examples": R("List example projects"),
    "load_example": W("Load example project"),
    "remove_example": D("Remove example project"),

    # ---- retrieval (_tools_retrieval) — the cross-host search/fetch contract (ChatGPT) ----
    "search": R("Search research records"),
    "fetch": R("Fetch research record"),

    # ---- flows (_tools_flows) ----
    "record_flow_manifest": W("Record secure flow manifest", idempotent=True),
    "record_reaction_test_capture_review": W("Review Reaction Test capture", idempotent=True),
    "list_flow_manifests": R("List secure flow manifests"),
    "get_flow_manifest": R("Get secure flow manifest"),
    "define_flow": W("Define flow"),
    "list_flows": R("List flows"),
    "brief_flow_walkthrough": R("Brief flow walkthrough"),
    "flow_funnel": R("Get flow funnel"),

    # ---- remote screenshot admission (_tools_assets) ----
    "admit_remote_screenshot": W("Admit remote screenshot", idempotent=True),

    # ---- grounding (_tools_grounding) ----
    "ingest_corpus": W("Ingest corpus", idempotent=True),  # local text/file; idempotent on content
    "list_corpora": R("List corpora"),
    "get_corpus": R("Get corpus"),
    "search_corpus": R("Search corpus"),
    "brief_grounding": R("Brief grounding"),
    "record_grounding": W("Record grounding"),
    "trace_evidence": R("Trace evidence"),

    # ---- hooks (_tools_hooks) ----
    "list_lifecycle_events": R("List lifecycle events"),
    "register_hook": W("Register hook"),
    "unregister_hook": D("Unregister hook"),
    "list_hooks": R("List hooks"),
    "test_hook": W("Test hook delivery", open_world=True),  # fires the webhook/command target

    # ---- hypotheses (_tools_hypotheses) ----
    "brief_hypothesis": R("Brief hypothesis"),
    "record_hypothesis": W("Record hypothesis"),
    "record_hypothesis_result": W("Record hypothesis result"),
    "drop_hypothesis": D("Drop hypothesis"),
    "eval_scorecard": R("Get hypothesis scorecard"),
    "get_hypothesis": R("Get hypothesis"),
    "list_hypotheses": R("List hypotheses"),

    # ---- ideation (_tools_ideation) ----
    "record_hmw_reframe": W("Record HMW reframe"),
    "record_ideas": W("Record ideas"),
    "list_ideas": R("List ideas"),
    "record_ideation_summary": W("Record ideation summary"),
    "get_ideation": R("Get ideation summary"),

    # ---- jobs (_tools_jobs) ----
    "list_job_presets": R("List job presets"),
    "get_job_preset": R("Get job preset"),
    "sharpen_question": R("Sharpen research question"),  # deterministic, no persistence
    "start_job_study": W("Start job study"),

    # ---- result schemas/contracts (_tools_result_schemas) ----
    "list_result_schemas": R("List result schemas"),
    "get_result_schema": R("Get result schema"),
    "list_result_contracts": R("List result contracts"),
    "result_contract_for_job": R("Get job result contract"),
    "result_contract_for_methodology": R("Get methodology result contract"),
    "set_project_result_schemas": W("Set project result schemas", idempotent=True),
    "record_job_outcome": W("Record job outcome", idempotent=True),
    "project_result_contract_state": R("Get project result contract state"),

    # ---- methodology (_tools_methodology) ----
    "suggest_capabilities": R("Suggest capability tags"),
    "suggest_roles": R("Suggest role tags"),
    "suggest_artifact_types": R("Suggest artifact types"),
    "suggest_methodologies": R("Suggest methodologies"),
    "list_methodologies": R("List methodologies"),
    "get_methodology": R("Get methodology"),
    "register_methodology": W("Register methodology"),
    "list_frameworks": R("List frameworks"),
    "describe_framework": R("Describe framework"),
    "set_project_methodology": W("Set project methodology"),
    "brief_next": R("Brief next task"),
    "record_judgment": W("Record gate judgment"),

    # ---- personas (_tools_personas) ----
    "brief_persona": R("Brief persona authoring"),
    "record_persona": W("Record persona"),
    "get_persona": R("Get persona"),
    "persona_readiness": R("Assess persona readiness"),
    "brief_persona_memory_onboarding": R("Brief persona memory onboarding"),
    "preview_persona_update": R("Preview persona update"),
    "list_personas": R("List personas"),
    "get_persona_soul": R("Get persona SOUL"),
    "prepare_persona_agent_context": R("Prepare persona agent context"),
    "update_persona": W("Update persona"),  # appends a revision per call → no idempotentHint
    "suggest_tech_comfort": R("Suggest tech-comfort levels"),
    "refresh_persona_from_source": W("Refresh persona from source", open_world=True),  # catalog re-pull
    "generate_avatar": W("Generate persona avatar", open_world=True),  # image provider API
    "attach_evidence": W("Attach persona evidence"),
    "export_persona": R("Export persona"),  # returns the document inline
    "assess_coverage": R("Assess persona coverage"),  # deterministic, no persistence

    # ---- plan & runs (_tools_plan) ----
    "start_project": W("Start project"),
    "get_plan": R("Get research plan"),
    "export_plan_md": R("Export plan markdown"),  # returns the rendering inline
    "add_task": W("Add plan task"),
    "record_frame": W("Record frame"),
    "brief_product_understanding": R("Brief product understanding"),
    "record_manifest_product_understanding": W(
        "Record manifest Product Understanding", idempotent=True),
    "record_product_understanding": W("Record product understanding", idempotent=True),
    "get_product_understanding": R("Get product understanding"),
    "project_health": R("Get project health"),
    "resume_project_run": R("Resume project run", idempotent=True),
    "supersede_project": W("Supersede project", idempotent=True),
    "archive_project": W("Archive project", idempotent=True),
    "link_evidence": W("Link evidence"),
    "park_evidence": W("Park evidence"),
    "unpark_evidence": W("Unpark evidence"),
    "complete_task": W("Complete task"),
    "iterate_task": W("Iterate task"),
    "assess_progress": W("Record progress assessment"),  # records the assessment
    "next_action": R("Get next action"),
    "assess_project": R("Assess project"),  # read-only, computed
    "start_run": W("Start run", idempotent=True),  # create-or-resume
    "run_journal": R("Get run journal"),
    "checkpoint_step": W("Checkpoint run step"),
    "record_critic_round": W("Record critic round"),
    "finish_run": W("Finish run"),
    "run_step": W("Advance run step", idempotent=True),  # idempotent/resumable by contract
    "inject_work": W("Inject critic work"),

    # ---- predictions (_tools_predictions) ----
    "suggest_likelihood_levels": R("Suggest likelihood levels"),
    "aggregate_predictions": R("Aggregate predictions"),

    # ---- prototypes (_tools_prototypes) ----
    "scaffold_prototype": W("Scaffold prototype"),
    "register_prototype": W("Register prototype"),
    "register_remote_prototype": W("Register hosted prototype", idempotent=True),
    "list_prototypes": R("List prototypes"),
    "get_prototype": R("Get prototype"),
    "run_prototype": W("Run prototype"),
    "stop_prototype": W("Stop prototype"),  # stops a local process; no data loss
    "delete_prototype": D("Delete prototype"),
    "proto_open": W("Open browser session", open_world=True),
    "proto_act": W("Act in browser session", open_world=True),
    "proto_read": R("Read browser snapshot", open_world=True),
    "proto_close": W("Close browser session", open_world=True),
    "list_proto_sessions": R("List browser sessions"),
    "brief_prototype_session": R("Brief prototype session"),
    "record_prototype_session": W("Record prototype session"),

    # ---- research graph (_tools_research) ----
    "create_research_project": W("Create research project"),
    "list_research_projects": R("List research projects"),
    "available_project_icons": R("List project icons"),
    "set_project_icon": W("Set project icon"),
    "generate_project_icon": W("Generate project icon"),
    "get_project_graph": R("Get project graph"),
    "record_open_questions": W("Record open questions"),
    "get_research_frontier": R("Get research frontier"),
    "brief_synthesis_outline": R("Brief report outline"),
    "record_synthesis_outline": W("Record report outline"),
    "brief_synthesis_section": R("Brief report section"),
    "suggest_chart_kinds": R("Suggest chart kinds"),
    "record_synthesis_section": W("Record report section"),
    "delete_research_project": D("Delete research project"),
    "delete_synthesis": D("Delete synthesis"),
    "delete_council": D("Delete council session"),
    "persona_deletion_impact": R("Preview persona deletion"),
    "delete_persona": D("Delete persona with confirmation token"),

    # ---- sections & notes (_tools_sections) ----
    "create_section": W("Create section"),
    "update_section": W("Update section", idempotent=True),
    "add_to_section": W("Add to section"),
    "remove_from_section": D("Remove from section"),
    "set_section_members": W("Set section members", idempotent=True),
    "reorder_sections": W("Reorder sections", idempotent=True),
    "list_sections": R("List sections"),
    "get_section": R("Get section"),
    "delete_section": D("Delete section"),
    "suggest_section_kinds": R("Suggest section kinds"),
    "get_section_members": R("Get section members"),
    "export_section": R("Export section"),  # returns the document inline
    "create_note": W("Create note"),
    "set_note_data": W("Set note data", idempotent=True),
    "list_notes": R("List notes"),
    "delete_note": D("Delete note"),
    "derive_sections": W("Derive sections"),
    "scaffold_synthesis": W("Scaffold report outline"),

    # ---- simulation & memory (_tools_simulation) ----
    "brief_day": R("Brief day plan"),
    "put_day_plan": W("Save day plan", idempotent=True),
    "record_day": W("Record day"),
    "get_day_plan": R("Get day plan"),
    "brief_period": R("Brief period plan"),
    "put_period_plan": W("Save period plan", idempotent=True),
    "get_period_plan": R("Get period plan"),
    "list_period_plans": R("List period plans"),
    "brief_consolidation": R("Brief consolidation"),
    "record_memory_deltas": W("Record memory deltas"),
    "brief_digest": R("Brief digest"),
    "put_digest": W("Save digest", idempotent=True),
    "list_digests": R("List digests"),
    "recall_memory": R("Recall memory"),
    "list_active_projects": R("List active memory projects"),
    "get_project": R("Get persona project"),
    "get_state_at": R("Get state at date"),
    "get_timeline": R("Get timeline"),
    "search_entities": R("Search memory entities"),
    "get_open_loops": R("Get open loops"),
    "resolve_entity": R("Resolve entity"),
    "get_persona_memory": W("Render persona memory", idempotent=True),  # writes MEMORY.md to disk
    "brief_month": R("Brief month bundle"),
    "record_month_bundle": W("Record month bundle"),
    "get_current_state": R("Get current state"),
    "get_calendar": R("Get calendar day"),
    "get_calendar_period": R("Get calendar period"),
    "get_activity": R("Get activity"),
    "summarize_persona_period": R("Summarize persona period"),
    "extract_pain_points": R("Extract pain points"),

    # ---- substrate (_tools_substrate) ----
    "substrate_schema": R("Get substrate schema"),
    "query_personas": R("Query personas"),
    "query_projects": R("Query projects"),
    "query_councils": R("Query councils"),
    "query_syntheses": R("Query syntheses"),
    "get_study_result": R("Get study result"),
    "chat_with_persona": W("Chat with persona"),  # opens/continues a durable chat record
    "record_chat_turn": W("Record chat turn"),
    "get_chat": R("Get chat"),
    "list_chats": R("List chats"),

    # ---- surveys (_tools_surveys) ----
    "brief_survey": R("Brief survey"),
    "record_survey": W("Record survey"),
    "get_survey": R("Get survey"),
    "list_surveys": R("List surveys"),
    "export_survey": W("Export survey form"),  # writes the HTML file + flips draft → open
    "import_survey_responses": W("Import survey responses"),
    "survey_results": R("Get survey results"),
    "attach_survey_evidence": W("Attach survey evidence"),

    # ---- usability (_tools_usability) ----
    "brief_usability_session": R("Brief usability session"),
    "record_usability_session": W("Record usability session"),
    "get_usability_session": R("Get usability session"),
    "list_usability_sessions": R("List usability sessions"),
    "suggest_friction_levels": R("Suggest friction levels"),
    "get_session_funnel": R("Get session funnel"),

    # ---- live walkthrough (_tools_walkthrough) ----
    "walk_policy_defaults": R("Get walk policy defaults"),
    "walk_open": W("Open live walkthrough", open_world=True),
    "walk_own": W("Walk owned surface", open_world=True),
    "record_actuation_gate": W("Record actuation gate"),
}


def apply_annotations(mcp) -> None:
    """Attach the registry's ToolAnnotations (+ title) to every registered tool.

    Called once from build_server() after the core register_* calls. Extension
    tools (sonaloop.mcp.tools entry points) pass their own `annotations=` at
    registration; names not in the registry are left untouched.
    """
    from mcp.types import ToolAnnotations
    for tool in mcp._tool_manager.list_tools():
        spec = TOOL_ANNOTATIONS.get(tool.name)
        if spec is None:
            continue
        tool.annotations = ToolAnnotations(**spec)
        tool.title = spec["title"]
