# Job → Framework → Format — the three-layer taxonomy

**This is the source of truth.** The whole Sonaloop product (core app, website IA, and the
tracker) aligns on the three orthogonal layers below. The machine-readable companion is
[`sonaloop/taxonomy.json`](../sonaloop/taxonomy.json), loaded via `sonaloop.job_taxonomy`;
keep the two in lock-step. Every repo and ticket tags itself with the layer (and id) it serves.

## The doctor analogy

> You walk into a doctor's office because **your stomach hurts** — that is the **Job**: *why
> does my stomach hurt?* The doctor runs a **process** — history → exam → tests → diagnose —
> that is the **Framework**. Along the way the doctor reaches for individual **tests** — a
> blood test, an X-ray — each of those is a **Format**.
>
> You arrive with a Job; the doctor runs a Framework; reaches for Formats inside it.

The three are **orthogonal axes, not competing lists**: a Job runs *through* a Framework
*using* Formats. The same Format (a council) shows up inside many Frameworks serving many Jobs.

## The three layers

| Layer | One-liner | What it is |
|-------|-----------|------------|
| **Job** | What the user wants — the use case they buy. | The outcome a customer walks in for ("how is my positioning?", "what should I charge?"). The thing sold and the thing measured. The core has **no first-class concept of it today** — the host (Claude) improvises it from a free-text goal; this taxonomy gives Jobs stable ids. |
| **Framework** | The process the run follows end-to-end. | A constellation of steps (a DAG) taking a run from ambiguity to a buildable answer. Frameworks **already exist** in core as [`sonaloop/methodologies/*.json`](../sonaloop/methodologies/) (keyed by `key`) and seed the plan engine. |
| **Format** | A single move inside a run. | One concrete research move at a plan step: a council, a prototype test, a head-to-head, a red-team. |

### Mislabels this model fixes

- **How-Might-We is a Format-shaped move**, not a Job — though it is often sold as one. Here
  it is folded into the **ideation** Job.
- **"JTBD" is a Job**, whose core engine is the `lean_jtbd` **Framework** of the same name.
  Keep the two layers distinct: the Job (`jtbd_demand`) *runs through* the Framework
  (`lean_jtbd`).

## Frameworks (real methodology keys)

Each Framework id maps 1:1 to a methodology `key` shipped under `sonaloop/methodologies/`. The
current catalogue is data-driven and visible in the inspector's **Methodologies** tab; this document
only defines the layer and its contracts.

Frameworks are exposed as structured data (`{id, name, what, when, stages}`) via
`sonaloop.job_taxonomy.framework_descriptions()` and the `list_frameworks` / `describe_framework`
MCP tools, so the website "how it works" page and the job presets draw on one source.

## Formats

| Format id | Name | Status |
|-----------|------|--------|
| `council` | Council | implemented |
| `prototype_test` | Prototype Test | implemented |
| `head_to_head` | Head-to-Head | implemented |
| `red_team` | Red-Team | implemented |

`head_to_head` ships as a Format on top of the artifacts/variant plumbing: it compares two (or more)
concrete options (captured A/B variants or plain text options) side-by-side and the server tallies a
reasoned, *segmented* preference (preference + margin + segment-splits). Drive it via
`brief_head_to_head` / `record_head_to_head` (MCP) — Job presets compose it.

`red_team` ships as a **falsification** Format on top of the council plumbing: it deliberately argues the
NEGATIVE case — *why would this segment NOT adopt / NOT pay / churn?* — to stress-test an idea instead of
flattering it. It re-frames a normal council toward disconfirmation and assigns each persona an explicit
adversarial lens (skeptic / blocker / switching-cost / status-quo / risk); the server groups their
concrete objections by theme into a structured **case-against** (how many personas raise each blocker +
worst severity), optionally beside the **case-for** when run with `stance="both"` (the same question in
both directions). Drive it via `brief_red_team` / `record_red_team` (MCP) — Job presets compose it.

## The mapping table — Job → Framework(s) → Formats → coverage

Each named Job resolves to a concrete default Framework, a set of Formats, and the persona
**coverage** it needs.

