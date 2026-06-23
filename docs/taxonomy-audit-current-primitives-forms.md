# Taxonomy audit - current primitives, forms and hardcoded formats

Status: baseline audit, 2026-06-16

This audit maps the current Sonaloop objects to the intended
`family -> primitive -> form -> protocol/schema/renderer` model. It is a
stabilization document before moving the implementation to a registry.

The important rule is narrow:

- A **primitive** is a stable Library object users learn and navigate.
- A **form** is a concrete protocol or format of that primitive.
- An **alias** is a compatibility/storage/API value that should resolve to a form.
- A **parameter** is a property of a form, not a new form.
- A **status** is lifecycle state, not a form.
- A **relationship** is graph trace data between objects, not a primitive.

## Current inventory

| Current object or value | Current owner | Current behavior | Target classification | Migration target | Backward compatibility |
| --- | --- | --- | --- | --- | --- |
| `open_question` | `web/_primitive_taxonomy.py`, project plan/open question rows | Library primitive in the frame family | Primitive: `frame/question`; form: `open_question` or `how_might_we` | Registry primitive `question` with form aliases | Keep stored `open_question` rows and URLs that call the tab "Open questions" |
| `hypothesis` | hypotheses service and Library | Falsifiable bet with metric and expected direction/value | Primitive: `frame/hypothesis`; form: `hypothesis` | Registry primitive `hypothesis` | Keep statuses `open`, `validated`, `refuted`, `inconclusive`, `dropped` |
| `url_artifact` / reference rows | artifact/reference service, Library, artifact ingestion | URLs shown as "references"; `kind` currently chooses website/prototype/variant | Primitive: `material/reference` | Forms `web_reference`, `prototype_reference`, `variant_reference` | Keep `kind=url`, `kind=prototype`, `kind=variant` and old URL routes |
| `website` | `url_artifact.kind` UI subtype | Reference to a website/page | Form alias | `reference/web_reference` | Keep filter label for old rows |
| `external_prototype` | `url_artifact.kind == prototype` | External prototype link, currently shown beside references | Form alias | `reference/prototype_reference` | Keep stored `kind=prototype` |
| `ab_variant` | `url_artifact.kind == variant` | One labelled side of a comparison, incorrectly easy to read as a primitive | Form alias plus variant parameter | `reference/variant_reference`; `label=A/B/...` stays parameter | Keep stored variants and A/B labels |
| `asset` | project assets service and Library | Attached files/images/screenshots/documents | Primitive: `material/asset` | Forms `image`, `screenshot`, `document`, `file` | Keep `kind` values and `direction` |
| `direction` on assets | project assets | Distinguishes evidence-in from deliverable-out | Parameter | `asset.direction` | Must not become a form |
| `prototype` | prototype service, Library, suggestions artifact types | Runnable or registered test material | Primitive: `material/prototype` | Forms from artifact registry: `app`, `flow`, `dashboard`, `cards`, `comparison`, `model`, `journey` | Keep existing prototype records and IDs |
| `lofi`, `midfi`, `hifi` | prototype `fidelity`, Library subtype today | Fidelity labels are rendered as prototype subtypes | Parameter | `prototype.fidelity` | Keep filters/chips as fidelity, not forms |
| `flow` | flow walkthrough service, old graph/UI language | Historically looked like a standalone thing; now should be material for sessions or a prototype form | Prototype form or session stimulus, not a primitive | `prototype/flow` or `session.walkthrough` subject | Keep `subject.kind=flow` for old sessions |
| `council` | council service, Library, council pages | Moderated persona answers over questions/options/proposals | Primitive: `ask/council` | Forms below | Keep `CouncilSession` storage shape |
| `discovery` | `services.council_mode` | Base council without proposal/votes | Form alias | `council/open_discussion` | Keep mode chips and filters until migrated |
| `evaluation` | `services.council_mode` | Proposal reaction without hard vote | Form alias | `council/proposal_reaction` | Keep mode chips and filters until migrated |
| `decision` council mode | `services.council_mode` | Proposal plus vote stances | Form alias | `council/vote` | Do not confuse with Decision primitive |
| `head_to_head` | `_head_to_head.py`, council block | Labelled option comparison with deterministic preference tally | Form alias | `council/option_comparison` | Keep `rec["head_to_head"]` block and MCP wrappers |
| `red_team` | `_red_team.py`, council block | Falsification council with objections and severity | Form alias | `council/objection_review` | Keep `rec["red_team"]` block and MCP wrappers |
| `price_ladder` | `_pricing.py`, council block | Price sensitivity over fixed price points | Form alias | `council/ladder_review` | Keep `rec["price_ladder"]` block and MCP wrappers |
| `ideation` | `_ideation.py`, council block | Structured idea generation/review | Form alias | `council/idea_review` | Keep `rec["ideation"]` block and MCP wrappers |
| `survey` | survey service, Library | Structured questionnaire | Primitive: `ask/survey` | Forms `choice`, `scale`, `text`, `ranking` | Keep survey rows and question payloads |
| `single_survey`, `multi_survey`, `scale_survey`, `text_survey` | `web/_primitive_taxonomy.py` derives from dominant question kind | UI subtypes today | Form aliases | `survey/choice`, `survey/scale`, `survey/text` | Keep old subtype filters as aliases |
| `questions.kind` on surveys | survey schema | Question-level format | Form component | Registry question schema inside survey form | Keep current `single`, `multi`, `scale`, `text` values |
| `session` | usability/prototype session services, Library | Observed or authored run against material | Primitive: `test/session` | Forms `walkthrough`, `prototype_use`, `live_use`, `variant_test` | Keep session rows and subject payloads |
| `walkthrough_session` | `subject.kind == flow` | Screen/flow walkthrough | Form alias | `session/walkthrough` | Keep `subject.kind=flow` |
| `prototype_session` | `subject.kind == prototype` and prototype-session service | Session against stored prototype | Form alias | `session/prototype_use` | Keep existing prototype session records |
| `live_session` | `subject.kind == live_url` | Session against live URL/owned surface | Form alias | `session/live_use` | Keep existing live session subject shape |
| `note` | note service, Library | Lightweight captured signal/concept | Primitive: `capture/note` | Forms `observation`, `insight`, `idea`, `concept` | Keep note rows and `data` |
| `observation_note` | taxonomy fallback | Free observation/signal | Form alias | `note/observation` | Keep as display alias |
| `concept_note` | note data with prototype intent | Solution/concept note | Form alias | `note/concept` | Keep `data.prototype_id`, `prototype_ids`, `artifact_kind` |
| `synthesis` | synthesis/report service, Library | Analysis record and report backing object | Primitive: `conclude/synthesis` | Form `synthesis` or `brief` | Keep synthesis IDs and exports |
| `report` | web report surface and Library alias | User-facing report presentation of synthesis content | Primitive or presentation of synthesis, currently separate in UI | Registry must decide `report` primitive vs `synthesis/report` form before migration | Keep Library "Reports" and exported report URLs |
| `decision` primitive | decision service, Library | Evidence-backed commitment | Primitive: `conclude/decision` | Form `decision` | Keep statuses `proposed`, `adopted`, `superseded` |
| `section` | composable graph, methodology phase overlays | Grouping/overlay, not evidence content | Primitive: `structure/section` | Forms or tags `phase`, `theme`, `group` | Keep section kinds open |
| `edge` / trace relation | `project_trace.py`, graph/list relation overlays | Relationship between records | Primitive: `structure/edge` only for graph tooling; not a Library row | Relationship types `derived_from`, `based_on`, `tested_in`, `uses_material`, `refines`, `informs`, etc. | Keep existing trace derivation and graph links |

