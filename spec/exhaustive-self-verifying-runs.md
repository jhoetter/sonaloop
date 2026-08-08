# Exhaustive, Self-Verifying Runs (ESV) — build-ready specification

> **Status:** ✅ IMPLEMENTED 2026-06-05 (ESV0–ESV6, suite green, pushed). ESV1 auto-organization
> (`derive_sections`+`scaffold_meta_report`); ESV2 completeness critic + rubric + concepts-as-data;
> ESV3 resumable run object + keyed prototype sessions; ESV4 the deterministic RunLoop driver
> (`run_step`/`inject_work`) + loop-until-dry critic gate (the keystone) + the host-skill rewrite;
> ESV5 the `journey` type + `spa-journey` + `chart`/`verdict`/`timeline` + evaluator comparison ops;
> ESV6 `cohort_memory_depth`/`memory_depth` + `score_run` + the pipeline regression test. Each shipped
> with tests; the driver is unit-tested end-to-end via a deterministic stub (OD-4: completes a
> methodology, the critic loop injects work then converges, a killed run resumes identically).
> Originally a build-ready SPEC; the design below stands as the reference. The detailed design for the three big-leverage moves in
> `spec/harness-leverage-roadmap.md`, plus the supporting work, broken into ordered milestones with
> data models, tool signatures, control flow, and acceptance criteria. **North star:** one HMW prompt
> → a resumable, multi-agent run that keeps going until an *independent critic* says it is exhaustive
> AND the project is organized + concluded + handed-off — every time, without depending on one agent's
> context or self-judgment.
>
> **Standing invariants (unchanged):** no in-process LLM text generation — the DRIVER is deterministic
> (no LLM), per-step AUTHORING is always a Claude subagent via the MCP `brief_*→record_*` contract;
> zero hardcoded methodology vocabulary (everything below is open tags / data / `suggestions/*.json`);
> the web UI stays read-only; structure enforced, dynamics LLM-judged with cited evidence; honesty
> (unknown → an open question, never fabricated progress). Suite green + commit/push per milestone.

---

## 0. Architecture at a glance

```
                       ┌──────────────────────────────────────────────────────────┐
                       │  DETERMINISTIC DRIVER  (Workflow script / RunLoop — NO LLM)│
   one HMW prompt ───► │  loop:  assess_project ─► next_action ─► dispatch 1 agent  │
                       │         per step ─► persist (keyed, idempotent) ─► journal │
                       │  stop ONLY when:  critic.passed  AND  finish.finished      │
                       └───────┬───────────────────────────┬───────────────────────┘
                               │ per-step (fresh context)   │ before stop (loop-until-dry)
                               ▼                            ▼
                    ┌──────────────────────┐     ┌────────────────────────────────┐
                    │ STEP SUBAGENT (Claude)│     │ COMPLETENESS / QUALITY CRITIC  │
                    │ authors 1 step via MCP│     │ brief_completeness_critic →    │
                    │ returns ONLY ids + 1ln│     │ (subagent verdict) →           │
                    └──────────────────────┘     │ record_completeness_critic     │
                                                  │ missing[] ⇒ new work ⇒ re-crit │
                                                  └────────────────────────────────┘
   EXPERIENCE LAYER: richer artifact types (model-in-flow journey, charts, verdicts) so the
   prototypes the run builds + ground-tests are production-credible.
```

Three pillars (A driver, B critic, C experience) + supporting (D). Build order is in §6.

---

## A. The resumable, multi-agent DRIVER (Pillar 1 — the biggest lever)

### A.1 Goal
Replace "one agent runs the whole project inside one growing context and decides when it's done" with
a **deterministic driver** that (a) holds only ids + the two lean reads (`assess_project`,
`next_action`), (b) dispatches a **fresh subagent per step** so authoring context never accumulates,
(c) **persists every write idempotently under a deterministic key** so the run is resumable/replayable,
and (d) stops only when the critic (B) passes and the finish gate is satisfied.

