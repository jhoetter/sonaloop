# Provider qualification contract

Sonaloop qualifies model/provider adapters with one invariant, offline-replayable harness. The
harness measures whether an adapter can operate the product contract; it never changes evidence or
completion rules to make a weaker provider pass.

Implementation: [`sonaloop/qualification.py`](../sonaloop/qualification.py). Packaged fixtures live
under `sonaloop/qualification_fixtures/`. Focused tests are in
`tests/test_provider_qualification.py`.

## What is held constant

`qualification_contract(fixture_id)` emits a canonical adapter input and a SHA-256 digest. For a
given fixture revision every provider receives byte-equivalent:

- system/task context;
- synthetic assets and their content;
- chronology and logical-request boundaries;
- the tool contract derived from the current Core service signatures;
- run, critic and tool-call budgets; and
- fixed pass thresholds.

The adapter never receives the fixture's private `expected` or correction block. Its returned
`contract_digest` must match the issued digest. A mismatch fails before any Core mutation.

The bundled cases contain only synthetic text and opaque fixture identities:

- `shkb-retry-chronology-v1`: request A plus three resumes, followed by distinct request B. The
  correct result is exactly two projects and two runs, not ten.
- `fink-false-absence-circular-persona-v1`: an untested capability must remain `unknown`; a later
  admitted observation appends an `observed_present` correction with lineage. Product-shaped
  profile claims first trigger the privacy-safe Cohort Integrity fixture. The adapter must replace
  them with the fixture's deep independent cohort; ordinary skepticism/indifference must survive.

## Adapter and result schemas

An adapter implements the synchronous library seam:

```python
class MyAdapter:
    def run_case(self, contract: dict) -> dict:
        # No scorer expectations are present in contract.
        return submission  # sonaloop.provider_qualification.submission.v1
```

The submission records provider/model/version/date, surface visibility, observable metrics and the
provider's protocol decisions. `RecordedQualificationAdapter` reads the same schema from JSON, so CI
and incident regressions make no live provider calls.

Results are versioned as:

- `sonaloop.provider_qualification.case_result.v1`; and
- `sonaloop.provider_qualification.report.v1`.

Public reports contain only synthetic aggregate evidence and hashed ephemeral object references.
They report completion, grounded claim posture, unsupported claims, retries, tool errors, latency,
tokens and cost.

## Real Core is the oracle

The harness executes adapter decisions through the actual public services: `start_project`,
`start_run`, `run_step`, stimulus admission, `record_product_understanding`, dispatch-bound frame and
council writes, `record_judgment`, `record_synthesis`, and the two independent critic rounds. Each
case runs in a temporary SQLite database and temporary asset partition, which are erased afterward.

Scoring then reads the persisted project, plan, Product Understanding history, councils, syntheses,
run journal, dispatch receipts and critic reports. It does not accept adapter claims such as
"evidence linked" or "run complete" as truth.

The ten deterministic checks all have a fixed threshold of `1.0`:

1. methodology resolution;
2. duplicate suppression;
3. governed state-machine compliance;
4. Product Understanding plus admitted stimulus;
5. versioned Cohort Integrity with deep independent context, a countervoice, and no accepted
   circular override (the countervoice must be quote/ref-grounded in pre-project persona context);
6. false-absence falsification and revision lineage;
7. explicit, supported claim posture;
8. task/journal/gate trace links;
9. two distinct passing critic rounds and engine-owned completion; and
10. skeptical and indifferent output coverage.

Every hard check must pass. Per-provider thresholds are not accepted.

The submission must declare `protocol.cohort_strategy`. `reselect_independent` exercises the
server-required remediation path and may pass. `override_circular` intentionally exercises the
auditable limitation path, but remains a hard provider-qualification failure: an override can make
an exceptional production run inspectable, never certify a provider.

## Semantic review cannot buy a contract pass

Deterministic checks are necessary but do not prove that a voice tagged `skeptical` is semantically
skeptical. Qualification therefore also requires a calibrated human or calibrated-judge review on
four fixed 0–5 dimensions: semantic stance fidelity, product-inventory accuracy, circularity
resistance and evidence use. Every dimension must score at least 4.

The combined score is the minimum of deterministic and semantic scores. A missing review produces
`review_required`; a failed hard check produces `failed_contract` regardless of review. Routing may
select a stronger hosted model or request human review, but `contract_gates_relaxed` is always false.

## Hosted versus external MCP visibility

Hosted adapters must report observed generation/host-turn visibility and numeric token/cost fields.
External MCP submissions must declare both as `unavailable_external_host`; token and cost values must
be null. Fabricating them is a schema error. External reports list the blind spots explicitly:

- host/provider turns and system prompt;
- hidden reasoning;
- retries that happen before an MCP request;
- provider-owned permission dialogs; and
- generation tokens and cost.

External clients are still scored on everything Sonaloop can actually observe at its tool boundary.

Cloud content observability is an independent qualification gate, never evidence of model quality.
Metadata/digests are the default. Capturing bounded Remote-MCP content requires the Cloud deployment
switch, a persisted owner-approved `mcp_content_capture` workspace purpose and explicit call or
persisted front-door job consent. PostHog export and hosted generation/tool content are separate
workspace purposes with separate deployment switches. Each audit event freezes a strict policy
snapshot; missing/legacy snapshots remain metadata-only and revocation affects all later receipts.
Provider canaries must therefore test default-off, cross-workspace denial, revocation and snapshot
replay in addition to generation/tool structure. They must never enable content merely to make a
weak-model run easier to debug.

## CLI

```bash
# Discover the packaged cases.
uv run sonaloop qualification-fixtures

# Hand this exact digest-bound contract to every adapter.
uv run sonaloop qualification-contract --fixture shkb-retry-chronology-v1

# Compare one or more captured adapters without a network call.
uv run sonaloop qualification-run \
  --submission exports/openai-submission.json \
  --submission exports/mistral-external-submission.json \
  --out exports/provider-qualification.json
```

Production support is declared only after the deterministic suite, repeated hosted staging runs and
freshly reconnected external-client canaries pass. Variance or a newly discovered failure becomes a
new privacy-safe fixture; thresholds do not move.
