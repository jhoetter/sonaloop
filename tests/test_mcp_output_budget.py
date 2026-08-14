"""MCP output budget (ticket mcp-output-budget-audit): every read tool stays ≤ ~20k
tokens (80k chars on the serialized envelope, safety margin under the 25k-token
directory line) against a REALISTIC fixture — two flagship example projects plus
one persona with 16 weeks of lived memory, real-sized corpora, a survey with
responses, a usability session, assets, a walkthrough script, a plan run and chats.

The audit is exhaustive by construction: every `readOnlyHint` tool in the
annotations registry must be either CALLED (args in _tool_args) or SKIPPED with a
written reason (_SKIPPED) — an unclassified new tool fails the test, so no tool
ever ships unaudited. One read-shaped writing tool the ticket names
(export_synthesis returns the document inline for format="md") is audited as an
extra. Persona memory is now a pure read; exporting it is a separate bounded write.

Fixed offenders pinned here (sizes from the audit run on this fixture):
- get_corpus include_chunks=True   306k -> ~12k  (chunk pagination + in-band note)
- get_calendar_period (month/year) 227k -> <60k  (summary rows + cap + note;
  detail="full" keeps the old shape for Python callers)
- get_timeline                     104k -> <60k  (newest-N caps + totals + note)
"""
from __future__ import annotations

import asyncio
import base64
import json
from datetime import date, timedelta
from typing import Any

from sonaloop import services
from sonaloop.storage import Store

BUDGET_CHARS = 80_000

# Read tools we cannot drive against a hermetic local fixture — every entry needs
# a reason; the coverage assertion below makes silent gaps impossible.
_SKIPPED: dict[str, str] = {
    "catalog_search": "remote catalog index over HTTP — needs network",
    "catalog_recommend": "remote catalog index over HTTP — needs network",
    "catalog_status": "remote catalog index over HTTP — needs network",
    "proto_read": "needs a live Playwright browser session",
    "list_flow_manifests": "requires an authenticated active remote workspace; dedicated admission tests drive a non-empty lean index",
    "get_flow_manifest": "requires an authenticated active remote workspace; dedicated admission tests drive the bounded 50-step exact record",
}


# --------------------------------------------------------------------- fixture

_BLOCK_THEMES = [
    ("Review pricing objections from the Friday calls", "focus"),
    ("Weekly sync with the analytics guild", "meeting"),
    ("Refactor the usage-export pipeline", "focus"),
    ("Answer escalations from the support queue", "admin"),
    ("Unplanned outage triage on the reporting cluster", "interruption"),
    ("Write up the quarterly capacity forecast", "focus"),
]

_ENTITY_POOL = [
    ("Meridian rollout", "project", "in progress"),
    ("Quarterly capacity forecast", "project", "drafting"),
    ("Anna (procurement)", "person", None),
    ("Jens from the data guild", "person", None),
    ("Helios reporting cluster", "topic", "flaky"),
    ("Usage-export pipeline", "project", "refactoring"),
    ("Vendor contract renewal", "project", "negotiating"),
    ("Support backlog", "topic", "growing"),
    ("New pricing tier evaluation", "project", "evaluating"),
    ("Margins review board", "org", None),
    ("On-call rotation", "topic", None),
    ("Berlin office move", "topic", "planned"),
]

_TRANSCRIPT_TOPICS = [
    "how the team decides between annual and monthly billing",
    "what broke during the last migration and who noticed first",
    "why the dashboard exports get rebuilt in spreadsheets anyway",
    "what a fair price for the premium tier would look like",
    "how procurement reviews a new vendor in practice",
    "which alerts get ignored and why nobody trusts the pager",
]


def _day_content(persona: dict, i: int) -> tuple[dict, dict]:
    """Host-authored day plan + activities for simulated day #i — realistic prose,
    varied by day so memory does not collapse into duplicates."""
    tools = persona.get("tools") or ["CAD"]
    pains = persona.get("pain_points") or ["pain"]
    blocks, acts = [], {}
    for b in range(5):
        theme, kind = _BLOCK_THEMES[(i + b) % len(_BLOCK_THEMES)]
        title = f"{theme} (day {i + 1})"
        blocks.append({
            "title": title, "duration_minutes": 45 + 15 * (b % 3), "event_type": kind,
            "tool": tools[(i + b) % len(tools)],
            "participants": (["Anna (procurement)", "Jens from the data guild"]
                             if kind == "meeting" else []),
            "why_it_happens": "It is on the team plan for this week and the deadline "
                              "pressure from the quarterly review keeps it on top of the stack.",
        })
        ent = _ENTITY_POOL[(i + b) % len(_ENTITY_POOL)][0]
        acts[title] = {
            "what_happened": (
                f"Worked through {theme.lower()}. Got about two thirds of the way before "
                f"a question about {ent} surfaced that nobody in the room could answer. "
                f"Parked it in the tracker and moved on; the rest went smoother than expected, "
                f"though the tooling friction around {pains[(i + b) % len(pains)]} cost another "
                f"twenty minutes."),
            "conversation": ([{"speaker": "Anna (procurement)",
                               "text": "Can we get the renewal numbers before Thursday? "
                                       "Legal wants a full week for review."},
                              {"speaker": persona["display_name"],
                               "text": "Only if the export pipeline behaves. I will send a "
                                       "partial cut tomorrow morning either way."}]
                             if kind == "meeting" else []),
            "key_quotes": [f"If {ent} slips again this quarter, I want it escalated, not patched."],
            "actions_done": [f"Updated the tracker entry for {ent}",
                             "Sent the partial numbers to the channel"],
            "artifacts_touched": [f"{ent} working doc", "team tracker"],
            "persona_thought": (
                f"Day {i + 1}: the pattern repeats — planning is fine, the handoffs are not. "
                f"{ent} is becoming the bottleneck I keep paying for."),
            "decision": (f"Escalate {ent} at the next review board" if b == 2 else None),
            "open_loops": [f"Waiting on Anna's numbers for {ent}"] if b % 2 == 0 else [],
            "mood": ["focused", "stretched", "annoyed", "steady", "drained"][(i + b) % 5],
            "energy_delta": -1 if kind == "interruption" else 0,
            "pain_points": [pains[(i + b) % len(pains)]] if kind != "meeting" else [],
        }
    return {"mood_forecast": ["steady", "tight", "optimistic"][i % 3], "blocks": blocks}, acts


