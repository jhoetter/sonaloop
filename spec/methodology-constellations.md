# Methodology Constellations — Specification

> **HX3 update (2026-06-05):** the constellation is now a **plan SEED**, not a runtime. The single
> runtime engine is the research plan (`plan.py`, analyze→act→verify); the old constellation runtime
> (`record_node`/`record_decision`/`advance`/`get_methodology_state` + `runtime.py`) was retired. The
> step model, tag-agnostic invariants and DAG/diamond derivation below still hold — realized through
> `seed_plan_from_methodology` + the plan engine. See `spec/hx3-engine-collapse.md` and
> `spec/research-plan-engine.md`. Tool names in this doc describe the historical engine.
>
> **Status:** IMPLEMENTED (rev.2) — milestones C1–C5 landed; full suite green. Supersedes the phase-grammar of
> `spec/methodology-engine-and-prototyping.md` §3–§4 and `deep-design-thinking-and-diamond.md` §4,
> and **rev.1's "capability catalog in code"** (now a *suggestion*, see §2.3).
> **Goal:** methodologies are **fully declarative and tag-driven — zero hardcoded vocabularies**.
> A methodology is a **constellation: a DAG of steps carrying open tags**. The MCP *suggests*
> building blocks (capabilities, roles, artifact-types, whole methodologies) as **data**, never as
> enforced code enums. The engine is **tag-agnostic**: it enforces only graph mechanics, references,
> and evidence — never tag membership. **Locked with the user:** capability-DAG model; **even
> `explore`/`cluster`/… are generic tags suggested by the MCP, not enums**; spec-first.
> **Leitsatz (unchanged):** capabilities via MCP; host/subagents author ALL text
> (`brief_*→record_*`); **no in-process LLM text-gen**; OpenAI = embeddings + images only;
> structure enforced by the engine, dynamics LLM-judged-by-the-host with evidence.

---

## 1. What's hardcoded today (the problem)
Phase *specs* are data already, but the **grammar** is Double-Diamond-shaped. Four baked-in spots:

| # | Hardcoded | Where | Blocks |
|---|---|---|---|
| 1 | phases must alternate diverge,converge,… | `methodology.py:61` | branches, parallel tracks, N-diamonds, loops |
| 2 | closed enums `ROLES`/`JUDGMENT_KINDS`/`FIDELITIES` | `methodology.py:23-27` | new roles/gates/fidelities |
| 3 | only `"prototype"`/`"prototype_session"` artifact types | `methodology.py:362,366` | surveys, journey-maps, canvases, … |
| 4 | UI maps literal phase keys (`ideate`/`refine`/…) | `web.py:1126-1159` | other methodologies' artifacts won't place |

rev.2 removes **all enums/closed vocabularies from code** — including the capability set.

---

## 2. The model — a tag-driven constellation

A **Methodology** = `{key, name, description, when_to_use, steps: Step[]}`. Steps form a **DAG** via
`consumes`. Every domain word a step uses (`capability`, `role`, `artifact_type`, `gate`, `strategy`)
is a **free tag** — a plain string, like the existing theme tags. **No closed set anywhere.**

### 2.1 Step schema (normative; `?` = optional)
```
Step:
  id          string   required   unique within the methodology
  name        string   required
  tags        string[] required   free tags, incl. a capability tag (e.g. "explore","cluster",
                                   "decide","build","test","synthesize" — or anything you invent)
  intent      string   required   prose for the host author
  consumes?   string[]            ids of upstream steps (DAG edges); [] for roots
  strategy?   string              free council-strategy tag (e.g. "pain-discovery")
  produces?   { role?: string, artifact_type?: string, more_tags?: string[] }   all free strings
  work_items? [{                   optional provider-neutral Act todos; all strings remain open:
                id: string
                title: string
                capability: string
                expected_output_kind: string
                intent: string
              }]
  requires?   {                   ALL data — the engine reads these structurally, never by name:
                min_inputs?: int       # >=N upstream nodes must exist before this step's node
                gate_tag?:   string    # a judgment carrying this tag must be recorded (decided+evidence)
                artifact_tags?:   string[]   # an upstream step must have PRODUCED an artifact carrying each tag
                session_of_tags?: string[]   # a recorded SESSION of an artifact carrying each tag must exist
              }
  loop_back?  string              a prior step id to revisit (LLM-judged)
```
There is **no `capability` enum, no `mode`/`breadth` enum, no `role`/`fidelity` enum.** The
capability is just one of the step's `tags`; the engine does not switch on it.