## Hardcoded form-like branches

These branches currently behave like format registries even though they are
implemented as Python conditionals.

| Branch | Owner ticket | Migration target |
| --- | --- | --- |
| `web/_primitive_taxonomy.py`: `PRIMITIVES`, `SUBTYPE_DOCS`, `subtype_value` | `taxonomy-registry-schema`, `taxonomy-library-registry-rendering` | A data-backed taxonomy registry consumed by Library, graph rows and docs |
| Library row builders and subtype filters | `taxonomy-library-registry-rendering` | Render primitive/form labels, purpose text, icon and color from registry |
| `services.council_mode` and `web/pages/councils.py` | `taxonomy-council-form-registry` | Council form registry with aliases for discovery/evaluation/decision |
| `_head_to_head.py` | `taxonomy-council-form-registry` | `council/option_comparison` with deterministic preference aggregation |
| `_red_team.py` | `taxonomy-council-form-registry` | `council/objection_review` with theme/severity aggregation |
| `_pricing.py` | `taxonomy-council-form-registry` | `council/ladder_review` with price ladder schema |
| `_ideation.py` | `taxonomy-council-form-registry` | `council/idea_review` with idea schema |
| `record_survey` and survey result aggregation | `taxonomy-survey-forms` | Survey form registry and question-kind schema |
| `_flows.py`, flow walkthrough tools | `taxonomy-session-test-forms`, `taxonomy-material-boundaries` | Flow becomes prototype/material form or session walkthrough subject, not a primitive |
| `_usability_sessions.py` | `taxonomy-session-test-forms` | `session/walkthrough`, `session/prototype_use`, `session/live_use`, `session/variant_test` |
| `_engines.py` prototype session writer | `taxonomy-session-test-forms` | Verified `session/prototype_use` form |
| Note data heuristics in taxonomy | `taxonomy-note-conclude-forms` | Explicit note forms: observation, insight, idea, concept |
| `suggestions/artifact_types.json` | `taxonomy-material-boundaries` | Prototype/material form registry source |
| `suggestions/edge_types.json` and `project_trace.py` | trace follow-up tickets, then registry | Relationship-type registry, separate from primitive/form registry |