def _memory_deltas(i: int) -> dict:
    e1 = _ENTITY_POOL[i % len(_ENTITY_POOL)]
    e2 = _ENTITY_POOL[(i + 3) % len(_ENTITY_POOL)]
    return {
        "entities": [{"mention": e1[0], "kind": e1[1], "status": e1[2]},
                     {"mention": e2[0], "kind": e2[1], "status": e2[2]}],
        "facts": [
            {"entity": e1[0], "importance": 3,
             "fact": f"Slipped by another two days in week {i // 5 + 1}; the export "
                     f"dependency is the recurring cause."},
            {"entity": e2[0], "importance": 2,
             "fact": f"Owner confirmed scope for week {i // 5 + 1}; budget unchanged."},
        ],
        "threads": [
            {"text": f"Chase the {e1[0]} numbers before Thursday (week {i // 5 + 1})",
             "entity": e1[0], "action": "open"},
        ] + ([{"text": f"Chase the {_ENTITY_POOL[(i - 2) % len(_ENTITY_POOL)][0]} numbers "
                       f"before Thursday (week {(i - 2) // 5 + 1})",
               "action": "resolve"}] if i >= 2 else []),
    }


def _transcript(n_turns: int, seed: int) -> str:
    """A realistic interview transcript (~the size of a 60-90 min session)."""
    lines = ["# Interview transcript — pricing & reporting study",
             "Moderator: Thanks for taking the time. I'd like to walk through your last quarter."]
    for t in range(n_turns):
        topic = _TRANSCRIPT_TOPICS[(seed + t) % len(_TRANSCRIPT_TOPICS)]
        lines.append(f"Moderator: Can you tell me more about {topic}?")
        lines.append(
            f"P{seed}: Honestly, it depends on the week. When we looked at {topic} last time, "
            f"the first thing that came up was budget ownership — nobody wants to sign off on a "
            f"recurring line item they can't explain in the margins review. So what actually "
            f"happens is someone exports the numbers, massages them in a spreadsheet, and the "
            f"tool of record quietly stops being the tool of record. We have talked about fixing "
            f"that maybe {t + 2} times this year. The blocker isn't the software, it's that the "
            f"person who owns the budget and the person who feels the pain sit two floors apart.")
        lines.append(
            f"P{seed}: And to be concrete — last month this cost us about {(t * 3 + seed) % 20 + 1} "
            f"hours, most of it in rework after the numbers diverged between the export and the "
            f"dashboard. If you ask me what I'd pay to make that go away: less than you think, "
            f"because half the fix is process, not product.")
    return "\n\n".join(lines)


def _rich_profile() -> dict[str, Any]:
    return {
        "display_name": "Maren Kolbe",
        "identity_traits": {"gender_presentation": "female", "gender_confidence": "high",
                            "age_range": "40-49", "appearance_notes": "unspecified",
                            "avatar_profile": "unspecified", "avatar_constraints": "unspecified"},
        "segment": {"customer_type": "Head of Business Operations", "market": "B2B SaaS",
                    "region": "DACH", "firm_size": "180"},
        "demographics": {"age": 44},
        "role": {"title": "Head of Business Operations",
                 "responsibilities": "owns reporting, vendor budget and the ops tooling stack",
                 "seniority": "head", "decision_power": "budget owner up to 50k"},
        "company_context": {"industry": "logistics software", "size": "mid",
                            "stack": "Postgres, Metabase, spreadsheets", "operating_model": "hybrid"},
        "goals": ["close the quarter without another reporting fire drill",
                  "consolidate the vendor stack to fewer line items",
                  "get the support backlog back under two days"],
        "constraints": ["procurement needs a full week for any new contract",
                        "no engineering capacity for tooling glue until Q3"],
        "tool_ids": ["sql_workbench", "spreadsheet", "helpdesk", "dashboards", "video_call", "crm"],
        "tools": ["SQL workbench", "Spreadsheet", "Helpdesk", "Dashboards", "Video call", "CRM"],
        "relationships": [
            {"name": "Anna (procurement)", "type": "colleague", "friction": "slow sign-offs"},
            {"name": "Jens from the data guild", "type": "colleague", "friction": "competing priorities"},
            {"name": "Margins review board", "type": "stakeholder", "friction": "wants weekly numbers"},
        ],
        "personality": {"working_style": "structured, lists everything",
                        "communication_style": "direct, allergic to vague status updates",
                        "risk_tolerance": "low", "character_notes": "burned by two tool migrations"},
        "pain_points": ["numbers diverge between export and dashboard",
                        "renewal negotiations eat unplanned weeks",
                        "support escalations bypass the queue",
                        "every report needs a manual spreadsheet pass"],
        "success_criteria": ["one source of truth the board accepts",
                             "renewals decided on data, not gut feel"],
    }