`work_items` removes the hidden requirement that a model invent the missing to-do list. Each item
seeds a real Act task after the step's frame and any integrity preflight. It is optional:
exploratory methodologies can keep a host-authored fan, while bounded methods such as Reaction Test
declare their exact evidence angles and recorder kind in data.

### 2.2 Shape is DERIVED from the data, not declared
- A step is a **fan** ("diverge") when the host records **>1 node** against it; a **waist**
  ("converge") when it records **1 node** consolidating its inputs. The UI/engine read this from the
  *actual recorded node counts + the DAG* — there is no fan/single flag to set.
- A "diamond" is any `fan → waist`. N diamonds, branches, parallel tracks, `loop_back` spirals are
  all just DAG shapes. (Kills #1 — no alternation concept exists.)

### 2.3 Suggestions registry (MCP-served **data**, never enforced)
The common building blocks live as **editable data** under `sonaloop/suggestions/`
(`capabilities.json`, `roles.json`, `artifact_types.json`, plus methodology templates), and the MCP
*offers* them so the host has good defaults and reuse — **as suggestions, not constraints**:
- `suggest_capabilities()` → e.g. `[{tag:"explore", hint:"fan councils per persona/idea", typical_requires:{}}, {tag:"decide", hint:"consolidate a fan", typical_requires:{min_inputs:2, gate_tag:"divergence_complete"}}, …]`
- `suggest_roles()` · `suggest_artifact_types()` · `suggest_methodologies()` (full constellation templates: double_diamond, dschool, lean, design_sprint, …).
You may adopt a suggested tag, tweak it, or invent a brand-new one — the engine treats them all
identically. Adding a suggestion = editing data; it never gates what's allowed. (Replaces rev.1's
"capability catalog = the code extension point": there is no code extension point — only suggestions.)

---

## 3. Generic invariants — graph mechanics only, tag-agnostic
The engine's **only** fixed concepts are: the DAG, an integer `min_inputs`, reference equality
between tags, and evidence-backed judgment *presence*. It **never compares a tag to a list**.

- **INV-DAG** `consumes` ids exist; acyclic except declared `loop_back` (logged).
- **INV-READY** a step is recordable only when its `consumes` are all complete.
- **INV-INPUTS** a step's consolidating node requires `>= requires.min_inputs` upstream nodes (when set).
- **INV-GATE** if `requires.gate_tag` is set, a judgment carrying that tag (decided, rationale, ≥1
  evidence_ref) must exist upstream. The tag string is free; only its *presence* is required.
- **INV-EDGES** a consolidating node's `from_node_ids ⊆ upstream nodes`; `refines` edges drawn.
- **INV-ARTIFACT** for each `requires.artifact_tags[T]`: some upstream step must have produced an
  artifact carrying tag T; for each `requires.session_of_tags[T]`: ≥1 recorded session of an
  artifact carrying tag T. Pure tag-equality references (an artifact's tags = its type + any
  discriminators, e.g. a fidelity tag) — no literal `"prototype"`/`"prototype_session"` in the
  invariants (only the compatibility `phases→steps` translator names old strings, as back-compat glue).
- **INV-CITE** every node cites ≥1 council; every artifact claim cites a session-log state.

A4 stands: "explored enough?", "which wins?", "ready?" are LLM judgments recorded with evidence;
the engine requires the judgment's *presence* (by `gate_tag`), never a count or a tag whitelist.

---

## 4. Engine — generic, tag-agnostic DAG interpreter
- **State (project):** `methodology` (key) + `step_log: {step_id:{status, node_ids:[], decision_node_id?,
  judgments:[], artifacts:[]}}`. No phase cursor, no shape flags.
- **Tools** (old names kept as thin aliases): `list_methodologies` · `get_methodology` ·
  `start_methodology_project` · `brief_next(project_id)` (the ready frontier + each step's tags,
  unmet `requires`, consumed artifacts, instructions) · `record_node(project_id, step_id,
  council_ids, payload)` · `record_judgment(project_id, step_id, gate_tag, decided, rationale,
  evidence_refs)` · `record_decision(project_id, step_id, from_node_ids, payload)` ·
  `record_artifact_session(...)` · `advance(project_id, step_id)` · `get_methodology_state`.
