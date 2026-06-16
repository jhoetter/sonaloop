"""The documentation hub — a dedicated, multi-page docs area (not one long scroll).

Audience: the HUMAN using the Sonaloop inspector (a researcher / PM / founder), not the agent that drives
the tools. The conceptual pages explain what each thing IS and why it matters to that person; tool names
live on the MCP-reference page (the one page aimed at whoever wires Sonaloop up).

Five focused pages share one shell (`_docs_shell`): a secondary tab nav across the top, a breadcrumb,
the page body, an optional sticky "on this page" rail, and a prev/next footer.

  Overview      — what Sonaloop is + the three guarantees that make it trustworthy
  Concepts      — every artefact, grouped into role bands, in plain language
  How it works  — a visual pipeline from question to answer + how a study stays rigorous
  Methodology   — a study runs a (pluggable) methodology; Double Diamond is one example; recipes
  MCP reference — the live, auto-generated tool catalogue, organized by domain

Content is bilingual (de/en) inline (long prose; keeps the t() table lean) and authored in Markdown so
the pages also exercise the _md renderer. Every (de, en) tuple is indexed by `li` (0=de, 1=en) at render.
Artefact NAME + COLOR still come from data (present()/t()), never hardcoded.
"""
from __future__ import annotations

from ._i18n import t
from ._components import _icon, _layout, _md, _md_inline, _lang
from ._html import h, raw, fragment
from ..storage import Store
from ..doc_schemas import PRIM_JSON, EXAMPLES   # example JSON kept out of the web pkg (R8 grep gate)


from ._docs_content import (
    DOC_PAGES, DOCS_INTRO, PRINCIPLES, DOCS, GROUPS, GROUP_MAP, PRIMITIVES, SCHEMAS, LIFECYCLE,
    EVIDENCE_PILLS, LOOP_NOTE, RIGOUR_STEPS, INSPECTOR_SECTIONS, DD_PHASES, RHYTHM, RECIPES,
    DOMAIN_META, SUPER_GROUPS)


# ============================ The shared shell ============================ #
def _doc_tabbar(active: str, li: int) -> str:
    """The secondary tab nav shared by every doc page (and concept-detail sub-pages) —
    BELOW the page header, aligned to the measure (W7 design pass: the Library idiom)."""
    tabs = [h("a", {"class_": "sl-tab" + (" is-active" if s == active else ""),
                    "href": "/documentation" + (f"/{s}" if s else "")},
              raw(_icon(ic)), lab[li])
            for s, ic, lab in DOC_PAGES]
    return h("nav", {"class_": "sl-tabs doc-tabs"}, fragment(*tabs))


def _doc_header(title: str, lead: str, icon: str = "", color: str = "") -> str:
    """The standard page-header anatomy (W7 design pass — ux-contract §8.2: eyebrow ·
    title · lead in the measure): the DOCUMENTATION eyebrow keys the area, the page name
    is the h1; sub-pages lead the title with their colored concept icon."""
    return h("div", {"class_": "doc-head"},
             h("div", {"class_": "eyebrow"}, t("documentation")),
             h("h1", {"class_": "h1"},
               h("span", {"class_": "rico lg", "style": f"color:{color}"}, raw(_icon(icon)))
               if icon else None,
               title),
             h("p", {"class_": "lead"}, raw(_md_inline(lead))) if lead else None)


def _docs_shell(slug: str, lead: str, body: str, subnav: list | None = None) -> str:
    """Wrap one doc page: breadcrumb · page header · tab bar · (content + optional
    on-this-page rail) · prev/next."""
    store = Store()
    de = _lang() == "de"
    li = 0 if de else 1
    idx = next(i for i, (s, *_) in enumerate(DOC_PAGES) if s == slug)
    _, icon, label = DOC_PAGES[idx]
    title = t("documentation") if slug == "" else label[li]

    tabbar = _doc_tabbar(slug, li)

    header = _doc_header(label[li], lead)

    if subnav:
        rail = h("aside", {"class_": "doc-toc"},
            h("nav", {"class_": "toc-nav"},
              h("div", {"class_": "toc-lbl"}, "Auf dieser Seite" if de else "On this page"),
              fragment(*(h("a", {"href": f"#{a}"}, lab) for a, lab in subnav))))
        content = h("div", {"class_": "doc-wrap"}, h("div", {"class_": "doc-main"}, body), rail)
    else:
        content = h("div", {"class_": "doc-main wide"}, body)

    prev = DOC_PAGES[idx - 1] if idx > 0 else None
    nxt = DOC_PAGES[idx + 1] if idx < len(DOC_PAGES) - 1 else None
    def _pn(page, kind):
        if not page:
            return h("span", {})
        s, ic, lab = page
        eye = ("Zurück" if de else "Back") if kind == "prev" else ("Weiter" if de else "Next")
        return h("a", {"class_": f"pn {kind}", "href": "/documentation" + (f"/{s}" if s else "")},
                 h("span", {"class_": "pn-eye"}, eye),
                 h("span", {"class_": "pn-lab"},
                   raw("&larr;&nbsp;") if kind == "prev" else None, lab[li],
                   raw("&nbsp;&rarr;") if kind == "next" else None))
    footer = h("div", {"class_": "doc-pn"}, _pn(prev, "prev"), _pn(nxt, "next"))

    page = h("div", {"class_": "page"}, header, tabbar, content, footer)
    crumbs = ([(t("documentation"), None)] if slug == ""
              else [(t("documentation"), "/documentation"), (title, None)])
    return _layout(title, page, store, crumbs=crumbs, active="docs")