def build_fixture(store: Store) -> dict[str, Any]:
    """Seed one realistic working set; returns the id registry the audit drives with."""
    ids: dict[str, Any] = {}

    ex = services.load_example("premium-pricing-study", store=store)
    services.load_example("positioning-council", store=store)
    project_id = ex["project_id"]
    ids["project_id"] = project_id

    # one council session per format (both examples together cover all five)
    cbf: dict[str, str] = {}
    for sess in store.list_council_sessions():
        fmt = next((k for k in ("price_ladder", "head_to_head", "red_team", "ideation")
                    if sess.get(k)), "council")
        cbf[fmt] = sess["id"]
    ids["council_by_format"] = cbf
    ids["synthesis_id"] = store.list_syntheses()[0]["id"]

    # --- the rich persona: 16 weeks of simulated weekdays ----------------------
    persona = services.record_persona(
        "Ops lead at a mid-size logistics-software firm; owns reporting and vendor budget; "
        "two previous tool migrations went badly and she documents everything.",
        _rich_profile(), store=store)
    pid = persona["id"]
    ids["persona_id"] = pid

    d = date(2026, 3, 2)  # a Monday
    sim_days: list[str] = []
    while len(sim_days) < 80:
        if d.weekday() < 5:
            sim_days.append(d.isoformat())
        d += timedelta(days=1)
    for i, day in enumerate(sim_days):
        day_plan, acts = _day_content(persona, i)
        services.simulate_day(pid, day, seed=f"audit-{i}", day_plan=day_plan,
                              activities=acts, store=store)
        services.record_memory_deltas(pid, day, _memory_deltas(i), store=store)
        if i % 5 == 4:  # Friday: weekly digest
            services.put_digest(pid, "week", day, {
                "text": (f"Week {i // 5 + 1}: the {_ENTITY_POOL[i % len(_ENTITY_POOL)][0]} arc "
                         f"dominated. Handoffs with procurement remain the slowest link; the "
                         f"export pipeline behaved better after the refactor. Mood drifted from "
                         f"focused to stretched as escalations piled up toward Thursday."),
                "themes": ["handoffs", "reporting trust", "renewals"],
                "project_arcs": [{"name": _ENTITY_POOL[i % len(_ENTITY_POOL)][0],
                                  "arc": "slipped early, recovered by Friday"}],
                "trends": ["escalations cluster late in the week"],
            }, store=store)
    ids["sim_dates"] = sim_days
    ids["month"] = sim_days[0][:7]

    services.put_period_plan(pid, "week", sim_days[0], {
        "summary": "Stabilise the export pipeline and pre-empt the renewal escalation.",
        "intentions": ["ship the partial renewal numbers by Tuesday",
                       "hold the guild to the pipeline freeze"],
        "expected_milestones": ["renewal numbers accepted by legal"],
        "mood_trajectory": "tight start, steadier after Wednesday",
        "sample_days": [sim_days[0], sim_days[2]],
    }, store=store)
    services.set_world_context([
        {"category": "market",
         "fact": "Logistics-software budgets are flat this year; renewals get extra scrutiny."},
        {"category": "regulation", "fact": "New e-invoicing mandate lands in January."},
    ], store=store)

    ids["activity_id"] = store.list_experience_events(pid)[0]["id"]
    ents = services.search_entities(pid, store=store)
    ids["entity_id"] = ents[0]["id"]
    ids["entity_mention"] = ents[0]["name"]

    # --- chats ------------------------------------------------------------------
    chat = services.chat_with_persona(pid, "How did the renewal prep go this week?", store=store)
    chat_id = chat["chat_id"] if "chat_id" in chat else chat["id"]
    for _ in range(6):
        services.record_chat_turn(
            pid, chat_id,
            "Follow-up: what would actually change your mind on the premium tier?",
            "Honestly? Show me the export and the dashboard agreeing for a full month. "
            "I have been burned twice; a discount does not fix trust. If the numbers hold "
            "I can defend the line item at the margins review without a side spreadsheet.",
            store=store)
    ids["chat_id"] = chat_id
    proposal = services.record_memory_proposal(pid, chat_id, [0], {
        "summary": "Prior renewal discussion",
        "continuity_notes": ["The prior chat discussed evidence needed for renewal."],
    }, store=store)
    ids["memory_proposal_id"] = proposal["id"]

    # --- corpora: two interviews + a quarter's support-ticket export -------------
    c1 = services.ingest_corpus(_transcript(60, 1), "interview",
                                title="Interview P1 — ops lead, 90 min", store=store)
    c2 = services.ingest_corpus(_transcript(45, 2), "interview",
                                title="Interview P2 — finance partner, 60 min", store=store)
    tickets = ["# Support ticket export — Q1 (reporting & billing)"]
    for n in range(700):
        tickets.append(
            f"Ticket #{4000 + n} [{['open', 'pending', 'resolved'][n % 3]}] "
            f"({['billing', 'exports', 'dashboards', 'sso'][n % 4]}): "
            f"Customer reports that {_TRANSCRIPT_TOPICS[n % len(_TRANSCRIPT_TOPICS)]} "
            f"went wrong again after the {['nightly sync', 'plan change', 'seat update', 'export run'][n % 4]}. "
            f"Agent note: reproduced on tenant {n % 40}; the numbers in the CSV export differ from "
            f"the dashboard by {(n * 7) % 23 + 1} rows. Workaround shared; root cause pending with "
            f"the data guild. Customer tone: {['calm', 'frustrated', 'resigned', 'escalating'][n % 4]}.")
    c3 = services.ingest_corpus("\n\n".join(tickets), "ticket_export",
                                title="Support tickets Q1 — reporting & billing", store=store)
    ids["corpus_id"] = c3["id"]                       # the big one — the offender case
    ids["corpus_ids"] = [c1["id"], c2["id"], c3["id"]]
    hits = services.search_corpus("budget ownership spreadsheet", store=store)
    ids["chunk_id"] = hits[0]["id"]

    # --- survey with imported responses -------------------------------------------
    survey = services.record_survey(
        project_id, "Premium tier pricing check",
        [{"id": "q1", "text": "How do you budget for analytics tooling today?", "kind": "single",
          "options": ["Central IT budget", "Team budget", "Ad-hoc approvals", "No formal budget"]},
         {"id": "q2", "text": "Which exports do you rebuild manually?", "kind": "multi",
          "options": ["Usage", "Billing", "Support", "None"]},
         {"id": "q3", "text": "A premium tier at 2x with SSO and audit logs would be worth it.",
          "kind": "scale", "options": ["oppose", "skeptical", "neutral", "conditional", "support"],
          "stance_mapped": True},
         {"id": "q4", "text": "What almost made you churn last year?", "kind": "text"}],
        intro="Ten questions, anonymous, five minutes.", store=store)["survey"]
    ids["survey_id"] = survey["id"]
    answers = ["oppose", "skeptical", "neutral", "conditional", "support"]
    services.import_survey_responses(survey["id"], responses=[
        {"respondent_key": f"r_{r:03d}", "submitted_at": f"2026-05-{r % 28 + 1:02d}T10:00:00Z",
         "answers": [
             {"question_id": "q1", "value": ["Central IT budget", "Team budget",
                                             "Ad-hoc approvals", "No formal budget"][r % 4]},
             {"question_id": "q2", "value": [["Usage"], ["Usage", "Billing"],
                                             ["Support"], ["None"]][r % 4]},
             {"question_id": "q3", "value": answers[r % 5]},
             {"question_id": "q4",
              "value": f"The {['renewal surprise', 'export outage', 'support silence', 'price jump'][r % 4]} "
                       f"in Q{r % 4 + 1} — we had no warning and the workaround cost us days."},
         ]} for r in range(24)], store=store)

    # --- assets + flow + artifact ----------------------------------------------------
    png = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"0" * 400).decode()
    asset_ids = []
    for n, title in enumerate(["Pricing page", "Checkout step", "Confirmation"]):
        a = services.attach_asset(project_id, content_base64=png, filename=f"shot{n}.png",
                                  title=title, kind="screenshot", store=store)
        asset_ids.append(a["id"])
    ids["asset_id"] = asset_ids[0]
    pu_ref = {"kind": "asset", "id": asset_ids[0]}
    services.record_product_understanding(
        project_id, {"name": "Premium pricing fixture"}, "fixture-v1",
        routes=[{"path": "/pricing", "evidence_refs": [pu_ref]}], flows=[], states=[],
        capabilities=[{"claim": "Pricing is visible", "status": "observed_present",
                       "evidence_refs": [pu_ref]}], evidence_refs=[pu_ref],
        observed_at="2026-05-20T09:00:00Z", key="output-budget:pu", store=store)
    flow = services.define_flow(project_id, "Upgrade flow",
                                [{"asset_id": a, "caption": f"step {i}"}
                                 for i, a in enumerate(asset_ids)], store=store)
    ids["flow_id"] = flow["id"]
    art = services.add_artifact(project_id, "https://example.test/pricing", kind="url",
                                title="Current pricing page", capture=False, store=store)
    ids["artifact_id"] = art["id"]

    # --- usability session ------------------------------------------------------------
    steps = [{
        "index": s,
        "action": {"type": "click", "target": f"cta-{s}",
                   "detail": f"clicked the step-{s} call to action"},
        "monologue": f"Step {s}: I expect the price breakdown here, not another feature list. "
                     f"If I cannot see the per-seat math I will not take this to procurement.",
        "state": {"screen": f"screen-{s}"},
        "friction": {"level": ["none", "hesitation", "confusion"][s % 3],
                     "note": "label ambiguous" if s % 3 else ""},
        "verdict": {"would_continue": s < 5, "reason": "lost trust in the math" if s == 5 else ""},
    } for s in range(6)]
    us = services.record_usability_session(
        pid, {"kind": "flow", "id": ids["flow_id"], "label": "Upgrade flow"}, "artifact",
        "2026-05-20", steps,
        {"completed": False, "dropoff_step": 5, "summary": "dropped at the seat-math screen",
         "predicted_behaviors": [{"action": "ask procurement to negotiate instead", "step": 5,
                                  "likelihood": "likely", "trigger": "opaque per-seat pricing"}]},
        project_id=project_id, store=store)
    ids["usability_session_id"] = us["usability_session"]["id"]

    # --- prototype --------------------------------------------------------------------
    proto = services.scaffold_prototype(
        "pricing-page-v2", "Pricing page v2",
        {"title": "Pricing page v2",
         "hypothesis": "a transparent per-seat breakdown restores trust",
         "screens": [
             {"id": "pricing", "title": "Pricing", "elements": [
                 {"id": "cta1", "kind": "button", "label": "See seat math", "goto": "seatmath"}]},
             {"id": "seatmath", "title": "Seat math", "elements": [
                 {"id": "cta2", "kind": "button", "label": "Checkout", "goto": "checkout"}]},
             {"id": "checkout", "title": "Checkout", "elements": []},
         ]},
        project_id=project_id, store=store)
    ids["prototype_id"] = proto["id"]

    # --- report outline + plan engine on the example project ----------------------------
    report = services.record_synthesis_outline(project_id, {
        "title": "Premium pricing — project report",
        "build_order_narrative": "Councils first, then the synthesis that consolidates them.",
        "sections": [
            {"heading": "Willingness to pay", "intent": "Consolidate the price-ladder evidence",
             "source_study_ids": [ids["synthesis_id"]], "theme_tags": ["pricing"]},
            {"heading": "Trust blockers", "intent": "Why the premium tier stalls in procurement",
             "source_study_ids": [ids["synthesis_id"]], "theme_tags": ["trust"]},
        ]}, store=store)
    ids["report_section_id"] = report["sections"][0]["id"]
    services.set_project_methodology(project_id, "double_diamond", store=store)
    ids["run_id"] = services.start_run(project_id, store=store)["run_id"]

    context_snapshot = services.prepare_persona_for_task(
        pid, "renewal negotiation reporting trust", project_id=project_id, store=store)
    ids["persona_context_snapshot_id"] = context_snapshot["id"]
    persona_build = services.begin_persona_build(
        pid, "output-budget-persona-build", store=store)
    ids["persona_build_id"] = persona_build["build_id"]

    # A compact but real deterministic cohort record lets both read surfaces participate
    # in this exhaustive budget audit without adding a second governed Reaction Test run.
    from sonaloop.cohort_integrity import evaluate_cohort
    cohort = evaluate_cohort(
        store.get_research_project(project_id), [], [], None, store,
        evaluated_at="2026-08-08T10:00:00Z")
    cohort.update({"id": "cohort_preflight_budget_fixture", "project_id": project_id,
                   "version": 1, "raw_status": cohort["status"]})
    project = store.get_research_project(project_id)
    project["cohort_preflight_versions"] = [cohort]
    project["cohort_preflight_current_id"] = cohort["id"]
    store.upsert_research_project(project)

    # vocabulary/registry ids + example-loaded entities
    ids["methodology_key"] = "double_diamond"
    ids["framework_id"] = services.list_frameworks(store=store)["frameworks"][0]["id"]
    ids["job_id"] = services.list_job_presets(store=store)["presets"][0]["id"]
    ids["result_schema_id"] = services.list_result_schemas(store=store)["schemas"][0]["id"]
    ids["hypothesis_id"] = services.list_hypotheses(project_id=project_id, store=store)[0]["id"]
    ids["decision_id"] = services.list_decisions(project_id=project_id, store=store)[0]["id"]
    ids["section_id"] = services.list_sections(project_id, store=store)[0]["id"]
    return ids


