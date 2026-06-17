# Taxonomy backcompat and migration

Status: contract, 2026-06-16

The primitive/form registry is canonical for product vocabulary, but existing
stores, URLs and MCP clients keep working. This migration is intentionally
lazy: records are classified at read/render time through registry aliases rather
than destructively rewritten.

## Canonical vs legacy fields

Canonical vocabulary:

- primitive ids in `primitive_taxonomy.json`, for example `council`, `session`,
  `url_artifact`, `survey`, `prototype`, `decision`;
- form ids scoped to a primitive, for example `council/option_comparison`,
  `council/objection_review`, `session/prototype_use`,
  `url_artifact/variant_reference`;
- orthogonal attributes such as `prototype_fidelity`, `survey_status`,
  `decision_status` and `variant_label`.

Legacy/storage fields that remain valid:

- `CouncilSession.mode` values such as `discovery`, `evaluation`, `decision`;
- special council blocks: `head_to_head`, `red_team`, `price_ladder`,
  `ideation`;
- URL material `kind` values such as `url`, `website`, `prototype`, `variant`;
- usability-session `subject.kind` values such as `flow`, `prototype`,
  `live_url`, `variant`;
- legacy `prototype_sessions` rows carrying `prototype_id` instead of a modern
  `subject`;
- old Library filter tokens such as `red_team`, `head_to_head`,
  `ab_variant`, `prototype_session`, `single_survey`.

Alias-only fields:

- old subtype URL values are accepted as stable filter tokens, but they are not
  new forms outside their primitive;
- old format names such as `red_team` are compatibility aliases for canonical
  forms such as `council/objection_review`;
- fidelity values (`lofi`, `midfi`, `hifi`) are parameters, not prototype
  forms.

## Read path

Classification is lazy and registry-backed:

- `services.council_form(row)` maps legacy council modes and special blocks to
  canonical `council/*` forms.
- `services.session_form(row)` maps modern usability sessions and legacy
  `prototype_sessions` rows to canonical `session/*` forms.
- `services.survey_form(row)` maps question structures and old survey subtype
  tokens to canonical `survey/*` forms.
- `web._primitive_taxonomy.subtype_value()` returns the URL-stable old filter
  token where needed, while `subtype_label()` and the form map are generated
  from the registry.

This means old projects render unchanged or with intentional copy improvements:
the Library still accepts old URLs, but detail/tooling can resolve the
canonical form when it needs schema/protocol metadata.

## Write path

New generic writes should prefer canonical forms:

- `record_council_form(project_id, form_id, payload, ...)` validates a
  `council/*` form and stamps `form` plus `form_payload`.
- `list_primitives`, `list_forms`, `get_form` and `suggest_forms` are the read
  APIs for choosing valid forms.

Existing specialized MCP tools remain wrappers:

- `record_head_to_head` -> `council/option_comparison`
- `record_red_team` -> `council/objection_review`
- `record_price_ladder` -> `council/ladder_review`
- `record_council` discovery/evaluation/decision modes ->
  `council/open_discussion`, `council/proposal_reaction`, `council/vote`
- `record_prototype_session` and `record_usability_session` continue to create
  session rows that classify through `session/*`.

They are compatibility APIs, not separate artifact types.

## Local SQLite and cloud/Postgres stores

No storage migration is required for the registry cutover. SQLite and
cloud/Postgres stores can keep existing JSON blobs as-is because the canonical
classification is derived at read time.

If a future release introduces persisted canonical form columns, migrate
additively:

1. Add nullable `primitive_id` / `form_id` columns or JSON metadata.
2. Backfill with the same service classifiers used by the web/MCP read path.
3. Keep alias resolution indefinitely for URL and API compatibility.
4. Never delete legacy blocks (`head_to_head`, `red_team`, `price_ladder`,
   `ideation`) until every public export and old MCP client has a replacement
   contract.

## Regression surface

Compatibility is pinned by tests for:

- registry alias resolution;
- old Library subtype filter URLs;
- specialized MCP tools still recording rows that classify to canonical forms;
- shipped example projects, including image assets, references, sessions,
  reports, decisions and graph/library parity;
- report/export round trips through the existing synthesis/report contracts.