def _anchor_block(aid: str, *children) -> str:
    return h("div", {"class_": "doc-block", "id": aid}, fragment(*children))


def _sub_h(text: str) -> str:
    return h("h2", {"class_": "doc-sub-h"}, text)


def _art_name(art: str, name_key) -> tuple[str, dict]:
    """Resolve an artefact's display name + presentation (color/label) from data — never hardcoded."""
    from .. import presentation as _pres
    pres = _pres.present(art)
    name = (t(name_key) if name_key
            else (pres["label"] if not pres["label"].islower() else pres["label"].capitalize()))
    return name, pres


def _code(text: str, lang: str = "json") -> str:
    """A fenced code block (the schema examples)."""
    return h("pre", {"class_": "doc-code"}, h("code", {}, text))


def _doc_subpage(active: str, crumbs: list, title: str, lead: str, icon: str, color: str,
                 body: str, subnav: list | None = None, footer: str = "") -> str:
    """Shell for a card-opened DETAIL sub-page (artefact / data model / principles): the same tab bar +
    breadcrumb chrome as a top page, a colored title icon, an optional on-this-page rail, optional footer."""
    store = Store()
    de = _lang() == "de"
    li = 0 if de else 1
    header = _doc_header(title, lead, icon=icon, color=color)
    if subnav:
        rail = h("aside", {"class_": "doc-toc"},
            h("nav", {"class_": "toc-nav"},
              h("div", {"class_": "toc-lbl"}, "Auf dieser Seite" if de else "On this page"),
              fragment(*(h("a", {"href": f"#{a}"}, lab) for a, lab in subnav))))
        content = h("div", {"class_": "doc-wrap"}, h("div", {"class_": "doc-main"}, body), rail)
    else:
        content = h("div", {"class_": "doc-main wide"}, body)
    page = h("div", {"class_": "page"}, header, _doc_tabbar(active, li), content, footer)
    return _layout(title, page, store, crumbs=crumbs, active="docs")


def _doc_datamodel_body(de: bool, li: int) -> str:
    """The data-format explainer body (three layers + the five primitives) — its own sub-page."""
    layers = [
        (("Inhalt — fünf Primitive", "Content — five primitives"),
         ("Jedes Stück Inhalt in jedem Artefakt ist eines von fünf: Statement · Finding · Prompt · Ref · "
          "Stance. Ein Renderer pro Primitive — darum sieht „dasselbe Ding“ überall gleich aus.",
          "Every piece of content in every artefact is one of five: Statement · Finding · Prompt · Ref · "
          "Stance. One renderer per primitive — so the \"same thing\" looks the same everywhere.")),
        (("Graph — Nodes & Edges", "Graph — nodes & edges"),
         ("Jedes Artefakt (Persona, Council, Report, Prototyp, Notiz, Section) ist ein **Node** mit "
          "`{id, kind, title, project_id, created_at}`. Typisierte **Edges** verbinden sie "
          "(`based_on`, `feeds_into`, `refines`, `answers`).",
          "Every artefact (persona, council, report, prototype, note, section) is a **Node** with "
          "`{id, kind, title, project_id, created_at}`. Typed **Edges** wire them together "
          "(`based_on`, `feeds_into`, `refines`, `answers`).")),
        (("Gedächtnis — zeit-indiziert", "Memory — time-indexed"),
         ("Persona-Erinnerung lebt in eigenen, datierten Records (Erlebnisse, Tages-Summaries, "
          "Pain-Points), sodass Recall und Zeitreise funktionieren.",
          "Persona memory lives in its own dated records (experiences, daily summaries, pain points), so "
          "recall and time-travel work.")),
    ]
    layer_cards = [h("div", {"class_": "dl-layer"},
        h("div", {"class_": "dl-layer-n"}, str(n + 1)),
        h("div", {"class_": "dl-layer-main"},
          h("div", {"class_": "dl-layer-t"}, ti[li]),
          h("div", {"class_": "sl-prose sm dl-layer-b"}, raw(_md(body[li])))))
        for n, (ti, body) in enumerate(layers)]
    prim_cards = [h("div", {"class_": "sl-card prim-card"},
        h("div", {"class_": "prim-card-h"}, h("code", {"class_": "prim-card-n"}, nm)),
        h("div", {"class_": "prim-card-d"}, raw(_md_inline(dde if de else den))),
        _code(PRIM_JSON[nm])) for nm, dde, den in PRIMITIVES]

    return fragment(
        h("div", {"class_": "doc-p"}, raw(_md(
          ("Sonaloop speichert alles als JSON in einem Graphen. Drei Schichten erklären das Format — und "
           "jedes Konzept zeigt sein konkretes Schema, wenn du es öffnest.") if de else
          ("Sonaloop stores everything as JSON in a graph. Three layers explain the format — and each "
           "concept shows its concrete schema when you open it.")))),
        _anchor_block("layers",
            _sub_h("Drei Schichten" if de else "Three layers"),
            h("div", {"class_": "dl-layers"}, fragment(*layer_cards))),
        _anchor_block("primitives",
            _sub_h("Die fünf Primitive" if de else "The five primitives"),
            h("div", {"class_": "prim-grid"}, fragment(*prim_cards))),
        h("div", {"class_": "doc-note", "style": "margin-top:18px"}, raw(_md(
          "Details & Migrationspfad: `spec/unified-artifact-schema.md`." if de else
          "Full details & migration path: `spec/unified-artifact-schema.md`."))))