| Job (`id`) | Sells as | Default Framework | Frameworks | Formats | Coverage (min personas · axes) |
|------------|----------|-------------------|------------|---------|--------------------------------|
| **Positioning** (`positioning`) | Positioning | `double_diamond` | `double_diamond` | `council`, `head_to_head`, `red_team` | 4 · segment, buying-stage, current-alternative |
| **Pricing / Price-Sensitivity** (`pricing`) | Pricing | `lean_jtbd` | `lean_jtbd`, `jtbd_switch` | `council`, `head_to_head`, `red_team` | 4 · willingness-to-pay, budget-authority, current-alternative |
| **Demand / Jobs-to-be-Done** (`jtbd_demand`) | Demand/JTBD | `lean_jtbd` | `lean_jtbd`, `jtbd_switch`, `customer_discovery` | `council`, `prototype_test` | 5 · segment, trigger-moment, current-alternative |
| **Ideation (How-Might-We)** (`ideation_hmw`) | Ideation (HMW) | `dschool_micro` | `dschool_micro`, `double_diamond_deep`, `design_sprint` | `council`, `prototype_test`, `head_to_head` | 4 · segment, expertise-level, extreme-user |
| **Continuous Discovery** (`continuous_discovery`) | Continuous discovery | `continuous_discovery` | `continuous_discovery`, `dschool_micro` | `council`, `prototype_test` | 3 · segment, lifecycle-stage, recency-of-use |
| **Churn Reasons** (`churn_reasons`) | Churn reasons | `lean_jtbd` | `lean_jtbd`, `customer_discovery`, `jtbd_switch` | `council`, `red_team` | 4 · churn-reason, tenure, current-alternative |
| **A/B Test** (`ab_test`) | A/B test | `lean_jtbd` | `lean_jtbd` | `head_to_head`, `prototype_test`, `red_team` | 4 · segment, current-alternative, buying-stage |
| **Content & Messaging Reaction** (`content_reaction`) | Content reaction | `reaction_test` | `reaction_test`, `double_diamond` | `council`, `head_to_head` | 4 · segment, familiarity, reading-context |

The **coverage** column is the persona spread a Job needs to be trustworthy: a minimum count
plus the axes the panel must span. The full notes (one per Job) live in `taxonomy.json`.

## Job protocols — the run discipline a Job carries

Some Jobs are only trustworthy when run with a specific **discipline** — not just the right
Framework and Formats, but rules about *ordering and commitment* (what must be frozen before
what). Those Jobs carry a `protocol` block in `taxonomy.json`:

```json
"protocol": {
  "name": "…",
  "summary": "…",
  "steps": [{"id": "…", "rule": "…", "tooling": "…"}]
}
```

Each step is a **rule** (what the discipline demands) plus the **tooling** that makes it
checkable (the MCP tools / fields that carry it). The protocol rides verbatim into the Job's
preset (`get_job_preset`), so the host sees the discipline exactly where it plans the run. As
everywhere in core: the host authors all text; a protocol constrains *structure and order* —
the server validates and persists, it never generates.

### A/B test (`ab_test`)

> *Which variant wins — and for whom?*

**Framework: `lean_jtbd`** — the decide-fast loop. An A/B test arrives with the variants
already in hand, so the empathy-first front half of `dschool_micro` (Understand & Observe →
Define POV) would be ceremony; `lean_jtbd`'s spine — state the bet, expose the thing, validate
at a hard waist, loop back if refuted — *is* the A/B discipline (hypothesis before exposure,
verdict at the gate). A run typically enters at `solution_explore` (the variants are the
solution options) and converges at `validate`.

The protocol (`taxonomy.json` → `jobs[ab_test].protocol`):

1. **`variants_up_front`** — all variants defined and FROZEN before any persona sees them; a
   changed variant is a new test. Tooling: `add_artifact` (captured variants) or text options.
2. **`hypothesis_before_exposure`** — exactly ONE falsifiable hypothesis + success metric
   stamped before exposure (`record_hypothesis`); the recording carries its ref
   (`variant_meta.hypothesis_id`), so the verdict answers a pre-registered bet, never a
   post-hoc story.
3. **`randomized_order`** — variant presentation order is randomized per persona (the
   position-bias guard). `brief_head_to_head` hands each participant a deterministic
   `option_order`; the order actually shown is recorded back via `variant_meta.order_shown`
   (validated: each entry must be a permutation of the option labels).
4. **`forced_preference`** — every persona states a forced preference plus intensity (a
   per-option stance −2..2 and one choice with a reason). A genuine "torn" is an
   **abstention** and is counted as one — never silently dropped.
