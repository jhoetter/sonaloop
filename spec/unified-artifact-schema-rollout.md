# Unified artifact schema — detailed rollout plan

Status: **Phase 0–4 DONE · Phase 3 field-removal DONE** (2026-06-06) — storage is primitives-only.
Companion to `spec/unified-artifact-schema.md` (the design). Step-by-step execution plan for all phases.

Progress:
- ✅ **Phase 0** — `sonaloop/artifacts.py` primitives + `suggestions/stance_scale.json` &
  `finding_kinds.json` + tests.
- ✅ **Phase 1** — read adapters + `web/_render.py` (one renderer per primitive); councils (transcript &
  voices), synthesis finding-lists and prototype sessions all route through it. Burndown down.
- ✅ **Phase 2** — `record_council/synthesis/prototype_session` accept + persist `statements/findings/
  prompts` (validated); adapters PREFER native (dual-read); briefs + 5 skills carry PRIMITIVES_CONTRACT.
- ✅ **Phase 3 (backfill)** — `scripts/migrate_to_primitives.py --apply` wrote primitives onto all 9
  councils / 4 syntheses / 20 sessions; render verified **byte-identical** before/after (loss-free).
- ✅ **Phase 4 (memory primitives)** — `event()` + `validate_event` (unifies ExperienceEvent/Calendar/
  DailySummary/Reflection) and `pain_point_finding()` (PainPointObservation → persona-scoped Finding);
  `finding_kinds.json` gains `pain_point`; the persona page renders structured pain-points through the
  one finding row.
- ✅ **Layer 2** — edge colors → `suggestions/edge_types.json` (`presentation.edge_colors()`); no edge
  color hardcoded.
- ✅ **UI consolidation (the priority)** — every detail page draws its content through the ONE renderer:
  council voices, synthesis voices and prototype sessions are the SAME `.turn` statement card; every
  finding section (key_problems/pain_solvers/clusters/segmente/ranking/recommendations + persona pains)
  is the SAME `.fitem` row; one stance scale everywhere.
- ✅ **Phase 3 (compatibility-field removal)** — DONE (2026-06-06; no backwards-compat needed — local dev,
  test data only). Storage + model are **primitives-only**: `CouncilSession` dropped `turns`;
  `Synthesis` dropped `key_problems/pain_solvers/handlungsempfehlungen/offene_fragen/shortlist/clusters/
  segmente/ranking/voices`. `record_*` convert the validated payload (or accept native primitives) to
  `statements/findings/prompts` at the write boundary and store ONLY those (+ canonical prose/ids).
  `votes` is **retained** (it drives council mode + the vote tally — not a pure duplicate). All readers
  (markdown export, study briefs, graph node, sentiment strip, persona voices, effort·impact chart,
  council export) were rewired to primitives via read-projection helpers (`finding_texts` /
  `synthesis_recommendations` / `synthesis_sentiment_counts`). The dead synthesis-voices cockpit
  (`_voices_panel`/`VOICES_JS`/`_sent_color`/`_relbar`/`_session_card`) was removed and
  `_persona_voices_html` now renders the unified `.turn` card. Demo re-seeded clean; 127 tests green;
  `tests/test_render_consolidation.py` guards that voice/finding markup comes only from `_render.py`.
  Remaining (NOT done, by choice): the host-authoring INPUT contract still accepts the convenient
  `turns`/`key_problems` shapes and converts them — that's authoring convenience, not stored compatibility.

Guiding rules for every phase:
- **Non-breaking until the last step.** Each phase ships independently and leaves the app green.
- **Verify with the existing gates**: `uv run --group dev pytest -q` (smoke, i18n parity, burndown ratchet,
  presentation-from-data), the golden-diff harness (`/tmp/verify.py` — re-baseline on intentional deltas),
  and Playwright screenshots for visual deltas.
- **Data is JSON.** Every change is a JSON-shape change + a render path; storage engine is untouched.
- **Zero hardcoded vocab.** New vocabularies (stance scale, finding kinds) live in `suggestions/*.json`
  exactly like `section_kinds.json`, so the presentation-from-data gate stays satisfied.

---

## Phase 0 — Foundations (primitive shapes + vocab data)  ·  ~0.5 day  ·  no behavior change

**Goal:** define the primitive shapes and their data-driven vocabularies once, with constructors that
normalize. No rendering or reading wired yet — pure additions + unit tests.

