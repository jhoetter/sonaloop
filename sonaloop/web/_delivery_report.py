"""Stakeholder delivery story shared by the web preview and PDF export.

The detailed report remains the evidence/audit surface.  A stored presentation
plan is already the reviewed, method-aware story for a cold reader, so the
stakeholder PDF should render that structure instead of truncating internal
research phases into a shorter but still internal report.
"""
from __future__ import annotations

from typing import Any

from ._avatar import _avatar
from ._components import _md
from ._html import fragment, h, raw, register_css
from ._presence import asset_content_url
from ..config import content_language


def _text(value: Any) -> str:
    return str(value or "").strip()


def _project(report: dict, store) -> dict:
    return store.get_research_project(_text(report.get("project_id"))) or {}


def _assets(report: dict, store) -> dict[str, dict]:
    project = _project(report, store)
    return {str(row.get("id") or ""): row for row in (project.get("assets") or [])
            if row.get("id")}


def _asset_figure(asset_id: str, assets: dict[str, dict], *, label: str = "",
                  callouts: list | None = None, highlight: bool = False) -> str:
    asset = assets.get(_text(asset_id))
    if not asset:
        return ""
    caption = label or _text(asset.get("title") or asset.get("filename"))
    return h(
        "figure", {"class_": "dr-stim" + (" dr-stim--highlight" if highlight else "")},
        h("div", {"class_": "dr-stim__label"}, caption) if caption else "",
        h("img", {"src": asset_content_url(asset), "alt": caption, "loading": "lazy"}),
        h("ul", {"class_": "dr-callouts"}, *[
            h("li", {}, _text(row)) for row in (callouts or []) if _text(row)
        ]) if callouts else "",
    )


def _persona_card(raw_persona: Any, store, *, quote: str = "", badge: str = "") -> str:
    item = raw_persona if isinstance(raw_persona, dict) else {"persona_id": raw_persona}
    persona_id = _text(item.get("persona_id") or item.get("id"))
    persona = store.get_persona(persona_id) or {}
    name = _text(item.get("name") or persona.get("display_name") or persona_id)
    role = persona.get("role") or {}
    role_title = _text(item.get("role") or role.get("title"))
    age = _text((persona.get("identity_traits") or {}).get("age_range"))
    lens = _text(item.get("lens") or item.get("detail"))
    if not lens:
        segment = persona.get("segment") or {}
        lens = " · ".join(_text(value) for value in list(segment.values())[:2] if _text(value))
    return h(
        "article", {"class_": "dr-persona"},
        h("div", {"class_": "dr-persona__top"}, raw(_avatar(persona, 46)),
          h("div", {}, h("h3", {}, name),
            h("p", {"class_": "dr-persona__role"},
              " · ".join(value for value in (role_title, age) if value))),
          h("span", {"class_": "dr-badge"}, badge or _text(item.get("badge")))
          if badge or item.get("badge") else ""),
        h("p", {"class_": "dr-persona__lens"}, lens) if lens else "",
        h("blockquote", {}, quote or _text(item.get("quote")))
        if quote or item.get("quote") else "",
    )


def _simple_cards(rows: list, *, cls: str = "") -> str:
    cards = []
    for row in rows:
        if isinstance(row, dict):
            title = _text(row.get("title") or row.get("label") or row.get("value"))
            body = _text(row.get("text") or row.get("detail") or row.get("description"))
            meta = _text(row.get("meta"))
            cards.append(h("article", {"class_": "dr-card"}, h("h3", {}, title),
                           h("p", {}, body) if body else "",
                           h("small", {}, meta) if meta else ""))
        elif _text(row):
            cards.append(h("article", {"class_": "dr-card"}, h("p", {}, _text(row))))
    return h("div", {"class_": "dr-cards " + cls}, *cards)


