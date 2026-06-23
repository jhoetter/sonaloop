# Unified artifact schema — one set of primitives across all artifacts

Status: **Phase 0-2 implemented + Phase 3 backfill done** (2026-06-06). Author: design analysis triggered by "we have too many data concepts
that are the same thing modeled differently."

## 1. The problem (root cause of the rendering inconsistency)

Storage is **JSON documents** (one per record in SQLite; each model `to_dict()`s to JSON). Today every
artifact invents its *own* JSON shape for what is, conceptually, the **same handful of things**. The UI
inconsistencies we keep fixing (literal `**`, three different "voice" layouts, contradictory grounded
badges) are downstream symptoms — the real duplication is in the **data model**.

### The same concept, modeled four different ways

**(a) "A persona said something, with a stance, grounded in evidence"** — the single most duplicated idea:

| where | shape (today) |
|---|---|
| `CouncilSession.turns[]` | `{persona_id, content, stance, question_index, memory_refs, input, questions_or_pushback}` |
| `Synthesis.voices[]` | `{persona_id, persona_name, segment, sentiment, relevance, key_argument, shift, evidence[]}` |
| `PrototypeSession.reaction{}` | `{persona, verdict, focus, liked[], friction[], observed_state_refs[], …}` (9+ ad-hoc shapes) |

All three are **one thing**: a persona uttered text, with a positivity/stance, about some target, grounded
in some references. The field names and extras differ; the core does not. Three schemas → three renderers
(`_answer_html`, the voices panel, `_session_card`) → three looks.

**(b) "How positive is this"** — three vocabularies: `votes` (SUPPORT/MAYBE/ABSTAIN/OPPOSE) · `turn.stance`
(free string) · `voice.sentiment` (positiv/bedingt/skeptisch/neutral). Each needs its own color/label map.

**(c) "A list of authored analysis items"** — at least seven near-identical lists on `Synthesis` alone:
`key_problems[]`, `pain_solvers[]`, `offene_fragen[]`, `shortlist[]` (all `list[str]`),
`handlungsempfehlungen[]` (`[{text, aufwand, nutzen}]`), `clusters[]` (`[{label, insight, members}]`),
`segmente[]` (`[{segment, why, stance}]`). Every one is *a list of {markdown text, optional score,
optional grounding}* — rendered by a different helper (`.psolve` raw, `_rec_row_n`, `_segrow`, …).

**(d) "The thing being asked / investigated"** — `council.prompt`, `council.questions[]`,
`council.proposal`, `synthesis.start_input`, `synthesis.goal`, `synthesis.next_council_question`,
`session.reaction.focus`. All a **prompt**.

**(e) "What this is grounded in"** — `turn.memory_refs[]`, `voice.evidence[]`, `synthesis.citations[]`,
`session.observed_state_refs[]`, and inline `[C#]` markers. All a **reference**.

## 2. The five primitives

Define a small, closed set of JSON primitives. Every artifact is **composed of these** — it never invents
a parallel shape. (camelCase or snake_case — match the existing snake_case.)

### `Ref` — a grounding pointer
```json
{ "kind": "memory|council|synthesis|prototype_state|persona|external",
  "id": "council_…",            // when it points at a record
  "text": "…",                  // when it's a free observed-state string
  "quote": "…" }                // optional supporting quote
```
Replaces: `memory_refs`, `evidence`, `citations`, `observed_state_refs`, inline `[C#]`.

### `Stance` — one ordered positivity scale
```json
{ "value": -2, "label": "oppose" }   // -2 oppose · -1 skeptical · 0 neutral · +1 conditional · +2 support
```
One scale; the UI derives color + label from data (no per-vocabulary maps). Votes/stance/sentiment all
become a `Stance`. A council "vote" is just a `Stance` with a stricter authoring rule.

Validation invariants: the stored `value` is ALWAYS on-scale and the stored `label` ALWAYS its
canonical term — free labels (incl. the EN/DE display labels) are alias-resolved via
`stance_scale.json`; on label/value disagreement the explicit on-scale `value` wins, while an
OFF-scale value defers to a resolvable label (else clamps to the nearest endpoint). Whatever loses is
never dropped silently: it survives as `label_raw` / `value_raw` (bare unknown tokens additionally
fall back to value 0).

### `Statement` — a persona's utterance (the big unifier)
```json
{ "persona_id": "persona_…",
  "text": "…markdown…",
  "stance": { "value": 1, "label": "conditional" },   // optional
  "about": { "kind": "prompt", "id": "q0" },           // what it responds to (a Prompt/proposal/prototype) — optional
  "refs": [ {Ref}, … ],                                 // grounding
  "relevance": "strong|partial|…",                      // optional
  "shift": { "from": "skeptical", "to": "support", "trigger": "…" },  // optional (synthesis)
  "meta": { "input": "…", "pushback": ["…"] } }         // artifact-specific extras live HERE, namespaced
```
Replaces council `turns`, synthesis `voices`, prototype `reaction`. **The schema is identical everywhere;
only the GROUPING differs** (by question, by persona, flat) — and grouping is a render-time choice driven
by `about`, not a different schema. One renderer: `render_statement()` → the `.turn` card we already unified.

### `Prompt` — the thing posed
```json
{ "text": "…markdown…", "kind": "question|proposal|goal|focus|hypothesis", "id": "q0" }
```
Replaces council prompt/questions/proposal, synthesis start_input/goal/next_council_question, session focus.

