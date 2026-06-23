# HX3 — Collapse the two engines (self-spec)

> Authority for the HX3 refactor (`spec/harness-evaluation-and-autonomy.md` §3 / §3b.2). Goal: ONE
> runtime engine. `plan.py` (analyze→act→verify) is canonical; methodologies are **only** plan seeds;
> the constellation runtime (`runtime.py` + the `phase_log` engine inside `methodology.py` + its MCP
> tools/CLI commands) is **retired**. No behavior loss for plan-driven projects (already the live
> path). Suite stays green at every commit.

## 1. Where we already are (measured)
- `start_project(... methodology=...)` already **seeds a plan** (`seed_plan_from_methodology`); the old
  `set_project_methodology` phase_log write is a redundant back-compat side-effect.
- `services.brief_next` / `services.record_judgment` already **dispatch to the plan** when a project
  has one (which all new projects do).
- `get_project_graph` already routes to `plan_graph`, whose `methodology_state` is derived from the
  plan via `_plan_methodology_state` — **not** from `phase_log`. The `get_methodology_state`/`phase_log`
  branch in `get_project_graph` only fires for compatibility plan-less methodology projects.
- The ONLY autonomous driver, `runtime.run_methodology`, runs on the constellation engine with a
  `StubAuthoringBackend`. It is unused in production (CLI `run-methodology` + 2 tests only).

So the duplication that remains is: (a) the unused autonomous driver, (b) a parallel MCP/CLI surface
(`record_node`/`record_decision`/`advance`/`get_methodology_state`/…), (c) the `phase_log` lifecycle
engine inside `methodology.py`, and (d) the compatibility graph branch.

## 2. Target end state
**`plan.py`** — unchanged; the single runtime engine.

**`methodology.py`** — demoted to a **spec + registry + structural-helper** module. KEEPS:
`validate_methodology_spec`, `_normalize_spec`/`_norm_step`/`_phases_to_steps`, `registry`,
`get_methodology`, `list_methodologies`, `register_methodology`, and the structural helpers
`plan.py` reuses: `_is_decide`, `_artifact_tags`, `_project_artifacts_with`, `_sessions_of`. LOSES the
phase_log lifecycle: `start_methodology_project`, `set_project_methodology`, `brief_next`,
`brief_phase`, `record_node`, `record_exploration`, `record_judgment`, `record_decision`,
`record_convergence`, `advance`, `advance_phase`, `get_methodology_state`, plus phase_log internals
(`_slog/_entry/_nodes/_is_complete/_ready/_judgments/_node_payload/_primary/_gate_tag_for_fan/`
`_ensure_methodology_project/_consumers/_step/_mode/_judgment_id/COMPLETE`).

**`runtime.py`** — DELETED (driver + `StubAuthoringBackend`).

**Services (`_engines.py` + `__init__`)** — drop the imports/exports of the retired functions.
`start_methodology_project(title, goal, key, …)` becomes a thin forward to
`start_project(… methodology=key)` (kept so the name/CLI/registry stay valid). `brief_next` /
`record_judgment` stop dispatching — they require a plan (raise `PlanError("NO_PLAN", …)` otherwise).

**MCP (`_tools_methodology.py`)** — remove the retired tools. Keep `suggest_*`, `list_methodologies`,
`get_methodology`, `start_methodology_project` (→ forwards), `set_project_methodology`
(→ re-seed a plan), and `brief_next` (plan router). Subagents now see ONE engine surface.

**CLI** — remove `run-methodology`, `methodology-state`, and the constellation stepping commands
(`step-node/step-decide/step-advance/step-judge`, `phase-explore/phase-judge/phase-converge/`
`phase-advance/phase-brief`). Keep `methodology-list/-get/-suggest/-start` (→ start_project),
`next-brief` (plan router) and the `plan-*` / `project-*` family.

**`get_project_graph`** — derive `methodology_state` from `_plan_methodology_state` for any project
with a plan; remove the `get_methodology_state`/`phase_log` branch. Route to `plan_graph` whenever a
plan exists (a freshly-seeded methodology project shows its diamond structure immediately).

**Storage/models** — `phase_log` field, `MethodologyJudgment`, `list/insert_methodology_judgment`
become dead code paths. Left in place (no migration risk; `import_snapshot` compat); not on any
active path.

## 3. Test migration
- `tests/test_runtime.py` — DELETE (driver gone). Plan completion is covered by `test_research_plan`.
- `tests/test_web_methodology_layout.py` — replace the `runtime.run_methodology` setup with a small
  **deterministic offline plan driver** (`_drive_plan`) in the test: seed via `start_project`,
  discharge each frame, add act councils per fan step, scaffold the lo-fi/mid-fi prototypes under the
  build frames, record a synthesis per verify. Same assertions (3 diamonds / 2 routed protos for
  deep; 2 / 1 for micro; no phase-key literals). This driver is the plan analogue of the old
  `StubAuthoringBackend`, owned by the test (production has ONE engine, no stub driver).
- `tests/test_methodology_engine.py` — keep the spec-validation / registry / no-hardcoded-vocab /
  seed tests; remove the phase_log lifecycle tests (record_node/decision/advance/state/aliases).
- `tests/test_research_plan.py::test_compatibility_methodology_project_still_renders` — remove (the compatibility
  plan-less path is gone; every methodology project now has a plan).
- `tests/test_mcp_contract.py` — drop assertions on the removed tools; assert the plan surface.

## 4. Sequence (commit + push after each; suite green)
1. Sub-spec (this file).
2. Graph routes only through the plan; migrate the layout test.
3. Remove the constellation MCP/CLI surface + service forwards; forward `start_methodology_project`.
4. Delete `runtime.py`; strip the phase_log engine from `methodology.py`; migrate the engine test.
5. Update `harness-evaluation-and-autonomy.md` (HX3 ✅) + observations; final green suite.