# ============================ The five pages ============================ #
def _doc_overview() -> str:
    de = _lang() == "de"
    li = 0 if de else 1

    # Every destination — the four sections + the Principles sub-page — as one directory of cards.
    NAV = [
        ("/documentation/principles", "target", ("Grundprinzipien", "Core principles"),
         ("Was Sonaloop vertrauenswürdig macht — die fünf Leitprinzipien.",
          "What makes Sonaloop trustworthy — the five guiding principles.")),
        ("/documentation/concepts", "squareGrid", ("Konzepte", "Concepts"),
         ("Die Bausteine — Personas, Councils, Prototypen, Reports — und das Datenmodell.",
          "The building blocks — personas, councils, prototypes, reports — and the data model.")),
        ("/documentation/how-it-works", "panel", ("So funktioniert's", "How it works"),
         ("Der Weg von der Frage zur Antwort — und was jeden Schritt belastbar hält.",
          "The path from question to answer — and what keeps every step trustworthy.")),
        ("/documentation/inspector", "activity", ("Live arbeiten", "Working live"),
         ("Beispielprojekte, Live-Aktivität, Runs, Tastatur, Tour, Bearbeitungs-Grenze, Feedback.",
          "Example projects, live activity, runs, keyboard, tour, the editing boundary, feedback.")),
        ("/documentation/methodology", "target", ("Methodik", "Methodology"),
         ("Eine Studie fährt eine austauschbare Methodik. Double Diamond ist nur eine davon.",
          "A study runs a swappable methodology. Double Diamond is just one of them.")),
        ("/documentation/mcp", "prototype", ("MCP-Referenz", "MCP reference"),
         ("Die komplette MCP-Tool-Referenz, nach Domäne geordnet.",
          "The complete MCP tool reference, organized by domain.")),
    ]
    cards = [h("a", {"class_": "sl-card navcard", "href": href},
               h("span", {"class_": "rico navcard-ic"}, raw(_icon(ic))),
               h("span", {"class_": "navcard-t"}, lab[li]),
               h("span", {"class_": "navcard-b"}, blurb[li]))
             for href, ic, lab, blurb in NAV]
    explore = h("div", {"class_": "doc-block"},
        _sub_h("Die Dokumentation" if de else "The documentation"),
        h("div", {"class_": "navgrid"}, fragment(*cards)))

    body = fragment(
        h("div", {"class_": "sl-prose", "style": "margin:2px 0 8px;max-width:74ch"},
          raw(_md(DOCS_INTRO["de" if de else "en"]))),
        explore)
    lead = ("Was Sonaloop ist und wie du damit arbeitest." if de
            else "What Sonaloop is, and how you work with it.")
    return _docs_shell("", lead, body)


def _doc_principles_page() -> str:
    """The principles as their own sub-page (opened from the Overview directory)."""
    de = _lang() == "de"
    li = 0 if de else 1
    tiles = [h("div", {"class_": "sl-card ptile"},
        h("span", {"class_": "rico ptile-ic"}, raw(_icon(ic))),
        h("div", {"class_": "ptile-t"}, ti[li]),
        h("div", {"class_": "sl-prose sm ptile-b"}, raw(_md(body[li]))))
        for ic, ti, body in PRINCIPLES]
    body = h("div", {"class_": "principles", "style": "margin-top:6px"}, fragment(*tiles))
    lead = ("Fünf Prinzipien, die bestimmen, warum man den Ergebnissen trauen kann." if de
            else "Five principles that determine why you can trust the results.")
    crumbs = [(t("documentation"), "/documentation"), (("Grundprinzipien" if de else "Core principles"), None)]
    return _doc_subpage("", crumbs, "Grundprinzipien" if de else "Core principles", lead,
                        "target", "var(--accent)", body)


