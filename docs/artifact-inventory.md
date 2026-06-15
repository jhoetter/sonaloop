# Primitive inventory and naming

Sonaloop has several real primitives that users may casually call "artifacts".
Do not collapse them into one concept in the UI or documentation.

Use three layers:

1. **Primitives** are the stable Library-level entities. They have a clear
   purpose, a route, a detail page and a presence declaration.
2. **Subtypes / formats** refine a primitive without creating a new top-level
   entity. Examples: a council can be a red-team or head-to-head format; a
   reference can be a website, external prototype or A/B variant; a session can
   walk a flow, prototype or live URL.
3. **Methodology `artifact_type` tags** are open planning/build tags used by
   the methodology engine and prototype renderer registry. They are not
   automatically Library primitives.

## Canonical primitives

- **References** (`add_artifact`, stored on `project["artifacts"]`, outline
  kind `url_artifact`): websites, external prototypes and A/B variants placed
  in a council room. They have `/references` and `/references/{id}` surfaces.
  They may carry a captured snapshot, but they are not files.
- **Assets** (`attach_asset`, stored on `project["assets"]`, outline kind
  `asset`): real files such as screenshots, documents, exports and generated
  deliverables. They have `/assets` and `/assets/{id}` surfaces, plus the
  project files lens.
- **Flows** (`define_flow`, stored on `project["flows"]`, outline kind
  `flow`): ordered screenshot assets used for artifact-first walkthroughs.
  They have `/flows` and `/flows/{id}` surfaces and collect sessions.
- **Sessions** (`record_usability_session`, outline kind `session`): replayable
  usage traces against a `flow`, `prototype` or `live_url`. The old fidelity
  label `artifact` means a **screen walkthrough**, not a generic artifact type.
- **Open questions** (`record_open_questions`, outline kind `open_question`):
  first-class research uncertainties with `/open-questions` detail surfaces.

Other Library primitives are councils, surveys, prototypes, hypotheses,
decisions, notes and reports/syntheses. Sections are a structural primitive:
they group existing nodes and can have detail/export surfaces, but they are not
evidence by themselves.

## Product taxonomy

The UI taxonomy is centralized in `sonaloop/web/_primitive_taxonomy.py`:

- primitive family: question, input, interaction, test surface, observation,
  answer or structure;
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
- usability sessions accept subject kinds `flow | prototype | live_url` and
  fidelities `artifact | prototype | live`;
- surveys, hypotheses and decisions reject unknown lifecycle/question/status
  values.

An LLM cannot silently create a new Library primitive by hallucinating a `kind`.
It can still supply a semantically poor subtype value where a service normalizes
or infers, so host instructions and UI labels should use the product taxonomy.

## Product rules

The Library must stay a complete cross-project browser for these primitives.
When adding a new project-scoped primitive, update the presence registry,
Library tab/row/detail route, palette search registry, tour showcase coverage
and the onboarding example fixture together.

Do not expose the word **artifact** as a product primitive. Use:

- **Reference** for captured URLs/external prototype links/A-B variants;
- **Asset** or **File** for uploaded/generated files;
- **Flow** for static screen sequences;
- **Session** for observed use of a flow, prototype or live surface.