### A.2 The run object + resumability (data model)
New storage table `runs` (gitignored DB, like the rest of runtime state):
```
runs(run_id TEXT PK, project_id TEXT, methodology TEXT, status TEXT,          -- active|finished|stopped
     budget INTEGER, cursor INTEGER, created_at TEXT, updated_at TEXT, data TEXT)  -- data = JSON below
```
`data` (the journal — the single source of truth for resume):
```jsonc
{ "run_id": "...", "project_id": "...", "steps": [
    { "idx": 0, "task_id": "frame__discover", "bucket": "analyze", "key": "<runkey>",
      "evidence": [{"kind":"frame","id":"frame__discover"}], "agent_id": "...", "status": "done",
      "summary": "9 questions, 11 memory refs" }, ... ],
  "critic_rounds": [ { "round": 0, "passed": false, "missing": 3 }, ... ] }
```
**Deterministic key scheme (the resumability core).** Every persistence call carries
`key = stable_id(kind, run_id, task_id, angle)` so a re-run of the same step is an **idempotent upsert**
(no duplicate, same id). Required `key` support (extend where missing — `record_council`/
`record_synthesis` already have it):
| write              | keyed by                                   | status |
|--------------------|--------------------------------------------|--------|
| `record_council`   | `key="<run>:<task>:<angle>"`               | ✅ done |
| `record_synthesis` | `key="<run>:<task>"`                        | ✅ done |
| `scaffold_artifact`| `slug` (already idempotent)                | ✅ done |
| `record_prototype_session` | **add `key`** = `<run>:<proto>:<persona>` | ⬜ new |
| `add_task`         | `task_id` (already explicit/idempotent)     | ✅ done |
| `record_frame` / `record_judgment` / `link_evidence` | idempotent by (task[,gate,ref]) | ✅ done |

`record_prototype_session` gets an optional `key` → `id = stable_id("protosession", key)` + upsert
(mirror the council/synthesis change; one small validator + service edit + test).

### A.3 Driver interface (deterministic; the engine the host runs)
Implement as a **Workflow script** `workflows/esv-run.js` (the Workflow tool natively does deterministic
fan-out + `resumeFromRunId`), with a thin service layer it calls:
```
start_project(..., operation_id=None) -> project                             # retry-safe when key supplied
start_run(project_id, budget=None, run_id=None, operation_id=None) -> {run_id, cursor}
# operation_id = retry-safe initial create; run_id = resume an already known run
run_journal(run_id) -> {steps, critic_rounds, cursor, status}                # read the journal (lean)
checkpoint_step(run_id, step{key,...}) -> {cursor, step_idx, key, deduplicated} # compare-and-dedupe
finish_run(run_id, status) -> {run_id, status}                                # finished is fail-closed
```

#### A.3.1 Dispatch-token write binding

`run_step` persists and returns a deterministic `dispatch_token` scoped to the run/project/task/
bucket/key. On `dispatch_v1` projects every active-run content write must echo it. Token-aware
recorders validate scope before mutation, adopt the dispatch key for primitive idempotency, link the
produced ref, complete the task when its evidence/gates are ready, and append the checkpoint. The
host must not append a second manual checkpoint when `dispatch.checkpointed=true`.

If a multi-write verify is incomplete, the first recorder returns linked/not-checkpointed; the
token-bound judgment (or other missing write) performs completion/checkpoint. Exact transport replay
deduplicates both primitive and receipt. A changed immutable write, foreign scope, wrong bucket/task,
or closed uncheckpointed dispatch fails before mutation. Legacy projects retain their prior paths with
explicit provenance. See `docs/research-integrity.md`.