def _slide_body(slide: dict, report: dict, store, assets: dict[str, dict]) -> str:
    kind = _text(slide.get("kind") or "content")
    if kind == "stimulus_comparison":
        panels = []
        for panel in (slide.get("left") or {}, slide.get("right") or {}):
            panels.append(_asset_figure(
                _text(panel.get("asset_id") or panel.get("image_ref") or panel.get("id")), assets,
                label=_text(panel.get("label")), callouts=list(panel.get("callouts") or []),
                highlight=bool(panel.get("highlight")),
            ))
        return h("div", {"class_": "dr-stimuli"}, *panels)
    if kind in {"persona_grid", "persona_detail"}:
        return h("div", {"class_": "dr-personas"}, *[
            _persona_card(row, store) for row in
            (slide.get("items") or slide.get("personas") or slide.get("persona_ids") or [])
        ])
    if kind == "preference_shift":
        stats = []
        for row in (slide.get("before") or {}, slide.get("after") or {}):
            value, total = row.get("value"), row.get("total")
            display = f"{value}/{total}" if total not in (None, "") else _text(value)
            stats.append(h("article", {"class_": "dr-stat"}, h("strong", {}, display),
                           h("span", {}, _text(row.get("label"))),
                           h("small", {}, _text(row.get("detail")))))
        switchers = [_persona_card(row, store, quote=_text(row.get("reason")))
                     for row in (slide.get("switchers") or [])]
        return fragment(h("div", {"class_": "dr-shift"}, *stats),
                        h("div", {"class_": "dr-personas"}, *switchers) if switchers else "")
    if kind == "revision_mockup":
        proposal = slide.get("proposal") or {}
        current = _asset_figure(
            _text(slide.get("asset_id") or slide.get("image_ref")), assets,
            label=_text(slide.get("source_label") or ("Heute" if content_language() == "de" else "Current")))
        proposed = h("article", {"class_": "dr-proposal"},
                     h("div", {"class_": "dr-badge"},
                       _text(slide.get("proposal_label") or
                             ("Vorschlag" if content_language() == "de" else "Proposed"))),
                     h("small", {}, _text(proposal.get("eyebrow"))),
                     h("h3", {}, _text(proposal.get("headline"))),
                     h("p", {}, _text(proposal.get("body"))),
                     h("div", {"class_": "dr-actions"},
                       h("span", {"class_": "dr-action dr-action--primary"},
                         _text(proposal.get("primary_cta"))) if proposal.get("primary_cta") else "",
                       h("span", {"class_": "dr-action"}, _text(proposal.get("secondary_cta")))
                       if proposal.get("secondary_cta") else ""),
                     h("ul", {}, *[h("li", {}, _text(row)) for row in (slide.get("why") or [])]))
        return h("div", {"class_": "dr-revision"}, current, proposed)
    if kind in {"decision_dashboard", "decision"}:
        decision = slide.get("decision") or {}
        lead = _text(decision.get("text") if isinstance(decision, dict) else decision)
        detail = _text(decision.get("detail")) if isinstance(decision, dict) else ""
        decision_html = h("article", {"class_": "dr-decision"},
                          h("span", {"class_": "dr-badge"}, _text(decision.get("label")))
                          if isinstance(decision, dict) and decision.get("label") else "",
                          h("h3", {}, lead), h("p", {}, detail) if detail else "")
        metrics = h("div", {"class_": "dr-metrics"}, *[
            h("article", {"class_": "dr-stat"}, h("strong", {}, _text(row.get("value"))),
              h("span", {}, _text(row.get("label"))), h("small", {}, _text(row.get("detail"))))
            for row in (slide.get("metrics") or []) if isinstance(row, dict)
        ])
        return fragment(decision_html, metrics, _simple_cards(list(slide.get("rationale") or [])))
    if kind in {"stats"}:
        return h("div", {"class_": "dr-metrics"}, *[
            h("article", {"class_": "dr-stat"}, h("strong", {}, _text(row.get("value"))),
              h("span", {}, _text(row.get("label"))), h("small", {}, _text(row.get("detail"))))
            for row in (slide.get("items") or []) if isinstance(row, dict)
        ])
    if kind in {"next_steps", "timeline"}:
        return h("ol", {"class_": "dr-steps"}, *[
            h("li", {}, h("span", {"class_": "dr-badge"}, _text(row.get("label"))),
              h("div", {}, h("h3", {}, _text(row.get("title"))),
                h("p", {}, _text(row.get("text")))))
            for row in (slide.get("steps") or slide.get("items") or []) if isinstance(row, dict)
        ])
    if kind in {"image", "annotated_screen"}:
        return _asset_figure(_text(slide.get("asset_id") or slide.get("image_ref")), assets,
                             label=_text(slide.get("caption")))
    if kind in {"table", "source_index"}:
        columns = list(slide.get("columns") or [])
        rows = list(slide.get("rows") or [])
        return h("div", {"class_": "dr-table-wrap"}, h("table", {},
                 h("thead", {}, h("tr", {}, *[h("th", {}, _text(col)) for col in columns])),
                 h("tbody", {}, *[h("tr", {}, *[h("td", {}, _text(cell)) for cell in row])
                                   for row in rows if isinstance(row, list)])))
    if kind == "quote":
        return h("blockquote", {"class_": "dr-quote"},
                 _text(slide.get("text") or slide.get("headline")),
                 h("footer", {}, _text(slide.get("attribution"))))
    rows = list(slide.get("items") or slide.get("support") or slide.get("rationale") or [])
    if rows:
        return _simple_cards(rows)
    markdown = _text(slide.get("markdown") or slide.get("body") or slide.get("text"))
    return h("div", {"class_": "dr-prose"}, raw(_md(markdown))) if markdown else ""


