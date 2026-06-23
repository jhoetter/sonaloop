# Research-Plan Engine — Implementation Spec & Tracker

> **Status:** SPEC (build-ready) — no code yet. Implements the direction in
> `spec/planning-and-evidence-architecture.md`. **Locked decisions:** (1) **Go full** — the plan is
> the unified source of truth; the methodology emits a plan; freeform + methodology research
> converge on one model. (2) The **analyze/`frame` step is default-but-discharge­able** — every plan
> opens with a frame task the orchestrator must address but may discharge quickly; never silently
> skipped. (3) **Plan lives in the DB (source of truth) + a rendered `plan.md` export** (bim-agent
> json→md style).
> **Preserved principles:** host/subagents author ALL text (no in-process LLM text-gen; OpenAI =
> embeddings + images only); **zero hardcoded vocabulary** (buckets/capabilities/kinds are tags with
> data-driven presentation, per `methodology-presentation-from-data.md`); structure enforced by the
> engine, dynamics LLM-judged with evidence; read-only web UI.
> **Builds on:** `methodology-constellations.md` (the step DAG → the plan backbone),
> `methodology-presentation-from-data.md` (rendering the new node/evidence kinds).

---

## 1. Concepts

### 1.1 Evidence (the atomic work products)
An **evidence item** is anything produced while working a plan. Kinds are **open tags**:
`frame` · `council` · `synthesis` · `artifact` · `session` (+ any future tag). Evidence already
lives in dedicated tables (councils, syntheses, prototypes, prototype_sessions); `frame` is new.
The plan references evidence by a uniform **EvidenceRef `{kind, id}`** — no table merge required.

### 1.2 Plan (the orchestrator's source of truth)
One **Plan per ResearchProject**: an editable DAG of **tasks**. The plan is authored + updated by
the orchestrator (host) via MCP, and rendered to a human `plan.md` on demand.
```
Plan { project_id, goal(HMW), methodology?, tasks: Task[], created_at, updated_at }
Task {
  id, title, intent, plan_note,                 # plan_note = the orchestrator's rationale (the prose)
  bucket:     "analyze" | "act" | "verify",      # an OPEN tag (the analyze/act/verify decomposition)
  capability: string,                            # frame | explore | cluster | decide | build | test | synthesize | …
  step?:      string,                            # optional grouping under a constellation step (for layout)
  consumes:   task_id[],                          # DAG edges (a task is ready when these are done)
  status:     "todo" | "active" | "done" | "blocked",
  produces:   EvidenceRef[],                      # evidence this task created
  requires?:  { min_inputs?, gate_tag?, artifact_tags?[], session_of_tags?[] },   # gates (constellation grammar)
  loop_back?: task_id,
  presentation?: {}                               # optional data hint (label/color/glyph)
}
```
`bucket` is the analyze/act/verify decomposition; `capability` is the concrete MCP action. Both are
**tags** validated by reference, never code enums (suggestions seed common ones + presentation).

### 1.3 The methodology is a plan TEMPLATE
A constellation (double_diamond_deep, …) **expands into a seed plan**. The DAG of steps becomes the
backbone; per step the seed contains the *scaffolding* tasks, and the orchestrator fills in the
breadth at runtime:
- a **fan/explore step** → a seed **`analyze`/frame** task + a placeholder **`act`** lane (the
  orchestrator adds N council/build act-tasks) → its downstream **`verify`** task gates the fan.
- a **decide step** → a seed **`verify`** task (synthesize + judge) consuming the fan's act evidence.
A **freeform project** = a plan with no template: just a root `frame` task; the orchestrator appends
`act` councils and drops `verify` syntheses when useful. **One model subsumes both flows.**

---

## 2. The analyze / act / verify loop (capabilities → MCP)
- **ANALYZE** — *understand before concluding.* `record_frame`: read persona **memory** (the lived
  simulated days), prior syntheses, world context, open questions; author research questions +
  hypotheses + cited memory refs. Anti-steering strongest. **Default-but-dischargeable:** every plan
  opens with a `frame` task; `act` tasks `consumes` it, so it can't be silently skipped — but a
  quick frame discharges it.
