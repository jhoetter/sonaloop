# Persona creation, memory and deletion

A persona is not research-ready merely because its profile sounds detailed. Sonaloop keeps
three states distinct:

1. **Profile and SOUL** describe identity, context, goals, constraints, relationships and voice.
2. **Grounding** links claims to independent real material.
3. **Memory** is accumulated continuity: dated ordinary events, facts, unresolved loops,
   consolidation and digests that existed before the current product stimulus.

## Creation paths

The curated catalog remains preferred when it contains a fitting lived persona. Custom creation
uses the same `record_persona` service from MCP, CLI and the detailed `/personas/new` UI. The web
form captures source facts; it does not generate simulated biography or mark the persona ready.

`persona_readiness(persona_id)` is a deterministic structural diagnostic over profile
completeness, grounding, memory volume, continuity and stored capabilities. Its score is an
inspection aid, not behavioral validity and not a replacement for Cohort Integrity.
The `ready` label is deliberately stricter than the numeric score: it requires a specific profile,
independent evidence, authored capabilities, at least eight lived events, four consolidated facts,
three daily summaries and one reflection. A pile of unprocessed events cannot pass as deep memory.

For a thin custom persona, call `brief_persona_memory_onboarding(persona_id, days=28)`. The brief
first routes the earliest structural gap to profile revision, evidence attachment or capability
authoring. It then requires an agent to plan the period, author sampled mundane days from the
loaded SOUL, persist them, consolidate deltas, create a digest, evaluate anomalies/continuity and
re-check readiness. Product-task material must not be written backwards into pre-project memory.

## Voice authenticity

Every persona response must load `prepare_persona_agent_context` and stay in demonstrated
first-person language. Research labels such as “findability problem”, “information architecture”
or “top task” belong in analyst synthesis unless that persona naturally uses them. A session
separates the persona's immediate thought from observed action/state and later researcher analysis.

## Destructive boundary

MCP deletion is two-step and state-bound:

1. `persona_deletion_impact(persona_id)` returns affected projects, personal records to remove,
   historical artifacts that will remain and a short-lived confirmation token.
2. `delete_persona(persona_id, confirmation_token)` succeeds only while that impact is unchanged.

Deletion removes the profile, SOUL, personal memory/evidence and avatar and detaches the id from
active project cohorts. Historical councils, usability sessions and prototype sessions remain
immutable research evidence. A linked active research run blocks deletion on every surface. The web
UI renders the same impact before requiring the display name.
