---
name: autonomous-research-run
description: The lean autonomous EXECUTION loop over the research-PLAN engine — 10s of iterations of councils, prototypes, exploration, synthesis and solution-spaces to a well-organized, documented result. Lean context per step via next_action + assess_project; one subagent authors each step; sections + a run-journal keep it self-organizing. Normally reached automatically from compose-research-plan (the front door for a bare HMW). Use directly to RESUME or CONTINUE an existing project's run.
---

# autonomous-research-run

You are the LEAN ORCHESTRATOR of a long run. The locked rule holds: **no in-process LLM** — YOU and
your SUBAGENTS author every word via MCP; the engine enforces structure + gates. The whole point of
this skill is to run **many iterations without bloating your context**: each iteration is one
`next_action` → one subagent authors+persists the step → you receive a *tiny* result (ids + 1 line).
You almost never read a full council/synthesis yourself — you steer from `assess_project`,
`coverage`, and `sections`. Specs: `spec/harness-evaluation-and-autonomy.md`,
`spec/research-plan-engine.md`, `spec/sections-and-composable-graph.md`.

## Setup (once)
1. **Cohort**: ensure richly-segmented personas exist with simulated memory (use `simulate-cohort`
   if not). Reuse an existing cohort when present.
2. **Project**: `start_project "<title>" "<HMW>" --methodology <key> --persona …` (double_diamond /
   double_diamond_deep / d.school / lean_jtbd, or freeform). The plan seeds analyze/act/verify.
3. **Run object**: `run = start_run(project_id, budget=<steps>, operation_id=<stable create key>)`; reuse
   that key if the initial response is ambiguous. Resume an interrupted run with
   `start_run(project_id, run_id=run.run_id)` — it replays the journal, no lost work.

## The lean loop — YOU ARE THE THIN HOST OVER THE DETERMINISTIC ENGINE (ESV)
The engine (`run_step`) decides the control flow; you only execute its dispatches by spawning ONE
subagent each (the same Agent-tool trigger as always) and recording the result. This is what stops a
run ending at "a good starting point": the engine does the deterministic finish work (sections + the
meta-report outline + critic-gap injection) itself, and only the independent **critic** — not your
own judgment — ends the run.
```
run = start_run(project_id, budget=50, operation_id=<stable run-create key>)
while True:
    s = run_step(run.run_id)                 # the brain: assess + next_action + finish + critic gate
    if s.kind == "done": break               # status: finished | capped | stopped — the run is over
    if s.kind == "critic":
        spawn ONE INDEPENDENT critic subagent on s.brief → it authors the verdict, calls
        record_completeness_critic(project_id, verdict, run_id, operation_id=dispatch.operation_id),
        then record_critic_round(run_id, critic_report_id=returned.id, key=dispatch.key)
        continue                             # the engine injects each `missing` gap as real work next loop
    # else s.kind ∈ {analyze, act, verify}: author ONE step (below), grounded in s.next_action, keyed by s.key
    spawn ONE subagent to author s → it persists via MCP and returns ONLY ids + 1 line
    checkpoint_step(run.run_id, {task_id: s.step_id, bucket: s.kind, key: s.key, evidence: [...], summary: "…"})
# you never read the authored text; the DB + plan.md + sections + the meta-report hold it
```
Authoring per dispatch (always a SUBAGENT, grounded in `s.next_action`):
- **analyze (frame)** → subagent reads cited persona memory + prior syntheses (from `n.grounding`),
  authors research questions, calls `record_frame`. Returns the frame id.