**Files**
- NEW `sonaloop/artifacts.py` — domain-level primitive constructors (no web import; reusable by
  web, export, meta-report, search):
  ```python
  def ref(kind, *, id=None, text=None, quote=None) -> dict
  def stance(value, *, label=None) -> dict                 # value in -2..+2
  def prompt(text, *, kind="question", id=None) -> dict    # kind: question|proposal|goal|focus|hypothesis
  def statement(persona_id, text, *, stance=None, about=None, refs=(), relevance=None, shift=None, meta=None) -> dict
  def finding(text, *, kind, score=None, refs=(), meta=None) -> dict
  ```
  Each returns a plain dict with a stable key set; drops empty optionals (so JSON stays lean).
- NEW `suggestions/stance_scale.json` — the ONE positivity vocabulary:
  ```json
  { "support":   {"value":  2, "label": "support",     "color": "var(--green)"},
    "conditional":{"value": 1, "label": "conditional", "color": "var(--accent)"},
    "neutral":   {"value":  0, "label": "neutral",     "color": "var(--muted)"},
    "skeptical": {"value": -1, "label": "skeptical",   "color": "var(--amber)"},
    "oppose":    {"value": -2, "label": "oppose",      "color": "var(--red)"} }
  ```
  Plus an alias map (compatibility → canonical): `SUPPORT→support, MAYBE→conditional, ABSTAIN→neutral,
  OPPOSE→oppose, positiv→support, bedingt→conditional, skeptisch→skeptical, dafür→support, …`. Put aliases
  in the same JSON (`"_aliases": {...}`) or a sibling; resolved by `present()`-style lookup.
- NEW `suggestions/finding_kinds.json` — the finding kinds → {label_key, id, glyph?}:
  `summary, key_problem, pain_solver, open_question, recommendation, cluster, segment, risk, shortlist,
  ranking`. (The list-section ids/labels the synthesis minimap depends on come from HERE, data-driven.)

**Tests (NEW `tests/test_artifacts_primitives.py`)**
- constructors normalize + drop empties; round-trip JSON-serializable.
- stance alias resolution (every compatibility vote/stance/sentiment term resolves to a canonical value).
- `present("stance:support")` / finding-kind lookups return label+color (extends the presentation gate).

**Done when:** module + JSON exist, unit tests green, full suite green (nothing wired yet).

---

## Phase 1 — Read-adapter layer + primitive renderers  ·  ~2–3 days  ·  the visible win

**Goal:** render every artifact through ONE path per primitive, reading *current* records via adapters.
**Zero data migration.** This is the completion of the `_prose`/`.turn`-card unification, pushed down to
the data view — the four "looks different" surfaces collapse to one code path.

### 1A — Adapters (compatibility record → primitives)
NEW `sonaloop/artifacts.py` (same module), pure read, `(record, store=None)`:
```python
def council_prompts(c)        -> list[prompt]      # prompt(kind=question|proposal) + questions[]
def council_statements(c,store)-> list[statement]  # turns[] → statement(about=prompt-id via question_index,
                                                   #   stance from turn.stance OR matching vote, refs=memory_refs,
                                                   #   meta={input, pushback})
def council_findings(c)       -> list[finding]     # exec_summary→summary, summary→summary(secondary)
def synthesis_prompts(s)      -> list[prompt]       # start_input/goal/next_council_question
def synthesis_statements(s,store)-> list[statement]# voices[] (stance=sentiment, shift, refs=evidence)
def synthesis_findings(s)     -> list[finding]      # gesamtbild/positionierung/arc_narrative→summary;
                                                   #   key_problems/pain_solvers/offene_fragen/shortlist→kind;
                                                   #   handlungsempfehlungen→recommendation(score={effort,value});
                                                   #   clusters→cluster(meta.members); segmente→segment(meta.stance);
                                                   #   ranking→ranking(score)
def synthesis_refs(s)         -> list[ref]          # citations/references/council_ids
def session_statements(se,store)-> list[statement] # reaction → statement(text=verdict, about=focus,
                                                   #   refs=observed_state_refs→ref(kind=prototype_state),
                                                   #   meta=remaining reaction fields)
def note_findings(n)          -> list[finding]      # text → finding(kind from note.kind)
```
Rule: adapters PREFER a record's native primitive fields if present (forward-compat for Phase 2), else
derive from compatibility fields. Stance terms resolved through `stance_scale.json`.

### 1B — Renderers
NEW `sonaloop/web/_render.py` (web HTML via `h()`/`_prose`):
```python
def render_stance(st)  -> str   # the colored chip (_label) from the scale — replaces _stance_color/_label maps
def render_ref(r)      -> str   # a chip: memory icon / internal link / quote tooltip
def render_prompt(p)   -> str   # question banner (.qround-q) or eyebrow, by p.kind
def render_statement(st, store) -> str   # the .turn card: avatar+name + render_stance + meta + _prose(text) + refs
def render_statements(items, store, *, group_by="persona"|"prompt"|None, prompts=None) -> str
def render_finding(f)  -> str   # .psolve row: _prose(text) + score chip (effort·impact) + refs
def render_findings(items, *, kind) -> (section_id, label, html)   # one list-section, id/label from finding_kinds.json
```
- `render_statements(group_by="prompt")` = the discovery transcript (groups by `about`→Prompt, question
  headers). `group_by="persona"` = eval/voices flat cards. Same card, grouping is an argument.