# ----------------------------------------------------------------------- audit

def _tool_args(ids: dict[str, Any]) -> dict[str, dict]:
    """Args for every auditable read tool — worst-case-leaning (year calendar view,
    include_chunks on the big corpus, no narrowing filters anywhere)."""
    pid, proj, cbf = ids["persona_id"], ids["project_id"], ids["council_by_format"]
    day = ids["sim_dates"][10]
    return {
        # no-arg / optional-only tools
        "available_project_icons": {}, "brief_calibration": {}, "brief_cohort_critic": {}, "calibration_trend": {},
        "cohort_memory_depth": {}, "eval_scorecard": {"project_id": proj},
        "get_language": {}, "get_world_context": {}, "list_chats": {},
        "list_corpora": {}, "list_councils": {}, "list_decisions": {},
        "list_examples": {}, "list_frameworks": {}, "list_hooks": {},
        "list_forms": {"primitive": "council"},
        "list_hypotheses": {}, "list_job_presets": {}, "list_lifecycle_events": {},
        "list_memory_anomalies": {}, "list_methodologies": {}, "list_personas": {},
        "list_primitives": {},
        "list_proto_sessions": {}, "list_prototypes": {}, "list_research_projects": {},
        "list_syntheses": {}, "list_surveys": {}, "list_usability_sessions": {},
        "list_result_schemas": {}, "list_result_contracts": {},
        "query_councils": {}, "query_personas": {}, "query_projects": {},
        "query_syntheses": {}, "substrate_schema": {}, "walk_policy_defaults": {},
        "suggest_artifact_types": {}, "suggest_capabilities": {}, "suggest_chart_kinds": {},
        "suggest_forms": {"primitive": "session"},
        "suggest_finding_kinds": {}, "suggest_friction_levels": {},
        "suggest_likelihood_levels": {}, "suggest_methodologies": {}, "suggest_roles": {},
        "suggest_section_kinds": {}, "suggest_stances": {}, "suggest_tech_comfort": {},
        "get_form": {"primitive": "council", "form_id": "head_to_head"},
        # project-scoped
        "aggregate_predictions": {"project_id": proj},
        "assess_coverage": {"project": proj},
        "assess_project": {"project_id": proj},
        "assess_progress": {"project_id": proj},
        "brief_completeness_critic": {"project_id": proj},
        "brief_cohort_preflight": {"project_id": proj},
        "brief_product_understanding": {"project_id": proj},
        "brief_hypothesis": {"project_id": proj},
        "brief_next": {"project_id": proj},
        "brief_survey": {"project_id": proj},
        "brief_synthesis_outline": {"project_id": proj},
        "brief_synthesis_section": {"project_id": proj, "section_id": ids["report_section_id"]},
        "export_plan_md": {"project_id": proj},
        "get_plan": {"project_id": proj},
        "project_health": {"project_id": proj},
        "project_result_contract_state": {"project_id": proj},
        "get_product_understanding": {"project_id": proj},
        "get_cohort_preflight": {"project_id": proj},
        "get_project_graph": {"project_id": proj},
        "get_research_frontier": {"project_id": proj},
        "get_study_result": {"project_id": proj},
        "list_artifacts": {"project_id": proj},
        "list_assets": {"project_id": proj},
        "list_flows": {"project_id": proj},
        "list_ideas": {"project_id": proj},
        "list_notes": {"project_id": proj},
        "list_sections": {"project_id": proj},
        "next_action": {"project_id": proj},
        "run_journal": {"run_id": ids["run_id"]},
        "resume_project_run": {"project_id": proj, "run_id": ids["run_id"]},
        "flow_funnel": {"project_id": proj, "flow_id": ids["flow_id"]},
        "get_session_funnel": {"subject_kind": "flow", "subject_id_or_url": ids["flow_id"]},
        # persona-scoped
        "brief_ask": {"persona_id": pid, "question": "Would you renew at a 20% higher price?"},
        "brief_consolidation": {"persona_id": pid, "date": day},
        "brief_day": {"persona_id": pid, "date": ids["sim_dates"][-1]},
        "brief_digest": {"persona_id": pid, "scope": "week", "date": day},
        "brief_eval_critic": {"persona_id": pid},
        "brief_evidence_check": {"persona_id": pid},
        "brief_month": {"persona_id": pid, "month": ids["month"]},
        "brief_period": {"persona_id": pid, "scope": "week", "date": day},
        "brief_persona_revision": {"persona_id": pid},
        "extract_pain_points": {"persona_id": pid},
        "get_calendar": {"persona_id": pid, "date": day},
        "get_calendar_period": {"persona_id": pid, "date": day, "view": "year"},
        "get_current_state": {"persona_id": pid},
        "get_day_plan": {"persona_id": pid, "date": day},
        "get_open_loops": {"persona_id": pid},
        "get_period_plan": {"persona_id": pid, "scope": "week", "date": ids["sim_dates"][0]},
        "get_persona": {"persona_id": pid},
        "persona_readiness": {"persona_id": pid},
        "brief_persona_memory_onboarding": {"persona_id": pid, "days": 28},
        "persona_task_readiness": {"persona_id": pid,
                                     "task": "renewal negotiation reporting trust"},
        "preview_persona_update": {"persona_id": pid,
                                    "patch": {"goals": ["Keep renewal reporting trustworthy"]}},
        "get_persona_context_snapshot": {"snapshot_id": ids["persona_context_snapshot_id"]},
        "list_persona_context_snapshots": {"persona_id": pid},
        "get_persona_build": {"build_id": ids["persona_build_id"]},
        "list_persona_builds": {"persona_id": pid},
        "validate_persona_output": {
            "persona_id": pid,
            "text": "I need to see the export match the dashboard first.",
        },
        "brief_memory_from_chat": {"persona_id": pid, "chat_id": ids["chat_id"],
                                    "turn_indexes": [0]},
        "get_memory_proposal": {"proposal_id": ids["memory_proposal_id"]},
        "list_memory_proposals": {"persona_id": pid},
        "persona_deletion_impact": {"persona_id": pid},
        "get_persona_soul": {"persona_id": pid},
        "get_persona_memory": {"persona_id": pid},
        "get_state_at": {"persona_id": pid, "as_of": day},
        "get_timeline": {"persona_id": pid},
        "get_project": {"persona_id": pid, "entity_id": ids["entity_id"]},
        "list_active_projects": {"persona_id": pid},
        "list_digests": {"persona_id": pid},
        "list_period_plans": {"persona_id": pid},
        "list_persona_revisions": {"persona_id": pid},
        "prepare_persona_agent_context": {"persona_id": pid,
                                          "task": "council on premium pricing"},
        "recall_memory": {"persona_id": pid, "query": "renewal negotiation reporting trust"},
        "resolve_entity": {"persona_id": pid, "mention": ids["entity_mention"]},
        "search_entities": {"persona_id": pid},
        "summarize_persona_period": {"persona_id": pid},
        "export_persona": {"persona_id": pid},
        "get_activity": {"activity_id": ids["activity_id"]},
        # council formats / sessions / syntheses
        "get_council": {"session_id": cbf["council"]},
        "export_council_session": {"session_id": cbf["council"]},
        "get_head_to_head": {"session_id": cbf["head_to_head"]},
        "get_price_ladder": {"session_id": cbf["price_ladder"]},
        "price_ladder_analysis": {"session_id": cbf["price_ladder"]},
        "get_red_team": {"session_id": cbf["red_team"]},
        "get_ideation": {"session_id": cbf["ideation"]},
        "get_synthesis": {"synthesis_id": ids["synthesis_id"]},
        "brief_synthesis": {"council_ids": list(cbf.values())[:3]},
        "brief_council": {"project_id": proj, "prompt": "Is the premium tier worth 2x?"},
        "brief_head_to_head": {"project_id": proj, "prompt": "Which positioning lands?",
                               "options": ["Time saved", "One source of truth"]},
        "brief_price_ladder": {"project_id": proj, "prompt": "Premium tier price points",
                               "price_points": ["19", "29", "49"]},
        "brief_red_team": {"project_id": proj, "prompt": "Premium tier launch plan"},
        # grounding / corpora
        "brief_grounding": {"corpus_ids": ids["corpus_ids"], "persona_id": pid},
        "get_corpus": {"corpus_id": ids["corpus_id"], "include_chunks": True},
        "search_corpus": {"query": "budget ownership spreadsheet"},
        "trace_evidence": {"chunk_id": ids["chunk_id"]},
        # surveys / usability / prototypes / chats / flows
        "get_survey": {"survey_id": ids["survey_id"]},
        "survey_results": {"survey_id": ids["survey_id"]},
        "get_usability_session": {"session_id": ids["usability_session_id"]},
        "brief_usability_session": {"persona_id": pid, "fidelity": "artifact",
                                    "subject": {"kind": "flow", "id": ids["flow_id"],
                                                "label": "Upgrade flow"}},
        "brief_prototype_session": {"persona_id": pid, "prototype_id": ids["prototype_id"]},
        "get_prototype": {"prototype_id": ids["prototype_id"]},
        "get_chat": {"chat_id": ids["chat_id"]},
        "brief_flow_walkthrough": {"persona_id": pid, "project_id": proj,
                                   "flow_id": ids["flow_id"]},
        # entity reads
        "get_artifact": {"project_id": proj, "artifact_id": ids["artifact_id"]},
        "get_asset": {"project_id": proj, "asset_id": ids["asset_id"]},
        "view_asset": {"project_id": proj, "asset_id": ids["asset_id"]},
        "get_decision": {"decision_id": ids["decision_id"]},
        "get_hypothesis": {"hypothesis_id": ids["hypothesis_id"]},
        "get_section": {"section_id": ids["section_id"]},
        "get_section_members": {"section_id": ids["section_id"]},
        "export_section": {"section_id": ids["section_id"]},
        "get_job_preset": {"job_id": ids["job_id"]},
        "get_result_schema": {"schema_id": ids["result_schema_id"]},
        "result_contract_for_job": {"job_id": ids["job_id"]},
        "result_contract_for_methodology": {"methodology_key": ids["methodology_key"]},
        "get_methodology": {"key": ids["methodology_key"]},
        "describe_framework": {"framework_id": ids["framework_id"]},
        # pure-input tools
        "brief_persona": {"description": "A finance partner at a logistics-software firm "
                                         "who signs off vendor renewals."},
        "sharpen_question": {"goal": "Understand willingness to pay for a premium tier"},
    }


