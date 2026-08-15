# Persona lifecycle: creation, memory, task context and deletion

A persona is not research-ready merely because its profile sounds detailed. Sonaloop keeps
three states distinct:

1. **Profile and SOUL** describe identity, context, goals, constraints, relationships and voice.
2. **Grounding** links claims to independent real material.
3. **Memory** is accumulated synthetic continuity: dated ordinary events, facts, unresolved
   loops, consolidation and digests that existed before the current product stimulus.

Synthetic continuity is useful context, not real-user observation. Every recalled fact or episode
retains `source_kind`, exact `source_refs`, `confidence` and `review_status`. Current recall excludes
superseded facts and archived episodes; `as_of` recall also excludes facts, events, threads, digests
and persona revisions that did not yet exist at the requested date. Embeddings are qualified by
provider and model and are never mixed across vector spaces.

## Creation paths

The curated catalog remains preferred when it contains a fitting lived persona. Custom creation
uses the same `record_persona` service from MCP, CLI and the detailed `/personas/new` UI. The web
form captures source facts; it does not generate simulated biography or mark the persona ready.

`persona_readiness(persona_id)` is a deterministic structural diagnostic over profile
completeness, grounding, memory volume, continuity and stored capabilities. Its score is an
inspection aid, not behavioral validity and not a replacement for Cohort Integrity.
The `ready` label is deliberately stricter than the numeric score: it requires a specific profile,
claim-level grounding in independent evidence, authored capabilities, at least eight simulated lived
events, four consolidated facts, three daily summaries, one reflection, a period digest, a current
green semantic critic and no current severe memory anomaly. A pile of unprocessed events cannot pass.

For a thin custom persona, `begin_persona_build(persona_id, operation_id, days=28)` is the retry-safe
front door. It creates one durable build and returns the exact current dispatch. Execute that
gather/write-back pair and call `persona_build_step(build_id)` until its state-derived dispatch is
`done`. The build covers profile specificity, independent claim grounding, capabilities, a period
plan, sampled mundane days, per-day consolidation, a digest and the persisted semantic critic.
`get_persona_build` and `list_persona_builds` make interrupted builds resumable. The earlier
`brief_persona_memory_onboarding` remains a readable workflow brief.

Product-task material must not be written backwards into pre-project memory. A build without an
independent corpus returns an explicit blocked grounding dispatch; it does not manufacture one.

## Task-specific use and reproducibility

Global readiness does not imply readiness for every assignment.
`persona_task_readiness(persona_id, task, project_id?, as_of?, required_capability?)` combines global
quality with task-relevant memory/grounding, project-cohort membership and the requested interaction
rung. `prepare_persona_for_task` then freezes the exact SOUL-derived context, persona version,
memory cutoff, vector space, capability requirement, loaded refs, limitations and context hash.
`get_persona_context_snapshot` reopens that immutable context later, so a session can be audited
without silently re-running recall against newer memory.

`prepare_persona_agent_context(..., as_of=...)` is the lower-level historical context read. Use the
task snapshot for consequential sessions and reports.

## Voice authenticity

Every persona response must load its task context and stay in demonstrated first-person language.
Research labels such as “findability problem”, “information architecture” or “top task” belong in
analyst synthesis unless that persona naturally uses them. `validate_persona_output` gathers the
exact persona context plus deterministic warning signals; the host authors a four-dimensional
semantic verdict and `record_persona_voice_check` persists only scores, issues, a content hash and an
optional rewrite. Warning phrases are review prompts, never a fake deterministic proof of voice.
A session separates immediate persona thought from observed action/state and researcher analysis.

## Chat continuity is proposed, never learned silently

Persona chat remains host-authored. A completed chat does not mutate identity, lived episodes or
facts. If continuity across separate chats is useful:

1. `brief_memory_from_chat` loads only selected exact turns.
2. `record_memory_proposal` stores a pending, conversation-only summary and notes.
3. `review_memory_proposal(..., approve|reject, reason)` records an explicit decision.
4. Only approved notes are loaded by future chats, under a visible warning that they came from
   synthetic conversation and are neither evidence nor lived experience.

This prevents self-reinforcing persona drift where generated replies become their own grounding.

## Reads, exports and pruning

`get_persona_memory` is a pure read. It renders the current projection in memory and never writes a
file. `export_persona_memory` is the explicit write and is contained inside the active workspace
partition. Pruning archives old raw episodes reversibly; it does not silently destroy them.

## Destructive boundary

Profile edits should use `preview_persona_update`, then `update_persona` with the returned
`expected_updated_at` and a non-empty reason. The preview is side-effect free and includes the exact
field diff, identity/routine risk, linked-project/session/history counts and the history contract.
Changes to name, source description, identity traits, segment, demographics, role or company context
also require its state-bound `confirmation_token`; a changed persona version or changed patch
invalidates that token. Past sessions and frozen task-context snapshots remain unchanged; future
context uses the revised profile. Immutable ids, provenance and runtime counters are not editable.
Identity evolution through lived time still requires an explicit rationale and resolving
fact/digest/event/evidence refs.

MCP deletion is two-step and state-bound:

1. `persona_deletion_impact(persona_id)` returns affected projects, personal records to remove,
   historical artifacts that will remain and a short-lived confirmation token.
2. `delete_persona(persona_id, confirmation_token)` succeeds only while that impact is unchanged.

Deletion removes the profile, SOUL, personal memory/evidence and avatar and detaches the id from
active project cohorts. Historical councils, usability sessions and prototype sessions remain
immutable research evidence. A linked active research run blocks deletion on every surface. The web
UI renders the same impact before requiring the display name.
