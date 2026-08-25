"""Report — report-grade renderer (spec/meta-report-presentation-and-pdf.md, Phase 1).

Turns a stored report (a synthesis: outline + authored markdown sections + citations, and/or the
structured findings layer) into a presentation-quality document: a cover, a table of contents,
numbered sections, callout boxes (:::insight / :::recommendation / :::risk), pull-quotes, and
footnote-style citations. Built as clean semantic HTML + a print-first stylesheet so the
headless-Chromium PDF reuses the exact same markup. The host authors all text; this only typesets.
"""
from __future__ import annotations

import re

from . import ui
from ._html import h, raw, fragment, register_css
from ._components import _md, _icon
from ._i18n import t
from ._presence import synthesis_status_pill
from ..config import content_language
from ..assets import asset_url

# callout directive kind → (icon, css-suffix). A small fixed PRESENTATION set (not methodology vocab).
_CALLOUT = {"insight": ("bulb", "insight"), "recommendation": ("check", "rec"),
            "risk": ("alert", "risk"), "key": ("target", "key"), "keytakeaway": ("target", "key")}
_DIRECTIVE = re.compile(r":::(\w+)[ \t]*\n(.*?)\n:::", re.DOTALL)


def _cover_title(title: str) -> str:
    """Report covers are their own printable header, so they do not use the shared
    `detail_page` hero. Keep the same detail-page visual contract by leading the
    title with the Report icon here instead of adding a second header above it."""
    return h("h1", {"class_": "rp-title"},
             h("span", {"class_": "rp-title__icon"}, raw(_icon("syntheses"))),
             h("span", {"class_": "rp-title__text"}, title))


def _ref_titler(report, store):
    node_title = {n["study_id"]: (n.get("title") or "") for n in (report.get("graph_snapshot") or {}).get("nodes", [])}

    def title(ref: str) -> str:
        if node_title.get(ref):
            return node_title[ref]
        rid = ref.split(":", 1)[-1]
        s = store.get_synthesis(rid)
        if s:
            return s.get("title", rid)
        c = store.get_council_session(rid)
        if c:
            return (c.get("prompt") or rid)[:70]
        return rid
    return title


_FIG = re.compile(r"!\[\[fig:(\d+)\]\]")


def _resolve_figure(f: dict, store, *, project_id: str = "") -> dict | None:
    """A figure ref → {url, caption} (or None if it can't be shown). Web is read-only: a prototype that
    was never screenshotted simply doesn't render (capture happens via an explicit MCP/CLI action).

    Project-asset records resolve through the canonical browser URL helper in both modes (their
    stored ``url`` locally, the opaque route in shared Postgres).  RLS scopes the project lookup
    to the active workspace; the explicit project membership additionally prevents a report from
    smuggling in another project's asset id.  If no project record exists, local SQLite retains
    the historical content-addressed ``/data/<asset-id>`` fallback while Postgres fails closed.
    """
    if not isinstance(f, dict):
        return None
    kind = f.get("kind")
    cap = f.get("caption", "")
    if kind == "asset" and f.get("id"):
        from .. import config
        project = store.get_research_project(project_id) if isinstance(project_id, str) and project_id else None
        asset = next((a for a in (project or {}).get("assets") or []
                      if a.get("id") == f["id"]), None)
        if asset:
            from ._presence import asset_content_url
            return {"url": asset_content_url(asset), "caption": cap, "kind": "asset"}
        if config.postgres_row_tenancy_enabled():
            return None
        return {"url": asset_url(f["id"]), "caption": cap, "kind": "asset"}
    if kind == "prototype" and f.get("id"):
        p = store.get_prototype(f["id"])
        if p and p.get("shot"):
            return {"url": asset_url(p["shot"]), "caption": cap or p.get("name", "")}
    if kind == "avatar" and f.get("id"):
        from ._components import _avatar_src
        p = store.get_persona(f["id"])
        src = _avatar_src(p or {})
        if src:
            return {"url": src, "caption": cap or p.get("display_name", "")}
    if kind == "chart":
        # Author-supplied charts dispatch through the modular registry (charts_catalogue), which is
        # the single source of truth for which `of` exists, how to call its design-system renderer,
        # and the agent-facing `suggest_chart_kinds` catalogue. effort_impact is the one exception:
        # it is source-driven (derived from a synthesis), handled below.
        of = f.get("of", "effort_impact")
        series = [s for s in (f.get("series") or []) if isinstance(s, dict)]
        if of != "effort_impact":
            from ..charts_catalogue import render_chart
            chart = render_chart(of, f, series)
            return {"html": chart, "caption": cap} if chart else None
        sid = f.get("source_id") or f.get("id")
        syn = store.get_synthesis(sid) if sid else None
        if syn and of == "effort_impact":
            from ._components import _effort_impact
            from .. import artifacts as _A
            recs = _A.synthesis_recommendations(syn)
            chart = _effort_impact(recs) if recs else ""
            if chart:
                return {"html": chart, "caption": cap or syn.get("title", "")}
    return None


