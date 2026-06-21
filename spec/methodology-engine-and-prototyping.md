# Methodology Engine, Orchestration Runtime & Agent-Usable Prototyping — Specification

> **Status:** **IMPLEMENTED — M1–M5 shipped 2026-06-03** (rev.3 design below).
> **Built:** `methodology.py` (engine + registry; built-ins double_diamond/dschool_micro/
> lean_jtbd), `prototypes.py` (scaffold/registry/runner), `browser.py` (Playwright harness),
> `runtime.py` (autonomous loop + LLM/Stub AuthoringBackend); storage v4 tables; MCP tools
> (§8) + CLI mirrors (§8.5); read-only UI (methodology strip + diamond view + prototype
> viewer); `make playwright`; the `methodology-run` skill. Tests: `test_methodology_engine`,
> `test_prototypes`, `test_browser_harness` (live + graceful), `test_runtime`, and the MCP
> contract. A live autonomous run produces a real wide→narrow→wide→narrow diamond with a real
> prototype + a real Playwright session.
> **Supersedes** `spec/design-thinking-methodology.md` (history only; see §1).
> rev.3 closes the five gaps that blocked a cold start: runtime two-mode mechanics (§5),
> Playwright session/ref model (§7), the normative methodology schema (§4), the prototype
> scaffold/concept model (§6), and the full MCP/CLI/data wiring (§8–§10).
>
> **Locked decisions:** (1) engine is **structure-enforcing + LLM-judged** — it guarantees shape,
> never hardcodes dynamics; (2) **first-class app generation** (scaffold); (3) personas use apps via
> **headless Playwright** on the real running app; (4) methodologies are a **data-driven registry**;
> (5) a **thin hybrid runtime** (§5): an always-present host-stepped **engine** + an optional
> **autonomous loop**. **Leitsatz (unchanged):** nothing hardcoded as dynamics/outcomes; MCP exposes
> capabilities; all *text* is authored via `brief_*→author→record_*`; every claim traceable;
> personas non-directional (anti-steering). The persona experience-driven council loop is the base.

---

## 1. Why the first attempt failed (lessons this spec encodes)
A facilitation-only run (one skill + phase tags) produced a **chain, not two diamonds**, and a
**prototype no agent ran**: (1) **no divergence** — one council/phase, four nodes in a line;
(2) **no real artifact** — the app was *described in prose*; (3) **methodology not first-class** —
tags, not a selectable engine; (4) **ventriloquized** — a single ambient orchestrator improvised
every step (non-reproducible). **Kept:** graph substrate (Project ⊃ Synthesis ⊃ Council, typed
edges, `voices`, meta-report), host-authoring, anti-steering, the experience→memory seam.
**Added:** the engine (§3–4), the runtime (§5), the prototype harness (§6–7).

**Spec-wide acceptance invariants** (every milestone is tested against these):
- **A1** a converge phase cannot be recorded until its diverge phase has **≥2 distinct exploration
  nodes** *and* a recorded **`divergence_complete`** judgment with rationale + ≥1 evidence ref;
- **A2** a converge node carries **edges from every exploration it consumed**;
- **A3** every node references ≥1 council; every prototype claim references a **session_id present
  in the session log**;
