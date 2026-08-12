# UX Contract — the structural layer above the tokens (U-exec spec)

> **Status:** SPEC (for review — no code beyond the P0 unblock has landed).
> **One-line goal:** make the inspector read like Linear *structurally* — one row atom, peek before
> page, the project as the single home, a 4-item sidebar — and make drift **technically impossible**
> via design-system class contracts + grep gates + visual regression.
> **Builds on:** `linear-design-system.md` (L1 tokens/components), `linear-gap.md` (L2 token exec,
> which explicitly deferred "per-screen micro-polish" to a Phase U), `component-ssr-architecture.md`
> (the SSR component model this spec composes with), `sections-and-composable-graph.md` (the
> composable-graph philosophy this spec renders).

---

## 0. Why (the user's ask, restated)

The showcase project ("Mittagspause unter Termindruck") made the app's full feature surface visible
for the first time — and exposed that the UX collapsed under it. The owner's verdict: *"funktional
ist das allermeiste richtig, aber die UX ist grottenschlecht — wie erreichen wir wieder die extrem
gute UX (linear.app-Level)?"* Concrete sightings: the project looked **empty** (the outline was
invisible), the adopted decision was a **wall of text covering everything**, assets showed as a bare
"Assets (1)", and `/runs` looked misplaced as top-level navigation.

The L2 token pass solved how the app *looks*. This spec solves how the app *is organized* — the
part L2 deferred.

## 1. Current state (measured, 2026-06-11)

**The acute bug (P0, hotfixed).** The project page is a `.proj` flex column. The new section kinds
(decisions/hypotheses/open-questions/assets/surveys) reused `.outlinecard` — the class designed for
*the one* viewport-filling outline (`flex:1; overflow:auto`). Several flex:1 scrollers competed; the
unbounded ADR text won. Measured before the fix: outline **48px** (scrollHeight 864 — the content
existed, the research looked deleted), decision card **778px**, assets/surveys 48px each. P0
landed: `.proj` scrolls as one document, sections became `.projsection` (content-sized, never
flexed), decision bodies clamp at 5 lines with an expand toggle, `prototype`/`note` got
`_REF_ROUTES` entries (chips now resolve titles + deep-link). Tests green. **P0 is a patch; the
disease is structural:**

1. **Two design languages in one app.** The vendored design-system CSS already ships the needed
   contracts — `sl-entity`, `sl-drawer`, `sl-tabs`, `sl-page-header`, `sl-detail` + `sl-rail`,
   `sl-table`, `sl-empty` — but `web/` uses them sparsely (33× `sl-btn` vs. **126 ad-hoc classes**
   in `web_assets.py` and **130 inline `style=` attributes**). Every recent feature invented its
   own presentation; `.outlinecard`-as-section was the inevitable accident.
2. **Object model ≠ UI model.** Domain truth: the project is the container; every primitive is a
   graph node. UI reality: 13 flat nav items; 8 library lists that duplicate the outline without
   its context; decisions/surveys/assets bolted **below** the outline as appendix sections (the
   code admits it: *"pending their own outline-row treatment"*).
3. **Walls of authored text.** ADRs, council exec summaries and the synthesis report render as
   full prose dumps. The row → peek → detail ladder exists in the ecosystem (the tracker's
   TicketRow → Slideover is exactly right) but the inspector never adopted it.
4. **Misplaced telemetry.** `/runs` as top-level nav renders one collapsed "Finished (1)" group on
   an empty screen. (Decision below: engine stays core, the nav item does not.)

**What already works** (proof the idioms carry): the projects list rows, the outline's phase
grouping with sticky headers, ⌘K + keymap, the token system — and the tracker's peek pattern.

## 2. The contract (Linear-level, operationalized)

These are **non-negotiables** for every inspector screen. They extend
`linear-design-system.md` §5.