- **Suggestion tools** (§2.3): `suggest_capabilities` / `suggest_roles` / `suggest_artifact_types` /
  `suggest_methodologies` — read-only, data-backed.
- `Synthesis` nodes carry `step`, `tags` (incl. role/capability), `methodology`, + converge
  enrichments. Artifacts carry `tags` + the `step` that built them.

---

## 5. Generic UI — derived from the graph + tags
- **Layout:** x = longest-path depth over `consumes`; a step's nodes spread vertically when it has
  >1 (fan), sit on the axis when 1 (waist) → diamonds emerge for any `fan→waist`. No phase-key maps.
- **Artifacts:** placed in their producing step's column (`artifact.step`); **solid** edge from that
  step, **dashed** edge to the first downstream step whose `requires.artifact_tags` includes the
  artifact's tag — all walked from the graph.
- **Tags everywhere:** capability/role/artifact tags render as chips and feed the existing
  Linear-style filter; the methodology strip shows steps by name + tags. Layout-version `lv` invalidation unchanged.

---

## 6. What stays vs changes
**Stays:** MCP primitives (councils, syntheses, prototypes, Playwright, embeddings, images),
host-authoring, anti-steering, no-LLM-text-gen, the diamond *visual* (emergent), the prototype
harness (prototypes are just artifacts whose `artifact_type` tag is e.g. `prototype`).
**Removed from code:** the alternation rule (#1), the `ROLES`/`JUDGMENT_KINDS`/`FIDELITIES` enums
(#2), the literal artifact strings (#3), the phase-key layout maps (#4), **and the rev.1 capability
catalog** — all become open tags + MCP suggestions (data).

---

## 7. Migration & back-compat
- Re-express the four built-ins as **tag constellations** under `methodologies/*.json` (and seed the
  same as templates under `suggestions/`).
- **Compatibility loader:** specs with the old `phases` key auto-translate to `steps` (`mode:diverge`→a
  step the host records multiple nodes against; `converge`→`requires.min_inputs:2 + gate_tag` + a
  single node; `produces_role`→`produces.role`; `requires_artifacts`→`requires.artifact_tags`;
  `fidelity`→a tag). Existing user phase-specs keep working.
- Engine/UI: delete the enums + parity rule + phase-key maps; replace with §3 invariants + §5 layout.

---

## 8. Milestones (each with a failure-proof acceptance test)
- **C1 — Tags + suggestions, zero enums:** step schema (all tags) + `suggestions/` data +
  `suggest_*` tools + compatibility translator. **Accept:** **grep proves no closed capability/role/
  breadth/judgment/artifact set remains in code**; a step using an **invented capability tag** and
  an **invented artifact_type tag** loads and validates.
- **C2 — Tag-agnostic engine:** DAG frontier + INV-* by graph/`min_inputs`/`gate_tag`/tag-equality
  only. **Accept:** a methodology with a **non-prototype** artifact (`survey`/`survey_response`) and
  a **non-alternating** shape (a fan feeding two parallel decides) runs end-to-end; the engine has
  **no** literal capability/artifact string in its invariants (grep).
- **C3 — Generic UI:** DAG layout, emergent diamonds, artifact attach/route + tag chips/filter from
  the graph. **Accept:** `double_diamond_deep` renders as today AND a different-shaped methodology
  renders correctly — no phase-key/tag literals in layout (grep).
- **C4 — Migrate built-ins** to tag constellations; full suite green; Pfefferminzia still 3 diamonds.
- **C5 — Docs/skills:** driver skills + AGENTS.md use the tag/suggestion vocabulary; an authoring
  guide ("add a methodology = author a constellation of tagged steps; draw on `suggest_*` or invent
  your own tags").

---

## 9. Amendments to existing specs
The **phase grammar and the rev.1 code-level capability catalog are superseded** by this tag-driven
constellation grammar. Built-ins move to `steps` (compatibility `phases` still loads). Host-authoring,
no-LLM, the prototype harness, and the fidelity concept (now a tag) are retained.
