# Design delivery: PowerPoint masters and provider-neutral MCP hand-offs

Sonaloop has two separate design-delivery boundaries:

1. a workspace-owned PowerPoint master controls editable `.pptx` exports; and
2. `get_design_handoff` projects research evidence into a bounded, destination-neutral
   structure that another design, canvas, code, or document MCP can consume.

Neither path gives Sonaloop access to a customer's destination design account.

## Customer result surface

Cloud workspace members use a result-first job projection. Once a durable report,
outcome, synthesis, prototype, or deliverable exists, the job reads **Result ready** even
when the underlying autonomous run has paused or expired. The normal customer surface
does not expose the global runs/attention widget, run journal route, run chip, plan setup,
or engine-health vocabulary. It shows results first and keeps the deeper research outline
collapsed but available.

This projection does not alter the plan/run source of truth. Owners/operators retain the
technical run surface for recovery and audit; customer roles cannot access `/runs` or
`/api/runs`. A real missing user choice still appears as **Input required** because it is
actionable for the customer. A useful result is never relabeled as broken merely because
the engine had more internal work queued.

## PowerPoint master contract

Cloud workspace owners upload a `.pptx` under **Workspace → Templates**. The upload
boundary accepts at most 24 MB, requires a 16:9 canvas, and rejects macros, embedded/OLE
objects, ActiveX, external relationships, path traversal, and expanded packages above the
safe limit. Concrete slide instances are removed before durable storage. Theme, slide
masters, layouts, placeholders, page geometry, and document properties remain.

The stored asset retains two hashes: the immutable source upload hash used by the
workspace reference and a stored hash for the sanitized zero-slide package. Metadata
records the source/stored sizes, discarded slide count, layout names, placeholder types
and geometry, theme colors/fonts, a semantic palette, inferred roles, and a compatibility
summary. The normal workspace UI reduces this to **ready** or **limited** plus the supported
slide purposes; the detailed profile stays in the advanced surface and export provenance.

At export, `sonaloop._pptx_master.layout_for_slide` maps generated slide kinds onto a
small semantic role vocabulary derived first from multilingual layout names and then,
for agency-specific or opaque names, from portable placeholder structure:

| Generated kind | Preferred master role |
| --- | --- |
| `cover`, `title` | `cover` |
| `agenda` | `agenda`, then `content` |
| `section`, `canvas-section` | `section` |
| `comparison`, `charts` | `two_column`, then `content` |
| `image` | `image`, then `content` |
| `closing` | `closing`, then `section`/`cover` |
| all other report slides | `content`, `two_column`, or `image` |

Native title, subtitle, body, and picture placeholders receive report content wherever
the selected layout provides them. Generated editable content is fitted to the layout's
content grid. Inherited bullets are disabled when the report already supplies numbering.
Missing roles fall back through the compatible roles above and finally to the blank or
emptiest layout.

When a customer master is active, it owns layout backgrounds, fixed artwork, theme-font
inheritance, and color language. Sonaloop derives the editable chart/card palette from the
master theme and actual layout artwork; Cloud does not recolor it with the workspace web
palette. The generated Sonaloop canvas, logo, footer, and forced Geist/Geist Mono font
names are suppressed. Each export records a content-free QA result covering exact master
part retention, layout use, filled placeholders, slide bounds, explicit font overrides,
and colors outside the derived master palette.

## Design hand-off contract

`get_design_handoff(project_id, synthesis_id?, prototype_id?, max_findings=30,
max_voices=24)` is a read-only MCP tool. It returns
`schema="sonaloop.design_handoff.v1"` with:

- project goal, methodology, selected convergence syntheses, and the latest project report;
- compact cohort context;
- authored findings and persona voices with stable evidence refs and claim posture;
- open questions, behavioral predictions, and decision records;
- workspace brand, color, typography, layout, and chart tokens from the active runtime
  design-system snapshot;
- existing concept notes, remote/local prototype metadata, ordered flows, asset handles,
  and bounded usability-session outcomes; and
- a destination contract with a generic sequence and the optional
  `register_remote_prototype` callback for an interactive result URL.

Strings, collections, nesting, findings, voices, assets, reports, flows, and sessions are
bounded before they reach the MCP result. Local filesystem paths, run commands, and
destination credentials are never included. Image/screenshot entries carry an exact
`view_asset(project_id, asset_id)` call; documents carry `get_asset`. Every request passes
the substrate access-guard seam, so Cloud RLS and active-workspace scope apply before any
project data is projected.

### Multi-MCP usage

A host may connect Sonaloop and Figma (or another destination) independently:

1. call `get_design_handoff` for the Sonaloop project;
2. fetch only the required visual assets through the returned Sonaloop calls;
3. create or update the artifact through the separately connected destination MCP;
4. keep evidence refs and unresolved questions visible in the design rationale; and
5. if the destination yields a shareable interactive URL, register it as a remote
   prototype and run normal persona/usability validation.

Figma file- or library-scoped authorization therefore stays between the user, host, and
Figma MCP. Sonaloop never needs a direct Figma integration or a workspace-wide Figma token.
