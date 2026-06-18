# Result schemas

Result schemas are the output contracts for research jobs. They define what must exist before a
job can be considered done.

They extend the existing model:

- **Job**: what the user wants answered.
- **Framework / methodology**: the process used to get there.
- **Format**: one concrete research move inside that process.
- **Result schema**: the neutral shape of the final or intermediate output.

The machine-readable source is [`sonaloop/result_schemas.json`](../sonaloop/result_schemas.json),
loaded by `sonaloop.result_schemas`.

## Why they are domain-neutral

Schemas should not encode business domains. A pricing job should not create a
`price_sensitivity` schema; it uses `ordered_ladder_sensitivity.v1`. A blog pre-launch check should
not create a `blog_sentiment` schema; it uses `stimulus_reaction.v1` plus, optionally,
`threshold_gate.v1`.

Domain vocabulary belongs in:

- the **Job** contract, e.g. `pricing`, `content_reaction`;
- the user prompt and artifacts shown to personas;
- thresholds and labels configured by the job.

The schema names the reusable result shape.

## Relationship to methodologies

The relationship is many-to-many.

- One methodology can produce several result schemas.
  - `reaction_test` usually produces `stimulus_reaction.v1`, optionally `threshold_gate.v1`.
  - `double_diamond` usually produces `opportunity_map.v1`, `concept_validation.v1`, and
    `study_handoff.v1`.
- One result schema can be reused by many methodologies.
  - `option_comparison.v1` appears in A/B tests, positioning, design sprint down-selection and
    packaging comparisons.

Do not create one methodology per schema. Methodologies are process shapes; schemas are output
contracts.

## Registry shape

Each schema record has:

```json
{
  "id": "stimulus_reaction.v1",
  "name": "Stimulus Reaction",
  "summary": "A cohort reacts to a concrete stimulus...",
  "result_kind": "score_plus_themes",
  "fields": [
    {"id": "sentiment_score", "type": "number", "range": [0, 1], "required": true}
  ],
  "derived_metrics": ["sentiment_score"],
  "done_when": ["A stimulus is fixed before reactions are collected."]
}
```

The registry also carries:

- `job_contracts`: every taxonomy Job and the schemas that define its done state.
- `methodology_contracts`: every methodology and the schemas it typically produces.

Evidence-source requirements are deliberately not part of a result schema. A schema defines the
shape of the finished output; whether a run may use simulated persona evidence or must wait for
real survey/session input belongs to the job/run gate layer.

## Runtime outcomes

A schema registry entry is not the outcome itself. At runtime the completion milestone is a
project-owned `job_outcome` record:

- expected schemas live on the project as `expected_result_schemas` (Job presets stamp this from the
  Job contract);
- `record_job_outcome(project_id, schema_id, result, evidence_refs=[...])` persists the structured
  result;
- syntheses/reports may appear in `evidence_refs`, but they do not own the outcome;
- a project with expected schemas is not complete until every expected schema has a recorded
  `job_outcome`.

This avoids the dangerous shortcut of deriving completion from report prose or `meta.schema`
findings inside a synthesis. The plan can finish its evidence tasks, but the run stays in the finish
lane until the target-schema outcomes are recorded.

## Current schemas

| Schema id | Use |
| --- | --- |
| `stimulus_reaction.v1` | Reactions to a fixed stimulus, with sentiment/comprehension/themes. |
| `ordered_ladder_sensitivity.v1` | Reactions across ordered levels, with acceptable range and cliff. |
| `option_comparison.v1` | Forced or explicit comparison among alternatives, with segment splits. |
| `threshold_gate.v1` | Pass/fail/needs-review decision from a metric threshold. |
| `funnel_friction.v1` | Step-level behavior, drop-off and blockers. |
| `change_forces.v1` | Push, pull, anxiety and habit around change. |
| `opportunity_map.v1` | Clustered opportunities under a target outcome. |
| `concept_validation.v1` | Tested concept/prototype fit, risks and next action. |
| `study_handoff.v1` | Presentation-grade answer, evidence trail and exportable deliverable. |

## Service surface

Read helpers:

- `services.list_result_schemas()`
- `services.get_result_schema(schema_id)`
- `services.list_result_contracts()`
- `services.result_contract_for_job(job_id)`
- `services.result_contract_for_methodology(methodology_key)`
- `services.project_result_contract_state(project_id)`

Write helpers:

- `services.set_project_result_schemas(project_id, refs, source=...)`
- `services.record_job_outcome(project_id, schema_id, result, evidence_refs=[...])`

CLI:

- `sonaloop result-schema-list`
- `sonaloop result-schema-get stimulus_reaction.v1`
- `sonaloop result-contracts`
- `sonaloop result-contract-job content_reaction`
- `sonaloop result-contract-methodology reaction_test`
- `sonaloop result-contract-project <project_id>`
- `sonaloop result-contract-set <project_id> refs.json`
- `sonaloop job-outcome-record <project_id> stimulus_reaction.v1 result.json --ref council:c1`

MCP exposes the same read/write surface for agents.