- **A4** no engine code contains a numeric threshold that decides *dynamics* (saturation, "good
  enough"); those are LLM judgments recorded with evidence.

---

## 2. Architecture map
```
 FOUNDATION (unchanged): personas · experience/memory · councils · syntheses · graph · meta-report
        ▲ MCP capabilities          ▲                         ▲
 ┌──────┴──────┐         ┌──────────┴─────────┐     ┌─────────┴──────────┐
 │ A. ENGINE   │         │ B. PROTOTYPES      │     │ C. RUNTIME (§5)    │
 │ data-driven │         │ scaffold·run·      │     │ engine (host-      │
 │ methodology │         │ Playwright-drive   │     │ stepped) + optional│
 │ structure + │         │ real apps          │     │ autonomous loop    │
 │ LLM-judged  │         │                    │     │ + persona sessions │
 └──────┬──────┘         └──────────┬─────────┘     └─────────┬──────────┘
        └──────── the engine + runtime orchestrate A & B per the chosen methodology ─────┘
```

---

## 3. Pillar A — the engine: enforce structure, let the LLM judge dynamics

### 3.1 Two layers
- **Structural invariants** (deterministic validation; about *shape*, safe to encode — like "a
  synthesis must cite councils"). Listed normatively in §3.4.
- **Dynamic judgments** (LLM-made, evidence-backed, *recorded* — never counted): "explored
  enough?", "is this THE core problem?", "spec fundable?". The engine **requires their presence**
  but never their content or a number.

### 3.2 Node model (reuses `Synthesis`)
Every phase output is a `Synthesis` with added fields `phase`, `mode∈{diverge,converge}`, `role`,
`methodology`. A **diverge** phase yields **N exploration syntheses** (same graph depth = the fan);
a **converge** phase yields **one** synthesis with `refines` edges *from* each consumed exploration
(`from_exploration → to_convergence`). Cross-phase hand-off (waist → next fan) is a `spawned_from`
edge `convergence → each next exploration`. The existing longest-path layout then renders
wide→narrow→wide→narrow (§9 diamond view).

### 3.3 Judgments
A judgment = `{id, project_id, phase_key, kind, decided:bool, rationale, evidence_refs:[ref],
created_at}` where `kind∈{divergence_complete, core_problem_chosen, spec_ready, loop_back}` and
`ref` is a `council_id | synthesis_id | session_id`. Stored in `methodology_judgments` (§10).

### 3.4 Structural invariants (enforced in `record_convergence` / `advance_phase`)
- **INV-ORDER** phases are recorded in the methodology's declared order; `advance_phase` only moves
  to the next phase or a declared `loop_back` target (logged as a `loop_back` judgment).
- **INV-BREADTH** for a converge phase whose `consumes = D`: `count(explorations where phase=D) ≥ 2`.
- **INV-JUDGE** a `divergence_complete` judgment for `D` exists with `decided=true`, non-empty
  `rationale`, ≥1 `evidence_ref`.
- **INV-EDGES** the convergence node's `from_node_ids ⊆ explorations(D)`; the engine creates a
  `refines` edge from each (and `spawned_from` from this convergence to next-phase explorations as
  they are recorded).
- **INV-CITE** each exploration/convergence node has ≥1 `council_id`.
- **INV-ARTIFACT** if the *current* phase declares `requires_artifacts`: `prototype` ⇒ ≥1 prototype
  is linked to the project before its `divergence_complete`; `prototype_session` ⇒ ≥1
  `prototype_session` recorded before convergence.
- Violations raise a typed `MethodologyError` with a precise message (see §8.4).

### 3.5 No dynamics are hardcoded (the A4 guarantee)
The engine has **no** saturation window, no min/max counts driving transitions. `diverge_by` in a
spec is *guidance text*, not a loop bound. "How many explorations" is decided by whoever authors
the `divergence_complete` judgment (host or autonomous backend), always with evidence.

---

## 4. Methodology spec — normative schema (data-driven registry)
Built-ins ship as `sonaloop/methodologies/<key>.json`, loaded into an in-memory registry at
import; user-defined specs persist in the `methodologies` table. Validation = `validate_methodology_spec()`.

**Schema (all keys lowercase; `?` = optional):**
```
Methodology:
  key            string   required  unique, [a-z0-9_]+
  name           string   required
  description    string   required
  when_to_use    string   required
  phases         Phase[]  required  length ≥ 2
Phase:
  key                string                 required  unique within methodology
  name               string                 required
  mode               "diverge"|"converge"   required
  intent             string                 required  (prose for the author)
  council_strategy   "pain-discovery"|"positive-deepdive"|"tension"|"goal"   required
  diverge_by?        "persona_subset"|"angle"|"solution_candidate"           (diverge only; guidance)
  consumes?          string (a prior phase.key)        (converge: which fan it consolidates)
  produces_role      "problem-landscape"|"point-of-view"|"solution-options"|"spec"   required
  requires_artifacts? ("prototype"|"prototype_session")[]
  loop_back?         string (a prior phase.key)        (converge only; target if LLM judges fail)
```
**Validation rules:** first phase `mode=diverge`; modes alternate `diverge,converge,...`; every
`converge` phase has `consumes` pointing at the immediately preceding `diverge` phase; every
`loop_back`/`consumes` target exists; `produces_role` of a converge phase ∈ {point-of-view, spec}.

**Built-ins shipped at M1:**
- `double_diamond` — discover(diverge,pain-discovery,problem-landscape) → define(converge,goal,
  point-of-view) → develop(diverge,positive-deepdive,solution-options, requires `prototype`) →
  deliver(converge,tension,spec, requires `prototype_session`, loop_back=develop).
- `dschool_micro` — understand·observe (diverge) → define-pov (converge) → ideate (diverge) →
  prototype-test (converge, requires prototype_session). (Maps the d.school micro-cycle.)
- `lean_jtbd` — problem-explore (diverge) → problem-pick (converge) → solution-explore (diverge,
  requires prototype) → validate (converge, requires prototype_session).

`role` is a **light tag** (UI + next-phase `consumes`); the synthesis content stays emergent and
host-authored. **No structured `*_set` objects.**

---

## 5. Pillar C — the thin hybrid runtime (engine + optional autonomous loop)

**The MCP subtlety, pinned:** the server cannot call back into the ambient coding agent. So there
are exactly two execution modes over one engine:

- **Engine (always present, host-stepped).** Pure capability layer: registry, state, validation,
  `brief_phase`/`record_*`/`advance_phase`. The ambient agent (or a human via CLI) drives the loop:
  `brief_phase → author → record_exploration|record_convergence → record_judgment → advance_phase`.
  This is the only mode shipped through M4. It is *reproducible in structure* (invariants hold for
  any caller) even though the *text* is caller-authored.
- **Autonomous loop (optional, M5).** A `run_methodology(project_id)` process that owns the loop
  itself and authors text via an **LLM AuthoringBackend** (§5.2). It calls the *same* engine
  functions, so invariants and anti-steering gates apply identically.

**Persona-agent session** is a first-class runtime object only where it must be — driving a
prototype (§7) — and is otherwise just a `prepare_persona_agent_context` packet. In engine mode the
*ambient* agent runs persona reasoning (spawning subagents is the caller's job, as today); in
autonomous mode the runtime runs it via the backend. Either way, persona reactions reach the engine
through the same `record_*` contract.

### 5.2 AuthoringBackend interface (autonomous mode, M5)
```
class AuthoringBackend(Protocol):
    def council_turns(frame) -> turns           # per-persona, grounded in context
    def synthesis(frame) -> payload             # exploration or convergence payload
    def judgment(frame) -> {decided, rationale, evidence_refs}
    def prototype_reaction(frame, driver) -> reaction   # driver = ProtoSession (§7)
```
Default impl `LLMAuthoringBackend` (Anthropic Claude; pluggable) configured via
`PERSONA_COUNCIL_LLM_PROVIDER` / `_MODEL` / `_API_KEY` (M5). It reuses the existing prompt builders
(`build_synthesis_prompt`, council frames) so autonomous output matches the host-authored schema.
The autonomous loop, in pseudocode:
```
while not state.complete:
    b = brief_phase(pid)
    if b.mode == "diverge":
        while backend.judgment(divergence_frame).decided is False:   # LLM decides breadth, not a count
            ex = backend.synthesis(exploration_frame(b));  record_exploration(pid, ex.council_ids, ex)
        record_judgment(pid, b.phase, "divergence_complete", True, j.rationale, j.evidence_refs)
    else:
        conv = backend.synthesis(convergence_frame(b));   record_convergence(pid, conv.from, conv, b.role)
    advance_phase(pid)
```
Anti-steering: the autonomous backend is bound by the same critic gates (§7.4); a run that trips
groundedness/anti-steering is flagged and halts for review.

---

## 6. Pillar B — prototype generation, registry, runner

### 6.1 Concept model (host-authored input) → generated runnable app
`scaffold_prototype(slug, name, concept, kind="web", template="spa-min", project_id?)`. The
**concept** is host-authored JSON; the **app is generated deterministically** from it (so it is
runnable with no hand-editing — that is "very easily"). The legacy `kind="web"` path remains the
classic prototype. Passing a DATA artifact type as `kind` (or CLI `--type`) chooses a richer
archetype from `suggestions/artifact_types.json`, for example `canvas`, `model`, `journey`,
`dashboard`, `cards` or `comparison`.
```
Concept (template "spa-min"):
  title    string
  summary  string
  screens  [ { id, title,
               elements: [ { kind: "button"|"input"|"select"|"text"|"link",
                             id, label, options?:[..], goto?: screenId } ] } ]
  start    screenId
```
The `spa-min` template (`sonaloop/prototype_templates/spa-min/`) renders a **real,
clickable, single-file SPA**: a nav of screens, each with the declared elements as actual DOM
(`<button>`, `<input>`, `<select>`…); `goto` wires navigation; inputs hold state. Result: a genuine
app a persona can drive via Playwright (real refs, real state changes) — not a mockup. Output is
written to `prototypes/<slug>/index.html`, registered, versioned.

Freeform concepts do not need `screens[]`. The `canvas` artifact type uses `spa-freeform` and
accepts frames or a single surface:
```
Canvas concept:
  title    string
  summary  string
  start    frameId
  frames   [ { id, title, layout?: "canvas"|"map"|"board"|"room",
               layers: [ { kind: "panel"|"hotspot"|"map"|"timeline"|"board"|
                           "metric"|"meter"|"person"|"entity"|"image"|"control",
                           id, x?, y?, w?, h?, goto? } ],
               actions?: [ { label, goto?, primary? } ] } ]
```
This is the intended path for service-control rooms, dispatch maps, tangible-product mockups,
game-like simulations and other prototypes whose main learning is visual or operational rather
than a linear form flow.

Generated prototypes are design-system surfaces. `prototypes.py` injects the compiled
`workspace_design_system.v2` runtime context into the static HTML: local/core runs use the
Sonaloop default tokens; Cloud-hosted or Remote-MCP runs bind the active workspace design system
before scaffolding. Templates therefore consume tokenized color, radius, shadow, typography and
chart/status variables instead of hardcoded brand choices. The generated file includes:

- a reproducible `sonaloop-design-system` JSON snapshot with workspace/version/hash metadata;
- light/dark CSS variable blocks;
- a semantic `--proto-*` layer for prototype components (surfaces, fields, controls, cards,
  chips, maps, charts, focus rings, spacing, density and radius);
- `data-design-*` body attributes for the resolved preset, density and radius mode;
- optional brand markup from the design-system logo/wordmark when the concept requests
  `show_brand` / `brand_header`.

That means presets and fine-grained workspace edits both flow through the same token compiler:
changing radius, density rows, spacing, font stacks, chart series or status colors changes the next
scaffolded prototype without adding a template-specific branch. Cloud resolves `workspace-asset:`
logo refs to data URIs so the generated file stays self-contained.

Other entry points: `register_prototype(...)` for hand-authored apps (any `run` mode); richer
templates (`fastapi-min`) deferred.

### 6.2 Registry & runner
- `Prototype{ id, slug, project_id?, name, version, kind:"web", path, entry, run:"static|node|
  python", run_cmd?, created_at, notes }` (table §10). Versioned (`v0.1`…) for cross-version
  reaction comparison.
- `run_prototype(id)` → starts the app on an ephemeral **127.0.0.1** port (static: a local
  `http.server` rooted at `path`; else `run_cmd`), returns `{prototype_id, url, pid}`; tracked in a
  process registry. `stop_prototype(id)` terminates it. **Never** binds a public interface.

---

## 7. Playwright harness — agents drive the REAL app

### 7.1 Sessions (server-side, key the whole interaction)
A `ProtoSession` lives **in the MCP-server process**, keyed by `session_id`:
`{session_id, prototype_id?, url, persona_id?, browser, page, refmap, log:[snapshot|action…],
created_at}`. Sessions are explicit, closed by `proto_close`, and reaped on idle/exit. Concurrency:
a small cap (default 4) of live sessions; `proto_open` errors past the cap.

### 7.2 Snapshot & the `ref` model (pinned)
Each `proto_open`/`proto_read`/`proto_act` returns a fresh **snapshot**:
```
Snapshot:
  url, title
  tree: Node[]                         # accessibility tree, actionable-pruned
  text: string                         # visible text, truncated (cap ~4k chars)
  screenshot_path?: string             # optional, off by default
Node: { role, name, ref?, value?, checked?, disabled?, children:Node[] }
```
- A `ref` (`"e1","e2",…`) is assigned **only to actionable nodes** (button, link, textbox,
  checkbox, combobox, menuitem, tab). **Refs are valid only for the latest snapshot of that
  session**: every snapshot regenerates `refmap: ref → locator` (built from Playwright element
  handles). `proto_act` with a ref **not in the current refmap** errors `STALE_REF: re-read`.
  Agents always act on the most recent snapshot — no cross-render stability needed.
- The tree is pruned to actionable + structural-with-name nodes to cap tokens.

### 7.3 Action tools
- `proto_open(prototype_id? | url?, persona_id?)` → `{session_id, snapshot}`. (If `prototype_id`
  and not running, auto-`run_prototype` first.)
- `proto_act(session_id, action)` → `{snapshot}`. `action = { type:"click"|"type"|"select"|
  "scroll"|"key"|"wait", ref?, text?, value?, key?, ms? }`. Appends to `session.log`.
- `proto_read(session_id)` → `{snapshot}`. `proto_close(session_id)`. `list_proto_sessions()`.
- Missing Playwright/chromium → all return a clear `PLAYWRIGHT_UNAVAILABLE` envelope (degrade, not
  crash).

### 7.4 Reaction → experience → council (real use, audited)
- `brief_prototype_session(persona_id, prototype_id)` → gather: persona context + how-to-drive +
  anti-steering instructions + the prototype's screen map.
- The driver (host subagent, or autonomous backend) runs a Playwright session, then authors the
  lived experience; `record_prototype_session(persona_id, prototype_id, session_id, date,
  reaction)` →
  (a) writes a **`prototype_session`** artifact `{id, persona_id, prototype_id, session_id, date,
  reaction, observed_state_refs}` (table §10); (b) writes it as an **experience day-activity +
  memory deltas** (reuses `record_day`/`record_memory_deltas`) with `artifacts_touched=[prototype
  ref]`. So `prepare_persona_agent_context` surfaces the real use in the Deliver council.
- **Groundedness critic (new dimension).** `brief_eval_critic` for a prototype reaction includes
  the session `log`; the verdict gains `prototype_groundedness` (0–5). `record_prototype_session`
  validates that the reaction's claims map to states present in `session.log` (by ref/text); a
  reaction praising what was never exercised is flagged (anomaly) — killing the first attempt's
  fiction by construction.

---

## 8. MCP surface (full; envelope + `_NEXT` as in `mcp-tool-contract.md`)

### 8.1 Methodology (engine)
| tool | params | returns | `_NEXT` |
|---|---|---|---|
| `list_methodologies` | — | `[{key,name,description,when_to_use,phase_keys}]` | `get_methodology` |
| `get_methodology` | `key` | spec | `start_methodology_project` |
| `start_methodology_project` | `title, goal, methodology_key, persona_ids?, description?` | project (phase=phases[0]) | `brief_phase` |
| `set_project_methodology` | `project_id, methodology_key` | project | `brief_phase` |
| `brief_phase` | `project_id` | `{phase, mode, intent, council_strategy, diverge_by?, consumes?, requires_artifacts?, unmet, instructions, frame}` | mode=diverge→`record_exploration`; converge→`record_convergence` |
| `record_exploration` | `project_id, council_ids, payload` | synthesis (diverge node) | `record_exploration`\|`record_judgment` |
| `record_judgment` | `project_id, phase_key, kind, decided, rationale, evidence_refs` | judgment | diverge_complete→`record_convergence`; else `advance_phase` |
| `record_convergence` | `project_id, from_node_ids, payload, role` | synthesis (converge node)+edges | `advance_phase` |
| `advance_phase` | `project_id` | `{project, phase}` or `MethodologyError` | `brief_phase` |
| `get_methodology_state` | `project_id` | `{methodology, phase, phases:[{key,mode,status,exploration_count,judgments,convergence_node}], complete}` | — |

### 8.2 Prototypes
`scaffold_prototype(slug,name,concept,kind?,template?,project_id?)`→prototype (`_NEXT run_prototype`);
`register_prototype(...)`; `list_prototypes(project_id?)`; `get_prototype(id)`;
`run_prototype(id)`→`{url,pid}` (`_NEXT proto_open`); `stop_prototype(id)`; `delete_prototype(id)`.

### 8.3 Harness & session
`proto_open(prototype_id?|url?,persona_id?)`→`{session_id,snapshot}` (`_NEXT proto_act`);
`proto_act(session_id,action)`→`{snapshot}`; `proto_read(session_id)`; `proto_close(session_id)`;
`list_proto_sessions()`; `brief_prototype_session(persona_id,prototype_id)` (`_NEXT proto_open`);
`record_prototype_session(persona_id,prototype_id,session_id,date,reaction)` (`_NEXT brief_council`).

### 8.4 Errors (typed; returned in the envelope `ok:false, error:{code,message}`)
`MethodologyError` codes: `BREADTH_TOO_LOW` (INV-BREADTH), `MISSING_DIVERGENCE_JUDGMENT`
(INV-JUDGE), `EDGES_NOT_FROM_FAN` (INV-EDGES), `PHASE_OUT_OF_ORDER` (INV-ORDER), `MISSING_ARTIFACT`
(INV-ARTIFACT), `NO_COUNCIL_CITED` (INV-CITE). Harness: `STALE_REF`, `SESSION_NOT_FOUND`,
`PLAYWRIGHT_UNAVAILABLE`, `SESSION_CAP`. Each message states exactly what is missing.

### 8.5 CLI mirrors
`methodology-list/-get/-start`, `phase-brief/-explore/-judge/-converge/-advance`, `methodology-state`;
`prototype-scaffold/-register/-list/-run/-stop/-delete`; `proto-open/-act/-read/-close`,
`proto-sessions`; `session-brief/-record`. (Same JSON payload contracts as MCP.)

---

## 9. UI (read-only — create/run only via MCP/CLI)
- **Methodology strip** on the project: methodology name, current phase, per-phase status +
  recorded judgments (with evidence links).
- **Diamond view:** x = phase index (the methodology order); within a **diverge** phase, stack its
  explorations vertically (the fan) and draw the **converge** node centered at the next x (the
  waist). Width-by-count per phase yields the genuine two-diamond silhouette. Reuse the interactive
  graph engine (drag/zoom/minimap already built); add phase/mode-aware initial layout + a faint
  diamond guide behind the nodes.
- **Prototype viewer:** prototypes + versions; **iframe** the running app (or screenshot); list
  personas who used it, their reactions, `prototype_groundedness`, and the observed-state evidence.

---

## 10. Data model (schema v3→v4; idempotent `CREATE TABLE IF NOT EXISTS`; JSON-blob)
- **`Synthesis`** += `phase:str`, `mode:str`, `role:str`, `methodology:str` (JSON-blob; no migration).
- **`ResearchProject`** += `methodology:str`, `phase:str`, `phase_log:json`
  (`{phase_key:{status, exploration_node_ids:[], convergence_node_id?, decided_at?}}`).
- **`methodologies`** `(key PK, name, data json, created_at)` — user-defined specs.
- **`methodology_judgments`** `(id PK, project_id idx, phase_key, kind, decided int, data json,
  created_at)`.
- **`prototypes`** `(id PK, slug uniq, project_id idx, version, data json, created_at)`.
- **`prototype_sessions`** `(id PK, persona_id idx, prototype_id idx, session_id, data json,
  created_at)`.
- `config.MEMORY_SCHEMA_VERSION = 4`. `purge_runtime_data` + deletes cascade the new tables.
- Live `ProtoSession` objects and the running-prototype process table are **in-memory only**
  (not persisted); the durable record is the `prototype_session` row + its experience events.

---

## 11. Module layout (new/changed)
```
sonaloop/
  methodology.py          # registry load+validate, engine: brief_phase/record_*/advance_phase, invariants, judgments
  methodologies/*.json    # built-in specs (double_diamond, dschool_micro, lean_jtbd)
  prototypes.py           # scaffold (concept→app via templates), registry, runner (run/stop), process table
  prototype_templates/spa-min/   # the spa-min generator template
  browser.py              # Playwright ProtoSession: open/act/read/close, snapshot+refmap, session cap
  runtime.py              # AuthoringBackend protocol + autonomous run_methodology loop (M5)
  services.py             # thin wiring to the above (reuse record_synthesis/link_studies/record_day/deltas)
  storage.py              # v4 tables + accessors + cascade deletes
  models.py               # Synthesis/ResearchProject field additions; Prototype/PrototypeSession/Judgment
  mcp_server.py           # new tools (§8) + _NEXT entries
  cli.py                  # CLI mirrors (§8.5)
  web.py                  # methodology strip, diamond layout, prototype viewer
tests/  test_methodology_engine.py · test_prototypes.py · test_browser_harness.py (skip if no chromium)
claude-skills/methodology-run/   # thin host-mode driver skill (engine mode): loops brief_phase→author→record
```
Deps: `playwright` as an **optional extra**; `make playwright` runs `playwright install chromium`.

---

## 12. Milestones (ordered; each with a failure-proof acceptance test)
- **M1 — Engine (host-stepped) + registry.** `methodology.py`, 3 built-in specs, all engine MCP
  tools + invariants + judgments, v4 schema, `methodology-run` skill. **Accept:** with
  `double_diamond`, Discover yields ≥2 explorations and `record_convergence` for Define **fails**
  (`BREADTH_TOO_LOW`/`MISSING_DIVERGENCE_JUDGMENT`) until both exist; `get_methodology_state` shows
  wide→narrow→wide→narrow node counts. No numeric dynamic threshold anywhere (grep-tested).
- **M2 — Prototype generation + runner.** `scaffold_prototype` (spa-min), registry, run/stop.
  **Accept:** one `scaffold_prototype` call produces `prototypes/<slug>/index.html` that
  `run_prototype` serves on `127.0.0.1:<port>`, reachable, with the declared screens/buttons in the
  DOM.
- **M3 — Playwright harness + session seam.** `browser.py`, `proto_*` tools, `brief_/record_
  prototype_session`, groundedness critic. **Accept:** a session opens the scaffolded app, performs
  ≥1 `click`/`type`, the returned snapshot reflects the state change, and `record_prototype_session`
  rejects a reaction whose claims have no matching ref/text in `session.log`.
- **M4 — UI.** Methodology strip, diamond view, prototype viewer (iframe + reactions + evidence).
- **M5 — Autonomous mode + hardening.** `runtime.py` + `LLMAuthoringBackend`, parallelism/cost
  caps, anti-steering gates in the loop, more methodologies. **Accept:** `run_methodology` drives a
  full diamond unattended, honoring all invariants and halting on a critic flag.
- **Cross-cutting:** MCP-contract test additions, CLI mirrors, docs/AGENTS.md update.

---

## 13. Risks & open questions
- Keep the runtime **thin** (orchestration + sessions only; not an agent platform).
- Playwright weight → optional extra; harness tests skip without chromium.
- Snapshot tokens → actionable-pruned tree, screenshots off by default, text capped.
- LLM-judged gates must always carry `evidence_refs`; the critic audits them like any claim.
- Loop-backs bounded + logged (a `loop_back` judgment per hop).
- App-use is non-deterministic → the full `session.log` makes every reaction auditable.
- Autonomous-mode model/cost (M5): pluggable client; default Anthropic Claude; budget guard.

---

## 14. Relationship to existing specs
Foundation specs unchanged (`mcp-tool-contract.md`, `memory-and-simulation-architecture.md`,
`research-graph-and-meta-report.md`, `simulation-loop-contract.md`).
`design-thinking-methodology.md` is **superseded**: Double Diamond is one data-driven methodology
(§4) run by the engine/runtime (§3, §5), with prototypes realized by §6–§7.
