"""Detail-page building blocks: the shared detail_page() shell + the Linear-style Relations / Properties
panels (spec/design-system.md). Every artifact detail page (council, synthesis, note, section,
prototype) is assembled by detail_page(), so the structure — hero, content column, Properties→Relations
aside, section minimap, topbar star — is identical by construction instead of duplicated per route."""
from __future__ import annotations

from .. import services
from ._i18n import t
from ._components import _esc, _icon, _hero, _doc, _layout, _star, _prose, _avatar, _label  # noqa: F401
from ._rail import _page_rail
from ._slide import slide_mode
from ._html import h, raw, fragment, register_css
from ._primitive_taxonomy import form_label, survey_question_form_labels

# The shared header's first line (ux-contract §8.2 — ONE detail anatomy): the kind eyebrow +
# the status pills ride the design-system `sl-page-header__top` slot; the generic `.eyebrow`
# brings its own bottom margin (the _study_lead context), which the flex top slot neutralises.
register_css(".sl-page-header__top .eyebrow{margin:0}")

# The slide-over variant (§8.1 + §9 V5): in the ~700px panel there is no second column, so
# the Properties→Relations aside flows right under the header — the Notion anatomy (eyebrow,
# title, breathing room, quiet frameless properties, hairline, then the content). The
# rhythm fix is deliberate: eyebrow→title→props sat "viel zu nah beieinander" in round 3.
register_css(".rail--slide{position:static;margin:20px 0 28px;padding:0 0 20px;"
             "border-bottom:1px solid var(--line-2)}")

# Round-4 J5: in the narrow 280px page rail a LONG value beside the 8.5rem label column wraps
# 3-4 cramped lines — rows whose plain-text value can't read inline TIER instead (label line,
# then the value at the rail's full width). Inline rows keep the Notion anatomy unchanged; the
# wide slide-over props card never tiers (the value fits beside the label there).
register_css(".rail:not(.rail--slide) .sl-prop--tier{flex-wrap:wrap;row-gap:4px}"
             ".rail:not(.rail--slide) .sl-prop--tier .sl-prop__v{flex-basis:100%}")

# A plain-string value longer than this reads cramped beside the rail's label column
# (~21 chars/line at the rail width) — the tier threshold for _properties_html.
_TIER_CHARS = 28


def _detail_trace_graph(store, proj_id: str) -> dict | None:
    try:
        g = services.get_project_graph(proj_id, store=store)
        from ._graph_outline_sessions import outline_session_groups
        from ._project_graph_view import augment_project_graph
        proto_ids = {p.get("id") for p in (g.get("prototypes") or [])}
        proto_sessions = [s for s in store.list_prototype_sessions() if s.get("prototype_id") in proto_ids]
        sessions = outline_session_groups(
            services.list_usability_sessions(project_id=proj_id, store=store), store,
            prototype_sessions=proto_sessions)
        return augment_project_graph(
            g, sessions=sessions,
            decisions=services.list_decisions(proj_id, store=store),
            hypotheses=services.list_hypotheses(proj_id, store=store),
            surveys=services.list_surveys(project_id=proj_id, store=store),
            assets=list(g.get("assets") or []))
    except Exception:
        return None


def detail_eyebrow(kind: str, pills=()) -> str:
    """The first line of EVERY detail header (ux-contract §8.2): the kind eyebrow ("COUNCIL",
    "DECISION", "PROTOTYPE SESSION", …) followed by the record's status pills. Pages pass the
    result as `_hero(top=…)` / `detail_page(kind=…, pills=…)` so the anatomy is identical by
    construction across all artifact kinds."""
    return fragment(h("span", {"class_": "eyebrow"}, kind),
                    *[raw(str(p)) for p in pills if p])


def detail_form_rows(kind: str, rec: dict) -> list[tuple[str, str, str]]:
    """The taxonomy Form row shared by every primitive detail page.

    The eyebrow names the primitive (Council, Survey, Prototype). This row names
    the concrete form inside that primitive (Discovery, Red-team, Model, ...).
    """
    if kind == "survey":
        labels = survey_question_form_labels(rec or {})
        return [("tag", t("question_forms_h"), ", ".join(labels))] if labels else []
    label = form_label(kind, rec or {})
    return [("tag", t("form_h"), label)] if label else []


