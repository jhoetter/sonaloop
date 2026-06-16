# Primitive taxonomy registry schema

Status: contract, 2026-06-16

The primitive taxonomy registry is the machine-readable contract behind the
Library and research graph vocabulary. It does not replace the current UI
helpers yet. Its job is to make the product model explicit enough that later
migrations can render and validate from data instead of hardcoded branches.

The data source is `sonaloop/primitive_taxonomy.json`; the loader and linter are
in `sonaloop/primitive_taxonomy_registry.py`.

## Top-level document

```json
{
  "schema": "sonaloop.primitive_taxonomy.registry",
  "version": 1,
  "custom_form_policy": {},
  "families": [],
  "primitives": [],
  "forms": [],
  "orthogonal_attributes": [],
  "relationship_types": []
}
```

## Families

Families are the high-level learning buckets in the product. They are not
methodology phases and they are not stored content records.

Required fields:

- `id`: lower_snake_case stable id.
- `label`: display label.
- `description`: one-sentence purpose.
- `icon`: design-system icon token.

The initial families are `frame`, `material`, `ask`, `test`, `capture`,
`conclude` and `structure`.

## Primitives

A primitive is a stable object users can learn and navigate. It changes rarely.

Required fields:

- `id`: lower_snake_case stable id.
- `family`: one registered family id.
- `label`: display label.
- `description`: one-sentence purpose.
- `icon`: design-system icon token.
- `color`: stable hex color for rows, graph nodes and relationship highlights.

Example:

```json
{
  "id": "council",
  "family": "ask",
  "label": "Council",
  "description": "A moderated persona round.",
  "icon": "councils",
  "color": "#6d5ef0"
}
```

## Forms

A form is a concrete structure of a primitive: protocol, payload schema,
renderers and optional aggregators. A product feature is not a form until it is
registered here or as a validated workspace custom form.

Minimum required fields:

- `id`: lower_snake_case form id, unique within its primitive.
- `primitive`: one registered primitive id.
- `label`: display label.
- `description`: one-sentence purpose.
- `aliases`: compatibility values that resolve to this form.
- `schema`: object contract with `type: "object"` and non-empty `fields`.
- `renderer.library`: renderer template for Library rows, or `none`.
- `renderer.detail`: renderer template for detail pages.
- `protocol`: how the form is run and what it outputs.

Optional fields:

- `parameters`: references to orthogonal attributes such as fidelity or stance.
- `aggregators`: deterministic calculations over the form payload.

Example:

```json
{
  "id": "objection_review",
  "primitive": "council",
  "label": "Objection review",
  "description": "Personas argue blockers and severity to falsify or stress-test an idea.",
  "aliases": ["red_team"],
  "parameters": [{"id": "stance_mode", "attribute": "stance_mode"}],
  "schema": {
    "type": "object",
    "required": ["objections"],
    "fields": {
      "objections": "array",
      "endorsements": "array?",
      "stance": "attribute:stance_mode"
    }
  },
  "renderer": {"library": "row", "detail": "red_team_detail"},
  "protocol": {"kind": "ask", "inputs": ["proposal"], "outputs": ["objections"]},
  "aggregators": [
    {"type": "group_by", "field": "theme"},
    {"type": "max_enum", "field": "severity"}
  ]
}
```

## Aliases

Aliases preserve old product/API names while moving the product to structural
forms. They are resolved only inside their primitive, so `decision` can remain a
Decision primitive form while `council/decision` maps to `council/vote`.

Required compatibility aliases include:

- `council/discovery` -> `council/open_discussion`
- `council/evaluation` -> `council/proposal_reaction`
- `council/decision` -> `council/vote`
- `council/head_to_head` -> `council/option_comparison`
- `council/red_team` -> `council/objection_review`
- `council/price_ladder` -> `council/ladder_review`
- `council/ideation` -> `council/idea_review`
- `url_artifact/website` -> `url_artifact/web_reference`
- `url_artifact/external_prototype` -> `url_artifact/prototype_reference`
- `url_artifact/ab_variant` -> `url_artifact/variant_reference`
- `session/walkthrough_session` -> `session/walkthrough`
- `session/prototype_session` -> `session/prototype_use`
- `session/live_session` -> `session/live_use`

## Orthogonal attributes

Orthogonal attributes are values that should not create combinatorial forms.
They are statuses, parameters or labels.

Examples:

- `prototype_fidelity`: `lofi`, `midfi`, `hifi`
- `asset_direction`: `evidence`, `deliverable`
- `stance_mode`: `against`, `for`, `both`
- `variant_label`: open parameter for `A`, `B`, `C`, ...
- lifecycle statuses such as `survey_status` or `decision_status`
- open domain labels and methodology phase labels

The registry linter requires form parameters to reference a registered
orthogonal attribute.

## Relationships

Relationships are trace edges between nodes. They are not Library primitives in
the normal user sense, but the registry includes an `edge` structure primitive so
graph tooling can validate relationship vocabulary.

Registered relationship types include `derived_from`, `based_on`, `tested_in`,
`uses_material`, `supports`, `contradicts`, `supersedes` and `groups`.

## Examples by family

| Family | Example form | Why it exists |
| --- | --- | --- |
| `frame` | `open_question/open_question` | Captures unresolved research questions. |
| `material` | `url_artifact/web_reference` | Represents a website/page used as material. |
| `ask` | `council/objection_review` | Represents the old `red_team` protocol structurally. |
| `test` | `session/prototype_use` | Represents observed use of a stored prototype. |
| `capture` | `note/observation` | Represents a lightweight captured signal. |
| `conclude` | `decision/decision` | Represents an evidence-backed commitment. |
| `structure` | `edge/derived_from` | Represents a trace relationship between nodes. |

## Unknown and custom forms

The default policy is `reject_unknown`. Unknown LLM-authored values must never
silently create new primitives or forms.

Workspace custom forms are allowed only after registration. A custom form must:

- extend an existing primitive/form;
- declare label, description, schema and renderer templates;
- reference only registered orthogonal attributes;
- use a renderer whose required fields are present in its schema;
- keep aliases scoped to its primitive.

This gives customers room to make their own council or session forms without
letting arbitrary text fragment the Library model.

## Lint contract

`registry_errors()` checks:

- top-level schema/version;
- lower_snake_case and uniqueness for ids and aliases;
- primitive family references;
- form primitive references;
- required form schema, renderer and protocol fields;
- at least one registered form per family;
- parameter references to registered orthogonal attributes;
- edge forms backed by relationship types;
- default custom-form policy is `reject_unknown`.
