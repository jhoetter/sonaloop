# Artifact inventory and naming

Sonaloop has several real primitives that users may casually call "artifacts".
Do not collapse them into one concept in the UI or documentation:

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

The Library must stay a complete cross-project browser for these primitives.
When adding a new project-scoped primitive, update the presence registry,
Library tab/row/detail route, palette search registry, tour showcase coverage
and the onboarding example fixture together.