# Read-shaped writing tools the ticket names explicitly. export_synthesis with
# format="md" returns the document inline. Persona memory export returns only a
# bounded write receipt and needs no read-output exception.
def _extra_args(ids: dict[str, Any]) -> dict[str, dict]:
    return {
        "export_synthesis": {"synthesis_id": ids["synthesis_id"], "format": "md"},
        # the cross-host retrieval contract: search caps at 20 hits × short snippets,
        # fetch renders ONE record — both bounded by construction, audited here for real
        "search": {"query": "pricing onboarding council"},
        "fetch": {"id": ids["synthesis_id"]},
    }


def _result_chars(server, name: str, args: dict) -> int:
    """The serialized size of what the host receives: the structured envelope when
    the tool returns one, otherwise the raw content blocks (e.g. view_asset images)."""
    res = asyncio.run(server.call_tool(name, args))
    content, structured = res if isinstance(res, tuple) else (res, None)
    if structured is not None:
        return len(json.dumps(structured, ensure_ascii=False, default=str))
    return sum(len(getattr(c, "text", "") or "") + len(getattr(c, "data", b"") or b"")
               for c in content)


def test_typed_council_report_brief_is_bounded_with_visible_truncation(store):
    project = services.start_project("Large council report", "What did people notice?", store=store)
    council = services.record_council(
        project["id"], "What did you notice first?", [f"p{i}" for i in range(8)],
        [{"persona_id": f"p{i}", "text": f"voice-{i}: " + "x" * 5_000}
         for i in range(8)],
        summary="A deliberately large source.", key="large-typed-council", store=store)
    report = services.record_synthesis_outline(project["id"], {
        "build_order_narrative": "One large council.",
        "sections": [{"heading": "Finding", "intent": "Summarize it.",
                      "theme_tags": [],
                      "source_study_ids": [f'council:{council["id"]}']}],
    }, store=store)
    section_id = report["sections"][0]["id"]

    brief = services.brief_synthesis_section(
        project["id"], section_id, report_id=report["id"], store=store)
    assert brief["frame"]["source_budget"]["truncated"] is True
    assert brief["frame"]["source_budget"]["omitted_sources"] == 0
    assert brief["frame"]["studies"][0]["study_id"] == f'council:{council["id"]}'

    from sonaloop.mcp_server import build_server
    assert _result_chars(build_server(), "brief_synthesis_section", {
        "project_id": project["id"], "section_id": section_id, "report_id": report["id"],
    }) < BUDGET_CHARS


