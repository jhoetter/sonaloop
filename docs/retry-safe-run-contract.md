# Retry-safe project and run contract

External MCP hosts can lose a response after Sonaloop has committed a write. A host retry must
therefore resume the same logical operation instead of creating another project or journal row.
This contract is shared by Python, MCP and CLI callers.

## Project creation

`start_project(..., operation_id=...)` accepts an optional caller-generated idempotency key. A
client should create one stable key for the user's **create-study intent** and reuse it for every
transport retry of that intent. Replaying identical canonical inputs returns the original project
with `idempotent_replay=true`; it does not emit another `project.created` event. Reusing the key
with different inputs raises `IDEMPOTENCY_CONFLICT` and changes nothing.

The key is scoped by the active store/workspace and may contain 1–200 printable characters. Use an
opaque UUID/hash-like value: it is persisted for audit but is not an authentication secret, so never
put a prompt, email address, token or other sensitive content in it. Omitting it preserves the legacy
behavior: every call creates a new project.

The project-id claim is atomic: concurrent calls cannot overwrite the operation owner, and a
different payload under the same key fails. Project and plan currently live in separate storage
rows, so their initialization is intentionally a **deterministic compare-and-repair protocol**, not
one cross-row transaction. The project moves from `operation_state="creating"` to `"initialized"`;
a retry that finds the former validates the request fingerprint and finishes the same project's
canonical plan. It never creates a replacement shell. In row-tenanted Postgres the deterministic id
and uniqueness constraint are workspace-scoped, so two workspaces may independently use the same
client operation id.

An authenticated server adapter may bind a provider-neutral `sonaloop.request_actor.v1` request
context before project creation. The first physical project insert freezes that bounded snapshot as
optional `created_by` (`kind`, opaque `id`, display `label`, optional `role`/`channel`, and
`captured_at`). It is server-owned context, not a `start_project`/`create_research_project` argument,
and therefore never appears in MCP input schemas. Exact retries and concurrent creators retain the
first atomic winner; later project edits and whole-row upserts cannot replace it. Historical,
unbound and local projects remain honestly unattributed—Sonaloop never guesses a creator from a
later editor, operation id, prompt or tool call. The inspector renders only the frozen display
label, never the opaque actor id.

Before project or plan storage is touched, `methodology` is resolved against the registry. Stable
keys and human display names are accepted, with case, whitespace, `_`, `-` and punctuation treated
as spelling variants. For example, all of these seed `reaction_test`:

```text
reaction_test
Reaction Test
reaction-test
```

An unknown or ambiguous methodology fails without leaving an orphan project or root plan.

When Sonaloop Cloud exposes `begin_research_job`, `methodology="auto"` is the normal front-door
choice. The server ranks **data-authored routing hints from the live methodology registry**; the
adapter contains no framework keyword table. An explicit methodology or Job preset always wins.
A unique candidate must clear its registry-declared score threshold and ambiguity margin. If none
does, or two candidates remain too close, the call returns one short clarification with
`no_mutation=true`; the host asks it once and repeats the call with the exact answer. `freeform`
remains valid only as an explicit choice and is never the automatic fallback.

Every accepted Cloud job stores `methodology_decision.v1` in its ingress record: requested and
resolved value, selection source, deterministic confidence, ranked candidates, matched registry
signals, rationale, and any explicit override of the automatic recommendation. These fields are
routing evidence, not a calibrated probability or a substitute for the governed research gates.

## Initial run creation

`start_run(project_id, operation_id=...)` uses the same contract for the separate run-create
intent. Reuse that key if the initial response is ambiguous; the same project and budget return the
original run with `idempotent_replay=true`. A different project or budget under the same key raises
`RUN_IDEMPOTENCY_CONFLICT`. Once the returned `run_id` is known, resume with
`start_run(project_id, run_id=...)`; do not pass both identities in one call. Legacy calls without
either key may still create a first run, but they cannot create a second active run for the project.