def _relations_html(store, study_id: str, proj_id: str | None,
                    extra_in: list | None = None, extra_out: list | None = None, aside: bool = False,
                    include_in: bool = True, include_out: bool = True) -> str:
    """Linear-style RELATIONS block for a detail page (progressive disclosure: precise links live HERE,
    not in the list). Built from the project graph's real plan-evidence edges — what this was BASED ON
    (incoming) and what it FEEDS INTO (outgoing) — plus any caller-supplied extra links (e.g. a prototype's
    concept). Returns "" when there's nothing to show."""
    incoming, outgoing = list(extra_in or []), list(extra_out or [])
    if proj_id:
        try:
            g = _detail_trace_graph(store, proj_id)
        except Exception:
            g = None
        if g:
            nmap = {n["study_id"]: n for n in g["nodes"]}
            for e in g.get("edges", []):
                if e.get("to_study") == study_id and e.get("from_study") in nmap:
                    n = dict(nmap[e["from_study"]])
                    n["rel_label"] = e.get("label") or e.get("type", "")
                    incoming.append(n)
                elif e.get("from_study") == study_id and e.get("to_study") in nmap:
                    n = dict(nmap[e["to_study"]])
                    n["rel_label"] = e.get("label") or e.get("type", "")
                    outgoing.append(n)
            cur = nmap.get(study_id)
            for pid in (cur or {}).get("prototype_ids", []):  # a built note → its prototype(s) (not a graph edge)
                pr = next((p for p in g.get("prototypes", []) if p["id"] == pid), None)
                if pr:
                    outgoing.append({"href": f'/prototypes/{pr["slug"]}', "title": pr["name"],
                                     "color": "#00897b", "kind_label": t("prototypes_h")})

    def _dedupe(ns: list) -> list[dict]:
        out: list[dict] = []
        seen: dict[tuple[str, str], dict] = {}
        for n in ns:
            kind = str(n.get("kind_label", n.get("kind", "")))
            title = str(n.get("title", ""))
            key = (kind, title)
            if key not in seen:
                row = dict(n)
                row["_kind_label"] = kind
                row["_rel_labels"] = []
                row["_count"] = 0
                seen[key] = row
                out.append(row)
            row = seen[key]
            row["_count"] += 1
            rel = str(n.get("rel_label") or n.get("type") or "")
            if rel and rel not in row["_rel_labels"]:
                row["_rel_labels"].append(rel)
        return out

    def grp(label, ns):
        if not ns:
            return ""
        ns = _dedupe(ns)
        rows = fragment(*(
            h("a", {"class_": "relrow", "href": n.get("href", "")},
              h("span", {"class_": "ol-dot", "style": f"background:{n.get('color', '#9aa0a6')}"}),
              h("span", {"class_": "relt"}, n.get("title", "")),
              h("span", {"class_": "muted small"},
                " · ".join(x for x in (
                    (f'{n["_count"]}x {n["_kind_label"]}' if n.get("_count", 1) > 1 else n["_kind_label"]),
                    ", ".join(n.get("_rel_labels") or []),
                ) if x)))
            for n in ns))
        return h("div", {"class_": "relgrp"}, h("div", {"class_": "rellbl"}, label), rows)

    blocks = fragment(grp(t("rel_based_on"), incoming if include_in else []),
                      grp(t("rel_feeds_into"), outgoing if include_out else []))
    if not blocks:
        return ""
    if aside:                                                  # plain uppercase header, uniform with Properties
        return fragment(h("h4", {"id": "sec-relations"}, t("relations")), blocks)
    return h("div", {"class_": "sl-card relcard", "id": "sec-relations"},
             h("div", {"class_": "relh"}, raw(_icon("link")), " ", t("relations")), blocks)



def _properties_html(rows, aside: bool = False) -> str:
    """Notion-style QUIET properties (ux-contract §9 V5): icon + label + value per row over
    the vendored frameless `.sl-props--quiet` contract — no card box, muted label column,
    regular-weight values, gap-token rhythm. Skips empty values. aside=True renders a bare
    section (h4 + rows) to sit inside the detail aside / slide-over flow. Long plain-text
    values tier in the narrow page rail (round-4 J5, the `--tier` rule above)."""
    proprows = [h("div", {"class_": "sl-prop"
                          + (" sl-prop--tier" if isinstance(val, str) and len(val) > _TIER_CHARS
                             else "")},
                  h("span", {"class_": "sl-prop__k"}, raw(_icon(ic)), lbl),
                  h("span", {"class_": "sl-prop__v"}, val))            # text auto-escaped; h-built links (Safe) kept
                for ic, lbl, val in rows if val not in (None, "", "—")]
    if not proprows:
        return ""
    inner = h("div", {"class_": "sl-props sl-props--quiet"}, fragment(*proprows))
    if aside:
        return fragment(h("h4", {"id": "sec-properties"}, t("properties")), inner)
    return h("div", {"class_": "sl-props sl-props--quiet", "id": "sec-properties"},
             h("div", {"class_": "relh"}, t("properties")), fragment(*proprows))