def test_report_briefs_bound_pretty_nested_sources_and_large_outlines(store):
    project = services.start_project(
        "Deep report sources", "What did we learn?", methodology="double_diamond", store=store)
    note_ids = []
    for index in range(50):
        note = services.create_note(
            project["id"], f"Observation {index}", title=f"Note {index}",
            data={f"field_{item}": {"nested": {"value": "small"}}
                  for item in range(20)}, store=store)
        note_ids.append(note["id"])
    report = services.record_synthesis_outline(project["id"], {
        "build_order_narrative": "Fifty nested notes.",
        "sections": [{"heading": "All notes", "intent": "Consolidate them.",
                      "theme_tags": [],
                      "source_study_ids": [f"note:{note_id}" for note_id in note_ids]}],
    }, store=store)
    section_id = report["sections"][0]["id"]

    section_brief = services.brief_synthesis_section(
        project["id"], section_id, report_id=report["id"], store=store)
    section_budget = section_brief["frame"]["source_budget"]
    assert section_budget["truncated"] is True
    assert section_budget["omitted_serialized_chars"] > 0
    assert section_budget["omitted_fields"] > 0

    council_ids = []
    for index in range(220):
        council_id = f"large_outline_council_{index}"
        council_ids.append(council_id)
        store.insert_council_session({
            "id": council_id, "project_id": project["id"],
            "created_at": f"2026-08-11T00:{index:02d}:00+00:00",
            "prompt": f"Council {index}", "persona_ids": ["p1"], "statements": [],
            "votes": [], "proposal": "", "summary": "s" * 5_000,
            "exec_summary": "e" * 5_000, "selection_reason": "fixture",
        })
    persisted = store.get_research_project(project["id"])
    persisted["council_ids"] = list(dict.fromkeys(
        list(persisted.get("council_ids") or []) + council_ids))
    store.upsert_research_project(persisted)
    terminal_id = "large_outline_terminal_synthesis"
    store.upsert_synthesis({
        "id": terminal_id, "project_id": project["id"], "scope": "study", "status": "done",
        "created_at": "2026-08-11T23:59:00+00:00", "title": "Terminal conclusion",
        "goal": "Conclude the work", "council_ids": [council_ids[-1]],
        "statements": [], "findings": [], "gesamtbild": "The required final conclusion.",
    })
    plan = services.get_plan(project["id"], store=store)
    terminal_verify = [task for task in plan["tasks"] if task["bucket"] == "verify"][-1]
    services.link_evidence(
        project["id"], terminal_verify["id"], {"kind": "synthesis", "id": terminal_id},
        store=store)

    from sonaloop.mcp_server import build_server
    server = build_server()
    assert _result_chars(server, "brief_synthesis_section", {
        "project_id": project["id"], "section_id": section_id, "report_id": report["id"],
    }) < BUDGET_CHARS
    outline_brief = services.brief_synthesis_outline(project["id"], store=store)
    graph_budget = outline_brief["frame"]["graph_budget"]
    assert graph_budget["truncated"] is True
    assert graph_budget["build_order_total"] > graph_budget["build_order_returned"]
    assert outline_brief["study_ids_total"] == graph_budget["build_order_total"]
    assert len(outline_brief["study_ids"]) == graph_budget["build_order_returned"]
    assert f"synthesis:{terminal_id}" in outline_brief["study_ids"]
    assert f"synthesis:{terminal_id}" in graph_budget["pinned_source_ids"]
    assert _result_chars(server, "brief_synthesis_outline", {
        "project_id": project["id"],
    }) < BUDGET_CHARS