def _figure_html(fig: dict) -> str:
    inner = raw(fig["html"]) if fig.get("html") else h(
        "img", {"src": fig["url"], "alt": fig.get("caption", ""), "loading": "lazy"})
    cls = "rp-fig" + (" rp-fig--asset" if fig.get("kind") == "asset" else "")
    return h("figure", {"class_": cls}, inner,
             h("figcaption", {}, fig["caption"]) if fig.get("caption") else "")


def _figure_run(figs: list[dict]) -> str:
    """Keep charts and explicitly placed figures at reading width, but dose consecutive
    unplaced asset screenshots as a compact responsive gallery.  The original ordering and
    captions remain intact; a single asset stays a normal full-width figure."""
    out: list = []
    assets: list[dict] = []

    def flush_assets() -> None:
        if not assets:
            return
        rendered = [_figure_html(fig) for fig in assets]
        out.append(h("div", {"class_": "rp-asset-grid", "role": "list",
                             "aria-label": t("assets_h")},
                     fragment(*(h("div", {"role": "listitem"}, figure)
                                for figure in rendered))) if len(rendered) > 1
                   else rendered[0])
        assets.clear()

    for fig in figs:
        if fig.get("kind") == "asset":
            assets.append(fig)
        else:
            flush_assets()
            out.append(_figure_html(fig))
    flush_assets()
    return fragment(*out)


def _prose_run(md_text: str) -> str:
    """One uninterrupted prose run, dosed through ui.clamp at the SECTION threshold (ux-contract
    §3.6d): a normal section reads naturally, a genuinely long one collapses to 5 lines with an
    in-place expand. Callouts/figures never clamp — they ARE the structure between the runs."""
    from . import ui
    return ui.clamp(raw(_md(md_text)), threshold=ui.SECTION_CLAMP)


def _segment(md_text: str) -> str:
    """A markdown segment with :::callout::: blocks lifted into styled boxes."""
    out, pos = [], 0
    for m in _DIRECTIVE.finditer(md_text):
        pre = md_text[pos:m.start()].strip()
        if pre:
            out.append(_prose_run(pre))
        icon, cls = _CALLOUT.get(m.group(1).lower(), ("dot", "insight"))
        out.append(h("div", {"class_": f"rp-call rp-{cls}"},
                     h("div", {"class_": "rp-call-ic"}, raw(_icon(icon))),
                     h("div", {"class_": "rp-call-body"}, raw(_md(m.group(2).strip())))))
        pos = m.end()
    rest = md_text[pos:].strip()
    if rest:
        out.append(_prose_run(rest))
    return fragment(*out)


def _body(md_text: str, figs: list) -> str:
    """Render a section body: markdown + callouts, with inline ![[fig:N]] placeholders resolved to
    figures; any unreferenced figures append at the end."""
    out, used = [], set()
    parts = _FIG.split(md_text)
    for k, part in enumerate(parts):
        if k % 2 == 0:
            if part.strip():
                out.append(_segment(part))
        else:
            i = int(part) - 1
            if 0 <= i < len(figs):
                out.append(_figure_html(figs[i])); used.add(i)
    remaining = [fg for i, fg in enumerate(figs) if i not in used]
    if remaining:
        out.append(_figure_run(remaining))
    return fragment(*out)