def render_delivery_story(report: dict, store) -> tuple[str, list[tuple[str, str]]]:
    plan = report.get("presentation_plan") or {}
    project = _project(report, store)
    assets = _assets(report, store)
    de = content_language() == "de"
    labels = {
        "appendix": "Anhang" if de else "Appendix",
        "appendix_subtitle": ("Evidenz, Methode und Quellen" if de
                              else "Evidence, method and sources"),
    }
    project_title = _text(project.get("title") or report.get("title")).removesuffix(" — Report")
    delivery_title = _text(plan.get("title")) or project_title
    slides = list(plan.get("slides") or [])
    cover_slide = slides[0] if slides and slides[0].get("kind") == "cover" else {}
    content_slides = slides[1:] if cover_slide else slides
    cover = h(
        "header", {"class_": "dr-cover"},
        h("p", {"class_": "dr-eyebrow"},
          _text(cover_slide.get("eyebrow") or ("Research-Ergebnis" if de else "Research result"))),
        h("h1", {}, delivery_title),
        h("p", {"class_": "dr-verdict"}, _text(cover_slide.get("headline")))
        if cover_slide.get("headline") and _text(cover_slide.get("headline")) != delivery_title else "",
        h("p", {"class_": "dr-subtitle"},
          _text(cover_slide.get("subheadline") or plan.get("objective") or project.get("goal"))),
        h("div", {"class_": "dr-meta"},
          " · ".join(value for value in (
              _text(plan.get("audience")),
              f"{plan.get('duration_minutes')} min" if plan.get("duration_minutes") else "",
              _text(report.get("created_at"))[:10],
          ) if value)),
    )
    rendered, toc = [], []
    for index, slide in enumerate(content_slides, 1):
        anchor = f"delivery-{index}"
        headline = _text(slide.get("headline") or slide.get("title"))
        toc.append((anchor, headline))
        rendered.append(h("section", {"class_": f"dr-section dr-{_text(slide.get('kind'))}",
                                       "id": anchor},
                          h("p", {"class_": "dr-section__num"}, f"{index:02d}"),
                          h("h2", {}, headline), _slide_body(slide, report, store, assets)))
    appendix = list(plan.get("appendix") or [])
    if appendix:
        rendered.append(h("header", {"class_": "dr-appendix"},
                          h("p", {"class_": "dr-eyebrow"}, labels["appendix"]),
                          h("h2", {}, labels["appendix_subtitle"])))
        for offset, slide in enumerate(appendix, len(content_slides) + 1):
            anchor = f"delivery-{offset}"
            headline = _text(slide.get("headline") or slide.get("title"))
            toc.append((anchor, headline))
            rendered.append(h("section", {"class_": f"dr-section dr-{_text(slide.get('kind'))}",
                                           "id": anchor},
                              h("p", {"class_": "dr-section__num"}, f"A{offset-len(content_slides):02d}"),
                              h("h2", {}, headline), _slide_body(slide, report, store, assets)))
    disclaimer = h(
        "footer", {"class_": "dr-method-note"},
        h("h2", {}, "Methode und Einordnung" if de else "Method and interpretation"),
        h("p", {},
          "Die Ergebnisse stammen aus Simulationen mit synthetischen Personas. Sie liefern "
          "gerichtete Hypothesen und Entscheidungshilfe, ersetzen aber keinen Test mit echten Kundinnen und Kunden."
          if de else
          "These results come from simulations with synthetic personas. They provide directional "
          "hypotheses and decision support, but do not replace testing with real customers."),
    )
    return h("article", {"class_": "delivery-report"}, cover, *rendered, disclaimer), toc