def test_outline_budget_applies_to_the_composed_graph_frame(store):
    project = services.start_project("Combined outline budget", "g" * 5_000, store=store)
    council_ids = []
    for index in range(100):
        stamp = f"2026-08-11T{index // 60:02d}:{index % 60:02d}:00+00:00"
        council_id = f"combined_council_{index}"
        council_ids.append(council_id)
        store.insert_council_session({
            "id": council_id, "project_id": project["id"], "created_at": stamp,
            "prompt": f"Normal council {index}", "persona_ids": ["p1"],
            "statements": [], "votes": [], "proposal": "", "summary": "short",
            "exec_summary": "short", "selection_reason": "fixture",
        })
        store.upsert_synthesis({
            "id": f"combined_synthesis_{index}", "project_id": project["id"],
            "scope": "study", "status": "done", "created_at": stamp,
            "title": f"Normal synthesis {index}", "goal": "short",
            "council_ids": [council_id], "statements": [], "findings": [],
            "gesamtbild": "short",
        })
    persisted = store.get_research_project(project["id"])
    persisted["council_ids"] = council_ids
    persisted["themes"] = [(f"theme-{index}-" + "t" * 100) for index in range(100)]
    store.upsert_research_project(persisted)
    services.record_open_questions(
        project["id"], [f"Question {index}: " + "q" * 600 for index in range(100)], store=store)

    brief = services.brief_synthesis_outline(project["id"], store=store)
    budget = brief["frame"]["graph_budget"]
    assert budget["truncated"] is True
    assert budget["frame_pretty_chars"] <= budget["frame_limit_chars"]
    assert budget["edges_omitted"] > 0
    assert budget["open_questions_omitted"] > 0
    assert budget["project_truncated"] is True

    from sonaloop.mcp_server import build_server
    assert _result_chars(build_server(), "brief_synthesis_outline", {
        "project_id": project["id"],
    }) < BUDGET_CHARS


