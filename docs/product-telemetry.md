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
- an optional stable workflow trace id (otherwise derived from the project id);
- at most 32 bounded structural properties; and
- an optional stable idempotency key.

The actor and workspace always come from server-owned request context. Callers cannot
supply them. Property names that could become a content channel (`text`, `title`, `query`,
`prompt`, `email`, `url`, and similar) are rejected, as are nested objects and unbounded
strings/lists. Entity identifiers use dedicated fields so a hosted sink can pseudonymize
them before persistence.

`workflow_trace_id` is provider-neutral, content-free and stable for the lifetime of one research
job. It joins job creation, later MCP calls, the governed run, sessions, reports and exports even
though their W3C transport trace ids change per request. Cloud exports only a workspace-HMAC
pseudonym as `sonaloop_workflow_trace_id`; it never sends the raw `sltrace_*` value to PostHog.

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

The persona lifecycle is covered at its semantic boundaries: task context prepared; persona build
started/advanced/completed; day recorded; memory consolidated; digest and semantic critic recorded;
persona voice checked; and a chat-memory proposal approved or rejected. Properties are only states,
counts and booleans (for example `dispatch_kind`, `activity_count`, `passed` and `decision`). Task
text, persona output, continuity notes, source excerpts and critic prose never enter telemetry.

Product-facing adoption edges are semantic events too: custom/catalog persona creation starts,
persona views carry only readiness/memory-depth buckets and evidence presence, report exports carry
format/audience plus default-vs-workspace branding/master sources, design-system publishing and safe
asset uploads carry structural kinds, and prototype registration records whether workspace branding
was inherited. No profile prose, report text, filenames or visual content enters telemetry.

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
| Are thin personas being used or deliberately deepened? | `persona_viewed` readiness and memory-level buckets followed by session/run events; authored memory content is never sent. |
| Where does persona preparation stall? | `persona_build_started` → repeated `persona_build_advanced` by `dispatch_kind` → `persona_build_completed`. |
| Are prepared personas actually used with reproducible context? | `persona_context_prepared` by readiness and capability-gate presence, followed by session/run events. |
| Does the authenticity safeguard catch wording before use? | `persona_voice_checked` grouped by `passed`, issue count and warning-signal count. |
| Is cross-chat continuity curated? | `persona_memory_proposal_reviewed` by approve/reject decision; no chat content is exported. |
| Do people use share-ready output? | `report_exported` by `export_format`, `audience`, `branding_source` and `master_source`. |
| Does workspace branding reach generated work? | `workspace_design_published`/`workspace_design_asset_uploaded` followed by `prototype_registered` or `report_exported` with structural branding-source fields. |

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
