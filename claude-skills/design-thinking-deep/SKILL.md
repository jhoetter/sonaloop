---
name: design-thinking-deep
description: Run the FULL deep design-thinking process (double_diamond_deep) at depth — many personas, broad problem exploration, affinity clustering to key problems, a lo-fi→mid-fi prototype ladder with real Playwright tests, and a solution presentation. Drives breadth via PARALLEL subagent fan-out (never an in-process LLM). Use for "run a deep/full design thinking project", "do it in way more detail", "three diamonds".
---

# design-thinking-deep

The deep variant of `methodology-run`, on the `double_diamond_deep` **constellation** (three linked
diamonds). A methodology only SEEDS the **research PLAN** — the single engine: a DAG of tasks bucketed
**analyze / act / verify** (since HX3 there is one engine; the old constellation runtime was retired
— see `spec/hx3-engine-collapse.md`). The plan enforces the SHAPE + gates and is tag-agnostic;
**I (the host) and my subagents author every word** via MCP — **never call an LLM API for text**
(OpenAI = embeddings + images only). "At scale" = **parallel subagent fan-out**, not a server-side
loop. Specs: `spec/research-plan-engine.md` + `spec/methodology-constellations.md` +
`spec/deep-design-thinking-and-diamond.md`.

## Setup — a real cohort
Author **12–16 segmented personas** (record_persona; host-authored) spanning age × life-stage ×
attitude × channel × region + 2–3 provider-side roles. Then seed the plan:
```
start_project "<title>" "<HMW>" --methodology double_diamond_deep --persona … (all of them)
# seeds a `frame` analyze task per fan step + a gated `verify` task per decide step.
```

## The loop (`next_action`/`brief_next` drives it; one Synthesis per converge; six steps)
For each ready task, `next_action`; then by bucket:

**analyze (frame) — understand before concluding:**
- `frame__discover` / `frame__ideate` / `frame__refine`: read persona memory (their simulated days)
  + prior evidence, author the research questions/angles → `record_frame(questions, hypotheses,
  memory_refs)` (≥1 question + ≥1 memory ref). This opens the diamond.

**act — FAN OUT WIDE (this is the diamond; breadth = angles × persona diversity):**
- discover: spawn subagents (parallel batches) each loading its own `persona-context` and reacting
  (pain-discovery); assemble a FEW **real multi-persona councils** per angle → `add_task("act",
  "explore", "<angle>", consumes=[frame__discover])` + `link_evidence(kind="council")` +
  `complete_task`. (Several councils of many personas — NOT one council per persona.)
- ideate: **push for genuine innovation, not incremental tweaks.** Apply the creativity lenses in
  `next_action.act.ideation_lenses` (cross-domain analogy, make-the-invisible-EXPERIENCEABLE→an
  interactive `model`, provocation/reversal, extreme-user, mechanism-transfer, hybrid, subtract,
  honest anti-goal) — at least ONE concept must carry a mechanism you didn't expect at the start.
  One act task per solution angle; build **several lo-fi prototypes** DIVERSE IN KIND
  (`scaffold_artifact(..., type="model"|"prototype"|"comparison"|"flow"|…, tags=["lofi"])`, consuming
  `frame__ideate`) + `link_evidence(kind="artifact")`. Check `assess_project.novelty` — if it says
  "narrow", you're building forms; add an experienceable model + a dark-horse.
- refine: build **mid-fi** prototype(s) of the shortlist (`tags=["midfi"]`, consuming `frame__refine`).
- Stop fanning out by your own judgment (evidence-backed) — never a fixed count.

**verify — cluster / decide behind an evidence gate (one synthesis per waist):**
- `verify__define`: **affinity-cluster** the discover fan; author a synthesis payload whose `findings`
  carry `kind="cluster"` items (`{text=<label+insight>, refs to the clustered council statements}`) +
  `kind="key_problem"` items → `record_synthesis` + `link_evidence(kind="synthesis")` +
  `record_judgment("divergence_complete", …)` + `complete_task`.
