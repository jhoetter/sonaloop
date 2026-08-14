# Web mutations — the inspector's write boundary

The web inspector started as a strictly read-only SSR surface. It now carries a
**structural write path**: metadata and container operations are editable in the
browser, while generated research claims stay host-authored. One deliberate
exception is a guided custom-persona intake: a human may provide the concrete
source facts from which the normal `record_persona` service builds and validates
the profile. Research artifacts (projects, notes, sections, councils, reports and
sessions) are still created by the MCP/CLI host. This page documents that boundary.

## The mutation boundary

| Entity | Create | Edit | Delete | Notes |
| --- | --- | --- | --- | --- |
| Project | ❌ UI (MCP/CLI: `start_project` / `create_research_project`; `POST /jobs/new` stays as API surface) | ✅ title/goal/icon; title-only rename in the Jobs list | ✅ typed-confirmation (type the project title) | the row's `…` menu sits beside Favorite; never-started containers hard-delete, while jobs with terminal run history leave the working set through evidence-preserving archive; active runs remain protected |
| Persona | ✅ guided detailed intake at `/personas/new`; ✅ catalog import; ✅ MCP `brief_persona` → `record_persona` | ✅ metadata: name, role title, segment, industry | ✅ typed-confirmation with an impact preview | creation yields a validated profile and SOUL, not invented lived memory; readiness makes the remaining depth visible |
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

Project deletion is exposed in both the detail header and each Jobs-list row. A
never-started container is hard-deleted with its project-scoped outputs. Once a governed
run journal exists, the same confirmed action removes the job from the current working set
by calling `archive_project`; evidence and exact deep links remain available. An active run
fails closed until it is explicitly finished or stopped. Personas and their memory remain
available to the workspace. Content-addressed asset/preview files and generated
prototype/session/icon/export files are not garbage-collected by a hard-delete cascade;
operators may prune unreferenced runtime files separately after a verified backup.

The catalog remains the fastest browser-side persona addition affordance:
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
Small avatar atoms use `/personas/<persona-id>/avatar/thumbnail`, a fixed 96 px WebP
derived only after the same lookup. Its content-addressed cache lives in the active
workspace partition, while the full portrait remains the persona-detail source.

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

## Guided custom personas and readiness

`/personas/new` asks for the specificity the validator actually needs: work/life
context, tools, goals, constraints, recurring friction, success criteria, working
and communication style, risk posture and concrete relationships. It uses the
same `record_persona` service as MCP and therefore produces the same validated
profile, SOUL, lifecycle event and telemetry. Optional observed situations are
stored as explicit source evidence; the form does not pretend they are memories.

After creation, `persona_readiness` exposes a structural 0–100 readiness view over
profile completeness, grounding, memory volume, continuity and capability coverage.
`brief_persona_memory_onboarding` returns the governed period/day/consolidation/
digest/evaluation sequence an agent should execute. A profile can therefore be
complete while still visibly **thin** for consequential research.

Deletion is intentionally two-stage over MCP: `persona_deletion_impact` returns
counts plus a state-bound confirmation token, and `delete_persona` accepts only
that token. The UI renders the same impact before typed confirmation. Personal
profile/SOUL/memory is removed and the persona is detached from active cohorts;
historical councils and recorded sessions remain as research evidence.

## The write-path pattern (web/_forms.py)

Every mutating route follows one shape:

1. The UI affordance is the detail header's **"…" overflow → Edit**. Project rows also
   expose a quiet **Favorite · “…”** pair: **Rename** opens a title-only dialog and
   **Delete job** uses the same typed confirmation as the detail page. The list has no
   permanent selection mode or decorative row separators. Detail editing opens a native
   **edit `<dialog>` over the detail page** (UX V10,
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

The Jobs overview deliberately repeats only the two object-level actions needed while
triaging a working set: Rename and Delete. Dialog ids remain project-specific, the whole
content row stays one normal deep link for keyboard navigation, and the Favorite and overflow
buttons sit outside that link so they never navigate accidentally.

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
