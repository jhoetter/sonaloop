# MCP Tool Contract

Exact tool surface for Sonaloop (implemented in `sonaloop/mcp_server.py`).
Model-neutral: the same tools work for any MCP host (Claude Code, Codex, …).

## Envelope (every tool)
```json
{ "ok": true,
  "data": <result>,
  "next_recommended_tool": {"name": "...", "reason": "..."} | null,
  "_meta": {"tool": "...", "latency_ms": 0, "server_version": "0.2.0", "schema_version": 2} }
```
`next_recommended_tool` encodes the implicit decision DAG
(simulate → consolidate → digest → evaluate). 58 tools total.

## Naming conventions
`list_*` overview · `get_*` detail · `set_*`/`put_*`/`record_*` write ·
`*_status`/`*_summary` compact · `brief_*` gather context for a host-authored step ·
`recall_*` hybrid retrieval · `evaluate_*` quality gate. Prefer compact reads;
request detail only when a decision needs it.

## The host-authoring contract (no server-side text)
Generative steps are split: `brief_X(...)` returns `{instructions, frame, schema}`;
the host LLM authors JSON; `record_X(...)` / `put_X(...)` validate + persist.
This follows a context-gatherer + reader/judge split.

For `dispatch_v1` governed runs, `run_step` adds `dispatch_token` to every
analyze/act/verify dispatch. The matching write tool accepts that token, validates its
workspace/project/run/task/bucket/key, dispatch cursor, input fingerprint and output contract
before mutation, and returns `dispatch` state. One primary output kind is bound per dispatch;
supporting stimulus assets/flow manifests and closing judgments are declared separately. A
successful terminal write auto-links and auto-checkpoints; the host must not checkpoint it twice.
An identical payload replay returns the original primitive. A pre-checkpoint authored repair is
versioned by fingerprint; after task completion/checkpoint, changed content fails closed.
Reaction Test adds the gather/write pair `brief_product_understanding` →
`record_product_understanding` plus `get_product_understanding`. After the initial
`record_frame` commits the actual questions/hypotheses, council/synthesis writes wait for
`brief_cohort_preflight` → `record_cohort_preflight` (inspectable through
`get_cohort_preflight`): a versioned, provider-neutral depth/provenance/hypothesis-leakage gate
whose failed result injects real remediation work. Council/synthesis writes accept an explicit
`claims` inventory with the posture contract in
`docs/research-integrity.md`.

| Phase | gather | write-back |
|---|---|---|
| Day plan | `brief_day` | `put_day_plan` |
| Period plan | `brief_period` | `put_period_plan` |
| Consolidation | `brief_consolidation` | `record_memory_deltas` |
| Digest | `brief_digest` | `put_digest` |
| Persona drift | `brief_persona_revision` | `record_persona_revision` |

## Categories (see mcp_server.py for full signatures + docstrings)
- Persona/identity: create_persona, bulk_create_personas, get_persona, list_personas,
  get_persona_soul, prepare_persona_agent_context, update_persona,
  refresh_persona_from_source, generate_avatar
- Planning: brief_day, put_day_plan, get_day_plan, brief_period, put_period_plan,
  get_period_plan, list_period_plans
- Simulation: simulate_day, simulate_range, continue_simulation, clear_simulations,
  purge_runtime_data
- Consolidation: brief_consolidation, record_memory_deltas
- Digests: brief_digest, put_digest, list_digests
- Memory retrieval: recall_memory, list_active_projects, get_project, get_state_at,
  get_timeline, search_entities, get_open_loops, resolve_entity, get_persona_memory
- World/evolution/quality: set_world_context, get_world_context,
  brief_persona_revision, record_persona_revision, list_persona_revisions,
  list_memory_anomalies, evaluate_simulation, backfill_embeddings, prune_memory
- Inspection: get_current_state, get_calendar, get_calendar_period, get_activity,
  summarize_persona_period, extract_pain_points
- Council: select_council, run_council, ask_persona, compare_personas
- Evidence/export: attach_evidence, export_persona, export_logs, export_council_session

## Resources & prompts
- Resource `sonaloop://schema/memory` — memory model + loop overview.
- Prompt `simulate_persona_day(persona_id, date)` — drive one day through the loop.