| # | Rule |
|---|------|
| C1 | **The row is the atom.** Every primitive (council, synthesis/report, decision, survey, session, note, prototype, hypothesis, persona) renders as one `sl-entity` row: leading visual · title · status pill(s) · right-aligned meta. An asset uses the equivalent `sl-file` atom; several files in a project/report detail subgroup may form a compact responsive gallery without changing their individual open/detail contract. |
| C2 | **Peek before page.** Clicking a row opens the `sl-drawer` peek with the essence; the full detail page (with `sl-rail` properties) is one more click (or `Enter` from the peek). No primitive ever dumps its full body into a list context. |
| C3 | **The project is the home.** The outline is the single canvas; *everything the project produced is an outline row in its phase context.* No appendix sections. Cross-project lists exist for browsing, never as the primary surface. |
| C4 | **One scroll context per page.** The page scaffold owns scrolling; only structure may be sticky (phase headers, rail). Two nested scroll traps = bug. |
| C5 | **One measure, one density.** 900px content measure, 13px base, 30-36px rows. No per-page font/spacing inventions. |
| C6 | **Authored prose is dosed.** Long host-authored text is a feature of the *data*, not of the *list*: clamp at 5 lines + expand in rows/peeks; full text only on detail pages, led by structure (verdict card, charts, TOC) before prose. |
| C7 | **Keyboard-first.** ⌘K reaches every object; `j/k` + `Enter`/`Esc` walk rows and peeks; `?` shows the map. |
| C8 | **Empty states teach** (`sl-empty` with the next action), **counts are honest** (a chip count always equals what the target shows). |
| C9 | **No new presentation without a contract.** Pages compose `.sl-*` classes via `web/ui.py` helpers; `style=` and new CSS classes in `web/pages/` are gated (see §5). |
| C10 | **Concept economy & orientation.** The whole app runs on ONE mental model: *Project → phases → rows; click = peek; everything else is context.* Every concept appears in exactly one place (no duplicate surfaces); every screen answers "Wo bin ich · was sehe ich · was kann ich als Nächstes tun" without training. A feature that needs its own new concept must retire an old one. |
| C11 | **Time belongs to the reader, not the server.** Persist absolute instants in UTC, render semantic `<time datetime>` values, and localize them in the browser across initial HTML, SPA swaps and drawers. A no-JS fallback says `UTC` explicitly; date-only domain values are never timezone-shifted. |

## 3. Design

### 3.1 Page scaffold (`sl-scaffold`)

One layout contract replaces every hand-rolled flex/scroll arrangement:

```
.sl-scaffold          column; height:100%; min-height:0
  .sl-scaffold__head  flex:0 0 auto   (page header: breadcrumb/title/actions/chips)
  .sl-scaffold__bar   flex:0 0 auto   (optional toolbar: filters, tabs)
  .sl-scaffold__body  flex:1 1 auto; overflow-y:auto   ← THE one scroll container
  .sl-scaffold__rail  (optional right rail inside body via .sl-detail grid)
```

Python: `ui.scaffold(head=…, bar=…, body=…, rail=…)`. The `.proj`/`.outlinecard` flex rules retire;
the outline becomes plain content inside `__body` (its sticky phase headers stick against it).

### 3.2 The row atom (`sl-entity`)

Anatomy (left → right): `visual` (icon, avatar, or avatar-group) · `title` (one line, ellipsis) ·
`badges` (status pill, kind tag) · `meta` (right-aligned: counts, date, persona chips). States:
hover (var(--sel)), selected, focus-visible ring. Row height 36px (lists) / 32px (dense outline).
Per-kind mapping (the **whole** vocabulary — one table, used everywhere):

| primitive | visual | badges | meta right |
|---|---|---|---|
| council | councils icon | round tag | participants avatar-group · date |
| report/synthesis | report icon | `Report` | sources count · date |
| decision | flag | status pill (adopted/proposed/superseded) | evidence count · date |
| survey | plan icon | lifecycle pill | n questions · n responses |
| session | activity icon | `verified` check when grounded | persona avatar · steps · date |
| prototype | prototype icon | fidelity tag (lofi/midfi) | sessions count |
| asset | thumb (image) / file icon | kind + direction pill | size · date |
| note / hypothesis | panel / target icon | — / status | date |