def _doc_data_model_page() -> str:
    """The data model as its own sub-page (opened from the Concepts directory)."""
    de = _lang() == "de"
    li = 0 if de else 1
    body = _doc_datamodel_body(de, li)
    lead = ("Wie Sonaloop alles als JSON in einem Graphen speichert." if de
            else "How Sonaloop stores everything as JSON in one graph.")
    crumbs = [(t("documentation"), "/documentation"),
              (("Konzepte" if de else "Concepts"), "/documentation/concepts"),
              (("Datenmodell" if de else "Data model"), None)]
    subnav = [("layers", "Drei Schichten" if de else "Three layers"),
              ("primitives", "Fünf Primitive" if de else "Five primitives")]
    return _doc_subpage("concepts", crumbs, "Datenmodell" if de else "Data model", lead,
                        "squareGrid", "var(--accent)", body, subnav)


def _doc_concepts() -> str:
    from .. import presentation as _pres
    de = _lang() == "de"
    li = 0 if de else 1

    def _card(d):
        name, pres = _art_name(d["art"], d["name"])
        glabel_de, glabel_en, gcolor = GROUP_MAP[d["group"]]
        open_lbl = ("Schema ansehen" if de else "View schema") if d["art"] in SCHEMAS else ("Mehr" if de else "More")
        return h("a", {"class_": "sl-card doccard", "href": f"/documentation/concepts/{d['art']}"},
            h("div", {"class_": "doc-h"},
              h("span", {"class_": "rico", "style": f"color:{pres['color']}"}, raw(_icon(d["icon"]))),
              h("span", {"class_": "doc-name"}, name),
              h("span", {"class_": "doc-gtag"},
                h("span", {"class_": "doc-gdot", "style": f"background:{gcolor}"}),
                glabel_de if de else glabel_en)),
            h("div", {"class_": "sl-prose sm doc-what"}, raw(_md(d["what"][li]))),
            h("div", {"class_": "doc-why"},
              h("span", {"class_": "doc-why-lbl"}, "Wofür" if de else "Why it matters"),
              h("span", {}, raw(_md_inline(d["why"][li])))),
            h("div", {"class_": "doc-open"}, open_lbl, raw("&nbsp;&rarr;")))

    # One dense grid: the artefacts (ordered by role band) + a Data-model card. Each opens a sub-page.
    order = [k for k, _ in GROUPS]
    cards = [_card(d) for d in sorted(DOCS, key=lambda d: order.index(d["group"]))]
    dm_card = h("a", {"class_": "sl-card doccard", "href": "/documentation/concepts/data-model"},
        h("div", {"class_": "doc-h"},
          h("span", {"class_": "rico", "style": "color:var(--accent)"}, raw(_icon("squareGrid"))),
          h("span", {"class_": "doc-name"}, "Datenmodell" if de else "Data model"),
          h("span", {"class_": "doc-gtag"},
            h("span", {"class_": "doc-gdot", "style": "background:var(--ink)"}),
            "Format")),
        h("div", {"class_": "sl-prose sm doc-what"}, raw(_md(
          ("Wie alles als JSON gespeichert wird: drei Schichten und die fünf gemeinsamen Primitive, aus "
           "denen jedes Artefakt besteht.") if de else
          ("How everything is stored as JSON: three layers and the five shared primitives every artefact "
           "is composed of.")))),
        h("div", {"class_": "doc-why"},
          h("span", {"class_": "doc-why-lbl"}, "Wofür" if de else "Why it matters"),
          h("span", {}, ("Verstehe das Datenformat — und exportiere/integriere sicher." if de
                         else "Understand the data format — and export/integrate with confidence."))),
        h("div", {"class_": "doc-open"}, ("Format ansehen" if de else "View the format"), raw("&nbsp;&rarr;")))
    grid = h("div", {"class_": "concept-grid"}, fragment(*cards, dm_card))

    lead = ("Die Vokabeln — jedes Artefakt ist ein Knoten in einer verknüpften Studie. "
            "Öffne ein Konzept für sein Daten-Schema." if de
            else "The vocabulary — every artefact is a node in one linked study. "
            "Open a concept for its data schema.")
    return _docs_shell("concepts", lead, grid)


