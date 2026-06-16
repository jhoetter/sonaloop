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
.rgwrap{position:relative;border:1px solid var(--line);border-radius:var(--radius);overflow:hidden;background:var(--panel)}
#rg{display:block;touch-action:none;cursor:grab}
#rg.grabbing{cursor:grabbing}
.rghint{position:absolute;top:12px;left:12px;font-size:var(--t-xs);color:var(--muted);pointer-events:none;background:color-mix(in srgb,var(--panel) 75%,transparent);padding:3px 8px;border-radius:var(--radius-sm);backdrop-filter:blur(2px)}
.rgn{user-select:none;cursor:pointer}
.rgn>rect:first-of-type{transition:stroke .12s,filter .12s}
.rgn,.rge{transition:opacity .16s}
/* Calm-by-default edges (Linear-style): structural edges quiet at rest, the long dashed loop-backs
   barely-there — relationships light UP on hover/select via .on, dim via .off. */
.rge{transition:opacity .16s,stroke-width .12s;opacity:.42}
.rge.dash{opacity:.16}
.rgel{font-size:var(--t-xs);font-weight:650;fill:var(--muted);paint-order:stroke;stroke:var(--panel);stroke-width:5px;stroke-linejoin:round;opacity:.72;pointer-events:none}
.rgel.off{opacity:.10}.rgel.on{opacity:1;fill:var(--ink)}
.rgn:hover>rect:first-of-type{stroke:var(--accent)}
.rgn.off,.rge.off{opacity:.10}
.rgn.on>rect:first-of-type{stroke:var(--accent)}
.rge.on{opacity:1;stroke-width:3}
.rgn.sel>rect:first-of-type{stroke:var(--accent);stroke-width:2.2;filter:drop-shadow(0 3px 9px color-mix(in srgb,var(--accent) 42%,transparent))}
.rgn.rg-hidden{opacity:.07;pointer-events:none}
/* node label/sub live in a foreignObject — clamp so long titles never bleed out of the card */
.rgn-body{box-sizing:border-box;height:100%;display:flex;flex-direction:column;justify-content:center;overflow:hidden;font-family:inherit;pointer-events:none}
.rgn-title{font-size:var(--t-body);font-weight:600;line-height:1.2;color:var(--ink);display:-webkit-box;-webkit-box-orient:vertical;-webkit-line-clamp:2;line-clamp:2;overflow:hidden;overflow-wrap:anywhere}
.rgn-sub{margin-top:2px;font-size:var(--t-sm);line-height:1.35;color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.rgctrls{position:absolute;left:12px;bottom:12px;display:flex;flex-direction:column;background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);overflow:hidden;box-shadow:0 4px 16px rgba(0,0,0,.12)}
.rgctrls .rgzl{font-size:var(--t-xs);color:var(--muted);text-align:center;padding:3px 0;border-bottom:1px solid var(--line-2);user-select:none}
.rgbtn{width:var(--ctl-sm);height:var(--ctl-sm);display:flex;align-items:center;justify-content:center;border:0;border-bottom:1px solid var(--line-2);background:var(--panel);color:var(--ink);cursor:pointer;font-size:var(--t-md);line-height:1}
.rgbtn:last-child{border-bottom:0}
.rgbtn:hover{background:var(--hover);color:var(--accent)}
.rgmini{position:absolute;right:12px;bottom:12px;width:172px;height:118px;background:color-mix(in srgb,var(--panel) 90%,transparent);border:1px solid var(--line);border-radius:var(--radius);cursor:pointer;box-shadow:0 4px 16px rgba(0,0,0,.12);backdrop-filter:blur(2px)}
.rgmini .mn{fill:var(--muted);opacity:.5}
#rgmvp{fill:color-mix(in srgb,var(--accent) 15%,transparent);stroke:var(--accent);stroke-width:1.3}
.rgdiamond{fill:var(--accent);opacity:.055;stroke:var(--accent);stroke-opacity:.16;stroke-width:1.2}
.rgwrap:not(.groups-on) #rgsections{display:none}
.rgbtn.on{color:var(--accent);background:var(--accent-weak)}
.rgsection{stroke-width:1.5}
.rgsection-phase{fill-opacity:.05;stroke-opacity:.30;stroke-dasharray:none}
.rgphase-guide{stroke:var(--line);stroke-width:1;stroke-dasharray:2 8;opacity:.5}
.rgphase-label{fill:var(--ink);font-size:var(--t-md);font-weight:700;letter-spacing:-.01em}
.rgphase-sub{fill:var(--muted);font-size:var(--t-xs)}
.rground-sep{stroke:var(--line);stroke-width:1;stroke-dasharray:3 7;opacity:.7}
.rground-label{fill:var(--muted);font-size:var(--t-sm);font-weight:700;letter-spacing:.04em;text-transform:uppercase}
/* Linear-style project OUTLINE (primary view) — phase-grouped, collapsible, never overlaps.
   flex:1 0 auto: the outline GROWS to fill a sparse first screen but NEVER shrinks below its
   content — the page (.proj) scrolls as one document. Since UX P2 the outline IS the whole
   page (every primitive is a row in its phase group; the appendix sections retired). */
