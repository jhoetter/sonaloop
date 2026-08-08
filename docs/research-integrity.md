# Research integrity: product understanding, claim posture, and governed dispatches

This contract keeps a weak or interrupted MCP host from turning plausible text into
research evidence. It is enforced in the service and plan layers; prompts explain it but
do not constitute the guardrail.

## Front door and retry identity

Feature-detect the host surface first:

- If a cloud host exposes `begin_research_job`, call that **one** front door with the
  user's full request, a stable non-sensitive `operation_id`, and `methodology` set to
  `auto`, `freeform`, or an exact name/key. On an ambiguous response, retry the exact
  call and exact inputs. Do not also call `start_project` or `start_run`.
- Otherwise use the Core fallback: retry-safe `start_project(operation_id=...)`, then
  retry-safe `start_run(operation_id=...)`, then `run_step` until `kind == "done"`.

Projects created through the retry-safe Core front door are stamped with
`governance_contract="dispatch_v1"`. Historical projects without that stamp remain
readable and writable through the legacy contract.

## Dispatch write contract

Every analyze/act/verify result from `run_step` carries a deterministic opaque
`dispatch_token`. It is a correlation/scope identity, not an authorization bearer;
workspace authorization remains the storage/RLS boundary.

For an active `dispatch_v1` run:

1. Pass the exact token to every recorder used by that dispatch.
2. The recorder validates project, run, task, bucket, capability, and operation key
   **before mutation**.
3. The write uses the dispatch key as its deterministic primitive key.
4. The service links its `{kind,id}` to the task, attempts gate completion, and appends
   the run checkpoint. A response with `dispatch.checkpointed=true` is final; do not
   checkpoint a second time.
5. If more work is required (for example a verify synthesis exists but its judgment is
   missing), the recorder returns `state="linked", checkpointed=false`. Make the required
   token-bound write; the final recorder completes and checkpoints the dispatch.

An exact retry returns or upserts the same primitive and deduplicates the same checkpoint.
Changed content under an immutable operation identity fails closed. A missing, foreign,
wrong-bucket, wrong-task, or wrong-key token fails before content mutation.

Token-aware surfaces include Product Understanding, frames, councils and their structured
formats, syntheses, assets, captured artifacts, flows, usability/prototype sessions,
evidence links, judgments, and completion. CLI commands expose `--dispatch-token`; MCP
tool schemas expose `dispatch_token`.

## Product Understanding preflight

Reaction Test plans insert a mandatory root analyze task with capability
`product_understanding`. `record_frame` cannot bypass it. Every former root consumes the
preflight, so no persona reaction can become ready first.

`record_product_understanding` appends an immutable
`sonaloop.product_understanding.v1` version containing:

```json
{
  "target": {"name": "Product", "url": "https://..."},
  "revision": "deploy:abc123",
  "observed_at": "2026-08-08T10:00:00Z",
  "routes": [{"path": "/", "evidence_refs": [{"kind": "asset", "id": "..."}]}],
  "flows": [{"name": "Home to checkout", "evidence_refs": [{"kind": "flow", "id": "..."}]}],
  "states": [{"state": "home", "evidence_refs": [{"kind": "asset", "id": "..."}]}],
  "capabilities": [{
    "key": "checkout",
    "claim": "Checkout is reachable",
    "status": "observed_present",
    "evidence_refs": [{"kind": "flow", "id": "..."}]
  }]
}
```

Capability status is exactly one of:

| Status | Meaning | Required evidence |
| --- | --- | --- |
| `observed_present` | Seen in the cited revision | project-owned refs |
| `observed_absent` | Actively looked for and not found | refs **and** a documented `verification_attempt` |
| `inferred` | Derived from evidence, not directly seen | project-owned refs |
| `unknown` | Not established | no invented evidence |

Routes, flows, and states are observations and therefore require project-owned refs.
Unknown is preferable to an assumed absence. Later observations append versions with
`supersedes` lineage; they never rewrite the version used by an earlier run.

