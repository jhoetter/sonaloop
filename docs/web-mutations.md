# Web mutations — the inspector's write boundary

The web inspector started as a strictly read-only SSR surface. It now carries a
**structural write path**: metadata and container operations are editable in the
browser, while every piece of authored or generated text stays host-authored
(the HOST-AUTHORS-ALL-TEXT invariant). The affordance policy (UX U9,
spec/ux-contract.md §8.4) on top of it: **the UI inspects and edits — it never
creates.** Creation of projects and project elements belongs to the MCP/CLI
host; the browser offers no "New …" button and no create form anywhere. This
page documents the boundary, the write-path pattern, and why some operations
remain MCP-only.

## The mutation boundary

| Entity | Create | Edit | Delete | Notes |
| --- | --- | --- | --- | --- |
| Project | ❌ UI (MCP/CLI: `start_project` / `create_research_project`; `POST /jobs/new` stays as API surface) | ✅ title/goal/icon | ✅ typed-confirmation (type the project title) | browser edits the primary container metadata only; description remains API/MCP metadata; the graph/plan stays agent-driven; regular icons are selectable in the browser, custom SVG icons are generated/set through MCP/CLI |
| Persona | ❌ MCP-only for authored profiles (`brief_persona` → `record_persona`); ✅ catalog import from `/personas/catalog` via `catalog_pull` | ✅ metadata: name, role title, segment, industry | ✅ typed-confirmation (type the display name) | catalog import is a selective structural pull from sonaloop-data, not browser authoring |
| Note | ❌ UI (MCP: `create_note`; `POST /jobs/{id}/notes/new` stays as API surface) | ✅ title/text | ✅ | notes are observations the agent records; editing their text in the browser stays fine |
| Section | ❌ UI (MCP: `create_section`; `POST /jobs/{id}/sections/new` stays as API surface) | ✅ title/kind/note | ✅ (member nodes untouched) | a section is a view; membership editing stays MCP (`add_to_section` …) |
| Council | ❌ | ❌ | ✅ delete only | statements are generated prose — never editable |
| Synthesis / report | ❌ | ❌ | ✅ delete only | report prose is authored/generated — never editable |
| Prototype | ❌ | ❌ | ✅ delete only | recorded artifacts |
| Memories, SOUL, evidence, councils' content, calendar days | ❌ | ❌ | ❌ | host-authored / generated — MCP/CLI only |

The `POST …/new` routes remain registered (CSRF + access-guard gated) so hosts and
automations keep a stable HTTP surface, but their GET forms are gone and nothing in
the UI links them.

### Product-tour and showcase boundary

The optional product tour is a local/single-user Core onboarding surface. In that
mode it is enabled by default and may load the bundled `onboarding-showcase` through
the inspector. When shared Postgres row tenancy is active, the default flips off:
tour affordances and markup are absent, and the browser's
`POST /examples/onboarding-showcase/load` path is rejected before it can mutate the
customer workspace. `SONALOOP_PRODUCT_TOUR_ENABLED` is the explicit operator
override. MCP/CLI example services remain separate host-controlled paths.

Project deletion removes the project container and its project-scoped outputs,
including councils/reports, calibration outcomes and transient Activity/SSE rows.
Personas and their memory remain available to the workspace. Content-addressed
asset/preview files and generated prototype/session/icon/export files are not garbage-
collected by this database cascade; operators may prune unreferenced runtime files
separately after a verified backup.

The one browser-side persona addition affordance is **catalog import**:
`/personas/catalog` searches the curated sonaloop-data catalog and posts a selected
slug to `catalog_pull`. When a local `sonaloop-data` checkout is available, the page
uses the same facet rules and avatar files as the catalog UI; otherwise it falls back
to the published manifest. Free personas import directly; premium personas remain
visible but require `SONALOOP_CATALOG_TOKEN` (or a request-scoped hosted token) and
otherwise return the service's `skipped_premium` explanation in-band. This path does
not create or edit profile prose in the browser; it pulls an existing, validated
catalog snapshot through the same service used by MCP/CLI.

Imported avatar binaries stay in the active runtime partition. Local SQLite serves
their historical `/data/...` path; shared Postgres renders the opaque
`/personas/<persona-id>/avatar` route instead. That route resolves the persona through
the active RLS workspace, contains the recorded PNG inside that workspace's avatar
directory and returns `private, no-store`; the raw `/data` mount remains unavailable.

