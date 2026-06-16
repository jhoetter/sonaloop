# Sonaloop Agent Guide

Sonaloop is terminal-first and MCP-first. The web UI is an inspection
surface only.

## THE FRONT DOOR — a research question IS the assignment (read this first)

When the user's message is a research question — an HMW ("How might we …"), "explore X",
"what do/would users think of Y", "is there a market for Z", or any request to understand,
validate, or position a concept/segment — **do not answer it from your own knowledge**. Even
when the message is JUST the bare question with no other instruction, that prompt is the
assignment to run a Sonaloop research project end-to-end:

1. **Cohort**: `list_personas` — reuse a fitting cohort. Thin or empty? The curated catalog
   has 300+ ready-made personas with lived memory: `catalog_search` / `catalog_recommend` →
   `catalog_pull`. Author from scratch (`brief_persona` → `record_persona`) only what the
   catalog lacks. If the cohort has no simulated memory (`start_project` warns), deepen it
   FIRST (simulate days/months) — councils are only as deep as the lives behind them.
2. **Project**: `start_project(title, goal=<the question>, methodology=…, persona_ids=[…])`.
3. **Governed loop**: `start_run(project_id)`, then loop `run_step(run_id)` — execute each
   dispatch (author the step, persist via MCP, link every produced evidence ref, `checkpoint_step`) until it returns
   `kind=='done'` (CLI: `run-start` / `run-step` / `run-checkpoint`). Only the engine ends the run (`assess_project.finish.finished` + the
   completeness critic) — never your own sense of "enough", and never at a phase boundary.