Remote MCP screenshots follow the stricter [remote stimulus admission](remote-stimulus-admission.md)
contract. Product Understanding must bind the exact immutable flow-manifest id, integer version,
target revision and manifest digest. Its `revision` must equal that target revision, and its
coverage checklist must contain exactly one `inspected` entry for every ordered manifest step,
citing that step's exact admitted asset version. The resolved manifest digest, asset digests and
coverage are copied into the Product Understanding version. A new manifest version therefore
cannot change an older preflight or silently substitute a newer screen.

The compact Product Understanding block is added to council context as **external
stimulus**, never persona memory.

## Cohort Integrity preflight

Reaction Test plans place a final mandatory preflight after Product Understanding **and the initial
research frame**: `cohort_integrity`. The order is deliberate. Product Understanding defines the
external stimulus; `record_frame` commits the actual questions/hypotheses; Cohort Integrity then
checks that the people reacting have independent target context rather than freshly seeded copies of
either. Council completion and the final integrity gate cannot skip it.

The MCP/CLI gather/write/read surfaces are:

- `brief_cohort_preflight(project_id, hypotheses?)`;
- `record_cohort_preflight(project_id, representation, ..., dispatch_token)`; and
- `get_cohort_preflight(project_id, version_id?)`.

Every evaluation appends an immutable `sonaloop.cohort_integrity.v1` version. The current policy is
versioned separately, and every result persists the exact thresholds and feature schema used. A
passing version becomes stale when either the cohort ids or current Product Understanding revision
changes, when the project goal/description changes, or when the root frame's bound
question/hypothesis digest changes. Governed frame dispatches are immutable; the digest check is an
additional fail-closed defense for repair/migration paths.

### Two data lanes

The server never mixes these inputs:

| Lane | Included | Purpose |
| --- | --- | --- |
| independent target context | persona facts, experience events and attached evidence timestamped at or before project creation | establishes lived context that did not originate from this test |
| product stimulus | project goal/description, explicit hypotheses and current Product Understanding | defines what might have leaked into an authored profile |

For each persona the persisted depth record contains total and independent fact/event/evidence
counts, post-project counts, evidence source type, event range, origin provenance, profile creation
time and age at project start. A profile is considered deep only when it has at least six independent
context items and either three independent events or two independent evidence records. Thresholds
are data in `DEFAULT_THRESHOLDS`, never prompt prose.

### Hypothesis leakage features

The deterministic path is always active and contains no product/category vocabulary. It tokenizes
the selected profile claims and each stimulus claim, removes only language function words, then
persists a weighted score:

```text
0.55 × hypothesis-token coverage
+ 0.20 × token Jaccard
+ 0.25 × shared-bigram coverage
```

The gate records input digests, shared-token diagnostics, matched stimulus-segment digest and the
feature algorithm version. A host may optionally supply `sonaloop.semantic_overlap.v1` scores. Each
semantic score must be bound to the server-issued stimulus/profile input digest. The server applies
the same `0.82` threshold regardless of provider/model, while lexical checking still runs; semantic
similarity cannot replace or tune away the deterministic check.

The host also proposes a rationale-bearing representation posture for every participant: `target`,
`skeptical`, `indifferent`, or `non_target`. A countervoice proposal counts only when it carries an
exact `basis_quote` (minimum eight characters) and a `{kind: fact|event|evidence, id}` ref owned by
that persona, dated before project creation, whose stored text contains the quote. The server marks
an unmatched/bare host declaration `unverified` and fails closed with
`COUNTERVOICE_UNVERIFIED`; it never upgrades the label from persuasive rationale prose. A passing
governed council must include one grounded countervoice and a statement whose structured stance
matches the declared non-positive posture (`skeptical <= -1`, `indifferent == 0`, `non_target <= 0`).

### Gate outcomes and real remediation work

The status is one of `pass`, `needs_deepening`, `needs_reselection`, or `overridden`:

- Missing/small cohorts, an ungrounded/missing countervoice, or any high-overlap profile require
  reselection. Independent depth is reported separately but never waives strong hypothesis leakage;
  accept an exceptional legitimate overlap only through the visible rationale-bearing override.