- **act** → execute the already-dispatched Act task and pass its `dispatch_token` to the matching
  recorder; do **not** add a duplicate task when the methodology supplied a `work_item` (Reaction
  Test already supplies both Council angles). Only when a verify dispatch explicitly reports an
  incomplete, unseeded fan should the host add a new angle task. Run a REAL multi-persona council
  (`n.act.suggested_participants` — segment-diverse, NOT keyword) or `scaffold_artifact` + a grounded
  Playwright session. Breadth = angles × persona diversity, **never one council per persona**.
  **Council shape (Q1/Q2):** councils are PRIMITIVES-ONLY — `record_council(project_id, prompt,
  persona_ids, statements=[…], votes=…, proposal=…, questions=…, findings=…)` (no `turns` param).
  Each statement is `{persona_id, text, stance:{value -2..2}, about:{kind:'prompt', id}, refs}` — the
  honest answer/utterance, its position on the one −2..2 scale, what prompt it responds to, and its
  grounding. EARLY discovery is OPEN USER RESEARCH — pass `questions=[…]` (conversational: "Welche
  Versicherungen hast du? Wie sparst du gerade?"), statements are honest ANSWERS, NO proposal/votes
  (you are LISTENING; hypotheses are an OUTPUT of Define, never the input). Use a `proposal` only to
  react to a concept/prototype (evaluation), and `votes` only for an explicit decision (rare). State
  motions as questions, not hypotheses, until you have understood.
- **verify** → subagent consolidates the fan (`n.verify.fan_evidence`) into a synthesis
  (`record_synthesis` — councils OPTIONAL/decoupled; for affinity, synthesize over notes/other
  syntheses with `council_ids=[]`), records the gate judgment, `assess_progress`, `complete_task`.
  **The synthesis IS the answer artifact — author it RICH** (primitives-only payload): fill
  `gesamtbild` (the answer), `positionierung` (the POV), and a set of `findings` —
  `{text, kind:'key_problem'|'recommendation'|'open_question'|'cluster'|…, score, refs}` — that carry
  the analysis. Don't re-host voices: cross-reference the council statements that ground each finding
  via a finding `ref` `{kind:'council', id:<council_id>, anchor:<statement part id>, role:'derived_from'}`.
  Optional `statements` carry any synthesis-level voices. Notes are observation ATOMS, never a
  substitute for the synthesis. `assess_project` flags a thin/empty synthesis as a gap — fix it
  before moving on. (Council votes use the −2..2 stance scale so the UI tallies render.)

## Stay organized & documented (every few iterations — HX5)
- **Sections**: maintain methodology-independent groupings as the run grows — `create_section` /
  `set_section_members` for emerging themes ("Initial user research", "Trust & honest non-option",
  "Solution space"); the methodology PHASES render as derived sections automatically. This is the
  primary "well-organized" surface.
- **Affinity**: capture sharp observations as `create_note` nodes, then `set_section_members` to
  **promote a cluster** into a named theme section (the KJ-method move) — and synthesize the cluster
  council-free.
- **Run journal**: append a one-line `create_note` per milestone ("iter 12: develop diamond gated;
  winner = honest check") and keep them in a "Run-Journal" section. This is durable external memory
  so YOU stay lean.

## Stop criteria (HX7 — don't run forever, don't stop arbitrarily, don't stop EARLY)
**"Gates passed" ≠ "finished".** A run is DONE only when `assess_project.finish.finished` is true —
i.e. the project is ORGANIZED (sections), CONCLUDED (a substantial terminal solution-presentation
synthesis), and HANDED-OFF (a meta-report). `recommendation == "finish"` means the plan's gates are
met but the project is still a *starting point*; keep going (organize + conclude + meta-report) — do
NOT report done. Only then converge/stop when ANY: `recommendation == "complete"`; `saturation.hint ==
"converging"` AND open_questions empty; K consecutive councils add no new theme; or the iteration
budget is hit (then still finish: organize + Deliver synthesis + meta-report + roadmap, honestly noting
what was capped). Also heed `assess_project.novelty` — if the solution space is "narrow", push for a
bolder, more experienceable concept before converging.

## Output
`export_plan_md` (the analyze→act→verify log) + the section overlays (themes + phases) + the Deliver
synthesis + a roadmap + (optionally) a meta-report. The graph reads as a well-organized, multi-diamond
project; `export_section`/`export_synthesis` hand any part to a downstream agent.

## Context hygiene (the discipline that makes 50+ iterations possible)
- One `next_action` and one `assess_project` read per iteration — nothing else in your context.
- Subagents author + persist + return ids only; their context is discarded.
- Re-ground via `assess_project` / `coverage` / `list_sections`, never by re-reading evidence.
- Persist ALL state in the project (plan, sections, notes) — keep no scratch state in your head.

## Hard rules
No in-process LLM authoring (host/subagents only). No one-council-per-persona. Understand before
concluding (never skip the frame). Honest uncertainty raises an open question, not fake progress.
Gates are not skippable — they are the quality floor.