- **ACT** — *do the work.* `run-council` (a real multi-persona council on a framed question),
  `scaffold_artifact` (build), `record_artifact_session` (a proband drives it). Each links its
  evidence to its act-task. Breadth = angles × persona diversity, **not one-council-per-persona**.
- **VERIFY** — *consolidate + measure.* `record_synthesis` (OPTIONAL consolidation over a *chosen*
  subset of councils), `record_judgment` (the gate), and `assess_progress` (LLM-judged progress
  toward the HMW with evidence — the design analogue of bim-agent's score, never a hardcoded metric).

---

## 3. Router, lifecycle, gates
- **`brief_next(project_id)`** = the plan's next-action router: returns the ready task frontier (all
  tasks whose `consumes` are done), each with `bucket`, `capability`, `intent`, unmet evidence/gates,
  and the fitting MCP tools. Mirrors bim-agent's `get_..._next_action` (one clear action, or several
  when branches are ready).
- **Lifecycle:** `todo → active` (work starts) `→ done` (evidence + gate satisfied) via
  `complete_task`. `blocked` when an open question must be answered first.
- **Gates** = the existing evidence-backed `record_judgment` + structural invariants
  (`min_inputs`/`gate_tag`/artifact-by-tag), now attached to **verify tasks**: a decide/verify can't
  close until breadth + a decided gate judgment + required artifacts/sessions exist. No regression
  vs. the constellation engine — same grammar, reused.
- **Defects = open questions:** any task may raise `research_open_questions`; a later task `answers`
  them; unanswered blockers keep the plan non-terminal (bim-agent defect-terminality).
- **Honesty:** "we don't know yet" is a first-class verify outcome that raises an open question
  instead of fabricating progress; the prototype-session groundedness gate generalizes to evidence.

---

## 4. The decoupled, heterogeneous evidence graph
- Graph **nodes become heterogeneous**: `kind ∈ {council, synthesis, artifact, frame}` (open tag),
  each rendered **from data** (presentation-from-data: label/color/glyph per kind in suggestions).
  Councils are first-class nodes now — visible, sequential — not buried inside a synthesis.
- **Edges:** `council —consolidated_by→ synthesis`, `synthesis —spawned→ council`, plus existing
  `refines`/`answers`/`spawned_from`.
- **Diamonds re-derive cleanly:** a step's **act councils = the fan**, its **verify synthesis = the
  waist**. The convex-hull silhouette now groups act-evidence converging to a verify node — still
  purely structural, no diamond assumption.
- `add_study_to_project` generalizes to `add_evidence_to_project(ref)`.

---

## 5. Plan surface
- **DB source of truth:** a `plan` row per project (`tasks[]` JSON), reusing the `plans`-table
  pattern. Accessors `get_plan` / `upsert_plan`.
- **Rendered `plan.md` export:** `export_plan_md(project_id)` renders tasks bucketed analyze/act/
  verify with status, gates, evidence refs, and plan_notes (bim-agent json→md). Surfaced read-only
  in the web inspector; exportable.

---

## 6. Tool surface (MCP/CLI)
New / changed (old names kept as aliases where sensible):
- `start_project(title, goal, methodology?=, persona_ids)` → project + seeded plan. *(extends
  `start_methodology_project`; methodology optional → freeform.)*
- `brief_next(project_id)` → plan frontier (bucket/capability/unmet/instructions). *(reframed.)*
- `add_task(project_id, bucket, capability, title, intent, consumes?, requires?, step?)` → orchestrator
  inserts a task (e.g., another act council, an extra analyze, a mid-stream synthesis).
- `record_frame(project_id, task_id, questions[], hypotheses[], memory_refs[])` → analyze output.
- `link_evidence(project_id, task_id, ref)` → attach a council/artifact/session to its act-task
  (run-council/scaffold/record_session already create the evidence; this links + surfaces it).
