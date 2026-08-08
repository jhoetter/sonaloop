"""Co-located presentation contracts for the bilingual documentation hub.

Kept separate from :mod:`_docs_content` so the large, pure-data catalogue
and its styles both remain within the repository's module-size budget.
"""
from __future__ import annotations

from ._html import register_css

register_css(r"""
/* ==== Documentation hub: the standard page header (eyebrow/.h1/.lead — W7) + tabs in the measure ==== */
.doc-head{margin-bottom:2px}
.doc-head .h1{display:flex;align-items:center;gap:12px}
.doc-tabs{margin:8px 0 24px}
.doc-p{color:var(--muted);font-size:var(--t-body);line-height:1.6;margin:0 0 16px;max-width:74ch}
.doc-p strong{color:var(--ink)}
.doc-p p{margin:0;max-width:none}
.doc-note{color:var(--ink);font-size:var(--t-sm);background:var(--panel-2);border:1px solid var(--line-2);border-radius:var(--radius-md,10px);padding:11px 14px;max-width:74ch}
.doc-note p,.doc-note{margin:0}

/* ==== Documentation: two-column wrap + sticky on-this-page rail ==== */
.doc-wrap{display:flex;align-items:flex-start;gap:38px;margin-top:18px}
.doc-main{flex:1;min-width:0}.doc-main.wide{margin-top:18px}
.doc-main [id]{scroll-margin-top:16px}
.doc-toc{width:188px;flex-shrink:0;position:sticky;top:14px}
.toc-nav{display:flex;flex-direction:column;gap:2px;border-left:1px solid var(--line);padding-left:14px}
.toc-lbl{font-size:var(--t-xs,11px);font-weight:700;letter-spacing:.05em;text-transform:uppercase;color:var(--faint);margin-bottom:6px}
.toc-nav a{color:var(--muted);font-size:var(--t-sm);text-decoration:none;padding:4px 0;transition:color 110ms}
.toc-nav a:hover{color:var(--ink)}
.doc-block{margin-top:38px}.doc-block:first-child{margin-top:0}
.doc-sub-h{font-size:var(--t-md);font-weight:650;letter-spacing:-.01em;margin:0 0 12px}

/* ==== Overview: principle tiles + landing cards ==== */
.principles{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:14px}
.ptile-ic{color:var(--accent);margin-bottom:9px}
.ptile-t{font-weight:650;font-size:var(--t-md);letter-spacing:-.01em;margin-bottom:5px}
.ptile-b{color:var(--muted)}.ptile-b p{margin:0;max-width:none}
.navgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:12px}
.navcard{display:flex;flex-direction:column;gap:8px;text-decoration:none;transition:border-color 120ms,box-shadow 120ms}
.navcard:hover{border-color:var(--accent);box-shadow:0 1px 3px rgba(0,0,0,.04)}
.navcard-ic{color:var(--accent)}
.navcard-t{font-weight:650;font-size:var(--t-md);letter-spacing:-.01em;color:var(--ink)}
.navcard-b{color:var(--muted);font-size:var(--t-sm);line-height:1.5}

/* ==== Concepts: one dense grid, role shown as a per-card tag ==== */
.concept-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:14px;align-items:start}
.doccard{display:flex;flex-direction:column;text-decoration:none;color:inherit;transition:border-color 120ms,box-shadow 120ms}
.doccard:hover{border-color:var(--accent);box-shadow:0 1px 3px rgba(0,0,0,.04)}
.doccard:hover .doc-open{color:var(--accent)}
.doc-open{margin-top:12px;padding-top:10px;border-top:1px dashed var(--line-2);font-size:var(--t-xs,11px);font-weight:600;text-transform:uppercase;letter-spacing:.04em;color:var(--faint);transition:color 120ms}
.doc-h{display:flex;align-items:center;gap:9px;margin-bottom:8px}
.rico{display:inline-flex;align-items:center;justify-content:center;flex-shrink:0;width:28px;height:28px;border-radius:var(--radius-sm);background:var(--panel-2)}
.doc-h .rico svg{width:17px;height:17px}
.doc-name{font-size:var(--t-md);font-weight:650;letter-spacing:-.01em;flex:1;min-width:0}
.doc-gtag{display:inline-flex;align-items:center;gap:5px;flex-shrink:0;font-size:var(--t-xs,11px);font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:.03em}
.doc-gdot{width:6px;height:6px;border-radius:50%;flex-shrink:0}
.doc-what{color:var(--ink);line-height:1.6}.doc-what p{margin:0;max-width:none}
.doc-why{margin-top:11px;padding-top:10px;border-top:1px solid var(--line-2);font-size:var(--t-sm);color:var(--muted);line-height:1.5}
.doc-why-lbl{display:block;font-size:var(--t-xs,11px);font-weight:700;letter-spacing:.04em;text-transform:uppercase;color:var(--faint);margin-bottom:3px}
.doc-why strong{color:var(--ink)}
/* ==== Concepts: data-model (three layers + five primitives w/ JSON) ==== */
.rico.lg{width:34px;height:34px}.rico.lg svg{width:20px;height:20px}
.doc-code{margin:0;background:var(--panel-2);border:1px solid var(--line-2);border-radius:var(--radius-md,10px);padding:13px 15px;overflow-x:auto}
.doc-code code{font-family:var(--mono,'Geist Mono',monospace);font-size:var(--t-xs,12px);line-height:1.6;color:var(--ink);white-space:pre;background:none;border:0;padding:0}
.dl-layers{display:flex;flex-direction:column;gap:2px;margin-top:6px}
.dl-layer{display:flex;gap:14px;padding:12px 0;border-bottom:1px solid var(--line-2)}
.dl-layer:last-child{border-bottom:0}
.dl-layer-n{flex-shrink:0;width:26px;height:26px;border-radius:50%;background:var(--panel-2);color:var(--accent);font-weight:650;font-size:var(--t-sm);display:flex;align-items:center;justify-content:center}
.dl-layer-main{min-width:0}
.dl-layer-t{font-weight:650;font-size:var(--t-md);letter-spacing:-.01em;margin-bottom:3px}
.dl-layer-b{color:var(--muted)}.dl-layer-b p{margin:0;max-width:none}
.prim-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:12px}

.prim-card-h{margin-bottom:6px}
.prim-card-n{font-family:var(--mono,'Geist Mono',monospace);font-size:var(--t-sm);font-weight:700;color:var(--accent)}
.prim-card-d{color:var(--muted);font-size:var(--t-sm);line-height:1.5;margin-bottom:10px}
.prim-chips{display:flex;flex-wrap:wrap;gap:7px}
.prim-chip{font-family:var(--mono,'Geist Mono',monospace);font-size:var(--t-sm);font-weight:600;color:var(--accent);background:var(--panel-2);border:1px solid var(--line-2);border-radius:20px;padding:3px 11px;text-decoration:none;transition:border-color 110ms}
.prim-chip:hover{border-color:var(--accent)}

/* ==== How it works: lifecycle pipeline ==== */
.flow{display:flex;align-items:stretch;gap:0;flex-wrap:wrap;margin-top:6px}
.flow-stage{flex:1 1 150px;min-width:140px;border:1px solid var(--line);border-radius:var(--radius-md,10px);padding:14px 15px;background:var(--panel);display:flex;flex-direction:column;gap:4px}
.flow-stage.wide{flex:1.3 1 180px;border-color:var(--accent);background:color-mix(in srgb,var(--accent) 5%,var(--panel))}
.flow-ic{display:inline-flex;color:var(--accent);margin-bottom:4px}.flow-ic svg{width:19px;height:19px}
.flow-t{font-weight:650;font-size:var(--t-md);letter-spacing:-.01em}
.flow-s{color:var(--muted);font-size:var(--t-sm);line-height:1.5}
.flow-pills{display:flex;flex-wrap:wrap;gap:5px;margin-top:8px}
.flow-pill{display:inline-flex;align-items:center;gap:4px;font-size:var(--t-xs,11px);font-weight:500;color:var(--ink);background:var(--panel);border:1px solid var(--line-2);border-radius:20px;padding:2px 9px}
.flow-pill svg{width:12px;height:12px;color:var(--accent)}
.flow-arrow{display:flex;align-items:center;justify-content:center;color:var(--faint);font-size:19px;padding:0 9px;flex-shrink:0}
.flow-loop{margin-top:12px;font-size:var(--t-sm);color:var(--accent);font-weight:500;text-align:center;background:var(--panel-2);border:1px dashed var(--line);border-radius:20px;padding:7px 14px}

/* ==== How it works: rigour cycle ==== */
.cyc{display:flex;align-items:stretch;gap:0;flex-wrap:wrap;margin-top:6px}
.cyc-step{flex:1 1 180px;min-width:160px;border:1px solid var(--line-2);border-radius:var(--radius-md,10px);padding:14px 15px;background:var(--panel-2)}
.cyc-n{width:24px;height:24px;border-radius:50%;background:var(--panel);border:1px solid var(--line);color:var(--accent);font-weight:650;font-size:var(--t-sm);display:flex;align-items:center;justify-content:center;margin-bottom:8px}
.cyc-t{font-weight:650;font-size:var(--t-md);letter-spacing:-.01em;margin-bottom:4px}
.cyc-b{color:var(--muted);font-size:var(--t-sm);line-height:1.5}
.flow-arrow.loopback{font-size:22px;color:var(--accent)}

/* ==== Methodology: catalogue cards + DD phases + recipes ==== */
.methgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:14px}

.methcard-h{display:flex;align-items:baseline;justify-content:space-between;gap:8px;margin-bottom:6px}
.methcard-n{font-weight:650;font-size:var(--t-md);letter-spacing:-.01em}
.methcard-c{font-size:var(--t-xs,11px);color:var(--faint);font-weight:600;flex-shrink:0}
.methcard-d{color:var(--muted);font-size:var(--t-sm);line-height:1.5;margin-bottom:10px}
.methcard-when{color:var(--faint);font-size:var(--t-sm);line-height:1.5;margin-bottom:10px}
.methcard-when b{color:var(--muted);font-weight:600}
.step-pills{display:flex;flex-wrap:wrap;gap:5px}
.step-pill{font-size:var(--t-xs,11px);color:var(--ink);background:var(--panel-2);border:1px solid var(--line-2);border-radius:20px;padding:2px 9px}
.ddphases{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;margin-top:6px}
.ddphase{border:1px solid var(--line-2);border-radius:var(--radius-md,10px);padding:13px 15px;background:var(--panel);border-top:3px solid var(--line)}
.ddphase.diverge{border-top-color:var(--accent)}
.ddphase.converge{border-top-color:var(--amber,#d08700)}
.dd-rhythm{font-size:var(--t-xs,11px);font-weight:700;letter-spacing:.05em;text-transform:uppercase;color:var(--faint)}
.dd-name{font-weight:650;font-size:var(--t-md);letter-spacing:-.01em;margin:3px 0 6px}
.dd-intent{color:var(--muted)}.dd-intent p{margin:0;max-width:none}
.plays{display:flex;flex-direction:column;gap:0}
.play{display:flex;gap:16px;align-items:baseline;padding:11px 0;border-bottom:1px solid var(--line-2)}
.play:last-child{border-bottom:0}
.play-l{flex-shrink:0;min-width:210px;display:flex;flex-direction:column;gap:2px}
.play-name{font-weight:600;font-size:var(--t-sm);color:var(--ink)}
.play-code{font-family:var(--mono,'Geist Mono',monospace);font-size:var(--t-xs,11px);color:var(--accent)}
.play-desc{color:var(--muted);font-size:var(--t-sm);line-height:1.6}.play-desc strong{color:var(--ink)}

/* ==== MCP reference: two-level taxonomy (super-group index → domains → tools) ==== */
.mcp-superindex{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:12px;margin:22px 0 8px}

.mcp-super-card-h{display:flex;align-items:baseline;justify-content:space-between;gap:8px}
.mcp-super-card-t{font-weight:650;font-size:var(--t-md);letter-spacing:-.01em}
.mcp-super-card-n{flex-shrink:0;font-size:var(--t-xs,11px);font-weight:700;color:var(--accent);background:var(--panel-2);border-radius:20px;padding:1px 8px}
.mcp-super-card-d{color:var(--muted);font-size:var(--t-sm);line-height:1.5;margin:4px 0 10px}
.mcp-pills{display:flex;flex-wrap:wrap;gap:6px}
.mcp-pill{display:inline-flex;align-items:center;gap:5px;font-size:var(--t-xs,11px);font-weight:500;color:var(--ink);background:var(--panel-2);border:1px solid var(--line-2);border-radius:20px;padding:2px 9px;text-decoration:none;transition:border-color 110ms}
.mcp-pill:hover{border-color:var(--accent)}
.mcp-pill-c{color:var(--faint);font-weight:700}
.mcp-super{margin-top:44px;scroll-margin-top:16px}
.mcp-super-h{font-size:var(--t-lg);font-weight:650;letter-spacing:-.02em;margin:0 0 4px;padding-bottom:10px;border-bottom:2px solid var(--line)}
.mcp-domain{margin-top:26px;scroll-margin-top:16px}
.mcp-domain-h{display:flex;align-items:baseline;gap:10px;margin-bottom:11px}
.mcp-domain-t{font-size:var(--t-md);font-weight:650;letter-spacing:-.01em}
.mcp-domain-c{flex-shrink:0;font-size:var(--t-xs,11px);font-weight:700;color:var(--accent);background:var(--panel-2);border-radius:20px;padding:1px 8px}
.mcp-domain-d{color:var(--muted);font-size:var(--t-sm)}
.mcp-tools{display:grid;grid-template-columns:repeat(auto-fill,minmax(330px,1fr));gap:8px}
.mcp-tool{border:1px solid var(--line-2);border-radius:var(--radius-sm);padding:9px 12px;background:var(--panel)}
.mcp-tool-n{display:inline-block;font-family:var(--mono,'Geist Mono',monospace);font-size:var(--t-sm);font-weight:600;color:var(--accent);margin-bottom:3px}
.mcp-tool-d{display:block;color:var(--muted);font-size:var(--t-sm);line-height:1.5}
.mcp-kind{font-size:var(--t-xs,10px);text-transform:uppercase;letter-spacing:.04em;color:var(--faint);font-weight:700;margin-right:2px}

/* ==== Documentation: prev/next footer ==== */
.doc-pn{display:flex;justify-content:space-between;gap:12px;margin-top:48px;padding-top:20px;border-top:1px solid var(--line)}
.pn{display:flex;flex-direction:column;gap:3px;text-decoration:none;min-width:160px}
.pn.next{text-align:right;align-items:flex-end}
.pn-eye{font-size:var(--t-xs,11px);text-transform:uppercase;letter-spacing:.05em;color:var(--faint);font-weight:600}
.pn-lab{display:flex;align-items:center;gap:5px;color:var(--ink);font-weight:600;font-size:var(--t-sm);transition:color 120ms}
.pn:hover .pn-lab{color:var(--accent)}

@media(max-width:900px){.doc-toc{display:none}.doc-wrap{gap:0}.flow-arrow{display:none}.flow,.cyc{gap:10px}}
""")