def detail_page(store, *, title: str, active: str, crumbs: list, body,
                hero=None, icon: str | None = None, sub=None, hid: str | None = None,
                kind: str | None = None, pills=(),
                prop_rows: list | None = None,
                rel_study_id: str | None = None, rel_proj_id: str | None = None,
                rel_extra_in: list | None = None, rel_extra_out: list | None = None,
                rel_include_in: bool = True, rel_include_out: bool = True,
                rail_sections: list | None = None, star: tuple | None = None,
                actions: str = "", aside_extra: str = "") -> str:
    """The ONE detail-page shell every artifact page extends — consistency by construction.

    Assembles: hero · content column (`body`) · Properties→Relations aside (always that order) · the
    section minimap (`rail_sections` + auto Properties/Relations anchors) · a topbar favourite star.

    - `hero`: a pre-built hero (Safe) — e.g. the synthesis syn-head, or "" to omit. If None, the
      component builds `_hero(title, icon=, sub=, hid=)` — with the shared eyebrow line
      (`kind` + status `pills`, §8.2) in the header's top slot when `kind` is given. Pages that
      build their own hero compose the same line via detail_eyebrow() + `_hero(top=…)`.
    - `body`: the content after the hero (Safe).
    - `prop_rows`: `[(icon, label, value), …]` for Properties (empty values are skipped).
    - `rel_study_id`/`rel_proj_id`/`rel_extra_*`: build the Relations panel from the project graph.
    - `star`: `(kind, ident, label, href)` for the topbar favourite.
    - `actions`: extra topbar HTML (e.g. the Edit affordance) rendered before the star.
    """
    top = detail_eyebrow(kind, pills) if kind else None
    hero_html = hero if hero is not None else _hero(title, icon=icon, sub=sub, hid=hid, top=top)
    # The palette's recents beacon (UX V6): one injection point covers EVERY artifact detail
    # page — full page, ?slide=1 fragment and the ?d= SSR panel alike. The owning project's
    # title rides the existing crumbs (the /jobs/{id} crumb), no new parameter.
    from ._palette import visit_marker
    beacon = visit_marker(title, next((lbl for lbl, href in (crumbs or [])
                                       if href and str(href).startswith("/jobs/")), ""))
    props = _properties_html(prop_rows, aside=True) if prop_rows else ""
    rel = ""
    if rel_study_id:
        rel = _relations_html(store, rel_study_id, rel_proj_id, extra_in=rel_extra_in,
                              extra_out=rel_extra_out, aside=True,
                              include_in=rel_include_in, include_out=rel_include_out)
    acts = fragment(raw(actions), raw(_star(*star)) if star else "")
    # The slide-over variant (§8.1) — the SAME renderer, one flag: header, then the aside as an
    # in-flow properties card (the Notion anatomy), then the content; the fixed-position minimap
    # is skipped (it would overlay the host page, not the panel). _layout strips the chrome and
    # carries `acts` (the V10 overflow + dialogs + star) as the hidden [data-slide-actions]
    # block the drawer hoists into its header.
    if slide_mode():
        aside = (str(h("aside", {"class_": "rail rail--slide"},
                       raw(props), raw(aside_extra), raw(rel)))
                 if (props or aside_extra or rel) else "")
        body_html = str(body)
        if aside and not str(hero_html):
            # hero-less pages (the report shell) open with their own <header> cover at the head
            # of the body — the properties card slots right UNDER it, never above the title.
            cut = body_html.find("</header>")
            cut = cut + len("</header>") if cut != -1 else 0
            content = raw(body_html[:cut] + aside + body_html[cut:])
        else:
            content = raw(str(hero_html) + aside + body_html)
        page = h("div", {"class_": "page"}, h("div", {"class_": "doc-main"}, content), raw(beacon))
        return _layout(title, page, store, crumbs=crumbs, active=active, actions=str(acts))
    main = fragment(raw(hero_html), body, raw(beacon))
    # The right-edge TOC (scrollspy) indexes the MAIN-content sections only — Properties/Relations live in
    # the aside, not the scrolling column, so they must NOT appear as TOC ticks.
    rail = list(rail_sections or [])
    page = _doc(main, rail=raw(props) + raw(aside_extra) + raw(rel)) + _page_rail(rail)
    return _layout(title, page, store, crumbs=crumbs, active=active, actions=acts)