def stakeholder_context(report: dict, store) -> str:
    """Visual primer for legacy stakeholder reports without a delivery story."""
    project = _project(report, store)
    assets = [row for row in (project.get("assets") or [])
              if row.get("kind") in {"image", "screenshot"} and row.get("direction") != "output"][:6]
    personas = [store.get_persona(pid) for pid in (project.get("persona_ids") or [])]
    personas = [row for row in personas if row]
    de = content_language() == "de"
    blocks = []
    if assets:
        blocks.append(h("section", {"class_": "dr-section"},
                        h("h2", {}, "Getestetes Material" if de else "Tested material"),
                        h("div", {"class_": "dr-stimuli"}, *[
                            _asset_figure(row["id"], {row["id"]: row}) for row in assets
                        ])))
    if personas:
        blocks.append(h("section", {"class_": "dr-section"},
                        h("h2", {}, "Beteiligte Perspektiven" if de else "Participating perspectives"),
                        h("div", {"class_": "dr-personas"}, *[
                            _persona_card({"persona_id": row["id"]}, store) for row in personas
                        ])))
    return fragment(*blocks)


def stakeholder_disclaimer() -> str:
    de = content_language() == "de"
    return h("footer", {"class_": "dr-method-note"},
             h("h2", {}, "Methode und Einordnung" if de else "Method and interpretation"),
             h("p", {}, "Die Ergebnisse stammen aus Simulationen mit synthetischen Personas und "
               "ersetzen keinen Test mit echten Kundinnen und Kunden." if de else
               "These results come from simulations with synthetic personas and do not replace "
               "testing with real customers."))