### 3.3 Peek (`sl-drawer`)

> **Superseded by §8.1 (UX U6).** The essence-peek became the Notion-style slide-over: a row click
> opens the kind's FULL detail page (`?slide=1` fragment of the same route) in a `sl-drawer--wide`
> panel, pushState makes the CANONICAL detail URL the address, Esc/scrim/back restores the list,
> and an expand control navigates to the full page. The `/peek/*` fragments are retired.

Same drawer contract the tracker uses. Opens on row click; `Esc`/outside-click closes; the URL
deep-link (`/decisions/{id}` etc.) still resolves to the full detail — peeks are navigation sugar,
never the only address. Peek content per kind = the row + the *essence*:

- **decision:** status, title, clamped body (5 lines + expand), based-on chips, rejected-with-note.
- **survey:** lifecycle, question list (kind icons), response count, stance distribution strip.
- **session:** persona, verified badge, verdict line, first friction, link to replay.
- **asset:** preview (image) or file card, kind/direction, download/open action.
- **council/report:** exec-summary clamp + sentiment strip, participants.

### 3.4 Project page = the outline, period

- Decisions, surveys, hypotheses and open questions become **outline rows in their phase context**;
  assets become file atoms in a compact gallery in that same context: a decision sits in the round
  whose gate it decided; a survey under the phase that ran it; deliverable assets in a final
  *Deliver* group; evidence assets next to what they ground.
  (Implementation note: these kinds enter `plan_graph`'s node list with their producing task's
  round — the graph builder already knows the linkage via `produces`/judgments.)