.outlinecard{flex:1 0 auto;padding:8px 0 40px}
.outline{max-width:900px;margin:0 auto;padding:0 24px 0 58px;position:relative}
.ol-rel-svg{position:absolute;left:18px;top:0;width:34px;height:100%;overflow:visible;pointer-events:none;z-index:2}
.ol-rel-svg path{fill:none;stroke:var(--accent);stroke-width:2.2;opacity:.9;marker-end:url(#olrel-arrow)}
.ol-rel-svg path.ol-rel-in{stroke:var(--muted);opacity:.6;marker-end:none}
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
.outline.is-relating .olrow,.outline.is-relating .sl-file--row{opacity:.58}
.outline.is-relating .olrow.ol-rel-active,.outline.is-relating .sl-file--row.ol-rel-active{opacity:1;background:var(--hover)}
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
/* view toggle (Outline / Graph) */
.rgsection-theme{fill-opacity:0;stroke-opacity:.6;stroke-width:1.6;stroke-dasharray:6 5}
.rgseclab-bg{fill:var(--panel);fill-opacity:.92;stroke-opacity:.55;stroke-width:1.2}
.rgseclab-t{font-size:var(--t-sm);font-weight:700;letter-spacing:.01em}
.rgseclab-k{font-size:var(--t-xs);font-weight:700;text-transform:uppercase;letter-spacing:.07em;fill:var(--muted)}
/* W8 containment: isolation + contain:paint pin the embedded document into its own stacking
   context and clip it hard to the card (overflow + radius) — an iframe can never paint over
   page chrome or an overlay, whatever it renders. */
.protoframe{border:1px solid var(--line);border-radius:var(--radius-lg);overflow:hidden;background:var(--panel);height:620px;box-shadow:0 4px 16px rgba(0,0,0,.08);position:relative;isolation:isolate;contain:paint}
.protoframe iframe{width:100%;height:100%;border:0;display:block}
.strow{padding:8px 0;border-bottom:1px solid var(--line)}.strow:last-child{border-bottom:0}
.strow a{text-decoration:none}.strow .ic{vertical-align:-3px;margin-right:5px}
.ptoolbar{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin:16px 0 8px}
.ptlabel{display:inline-flex;align-items:center;gap:5px;font-size:var(--t-sm);color:var(--muted)}.ptlabel .ic{width:14px;height:14px}
.ptlabel-2{margin-left:8px;padding-left:12px;border-left:1px solid var(--line);opacity:.85}
.rgchip.tagchip{font-size:var(--t-sm);padding:2px 9px;opacity:.82}
.rgchip{border:1px solid var(--line);background:var(--panel);color:var(--ink);border-radius:var(--radius-sm);padding:3px 11px;font-size:var(--t-sm);cursor:pointer;display:inline-flex;align-items:center;gap:6px}
.rgchip::before{content:"";width:8px;height:8px;border-radius:50%;background:var(--c,#9aa0a6)}
.rgchip:hover{background:var(--hover)}
.rgchip.active{border-color:var(--c,var(--accent));background:color-mix(in srgb,var(--c) 14%,var(--panel));font-weight:600}
.rgclear{font-size:var(--t-sm);color:var(--muted);cursor:pointer;text-decoration:underline}
.graphcard{padding:0;border:0;background:none}
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
/* Project detail = full-bleed graph hero */
.sl-main>section:has(.proj){flex:1;min-height:0;padding:0;display:flex;flex-direction:column;overflow:hidden}
.proj{flex:1;min-height:0;display:flex;flex-direction:column;overflow-y:auto}
.proj-head{flex-shrink:0;width:100%;max-width:900px;margin:0 auto;padding:24px 24px 12px}
.proj-head .stats{margin:0 0 12px}
.proj-head .pills{display:flex;flex-wrap:wrap;align-items:center;gap:8px}
.proj-head .ptoolbar{margin:0}
.proj-graph{flex:1;min-height:0;display:flex}
.proj-graph .rgwrap{flex:1;border:0;border-top:1px solid var(--line);border-radius:0}
.proj-graph #rg{height:100%}
.oqpanel{position:fixed;right:24px;bottom:24px;width:380px;max-width:calc(100vw - 320px);max-height:62vh;overflow:auto;background:var(--panel);border:1px solid var(--line);border-radius:var(--radius-lg);box-shadow:0 16px 44px rgba(0,0,0,.22);padding:16px;z-index:60}
.oqp-h{font-size:var(--t-sm);font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:.04em;margin-top:16px}
.oqp-h:first-child{margin-top:0}
.oqpanel .pills{margin:8px 0 16px}
.oqpanel>ul{margin:8px 0 0 16px}

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

_RGRAPH_JS = """<script>
(function(){
  var dataEl=document.getElementById('rgdata'); if(!dataEl) return;
  var D=JSON.parse(dataEl.textContent);
  var svg=document.getElementById('rg'), root=document.getElementById('rgroot'),
      gE=document.getElementById('rgedges'), gN=document.getElementById('rgnodes');
  var NS='http://www.w3.org/2000/svg', NW=320, NH=64, MIN=0.25, MAX=2.6;
  var tx=0, ty=0, scale=1, KEY='rgstate:'+(D.key||'x');
  function el(t,a){ var e=document.createElementNS(NS,t); for(var k in a) e.setAttribute(k,a[k]); return e; }
  // Render a sonaloop-design glyph (icon name -> path body from D.iconpaths) as a nested
  // <svg> at (x,y,size). color drives both stroke (currentColor) and any inline fill.
  function iconEl(name,x,y,size,color){
    var body=(D.iconpaths||{})[name]; if(!body) return null;
    var s=el('svg',{x:x,y:y,width:size,height:size,viewBox:'0 0 24 24',fill:'none',
      stroke:'currentColor','stroke-width':1.9,'stroke-linecap':'round','stroke-linejoin':'round'});
    if(color) s.setAttribute('style','color:'+color);
    s.innerHTML=body; return s;
  }
  var byId={}; D.nodes.forEach(function(n){ byId[n.id]=n; n.dx=n.x; n.dy=n.y; });

  // ---- persistence (per project): node positions, viewport, active filters ----
  // Discard saved positions when the layout algorithm changed (D.lv) so a stale drag
  // layout never masks a new diamond layout.
  var saved=null; try{ saved=JSON.parse(localStorage.getItem(KEY)||'null'); }catch(_){}
  if(saved && saved.lv !== D.lv) saved=null;
  if(saved&&saved.pos) D.nodes.forEach(function(n){ var p=saved.pos[n.id]; if(p){ n.x=p[0]; n.y=p[1]; } });
  var saveT=null;
  function writeNow(){ if(saveT){ clearTimeout(saveT); saveT=null; }
    var pos={}; D.nodes.forEach(function(n){ pos[n.id]=[Math.round(n.x),Math.round(n.y)]; });
    var f=[]; document.querySelectorAll('.rgchip.active').forEach(function(c){ f.push(c.getAttribute('data-theme')); });
    try{ localStorage.setItem(KEY,JSON.stringify({lv:D.lv,pos:pos,view:{tx:tx,ty:ty,scale:scale},filter:f})); }catch(_){}
  }
  function save(){ if(saveT) return; saveT=setTimeout(writeNow,250); }   // debounced (continuous gestures)
  // Flush any pending write before the page goes away, so a quick refresh never loses a change.
  window.addEventListener('pagehide',function(){ if(saveT) writeNow(); });
  document.addEventListener('visibilitychange',function(){ if(document.visibilityState==='hidden'&&saveT) writeNow(); });

  var zl=document.getElementById('rgzl'), bgp=document.getElementById('rggrid');
  function applyT(){ root.setAttribute('transform','translate('+tx+','+ty+') scale('+scale+')');
    if(bgp) bgp.setAttribute('patternTransform','translate('+tx+' '+ty+') scale('+scale+')');
    if(zl) zl.textContent=Math.round(scale*100)+'%'; drawMini(); }

  // ---- diamond silhouettes (methodology layout) ----
  var gD=document.getElementById('rgdia');
  if(gD && D.diamonds){ D.diamonds.forEach(function(poly){
    gD.appendChild(el('polygon',{points: poly.map(function(p){return p[0]+','+p[1];}).join(' '),'class':'rgdiamond'})); }); }

  // ---- section overlays (methodology-independent groupings) ----
  // ---- Q3: phase-column headers + faint guides (the left→right flow, made explicit) ----
  var gP=document.getElementById('rgphases');
  if(gP && D.phases && D.phases.length){
    var ys=D.nodes.map(function(n){return n.y;}); var ymin=Math.min.apply(null,ys.concat([0]))-80;
    var ymax=Math.max.apply(null,ys.concat([0]))+160;
    D.phases.forEach(function(p){
      var ln=el('line',{x1:p.x,y1:ymin,x2:p.x,y2:ymax,'class':'rgphase-guide'}); gP.appendChild(ln);
      var t=el('text',{x:p.x,y:p.top,'class':'rgphase-label','text-anchor':'middle'});
      t.textContent=p.i+'. '+p.label; gP.appendChild(t);
      var g=el('text',{x:p.x,y:p.top+18,'class':'rgphase-sub','text-anchor':'middle'});
      g.textContent=p.sub || (p.is_fan?'divergieren':'konvergieren'); gP.appendChild(g);
      var gw=0; try{gw=g.getComputedTextLength();}catch(_){}
      var gi=iconEl(p.is_fan?'diamond':'diamondFilled', p.x-gw/2-15, p.top+18-9, 11);
      if(gi) gP.appendChild(gi);
    });
  }
  // ---- iteration swimlanes: "Runde N" labels + faint separators between rounds (only if looped) ----
  var gR=document.getElementById('rgrounds');
  if(gR && D.rounds && D.rounds.length>1){
    var xs2=D.nodes.map(function(n){return n.x;});
    var xmn=Math.min.apply(null,xs2.concat([0]))-44, xmx=Math.max.apply(null,xs2.concat([0]))+300;
    D.rounds.forEach(function(r,idx){
      if(idx>0){ var midY=(r.y+D.rounds[idx-1].y)/2;
        var ln=el('line',{x1:xmn,y1:midY,x2:xmx,y2:midY,'class':'rground-sep'}); gR.appendChild(ln); }
      var lab=el('text',{x:xmn,y:r.y-4,'class':'rground-label'}); lab.textContent=r.label; gR.appendChild(lab);
    });
  }
  var gS=document.getElementById('rgsections');
  if(gS && D.sections){ D.sections.forEach(function(s){
    var pts=s.poly.map(function(p){return p[0]+','+p[1];}).join(' ');
    var cls='rgsection '+(s.phase?'rgsection-phase':'rgsection-theme');
    var poly=el('polygon',{points:pts,'class':cls,style:'fill:'+s.color+';stroke:'+s.color});
    poly.setAttribute('data-section', s.id); gS.appendChild(poly);
    // Group label as a readable PILL floating just above the hull's top-left, so it
    // never overlaps the nodes inside the group (it used to sit on the first node).
    var chip=el('g',{'class':'rgseclab'}); gS.appendChild(chip);
    var PADX=10, CH=24, cx=PADX;
    var rect=el('rect',{x:0,y:0,height:CH,rx:8,'class':'rgseclab-bg',style:'stroke:'+s.color}); chip.appendChild(rect);
    if(s.glyph){ var si=iconEl(s.glyph, cx, CH/2-7, 14, s.color); if(si){ chip.appendChild(si); cx+=19; } }
    var lab=el('text',{x:cx,y:CH/2,'class':'rgseclab-t','dominant-baseline':'central',style:'fill:'+s.color});
    lab.textContent=s.label; chip.appendChild(lab);
    var lw=0; try{lw=lab.getComputedTextLength();}catch(_){} cx+=lw;
    if(s.kind){ cx+=8; var k=el('text',{x:cx,y:CH/2,'class':'rgseclab-k','dominant-baseline':'central'});
      k.textContent=s.kind; chip.appendChild(k); var kw=0; try{kw=k.getComputedTextLength();}catch(_){} cx+=kw; }
    rect.setAttribute('width', cx+PADX);
    chip.setAttribute('transform','translate('+(s.lx+4)+','+(s.ly-CH-6)+')');
  }); }

  // ---- edges (bezier, depth-aware) ----
  var edgeEls=[];
  D.edges.forEach(function(ed){
    var a={fill:'none',stroke:ed.color,'stroke-width':'2','marker-end':'url(#rgah-'+ed.mid+')','class':ed.dashed?'rge dash':'rge'};
    if(ed.dashed){a['stroke-dasharray']='6 5'; a['stroke-width']='1.6';}
    var p=el('path',a); gE.appendChild(p);
    var txt=null;
    if(ed.label){ txt=el('text',{'class':'rgel','text-anchor':'middle'}); txt.textContent=ed.label; gE.appendChild(txt); }
    edgeEls.push({ed:ed,p:p,t:txt});
  });
  function route(){ edgeEls.forEach(function(o){ var a=byId[o.ed.from], b=byId[o.ed.to]; if(!a||!b) return;
    o.p.style.display=(a.hidden||b.hidden)?'none':'';
    if(o.t) o.t.style.display=(a.hidden||b.hidden)?'none':'';
    var aw=a.w||NW, ah=a.h||NH, bw=b.w||NW, bh=b.h||NH;
    var sx,sy,ex,ey,d,lx,ly;
    if(Math.abs(b.x-a.x)<NW*0.6){
      sx=a.x+aw/2; ex=b.x+bw/2;
      if(b.y>=a.y){ sy=a.y+ah; ey=b.y; } else { sy=a.y; ey=b.y+bh; }
      var cv=(ey-sy)*0.5; d='M'+sx+' '+sy+' C '+sx+' '+(sy+cv)+' '+ex+' '+(ey-cv)+' '+ex+' '+ey;
      lx=(sx+ex)/2+18; ly=(sy+ey)/2;
    } else {
      if(b.x>=a.x){ sx=a.x+aw; ex=b.x; } else { sx=a.x; ex=b.x+bw; }
      sy=a.y+ah/2; ey=b.y+bh/2; var ch=(ex-sx)*0.5;
      d='M'+sx+' '+sy+' C '+(sx+ch)+' '+sy+' '+(ex-ch)+' '+ey+' '+ex+' '+ey;
      lx=(sx+ex)/2; ly=(sy+ey)/2-7;
    }
    o.p.setAttribute('d',d);
    if(o.t){ o.t.setAttribute('x',lx); o.t.setAttribute('y',ly); }
  }); drawMini(); }

  // ---- theme filter ----
  function applyFilter(){ var act=[]; document.querySelectorAll('.rgchip.active').forEach(function(c){ act.push(c.getAttribute('data-theme')); });
    D.nodes.forEach(function(n){ var show=!act.length||(n.tags||[]).some(function(t){ return act.indexOf(t)>=0; }); n.hidden=!show; if(n.el) n.el.classList.toggle('rg-hidden',!show); });
    var clr=document.querySelector('.rgclear'); if(clr) clr.style.display=act.length?'':'none'; route(); writeNow(); }
  document.addEventListener('click',function(e){ var chip=e.target.closest&&e.target.closest('.rgchip'); if(chip){ chip.classList.toggle('active'); applyFilter(); return; } var clr=e.target.closest&&e.target.closest('.rgclear'); if(clr){ document.querySelectorAll('.rgchip.active').forEach(function(c){c.classList.remove('active');}); applyFilter(); } });

  // ---- neighborhood highlight + selection ----
  function neigh(id){ var s={}; s[id]=1; D.edges.forEach(function(e){ if(e.from===id)s[e.to]=1; if(e.to===id)s[e.from]=1; }); return s; }
  function highlight(id){ if(!id){ D.nodes.forEach(function(n){ n.el.classList.remove('on','off'); }); edgeEls.forEach(function(o){ o.p.classList.remove('on','off'); if(o.t)o.t.classList.remove('on','off'); }); return; }
    var nb=neigh(id);
    D.nodes.forEach(function(n){ var on=!!nb[n.id]; n.el.classList.toggle('on',on); n.el.classList.toggle('off',!on); });
    edgeEls.forEach(function(o){ var on=(o.ed.from===id||o.ed.to===id); o.p.classList.toggle('on',on); o.p.classList.toggle('off',!on); if(o.t){o.t.classList.toggle('on',on); o.t.classList.toggle('off',!on);} }); }
  var selId=null;
  function select(id){ selId=id; D.nodes.forEach(function(n){ n.el.classList.toggle('sel',n.id===id); }); highlight(id); }
  function deselect(){ selId=null; D.nodes.forEach(function(n){ n.el.classList.remove('sel'); }); highlight(null); }

  // ---- nodes ----
  D.nodes.forEach(function(n){
    var W=n.w||NW, H=n.h||NH;
    var g=el('g',{'class':'rgn'+(n.proto?' proto':''),transform:'translate('+n.x+','+n.y+')'});
    var rectAttrs={width:W,height:H,rx:10,fill:'var(--panel)',stroke:(n.proto?n.color:'var(--line)'),'stroke-width':'1.4'};
    if(n.proto){ rectAttrs['stroke-dasharray']='6 4'; }
    g.appendChild(el('rect',rectAttrs));
    g.appendChild(el('rect',{width:5,height:H,rx:2.5,fill:n.color}));
    // Title + sub live in a foreignObject so long labels clamp/ellipsize INSIDE the
    // card instead of overflowing into neighbours (raw <text> doesn't clip). The glyph
    // and external-link icons stay as SVG overlays, vertically centred.
    var padL=14;
    if(n.glyph){ var ni=iconEl(n.glyph, 14, H/2-7, 15, n.color); if(ni){ g.appendChild(ni); padL=37; } }
    var padR=(n.ext?24:12);
    var fo=el('foreignObject',{x:padL,y:0,width:Math.max(12,W-padL-padR),height:H,'pointer-events':'none'});
    var XH='http://www.w3.org/1999/xhtml';
    var box=document.createElementNS(XH,'div'); box.setAttribute('class','rgn-body');
    var a=document.createElementNS(XH,'div'); a.setAttribute('class','rgn-title'); a.textContent=n.label; box.appendChild(a);
    if(n.sub){ var b=document.createElementNS(XH,'div'); b.setAttribute('class','rgn-sub'); b.textContent=n.sub; box.appendChild(b); }
    fo.appendChild(box); g.appendChild(fo);
    if(n.ext){ var ei=iconEl('external', W-20, 8, 12, 'var(--muted)'); if(ei) g.appendChild(ei); }
    gN.appendChild(g); n.el=g;
    var down=null,moved=false;
    g.addEventListener('pointerdown',function(e){ e.stopPropagation(); down={x:e.clientX,y:e.clientY,nx:n.x,ny:n.y}; moved=false; gN.appendChild(g); try{g.setPointerCapture(e.pointerId);}catch(_){} });
    g.addEventListener('pointermove',function(e){ if(!down) return; var dx=(e.clientX-down.x)/scale, dy=(e.clientY-down.y)/scale; if(Math.abs(dx)+Math.abs(dy)>3) moved=true; n.x=down.nx+dx; n.y=down.ny+dy; g.setAttribute('transform','translate('+n.x+','+n.y+')'); route(); });
    g.addEventListener('pointerup',function(e){ if(down){ if(!moved){ if(selId===n.id) location.href=n.href; else select(n.id); } else writeNow(); } down=null; });
    g.addEventListener('dblclick',function(e){ e.preventDefault(); location.href=n.href; });
    g.addEventListener('pointerenter',function(){ if(!selId&&!down) highlight(n.id); });
    g.addEventListener('pointerleave',function(){ if(!selId&&!down) highlight(null); });
  });

  // ---- view transforms ----
  function go(nx,ny,ns,anim){ ns=Math.max(MIN,Math.min(MAX,ns)); if(!anim){ tx=nx; ty=ny; scale=ns; applyT(); save(); return; }
    var ox=tx,oy=ty,os=scale,t0=null;
    function step(ts){ if(t0===null)t0=ts; var k=Math.min(1,(ts-t0)/300), e=1-Math.pow(1-k,3); tx=ox+(nx-ox)*e; ty=oy+(ny-oy)*e; scale=os+(ns-os)*e; applyT(); if(k<1) requestAnimationFrame(step); else save(); }
    requestAnimationFrame(step); }
  function zoomAt(cx,cy,f){ var ns=Math.max(MIN,Math.min(MAX,scale*f)); tx=cx-(cx-tx)*(ns/scale); ty=cy-(cy-ty)*(ns/scale); scale=ns; applyT(); save(); }
  function bbox(vis){ var mnx=1e9,mny=1e9,mxx=-1e9,mxy=-1e9,any=false;
    D.nodes.forEach(function(n){ if(vis&&n.hidden) return; any=true; mnx=Math.min(mnx,n.x); mny=Math.min(mny,n.y); mxx=Math.max(mxx,n.x+(n.w||NW)); mxy=Math.max(mxy,n.y+(n.h||NH)); });
    if(!any) return bbox(false); return {x:mnx,y:mny,X:mxx,Y:mxy}; }
  function fit(anim){ var r=svg.getBoundingClientRect(); if(!r.width) return; var b=bbox(true), pad=64; var bw=Math.max(1,b.X-b.x), bh=Math.max(1,b.Y-b.y);
    var s=Math.max(MIN,Math.min(MAX,Math.min((r.width-pad*2)/bw,(r.height-pad*2)/bh)));
    go((r.width-bw*s)/2-b.x*s,(r.height-bh*s)/2-b.y*s,s,anim); }
  function resetLayout(){ D.nodes.forEach(function(n){ n.x=n.dx; n.y=n.dy; n.el.setAttribute('transform','translate('+n.x+','+n.y+')'); });
    try{ localStorage.removeItem(KEY); }catch(_){}
    document.querySelectorAll('.rgchip.active').forEach(function(c){ c.classList.remove('active'); });
    deselect(); applyFilter(); fit(true); }

  // ---- control buttons ----
  var ctrls=document.querySelector('.rgctrls');
  if(ctrls) ctrls.addEventListener('click',function(e){ var btn=e.target.closest('.rgbtn'); if(!btn) return; var a=btn.getAttribute('data-act'), r=svg.getBoundingClientRect();
    if(a==='zin') zoomAt(r.width/2,r.height/2,1.25); else if(a==='zout') zoomAt(r.width/2,r.height/2,0.8); else if(a==='fit') fit(true); else if(a==='reset') resetLayout(); else if(a==='groups'){ var w=svg.closest('.rgwrap'); if(w){ var on=w.classList.toggle('groups-on'); btn.classList.toggle('on',on); } } });

  // ---- background pan + wheel/trackpad ----
  var pan=null;
  svg.addEventListener('pointerdown',function(e){ if(e.target.closest('.rgn')) return; pan={x:e.clientX,y:e.clientY,tx:tx,ty:ty,moved:false,pid:e.pointerId}; svg.classList.add('grabbing'); try{svg.setPointerCapture(e.pointerId);}catch(_){} });
  svg.addEventListener('pointermove',function(e){ if(!pan) return; if(Math.abs(e.clientX-pan.x)+Math.abs(e.clientY-pan.y)>3) pan.moved=true; tx=pan.tx+(e.clientX-pan.x); ty=pan.ty+(e.clientY-pan.y); applyT(); });
  function endPan(){ if(!pan) return; if(!pan.moved&&selId) deselect(); else if(pan.moved) writeNow(); try{svg.releasePointerCapture(pan.pid);}catch(_){} svg.classList.remove('grabbing'); pan=null; }
  svg.addEventListener('pointerup',endPan); svg.addEventListener('pointercancel',endPan); window.addEventListener('pointerup',endPan);
  // Detect a trackpad ONCE per session and latch it, so the same device never flip-flops
  // between "two-finger pan" and "mouse-wheel zoom" tick to tick (the main source of jumpiness).
  var trackpadSeen=false;
  svg.addEventListener('wheel',function(e){ e.preventDefault(); var r=svg.getBoundingClientRect(), mx=e.clientX-r.left, my=e.clientY-r.top;
    if(e.ctrlKey){ zoomAt(mx,my,Math.exp(-e.deltaY*0.01)); return; }              // pinch / ctrl+wheel = zoom to cursor
    if(e.shiftKey){ tx-=e.deltaY; applyT(); save(); return; }                      // shift+wheel = horizontal pan
    if(e.deltaX!==0 || !Number.isInteger(e.deltaY)) trackpadSeen=true;             // latch on any trackpad signal
    if(trackpadSeen){ tx-=e.deltaX; ty-=e.deltaY; applyT(); save(); }              // two-finger scroll = pan
    else { zoomAt(mx,my,e.deltaY<0?1.12:0.892); }                                  // mouse wheel = zoom to cursor
  },{passive:false});

  // ---- keyboard ----
  window.addEventListener('keydown',function(e){ if(e.metaKey||e.ctrlKey||e.altKey) return; var ae=document.activeElement; if(ae&&/input|textarea|select/i.test(ae.tagName)) return; var r=svg.getBoundingClientRect();
    if(e.key==='+'||e.key==='=') zoomAt(r.width/2,r.height/2,1.25);
    else if(e.key==='-'||e.key==='_') zoomAt(r.width/2,r.height/2,0.8);
    else if(e.key==='0'||e.key==='f'||e.key==='F') fit(true);
    else if(e.key==='r'||e.key==='R') resetLayout();
    else if(e.key==='Escape') deselect();
    else if(e.key==='Enter'&&selId){ location.href=byId[selId].href; }
    else if(e.key==='ArrowLeft'){ tx+=40; applyT(); save(); }
    else if(e.key==='ArrowRight'){ tx-=40; applyT(); save(); }
    else if(e.key==='ArrowUp'){ ty+=40; applyT(); save(); }
    else if(e.key==='ArrowDown'){ ty-=40; applyT(); save(); }
    else return; e.preventDefault(); });

  // ---- minimap ----
  // Scale to the union of node bbox + current viewport so the viewport rectangle
  // always fits inside the minimap and stays accurate at any zoom level.
  var mini=document.getElementById('rgmini'), gMN=document.getElementById('rgmnodes'), vp=document.getElementById('rgmvp');
  var MMW=172, MMH=118, mm={s:1,ox:0,oy:0};
  function drawMini(){ if(!mini) return;
    var b=bbox(false), r=svg.getBoundingClientRect(), hasV=r.width>0, vx,vy,vw,vh;
    if(hasV){ vx=(-tx)/scale; vy=(-ty)/scale; vw=r.width/scale; vh=r.height/scale;
      b={x:Math.min(b.x,vx),y:Math.min(b.y,vy),X:Math.max(b.X,vx+vw),Y:Math.max(b.Y,vy+vh)}; }
    var pad=10, bw=Math.max(1,b.X-b.x), bh=Math.max(1,b.Y-b.y);
    var s=Math.min((MMW-pad*2)/bw,(MMH-pad*2)/bh);
    var ox=pad+((MMW-pad*2)-bw*s)/2-b.x*s, oy=pad+((MMH-pad*2)-bh*s)/2-b.y*s; mm={s:s,ox:ox,oy:oy};
    while(gMN.firstChild) gMN.removeChild(gMN.firstChild);
    D.nodes.forEach(function(n){ if(n.hidden) return; gMN.appendChild(el('rect',{'class':'mn',x:ox+n.x*s,y:oy+n.y*s,width:NW*s,height:NH*s,rx:1.5})); });
    if(hasV){ vp.style.display=''; vp.setAttribute('x',ox+vx*s); vp.setAttribute('y',oy+vy*s); vp.setAttribute('width',Math.max(3,vw*s)); vp.setAttribute('height',Math.max(3,vh*s)); vp.setAttribute('rx',3); } }
  function miniCenter(e){ var r=mini.getBoundingClientRect(); var cx=((e.clientX-r.left)*(MMW/r.width)-mm.ox)/mm.s, cy=((e.clientY-r.top)*(MMH/r.height)-mm.oy)/mm.s; var sr=svg.getBoundingClientRect(); tx=sr.width/2-cx*scale; ty=sr.height/2-cy*scale; applyT(); save(); }
  if(mini){ var md=null;
    mini.addEventListener('pointerdown',function(e){ md={x:e.clientX,y:e.clientY}; try{mini.setPointerCapture(e.pointerId);}catch(_){} miniCenter(e); md.x=e.clientX; md.y=e.clientY; });
    mini.addEventListener('pointermove',function(e){ if(!md) return; var r=mini.getBoundingClientRect(); var dcx=(e.clientX-md.x)*(MMW/r.width)/mm.s, dcy=(e.clientY-md.y)*(MMH/r.height)/mm.s; tx-=dcx*scale; ty-=dcy*scale; md.x=e.clientX; md.y=e.clientY; applyT(); save(); });
    window.addEventListener('pointerup',function(){ md=null; }); }

  window.addEventListener('resize',function(){ applyT(); });

  // ---- init: restore filter chips, then viewport (saved or fit) ----
  if(saved&&saved.filter&&saved.filter.length) saved.filter.forEach(function(th){ try{ var sel='.rgchip[data-theme="'+(window.CSS&&CSS.escape?CSS.escape(th):th)+'"]'; var c=document.querySelector(sel); if(c) c.classList.add('active'); }catch(_){} });
  applyFilter();
  if(saved&&saved.view){ tx=saved.view.tx; ty=saved.view.ty; scale=saved.view.scale; applyT(); } else { fit(false); }
})();
</script>"""