Driver loop (pseudocode — NO LLM in the driver itself):
```
run = start_run(project, budget, operation_id=stable_run_create_key)
while budget_remaining(run):
    a = assess_project(project)
    if a.recommendation == "finish":            # gates met, not finished → organize+conclude+handoff
        do_finish_steps(a.finish)               # auto-organize (D.1), conclusion subagent, meta-report
        continue
    if a.recommendation == "complete":          # plan done AND finished → run the CRITIC gate (B)
        if critic_passes_twice(project): finish_run(run, "finished"); break  # engine-verified only
        else: continue                          # critic injected new tasks → keep going
    n = next_action(project)
    spec = step_spec(n)                          # bucket-aware dispatch spec (what the subagent must do)
    if n.bucket == "act" and len(n.act.framed_questions) > 1:
        results = parallel( dispatch_step(n, angle) for angle in n.act.framed_questions )  # fan-out
    else:
        results = [ dispatch_step(n, key=run_key(run, n.task)) ]
    checkpoint_step(run, summarize(results))     # ids + 1 line only; never the authored text
```
`dispatch_step` spawns ONE subagent with: the lean `next_action` payload, the deterministic `key`, and
the bucket contract (A.4). The subagent persists via MCP and returns **only** ids + a one-line summary.

### A.4 Step-subagent contract (per bucket — fresh context each)
- **analyze (frame):** read `n.grounding` (cited persona memory + prior syntheses), author research
  questions + hypotheses, `record_frame`. Return the frame id.
- **act:** for the assigned ANGLE, run a REAL multi-persona council (`n.act.suggested_participants`,
  segment-diverse) via run-council, OR `scaffold_artifact` + a grounded Playwright proband session;
  `add_task` + `link_evidence` + `complete_task`. Apply `n.act.ideation_lenses` for ≥1 unexpected
  mechanism + ≥1 experienceable model on ideation steps. Return evidence ids.
- **verify:** consolidate `n.verify.fan_evidence` into a rich `record_synthesis` (structured blocks:
  clusters/key_problems/ranking/shortlist), record the gate judgment, `assess_progress`,
  `complete_task`. Return the synthesis id.

### A.5 Resume semantics
`resumeFromRunId` (Workflow) OR `start_run(run_id=...)` replays the journal: each already-checkpointed
step's keyed writes are idempotent **no-ops** (same id returned), so the longest unchanged prefix is
instant; the first new/edited step and everything after runs live. A run that died mid-flight resumes
from `assess_project` with zero lost work.

### A.6 Acceptance (A)
1. A run created by the driver completes a full methodology with one subagent per step; host context
   holds only ids (verify: the driver transcript never contains authored council/synthesis text).
2. Killing the driver mid-run and re-invoking with the same `run_id` reproduces the same project
   (same evidence ids; no duplicates) and continues — proven by a test that runs N steps, "kills"
   (stops), resumes, and asserts identical ids + completion.
3. Independent act angles run in parallel (wall-clock < sum-of-steps), persisted sequentially.
4. The driver never reports "done" while `assess_project.recommendation != "complete"` or the critic
   has un-filled `missing` items.

---

## B. The adversarial COMPLETENESS / QUALITY critic (Pillar 2 — exhaustiveness + consistency)

### B.1 Goal
An **independent** judge (not the author) that, before a run may stop, scores the project against a
rubric AND surfaces concrete `missing` work; the driver fills each gap and re-runs the critic until it
finds nothing material (loop-until-dry). This converts "one pass then stop" into "exhaustive".