def _doc_how() -> str:
    de = _lang() == "de"
    li = 0 if de else 1

    # The lifecycle as a visual pipeline (nodes + connectors), with the evidence node expanded into chips.
    stages = []
    for n, (ic, ti, sub) in enumerate(LIFECYCLE):
        if n:
            stages.append(h("div", {"class_": "flow-arrow"}, raw("&rarr;")))
        inner = [h("span", {"class_": "flow-ic"}, raw(_icon(ic))),
                 h("div", {"class_": "flow-t"}, ti[li]),
                 h("div", {"class_": "flow-s"}, sub[li])]
        if ti[1] == "Evidence":
            inner.append(h("div", {"class_": "flow-pills"},
                fragment(*(h("span", {"class_": "flow-pill"}, raw(_icon(pi)), lab)
                           for pi, lab in EVIDENCE_PILLS))))
        stages.append(h("div", {"class_": "flow-stage" + (" wide" if ti[1] == "Evidence" else "")}, *inner))
    pipeline = h("div", {"class_": "flow"}, fragment(*stages))
    loop = h("div", {"class_": "flow-loop"}, LOOP_NOTE[li])
    lifecycle = _anchor_block("lifecycle",
        _sub_h("Von der Frage zur Antwort" if de else "From question to answer"),
        h("p", {"class_": "doc-p"}, "Eine Studie folgt einem einfachen Bogen — und iteriert, bis die "
          "Evidenz überzeugt." if de else "A study follows one simple arc — and iterates until the "
          "evidence convinces."),
        pipeline, loop,
        h("div", {"class_": "doc-note", "style": "margin-top:14px"}, raw(_md(
          ("Ein Report entsteht *aus* der Evidenz — und ist selbst zitierbare Evidenz: Reports verketten "
           "sich so zu größeren Studien.") if de else
          ("A report is woven *from* the evidence — and is itself citable evidence, so reports chain into "
           "larger studies.")))))

    # How a study stays rigorous — the repeating Frame → Gather → Verify cycle.
    cyc = []
    for n, ((ti), body) in enumerate(RIGOUR_STEPS):
        if n:
            cyc.append(h("div", {"class_": "flow-arrow"}, raw("&rarr;")))
        cyc.append(h("div", {"class_": "cyc-step"},
            h("div", {"class_": "cyc-n"}, str(n + 1)),
            h("div", {"class_": "cyc-t"}, ti[li]),
            h("div", {"class_": "cyc-b"}, raw(_md_inline(body[li])))))
    cyc.append(h("div", {"class_": "flow-arrow loopback"}, raw("&#8635;")))
    rigour = _anchor_block("rigour",
        _sub_h("Warum man den Ergebnissen trauen kann" if de else "Why you can trust the result"),
        h("p", {"class_": "doc-p"}, "Sonaloop generiert nicht einfach drauflos. Jeder Schritt rahmt eine "
          "Frage, sammelt geerdete Evidenz und prüft, bevor es weitergeht — die Antwort ist belegt, nicht "
          "behauptet." if de else "Sonaloop doesn't just free-associate. Each step frames a question, "
          "gathers grounded evidence, and verifies before moving on — the answer is backed, not asserted."),
        h("div", {"class_": "cyc"}, fragment(*cyc)))

    subnav = [("lifecycle", "Von der Frage zur Antwort" if de else "Question → answer"),
              ("rigour", "Warum belastbar" if de else "Why trustworthy")]
    lead = ("Der Weg von der Frage zur Antwort — und was jeden Schritt belastbar hält." if de
            else "The path from question to answer — and what keeps every step trustworthy.")
    return _docs_shell("how-it-works", lead, fragment(lifecycle, rigour), subnav)


def _doc_inspector() -> str:
    """Working live — what the inspector itself offers the human: examples, live activity,
    runs, keyboard/palette, tour, the edit boundary, language, feedback. Pure data render
    over INSPECTOR_SECTIONS (the bilingual content lives in _docs_content.py)."""
    de = _lang() == "de"
    li = 0 if de else 1
    blocks = [_anchor_block(aid,
                h("div", {"class_": "doc-h", "style": "margin-bottom:10px"},
                  h("span", {"class_": "rico", "style": "color:var(--accent)"}, raw(_icon(ic))),
                  h("span", {"class_": "doc-name"}, title[li])),
                h("div", {"class_": "sl-prose doc-p"}, raw(_md(body[li]))))
              for aid, ic, title, body in INSPECTOR_SECTIONS]
    subnav = [(aid, title[li]) for aid, _ic, title, _b in INSPECTOR_SECTIONS]
    lead = ("Was der Inspector selbst kann, während dein Agent arbeitet — live, "
            "per Tastatur, und mit einer klaren Bearbeitungs-Grenze." if de
            else "What the inspector itself offers while your agent works — live, "
            "keyboard-first, and with one clear editing boundary.")
    return _docs_shell("inspector", lead, fragment(*blocks), subnav)


