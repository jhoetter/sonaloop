# Project assets — files, images & screenshots as evidence

The biggest credibility gap is personas reasoning from prompts instead of real
material. Assets close it: any file — a screenshot of your onboarding, a pricing
page capture, an interview note, a PDF — attaches to a research project as
first-class, citable evidence with a stable id. `brief_council` automatically
puts every project asset in the room, so reactions are grounded in what is
actually there.

Terminology: assets are **files**. Council-room websites, external prototype
links and A/B variants are **references** (`add_artifact`, surfaced under
`/references`), not assets. Replayable uses of either are **sessions**.

## Attaching

```bash
# MCP (the natural path — an agent attaches material while it works):
attach_asset(project_id, path="/tmp/onboarding-step2.png", title="Onboarding step 2")
attach_asset(project_id, content_base64=…, filename="interview-01.md")
attach_prototype_shot(project_id, prototype_id)   # screenshot a registered prototype

# CLI parity:
sonaloop asset-attach <project_id> ./pricing.png --title "Pricing page" --notes "v2 draft"
sonaloop asset-list <project_id>
sonaloop asset-remove <project_id> <asset_id>
```

Binaries land in the active partition's content-addressed store
(`data/assets/<hash>.<ext>` in local SQLite; internally
`data/workspaces/<workspace-id>/assets/…` in shared Postgres); the record lands
on the project. The local inspector serves the store at `/data/assets/…`.
Shared-Postgres/RLS deployments block raw `/data`, `/proto-files`, and
`/sessions-files` delivery. Browser previews and downloads instead use
`/assets/{asset-id}/content` (and `/preview` for generated document previews):
the authenticated route resolves the opaque id only inside the active workspace,
then reads that workspace's partition. Compact Inspector galleries use the fixed
`/assets/{asset-id}/thumbnail` route instead of transferring the original. It repeats
the same record/RLS check, decodes only bounded inert raster input, and caches the
640 px WebP derivative inside that workspace's partition; opening/downloading still
targets the original. Existing records are rewritten to these URLs at render time,
so no binary or database migration is needed. Unsafe active formats
(for example SVG/HTML) are download-only and every response is private/no-store.
MCP `view_asset` remains the agent evidence-read surface. Ids are content-addressed
per project, so re-attaching the same bytes is an idempotent upsert. `kind` (image |
screenshot | document | file) is inferred from the extension. Attaching emits the
`asset.attached` lifecycle event (docs/lifecycle-hooks.md).

## The multimodal contract

Images are evidence, not just storage: **`view_asset(project_id, asset_id)`
returns the actual image** over MCP, so the host LLM looks at it with its own
eyes before authoring persona reactions — no in-process vision, no OCR. Text
documents carry an inline excerpt (quoted directly in council briefs); other
binaries are cited by id.

In a council brief, every project asset rides each participant's
`agent_context` as an `EVIDENCE ASSETS IN THE ROOM` block: image assets
instruct the host to `view_asset` them first; document excerpts are inline.

## Direction & provenance

An asset flows `in` (evidence brought INTO the project — the default; every
pre-direction record reads as `in`) or `out` (a deliverable PRODUCED from it —
`export_synthesis_deliverable` attaches the rendered PPTX/PDF with
`source: synthesis:<id>`). A re-export supersedes the stale deliverable record
and records the chain on the survivor (`supersedes: [{id, filename,
created_at}]`), so the provenance of "several versions over time" stays
readable. `record_asset_supersession` is the service seam that writes it.

## In the inspector (UX U8)

- **Detail page** `/assets/{id}` (global id resolution): image preview / file
  card with download, and a provenance block — received/generated timestamp,
  source resolved as a chip, direction, supersede chain, notes.
- **Library → Assets tab** (`/assets`): every asset across projects, badged by
  kind + direction, owning project on the row.
- **Project outline** (`/jobs/{id}`): every project asset appears in context
  under an Assets subgroup for incoming files, or in the final Deliver group
  when the software generated it. Multiple files form a compact responsive
  gallery with bounded previews; each file still opens its canonical detail.
- **Report detail** (`/syntheses/{id}`): consecutive unplaced asset figures form
  the same kind of responsive gallery. Explicitly positioned figures and charts
  retain the report's reading width; print/export restores the figures' natural height.

## Persistence

- In local SQLite mode, assets appear read-only in the web inspector; every asset
  file deep-links to its detail page. Both storage modes use the opaque bounded
  thumbnail route for compact cards. Shared-Postgres deployments also serve the
  original previews/downloads through the authenticated, active-workspace-only
  asset route; the raw file tree remains unreachable. Thumbnail responses stay
  `private, no-store` because their URL intentionally contains no workspace id.
- `export-snapshot` now includes research projects and copies asset binaries to
  the active partition's `export/assets/` directory (`data/export/assets/`
  locally); `import-snapshot` restores both — the evidence survives the portable
  round-trip.