### `Finding` — an authored analysis item
```json
{ "text": "…markdown…",
  "kind": "summary|key_problem|pain_solver|open_question|recommendation|cluster|segment|risk",
  "score": { "effort": 2, "value": 5 },   // optional; or a single number / ranking
  "refs": [ {Ref}, … ],                    // optional grounding
  "meta": { "members": ["…"], "stance": {Stance} } }  // kind-specific extras, namespaced
```
Replaces key_problems / pain_solvers / offene_fragen / shortlist / handlungsempfehlungen / clusters /
segmente. One renderer: `render_finding()` (text via `_prose`, optional score chip, refs as chips).

## 3. Artifacts become compositions

```
Council   = { prompts:   [Prompt],         // the question(s) / proposal
              participants: [persona_id],
              statements:[Statement],      // every turn/voice (grouped at render by .about)
              findings:  [Finding],        // exec_summary + summary as kind:"summary", etc.
              mode }                        // still DERIVED (presence of proposal/votes/questions)

Synthesis = { prompts:   [Prompt],         // start_input / goal
              statements:[Statement],      // the voices
              findings:  [Finding],        // gesamtbild + key_problems + recommendations + open_questions…
              sources:   [Ref] }           // council_ids → refs

Session   = { persona_id, prototype_id,
              statements:[Statement] }     // the reaction, grounded in prototype_state refs
```

Same three render functions (`render_prompt`, `render_statement`, `render_finding`) drive **every** artifact
page. Consistency stops being a CSS chase and becomes structural: there is only one way to draw each thing.

## 4. JSON, yes — and how to evolve it safely

Records already serialize to JSON, so this is a **shape** change, not a storage-engine change. Roll out in
three non-breaking phases so we never do a risky big-bang migration:

1. **View/adapter layer first (no data migration).** Add pure read adapters
   `as_statements(record)`, `as_findings(record)`, `as_prompts(record)`, `as_refs(field)` that map the
   *current* fields onto the primitives. Point the web renderers (`_session_card`, the voices panel, the
   council turns, the synthesis lists) at these adapters + the three primitive renderers. → immediate,
   total UI consistency with **zero** data change or risk. (This is the natural completion of the
   `_prose` / `.turn`-card unification already shipped — it pushes the unification down to the data view.)
2. **Author the primitives natively.** Update the `brief_*` instructions + `record_*` schemas
   (spec/markdown-authoring-harness.md is the precedent) so new councils/syntheses/sessions write
   `statements`/`findings`/`prompts`/`refs` directly. Keep the adapters reading compatibility records.
3. **Optional backfill.** A one-off migration rewrites old records into the primitive shape; then the
   compatibility fields + adapters can be retired. Never required for correctness — the adapters cover old data
   forever.

A `stance_scale.json` (like `section_kinds.json`) holds the one stance vocabulary → label/color, keeping
the zero-hardcoded-values gate satisfied.

## 5. Why this is the right root fix

- **One mental model.** "A persona statement", "a finding", "a prompt", "a ref", "a stance" — five nouns
  describe the entire corpus. New artifact types compose them instead of inventing shapes.
- **One renderer per noun** → consistency by construction (the user's ask), not by repeated CSS patches.
- **Cheaper everything**: search, export, the meta-report, embeddings, and the project graph all read a
  uniform shape instead of special-casing each artifact.
- **Non-breaking path**: the adapter layer delivers the visible win immediately; native authoring and
  backfill follow at leisure.

## 5b. Completeness — the five are one of three layers

Audited against the *whole* model set, the five primitives are **complete for artifact CONTENT**, and sit
in a three-layer model:

- **Layer 1 — content (the five):** Statement · Finding · Prompt · Ref · Stance. Cover every field inside
  council / synthesis / prototype-session / note / meta-report. Nothing content-level is left over.
- **Layer 2 — graph structure:**
  - **Node** — the entity wrapper (id, kind, title, project_id, created_at, presentation). Persona,
    Council, Synthesis, Prototype, Note, Section, MetaReport, OpenQuestion are all Nodes. *Already*
    unified via `present(kind)`.
  - **Edge** — a typed directed relation between nodes (`StudyEdge`: from/to/type/rationale —
    based_on/feeds_into/refines/answers). NOT a Ref: a Ref grounds *content* in a source; an Edge wires
    *nodes*. First-class graph structure.
  - **Section** — a labeled set of node ids (a grouping overlay; a node-of-nodes).
  - (`OpenQuestion` demonstrates the layering: a **Prompt** promoted to a **Node** with an `answers` Edge.)
- **Layer 3 — persona memory / simulation (separate subsystem):**
  - **Event** — a time-stamped life event (`ExperienceEvent`, `CalendarEvent`, `DailySummary`,
    `Reflection`): actor + time + body + refs. This subsystem has the SAME duplication disease — e.g.
    `pain_points` is modeled FIVE ways (ExperienceEvent, DailySummary, Reflection, PainPointObservation,
    Persona). A `PainPoint` is a persona-scoped **Finding**. Out of scope for the artifact unification, but
    the same treatment applies.

**Deliberately not reduced:** **Persona** is the *Actor* Node with a rich attribute schema (its lists are
Findings; its structured blocks define the entity). **Score/Metric** folds into `Finding.score` +
`Stance` for now (name it later only if scores proliferate).

So the full map: **5 content + 3 structural (Node/Edge/Section) + 1 temporal (Event)** — but Layer 1 is the
only one with real, fixable duplication in the artifacts; Layer 2 is mostly unified already; Layer 3 is a
separate cleanup with the same pattern.

## 6. Next step (not yet done)
Implement Phase 1: `sonaloop/web/_adapt.py` (the read adapters) + `render_statement/finding/prompt`
in `_components`, and route the council/synthesis/session renderers through them. Then the four "looks
different" surfaces collapse to one code path. Estimated: contained, behind the existing golden-diff
harness.