register_css(r"""
.delivery-report{max-width:900px;margin:0 auto;color:var(--ink);font-size:var(--t-md);line-height:1.55}
.dr-cover{min-height:420px;display:flex;flex-direction:column;justify-content:center;padding:52px 0;border-bottom:4px solid var(--accent);margin-bottom:42px}
.dr-eyebrow,.dr-section__num{font-family:var(--mono);text-transform:uppercase;letter-spacing:.12em;color:var(--accent);font-size:var(--t-xs);font-weight:650}
.dr-cover h1{font-size:clamp(34px,5vw,60px);line-height:1.04;letter-spacing:-.035em;margin:10px 0 18px;max-width:820px}
.dr-verdict{font-size:var(--t-xl);line-height:1.25;font-weight:650;max-width:760px;margin:0 0 12px}
.dr-subtitle{font-size:var(--t-lg);max-width:680px;color:var(--muted);margin:0}.dr-meta{margin-top:28px;color:var(--faint);font-size:var(--t-sm)}
.dr-section{margin:0 0 56px;padding-top:8px;break-inside:avoid}.dr-section h2{font-size:var(--t-2xl);line-height:1.14;margin:5px 0 24px;letter-spacing:-.025em;max-width:820px}
.dr-stimuli,.dr-revision{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:20px}.dr-stim{margin:0;border:1px solid var(--line);border-radius:var(--radius);padding:12px;background:var(--panel)}
.dr-stim--highlight{border:2px solid var(--accent)}.dr-stim__label{font-weight:700;margin:0 0 9px}.dr-stim img{display:block;width:100%;height:310px;object-fit:contain;background:var(--panel-2);border-radius:calc(var(--radius) - 3px)}
.dr-callouts{margin:10px 0 0;padding-left:20px;color:var(--muted)}
.dr-personas{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.dr-persona{border:1px solid var(--line);border-radius:var(--radius);padding:14px;break-inside:avoid}.dr-persona__top{display:flex;align-items:center;gap:10px}.dr-persona__top>div{min-width:0;flex:1}.dr-persona h3{font-size:var(--t-prose);margin:0}.dr-persona__role,.dr-persona__lens{font-size:var(--t-sm);color:var(--muted);margin:2px 0 0}.dr-persona blockquote{font-size:var(--t-sm);font-style:normal;margin:10px 0 0;padding-left:10px;border-left:2px solid var(--accent)}
.dr-badge{display:inline-flex;align-items:center;padding:3px 8px;border-radius:999px;background:var(--accent-weak);color:var(--accent);font-size:var(--t-xs);font-weight:700}
.dr-shift,.dr-metrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin-bottom:18px}.dr-stat{border:1px solid var(--line);border-radius:var(--radius);padding:18px;background:var(--panel-2)}.dr-stat strong{display:block;font-size:var(--t-2xl);line-height:1}.dr-stat span,.dr-stat small{display:block;margin-top:8px}.dr-stat small{color:var(--muted)}
.dr-proposal,.dr-decision{border:1px solid var(--line);border-left:4px solid var(--accent);border-radius:var(--radius);padding:22px;background:var(--panel-2)}.dr-proposal h3,.dr-decision h3{font-size:var(--t-xl);margin:12px 0 8px}.dr-actions{display:flex;gap:8px;margin:18px 0}.dr-action{padding:8px 12px;border:1px solid var(--line);border-radius:6px}.dr-action--primary{background:var(--ink);color:var(--panel);border-color:var(--ink)}
.dr-cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px}.dr-card{padding:16px;border:1px solid var(--line);border-radius:var(--radius)}.dr-card h3{font-size:var(--t-prose);margin:0 0 7px}.dr-card p{margin:0;color:var(--muted)}
.dr-steps{list-style:none;padding:0;margin:0;display:grid;gap:12px}.dr-steps li{display:flex;gap:14px;padding:15px;border-top:1px solid var(--line)}.dr-steps h3{margin:0}.dr-steps p{margin:4px 0 0;color:var(--muted)}
.dr-table-wrap{overflow:auto}.delivery-report table{border-collapse:collapse;width:100%}.delivery-report th,.delivery-report td{text-align:left;padding:10px;border-bottom:1px solid var(--line);vertical-align:top}.delivery-report th{font-size:var(--t-xs);text-transform:uppercase;color:var(--muted)}
.dr-quote{font-size:var(--t-xl);padding:20px;border-left:4px solid var(--accent);margin:0}.dr-quote footer{font-size:var(--t-sm);color:var(--muted);margin-top:10px}.dr-appendix{margin:72px 0 36px;padding-top:28px;border-top:4px solid var(--ink)}.dr-appendix h2{font-size:var(--t-2xl);margin:8px 0}
.dr-method-note{margin:72px 0 0;padding:24px 0 0;border-top:1px solid var(--line);color:var(--muted);break-inside:avoid}.dr-method-note h2{font-size:var(--t-prose);color:var(--ink);margin:0 0 8px}.dr-method-note p{max-width:720px}
@media(max-width:680px){.dr-stimuli,.dr-revision,.dr-personas{grid-template-columns:1fr}.dr-stim img{height:auto}.dr-cover{min-height:0}}
@media print{.delivery-report{max-width:none}.dr-cover{min-height:225mm;break-after:page}.dr-section{break-before:page;margin:0;padding-top:12mm}.dr-section h2{font-size:25pt}.dr-stim img{max-height:105mm}.dr-personas{display:flex;flex-wrap:wrap;gap:10px}.dr-persona{box-sizing:border-box;flex:0 0 calc(50% - 5px);break-inside:avoid}.dr-appendix{break-before:page}.dr-method-note{break-before:page}}
""")