- `record_synthesis(...)` → verify consolidation over chosen councils (existing; now optional + task-linked).
- `record_judgment(project_id, task_id, gate_tag, decided, rationale, evidence_refs)` → gate (existing).
- `assess_progress(project_id, task_id, rationale, evidence_refs, delta)` → HMW-progress verify.
- `complete_task(project_id, task_id)` → mark done; recompute frontier (never loops on its own).
- `iterate_task(project_id, task_id, note?)` → HOST-judged `loop_back` round: clone the loop
  subgraph as fresh `__r<n>` tasks (todo, no carried evidence/frames, gates preserved), the new
  entry consuming the looping task.
- `get_plan(project_id)` / `export_plan_md(project_id)` → DB plan + rendered md.
- `suggest_*` extended with bucket/kind presentation. Compatibility `record_node`/`record_decision`/
  `advance` map onto act/verify task ops for back-compat.

---

## 7. Migration & back-compat
- The constellation engine stays; `start_methodology_project` now **also seeds a plan**.
- Old syntheses/projects render unchanged (a project with no plan falls back to the current graph).
- `analyze/act/verify` + evidence kinds are **tags** → consistent with presentation-from-data; the
  grep-gate test extends to the new kinds.
- Skills updated: `methodology-run`/`design-thinking-deep` drive the plan loop (frame → councils →
  synthesize/judge), not one-council-per-persona.

---

## 8. Non-goals / preserved
No in-process LLM text-gen; the orchestrator authors the plan + all text. No hardcoded buckets/
capabilities/kinds/colors. Web UI stays read-only. The constellation shape + invariants are reused,
not replaced.

---

## 9. Milestone tracker
Each milestone is independently shippable with a failure-proof acceptance test.

- **R1 — Plan model + storage + render.** Plan/Task schema; `plans`-table-style storage; `get_plan`/
  `upsert_plan`; `export_plan_md`. **Accept:** a hand-authored plan persists, round-trips, and
  renders a bucketed `plan.md`; buckets/capabilities validated by reference (no enum) — grep clean.
- **R2 — Methodology → plan seeding + freeform.** `start_project` seeds a plan from a constellation
  (analyze/act/verify scaffolding per step) and, with no methodology, seeds a single root `frame`
  task. **Accept:** double_diamond_deep seeds a plan whose verify tasks carry the right gates; a
  freeform project seeds exactly one dischargeable frame task.
- **R3 — Frame capability (analyze, default-but-dischargeable).** `record_frame` (questions +
  hypotheses + cited persona-memory refs); act tasks `consumes` the frame. **Accept:** an act council
  cannot start before the frame task is addressed; a minimal frame discharges it; the frame cites ≥1
  memory ref.
- **R4 — Plan router + task lifecycle + gates.** `brief_next` over the task frontier; `add_task`;
  `complete_task`; gates (judgment + invariants) on verify tasks; open-question blockers. **Accept:**
  a verify/decide task is rejected until breadth + gate judgment exist; `brief_next` returns the
  correct ready set across a branch.
- **R5 — Evidence decoupling + heterogeneous graph.** Councils/artifacts/syntheses/frames as
  first-class nodes; `link_evidence`; `add_evidence_to_project`; data-driven kind presentation;
  diamonds over act→verify. **Accept:** a project with 3 councils + 1 optional synthesis renders 3
  council nodes + 1 synthesis node (not 3 wrapper syntheses); no hardcoded kind literal in web.py.
- **R6 — Progress-to-goal verify.** `assess_progress` (LLM-judged, evidence-cited, non-binding
  structural coverage hint). **Accept:** a deliver/verify task records an HMW-progress assessment
  citing evidence; no hardcoded numeric metric in code.
- **R7 — Skills + a real Pfefferminzia re-run.** Update `methodology-run`/`design-thinking-deep` to
  the plan loop; re-run Pfefferminzia. **Accept:** discover = 1 frame + a *few* real multi-persona
  councils + 1 synthesis (NOT 14 micro-councils); the plan.md reads as a coherent analyze/act/verify
  log; three diamonds still emerge over act→verify.
- **R8 — Migration + grep gate + full suite.** Back-compat (old projects render); extend the
  no-hardcoded-vocabulary gate to buckets/kinds; full test suite green. **Accept:** compatibility
  methodology projects still render; grep gate passes; `pytest` green.