Everything in the ✅ columns goes through the **existing service layer**
(`sonaloop.services`) — the web routes never touch the `Store` for writes, so
lifecycle events, hooks, the event bus (SSE/activity feed) and cloud guards all
keep firing. Two service functions were added for the web path and are equally
available to MCP/CLI: `update_research_project(project_id, patch)` and
`update_note(note_id, patch)`.

Project/Job icons are structural metadata. New projects get a persisted
`project["icon"]` (existing regular icon by name, or a custom SVG reference).
MCP/CLI callers can choose an existing icon at initialization (`icon="pricingResearch"`
or `icon="random"`), replace it later via `set_project_icon`, or create a
sanitized custom SVG with `generate_project_icon`. Custom SVGs are written under
`data/project-icons/…` and assigned back to the project. In the browser, clicking
the project header icon opens the same edit dialog directly at the visual icon
picker; the picker only selects from the existing icon catalogue.

## Why persona create is MCP-only

`record_persona` (the only authored create path) requires the **complete host-authored
profile JSON** produced by the `brief_persona` protocol: goals, pain points,
personality, relationships, success criteria, … — prose authored by the agent
against the briefing instructions, validated by `validate_profile_payload`. The
generated SOUL is then derived from that profile. There is no meaningful
"structural shell" subset that passes validation, and a web form that asked a
human to hand-type the full profile would bypass the briefing protocol that
keeps personas evidence-shaped. The web therefore offers **metadata edit +
delete** only for authored personas; catalog personas can be imported because
the authored profile already exists in sonaloop-data and is pulled verbatim.

## The write-path pattern (web/_forms.py)

Every mutating route follows one shape:

1. The UI affordance is the detail header's **"…" overflow → Edit**, which
   opens a native **edit `<dialog>` over the detail page** (UX V10,
   ux-contract §9) carrying the kind's form fields (`edit_dialog` +
   the `pages/edit.py` field builders). `GET /thing/{id}/edit` keeps
   answering for deep links with the SAME fields as a plain HTML form
   (`form_page`/`field`, design-system `.sl-field` markup, no JS required —
   one field source for page and dialog). Create endpoints are POST-only —
   no GET form (the affordance policy above).
2. `POST` runs `write_gate(form, operation, resource)`:
   - **CSRF** check first (403 on failure),
   - then the **cloud access-guard seam** (403 on `PermissionError`).
3. Server-side validation; on failure HTTP **400** re-renders the dialog
   RE-OPENED over the detail backdrop with inline errors (the create POSTs,
   which have no detail page, re-render the plain form instead).
4. The service call, then **303 See Other** to the entity page
   (POST-redirect-GET — a refresh never re-submits).
5. Unknown ids answer HTTP **404** (the calm empty-state page).

Edit and Delete share **one visible "…" overflow on every detail header**
(`detail_overflow`, UX V10 — the owner could not FIND deletion while it hid on
the edit pages): kinds with editable structure (project / persona / note /
section) hold Edit + Delete there, recorded artifacts (council / synthesis /
prototype) Delete only, kinds without a delete route render no overflow. The
same actions ride the **slide-over header** (next to expand/close) — the
fragment carries them as a hidden `[data-slide-actions]` block the drawer JS
hoists. Deletion stays **subtle, never a danger zone** (UX U9): choosing
Delete opens a confirm `<dialog>`; projects and personas keep the
typed-confirmation field there (the server re-checks `confirm == name` — the
JS is convenience, not protection); the other entities confirm in the same
modal without typing.

### CSRF: double-submit cookie

The app has no server-side session store, so CSRF protection is stateless: a
middleware issues a random token in an `sl_csrf` cookie (`SameSite=Lax`,
`HttpOnly`), every form embeds the same token in a hidden `csrf_token` field
(`csrf_field()`), and a POST is accepted only when cookie and field match
(constant-time compare). A cross-site attacker can make the browser *send* the
cookie but can neither read it nor set a cookie for this origin, so it cannot
produce the matching field. Chosen over a signed token because it needs no key
management and is equally robust for a same-origin SSR app.

### The cloud guard seam

`services.check_access(operation, resource)` runs the SAME guard list that
`register_access_guard` feeds for substrate queries (`services/_substrate.py`).
Web writes call it with namespaced operations — `web.create_project`,
`web.update_persona`, `web.delete_council`, … — so sonaloop-cloud's tenancy
guard can enforce its editor+ write rule for every browser mutation with one
registration, without core importing anything cloud-specific. Locally the guard
list is empty and every call passes.