- The appendix sections and `#jump`-chips **retire** (P0's `.projsection` is the bridge until P2).
- The header keeps: title, goal, and a single **status chip row**: run state (`Run · finished`,
  links to the run journal), counts that the outline groups repeat.
- `?view=graph` stays URL-reachable (unchanged policy).

### 3.5 Information architecture (decided: radical)

Sidebar (workspace): **Projects · Personas · Library · Activity** — Settings stays in the footer.

- **Library** = one browser page with `sl-tabs`: Councils · Reports · Prototypes · Sessions ·
  Surveys · Hypotheses · Decisions · Notes. One shared filter/search bar; each tab renders the
  same `sl-entity` rows + peek. Old routes (`/councils`, `/decisions`, …) stay registered and
  render the library with that tab active (deep links and `next_recommended_tool` hints survive).
- **Runs:** the engine and `/runs` route stay core (OSS users need run visibility; the loop runs
  locally) — but the nav item retires. Run state surfaces as the project-header chip; `/runs`
  remains linked from there and from Activity rows. Recurring jobs remain sonaloop-cloud-only.
- **Documentation** moves to the Settings/footer cluster (it is reference, not workspace).
- Extensions (cloud/research nav sections) are untouched — they already register their own groups.

### 3.6 Detail pages: structure before prose

- **Report/synthesis:** verdict/POV card first, then the sentiment + stance charts row, then a
  TOC rail (`sl-rail`, scrollspy) beside clamped prose sections; voices render as rows with
  expandable quotes (not a continuous transcript).
- **Council:** header (prompt as `render_prompt`), participants avatar row, sentiment strip, then
  rounds as collapsible groups (round tag + per-turn rows).
- **Survey:** questions as rows with kind icons; results = the existing charts; responses as rows
  with persona chips.

### 3.7 Design-system extensions (the only new CSS lives there)

| addition | side | note |
|---|---|---|
| `sl-scaffold` (+`__head/__bar/__body/__rail`) | components.css + React wrapper | §3.1 |
| `sl-section` | components.css | quiet content section (replaces `.projsection`, `.oqp-h`) |
| `sl-clamp` (+`sl-clamp-toggle`) | components.css | generalizes P0's `.clamp` |
| `sl-entity` meta-slot + avatar-group in row | verify existing contract covers §3.2; extend if not | |
| `web/ui.py` | sonaloop (Python) | `scaffold() entity_row() peek() section() tabs() clamp()` — 1:1 with the class contracts, mirroring the React wrappers |
| backlog from the live session | sonaloop-design | Stepper component; EmptyState variants; ⌘K synonym map; `arrowLeft` icon (evidence: usession_ab7bba9c6e42cbf7) |

After `npm run gen`, `_components_css.py` carries the new contracts into the app; `web_assets.py`
shrinks to what is genuinely app-specific (outline visuals, graph SVG, keymap).

## 4. Mockups (review against these, not against code)

**Project page (default view):**
```
┌────────────────────────────────────────────────────────────────────────┐
│ Projects › Mittagspause unter Termindruck            [≡ Plan] [+ Note] │
│ Mittagspause unter Termindruck                                         │
│ Wie können wir Schreibtisch-Arbeiter:innen … Mittagspause zu kommen?   │
│ (▶ Run · finished)  (5 Personas)  (3 Councils · 2 Reports · 4 Protos)  │
├────────────────────────────────────────────────────────────────────────┤
│ ▾ Discover · Round 1                                            3 rows │
│   ◯ Council   Der Moment, in dem die Pause kippt   (●●●●●)  11. Jun   │
│   ◯ Council   Gegenstrategien und ihre Bruchstellen (●●●●●) 11. Jun   │
│   ◯ Council   Prämissen-Check …                     (●●●●●) 11. Jun   │
│ ▾ Define                                                        2 rows │
│   ▤ Report    Define-Synthese: Verlässliches Essensfenster  11. Jun   │
│   ⚑ Decision  [adopted] Lo-Fi Down-Select: Journey statt …  11. Jun   │  ← row, not wall
│ ▾ Lo-Fi · Build & Test                                          8 rows │
│   ▢ Prototype [lofi] Fenster-Fürsprecher        2 sessions            │
│   ✓ Session   Fabian Drees · verified · 11 steps            12. Jun   │
│   …                                                                    │
│ ▾ Refine                                                               │
│   ▦ Survey    [closed] Essensfenster unter Druck   8 Q · 5 resp.      │
│   …                                                                    │
│ ▾ Deliver                                                              │
│   ▤ Report    Finale Lösungspräsentation …                  11. Jun   │
│   ⬇ Asset     mittagspause-final-report.pptx   101 KB · deliverable   │
└────────────────────────────────────────────────────────────────────────┘
```

**Decision peek (row click → drawer from the right):**
```
                                   ┌───────────────────────────────────┐
                                   │ ⚑ [adopted] Lo-Fi Down-Select:    │
                                   │   Journey statt drei Einzelkonz.  │
                                   │ Ranking: B > A > C. Shortlist …   │
                                   │ … (5 lines) …            [mehr]   │
                                   │ Based on: ⟬Define-Synthese⟭       │
                                   │  ⟬Sichtbares Rutschen⟭ ⟬Fenster-…⟭│
                                   │ Rejected: ⟬Team-Pausenfenster⟭ —  │
                                   │  Org-Adoption (Krampe) …          │
                                   │            [Open decision ↗]      │
                                   └───────────────────────────────────┘
```

**Library (one browser, 4-item sidebar):**
```
│ Projects   │  Library                                    [search…]    │
│ Personas   │  Councils · Reports · Prototypes · Sessions · Surveys ·  │
│ Library ◀  │  Hypotheses · Decisions · Notes                          │
│ Activity   │  ─────────────────────────────────────────────────────   │
│            │  ◯ Council  Der Moment, in dem …   Mittagspause  11. Jun │
│ ⚙ Settings │  ◯ Council  …                                            │
```

## 5. Enforcement (drift becomes impossible, not discouraged)

1. **Grep gates** (house pattern, like the kind-vocabulary gate): a test fails when
   `web/pages/**` contains `style="` or a `class_` outside the contract whitelist
   (`sl-*` + the documented app-specific set: outline/graph/keymap classes). Existing violations
   are burned down during P2-P4; the gate ratchets (count may only decrease).
2. **Visual regression** (`make ux`): seed a deterministic demo store (load_example), Playwright
   screenshots of ~12 canonical screens (project, peek open, library tabs, report, council,
   survey, persona, settings — light + dark), pixel-diff against committed goldens with a small
   threshold. The flex-squeeze class of bug becomes a red diff on the day it is written.
3. **Rubric:** Phase U's `ux-audit.md` scores every screen /10; **target ≥9 average, no screen <8**
   after P4; the audit re-runs as the acceptance step of each phase.

## 6. Migration phases (each: implement → full pytest green → `make ux` diff → re-score)

| phase | scope | accept |
|---|---|---|
| **P0** ✅ | unsqueeze (done: page scroll, `.projsection`, clamp, ref routes) | tests green (660 ✓) |
| **P1** | DS: `sl-scaffold`/`sl-section`/`sl-clamp` + gen; `web/ui.py`; grep gate (ratchet mode); visual-regression harness + goldens of the CURRENT state | gate + `make ux` runnable in CI |
| **P2** | row+peek unification: per-kind `sl-entity` rows (§3.2 table), `sl-drawer` peeks, outline absorbs decisions/surveys/assets/hypotheses/OQs as phase rows; appendix sections + jump chips retire | project mockup matches; counts honest (C8) |
| **P3** | IA: 4-item sidebar, Library browser with tabs, runs→header chip, Documentation→footer; old routes render library-with-tab | nav mockup matches; all old URLs 200 |
| **P4** | detail text discipline: report/council/survey per §3.6 | no screen opens with >10 lines of unbroken prose above the first structural element |
| **P5** | DS backlog: Stepper, EmptyState variants, ⌘K synonyms, arrowLeft; goldens refreshed; rubric re-scored | audit ≥9 avg, no screen <8 |

## 7. Decisions (reviewed 2026-06-11 — owner: conceptual economy beats per-case optimization)

1. **Hypotheses = outline rows like everything else.** One rule, zero exceptions: *everything the
   project produced is a row in its phase.* Special cases are concepts users must learn (C10).
2. **Evidence assets: v1 = one *Evidence* group per phase** (cheap, predictable place);
   deliverables live in the *Deliver* group. Node-adjacent placement upgrades later, once
   `plan_graph` carries grounding edges — the group is forward-compatible.
3. **Peek v1 covers ALL kinds.** "Click a row → peek" must be universally true or it is a
   coin-flip the user has to learn. A generic default peek (row header · clamped body · ref chips ·
   "Open ↗") covers every kind; kind-specific extras (survey stance strip, asset preview, session
   verdict) are added only where the renderer already exists.
4. **Runs: header chip with popover** (state · last activity · human-readable recovery hint ·
   link to journal). Support-grade invariant text, operation calls and trace ids use progressive
   disclosure inside that existing popover and `/runs`; they never become a full-width project
   card. `/runs` stays as the minimal off-nav journal page the popover links to — it is telemetry,
   not a second project canvas.
5. **Goldens are committed in-repo.** Deterministic seed, fixed viewport, ~12 screens × light+dark
   (~3-5 MB). Exact, reviewable diffs in PRs beat lighter-but-weaker on-demand baselines — and
   committing generated artifacts with a freshness gate is already house culture.

## 8. Round 2 (2026-06-12) — owner review of the landed P0-P5

The owner's verdict on P0-P5: a clear step forward, but a significant gap remains. The decisions:

1. **Peek v2 — Notion-style slide-over (supersedes §3.3's essence-peek).** Clicking a row opens
   the FULL detail page as a slide-over in a narrow "sidebar layout" (not a preview). The URL
   becomes the detail URL (pushState; Esc/scrim/popstate restores the list URL), so the link is
   real: loading that URL directly renders the full page; opening it from a list keeps the
   background context visible behind the slide-over. An expand control toggles slide-over ↔
   full page (URL already correct — expand is just layout). `/peek/*` fragments retire in favor
   of the detail routes rendering their content scaffold-aware.
2. **Detail completeness & layout consistency — every kind, one scaffold.** Audit ALL artifact
   kinds; some lack detail pages entirely (prototype sessions!), others drift in layout. Every
   kind gets a real detail page on ONE shared detail scaffold (header · content · properties
   rail), identical anatomy across kinds. Sessions are explicitly first-class (owner: "ich lege
   viel Wert auf Sessions").
3. **Assets as a first-class surface.** Input files received via MCP (possibly across many user
   messages) and documents generated by the software are visible as such: an Assets library tab
   + a project files view with a provenance timeline (created_at · source ref · direction in/out
   · supersede chain), and an asset detail page (preview, download, provenance).
4. **Affordance restraint (read-mostly inspector).** The UI does NOT create projects or project
   elements (notes/sections) — creation belongs to the MCP/CLI host. Editing stays. Deletion
   becomes subtle: an overflow ("…") menu action with typed confirm — the bottom "danger zone"
   pattern retires.
5. **Linear-grade filtering.** The design system's FilterBar (already proven in the tracker)
   lands on the project outline (kind · phase · persona · status) and the Library tabs.

Work tickets: sonaloop/ux-u6-notion-slideover · ux-u7-detail-completeness · ux-u8-assets-surface
· ux-u9-affordance-restraint · ux-u10-filterbar. Audit follow-ups F1 (teaching empty states) and
F3/F4 (wording, activity coalescing) fold into U7; F2 (avatar binaries in snapshots) stays a
data-layer follow-up.

### §8 addenda (2026-06-12, second owner pass)

6. **Slide-over URL semantics v2 (fixes a U6 misread).** Reloading after opening a slide-over
   currently lands on the full detail page — confusing. Correct (Notion) semantics: opening a row
   pushes the BACKGROUND URL + a slide param (`?d=<detail-path>`); loading/reloading that URL
   server-renders the background page WITH the slide-over open (SSR, no flash). Esc/back drops
   `?d=`. Expand navigates to the canonical detail URL (full page) — that URL keeps rendering
   full-page on direct load. Shareable both ways: list-context URL shares the context view, the
   canonical URL shares the document.
7. **Spacing & density system (design-system level).** Row heights and inter-element distances
   become a documented, tokenized rhythm like mature design systems: density tokens (row heights
   for dense outline / list / touch), a vertical-rhythm scale for gaps between rows, sections and
   page regions, and normalization of existing `.sl-*` rules onto that scale (no off-scale px
   values). Documented as its own docs-site page; the inspector consumes it via the vendored CSS.
8. **Fragment shell coherence across releases.** A full document and every content-only SPA or
   slide-over response carry a content-derived `release.context` shell token covering
   CSS/JavaScript plus the persistent static shell-markup contract. SPA and drawer requests send
   the token they are currently running. A missing
   or different **release** segment (including a tab opened before this protocol shipped) receives
   `409`, `no-store`, and no fragment; even the pre-protocol client already turns that non-2xx into
   a full navigation. A matching release with a different **context** (language, workspace,
   branding/theme or persistent extension chrome) receives a normal `200` tokened fragment; the
   client detects the full-token mismatch, refuses the DOM swap, and full-navigates. Full HTML is
   itself `no-store`, so that recovery cannot reload a cached stale shell. New markup therefore
   never enters a document whose retained shell cannot render or operate it.

## 9. Round 3 (2026-06-12, second screenshot review) — CRAFT

The owner's verdict on round 2: right structure, but "noch weit von 9/10 entfernt — das geht noch
ERHEBLICH besser." The prior audits over-scored: they checked structure and consistency but not
**craft** — visual information design, density judgment, microcopy. The rubric gains a 7th
dimension, **Craft** (anchors: 9 = would ship at Linear/Notion unchanged; compare against real
Linear/Notion screenshots, not against our own previous state). Concrete findings, all owner-cited:

| # | finding | direction |
|---|---|---|
| V1 | Filter button floats OUTSIDE the content measure; Themes chip row overflows the frame; themes are obviously a facet; **no text search** | FilterBar v2 in the scaffold bar INSIDE the measure; search input is PART of the filter contract (design-system level: FilterBar always = search + facets); Themes row retires into a section facet |
| V2 | Outline rows overloaded & partly redundant (avatars AND "15 statements"; NOTE + "Observation"; theme chip + round pill + count + date) | Row vocabulary v2: ≤2 trailing chips + date; counts move to detail/hover; default-kind pills dropped |
| V3 | Charts: bars all render FULL WIDTH regardless of value (length encodes nothing); persona boxes waste space; "Oppose 0" legend entries; predicted-behavior shows bare "0.6" chips | Visualization redesign: diverging bars that encode value, no entity boxes, compact rows, zero categories dropped, likelihood rendered as labeled % with mini-bar |
| V4 | Session step screenshots GONE (regression: `<img>` without src; files serve 200) — and prototypes/remote-software sessions must show them | Fix the src regression; screenshot strip + lightbox on session detail; prototype page shows session shots |
| V5 | Slide-over properties in a boxed card, cramped spacing; session header pill-soup ("Prototype" pill, date as pill) | Notion-style properties: quiet label/value rows, no frame; header meta as plain text; rhythm pass on detail headers |
| V6 | ⌘K is a bare 17-link jump list (re-exposes the old IA) | Palette v2: icons, sections (Recent · Navigate · results by kind with project context), entity search, Library sub-targets grouped |
| V7 | "Take the tour" floats as toast; Feedback/shortcuts rows visually off vs nav; topbar "• 0" runs chip when zero | Tour entry into the sidebar footer; footer rows styled exactly like nav rows; zero-state chip hidden |
| V8 | Runs vs Activity unclear; "what is a run?" | Explainer leads on both surfaces; run-chip popover defines the concept; Activity groups per run (G3) |
| V9 | Files lens not file-like (duplicate download icons, chips instead of file identity) | File cards: type icon/thumbnail, filename+extension prominent, grid; one download affordance |
| V10 | Edit pages should be modals/dialogs; deletion currently undiscoverable | Edit becomes a dialog over the detail page; a visible "…" overflow on detail headers holds Edit/Delete |
| V11 | Authored surfaces still read "wie auf dem Terminal" — the PPTX exec summary is a text wall | Deck export quality pass: statement/verdict slide layouts, charts on slides, voices slides; line-length + hierarchy rules in the deck renderer |
| V12 | Microcopy pass: terminal-flavored leads/labels de+en | Plain, human sentences; no abbreviations or colon-syntax in UI copy |

Round-3 audit rule: re-score EVERYTHING with the Craft dimension against external anchors; the
9/10 claim must survive the owner's screenshots.

## 10. Round 4 (2026-06-12, third screenshot review) — finish

Owner: "erneut deutlich besser, aber ich finde immer noch Mängel … geh das bitte an — alles!"

| # | finding | direction |
|---|---|---|
| W1 | Spacing violations still visible in places (Library shown) — "gehe das wirklich in der GESAMTEN UX durch" | App-wide spacing conformance sweep: DOM-measure every screen against the density tokens, fix every off-grid padding/gap/margin; record the measurement table |
| W2 | Search+filter bar must take the FULL content width | Search input stretches; bar spans the measure |
| W3 | Header chips (Run · Finished / 1 file) "nicht sauber visuell integriert"; adjacent controls mix sizes/styles (Plan bordered+label, … bordered square, ★ bare; slide-over: … boxed vs ★/⤢/× bare) | ONE control vocabulary: consistent heights, one icon-button treatment, chips share one shape family with the buttons |
| W4 | "Drew on:" memory-ref chips are raw (timestamp-prefixed grey slabs) | Quiet refs: formatted date, trimmed text, consistent chip anatomy |
| W5 | Council Q→A linkage is flat | Thread the answers: slight indentation + descending angled connector lines (file-tree look) from question to each answer |
| W6 | Document file cards show an empty stage with a badge — "schon die Titel-Slide anzeigen" | Export writes a first-slide preview PNG (own rasterizer); file cards/thumbs use it; images keep real thumbs |
| W7 | Documentation is absent from the sidebar and the docs page is plain; footer trio still under-designed ("? for shortcuts") | Documentation becomes a visible sidebar footer entry; docs page design pass; footer rows final polish (kbd chip for ?) |
| W8 | Session image lightbox buggy: prototype iframe bleeds over the dialog | Fix stacking/containment (z-index/top-layer; iframe clipped) |
| W9 | (Owner round-3 H2, now decided) donut + stance bars encode the same data twice | Keep the scaled stance bars, drop the donut on web council/synthesis blocks (deck keeps its single donut card) |
| W10 | Leftovers G1/G2/G5 | prototype-page session section naming; report lifecycle pill; sidebar active-state rule aligned with project-rooted crumbs |
| W11 | Persona attribution is inconsistent: prototype rows show "2 sessions" but NO persona avatars while councils show the avatar group | ONE rule app-wide: wherever an artifact's data carries persona participation (council participants, session subjects, prototype session drivers, survey respondents, report voices), the row AND the detail header show the persona avatar-group. Dense rows use max 4 + overflow; the job header lists and links the full cohort because the cohort is primary page context. |
| W12 | A legacy text-only session renders its `state.screen` prose inside a dashed pseudo-thumbnail, so readers reasonably assume an image failed | A missing screenshot is an explicit minimal empty visual state. Preserve the state description as text, but never frame it as pixels. Session rows disclose `Screen replay` / `Some screens` / `No screen`. |
| W13 | Browser-grounded usability sessions can omit screenshot refs even when the ordered harness log already captured one image per authored step | Backfill screenshot refs only when the ordered snapshot/step counts match exactly; otherwise remain text-only or partial rather than risk pairing a step with the wrong screen. |

## 11. Round 5 (2026-06-12) — typography & reading density

The craft column sits at 8.5; the holdouts are the text-heaviest pages (synthesis/council detail,
CR 8). Round 5 is a focused typography/information-density pass — plus the J1 decision (taken in
the owner's established direction): the distribution STRIP retires, the scaled stance bars are the
one encoding.

| # | item |
|---|---|
| T1 | **Type conformance gate** (sibling of the spacing harness): measure rendered font-size/weight/line-height per structural element on every canonical screen against the type tokens (t-xs…t-xl + the documented roles); flag off-scale values; fix to zero; keep as a re-runnable gate (`scripts/ux_type.py`). |
| T2 | **Prose measure:** running prose (turn texts, exec summaries, report sections, verdicts) reads at a true reading measure (~68-72ch), not the full 900px container; structural elements (rows, charts, rails) keep the full measure. |
| T3 | **Synthesis detail typography:** verdict card, section heads, prose blocks, voices rows — one hierarchy (display/lead/body/quiet) with deliberate contrast steps; quotes get real quote styling; refs/meta in the quiet layer. |
| T4 | **Council detail typography:** question banner vs turn text vs persona meta vs refs — same hierarchy system; the tree-threaded answers read as a conversation, not a form dump. |
| T5 | **J1 executed:** stance distribution strip removed on council/synthesis; bars are the single encoding. |