One project has at most one newly created active run. The storage layer claims the project's active
slot and inserts its journal in one transaction, including concurrent calls with different operation
ids or no ids. An identical operation replay and an explicit existing `run_id` resume are checked
before this creation guard and continue to return the original journal. Any other create attempt
raises `ACTIVE_RUN_EXISTS` and names both the existing run id and the exact safe
`start_run(project_id=..., run_id=...)` continuation; clients must not create a replacement. When a
run reaches `finished`, `stopped` or `capped`, its matching claim is released and a later run may be
started.

The claim table is intentionally separate from the append-preserving run journal. On an upgraded
store, it lazily adopts the most recently touched legacy active row and leaves all historical rows
readable; stale claims for terminal/missing rows repair on the next create. This avoids a partial
unique-index migration that would fail merely because an old store already contains several active
rows. Such legacy duplicates remain an explicit recovery/archive concern, but no new `start_run`
call can add another one.

Project lifecycle changes and deletion share the same project-scoped cross-process lock as run
creation. Postgres uses a session advisory lock; SQLite combines a re-entrant process lock with an
OS file lock. `archive_project`, `supersede_project` and `delete_research_project` therefore cannot
race a new active journal onto a closed or vanished project. Archive/supersede require any existing
active run to be explicitly recovered or stopped first. Hard delete is limited to never-started
containers with no run history; once a governed journal exists, preserve the job with archive instead.

For support/recovery surfaces, prefer `resume_project_run(project_id, run_id, operation_id?)`.
It validates that the named run is active and belongs to the project, then returns the existing
`run_step(run_id)` continuation. It never creates a replacement run, reopens a terminal run or
marks a run finished. `project_health(project_id)` supplies that exact call plus the unmet invariant,
last checkpoint and redacted support trace reference.

## Run journal checkpoints

The persisted dispatch claim includes its workspace, project, run, task, cursor,
`expected_output_kind`, a content-free input fingerprint and a single-primary-output contract.
Council and synthesis payloads are fingerprinted before mutation. An identical transport replay
returns the original primitive; an evidence-gate repair before the checkpoint increments the
recorded payload revision, while any changed replay after completion raises
`DISPATCH_OUTPUT_CONFLICT`. A different primary primitive kind raises
`DISPATCH_OUTPUT_KIND_CONFLICT` before that primitive is written.

Primitive persistence, evidence linking and checkpointing are currently a repairable saga over
separately committed records, not one physical database transaction. Token replay repairs a crash
or lost response at each seam without minting another primitive. Do not describe this seam as
atomic until the storage layer supplies a shared transaction boundary.

Every dispatch from `run_step` carries a deterministic `key`. Echo that key into
`checkpoint_step`. The first call appends the lean journal entry; a retry with the same non-empty
key and identical normalized payload is a no-op and returns `deduplicated=true` plus the original
receipt (`cursor`, `step_idx`, `key`). The original cursor is stable even if later steps have since
been appended. Reusing a key with a different payload raises `CHECKPOINT_KEY_CONFLICT` and changes
nothing. Concurrent writers use an atomic compare-and-swap, so distinct checkpoints are both
retained and conflicting same-key payloads cannot race past the check. Callers that omit a key keep
legacy append behavior and are not retry-safe.

Critic dispatches carry their own `operation_id` and `key`. Pass both plus the run id to
`record_completeness_critic`, then bind its returned report id with `record_critic_round`. Retries
return the same report/round. The run derives pass/missing state from that persisted report; one
logical critic response can therefore never masquerade as two independent dry rounds.

## Completion ownership

`finished` is a verified research state, not a user-controlled status label. `finish_run(...,
status="finished")` fails with `RUN_NOT_FINISHABLE` unless all of these are true:

- the plan and result contract are complete;
- organization, terminal conclusion and report hand-off are complete where required;
- the run journal ends in two passing dry completeness-critic rounds; and
- the project contains the corresponding two persisted passing critic reports.

Only `finished`, `stopped` and `capped` are valid terminal statuses. `stopped` and `capped` remain
explicit operational exits. Normal agents should never force a
successful finish: call `run_step`, execute its dispatch, checkpoint it, and repeat until
`run_step` itself returns `kind="done"`.