def test_every_read_tool_stays_under_output_budget(store, tmp_path, monkeypatch):
    from sonaloop import prototypes
    from sonaloop.mcp_server import build_server
    from sonaloop.mcp_server._annotations import TOOL_ANNOTATIONS

    # scaffold_prototype writes real files; keep them in the test sandbox
    # (conftest isolates the DB/ROOT, but prototypes_dir resolves via config.ROOT).
    monkeypatch.setattr(prototypes, "prototypes_dir", lambda: tmp_path / "prototypes")

    ids = build_fixture(store)

    # The fixture must be a realistic working set, not an empty shell — otherwise the
    # budget assertion below would pass vacuously.
    assert len(ids["sim_dates"]) >= 80, "rich persona needs months of lived memory"
    big = services.get_corpus(ids["corpus_id"], store=store)
    assert big["chunks"] > 100, "the offender corpus must be real-document-sized"
    assert len(store.list_council_sessions()) >= 6
    assert len(ids["council_by_format"]) == 5, "all five council formats must be present"

    server = build_server()
    read_tools = sorted(n for n, a in TOOL_ANNOTATIONS.items() if a.get("readOnlyHint"))
    args = _tool_args(ids)
    args.update(_extra_args(ids))

    # No silent gaps: every read tool is either driven or skipped WITH a reason.
    unclassified = [n for n in read_tools if n not in args and n not in _SKIPPED]
    assert not unclassified, (
        f"new read tools must be added to the output-budget audit (or skipped with a "
        f"written reason): {unclassified}")
    misfiled = sorted(set(_SKIPPED) & set(args))
    assert not misfiled, f"tools both skipped and driven: {misfiled}"

    over, sizes = [], {}
    for name in sorted(set(read_tools) | set(_extra_args(ids))):
        if name in _SKIPPED:
            continue
        size = _result_chars(server, name, args[name])
        sizes[name] = size
        if size > BUDGET_CHARS:
            over.append((name, size))
    assert not over, (
        f"MCP tool results over the {BUDGET_CHARS}-char (~20k-token) budget on the "
        f"realistic fixture: {over} — paginate, summarize-first, or cap with an "
        f"in-band note (see docs/pagination.md and this test's module docstring).")

    # Regression pins for the three fixed offenders: they must answer well under the
    # line AND say so in-band when they trim/page.
    assert sizes["get_corpus"] < 20_000
    assert sizes["get_calendar_period"] < BUDGET_CHARS
    assert sizes["get_timeline"] < BUDGET_CHARS

    # ---- the fixed tools never trim silently: totals + a note naming the param/tool
    # that returns the rest (same fixture session — building it is the expensive part).
    corpus = services.get_corpus(ids["corpus_id"], include_chunks=True, store=store)
    assert corpus["has_more"] is True and corpus["next_cursor"]
    assert corpus["chunk_total"] > len(corpus["chunk_list"]) == 25
    assert "search_corpus" in corpus["note"] and "cursor" in corpus["note"]
    page2 = services.get_corpus(ids["corpus_id"], include_chunks=True,
                                cursor=corpus["next_cursor"], store=store)
    assert page2["chunk_list"][0]["idx"] == 25      # stable continuation, no overlap

    cal = services.get_calendar_period(ids["persona_id"], ids["sim_dates"][10], "year", store)
    assert cal["events_total"] == 400 and "get_activity" in cal["note"]
    lean = next(iter(cal["days"].values()))[0]
    assert set(lean) == {"id", "timestamp", "event_type", "task", "tool"}
    full = services.get_calendar_period(ids["persona_id"], ids["sim_dates"][10], "month",
                                        store, detail="full")
    assert "what_happened" in next(iter(full["days"].values()))[0]  # Python opt-in unchanged

    tl = services.get_timeline(ids["persona_id"], store=store)
    assert tl["facts_total"] > len(tl["facts"]) == 100
    assert tl["events_total"] > len(tl["events"]) == 200
    assert "max_facts" in tl["note"]
    # raising the caps explicitly returns everything (the documented handle)
    tl_all = services.get_timeline(ids["persona_id"], max_facts=10_000, max_events=10_000,
                                   store=store)
    assert len(tl_all["facts"]) == tl["facts_total"]
    assert "note" not in tl_all