def _doc_methodology() -> str:
    from .. import methodology as _meth
    de = _lang() == "de"
    li = 0 if de else 1

    # Live list of every available methodology — Double Diamond is one card among several (+ custom).
    try:
        specs = list(_meth.registry().values())
    except Exception:
        specs = []
    meth_cards = []
    for s in sorted(specs, key=lambda x: (x.get("key") != "double_diamond", x.get("name", ""))):
        steps = [st.get("name", "") for st in s.get("steps", [])]
        pills = h("div", {"class_": "step-pills"},
                  fragment(*(h("span", {"class_": "step-pill"}, nm) for nm in steps if nm)))
        when = s.get("when_to_use", "")
        when_html = (h("div", {"class_": "methcard-when"},
                       h("b", {}, ("Wann" if de else "When") + ": "), when) if when else "")
        meth_cards.append(h("div", {"class_": "sl-card methcard"},
            h("div", {"class_": "methcard-h"},
              h("span", {"class_": "methcard-n"}, s.get("name", s.get("key", ""))),
              h("span", {"class_": "methcard-c"}, f'{len(steps)} ' + ("Phasen" if de else "phases"))),
            h("div", {"class_": "methcard-d"}, s.get("description", "")),
            when_html,
            pills))
    available = _anchor_block("available",
        _sub_h("Verfügbare Methodiken" if de else "Available methodologies"),
        h("div", {"class_": "doc-p"}, raw(_md(
          ("Eine Studie fährt eine **Methodik** — eine Abfolge von Phasen, die eine Frage von breiter "
           "Erkundung zu einer belastbaren Antwort führt. Sonaloop bringt mehrere mit, und du kannst "
           "eigene zusammenstellen.") if de else
          ("A study runs a **methodology** — a sequence of phases that takes a question from broad "
           "exploration to a confident answer. Sonaloop ships several, and you can compose your own.")))),
        h("div", {"class_": "methgrid"}, fragment(*meth_cards)))

    # The shared rhythm, with Double Diamond as the worked example.
    phase_cards = [h("div", {"class_": f"ddphase {rhythm}"},
        h("div", {"class_": "dd-rhythm"}, RHYTHM[rhythm][li]),
        h("div", {"class_": "dd-name"}, name),
        h("div", {"class_": "sl-prose sm dd-intent"}, raw(_md(intent[li]))))
        for name, rhythm, intent in DD_PHASES]
    anatomy = _anchor_block("anatomy",
        _sub_h("Der Rhythmus — am Beispiel Double Diamond" if de else "The rhythm — via Double Diamond"),
        h("div", {"class_": "doc-p"}, raw(_md(
          ("Die meisten Methodiken teilen denselben Takt: **öffnen** (breit erkunden), dann "
           "**verdichten** (zu einer Entscheidung). Double Diamond macht das zweimal — erst im "
           "Problemraum, dann im Lösungsraum.") if de else
          ("Most methodologies share the same beat: **diverge** (explore broadly), then **converge** "
           "(to a decision). Double Diamond does it twice — once in the problem space, once in the "
           "solution space.")))),
        h("div", {"class_": "ddphases"}, fragment(*phase_cards)),
        h("div", {"class_": "doc-note", "style": "margin-top:14px"}, raw(_md(
          ("Alle Methodiken teilen dieselbe Engine (rahmen → Evidenz sammeln → prüfen) — nur die Phasen "
           "unterscheiden sich.") if de else
          ("All methodologies share the same engine (frame → gather evidence → verify) — only the phases "
           "differ.")))))

    # Recipes — things you can ask your agent for.
    play_rows = [h("div", {"class_": "play"},
        h("div", {"class_": "play-l"}, h("span", {"class_": "play-name"}, ti[li]),
          h("code", {"class_": "play-code"}, code)),
        h("span", {"class_": "play-desc"}, raw(_md_inline(desc[li])))) for ti, code, desc in RECIPES]
    recipes = _anchor_block("recipes",
        _sub_h("Was du anfragen kannst" if de else "What you can ask for"),
        h("p", {"class_": "doc-p"}, "Fertige Abläufe, die dein Agent direkt fahren kann — vom einzelnen "
          "Council bis zur kompletten Studie." if de else "Ready-made flows your agent can run directly — "
          "from a single council to a whole study."),
        h("div", {"class_": "plays"}, fragment(*play_rows)))

    subnav = [("available", "Verfügbare Methodiken" if de else "Available methodologies"),
              ("anatomy", "Der Rhythmus" if de else "The rhythm"),
              ("recipes", "Was du anfragen kannst" if de else "What you can ask for")]
    lead = ("Eine Studie fährt eine austauschbare Methodik — Double Diamond ist nur eine davon." if de
            else "A study runs a swappable methodology — Double Diamond is just one of them.")
    return _docs_shell("methodology", lead, fragment(available, anatomy, recipes), subnav)