def _stakeholder_markdown(value: str, *, max_chars: int = 1400, max_blocks: int = 4) -> str:
    """Dose authored report prose without inventing a second summary.

    The share PDF keeps the first complete structural blocks of every section
    (including a complete callout directive) and points back to Sonaloop for the
    detailed evidence. The on-screen report and detailed export remain untouched.
    """
    blocks = [block.strip() for block in re.split(r"\n\s*\n", value or "") if block.strip()]
    kept: list[str] = []
    used = 0
    for block in blocks:
        if len(kept) >= max_blocks:
            break
        # Never split a callout directive; broken ::: markers are worse than one
        # slightly longer stakeholder section.
        if kept and used + len(block) > max_chars:
            break
        if not kept and len(block) > max_chars and not block.startswith(":::"):
            block = block[:max_chars].rsplit(" ", 1)[0].rstrip(" ,;:") + " …"
        kept.append(block)
        used += len(block)
    return "\n\n".join(kept)


def render_report(report: dict, store, *, with_toc: bool = False,
                  audience: str = "detailed"):
    """Report-grade render of ANY synthesis (spec/unified-synthesis-report.md §3 — one renderer):
    project scope → narrative sections + figures; convergence scope → the structured analysis
    (verdict card → charts → findings → 2×2, voices) in the SAME report shell (cover + report
    typography). `with_toc=True` additionally returns the [(anchor_id, label)] section list so
    the detail page can hang the scrollspy rail (`_page_rail`) beside the document (§3.6c)."""
    if audience not in {"detailed", "stakeholder"}:
        raise ValueError("report audience must be 'detailed' or 'stakeholder'")
    stakeholder = audience == "stakeholder"
    if stakeholder and report.get("scope") == "project" and report.get("presentation_plan"):
        from ._delivery_report import render_delivery_story
        article, delivery_toc = render_delivery_story(report, store)
        return (article, delivery_toc) if with_toc else article
    de = content_language() == "de"
    _t = report.get("title", "")           # the default title ends in " — Report"; custom titles show as-is
    project_title = _t[:-len(" — Report")] if _t.endswith(" — Report") else _t

    # Detail-header attribution (ux-contract §10 W11): when the report's DATA carries voices
    # (statements), their personas lead the cover meta line as the one avatar-group anatomy.
    vpids = [p for p in dict.fromkeys(st.get("persona_id", "")
                                      for st in report.get("statements") or []) if p]
    crew = ui.avatar_group((store.get_persona(p) for p in vpids[:4]), total=len(vpids), size=22)

    # G2: the lifecycle pill beside the cover eyebrow — the same words as the report rows
    # (the convergence meta line dropped its status TEXT: one encoding, the pill).
    status_pill = raw(synthesis_status_pill(report.get("status", "done")))

    if report.get("scope") != "project":
        # a convergence synthesis, rendered in the unified report shell.
        from ._synthesis import _synthesis_html
        meta_parts = [x for x in [
            (f'{len(report.get("council_ids", []))} {t("councils")}'
             if report.get("council_ids") else ""),
            ui.local_date(report.get("created_at") or "")] if x]
        meta_line = fragment(*(fragment(" · " if i else "", value)
                               for i, value in enumerate(meta_parts)))
        cover = h("header", {"class_": "rp-cover"},
                  h("div", {"class_": "rp-eyebrow"}, t("synthesis_kind"), status_pill),
                  raw(_cover_title(project_title)),
                  h("div", {"class_": "rp-metaline"}, crew if crew else None, h("span", {}, meta_line)))
        body, toc = _synthesis_html(store, report, embed=True)
        article = h("article", {"class_": "report report-syn"}, cover, raw(body))
        return (article, toc) if with_toc else article

    rtitle = _ref_titler(report, store)
    sections = report.get("sections", [])
    n_studies = len({x for sec in sections for x in sec.get("source_study_ids", [])})
    # The cover meta line is part of the printable DOCUMENT (PDF export reuses this markup),
    # so the whole line follows the content language — `t()` would mix the UI language into
    # an authored German report ("6 sections · 5 Studien", ux-audit P5 finding).
    n_sec = len(sections)
    sections_word = (("Abschnitt" if n_sec == 1 else "Abschnitte") if de
                     else ("section" if n_sec == 1 else "sections"))
    studies_word = (("Studie" if n_studies == 1 else "Studien") if de
                    else ("study" if n_studies == 1 else "studies"))
    meta_parts = [f"{n_sec} {sections_word}", f"{n_studies} {studies_word}",
                  ui.local_date(report.get("created_at") or "")]
    meta_line = fragment(*(fragment(" · " if i else "", value)
                           for i, value in enumerate(meta_parts)))

    cover = h("header", {"class_": "rp-cover"},
              h("div", {"class_": "rp-eyebrow"}, t("synthesis_kind"), status_pill),
              raw(_cover_title(project_title)),
              h("div", {"class_": "rp-metaline"}, crew if crew else None, h("span", {}, meta_line)),
              (h("p", {"class_": "rp-lead"}, raw(_md(report["lead"])))
               if report.get("lead") else ""))

    limitations = ""
    if report.get("limitations"):
        limitations = h(
            "section", {"class_": "rp-limitations", "role": "note"},
            h("h2", {}, "Limitationen" if de else "Limitations"),
            h("ul", {}, *[
                h("li", {}, h("code", {}, row.get("original_status") or
                              t("cohort_status_overridden")),
                  " — ", row.get("rationale") or "")
                for row in report.get("limitations") or []
            ]),
        )

    toc = h("nav", {"class_": "rp-toc"}, h("div", {"class_": "rp-toc-h"}, t("toc")),
            h("ol", {}, *[h("li", {}, h("a", {"href": f"#rp-s{i}"}, sec["heading"]))
                          for i, sec in enumerate(sections, 1)]))

    secs = []
    stakeholder_context_html = ""
    if stakeholder:
        from ._delivery_report import stakeholder_context
        stakeholder_context_html = stakeholder_context(report, store)
    for i, sec in enumerate(sections, 1):
        figs = [rf for rf in (_resolve_figure(f, store, project_id=report.get("project_id") or "")
                              for f in (sec.get("figures") or [])) if rf]
        if stakeholder:
            # A/B stimuli are one comparison and must travel together.  More than
            # two figures still belongs in the detailed evidence report.
            figs = figs[:2]
        section_md = (_stakeholder_markdown(sec.get("markdown", ""))
                      if stakeholder else sec.get("markdown", ""))
        body_html = (_body(section_md, figs) if section_md
                     # plain <em>, not markdown syntax — this string is never md-rendered
                     else h("p", {"class_": "muted"},
                            h("em", {}, f"({'noch nicht verfasst' if de else 'not yet authored'})")))
        cites = ""
        if sec.get("citations") and not stakeholder:
            rows = []
            for n, c in enumerate(sec["citations"], 1):
                council = h("span", {"class_": "rp-cite-src"}, f" · {rtitle(c['council_id'])}") if c.get("council_id") else ""
                quote = h("span", {"class_": "rp-cite-q"}, f"„{c['quote']}“") if c.get("quote") else ""
                rows.append(h("li", {}, h("span", {"class_": "rp-cite-n"}, str(n)),
                              h("span", {}, h("b", {}, rtitle(c["study_id"])), council, " ", quote)))
            cites = h("div", {"class_": "rp-cites"}, h("div", {"class_": "rp-cites-h"}, t("citations")),
                      h("ol", {}, *rows))
        src = ""
        if sec.get("source_study_ids"):
            src_text = ((f'{len(sec["source_study_ids"])} Quellen · Details in Sonaloop')
                        if de else
                        (f'{len(sec["source_study_ids"])} sources · Details in Sonaloop'))
            if not stakeholder:
                src_text = (("Quellen: " if de else "Sources: ")
                            + ", ".join(rtitle(x) for x in sec["source_study_ids"]))
            src = h("div", {"class_": "rp-src"}, src_text)
        secs.append(h("section", {"class_": "rp-sec", "id": f"rp-s{i}"},
                      h("h2", {}, h("span", {"class_": "rp-num"}, f"{i:02d}"), sec["heading"]),
                      body_html, cites, src))
    stakeholder_end = ""
    if stakeholder:
        from ._delivery_report import stakeholder_disclaimer
        stakeholder_end = stakeholder_disclaimer()
    article = h("article", {"class_": "report" + (" report--stakeholder" if stakeholder else "")},
                cover, limitations, "" if stakeholder else toc, stakeholder_context_html,
                *secs, stakeholder_end)
    if with_toc:
        return article, [(f"rp-s{i}", sec["heading"]) for i, sec in enumerate(sections, 1)]
    return article