### B.2 Tools (mirror `brief_eval_critic`→`record_eval_critic`)
```
brief_completeness_critic(project_id) -> {schema:"completeness_critic", frame:{...}, instructions:"..."}
record_completeness_critic(project_id, verdict, run_id, operation_id) ->
{id, passed, missing, scores, created_at, deduplicated}
```
`brief_completeness_critic.frame` is a COMPUTED snapshot (no LLM) the critic reasons over:
```jsonc
{ "goal": "<HMW>", "methodology": "...",
  "coverage": { "councils": 4, "syntheses": 3, "prototypes": 7, "personas_engaged": 13,
                "personas_total": 18, "segments_engaged": ["FIRE","prekär",...] },
  "breadth_candidates": {                              // the generative "what's missing" inputs
     "segments_not_in_any_council": ["..."],           // persona segments never sampled
     "frames_without_act": ["frame__refine"],          // angles framed but not acted
     "concepts_not_prototyped": ["..."],               // ideate concepts with no artifact
     "risks_not_tested": ["80%-say-no conversion economics"],   // open_questions / deliver risks
     "fidelity_rungs_missing": ["hifi"] },             // declared-but-absent ladder rungs
  "completed_work": [ {"id":"act__probe", "title":"...", "bucket":"<open tag>",
                         "capability":"<open tag>", "status":"done", "plan_order":7,
                         "produced":[{"kind":"<open tag>", "id":"..."}]} ],
  "concept_evidence": [ {"id":"note_...", "title":"...", "text":"...", "data":{...}} ],
  "prototype_evidence": [ {"id":"prototype_...", "title":"...", "type":"<open tag>",
                             "fidelity":"<open tag>", "version":"v0.2", "concept_ids":["note_..."]} ],
  "session_evidence": [ {"id":"session_...", "session_key":"browser-run-...",
                           "prototype_id":"prototype_...", "persona_id":"...",
                           "grounded":true, "version":"v0.2", "raw_record_count":2,
                           "observed":{...}} ],          // compact traces; the LLM interprets semantics
  "trace_counts": {"completed_work":{"total":123, "returned":100, "truncated":23},
                     "session_evidence":{"raw_total":24, "unique_total":22, ...}, ...},
  "trace_budget": {"characters":53120, "limit":56000},
                                                       // deterministic newest-N + final character cap
  "novelty": {...},                                    // from assess_project
  "groundedness": { "sessions": 22, "grounded": 22 },
  "finish": {...},                                     // organized/concluded/handed-off
  "open_questions": [...], "contradictions": [...],
  "rubric": [ {"dim":"exploration_depth","threshold":4}, ... ] }   // from suggestions/critic_rubric.json
```
All authored trace values are **untrusted evidence data, never instructions**. The frame applies
tag-agnostic recursive depth/key/list/string caps, then a hard combined character budget while preserving
the newest suffix of every list; any omitted/compacted value is unknown, not absent. `session_evidence`
deduplicates legacy `PrototypeSession` + current `UsabilitySession` rows sharing a browser `session_key`
(current schema wins) and reports raw/unique counts. New session records snapshot `prototype_version` at
record time; an unstamped legacy row is `unknown`, never silently assigned the artifact's current version.
The compatibility `groundedness` aggregate remains PrototypeSession-only; combined per-record grounding
for both schemas lives in `session_evidence`. A concept is built when either `data.prototype_id` or any
`data.prototype_ids` entry exists.