- Too many thin profiles require independent memory/evidence deepening.
- A failed version is still linked and checkpointed as evidence of the attempt. The plan engine
  inserts a new `cohort_integrity` remediation task between it and every former downstream consumer.
  Catalog selection, simulation or corpus grounding must happen as real work before the next
  preflight version is evaluated.
- An override is never inferred. It requires a concrete rationale of at least 20 characters, stays
  visible as `overridden`, and is copied into project/report `sonaloop.report_limitation.v1` records
  and exports. A passing cohort cannot be overridden.

Sonaloop Cloud audit schema v3 freezes this exact server-owned status before its normal result
summary is redacted. PostHog receives `sonaloop_outcome` only for a technically successful
`record_cohort_preflight` receipt with the matching contract version. The four values above plus the
fixed fallback `unknown` are the entire telemetry vocabulary; arbitrary result statuses, rationale
text and malformed contract versions are omitted. This structural projection never enables content
capture, and older receipts without it remain absent rather than being reinterpreted.

Example CLI sequence for a governed dispatch:

```bash
uv run sonaloop cohort-preflight-brief <project-id>
uv run sonaloop cohort-preflight-record <project-id> cohort.json \
  --dispatch-token <token> --key <stable-operation-id>
uv run sonaloop cohort-preflight-get <project-id>
```

`cohort.json` carries `representation`, optional `hypotheses`, optional digest-bound
`semantic_feature`, and—when actually changing the cohort—`persona_ids` plus a
`selection_rationale`. The project and report inspector cards show status, policy version,
independent depth, maximum overlap, countervoices, required work and any override limitation.

## Reaction Test stimulus and claim posture

A Reaction Test act task cannot complete without both a current Product Understanding
version and admitted project stimulus: an input asset/screenshot, successfully captured
artifact, valid screen flow, prototype, or grounded verified session.

Every structured assertion is stamped under `sonaloop.claim_posture.v1`:

| Posture | What it may say | Minimum citation |
| --- | --- | --- |
| `observed` | What a user actually did or saw in observed use | grounded verified session **and exact `step:N` anchor** |
| `memory_grounded` | A claim from persona memory/real evidence | memory/evidence/recall ref |
| `inferred` | An interpretation derived from cited records | project-owned evidence ref |
| `simulated` | A synthetic persona reaction or prediction | persona, stimulus, council, or derived-evidence ref |
| `unsupported` | A visible hypothesis, not evidence | none; terminal gate remains blocked |

Persona statements in a Reaction Test default to `simulated`. Findings without an
explicit posture default to `unsupported`. Summary/report prose must be covered by an
explicit top-level `claims` inventory; otherwise `prose_uncovered=true`. Screenshots and
flows prove product state, **not user behavior**. A synthetic council cannot prove observed
behavior either.

Reference ids are resolved server-side rather than trusted because they look plausible. A
`persona` ref must name a stored persona in the project's frozen cohort. An `evidence` ref must
name a stored evidence record owned by one of those personas. A `memory` or `recall` ref must
resolve to a real experience event or evidence record whose owner is in the same cohort. Invented
ids and records owned by a different project's cohort fail closed before the claim is persisted.

Unsupported/uncovered material is persisted for inspection rather than discarded, but the
artifact is labelled an unverified hypothesis draft and cannot satisfy act/verify or finish
gates. Council/report UI and Markdown/JSON exports retain posture and refs.

## Canonical project health and recovery

`project_health(project_id)` is the single read model used by MCP, CLI, the Jobs list, the
project header and `/runs`. It projects only persisted structures: the plan frontier, run journal,
issued/completed dispatches, critic rounds, Product Understanding versions, claim envelopes and
evidence references. It never treats long prose, a provider label, or a generic host error as proof.

