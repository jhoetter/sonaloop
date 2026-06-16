"""Web UI asset strings (CSS + inline JS) extracted from web.py (spec/refactor-plan.md target 1). Pure constants — no behaviour, imported back into web.py.

Colour tokens (the :root / dark / [data-theme] blocks) live in the design system, NOT here.
Single source: ../sonaloop-design/tokens.data.mjs → vendored as sonaloop/_tokens.py and
prepended below as TOKENS_CSS. Cursor-leaning brand: near-white warm light + cool dark
(#101113), Geist + Geist Mono, indigo accent used sparingly; panels lifted to crisp white.
Refresh the vendored tokens with `make icons`. See sonaloop-design/BRANDING.md."""

from ._tokens import TOKENS_CSS  # generated design tokens — single source: ../sonaloop-design
from ._components_css import COMPONENTS_CSS  # shared .sl-* component layer — same single source
from ._pixel_font import PIXEL_FONT_CSS  # Sona Pixel (base64) — powers the .sl-logo "loop"

CSS = PIXEL_FONT_CSS + TOKENS_CSS + COMPONENTS_CSS + """

*{box-sizing:border-box}
html,body{height:100%}
body.spa-loading{cursor:progress}
body{margin:0;font:13px/1.5 "Geist","Geist Variable",-apple-system,BlinkMacSystemFont,"Segoe UI",system-ui,sans-serif;background:var(--bg);color:var(--ink);-webkit-font-smoothing:antialiased;letter-spacing:-0.003em}
a{color:inherit;text-decoration:none}
.muted{color:var(--muted)}.small{font-size:var(--t-sm)}.faint{color:var(--faint)}
svg.ic{width:16px;height:16px;flex-shrink:0;stroke:currentColor;fill:none;stroke-width:1.75;stroke-linecap:round;stroke-linejoin:round;vertical-align:-3px}
::selection{background:var(--accent-weak)}

/* ---- app shell ---- The chrome (.sl-app-shell · .sl-sidebar · .sl-nav · .sl-resize ·
   .sl-topbar · .sl-usermenu) is the shared design-system layer (COMPONENTS_CSS); its
   behaviour is _shell.SHELL_JS. Only the app-specific favorites/footer rows live here. */
.sb-quick{display:flex;flex-direction:column;gap:1px}
.sb-quick a{display:block;padding:var(--s-1) var(--s-2);border-radius:var(--radius-sm);color:var(--muted);font-size:var(--t-sm);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.sb-quick a:hover{background:var(--hover);color:var(--ink)}
/* Sidebar footer rows (Documentation · Feedback · Take the tour · ? shortcuts): the SAME
   .sl-nav row contract as the nav above (height, hover, icon size — ux-contract §9 V7/W7);
   only the placement differs. The `?` keycap is the shared .sl-kbd chip, sized into the
   16px icon slot so the row geometry stays byte-identical to the rows around it. */
.sl-sb-foot{flex-shrink:0;padding:var(--s-2);border-top:1px solid var(--line)}
.sl-sb-foot .sl-kbd{flex:none;width:16px;height:16px;padding:0;display:inline-flex;align-items:center;justify-content:center;font-size:var(--t-xs);color:var(--faint);transition:transform .18s ease,color .18s,border-color .18s}
/* Hover liveliness parity with the nav rows (owner round 5: "unten … nicht animiert"): the
   docs/feedback/tour icons play their .pi-animate micro-interaction on row hover (the rows
   carry .pi-hover like the nav rows); the `?` keycap — no icon to animate — "presses" like
   a real key instead. Guarded by reduced-motion like the icon layer. */
@media (prefers-reduced-motion: no-preference){
.sl-sb-foot .pi-hover:hover .sl-kbd{transform:translateY(1px);color:var(--ink);border-color:var(--faint)}
}
/* The sidebar user/settings menu is the shared .sl-usermenu / .sl-um-* layer (COMPONENTS_CSS).
   Theme + language switchers use the shared .sl-segmented (--fill --stacked) from
   COMPONENTS_CSS. Only the icon size is bridged here (the design-system control leaves
   icon sizing to the host). See the design-system docs (Components › Segmented · Tabs). */
.sl-segmented .ic{width:17px;height:17px}
/* Linear-style project OUTLINE (primary view) — phase-grouped, collapsible, never overlaps.
   flex:1 0 auto: the outline GROWS to fill a sparse first screen but NEVER shrinks below its
   content — the page (.proj) scrolls as one document. Since UX P2 the outline IS the whole
   page (every primitive is a row in its phase group; the appendix sections retired). */
.outlinecard{flex:1 0 auto;padding:8px 0 40px}
.outline{max-width:900px;margin:0 auto;padding:0 24px;position:relative}
.ol-rel-svg{position:absolute;left:0;top:0;width:100%;height:100%;overflow:visible;pointer-events:none;z-index:3}
.ol-rel-svg path{fill:none;stroke:var(--accent);stroke-width:1.8;opacity:.86;marker-end:url(#olrel-arrow)}
.ol-rel-svg path.ol-rel-in{stroke:var(--muted);opacity:.72}
.ol-rel-svg marker path{fill:var(--accent)}
.ol-phase{border-bottom:1px solid var(--line-2)}
.ol-phase>summary{list-style:none;cursor:pointer;display:flex;align-items:center;gap:8px;padding:12px 8px;font-size:var(--t-body);position:sticky;top:0;background:var(--bg);z-index:1}
.ol-phase>summary::-webkit-details-marker{display:none}
.ol-phase>summary .ol-gl{color:var(--accent);font-size:var(--t-sm);width:14px;text-align:center}
.ol-phase>summary b{font-weight:650;letter-spacing:-.01em}
.ol-rlabel{font-size:var(--t-xs);font-weight:700;letter-spacing:.05em;text-transform:uppercase;color:var(--faint);padding:8px 8px 4px 32px}
/* File rows INSIDE the outline follow the outline's FLAT idiom — the boxed .sl-file--row
   card variant is for the Library/files lens. A box among flat siblings reads as a stray
   divider + floating card (owner round 5); the spacing harness flags the mixed idiom. */
.outline .sl-file--row{border:0;background:transparent;border-radius:0;padding:7px 8px}
.outline .sl-file--row:hover{background:var(--hover);border-radius:var(--radius-sm)}
.olrow{display:flex;align-items:center;gap:8px;padding:8px;border-radius:var(--radius-sm);color:var(--ink);text-decoration:none;font-size:var(--t-body);z-index:1}
.olrow:hover{background:var(--hover)}
.ol-dot{width:8px;height:8px;border-radius:2px;flex-shrink:0}
/* per-kind leading icon (§3.2 row atom) — same slot as the dot, tinted per kind */
.ol-ico{display:inline-flex;align-items:center;justify-content:center;width:16px;flex-shrink:0}
.ol-ico svg{width:15px;height:15px}
.ol-thumb{width:18px;height:18px;object-fit:cover;border-radius:4px;display:block}
.olrow .ol-title{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.olrow .ol-crew{display:inline-flex;align-items:center;flex-shrink:0}
/* crew avatars render through the ONE avatar_group anatomy (web/ui.py, ux-contract §10 W11):
   the vendored .sl-avatar-group overlap + the .sl-avatar-group__more overflow chip — no
   outline-local sizing/overlap overrides, so the cluster is identical on every surface. */
.ol-sds{display:inline-flex;gap:3px;margin-left:7px}
.ol-sd{width:6px;height:6px;border-radius:var(--radius-full);display:inline-block}
.olrow .ol-ts{color:var(--faint);font-size:var(--t-xs);flex-shrink:0;white-space:nowrap;font-variant-numeric:tabular-nums;min-width:96px;text-align:right}
.ol-gl.ol-round{color:var(--muted)}
.ol-cnt{font-size:var(--t-xs);color:var(--faint);font-weight:600;background:var(--panel-2);border-radius:var(--radius);padding:1px 7px;margin-left:2px}
/* Plan drawer (project plan view) — a tight, progress-led checklist */
.plan-hd{margin-bottom:8px}
.plan-goal{font-weight:600;font-size:var(--t-prose);line-height:1.5;color:var(--ink)}
.plan-prog-row{display:flex;align-items:center;gap:12px;margin-top:12px}
.plan-prog{flex:1;max-width:240px;height:6px;border-radius:var(--radius-full);background:var(--hover);overflow:hidden}
.plan-prog>i{display:block;height:100%;background:var(--accent);border-radius:var(--radius-full);transition:width .4s var(--ease)}
.plan-prog.full>i{background:var(--green)}
.plan-prog-txt{font-size:var(--t-sm);color:var(--muted);font-variant-numeric:tabular-nums}
.plan-sub{display:flex;align-items:center;gap:8px;margin-top:12px}
.plan-sub>span:last-child{font-size:var(--t-sm);color:var(--faint)}
.plan-fw{margin-top:12px;padding:12px;border:1px solid var(--line);border-radius:var(--radius-sm);background:var(--panel-2)}
.plan-fw-job{display:inline-flex;align-items:center;gap:6px;font-size:var(--t-xs);color:var(--muted);font-weight:550;margin-bottom:8px}
.plan-fw-hd{display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap}
.plan-fw-name{display:inline-flex;align-items:center;gap:6px;font-weight:600;font-size:var(--t-md);color:var(--ink)}
.plan-fw-cur{font-size:var(--t-xs);color:var(--accent);background:var(--accent-weak);padding:1px 8px;border-radius:var(--radius-full);font-weight:550;white-space:nowrap}
.plan-fw-stages{display:flex;gap:8px;flex-wrap:wrap;margin-top:8px}
.fw-stage{font-size:var(--t-xs);color:var(--faint);border:1px solid var(--line);padding:1px 8px;border-radius:var(--radius-full);white-space:nowrap}
.fw-stage.is-past{color:var(--muted)}
.fw-stage.is-current{color:var(--accent);border-color:var(--accent);font-weight:550}
.psec{margin-top:24px}
.psec-h{display:flex;align-items:center;justify-content:space-between;font-size:var(--t-xs);text-transform:uppercase;letter-spacing:.07em;color:var(--muted);font-weight:600;padding:0 2px 2px}
.psec-n{color:var(--faint);font-weight:550;font-variant-numeric:tabular-nums}
.psec-list{border-top:1px solid var(--line)}
.ptask{display:flex;gap:12px;padding:12px 8px;border-bottom:1px solid var(--line);margin:0 -8px;border-radius:var(--radius-sm)}
.ptask.is-last{border-bottom:0}.ptask:hover{background:var(--hover)}
.pt-mark{flex:none;width:18px;line-height:1.35;text-align:center}
.pt-body{flex:1;min-width:0}
.pt-row1{display:flex;align-items:baseline;gap:8px;flex-wrap:wrap}
.pt-title{font-weight:550;font-size:var(--t-md);color:var(--ink)}
.ptask.is-done .pt-title{color:var(--muted)}
.pt-cap{font-size:var(--t-xs);color:var(--accent);background:var(--accent-weak);padding:1px 7px;border-radius:var(--radius-full);font-weight:500;line-height:1.5}
.pt-sub{font-size:var(--t-xs);color:var(--faint);margin-top:3px;line-height:1.5}
.pt-evs{display:flex;gap:8px;flex-wrap:wrap;margin-top:8px}
.pt-evs .ev{font-size:var(--t-xs);color:var(--muted);background:var(--panel-2);border:1px solid var(--line);padding:1px 8px;border-radius:var(--radius-full);text-decoration:none;white-space:nowrap}
.pt-evs a.ev:hover{color:var(--accent);border-color:var(--accent)}
.ol-rcap{font-size:var(--t-body);font-weight:400;color:var(--muted);margin-left:8px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.ol-ptag{flex-shrink:0;width:86px;font-size:var(--t-xs);font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:.02em;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
/* round-5 J4: repeated kinds in a contiguous run keep their FULL label, one tone fainter —
   the first of the run stays muted; nothing is omitted (omission read as a bug). */
.ol-ptag--run{color:var(--faint);font-weight:500}
.ol-flat{padding-top:4px}
.olrow.ol-tw{position:relative}
/* Continuous tree spine: ::before is ONE straight vertical (full height for a middle child so it joins
   the next sibling; stops at center for the last child). ::after is the rounded elbow into the node.
   Splitting spine (straight) from elbow (curved) avoids the notch where a curved segment meets a
   straight one. Uniform colour (no hover recolour) so the spine never reads as two-tone. */
.olrow.ol-tw::before{content:"";position:absolute;left:calc(var(--ti,1)*24px);top:-3px;bottom:-3px;border-left:1.6px solid var(--line-2)}
.olrow.ol-tw.ol-last::before{bottom:auto;height:calc(50% + 3px)}
.olrow.ol-tw::after{content:"";position:absolute;left:calc(var(--ti,1)*24px);top:calc(50% - 6px);width:9px;height:6px;border-left:1.6px solid var(--line-2);border-bottom:1.6px solid var(--line-2);border-bottom-left-radius:6px}
/* sessions nest under their subject (tracker: project-page-sessions-live-under-their-subject):
   avatar lead + outcome/friction chips on the child rows; the parent's funnel aggregate is a REAL
   link, so that row is a <div> with a stretched overlay link and the chip layered above it. */
.olrow{position:relative}
.ol-stretch{position:absolute;inset:0;border-radius:var(--radius-sm)}
.ol-funnel{position:relative;z-index:1;flex-shrink:0;white-space:nowrap;font-size:var(--t-xs);color:var(--muted);border:1px solid var(--line);border-radius:var(--radius-full);background:var(--panel-2);padding:1px 9px;text-decoration:none}
.ol-funnel:hover{color:var(--accent);border-color:var(--accent)}
.olrow .lbl{flex-shrink:0}
/* the declared chips slot (outline chip contract, _outline_chips) — rendered only when non-empty */
.ol-chips{display:inline-flex;align-items:center;gap:8px;flex-shrink:0}
/* near-empty outlines (plan-less / young projects) size to content so the sections below rise
   above the fold (tracker: outline-drops-study-nodes-on-plan-less-projects); a full outline
   still fills the viewport. */
.outlinecard.ol-compact{flex:0 1 auto}
/* Long authored bodies (decision records) clamp via the shared .sl-clamp/.sl-clamp-toggle
   contract (COMPONENTS_CSS, ui.clamp) — the P0 app-local .clamp rules graduated there.
   The P0 bridge section classes + header jump chips retired with UX P2: every kind is an
   outline row in its phase group now (spec/ux-contract.md §3.4). */
.outline .olrow{transition:opacity .12s,background .12s}
.outline.is-relating .olrow,.outline.is-relating .sl-file--row{opacity:.62}
.outline.is-relating .olrow.ol-rel-source,.outline.is-relating .sl-file--row.ol-rel-source{opacity:1;background:var(--hover)}
.outline.is-relating .olrow.ol-rel-in-row,.outline.is-relating .sl-file--row.ol-rel-in-row,
.outline.is-relating .olrow.ol-rel-out-row,.outline.is-relating .sl-file--row.ol-rel-out-row{opacity:1}
/* themes — cross-cutting labels (V1: the chip row retired into a FilterBar facet; a row's
   membership is a small colored dot with the full theme title on hover) */
.olth-pills{display:inline-flex;align-items:center;gap:4px;flex-shrink:0;margin-right:10px}
.olth-dot{width:8px;height:8px;border-radius:50%;flex-shrink:0;display:inline-block}
/* relations block on detail pages (Linear progressive disclosure) */
.relcard{margin-top:16px}
.relh{font-size:var(--t-sm);font-weight:700;letter-spacing:.04em;text-transform:uppercase;color:var(--faint);margin-bottom:8px;display:flex;align-items:center;gap:6px}.relh svg{width:13px;height:13px}.h1ic{display:inline-flex;vertical-align:-3px;margin-right:8px}.h1ic svg{width:19px;height:19px}
.relgrp{padding:2px 0 8px}
.rellbl{font-size:var(--t-xs);font-weight:600;color:var(--muted);margin:0;padding:5px 0 3px}
.relrow{display:flex;align-items:center;gap:8px;padding:8px;margin:0 -8px;border-radius:var(--radius-sm);color:var(--ink);text-decoration:none;font-size:var(--t-body)}
.relrow:hover{background:var(--hover)}
.relrow .relt{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
/* Properties panel uses the shared .sl-props / .sl-prop; only the value-link tint is app-local */
.sl-prop__v a{color:var(--accent);text-decoration:none}.sl-prop__v a:hover{text-decoration:underline}
/* W8 containment: isolation + contain:paint pin the embedded document into its own stacking
   context and clip it hard to the card (overflow + radius) — an iframe can never paint over
   page chrome or an overlay, whatever it renders. */
.protoframe{border:1px solid var(--line);border-radius:var(--radius-lg);overflow:hidden;background:var(--panel);height:620px;box-shadow:0 4px 16px rgba(0,0,0,.08);position:relative;isolation:isolate;contain:paint}
.protoframe iframe{width:100%;height:100%;border:0;display:block}
.strow{padding:8px 0;border-bottom:1px solid var(--line)}.strow:last-child{border-bottom:0}
.strow a{text-decoration:none}.strow .ic{vertical-align:-3px;margin-right:5px}
.oqd{margin-top:16px;border:1px solid var(--line);border-radius:var(--radius);background:var(--panel)}
.oqd>summary{cursor:pointer;padding:12px 16px;font-size:var(--t-body);font-weight:600;list-style:none}
.oqd>summary::-webkit-details-marker{display:none}
.oqd[open]>summary{border-bottom:1px solid var(--line)}
.oqd>div{padding:12px 16px}
/* .sl-resize · .sl-main · .sl-topbar · .sl-iconbtn · .sl-spacer · .sl-tb-actions are the shared
   shell layer (COMPONENTS_CSS). Bridge only the inspector's collapse-only topbar toggle: the
   show-sidebar button appears once the sidebar is collapsed (you collapse via the handle or `[`). */
.sl-topbar .sl-iconbtn[data-sidebar-toggle]{display:none}
.sl-app-shell.is-collapsed .sl-topbar .sl-iconbtn[data-sidebar-toggle]{display:inline-flex}
/* Breadcrumb = the shared .sl-breadcrumb (+__link / __current / __sep) from COMPONENTS_CSS.
   Bridge the inspector's denser type size + bolder current crumb. */
.sl-breadcrumb{font-size:var(--t-body)}
.sl-breadcrumb__current{font-weight:600}
section{padding:24px 32px;overflow:auto;scroll-behavior:smooth}
.page{max-width:1200px;margin:0 auto}
.page.wide{max-width:none}
/* Project detail = full-bleed outline */
.sl-main>section:has(.proj){flex:1;min-height:0;padding:0;display:flex;flex-direction:column;overflow:hidden}
.proj{flex:1;min-height:0;display:flex;flex-direction:column;overflow-y:auto}
.proj-head{flex-shrink:0;width:100%;max-width:900px;margin:0 auto;padding:24px 24px 12px}
.proj-head .stats{margin:0 0 12px}
.proj-head .pills{display:flex;flex-wrap:wrap;align-items:center;gap:8px}

/* ---- generic ---- */
h1,h2,h3,h4{color:var(--ink)}
.h1{font-size:var(--t-xl);line-height:1.2;letter-spacing:-.02em;margin:0 0 4px;font-weight:650}
.lead{color:var(--muted);font-size:var(--t-body);margin:0 0 16px;max-width:var(--measure-prose);line-height:1.5}
/* Buttons come from the shared design-system layer: .sl-btn (+ --primary / --sm / .is-active /
   [disabled]) in COMPONENTS_CSS (vendored from sonaloop-design/styles/components.css). Em-based,
   so they render dense at the inspector's 13px base. See the design-system docs (Components ›
   Button). The old hand-rolled .btn block lived here. */
:focus-visible{outline:none;box-shadow:0 0 0 2px color-mix(in srgb,var(--accent) 45%,transparent)}
/* cards use the shared .sl-card; this app only sizes the bare <h3> inside them */
.sl-card h3{margin:0 0 8px;font-size:var(--t-body)}
.grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}.two{grid-template-columns:1.1fr 1fr}
.pill{display:inline-flex;align-items:center;gap:5px;border:0;border-radius:var(--radius-sm);padding:2px 8px;margin:2px;background:var(--panel-2);color:var(--muted);font-size:var(--t-sm);font-weight:500}

/* ---- document layout (G4): toc | doc | rail ---- */
.doc{display:grid;gap:32px;align-items:start}
.doc.d3{grid-template-columns:200px minmax(0,1fr) 280px}
.doc.d2{grid-template-columns:minmax(0,1fr) 280px}
.doc.d1{grid-template-columns:minmax(0,900px)}
.doc-main{min-width:0;max-width:900px}
.toc{position:sticky;top:0;align-self:start;font-size:var(--t-sm)}
.toc .th{font-size:var(--t-xs);text-transform:uppercase;letter-spacing:.06em;color:var(--muted);font-weight:600;margin:0 0 8px}
.toc a{display:block;padding:4px 8px;border-radius:var(--radius-sm);color:var(--muted);border-left:2px solid transparent}
.toc a:hover{color:var(--ink);background:var(--hover)}
.toc a.active{color:var(--accent);border-left-color:var(--accent);background:var(--accent-weak)}
/* Properties/Relations aside — Notion-quiet (V5): no card box; quiet uppercase group labels,
   the frameless .sl-props--quiet rows, a hairline only BETWEEN groups. The rail is CHROME,
   not document: it pins the UI voice (t-body/1.5) so a document context (the report shell's
   t-md base in the slide-over) never scales the em-sized prop rows off the type scale (T1). */
.rail{position:sticky;top:0;align-self:start;padding-top:8px;font-size:var(--t-body);line-height:1.5}
.rail h4{margin:0 0 8px;padding:0;font-size:var(--t-xs);text-transform:uppercase;letter-spacing:.06em;font-weight:600;color:var(--muted);display:flex;align-items:center;gap:8px}
.rail h4 svg{width:13px;height:13px;color:var(--faint)}
.rail h4:not(:first-child){border-top:1px solid var(--line-2);margin-top:20px;padding-top:16px}
/* .hero h1/.sub now co-located with the _hero component (component-SSR C3) */
/* Markdown tables render with the shared .sl-table (--bordered --zebra) from COMPONENTS_CSS.
   Bridge only the prose spacing + let cells grow inside prose. See docs (Components › Table). */
.sl-prose .sl-table{margin:16px 0}
.sl-prose .sl-table td,.sl-prose .sl-table th{max-width:none}
#favs .favic{display:inline-flex}#favs .favic svg{width:14px;height:14px}
.sec{margin:24px 0 0;padding-top:16px;border-top:1px solid var(--line)}
.sec>h2,.sec>summary{font-size:var(--t-sm);text-transform:uppercase;letter-spacing:.06em;color:var(--muted);margin:0 0 12px;font-weight:600}
details.sec{padding-top:16px}
details.sec>summary{cursor:pointer;list-style:none;display:flex;align-items:center;gap:7px}
details.sec>summary::-webkit-details-marker,details.block>summary.bh::-webkit-details-marker{display:none}
details.sec>summary::before,details.block>summary.bh::before{content:"\\25b8";color:var(--muted);transition:transform 150ms;font-size:var(--t-xs)}
details.sec[open]>summary::before,details.block[open]>summary.bh::before{transform:rotate(90deg)}
.doc-main p{max-width:var(--measure-prose)}.detail{overflow-wrap:break-word}pre{overflow-x:auto;max-width:100%}.detail img{max-width:100%;height:auto}
/* Prose typography is shared by many pages (note/section/synthesis prose) — stays global.
   .es/.eyebrow/.qa-q now live co-located with _study_lead (component-SSR C2/C3). */
/* .sl-prose (the shared design-system prose layer, from COMPONENTS_CSS) + this app's dense
   theme: the --t-* scale, tighter subheadings; the reading measure is the shared
   --measure-prose token (§11 T2 — running prose wraps at ~70ch, left-aligned; the vendored
   layer already caps p/ul/ol/blockquote at the same token). The base elements come from the
   shared layer so they can't drift; only the density deviations live here. */
.sl-prose{font-size:var(--t-prose)}.sl-prose.sm{font-size:var(--t-md);line-height:1.6}
.sl-prose ul,.sl-prose ol{padding-left:22px}
.sl-prose h3{font-size:var(--t-md);margin:22px 0 8px}.sl-prose h4{font-size:var(--t-body);margin:18px 0 6px}
.sl-prose pre code{font-size:var(--t-sm)}
/* Finding/recommendation ROWS are structure, not running prose (§11 T2): they span the
   content measure like every other row; only their inner paragraphs are prose-short. */
.rec{display:grid;grid-template-columns:74px 1fr;gap:12px;align-items:start;padding:12px 0;border-bottom:1px solid var(--line-2)}
.rec:last-child{border-bottom:0}
.prio{display:inline-block;font-size:var(--t-xs);font-weight:700;letter-spacing:.03em;color:#fff;border-radius:var(--radius-sm);padding:3px 7px;text-align:center;white-space:nowrap}
.prio-1{background:#b3493f}.prio-2{background:#a66b1f}.prio-3{background:#2f6f9f}.prio-4{background:#3d7b5f}.prio-5{background:#6d7378}
.srcchip{display:inline-block;font-size:var(--t-xs);color:var(--muted);border:1px solid var(--line);border-radius:var(--radius-sm);padding:1px 6px;margin-left:6px;background:var(--panel-2);white-space:nowrap;max-width:100%;overflow:hidden;text-overflow:ellipsis;vertical-align:bottom}
a.srcchip{text-decoration:none}a.srcchip:hover{border-color:var(--accent);color:var(--ink)}
.xref .xref-role{opacity:.7;font-variant:all-small-caps;letter-spacing:.02em}
.xref-broken{border-style:dashed;color:var(--red);opacity:.75}
/* deep-link arrival: briefly highlight the referenced statement/finding */
.turn-ans:target,.fitem:target,.rec:target{animation:xreflash 2s ease-out 1}
@keyframes xreflash{0%,40%{background:var(--accent-weak);box-shadow:0 0 0 6px var(--accent-weak)}100%{background:transparent;box-shadow:none}}
[id]{scroll-margin-top:70px}
.psolve{padding:8px 0;border-bottom:1px solid var(--line-2)}.psolve:last-child{border-bottom:0}
.psolve p{margin:0}
/* unified finding row (every finding section: key_problem/pain_solver/cluster/segment/ranking/…) */
.fitem{display:flex;justify-content:space-between;align-items:flex-start;gap:12px;padding:8px 0;border-bottom:1px solid var(--line-2)}
.fitem:last-child{border-bottom:0}.fitem .fbody{min-width:0;flex:1}.fitem .fbody p{margin:0}
.fitem .fchips{display:flex;align-items:center;gap:8px;flex-shrink:0}
.segrow{display:grid;grid-template-columns:1fr auto;gap:8px;align-items:start;padding:12px 0;border-bottom:1px solid var(--line-2)}
.segrow:last-child{border-bottom:0}
.srclist{list-style:none;padding:0;margin:0;counter-reset:c}
.srclist li{counter-increment:c;padding:8px 0;border-bottom:1px solid var(--line-2);display:grid;grid-template-columns:24px 1fr;gap:8px;align-items:baseline}
.srclist li:last-child{border-bottom:0}
.srclist li::before{content:counter(c);color:var(--muted);font-variant-numeric:tabular-nums;font-size:var(--t-sm)}

@media (max-width:1040px){.doc.d3{grid-template-columns:minmax(0,1fr)}.doc.d2{grid-template-columns:minmax(0,1fr)}.toc,.rail{position:static;display:none}}
@media (max-width:760px){
  /* .sl-sidebar / .sl-resize mobile behaviour ships in the shared shell layer (COMPONENTS_CSS);
     only the app's content grids collapse here. */
  .grid,.two{grid-template-columns:1fr}
}
@media print{
  .sl-sidebar,.sl-resize,.sl-topbar,.toc,.rail,.sl-tb-actions{display:none!important}
  .sl-app-shell{display:block;height:auto;overflow:visible}.sl-main{overflow:visible}
  section{overflow:visible;padding:0}.doc{display:block}.doc-main{max-width:100%}
  body{background:#fff;color:#000}.sec{break-inside:avoid}
}
"""

HEAD_JS = '<script>try{var t=localStorage.getItem("theme");if(t==="light"||t==="dark")document.documentElement.dataset.theme=t;}catch(e){}</script>'