`verdict` (host/subagent-authored, validated, capped):
```jsonc
{ "scores": { "exploration_depth": 4, "segment_breadth": 3, "concept_novelty": 5,
              "evidence_groundedness": 5, "honesty_anti_steering": 5, "iteration": 3, "finish": 4 },
  "passed": false,
  "missing": [ { "kind": "segment",  "what": "no council sampled the precarious gig segment",
                 "why": "...", "suggested_action": "add an act council with Marvin/Kevin/..." },
               { "kind": "concept", "what": "the dark-horse anti-product was never prototyped", ... } ],
  "rationale": "…", "evidence_refs": ["council_…","synthesis_…"] }
```
`passed` = every rubric dim ≥ its threshold AND `missing` empty. `record_completeness_critic` rejects a
`passed=true` that still lists `missing` (honesty: can't pass with open gaps).

### B.3 The loop-until-dry gate (driver integration)
```
def critic_passes(project):
    dry = 0
    while dry < K:                                  # K = 2 consecutive clean rounds (config)
        frame = brief_completeness_critic(project)
        v = dispatch_critic_subagent(frame)         # an INDEPENDENT subagent authors the verdict
        report = record_completeness_critic(project, v, run_id, dispatch.operation_id)
        record_critic_round(run_id, report.id, dispatch.key)
        if v.passed and not v.missing: dry += 1; continue
        dry = 0
        for m in v.missing:                         # turn each gap into real work
            inject_work(project, m)                 # add_task / new angle / new concept / new test
        # the driver's main loop now has new ready tasks → it does the work → re-enters critic_passes
        return False
    return True
```
`inject_work` maps a `missing.kind` → a plan mutation (data-driven, open tags):
`segment`/`angle`→`add_task("act",…)` consuming the relevant frame; `concept`→an ideate act task to
build it; `risk`→a verify/test task or an open question; `fidelity_rung`→a build task at that tag.

### B.4 The rubric (data, editable)
`suggestions/critic_rubric.json` (dimensions + thresholds + the probing question per dimension), so
the bar is tunable and methodology-agnostic. Default dims: exploration_depth, segment_breadth,
concept_novelty, evidence_groundedness, honesty_anti_steering, iteration, finish.

### B.5 Acceptance (B)
1. On a deliberately thin project (1 council, 1 form), `brief_completeness_critic` surfaces concrete
   `missing` items (an un-sampled segment, an un-prototyped concept) and `record_completeness_critic`
   refuses `passed=true`.
2. The driver's `critic_passes` injects ≥1 new task per `missing` item and only returns true after K
   consecutive clean rounds — proven by a test that seeds a thin project and asserts the loop adds
   work then converges.
3. A run cannot reach `status=finished` unless the last critic round `passed` with empty `missing`.

---

## C. The richer EXPERIENCE / prototype layer (Pillar 3 — production-credible hi-fi)

### C.1 Goal
Let a prototype be a real EXPERIENCE: an interactive model **embedded in a multi-screen narrative
flow**, with **charts/curves**, and **data-driven conditional verdicts** — so the hi-fi the run builds
and ground-tests is production-credible, not a single computed screen. All data-driven (new artifact
types + templates + concept-schema element kinds); the safe no-`eval` evaluator is reused/extended.

### C.2 Concept-schema extensions (new element kinds + cross-screen state)
- **`chart`** — `{kind:"chart", id, label, x:{from,to,step}, series:[{label, formula}]}`: the renderer
  sweeps `x` over [from,to] and plots each `series.formula` (the formula may reference the swept var by
  the chart's x-id + the screen's input ids) as an SVG line/area — e.g. two compounding curves racing.
- **`verdict`** — `{kind:"verdict", id, cases:[{when:"<expr>", text},…], else:"text"}`: evaluates each
  `when` expr (same safe evaluator) in order and shows the first true case's text — the ONLY conditional
  display, still pure data (no code branching), enabling "if gap>0 say X else say 'you don't need this'".
- **`timeline`** — `{kind:"timeline", id, label, points:[{t, formula}]}`: a horizontal time series.
- **Cross-screen state:** inputs persist across screens (one `state` object for the whole concept) so a
  model steered on screen 2 drives a verdict/chart on screen 3 (a real journey, not isolated screens).

### C.3 New templates + artifact types (data)
- `suggestions/artifact_types.json`: add **`journey`** (`default_template: spa-journey`) — a model
  embedded in a guided multi-screen flow (intro → steer the model → see the consequence/chart → honest
  verdict/fork). Keep `model`.
- `prototype_templates/spa-journey/index.html`: the flow rail + the full model/chart/verdict renderer
  (reuse spa-model's `renderEl` + `evalFormula`, add `chart`/`verdict`/`timeline`, share `state` across
  screens). `spa-model` gains `chart`/`verdict` too (single shared renderer module copied into both).
- Extend `_ELEMENT_KINDS` with `chart`, `verdict`, `timeline`; `_validate_concept` validates their
  shapes (x range present; verdict cases are exprs; series formulas non-empty) and reachability.

### C.4 Evaluator extension
`evalFormula` already supports `+ - * / % ^`, parens, `min/max/round/abs/pow/floor/ceil`, vars. For
`chart`/`timeline`, evaluate the series formula once per swept x-value (the x-id is bound in `state`
during the sweep). `verdict` uses the same evaluator on boolean exprs (extend with comparison ops
`> < >= <= == !=` and `&&`/`||`, all in the recursive-descent parser — no `eval`).

### C.5 Acceptance (C)
1. A `journey` artifact scaffolds: a 3-screen flow where a model steered on screen 2 drives a `chart`
   (two curves) and a `verdict` on screen 3; nav validated; renders without `__CONCEPT_JSON__` left.
2. Driven via Playwright: changing an input updates the chart + flips the verdict (proven by a browser
   test reading two snapshots with different verdict text).
3. The grep gate stays green (no hardcoded fidelity/type literals in code; all in data).

---

## D. Supporting moves (high value)

### D.1 Auto-organization (make every run organized + concluded BY CONSTRUCTION)
`derive_sections(project_id)` — from the plan steps + their evidence + prototypes, create: a section per
phase (Discover/Define/…/Deliver — labels from the step names, no hardcoded vocabulary), a
"Prototype-ladder" section (all artifacts), a "Deliver — Conclusion" section (the terminal synthesis),
and a "Run-Journal" section (the run's notes). Idempotent (keyed by title). The driver calls it during
`do_finish_steps`; `assess_project.finish.organized` then flips true automatically. Add
`scaffold_meta_report(project_id)` that seeds the meta-report outline from the graph so the conclusion
handoff is one author step, not from scratch.
*Acceptance:* after `derive_sections`, a completed methodology project has ≥4 sections covering all
phases + a prototypes + a deliver section; `assess_project.finish.organized == true`.

### D.2 Deeper persona-memory grounding
A pre-run **`deepen_cohort(persona_ids, months)`** convenience that runs the simulation loop so councils
sit on rich, evolving memory; `assess_project` gains a `memory_depth` descriptor (avg events/facts per
engaged persona) and flags "thin memory" as a gap. Councils grounded in deeper lives → deeper, more
surprising exploration. *Acceptance:* the depth signal appears; a thin cohort is flagged.

### D.3 Eval harness (quality regression)
`score_run(project_id)` → persists a `RunScore` (the critic's last rubric scores + finish + novelty +
groundedness) so quality is tracked over time. A regression test drives a tiny canned project through
the driver and asserts: finish gate, critic loop converges, structured syntheses + grounded session +
sections all present. *Acceptance:* scores persist + the regression test guards the whole pipeline.

---

## 6. Build order (ordered milestones; each: implement → suite green → commit + push)
- **ESV1 — Auto-organization (D.1).** Cheapest, immediately makes runs *finish* (organized + conclusion
  + meta-report scaffold). Unblocks the finish gate everywhere. *(small)*
- **ESV2 — Completeness critic tools (B.2/B.4).** `brief_/record_completeness_critic` + the rubric data
  + validation; not yet looped. *(medium)*
- **ESV3 — Resumable keyed writes + the run object (A.2).** Add `key` to `record_prototype_session`;
  the `runs` table + `start_run`/`run_journal`/`checkpoint_step`/`finish_run`. *(medium)*
- **ESV4 — The deterministic driver + critic gate (A.3/A.4/A.5 + B.3).** The `esv-run` Workflow script
  (or `RunLoop`): loop, per-step subagent dispatch, parallel act fan-out, the loop-until-dry critic
  gate, resume. This is the keystone. *(large)*
- **ESV5 — Experience layer (C).** `journey` type + `spa-journey` template + `chart`/`verdict`/
  `timeline` element kinds + evaluator comparison ops. *(medium-large)*
- **ESV6 — Eval harness + deeper memory (D.2/D.3).** Scoring, the pipeline regression test, the
  memory-depth signal + `deepen_cohort`. *(medium)*

## 8. OPEN DESIGN DECISIONS (resolve before ESV4 — the driver)
ESV1–ESV3 are build-ready as specified. The following are genuine forks, not details; ESV4 (the
driver) and the critic loop depend on them. Each lists the fork + a recommended default.

**OD-1 — How does a DETERMINISTIC driver dispatch Claude subagents? → DECIDED: (b).** (2026-06-05, with
user.) The locked rule forbids in-process LLM authoring, so the driver cannot author or spawn; it must
*be executed by* a Claude Code host agent that does the spawns. Option (c) `claude -p` is **rejected**
(would burn API tokens). The driver is therefore a **pure-Python `RunLoop` engine + a thin host skill**:
- **Engine (pure, deterministic, unit-testable, NO LLM, NO spawning):**
  `run_step(run_id) -> {kind, spec|done, …}` (bundles `assess_project` + `next_action` + the journal +
  the finish/critic gate into one deterministic call that returns the next *dispatch spec* or `done`);
  `record_result(run_id, step_id, evidence_ids)` (checkpoint); `resume(run_id)` (replay the journal).
- **Host skill (the Claude Code agent you trigger today):** runs `loop: s=run_step; if s.done break;
  SPAWN ONE subagent(s.spec) via the Agent/Task tool; record_result(...)`. The **subagent spawn is the
  exact same Claude-Code primitive used today** — ESV changes *who decides the control flow* (the
  engine, deterministically), not *how an agent is triggered* (still the host via the Agent tool).
This is **the same trigger model as `autonomous-research-run` today** (agent loops next_action → spawn
subagent → persist); ESV only hardens the control flow (journal + resume + critic gate + finish gate)
into the engine so the agent can't drift or stop early. **Caveat:** ESV always needs a Claude Code
agent session present to perform the spawns (as today) — it is NOT a headless Python daemon; truly
unattended runs still mean a Claude Code session, never `claude -p`. This reshapes A.3 (the driver
pseudocode is the *host skill*; the loop primitives are engine calls).

**OD-2 — Concurrency safety of parallel act fan-out on the shared plan. → DECIDED: (a) serialize plan
mutations.** Fan out the *authoring* (councils/prototypes/sessions write to their own tables safely);
the driver applies `add_task`/`link_evidence` sequentially after the parallel authoring. Removes the
read-modify-write race on the plan document.

**OD-3 — Concepts must become FIRST-CLASS structured data. → DECIDED: a concept = a `note`** (kind
`concept`) whose `data` carries `{title, lens, artifact_kind, prototype_id|null}`. When a prototype is
built for a concept, set `prototype_id`. `brief_completeness_critic` computes `concepts_not_prototyped`
= concept-notes with `prototype_id is null`. Cheap, reuses the notes primitive, makes the gap
computable. (Affects B.2 frame computation + the ideate step contract.)

**OD-4 — Driver testability without an LLM. → DECIDED: a deterministic authoring stub.** The engine
exposes `record_result(run_id, step_id, evidence_ids)`; tests feed canned evidence per step (no Claude)
so the loop/resume/critic-gate are fully unit-testable. Ship the stub helper in `tests/`.

**OD-5 — Budget semantics + critic non-convergence. → DECIDED.** `budget` = **step count** (primary),
optional token ceiling. The driver stops dispatching past budget, then still runs the finish steps + a
honest "capped" note. Critic: **K=2** consecutive dry rounds to pass; hard cap **4** critic rounds, then
finish with remaining `missing` recorded as open questions. Numbers live in config/data, not code.

**OD-6 — Integration with the existing front door. → DECIDED: wrap.** The `RunLoop` engine becomes the
core; `autonomous-research-run` becomes the thin host skill over it (OD-1b); `compose-research-plan`
hands off unchanged. One loop, not two.

**Smaller spec tightenings (can be settled in-PR, not blocking):** evaluator boolean/comparison
precedence + short-circuit (C.4); the chart x-sweep must not clobber a real input of the same id;
`spa-journey`/`spa-model` should share one renderer JS (build-time include) rather than copy; exact
`derive_sections` label derivation from step names; `memory_depth` thresholds as data.

**Net:** ESV1 (auto-org), ESV2 (critic tools), ESV3 (resumable writes + run object) can start now as
specified. **OD-1..OD-5 should be decided before ESV4** (they reshape the driver + critic loop). OD-1
is the one to settle first.

## 7. Definition of done for the program
One HMW prompt → the `esv-run` driver produces, **resumably and without context exhaustion**, a project
that an **independent critic** certifies exhaustive (rubric all ≥ threshold, no `missing`), that is
**organized + concluded + handed-off** by construction, with **production-credible interactive
prototypes** (journeys/charts/verdicts) **grounded**-tested across segments — every time, with quality
**tracked** by the eval harness. That is "a finished, exhaustive, self-verified design-thinking
project", not "a good starting point".