- The **effort·impact quadrant chart** stays a section-level viz (`_effort_impact`) that *consumes*
  recommendation findings — `render_findings(kind="recommendation")` emits chart + rows, preserving the
  current anchors (`#rec-N`) and the chart.
- The **voices filter/sort panel** (`_voices_panel`) becomes a thin wrapper over `render_statements` +
  the existing filter chrome (keep its JS).

### 1C — Route the four surfaces through it
- `web/pages/councils.py`: replace the transcript/cards branches + `_answer_html`/`_persona_head` with
  `render_statements(council_statements(c), group_by="prompt" if discovery else "persona")`; lead findings
  via `render_findings`/`_study_lead`. **Mode derivation stays** (presence of proposal/votes/questions).
- `web/_synthesis.py`: replace the ~7 bespoke list builders with a loop over `synthesis_findings` grouped
  by kind → `render_findings(kind=...)` (preserves section ids/labels for the minimap TOC); voices via
  `render_statements`.
- `web/_detail.py` `_session_card`: `render_statement(session_statements(se)[0], store)` (already a
  `.turn` card — this just removes the bespoke field loop).
- Notes/concepts page: `render_finding(note_findings(n)[0])` where prose is shown.

### 1D — Retire the now-dead per-surface helpers
`_answer_html`, `_persona_head`, `_answer_block`, the `.psolve`/`_rec_row_n`/`_segrow` ad-hoc builders,
`_stance_color`+`_label` map (→ `render_stance`). Lower the burndown baselines accordingly.

