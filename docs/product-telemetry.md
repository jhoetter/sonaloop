# Product telemetry service

Sonaloop Core exposes a provider-neutral product-event seam in
`sonaloop.telemetry`. Product functions emit semantic events after a successful read or
write; they do not import PostHog, know an API key, or perform network I/O. An installed
deployment registers one or more named sinks. Open Core without a request-bound actor and
workspace treats capture as a no-op.

## Contract

`capture_product_event()` accepts:

- a lowercase snake-case event name;
- optional project and typed subject identifiers;
- at most 32 bounded structural properties; and
- an optional stable idempotency key.

The actor and workspace always come from server-owned request context. Callers cannot
supply them. Property names that could become a content channel (`text`, `title`, `query`,
`prompt`, `email`, `url`, and similar) are rejected, as are nested objects and unbounded
strings/lists. Entity identifiers use dedicated fields so a hosted sink can pseudonymize
them before persistence.

The sink registry is replaceable by name. A sink exception is logged and returned as a
failed sink, but never changes the product operation. A sink may return a receipt for tests
and trusted integration code; domain services do not depend on provider response shapes.

## Current semantic coverage

The central Cloud render boundary records jobs, job details, personas, councils, sessions,
prototypes, surveys and report/synthesis artifacts only after a successful authenticated
HTML response. It collapses repeated render representations into a five-minute window.
Command-palette searches record only a length bucket and result count, never the term.

Core write boundaries record successful project create/update/delete, persona create/update/delete,
council and synthesis recording, survey save/response import, prototype registration/delete,
usability/prototype sessions, asset attach/remove, note and section changes, and run start/finish.
Retry-safe creates and sessions use their durable resource/operation key; an idempotent replay does
not invent another success.

## Canonical questions

Keep product questions independent of the current analytics vendor. The initial event contract can
answer, for example:

| Product question | Semantic evidence |
| --- | --- |
| Did a creator return after automation finished? | `run_finished` followed by `job_viewed` for the same pseudonymous project with `viewer_is_job_creator=true`. |
| Where does a research job activate? | Funnel `job_created` → `run_started` → one or more `session_recorded`/`council_recorded` → `run_finished`. |
| Are outputs actually inspected? | Detail-view events (`session_viewed`, `artifact_viewed`, `prototype_viewed`, etc.) after their corresponding record event. |
| Does search help people recover an item? | `search_used` by `surface`, query-length bucket and zero/non-zero result count, followed by a detail view. |
| Are runs producing grounded usage evidence? | `session_recorded` grouped by `grounded`, `visual_trace` and fidelity. |
| Which cohort sizes reach completion? | `persona_count` on `job_created`/`job_viewed`, joined to `run_finished` by pseudonymous project. |

These recipes are sequence/correlation definitions, not extra event names. They remain valid if the
outbox target changes from PostHog to another product-analytics system.

## Hosted adapter

Sonaloop Cloud registers `cloud_product_telemetry`. It validates a per-event property
allowlist, resolves the subject inside the active tenant, HMAC-pseudonymizes viewer,
workspace, project and subject identifiers, and writes an immutable projection plus outbox
receipt. It never calls a provider on the request path.

PostHog is the first outbox exporter, not the service contract. A future exporter replaces
the registered sink/export target without changing product functions or identity semantics.
The historical HMAC domain label remains frozen so an adapter refactor cannot split existing
viewer/workspace identities.

PostHog receives `sonaloop_<event>` names, `$process_person_profile=false`, structural
properties and pseudonyms. The exporter revalidates the wire shape before capture. Delivery
uses the existing retry, lease, dead-letter and retention machinery; the tenant-local outbox
remains the delivery authority when PostHog is unavailable.

## Adding an event

1. Name a user-meaningful completed action or successful view, not an implementation detail.
2. Add the event and its closed property keys to the Cloud allowlist.
3. Emit it at the authoritative service/render boundary after success.
4. Use counts, booleans and closed buckets. Never include authored research material.
5. Add tests for retries/deduplication, tenant isolation, pseudonymization and absence of raw
   identifiers/content.

This event model is intended to answer funnels and adoption questions such as: which job
states are revisited, whether a creator returns after completion, which artifact types are
actually opened, where real sessions exist, and which workflows reach a finished run. It is
not behavioral proof: a render means the server delivered a view, not that a human read or
understood it.