register_css(r"""
/* Meta-report — report-grade document (spec/meta-report-presentation-and-pdf.md Phase 1).
   Typography sits on the t-* scale + roles (ux-contract §11 T1/T3): display = the t-2xl cover
   title, lead = t-lg, body = the t-md report voice at the 1.6 reading rhythm, quiet = t-sm meta.
   RUNNING prose wraps at the --measure-prose reading width (T2); structural elements (headings,
   callout/toc boxes, figures, rows) keep the document column. */
.report{max-width:780px;margin:0 auto;color:var(--ink);font-size:var(--t-md);line-height:1.6}
.report h2,.report h3{max-width:none}
.report p,.report ul,.report ol{max-width:var(--measure-prose)}
.rp-call p,.rp-call ul,.rp-call ol,.rp-toc ol{max-width:none}
/* cover */
.rp-cover{padding:8px 0 26px;margin-bottom:30px;border-bottom:1px solid var(--line)}
.rp-eyebrow{font-family:var(--mono);font-size:var(--t-xs);text-transform:uppercase;letter-spacing:.14em;color:var(--accent);font-weight:500;display:flex;align-items:center;gap:8px}
.rp-eyebrow .lbl{font-family:var(--sans);text-transform:none;letter-spacing:normal}
.rp-title{display:flex;align-items:flex-start;gap:10px;font-size:var(--t-2xl);line-height:1.2;font-weight:700;margin:10px 0 0;letter-spacing:-.01em}
.rp-title__icon{flex:none;line-height:0;color:var(--accent);margin-top:.12em}
.rp-title__icon svg{width:.78em;height:.78em}
.rp-title__text{min-width:0}
.rp-metaline{margin-top:12px;color:var(--muted);font-size:var(--t-sm);font-variant-numeric:tabular-nums;
  display:flex;align-items:center;gap:8px}
.rp-lead{margin:22px 0 0;font-size:var(--t-lg);line-height:1.6;color:var(--ink);font-weight:400;
  border-left:3px solid var(--accent);padding-left:18px}
.rp-lead p{margin:0}
/* table of contents */
.rp-toc{margin:0 0 34px;padding:16px 18px;background:var(--panel-2);border:1px solid var(--line);border-radius:var(--radius)}
.rp-toc-h{font-size:var(--t-xs);text-transform:uppercase;letter-spacing:.07em;color:var(--muted);font-weight:600;margin-bottom:8px}
.rp-toc ol{margin:0;padding:0;list-style:none;counter-reset:toc}
.rp-toc li{counter-increment:toc;padding:3px 0}
.rp-toc li::before{content:counter(toc,decimal-leading-zero);color:var(--faint);font-variant-numeric:tabular-nums;margin-right:10px;font-size:var(--t-sm)}
.rp-toc a{color:var(--ink);text-decoration:none}.rp-toc a:hover{color:var(--accent)}
.rp-limitations{margin:0 0 24px;padding:14px 16px;border:1px solid var(--amber);border-radius:var(--radius);background:var(--panel-2)}
.rp-limitations h2{font-size:var(--t-prose);margin:0 0 8px}.rp-limitations ul{margin:0;padding-left:20px}.rp-limitations code{color:var(--amber)}
/* sections */
.rp-sec{margin:0 0 40px;scroll-margin-top:70px}
.rp-sec h2{display:flex;align-items:baseline;gap:12px;font-size:var(--t-xl);font-weight:650;line-height:1.2;margin:0 0 14px;letter-spacing:-.01em}
.rp-num{color:var(--faint);font-size:var(--t-prose);font-weight:600;font-variant-numeric:tabular-nums}
.report p{margin:0 0 14px}.report ul,.report ol{margin:0 0 14px;padding-left:22px}.report li{margin:3px 0}
.report h3{font-size:var(--t-prose);font-weight:600;margin:22px 0 8px}
/* pull-quote (blockquote) */
.report blockquote{margin:22px 0;padding:4px 0 4px 20px;border-left:3px solid var(--line-2);
  font-size:var(--t-lg);line-height:1.6;color:var(--muted);font-style:italic;max-width:var(--measure-prose)}
.report blockquote p{margin:0}
/* callouts */
.rp-call{display:flex;gap:12px;margin:18px 0;padding:14px 16px;border:1px solid var(--line);border-left-width:3px;border-radius:var(--radius);background:var(--panel-2)}
.rp-call-ic{flex:none;line-height:0;margin-top:2px}.rp-call-ic svg{width:18px;height:18px}
.rp-call-body{min-width:0}.rp-call-body>:first-child{margin-top:0}.rp-call-body>:last-child{margin-bottom:0}
.rp-insight{border-left-color:var(--accent)}.rp-insight .rp-call-ic{color:var(--accent)}
.rp-rec{border-left-color:var(--green)}.rp-rec .rp-call-ic{color:var(--green)}
.rp-risk{border-left-color:var(--amber)}.rp-risk .rp-call-ic{color:var(--amber)}
.rp-key{border-left-color:var(--accent);background:var(--accent-weak)}.rp-key .rp-call-ic{color:var(--accent)}
/* citations + sources */
.rp-cites{margin:18px 0 0;padding-top:12px;border-top:1px solid var(--line)}
.rp-cites-h{font-size:var(--t-xs);text-transform:uppercase;letter-spacing:.06em;color:var(--muted);font-weight:600;margin-bottom:6px}
.rp-cites ol{list-style:none;margin:0;padding:0}
.rp-cites li{display:flex;gap:9px;font-size:var(--t-sm);color:var(--muted);padding:3px 0;line-height:1.5}
.rp-cite-n{flex:none;width:18px;height:18px;border-radius:50%;background:var(--panel-2);border:1px solid var(--line);
  font-size:var(--t-xs);display:inline-flex;align-items:center;justify-content:center;color:var(--faint)}
.rp-cites b{color:var(--ink);font-weight:550}.rp-cite-q{color:var(--muted)}
.rp-src{margin-top:10px;font-size:var(--t-xs);color:var(--faint)}
/* convergence synthesis embedded in the report shell — its blocks inherit report typography;
   drop the first block's top divider so it sits cleanly under the cover (spec/unified-synthesis-report §3) */
.report-syn .sl-syn-main>.block:first-child,.report-syn .sl-syn-main>section:first-child .block{border-top:0;margin-top:6px;padding-top:0}
.report-syn .block{max-width:none}
/* figures (Phase 2) — prototype screenshots, images, charts */
.rp-fig{margin:22px 0}
.rp-fig img{display:block;max-width:100%;height:auto;border:1px solid var(--line);border-radius:var(--radius);box-shadow:0 1px 4px rgba(0,0,0,.07)}
.rp-fig figcaption{margin-top:9px;font-size:var(--t-sm);color:var(--muted);text-align:center}
.rp-asset-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:var(--sl-gap-group);margin:22px 0}
.rp-asset-grid .rp-fig{margin:0}.rp-asset-grid .rp-fig img{width:100%;height:180px;object-fit:contain;background:var(--panel-2)}
@media(max-width:560px){.rp-asset-grid{grid-template-columns:1fr}}
/* print: drop the app chrome, give the report the page (foundation for the Chromium PDF, Phase 3) */
@media print{
  .sl-sidebar,.sl-topbar,.sl-cmdk,.sl-drawer,.toc,.rail,.actions,.crumbs{display:none!important}
  .shell,.content,.page,main{margin:0!important;padding:0!important;max-width:none!important}
  body{background:#fff}
  .report{max-width:none}
  /* print/PDF gets the FULL prose — clamps are a screen-dosing device, never an export cut */
  .sl-clamp{display:block;-webkit-line-clamp:unset;overflow:visible}
  .sl-clamp-toggle{display:none}
  .rp-sec{break-inside:avoid}
  .rp-call,.report blockquote,.rp-cites,.rp-fig{break-inside:avoid}
  .rp-asset-grid .rp-fig img{height:auto}
  .rp-cover{break-after:avoid}
}
""")