def _doc_mcp() -> str:
    de = _lang() == "de"
    li = 0 if de else 1
    from ..mcp_server._catalogue import catalogue_data
    data = catalogue_data()
    by_key = {dom["key"]: dom for dom in data["domains"]}

    def _dom_title(key, fallback):
        m = DOMAIN_META.get(key)
        return m[li] if m else fallback.split("(")[0].strip()
    def _dom_desc(key):
        m = DOMAIN_META.get(key)
        return m[2 + li] if m else ""
    def _tool_row(name, desc, kind=None):
        return h("div", {"class_": "mcp-tool"},
            h("code", {"class_": "mcp-tool-n"}, name),
            h("span", {"class_": "mcp-tool-d"},
              h("span", {"class_": "mcp-kind"}, kind) if kind else None,
              (" " if kind else "") + (desc or "—")))

    intro = h("div", {"class_": "sl-prose sm", "style": "max-width:78ch"},
        raw(_md(
          (f"Sonaloop ist **MCP-first** — die Tools *sind* die API ({data['total']} Tools, automatisch aus "
           "den Live-Modulen generiert). Konvention: `brief_*` sammelt Kontext, dann autort der Agent, dann "
           "validiert + persistiert `record_*` / `put_*`. Beginne mit der Resource "
           "`sonaloop://guide/research` für den kanonischen Pfad.") if de else
          (f"Sonaloop is **MCP-first** — the tools *are* the API ({data['total']} tools, auto-generated "
           "from the live modules). Convention: `brief_*` gathers context, then the agent authors, then "
           "`record_*` / `put_*` validates + persists. Start from the `sonaloop://guide/research` resource "
           "for the canonical path."))))

    # Build each super-group: an index card (its domains as pills) + the full sections under it.
    index_cards, sections, subnav = [], [], []
    for si, (t_de, t_en, d_de, d_en, keys) in enumerate(SUPER_GROUPS):
        # Resolve the (domain_key, title, count, desc, items, [kind]) tuples this super-group owns.
        resolved = []
        for key in keys:
            if key == "__extras__":
                if data["extras"]:
                    resolved.append(("extras", "Resources & prompts", len(data["extras"]),
                                     d_en if not de else d_de,
                                     [(e["name"], e["desc"], e["kind"]) for e in data["extras"]]))
            elif key in by_key:
                dom = by_key[key]
                resolved.append((key, _dom_title(key, dom["label"]), len(dom["items"]), _dom_desc(key),
                                 [(it["name"], it["desc"], None) for it in dom["items"]]))
        if not resolved:
            continue
        total = sum(r[2] for r in resolved)
        sid = f"s-{si}"
        subnav.append((sid, (t_de if de else t_en)))
        # Index card.
        pills = [h("a", {"class_": "mcp-pill", "href": f"#d-{rk}"}, rt,
                   h("span", {"class_": "mcp-pill-c"}, str(rc)))
                 for rk, rt, rc, _rd, _ri in resolved]
        index_cards.append(h("div", {"class_": "sl-card mcp-super-card"},
            h("div", {"class_": "mcp-super-card-h"},
              h("span", {"class_": "mcp-super-card-t"}, (t_de if de else t_en)),
              h("span", {"class_": "mcp-super-card-n"}, f"{total}")),
            h("div", {"class_": "mcp-super-card-d"}, (d_de if de else d_en)),
            h("div", {"class_": "mcp-pills"}, fragment(*pills))))
        # Full section: super heading + each domain sub-block.
        domblocks = []
        for rk, rt, rc, rd, items in resolved:
            tools = [_tool_row(*it) for it in items]
            domblocks.append(h("div", {"class_": "mcp-domain", "id": f"d-{rk}"},
                h("div", {"class_": "mcp-domain-h"},
                  h("span", {"class_": "mcp-domain-t"}, rt),
                  h("span", {"class_": "mcp-domain-c"}, str(rc)),
                  h("span", {"class_": "mcp-domain-d"}, rd) if rd else None),
                h("div", {"class_": "mcp-tools"}, fragment(*tools))))
        sections.append(h("div", {"class_": "mcp-super", "id": sid},
            h("h2", {"class_": "mcp-super-h"}, (t_de if de else t_en)),
            fragment(*domblocks)))

    index = h("div", {"class_": "mcp-superindex"}, fragment(*index_cards))
    lead = ("Sonaloop ist MCP-first — die Tools sind die API." if de
            else "Sonaloop is MCP-first — the tools are the API.")
    return _docs_shell("mcp", lead, fragment(intro, index, *sections), subnav)