- `verify__lofi_select`: personas **USE each lo-fi prototype** via Playwright (`run_prototype` →
  `brief_prototype_session` → `proto_open`/`proto_act` → `record_prototype_session`); then a synthesis
  whose `findings` carry `kind="ranking"` items (one per prototype, score_rationale in `text`) +
  `kind="shortlist"` items; judge + complete. (Its
  `requires.session_of_tags:["lofi"]` is matched by tag-equality to the lo-fi prototypes' sessions.)
- `verify__deliver`: personas **USE the mid-fi** prototype (`session_of_tags:["midfi"]`); synthesize
  the **solution presentation** (winning concept, who-wins + non-targets, validated pain-solvers,
  evidence trail, open risks, spec); `assess_progress(delta="beantwortet")` + `complete_task`.

A verify task is **gated**: it cannot complete until its act fan has ≥`min_inputs` distinct act
tasks with evidence, a decided `gate_tag` judgment exists, and any required artifacts/sessions exist.
So you cannot skip the work or conclude early.

## Parallelism & cost (host judgment)
- Fan out subagents in **parallel batches** (e.g. 4–6 at a time). Each subagent does its OWN
  `persona-context` load + reaction; you assemble the multi-persona councils + act tasks.
- Breadth target: discover ≈ a few real councils across the segments; ideate ≈ 4–8 ideas; lo-fi ≈
  3–5 prototypes; mid-fi ≈ 1–2. Adjust to the problem; `log`/note when you cap.

## Real prototypes (lo-fi → mid-fi)
- DIVERSE IN KIND — read `next_action.act.artifact_palette` and pick varied archetypes, NOT N forms:
  a guided `flow`, a `comparison`, a `dashboard`, a `cards` interface, or an interactive **`model`**
  (`type="model"`: `range`/`number` inputs feeding `computed`/`bar` elements whose `formula` evaluates
  live — e.g. a steerable pension-gap / compounding model a persona actually drives). Include ≥1
  deliberately extreme **dark-horse** concept; an honest "this is not for you" verdict is legitimate.
- Lo-fi: `scaffold_artifact(slug, name, concept, type="prototype"|"model"|…, tags=["lofi"])` — several.
- Mid-fi: `scaffold_artifact(... tags=["midfi"])` of the shortlisted concept.
- Tested for REAL via Playwright — and groundedness is enforced: `proto_open` → `proto_act`/`proto_read`
  (cite states you actually saw) → `record_prototype_session`. The session log is retained past
  `proto_close`, so record AFTER driving; an UNVERIFIED session does not satisfy a `session_of_tags`
  gate. Every nav target must resolve to a screen (scaffold rejects dead interactions).

## Output
Three real diamonds in the project graph (wide discover fan → key problems → wide ideate fan →
shortlist → refine → solution presentation), real lo-fi + mid-fi prototypes, `export_plan_md` as the
analyze/act/verify log, and a Meta-Report = the **solution presentation**. See it in the web
inspector's methodology strip + diamond view.

## Hard rule
No LLM text-generation, ever. Host/subagents author all text via MCP. OpenAI key = embeddings +
images only. (See the project memory + `spec/deep-design-thinking-and-diamond.md` §2.)

## Authoring style (Markdown, not ALL-CAPS)

Write analysis/summary prose as **Markdown**: `**bold**`/`_italic_` for emphasis, `-`/`1.` lists,
`>` quotes, blank lines between paragraphs. **Never** use ALL-CAPS for emphasis or write a literal
section header inside the text (e.g. `SUMMARY:`, `VOTES:`, `WHAT THIS COUNCIL FOUND`) — the UI renders
the headers/labels. Applies to `exec_summary`, `summary`, `gesamtbild`, recommendations, meta sections,
notes, etc. A persona/proband statement `text` stays in that persona’s natural voice (it is a quote).

## Unified primitives (the ONLY shape)

Author content as the shared primitives (spec/unified-artifact-schema.md) — these are the only inputs
the code accepts (compatibility `turns`/`votes`/`voices`/`key_problems`/`clusters`/`ranking`/`shortlist`/… were removed):

- **`record_council(..., statements=[…], votes=None, proposal="", questions=[…], findings=[…])`** —
  `statements`: one per persona utterance `{persona_id, text (Markdown), stance:{value -2..2, label},
  about:{kind:"prompt", id:"q0"|"proposal"}, refs}`. A discover council carries `questions` + statements
  with `about.id="q0"/"q1"…`; an evaluation council carries a `proposal` + stances; a decision council
  adds `votes` for the tally.
- **`record_synthesis(..., payload={gesamtbild, positionierung, arc_narrative, references, citations,
  status, findings:[…], statements:[…], prompts:[…]})`** — all analysis lives in `findings`
  `{text, kind: key_problem|pain_solver|open_question|recommendation|cluster|segment|ranking|shortlist|summary,
  score:{effort,value}, refs}`. A synthesis **cross-references, never copies**: it re-interprets council
  statements via finding `refs {kind:"council", id, anchor:"<statement-id>", role:"derived_from"}` — it
  does not re-host voices.
- A concept/idea is just a **note** (`create_note`; `kind` normalizes to `note`) — set
  `data.prototype_id` once it's built; there is no separate concept entity.

One positivity scale only (oppose −2 … support +2) for every stance/vote/sentiment.