4. **Hand-off**: point the user at the inspector (http://127.0.0.1:8787) + the Deliver
   synthesis/report. If your session must end mid-run, say so and hand over
   `start_run(project_id, run_id=…)`.

Answering a research prompt with your own brainstorm is the failure mode this section exists
to prevent: your ideas are at best hypotheses; the personas' grounded reactions are the
product.

## Principles

- Do not infer product interest from the repository name, app name, or the fact
  that this is a council tool.
- Do not steer profiles toward AI, automation, or any other product thesis
  unless the profile source description, attached evidence, recent calendar, or
  explicit task context supports it.
- Treat synthetic details as hypotheses. Prefer ordinary work, skepticism,
  indifference, satisfaction, and rejection when those are plausible.
- Before speaking from a profile perspective, load `SOUL.md` through
  `prepare_persona_agent_context` or `sonaloop persona-context`.
- Use CLI/MCP for all CONTENT mutations: create profiles, generate avatars,
  simulate days, attach evidence, run councils, clear simulations, export logs.
- Point the user to the web inspector as soon as there is something to see. Once
  personas/councils/syntheses exist, tell them to open **http://127.0.0.1:8787**
  (start it with `make dev`, or `sonaloop-web`, which prints the URL). The
  web UI never authors or edits generated/authored TEXT; it does offer
  STRUCTURAL writes — create/edit/delete projects, notes and sections, persona
  metadata edits, and deletes — documented in docs/web-mutations.md.
- Language: generated CONTENT follows the language the user writes in, auto-
  detected on first input and persisted (de|en). Do not switch languages
  mid-stream. The web UI language is independent (toggle in the top bar, or
  `set_language`/`set-language`). Override content language only if asked.

## CLI

**Invocation ladder** — work down it; don't probe, and never give up at "command not found":

1. **MCP first**: if your host has the `sonaloop` MCP server connected, use the MCP tools —
   the richest surface (envelopes, `next_recommended_tool`, validation contracts).
2. **`uv run sonaloop <cmd>`** from this checkout — works with NO install (uv resolves the
   project venv). This is the default CLI invocation; the bare `sonaloop` is not on PATH.
3. **`python -m sonaloop.cli <cmd>`** if `uv` is unavailable in your shell.
4. Only if a step fails on missing dependencies: run `uv sync` once, then retry (2).
   Do not install globally (`uv tool install` / `pip install`) unless the user asks.

The CLI and the MCP tools are the SAME service surface — including the governed run loop:
`run-start` / `run-step` / `run-checkpoint` / `run-critic-round` / `run-finish` / `run-journal`.

```bash
# Cohort: check the curated catalog FIRST (300+ ready-made personas with lived memory),
# author from scratch only what it lacks.
sonaloop catalog-search --query "restaurant"
sonaloop catalog-recommend --keywords pflege,schicht -n 5
sonaloop catalog-pull --personas anna-petersen,ali-hassan     # drift-safe; --force overwrites local edits
sonaloop catalog-status                                       # the git fetch && git status of the catalog

# Persona creation is host-authored (no server-side text generation):
# gather -> you author the profile JSON -> persist.
sonaloop brief-persona "Restaurantleiterin in Deutschland, mittelgroßes Team, plant Schichten, Lieferanten, Reklamationen und Tagesabschluss, nutzt Kassensystem, Dienstplan, E-Mail und Telefon."
sonaloop record-persona profile.json   # JSON: {description, profile, segment_hint?, evidence?, generate_avatar?}
sonaloop persona-list
sonaloop persona-get <persona-id-or-slug>
sonaloop persona-soul <persona-id-or-slug>
sonaloop persona-context <persona-id-or-slug> --task "Evaluate this idea neutrally" --text
sonaloop avatar-generate <persona-id-or-slug>

# Single day, host-authored: brief-day -> author {day_plan, plan, activities} -> record-day.
sonaloop brief-day <persona-id-or-slug> --date 2026-06-02
sonaloop record-day <persona-id-or-slug> 2026-06-02 day.json
sonaloop simulate-continue --all --days 1
sonaloop simulate-clear
sonaloop purge-runtime-data

sonaloop calendar <persona-id-or-slug> --date 2026-06-02 --view day
sonaloop calendar <persona-id-or-slug> --date 2026-06-02 --view week
sonaloop activity <activity-id>
sonaloop state <persona-id-or-slug>
sonaloop summary <persona-id-or-slug> --start 2026-06-01 --end 2026-06-30

# Councils & interviews are host-authored (see the run-council skill):
#   brief-council <prompt>                 -> candidate personas to choose from
#   brief-council <prompt> --persona <id>… -> each participant's loaded context
#   (author turns + synthesis) -> record-council council.json
sonaloop brief-council "Should we change the approval workflow?" --persona <id> --persona <id>
sonaloop brief-ask <persona-id-or-slug> "What would make this unacceptable in your week?"

# Language: content is auto-detected from what you write, then persisted (de|en).
sonaloop language
sonaloop set-language --content de --ui en

sonaloop evidence-attach <persona-id-or-slug> interview notes/interview-01.md --notes "Customer interview"
sonaloop export-logs <persona-id-or-slug> --format md --out exports/logs.md
sonaloop export-council <session-id> --format md --out exports/council.md
```

## MCP

Run:

```bash
sonaloop-mcp
```

Core MCP tools:

- `brief_persona` (gather) → `record_persona` (persist authored profile), `update_persona`
- `get_persona`, `list_personas`, `get_persona_soul`
- `prepare_persona_agent_context`
- `generate_avatar`
- `brief_day` → `record_day` (host-authored single day); `record_month_bundle` for
  months; `continue_simulation`, `clear_simulations`, `purge_runtime_data`
- `get_current_state`, `get_calendar`, `get_calendar_period`, `get_activity`
- `summarize_persona_period`, `extract_pain_points`
- `brief_council` (gather candidates/contexts) → `record_council` (persist authored
  turns + synthesis), `get_council`, `list_councils`, `brief_ask`
- `get_language`, `set_language` (UI + generated-content language, de|en)
- Persona catalog (github:jhoetter/sonaloop-data, published at data.sonaloop.com —
  the deployed site serves the raw files as the API): `catalog_search` (browse: slugs/
  names/roles + facet summary; paginated) → `catalog_recommend` (deterministic,
  explainable persona-set recommendation; needs the sonaloop-data package) →
  `catalog_pull` (import personas/packs into the current store with
  `provenance.catalog` stamped; idempotent re-pulls, drift-SAFE: locally modified
  personas are skipped + reported unless `force=True`). `catalog_status` is the
  `git fetch && git status` of the catalog: per pulled persona — up_to_date /
  behind / locally_modified / diverged / removed_upstream. For catalog personas
  `refresh_persona_from_source` re-pulls from the recorded ref. Search + status +
  pull also work WITHOUT sonaloop-data installed, via a stdlib fallback against
  the published catalog. The other pull paths live in sonaloop-data (in-process
  `load_into`, `sonaloop-data pull` CLI / `pull_remote`).
- `attach_evidence`
- `export_persona`, `export_logs`, `export_council_session`
- Lifecycle hooks (docs/lifecycle-hooks.md): `list_lifecycle_events` →
  `register_hook` (command/webhook on e.g. `council.recorded`, `run.finished`) →
  `test_hook`; `list_hooks`, `unregister_hook`. CLI: `hooks-events`, `hook-register`,
  `hooks-list`, `hook-test`, `hook-remove`.
- Embeddings are provider-agnostic (docs/embeddings.md): SONALOOP_EMBEDDINGS_PROVIDER =
  openai | ollama | none (default: openai iff OPENAI_API_KEY, else none). Vector spaces
  never mix — recall skips+reports rows from another provider/model; switching = config
  change + `backfill-embeddings`. `sonaloop info` shows the resolved provider.
- Selective live actuation, rung 2 (docs/selective-live-actuation.md): `walk_own`
  (prototype_id → localhost, or a SONALOOP_OWNED_ORIGINS staging url; origin-locked,
  caps clamped to 40 actions / 300s; fail-soft without the browser) →
  `record_actuation_gate` (the rung-1-vs-rung-2 evidence head-to-head, persisted; live
  must WIN before it becomes a default anywhere).
- Screenshot flows — walkthrough with drop-off, artifact-first (docs/flow-walkthrough.md):
  attach the screens as assets → `define_flow(project, title, steps=[{asset_id}])` →
  `brief_flow_walkthrough` (view_asset every screen, author the timeline, dropoff_step +
  reason, predicted_behaviors) → `flow_funnel` (where the segment abandons and why). No
  live browser. CLI: `flow-define`, `flows-list`, `flow-funnel`.
- The calibration backtest loop (docs/calibration.md): `record_prediction_outcome`
  (match a real outcome to a prediction; Brier derived) → `calibration_report` (mean Brier,
  hit rate, reliability curve; persisted) → `calibration_trend` (the Brier delta over time) →
  `brief_calibration` (the misses + evidence) → author corrections (update_persona /
  record_grounding) → `record_calibration_round`. CLI: `calibration-report`, `calibration-trend`.
- Predicted behavior, not opinions: author `predicted_behaviors` (canonical
  `suggest_likelihood_levels` or raw 0..1 + evidence refs) on usability outcomes, councils
  (`record_council(predictions=…)`) and syntheses; `aggregate_predictions(project_id)` is the
  segment roll-up ("3 of 5 abandon at the price reveal") riding get_study_result and
  brief_hypothesis — promote recurring groups into falsifiable bets. CLI: `predictions-aggregate`.
- Grounding in REAL material (docs/grounding.md): `ingest_corpus` (transcript/tickets/
  reviews → deduped citable chunks) → `brief_grounding` (author a persona or patch FROM
  the chunks, with provenance) → `record_grounding` (claim → chunk-id traceability;
  emits `persona.grounded`). Sessions then carry the task-relevant chunks and cite them
  as refs {kind:'evidence', id, quote}; `trace_evidence`/`search_corpus` resolve and
  pull signal. CLI: `corpus-ingest`, `corpora-list`, `corpus-search`, `grounding-record`,
  `evidence-trace`.
- The queryable substrate (docs/substrate.md): versioned, paginated programmatic reads —
  `substrate_schema` (pin the contract) → `query_personas`/`query_projects`/`query_councils`/
  `query_syntheses` (filters: q, since, status; stable ordering) → `get_study_result` (the
  one-call structured result automations poll). Durable persona chat: `chat_with_persona`
  (gather context + history) → author the reply → `record_chat_turn` (persists, emits
  `chat.recorded`); `get_chat`, `list_chats`. CLI: `query-*`, `study-result`,
  `substrate-schema`, `chat-brief`/`chat-record`/`chat-get`/`chat-list`.
- Project assets — files/images/screenshots as evidence (docs/project-assets.md):
  `attach_asset` (path or base64) → `view_asset` (images return as REAL pixels — look
  before citing), `attach_prototype_shot`, `list_assets`, `get_asset`, `remove_asset`.
  brief_council puts every project asset in the room automatically. CLI: `asset-attach`,
  `asset-list`, `asset-get`, `asset-remove`.

Memory & multi-resolution simulation (gather → author → write-back):

- Planning: `brief_day`/`put_day_plan`/`get_day_plan`,
  `brief_period`/`put_period_plan`/`get_period_plan`/`list_period_plans`
- Consolidation: `brief_consolidation`/`record_memory_deltas`
- Digests: `brief_digest`/`put_digest`/`list_digests`
- Retrieval/inspection: `recall_memory` (hybrid: keyword + OpenAI embeddings),
  `list_active_projects`, `get_project`, `get_state_at` (time-travel),
  `get_timeline`, `search_entities`, `get_open_loops`, `resolve_entity`,
  `get_persona_memory`
- World/evolution/quality: `set_world_context`/`get_world_context`,
  `brief_persona_revision`/`record_persona_revision`/`list_persona_revisions`,
  `evaluate_simulation`, `brief_eval_critic`/`record_eval_critic`/
  `evaluate_simulation_full`, `list_memory_anomalies`, `backfill_embeddings`,
  `prune_memory`
- Driver: `brief_month`/`record_month_bundle`
- Synthesis (study arc over a council chain = an **analysis**: question → council
  loop → synthesis report): `brief_synthesis`/`record_synthesis`/`get_synthesis`/
  `list_syntheses`/`export_synthesis`. `brief_synthesis` returns per-persona turns +
  votes per council; author the structured **`voices`** array in the payload (one per
  persona: `sentiment`, `relevance`/tangiert, `key_argument`, `shift`{from,to,trigger,
  council_id}, `evidence`[{council_id,quote}]) — this powers the report's filterable
  Stimmen panel and the self-contained `export_synthesis` (md/json) for downstream agents.
- Portability: `export_snapshot`/`import_snapshot` (data/export is the one
  portable artifact; it is gitignored/local-only, as is the SQLite DB runtime)
- Research-plan engine — the SINGLE runtime engine (structure-enforcing + LLM-judged; ZERO hardcoded
  vocabularies): a per-project DAG of analyze→act→verify **tasks**, each bound to a free `capability`
  and referencing the evidence it produced. `start_project` (freeform: one root `frame` task; or
  `methodology=…`: seed the constellation), then the per-iteration loop `next_action`/`brief_next` →
  author the step → `add_task`/`record_frame`/`link_evidence`/`record_judgment`(free `gate_tag`) →
  `complete_task`, with `assess_project`/`assess_progress` for the read-only meta-assessment.
  Tag-agnostic: it enforces only the DAG (`consumes`), integer `min_inputs`, tag-equality references,
  and evidence-backed judgment PRESENCE — never tag membership. Shape (diverge/converge/diamonds/
  branches/loops) is DERIVED from the task DAG + recorded evidence.
- Project trace contract for agents: every `run_step`/`next_action` dispatch carries
  `consume_refs`, `optional_context_refs`, `open_questions`, `expected_output_kind` and
  `must_link_before_complete`. For `act` and `verify`, first record the output primitive
  (council, survey, prototype, session, synthesis, decision, asset/reference as appropriate),
  then call `link_evidence(project_id, task_id, kind, evidence_id)` before `complete_task`.
  If output should stay visible but deliberately not feed a downstream gate, call
  `park_evidence(refs, reason)` instead of leaving it stranded. `complete_task` returns a
  `TRACE_LINK_MISSING` nudge when evidence was completed without a trace link; repair that before
  moving on. `checkpoint_step` should echo `consume_refs`, `produced_refs`, `downstream_refs`,
  `open_questions` and `parked_refs` so the run journal can explain what happened later.
- ESV — exhaustive, self-verifying runs (`spec/exhaustive-self-verifying-runs.md`). The autonomous loop
  is a **deterministic RunLoop engine** the host skill executes: `start_run`(resumable run object +
  journal) → loop `run_step` (the brain: assess + next_action + the deterministic finish work + the
  critic gate) → spawn ONE subagent per dispatch → `checkpoint_step`. "Done" ≠ "gates passed": a run is
  only `complete` when `assess_project.finish` is **finished** (organized via `derive_sections` +
  concluded + handed-off via `scaffold_meta_report`/meta-report) AND an INDEPENDENT
  **completeness critic** (`brief_completeness_critic`→`record_completeness_critic`, rubric in
  `suggestions/critic_rubric.json`) passes — it lists concrete `missing` work (un-sampled segments,
  un-prototyped concepts, untested risks, missing fidelity rungs), the driver injects each as real work
  (`inject_work`) and re-runs until dry (K=2, hard cap 4). `assess_project` also surfaces `novelty`,
  `memory_depth` (thin cohorts → deepen via simulate-cohort), and `score_run` tracks quality over time.
  Concepts are first-class (`create_note kind="concept"` {lens, artifact_kind, prototype_id}). Resumable
  via deterministic keys; a killed run replays its journal with zero lost work.
- Methodologies = tag-driven CONSTELLATION **plan seeds**: a methodology is a DAG of steps carrying
  OPEN TAGS (capability/role/artifact-type/gate are free strings). `list_methodologies`/
  `get_methodology`/`start_methodology_project`/`set_project_methodology` SEED a plan from the
  constellation (a `frame` analyze task per fan step, a gated `verify` task per decide step); the plan
  engine then drives it. Common building blocks are SUGGESTED as data via `suggest_capabilities`/
  `suggest_roles`/`suggest_artifact_types`/`suggest_methodologies` — recommendations, not constraints;
  adopt, tweak, or invent your own tags. Authoring a new methodology = author a constellation of
  tagged steps in JSON (no code). Since HX3 there is ONE engine (the plan); the old constellation
  runtime (`record_node`/`record_decision`/`advance`/`get_methodology_state`) was retired — see
  `spec/hx3-engine-collapse.md`. Specs: `spec/methodology-constellations.md`, `spec/research-plan-engine.md`.
- Prototypes (real, minimal, local apps agents can use): `scaffold_prototype` (concept→clickable
  SPA), `register_prototype`, `list_prototypes`, `run_prototype`/`stop_prototype`; the Playwright
  harness `proto_open`/`proto_act`/`proto_read`/`proto_close` lets a persona drive the REAL app,
  and `brief_prototype_session`/`record_prototype_session` fold the grounded reaction into memory.
  Artifact archetypes are DATA (`suggestions/artifact_types.json`, surfaced as the `artifact_palette`
  in `next_action`): a guided `flow`, a `comparison`, a `dashboard`, a `cards` interface, or an
  interactive **`model`** (range/number inputs feeding `computed`/`bar` elements whose `formula` is
  evaluated live — a steerable pension-gap/compounding simulation, not a static screen), or a
  **`journey`** (a model embedded in a multi-screen flow with cross-screen state + `chart` live curves
  + `verdict` data-driven conditional text — the production-credible hi-fi class) — diversify the KIND,
  don't default to a form. `record_prototype_session` returns an `UNVERIFIED_SESSION`
  warning (and a session_of_tags gate requires a GROUNDED session) when a reaction isn't verified
  against real observed usage — the session log is retained past `proto_close` so a real drive verifies.
  Install with `make playwright` (optional; degrades gracefully without chromium).
- Composable graph — the graph is a canvas of composable LOW-LEVEL primitives (council · synthesis ·
  prototype · **note** · edge · **section**); the methodology/plan engine is ONE optional orchestrator,
  not the only structure (spec/sections-and-composable-graph.md):
  - **Sections** = methodology-INDEPENDENT labeled overlay groupings of nodes ("Initial user research",
    "Problem exploration"). Explicit set-membership (overlap allowed), a pure overlay (never alters the
    DAG layout), reference-not-containment (deleting a section never deletes nodes), `kind` an open tag
    (theme/phase/invented, data-driven via `section_kinds.json`). `create_section`/`update_section`/
    `add_to_section`/`remove_from_section`/`set_section_members` (promote-a-cluster)/`reorder_sections`/
    `list_sections`/`get_section`/`delete_section`/`get_section_members`/`export_section` (md/json,
    self-contained) + `suggest_section_kinds`. Methodology phases render as DERIVED `phase` sections.
  - **Notes** = lightweight first-class observation nodes (the atomic unit for affinity), creatable with
    NO methodology: `create_note`/`list_notes`/`delete_note`. They are normal graph nodes (groupable
    into sections, linkable by edges).
  - **Syntheses are DECOUPLED from councils**: a synthesis can have zero councils (affinity over notes,
    a synthesis over other syntheses, a standalone analysis); councils are cited, not owned.

Every tool returns an envelope `{ok, data, next_recommended_tool, _meta}`; the
`next_recommended_tool` hints the decision DAG (simulate → consolidate → digest;
council → synthesis). Full surface + conventions: `spec/mcp-tool-contract.md`.

## Playbooks — two layers

The workflows ship in two forms, so Sonaloop works across every MCP host:

1. **Provider-agnostic (the MCP server itself).** Any host (Claude, Cursor, ChatGPT, …) gets:
   - **Server `instructions`** in the `initialize` response — the operating contract above, auto-injected.
   - **MCP prompts** — `run_council`, `synthesize`, `design_thinking`, `compose_research_plan`,
     `simulate_persona_day` — ready playbooks any client can list + run. They describe a SEQUENTIAL
     single-agent core; parallel sub-agent fan-out is an optional acceleration. Defined in
     `sonaloop/mcp_server/_prompts.py`.
   - The `sonaloop://guide/catalogue` resource — a by-domain index of every tool.

2. **Claude Code skills (an adapter on top).** Run `make skills` once (symlinks `claude-skills/*` into
   gitignored `.claude/skills/`). These add Claude-specific auto-triggering + sub-agent fan-out over the
   same workflows. Thin orchestration playbooks; the methodology lives in `spec/`. A non-Claude host
   simply follows the MCP prompts + instructions instead.

- `methodology-run` — drive a plan-based methodology constellation (Double Diamond, d.school
  micro-cycle, Lean/JTBD, … or any you author) over the graph via the analyze→act→verify plan loop:
  genuinely fan out act tasks (real councils / built+tested prototypes) then converge behind an
  evidence-backed gate (`record_judgment` + a `record_synthesis`), incl. build/test steps where
  personas USE a real app via Playwright. The plan engine enforces the shape; you author the text.
  Specs: `methodology-constellations.md`, `research-plan-engine.md`.
- `simulate-cohort` — run the day/period loop for personas over months (sampling).
- `run-council` — memory-grounded council; judicious self-research (recall only
  when it sharpens the answer); optional moderated back-and-forth with mediator
  strategies (`positive-deepdive`, `pain-discovery`, `tension`, `goal`) and a
  hand-raising convergence loop + upper bound.
- `synthesize` — iterative driver: one statement → councils → read each exec
  summary → decide a follow-up (self-contained question, personas are
  council-stateless) or stop (goal reached / no follow-up / max 10) → report.

## Persona-Subagent Workflow

1. Call `prepare_persona_agent_context(persona_id, task, recent_events)`.
2. Verify `soul_loaded=true`.
3. Use the returned `agent_context` as the launch context for the subagent.
4. Ground responses in the loaded SOUL, recent events, evidence, and task.
5. If the context does not support a product-friendly answer, the profile should
   be skeptical, neutral, or rejecting.

## Simulation Quality

- Good simulations include timestamped activities, concrete tools/artifacts,
  realistic conversations, internal thoughts, decisions, unresolved loops, and
  emotional/energy shifts.
- Persona answers and council turns are LLM-authored through MCP/service calls;
  they must load `SOUL.md` via `prepare_persona_agent_context`.
- Council selection is LLM-authored from candidate persona summaries. Do not
  choose participants with fixed keyword scoring or product-topic assumptions.
- A meeting should contain enough conversation to understand what happened, not
  just one summary quote.
- A workday should include mundane friction and normal progress, not only
  problems.
- Calendar continuity matters: unresolved loops should influence later days.

## Documentation

A feature isn't done until the documentation surfaces are updated: the deep
agent-facing notes in `docs/*.md`, the user-facing bilingual in-app docs hub
(`sonaloop/web/_docs_content.py`), and — for anything product-facing — the
canonical published docs in the **sonaloop-docs** repo (page + `mkdocs.yml` nav +
`docs/llms.txt` index). The split rule and the discoverability map live in
[docs/README.md](docs/README.md). Every new env var gets a one-line entry in
[.env.example](.env.example).