def _doc_concept_detail(art: str) -> str:
    """A concept's deep-dive: description · what it holds · the real data schema · what it's made of."""
    d = next((x for x in DOCS if x["art"] == art), None)
    if not d:
        return ""
    de = _lang() == "de"
    li = 0 if de else 1
    name, pres = _art_name(art, d["name"])
    sc = SCHEMAS.get(art)

    blocks = [h("div", {"class_": "doc-note"},
                h("strong", {}, ("Wofür: " if de else "Why it matters: ")), raw(_md_inline(d["why"][li])))]
    subnav = []
    if sc:
        blocks.append(_anchor_block("holds",
            _sub_h("Was es enthält" if de else "What it holds"),
            h("ul", {"class_": "doc-caps"}, fragment(*(h("li", {}, raw(_md_inline(x))) for x in sc["holds"][li])))))
        blocks.append(_anchor_block("schema",
            _sub_h("Daten-Schema" if de else "Data shape"),
            h("div", {"class_": "doc-p"}, "Ein echter, gekürzter Record (gespeichert als JSON):" if de
              else "A real, trimmed record (stored as JSON):"),
            _code(EXAMPLES[art])))
        made_children = []
        if sc["made"]:
            made_children.append(h("div", {"class_": "doc-p"},
                "Zusammengesetzt aus den geteilten Primitiven:" if de else "Composed from the shared primitives:"))
            made_children.append(h("div", {"class_": "prim-chips"},
                fragment(*(h("a", {"class_": "prim-chip", "href": "/documentation/concepts#data-model"}, m)
                           for m in sc["made"]))))
        if sc.get("made_note"):
            made_children.append(h("div", {"class_": "doc-note", "style": "margin-top:12px"},
                                   raw(_md(sc["made_note"][li]))))
        blocks.append(_anchor_block("made",
            _sub_h("Woraus es besteht" if de else "What it's made of"), fragment(*made_children)))
        subnav = [("holds", "Was es enthält" if de else "What it holds"),
                  ("schema", "Daten-Schema" if de else "Data shape"),
                  ("made", "Woraus es besteht" if de else "What it's made of")]
    body = fragment(*blocks)

    # Prev/next across the concept order (same ordering as the Concepts grid).
    order = [k for k, _ in GROUPS]
    arts = sorted(DOCS, key=lambda x: order.index(x["group"]))
    aidx = next(i for i, x in enumerate(arts) if x["art"] == art)
    def _pn(x, kind):
        if not x:
            return h("span", {})
        xn, _ = _art_name(x["art"], x["name"])
        eye = ("Zurück" if de else "Back") if kind == "prev" else ("Weiter" if de else "Next")
        return h("a", {"class_": f"pn {kind}", "href": f"/documentation/concepts/{x['art']}"},
                 h("span", {"class_": "pn-eye"}, eye),
                 h("span", {"class_": "pn-lab"}, raw("&larr;&nbsp;") if kind == "prev" else None, xn,
                   raw("&nbsp;&rarr;") if kind == "next" else None))
    footer = h("div", {"class_": "doc-pn"},
        _pn(arts[aidx - 1] if aidx > 0 else None, "prev"),
        _pn(arts[aidx + 1] if aidx < len(arts) - 1 else None, "next"))

    crumbs = [(t("documentation"), "/documentation"),
              (("Konzepte" if de else "Concepts"), "/documentation/concepts"), (name, None)]
    return _doc_subpage("concepts", crumbs, name, d["what"][li], d["icon"], pres["color"],
                        body, subnav or None, footer)


# slug -> renderer (top-level tabs).  Sub-pages opened from cards:
_PAGES = {
    "": _doc_overview, "concepts": _doc_concepts, "how-it-works": _doc_how,
    "inspector": _doc_inspector, "methodology": _doc_methodology, "mcp": _doc_mcp,
    "principles": _doc_principles_page,
}
_CONCEPT_ARTS = {d["art"] for d in DOCS}


def register_docs(app) -> None:
    """Register the documentation hub: top pages + card-opened sub-pages (concept details, data model)."""
    from fastapi import HTTPException
    from fastapi.responses import HTMLResponse

    @app.get("/documentation", response_class=HTMLResponse)   # not /docs (FastAPI reserves that for Swagger)
    def docs_home() -> str:
        return _doc_overview()

    @app.get("/documentation/concepts/{art}", response_class=HTMLResponse)
    def docs_concept_detail(art: str) -> str:
        if art == "data-model":
            return _doc_data_model_page()
        if art not in _CONCEPT_ARTS:
            raise HTTPException(status_code=404)
        return _doc_concept_detail(art)

    @app.get("/documentation/{slug}", response_class=HTMLResponse)
    def docs_page(slug: str) -> str:
        fn = _PAGES.get(slug)            # includes the Principles sub-page (not a tab)
        if not fn or slug == "":
            raise HTTPException(status_code=404)
        return fn()