**Tests**
- `tests/test_adapters.py`: each artifact → expected primitive lists (table-driven, golden dicts).
- Re-baseline `/tmp/golden.json` (HTML WILL change — that's the unification) and review the diff page by
  page; Playwright screenshots of council (both modes) / synthesis / session to confirm one look.
- i18n: finding-kind + stance labels via `t()`/data (no hardcoded literals — presentation gate).
- burndown: net DOWN (dead helpers removed).

**Risks & mitigations**
- *Synthesis section anchors / minimap*: drive section id+label from `finding_kinds.json`; assert the TOC
  still resolves (smoke). — *Special viz* (chart, voices filter): keep as consumers of primitives, not
  replaced. — *Stance term coverage*: a test asserts every term seen in the corpus resolves via the scale
  (fail loud on an unmapped term, fallback neutral).

**Done when:** all four surfaces render via primitives, suite green, golden re-baselined + visually
reviewed, burndown down.

---

## Phase 2 — Native authoring of primitives  ·  ~1–2 days  ·  additive, dual-read

**Goal:** new councils/syntheses/sessions WRITE the primitive shape directly; adapters keep reading compatibility.

**Steps**
- **Models** (`models.py`): add optional fields `statements: list, findings: list, prompts: list,
  refs: list` to CouncilSession / Synthesis (additive; default `[]`). PrototypeSession: `statements`.
- **record_* (`services/_councils.py`, `_synthesis.py`, `_engines.py`)**: accept the primitive fields;
  `validate_statement`/`validate_finding`/`validate_prompt` (NEW in `artifacts.py`) normalize + check
  (persona_id resolvable, stance in scale, kind in finding_kinds). Compatibility params still accepted (back-compat).
  Persist whichever was given.
- **Adapter precedence** (from 1A) already prefers native fields → new records render natively, old via compatibility.
- **brief_\* (`services/_councils.py`, `_synthesis.py`)**: extend the instructions (precedent:
  `MARKDOWN_CONTRACT`) to describe the primitive shape — "author `statements[]` (one per persona answer)
  and `findings[]` (kind = key_problem|recommendation|…) instead of the compatibility fields."
- **Skills**: update run-council / synthesize / design-thinking to author primitives.
- **Validation tests**: `tests/test_record_primitives.py` — record a council/synthesis via primitives →
  read back → renders identically to the adapter-on-compatibility path.

**Done when:** a council/synthesis can be authored entirely in primitives and renders identically;
compatibility authoring still works; suite green.

---

## Phase 3 — Backfill + retire compatibility  ·  ~1 day  ·  the breaking cleanup (last)

**Goal:** migrate existing records into primitive fields, then delete the duplicate compatibility fields/branches.

**Steps**
1. **Backfill script** `scripts/migrate_to_primitives.py` (idempotent): for every council/synthesis/
   session/note, compute primitives via the Phase-1 adapters and write them into the record's primitive
   fields; `upsert`. Dry-run + `--apply`. Re-runnable.
2. **Verify**: golden-diff before/after backfill = identical (adapters already produced these primitives,
   so rendering is unchanged) — proves the backfill is loss-free.
3. **Retire**: drop the compatibility branches from the adapters (now always native); deprecate the compatibility model
   fields (`turns/votes/voices/key_problems/pain_solvers/handlungsempfehlungen/offene_fragen/clusters/
   segmente/shortlist/ranking/exec_summary/summary/...`). Keep a thin compatibility export shim only if an
   external consumer needs it; otherwise remove.
4. **Lower burndown** + delete dead code; update `spec/unified-artifact-schema.md` status → done.

**Risks:** this is the only breaking step. Gate it behind: backfill dry-run review, golden identity check,
and a DB snapshot (`make snapshot`) before `--apply`. Reversible via snapshot restore.

**Done when:** records store primitives natively, compatibility fields gone, all gates green, golden identical
across the migration.

---

## Phase 4 — Layer 3: persona memory / simulation  ·  ~2–3 days  ·  separate subsystem, same pattern

**Goal:** apply the same treatment to the memory subsystem, which has the same duplication (`pain_points`
modeled 5 ways).

**New primitives (extend `artifacts.py`)**
```python
def event(persona_id, time, *, kind, body, refs=(), meta=None) -> dict   # unifies ExperienceEvent/
        # CalendarEvent/DailySummary/Reflection: actor + time + kind + markdown body + refs
# PainPoint becomes a persona-scoped Finding:
finding(text, kind="pain_point", score={"severity":int,"frequency":int}, refs=[event refs])
```

**Sub-phases (mirror 1→3)**
- 4.1 **Adapters** `event_*` (ExperienceEvent/CalendarEvent/DailySummary/Reflection → `event`;
  PainPointObservation + scattered `pain_points` lists → persona-scoped `finding`).
- 4.2 **Renderers**: reuse `render_finding` for pain points; a `render_event`/`render_timeline` for the
  calendar/timeline views (the persona memory pages + `_calendar.py`).
- 4.3 **Route** the persona/timeline/calendar pages through them; retire bespoke memory renderers.
- 4.4 **Native authoring** in the simulation briefs (`brief_day`/`brief_period`/`brief_consolidation`) +
  `record_*` memory writers; then **backfill** + retire (mirror Phase 2–3).

**Why later / lower priority:** it's a self-contained subsystem; the research-artifact unification (1–3)
delivers the user-visible consistency. Do 4 once 1–3 have proven the pattern.

---

## Cross-cutting: Layer 2 (Node / Edge / Section)  ·  ~0.5 day  ·  mostly already done

Not a rewrite — a *formalization*:
- **Node**: already unified via `present(kind)` + `_study_node`/`_evidence_node`. Action: document the Node
  contract (id, kind, title, project_id, created_at, presentation, href) and have both graph builders emit
  the *same* dict (today plan-graph and the fallback differ slightly — converge them).
- **Edge**: `StudyEdge` is already first-class. Action: ensure the plan-evidence edges and `StudyEdge` use
  one shape; document the edge types in data (`suggestions/edge_types.json`) for the legend (it half is
  already — `_EDGE_COLORS`). Move `_EDGE_COLORS` to data (presentation gate).
- **Section**: already a clean grouping primitive. No change.

---

## Sequencing & estimates

| order | phase | payoff | breaking | est. |
|---|---|---|---|---|
| 1 | Phase 0 foundations | enables all | no | 0.5d |
| 2 | **Phase 1 adapters+renderers** | **the visible consistency win** | no | 2–3d |
| 3 | Phase 2 native authoring | new data is clean | no | 1–2d |
| 4 | Layer 2 formalization | tidies graph | no | 0.5d |
| 5 | Phase 3 backfill+retire | deletes duplication | YES (gated) | 1d |
| 6 | Phase 4 memory subsystem | same fix, layer 3 | no→YES | 2–3d |

**Recommended first slice to ship:** Phase 0 + Phase 1 (council + session + synthesis-lists). That alone
collapses the surfaces the user flagged into one code path, non-breaking, behind the golden harness.

## Definition of done (whole programme)
- Five render functions (`render_statement/finding/prompt/ref/stance`) are the ONLY way artifact content is
  drawn; no per-artifact prose/voice/list builders remain.
- Records store the five primitives natively; compatibility fields removed; one stance scale + one finding-kind
  vocab, both in `suggestions/*.json`.
- Memory subsystem unified on `event` + persona-scoped `finding`.
- All gates green; `spec/unified-artifact-schema.md` marked done.