The projection distinguishes `running`, `stalled`, engine-`finished`, and `unverified` output. It
also names the first unmet invariant, the last successful operation, every repairable integrity
finding, a safe next action and a redacted `sltrace_*` support reference. The normal project canvas
keeps the established run chip and a human-readable state; these support-grade values appear only
after explicitly opening **Technical diagnostics** in that chip or in `/runs`. Recovery signals keep
unknowns explicit: Core cannot prove that an external host disconnected, cannot inspect an external
provider's hidden prompt/reasoning/retry loop, and cannot project the Cloud audit ledger. Cloud may
join the returned project/run/operation query to its tenant-bound local replay API.

At that Cloud boundary, a valid W3C `traceparent` is preserved and a unique tool span is returned in
the response. Without propagated context, each request remains its own honest PostHog interaction
trace; the governed run groups those traces as `$ai_session_id`, and run/project correlation is also
the MCP conversation rather than a fabricated protocol session. Exported identifiers are
workspace-HMAC scoped, so Sonaloop spans nest without exposing raw ids, but independently ingested
raw OpenTelemetry spans do not automatically join them. None of this expands visibility into the
external model host.

`resume_project_run(project_id, run_id, operation_id?)` accepts one explicit active run. It returns
the existing journal's `run_step(run_id)` continuation and cannot create, reopen, or finish a run.
Multiple active runs fail into explicit selection rather than a guessed default. A completed
dispatch receipt is exposed as `retry_result=available`; an issued dispatch without a checkpoint is
`dispatch=incomplete`.

Project cleanup is non-destructive by default:

- `supersede_project(new_id, old_id, operation_id, reason)` records explicit old→new lineage, marks
  the predecessor `superseded`, and preserves all artifacts. Similar titles are never a match rule.
- `archive_project(project_id, operation_id, reason)` preserves the whole record and rejects active
  runs. Deletion remains a separate, explicit destructive operation.

Both writes are retry-safe under their operation id. The inspector renders lineage but does not
recommend a canonical record unless that relationship was explicitly persisted.

## Stable failure codes

Important codes include `DISPATCH_TOKEN_REQUIRED`, `UNKNOWN_DISPATCH_TOKEN`,
`DISPATCH_SCOPE_MISMATCH`, `DISPATCH_KEY_CONFLICT`, `DISPATCH_OUTPUT_CONFLICT`,
`PRODUCT_UNDERSTANDING_REQUIRED`, `ABSENCE_VERIFICATION_REQUIRED`,
`INVENTORY_EVIDENCE_REQUIRED`, `CLAIM_EVIDENCE_REQUIRED`,
`OBSERVATION_EVIDENCE_REQUIRED`, `OBSERVATION_ANCHOR_REQUIRED`, and
`REACTION_EVIDENCE_UNMET`. Remote-stimulus failures include
`REMOTE_WORKSPACE_SCOPE_REQUIRED`, `REMOTE_ASSET_IDEMPOTENCY_CONFLICT`,
`REMOTE_ASSET_SCANNER_REQUIRED`, `REMOTE_ASSET_REPLAY_SCAN_INSUFFICIENT`,
`FLOW_MANIFEST_REVISION_MISMATCH`, `STIMULUS_MANIFEST_VERSION_MISMATCH`,
`PRODUCT_REVISION_MISMATCH`, and `STIMULUS_COVERAGE_INCOMPLETE`. Reference-resolution
failures include `CROSS_PROJECT_EVIDENCE` and `MEMORY_REF_UNRESOLVED`.
Cohort-specific failures include
`COHORT_PREFLIGHT_REQUIRED`, `BAD_COHORT_REPRESENTATION`,
`COHORT_SELECTION_RATIONALE_REQUIRED`, `BAD_SEMANTIC_FEATURE`,
`SEMANTIC_INPUT_MISMATCH`, and `COHORT_OVERRIDE_RATIONALE_REQUIRED`.

## Compatibility and tenancy

- Legacy/no-operation projects remain on the explicit `legacy` provenance path.
- A strict project outside an active run may still be authored deliberately and is stamped
  `outside_run`; it is never misrepresented as governed-run output.
- Dispatch tokens do not grant workspace access. SQLite partitioning and Postgres RLS scope
  project/run/evidence lookups; cross-workspace token use resolves no writable dispatch.