## Values that must not become forms

The following values are meaningful, but they should remain orthogonal
parameters, statuses or display choices:

- A/B labels (`A`, `B`, `C`, ...): variant identifiers, not forms.
- Lifecycle states (`open`, `validated`, `adopted`, `completed`, `done`, etc.):
  statuses, not forms.
- Prototype fidelity (`lofi`, `midfi`, `hifi`): fidelity parameter, not a form.
- Asset direction (`evidence`, `deliverable`, incoming/outgoing): direction
  parameter, not a form.
- Council stance modes, vote labels and objection severity: protocol fields, not
  primitive/form names.
- Persona/project/section membership: graph membership, not form.
- Methodology phase names (`Discover`, `Define`, `Develop`, `Deliver`) and
  custom section titles: methodology/section labels, not global forms.
- Domain names such as "TeamPulse", "handover", "frontline" or a customer's
  industry: content labels, not taxonomy.
- UI renderer choices such as list, graph, chip, icon or hover line: display
  decisions, not taxonomy.

## Backward compatibility requirements

The registry migration must preserve these existing data and API contracts:

- Existing storage fields remain readable: `url_artifact.kind`,
  `CouncilSession.mode`, `head_to_head`, `red_team`, `price_ladder`, `ideation`,
  `prototype.fidelity`, session `subject.kind`, survey `questions.kind`,
  note `data`, asset `kind` and asset `direction`.
- MCP and CLI tools remain stable wrappers. Specialized tools such as
  `record_head_to_head`, `record_red_team`, `record_price_ladder`,
  `record_prototype_session` and `define_flow` may map to registry forms
  internally, but their tool names and payloads must continue to work.
- Existing Library filters and URLs that name old subtypes continue to resolve as
  aliases during migration.
- Example projects, onboarding tour content, exported reports and graph/list
  views keep rendering old rows without losing trace relationships.
- The registry may add new forms, but unknown LLM-authored values must not mint
  new primitives. They should resolve to an explicit custom form path only after
  registry validation.

## Immediate implementation sequence

1. Add the registry schema and load a data file that represents the target model.
2. Teach the existing taxonomy module to read from the registry while preserving
   its current public helpers.
3. Move Library rendering and subtype filters onto the registry.
4. Move material boundaries first, especially reference/prototype/variant and
   prototype fidelity versus prototype form.
5. Move council, survey and session formats onto form registries with aliases.
6. Add validation so LLM-authored or service-authored values cannot silently
   create new primitives or misleading subtypes.