5. **`segmented_verdict`** — the verdict is overall AND per-segment: winner, margin,
   abstentions per segment (`head_to_head.result.segment_splits` +
   `services.segmented_verdict(session_id)`), never one blended number.

The `head_to_head` Format persists all of this on the recorded session
(`head_to_head.variant_meta` = variant ids + per-persona order shown + hypothesis ref) and
stays **backward-compatible**: recordings made before the metadata existed still load, and
`segmented_verdict` derives per-segment margins from their stored tallies.

### Content reaction (`content_reaction`)

> *Does this content land clearly enough to ship?*

**Framework: `dschool_micro`** — the content is already concrete, so the run stays light:
show the fixed stimulus to the target audience, capture comprehension and confusion, then
converge on ship/revise/review. In result-schema terms this Job typically produces
`stimulus_reaction.v1` plus an optional `threshold_gate.v1`.

### Pricing (`pricing`) — willingness-to-pay ladder

> *What should I charge, and where does price sensitivity break?*

The pricing Job carries a van-Westendorp-style **price-ladder** protocol
(`taxonomy.json` → `jobs[pricing].protocol`):

1. **`ladder_up_front`** — a fixed ascending ladder of ≥ 2 price points
   (`brief_price_ladder` / `record_price_ladder`, `price_points=[{label, amount}]` or plain
   `"$29/mo"` strings); a changed ladder is a new run.
2. **`anchor_band_reactions`** — each persona reacts to EACH rung with exactly one anchor
   band: `too_cheap` (suspiciously cheap) / `bargain` / `getting_expensive` /
   `too_expensive`, plus a short grounding quote. The vocabulary is closed — an
   off-vocabulary band is rejected, never coerced.
3. **`grounded_in_profile`** — reactions quote the persona's budget, authority and
   constraints from their loaded `agent_context`; the host never invents a wallet.
4. **`range_and_cliffs`** — the server derives, deterministically: acceptance per rung
   (share in `bargain`/`getting_expensive`), the **acceptable-price range** (lowest→highest
   rung with majority acceptance) and the **cliff point** (largest acceptance drop between
   adjacent rungs) — overall and **per segment**
   (`price_ladder.result` + `services.price_ladder_analysis(session_id)`).
5. **`tier_head_to_head`** — tier/packaging comparisons reuse the `head_to_head` Format with
   price as variant metadata (`variant_meta.variants={label: {id, price}}`); the ladder finds
   the range, the head-to-head picks the tier.

Storage follows the head-to-head pattern: a recorded ladder IS a CouncilSession carrying a
`price_ladder` block — the ladder, the raw structured responses (persona, price point, band,
quote — queryable for analytics) and the derived result — plus a finding of kind
`price_ladder`. No new table.

### Ideation (`ideation_hmw`) — structured HMW, end-to-end

> *Given this How-Might-We, what could we build?*

The ideation Job carries a three-step **reframe → diverge → converge** protocol
(`taxonomy.json` → `jobs[ideation_hmw].protocol`), built entirely on existing record
primitives — no parallel store:

1. **`reframe`** — the host turns the raw problem into **3–5 HMW questions**
   (`record_hmw_reframe`), persisted as the project's open-question records (stable ids —
   the `hmw_ref` every idea attaches to). A bare HMW question is not falsifiable, so it is
   deliberately *not* forced into the hypotheses table (that would pollute the eval
   scorecard's calibration math); whenever the host can state a checkable bet for an HMW it
   passes `prediction` and the question is **also** promoted to a real hypothesis
   (`record_hypothesis`, full falsifiability validation, `derived_from` the question).
2. **`diverge`** — the council generates ideas (`brief_council` with the HMW questions as
   prompts); every idea is persisted as a first-class **note of kind `idea`**
   (`record_ideas`) carrying `{persona_id, hmw_ref, cluster?}` — an unattributed or
   unanchored idea is rejected. Ideas live in the project graph (sections/edges work on
   them) and are queryable via `list_ideas(project, hmw_ref|persona_id|cluster)`.
3. **`converge`** — a **forced ranking** (`record_ideation_summary`, ordered
   `shortlist=[{idea_id, rationale}]`, rank = position, rationale required per pick) is
   recorded as an `ideation` block on a CouncilSession: problem + HMW questions + the full
   idea pool + the ranked shortlist. The returned `cite_as` ref (`{kind: 'council', id}`)
   plugs straight into `record_decision`'s `based_on` — the ideation output is
   **decision-record compatible by construction**.

## Adding a Job — the repeatable recipe

Every new Job follows the same checklist (machine-checked by
`job_taxonomy.lint_taxonomy()` — run `sonaloop taxonomy-lint`, enforced for every Job by
`tests/test_job_taxonomy.py`):

1. **Definition question** — the `user_question` a buyer walks in with, phrased from their
   side ("Which variant wins — and for whom?"). Plus stable `id` (lower_snake_case, never
   renamed), `name`, and a unique buyer-facing `sells_as` label.
2. **Framework mapping** — `frameworks` (each id must be a taxonomy Framework whose
   `methodology_key` resolves to a real spec under `sonaloop/methodologies/`) and a
   `default_framework` from that list. Justify the default in this doc.
3. **Formats** — the moves the Job composes (`formats` ⊆ the taxonomy Format ids), lead
   Format first.
4. **Coverage minimum** — `coverage.min_personas` (≥ 1) + the `persona_axes` the panel must
   span, with a one-line `note` on why that spread makes the answer trustworthy.
5. **Protocol block** — when the Job sells a run *discipline* (ordering/commitment rules),
   encode it as `protocol.steps[{id, rule, tooling}]` (see "Job protocols" above) and add the
   Job to `job_taxonomy.PROTOCOL_REQUIRED_JOBS` so the lint enforces it.
6. **Docs section** — a row in the mapping table plus (if it has a protocol) a protocol
   subsection here, mentioning the job as ``(`<id>`)`` — the lint greps for it.
7. **Website registry note** — the website repo consumes this taxonomy (`sells_as` is the nav
   label); a new Job lands there by inheriting the taxonomy entry — never hand-duplicate ids
   or labels in the website registry. Keyword signals for `sharpen_question`
   (`job_presets._JOB_SIGNALS`) must also cover the new Job (test-enforced).

### Candidate Jobs (not yet scheduled)

| Candidate id | One-liner |
|--------------|-----------|
| `onboarding_friction` | Where do new users stall in the first session, and which friction is cheapest to remove? |
| `naming_tests` | Which name/label do the target segments understand, remember, and not mis-read? |
| `messaging_resonance` | Which message lands with which segment — and which falls flat or backfires? |
| `churn_deep_dive` | For ONE churn cohort: reconstruct the leaving journey and find the reversible moment. |

## How to consume it

```python
from sonaloop import job_taxonomy

job_taxonomy.jobs()                # all Jobs (id, frameworks, formats, coverage)
job_taxonomy.get_job("positioning")
job_taxonomy.framework_keys()      # {"double_diamond", "lean_jtbd", ...} — real methodology keys
job_taxonomy.format_ids()          # {"council", "prototype_test", "head_to_head", "red_team"}
```

Downstream tickets reference this artifact directly:

- **Website IA** — Jobs are the products sold; the `sells_as` field is the navigation label.
- **Job presets + sharpen-the-question** — shipped in `sonaloop/job_presets.py`: one preset per Job
  (framework + formats + coverage, derived live from this taxonomy) plus the deterministic
  `sharpen_question` helper that turns a fuzzy goal into a well-formed study spec. MCP surface:
  `list_job_presets` / `get_job_preset` / `sharpen_question` / `start_job_study`.
  Jobs/Projects also carry visual metadata: pass `icon=<existing name>|"random"` when
  creating/starting a study, inspect the existing catalogue with `available_project_icons`,
  replace it with `set_project_icon`, or generate a saved custom SVG via `generate_project_icon`.
- **Methodology surface** — Frameworks here are the real `key`s already in `sonaloop/methodologies/`;
  the inspector exposes them under `/methodologies` with one page per Framework.

## Naming + stable ids

- **Job ids** are lower_snake_case and stable (`positioning`, `pricing`, `jtbd_demand`,
  `ideation_hmw`, `continuous_discovery`, `churn_reasons`, `ab_test`, `content_reaction`). Never renumber or
  rename — add new Jobs instead.
- **Framework ids** equal the methodology `key` (`double_diamond`, …).
- **Format ids** are lower_snake_case (`council`, `prototype_test`, `head_to_head`, `red_team`).

Any repo or ticket tags itself with `layer` + the relevant id (e.g. `job:positioning`,
`format:red_team`) so cross-repo work stays aligned.
