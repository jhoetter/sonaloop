# Primitive inventory and naming

Sonaloop has several real primitives that users may casually call "artifacts".
Do not collapse them into one concept in the UI or documentation.

Use three layers:

1. **Primitives** are the stable Library-level entities. They have a clear
   purpose, a route, a detail page and a presence declaration.
2. **Subtypes / formats** refine a primitive without creating a new top-level
   entity. Examples: a council can be a red-team or head-to-head format; a
   reference can be a website, external prototype or A/B variant; a session can
   run against a screen walkthrough, prototype or live URL.
3. **Methodology `artifact_type` tags** are open planning/build tags used by
   the methodology engine and prototype renderer registry. They are not
   automatically Library primitives.

## Canonical primitives

- **Open questions** (`record_open_questions`, outline kind `open_question`):
  first-class research uncertainties with `/open-questions` detail surfaces.
- **Hypotheses** (`record_hypothesis`, outline kind `hypothesis`): testable
  assumptions with predictions. They are not answers; they are framed bets that
  reality can validate or refute.
- **References** (`add_artifact`, stored on `project["artifacts"]`, outline
  kind `url_artifact`): websites, external prototypes and A/B variants placed
  in a council room. They have `/references` and `/references/{id}` surfaces.
  They may carry a captured snapshot, but they are not files.
- **Assets** (`attach_asset`, stored on `project["assets"]`, outline kind
  `asset`): real files such as screenshots, documents, exports and generated
  deliverables. Assets can flow **in** as evidence or **out** as deliverables.
  They have `/assets` and `/assets/{id}` surfaces, plus the project files lens.
- **Councils** (`record_council`, outline kind `council`): moderated research
  rounds. A mediator asks; personas answer from memory. Formats such as
  red-team, head-to-head, price ladder and ideation are council formats, not
  new primitives.
- **Surveys** (`record_survey`, outline kind `survey`): structured question
  instruments for real responses.
- **Prototypes** (`register_prototype` / `scaffold_prototype`, outline kind
  `prototype`): interactive surfaces personas can actually use.
- **Sessions** (`record_usability_session`, outline kind `session`): replayable
  usage traces against a screen walkthrough, `prototype` or `live_url`.
  `define_flow` stores a reusable screen-walkthrough test script under
  `project["flows"]`, but that script is not a Library primitive; it exists so
  multiple sessions can reuse the same ordered screenshot sequence.
- **Notes** (`create_note`, outline kind `note`): captured signals, observations
  or concepts. They are intentionally lightweight and may later feed councils,
  prototypes or sections.
- **Reports / syntheses** (`record_synthesis`, outline kind `synthesis`):
  analyses that turn evidence into interpretation.
- **Decisions** (`record_decision`, outline kind `decision`): evidence-backed
  commitments about what to do. They are not answers; they are actions justified
  by evidence.
- **Sections** are a structural primitive: they group existing nodes and can
  have detail/export surfaces, but they are not evidence by themselves.

## Product taxonomy

The UI taxonomy is centralized in `sonaloop/web/_primitive_taxonomy.py`.
The Library groups primitives as a user-facing work map:

- **Frame**: open questions and hypotheses — what still needs to be resolved or
  proven.
- **Material**: references and assets — linked or stored material, whether
  evidence in or deliverable out.
- **Ask**: councils and surveys — ways to ask personas or real respondents.
- **Test**: prototypes and sessions — what can be exercised and the recorded
  run through it.
- **Capture**: notes — low-friction signals, observations and concepts.
- **Conclude**: reports and decisions — analysis and commitments.
- **Structure**: sections — grouping, not evidence.

Each primitive also has:

- primitive purpose: one sentence used by the Library to teach the mental model;
- subtype extraction: a bounded, URL-stable facet value derived from the stored
  record.

The taxonomy intentionally reads service records rather than inventing a second
storage model. A subtype never creates a new primitive. A new primitive must be
added to the presence contract and the Library; a new subtype normally only
extends the taxonomy labels and tests.

## Validation boundaries

Most persisted primitive subtypes are bounded by service validators:

- references accept `url | prototype | variant` and normalize unknown kinds to
  `url`;
- assets accept `image | screenshot | document | file`, with kind inferred from
  the filename when omitted or unknown;
- usability sessions accept subject kinds `flow | prototype | live_url`; `flow`
  means an internal screen-walkthrough script, not a product primitive;
- surveys, hypotheses and decisions reject unknown lifecycle/question/status
  values.

An LLM cannot silently create a new Library primitive by hallucinating a `kind`.
It can still supply a semantically poor subtype value where a service normalizes
or infers, so host instructions and UI labels should use the product taxonomy.

## Trace contract for agents

Project trace is the visible input/output graph of a study. It is not inferred
from prose after the fact; agents must write the links while they run the plan.

Every `run_step` / `next_action` dispatch carries:

- `consume_refs`: required upstream evidence or frames to read;
- `optional_context_refs`: useful context that is not required evidence;
- `open_questions`: framed questions that the step is expected to address;
- `expected_output_kind`: the output shape the step is likely to produce;
- `must_link_before_complete`: `true` for `act` and `verify` tasks.

For `act` and `verify` tasks, do this sequence:

1. Author and persist the output primitive: e.g. council, survey, prototype,
   session, synthesis, decision, reference or asset.
2. Call `link_evidence(project_id, task_id, kind, evidence_id)` for every output
   that should count as produced evidence for that task.
3. If a produced item should remain visible but deliberately not feed a gate,
   call `park_evidence(project_id, refs, reason, task_id)` with a concrete
   reason.
4. Only then call `complete_task(project_id, task_id)`.
5. Call `checkpoint_step(run_id, {...})` with `consume_refs`, `produced_refs`,
   `downstream_refs`, `open_questions` and `parked_refs` so the run journal can
   be audited later.

If `complete_task` returns `trace_nudge.code == TRACE_LINK_MISSING`, the task was
completed without non-frame produced evidence linked to the plan. Treat that as a
repair instruction: record or identify the output, call `link_evidence`, or park
it explicitly before continuing the run.

## Product rules

The Library must stay a complete cross-project browser for these primitives.
When adding a new project-scoped primitive, update the presence registry,
Library tab/row/detail route, palette search registry, tour showcase coverage
and the onboarding example fixture together.

Do not expose the word **artifact** as a product primitive. Use:

- **Reference** for captured URLs/external prototype links/A-B variants;
- **Asset** or **File** for uploaded/generated files;
- **Session** for observed use of a screen walkthrough, prototype or live
  surface.
