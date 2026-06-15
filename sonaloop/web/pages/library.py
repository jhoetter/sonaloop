"""The Library — ONE browser over every produced primitive (spec/ux-contract.md §3.5) —
plus the library detail pages: sections, notes, prototypes (spec/roadmap.md R2).

/library renders `ui.tabs` across the 8 produced kinds; every tab is the SAME shape:
the kind's existing list read rendered as `ui.primitive_row` rows (canonical href; click
opens it as the slide-over, §8.1) through the shared _list_page shell. The old list routes (/councils,
/syntheses, /prototypes, /sessions, /surveys, /hypotheses, /decisions, /notes) stay
registered — their handlers render the library with that tab active, so deep links and
`next_recommended_tool` hints survive without redirects; the tab links use the
canonical routes, ?tab= addresses a tab on /library itself. Detail routes unchanged."""
from __future__ import annotations

from ._ctx import *  # noqa: F401,F403  (shared render toolkit)
from .sessions import _sessions_section
from .. import ui
from .._html import register_css
from .._filterbar import filter_bar, parse_multi
from .._forms import overflow_delete
from .edit import note_actions, section_actions
from .._presence import asset_direction, record_status, status_filter_label
from .._primitive_taxonomy import (
    family_icon, family_label, primitive_family, primitive_purpose, subtype_label, subtype_value,
)

# (key, canonical route, icon, label, empty-state msg, lead, teach) — labels are lambdas so
# they resolve per request (i18n, the _nav_seed idiom). Tab order is the methodology arc:
# question/evidence → debate → synthesis → build → test → measure → bet → decide → note.
# `teach` is the first-use empty state's next action (audit F1, contract C8 "teach"): the UI
# is read-only, so it names the MCP verb that produces the kind — the import_survey_responses
# idiom.
LIBRARY_TABS: tuple = (
    ("questions", "/open-questions", "help",
     lambda: t("open_questions_h"), lambda: t("no_open_questions"), lambda: t("open_questions_lead"),
     lambda: t("open_questions_teach")),
    ("references", "/references", "link",
     lambda: t("references_h"), lambda: t("no_references"), lambda: t("references_lead"),
     lambda: t("references_teach")),
    ("councils", "/councils", "councils",
     lambda: t("councils"), lambda: t("no_councils"), lambda: t("councils_lead"),
     lambda: t("councils_teach")),
    ("reports", "/syntheses", "syntheses",
     lambda: t("syntheses"), lambda: t("no_synthesis"), lambda: t("syntheses_lead"),
     lambda: t("reports_teach")),
    ("prototypes", "/prototypes", "prototype",
     lambda: t("prototypes_h"), lambda: t("no_prototypes"), lambda: t("prototypes_lead"),
     lambda: t("prototypes_teach")),
    ("flows", "/flows", "compass",
     lambda: t("flows_h"), lambda: t("no_flows"), lambda: t("flows_lead"),
     lambda: t("flows_teach")),
    ("sessions", "/sessions", "activity",
     lambda: t("sessions"), lambda: t("no_sessions"), lambda: t("sessions_lead"),
     lambda: t("sessions_teach")),
    ("surveys", "/surveys", "plan",
     lambda: t("surveys_h"), lambda: t("no_surveys"), lambda: t("surveys_lead"),
     lambda: t("surveys_teach")),
    ("hypotheses", "/hypotheses", "target",
     lambda: t("hypotheses_h"), lambda: t("no_hypotheses"), lambda: t("hypotheses_lead"),
     lambda: t("hypotheses_teach")),
    ("decisions", "/decisions", "flag",
     lambda: t("decisions_h"), lambda: t("no_decisions"), lambda: t("decisions_lead"),
     lambda: t("decisions_teach")),
    ("notes", "/notes", "panel",
     lambda: t("notes"), lambda: t("no_notes"), lambda: t("notes_lead"),
     lambda: t("notes_teach")),
    # Assets close the arc (UX U8 §8.3): what came IN (evidence received via MCP) and what went
    # OUT (deliverables the software generated) — files as first-class, provenance-carrying rows.
    ("assets", "/assets", "clipboard",
     lambda: t("assets_h"), lambda: t("no_assets"), lambda: t("assets_lead"),
     lambda: t("assets_teach")),
)

TAB_KIND = {
    "questions": "open_question",
    "references": "url_artifact",
    "councils": "council",
    "reports": "synthesis",
    "prototypes": "prototype",
    "flows": "flow",
    "sessions": "session",
    "surveys": "survey",
    "hypotheses": "hypothesis",
    "decisions": "decision",
    "notes": "note",
    "assets": "asset",
}


def _tab_entries(key: str, store: Store, sessions: list | None = None) -> list[dict]:
    """The active tab's records as filterable entries {kind, rec, href, desc, project_id} —
    the kind's EXISTING list read; rows render through the one row vocabulary
    (ui.primitive_row — §3.2) AFTER the U10 facet filter ran, with the owning project's
    title as the muted desc line (this is a CROSS-project browser — the row must say where
    it lives). Every href is the canonical detail URL the slide-over pushes (§8.1)."""
    projects = {p["id"]: p["title"] for p in store.list_research_projects()}
    def e(kind, rec, href, project_id=None, desc=None):
        pid = rec.get("project_id") or project_id or ""
        return {"kind": kind, "rec": rec, "href": href, "project_id": pid,
                "desc": projects.get(pid, "") if desc is None else desc}
    if key == "questions":
        rows = []
        for proj in store.list_research_projects():
            for o in store.list_open_questions(proj["id"]):
                rows.append(e("open_question", o, f'/open-questions/{o["id"]}', project_id=proj["id"]))
        return rows
    if key == "references":
        pairs = [(a, proj["id"]) for proj in store.list_research_projects()
                 for a in proj.get("artifacts") or []]
        pairs.sort(key=lambda x: x[0].get("created_at", ""), reverse=True)
        return [e("url_artifact", a, f'/references/{a["id"]}', project_id=pid) for a, pid in pairs]
    if key == "councils":
        return [e("council", {**c, "mode": services.council_mode(c)}, f'/councils/{c["id"]}')
                for c in store.list_council_sessions()]
    if key == "reports":
        return [e("synthesis", s, f'/syntheses/{s["id"]}') for s in store.list_syntheses()]
    if key == "prototypes":
        # the W11 crew enrichment (n_sessions BOTH kinds + the drivers' personas/voices) —
        # the same services read the outline rows use, so the avatars never diverge
        return [e("prototype", {**p, **services.prototype_participation(p, store)},
                  f'/prototypes/{p["slug"]}')
                for p in store.list_prototypes()]
    if key == "flows":
        pairs = []
        for proj in store.list_research_projects():
            for f in services.list_flows(proj["id"], store=store):
                sessions_n = len(services.list_usability_sessions(
                    project_id=proj["id"], subject={"kind": "flow", "id": f["id"]}, store=store))
                pairs.append(({**f, "project_id": proj["id"], "n_sessions": sessions_n},
                              proj["id"]))
        pairs.sort(key=lambda x: x[0].get("updated_at", ""), reverse=True)
        return [e("flow", f, f'/flows/{f["id"]}', project_id=pid) for f, pid in pairs]
    if key == "sessions":
        if sessions is None:
            # BOTH session kinds (§8.2 — sessions are first-class): usability walks and
            # prototype reactions, one row vocabulary, newest first.
            from .sessions import proto_session_rows
            sessions = sorted(
                services.list_usability_sessions(store=store) + proto_session_rows(store),
                key=lambda s: s.get("created_at", ""), reverse=True)
        # desc stays the per-kind default: the walked subject says more than the project here.
        return [e("session", s, f'/sessions/{s["id"]}', desc="") for s in sessions]
    if key == "surveys":
        return [e("survey", s, f'/surveys/{s["id"]}') for s in services.list_surveys(store=store)]
    if key == "hypotheses":
        return [e("hypothesis", x, f'/hypotheses/{x["id"]}')
                for x in services.list_hypotheses(store=store)]
    if key == "decisions":
        return [e("decision", d, f'/decisions/{d["id"]}')
                for d in services.list_decisions(store=store)]
    if key == "notes":
        return [e("note", n, f'/notes/{n["id"]}', project_id=proj["id"])
                for proj in store.list_research_projects()
                for n in services.list_notes(proj["id"], store=store)]
    if key == "assets":
        pairs = [(a, proj["id"]) for proj in store.list_research_projects()
                 for a in proj.get("assets") or []]
        pairs.sort(key=lambda x: x[0].get("created_at", ""), reverse=True)
        return [e("asset", a, f'/assets/{a["id"]}', project_id=pid) for a, pid in pairs]
    return []


def _find_open_question(store: Store, question_id: str) -> tuple[dict | None, dict | None]:
    for proj in store.list_research_projects():
        for o in store.list_open_questions(proj["id"]):
            if o.get("id") == question_id:
                return proj, o
    return None, None


def _find_reference(store: Store, reference_id: str) -> tuple[dict | None, dict | None]:
    for proj in store.list_research_projects():
        for a in proj.get("artifacts") or []:
            if a.get("id") == reference_id or a.get("label") == reference_id:
                return proj, a
    return None, None


def _find_flow(store: Store, flow_id: str) -> tuple[dict | None, dict | None]:
    for proj in store.list_research_projects():
        try:
            return proj, services.get_flow(proj["id"], flow_id, store=store)
        except KeyError:
            continue
    return None, None


def _reference_status_pill(ref: dict) -> str:
    snap = ref.get("snapshot") or {}
    if snap.get("ok"):
        return _label(t("artifact_captured"), "var(--green)")
    return _label(t("artifact_capture_failed"), "var(--muted)")


def _flow_steps_html(flow: dict, project: dict) -> str:
    assets = {a["id"]: a for a in project.get("assets") or []}
    rows = []
    for s in flow.get("steps") or []:
        a = assets.get(s.get("asset_id"), {})
        title = a.get("title") or a.get("filename") or s.get("asset_id", "")
        rows.append(h("div", {"class_": "strow"},
                      h("b", {}, h("a", {"href": f'/assets/{s.get("asset_id", "")}'}, title)),
                      h("div", {"class_": "muted small"},
                        t("step_n", n=int(s.get("index", 0)) + 1), " · ", s.get("caption", ""))))
    return fragment(*rows)


def _library_facets(entries: list[dict], store: Store, *, with_direction: bool) -> list[dict]:
    """The tab's facet model for the FilterBar (U10 §8.5): project + status everywhere they
    actually occur, + direction (in/out) on the Assets tab. Counts over the unfiltered set;
    values that no row carries never become options (honest, no dead entries)."""
    from collections import Counter
    projects = {p["id"]: p["title"] for p in store.list_research_projects()}
    proj_n: Counter = Counter(x["project_id"] for x in entries if x["project_id"])
    status_n: Counter = Counter()
    status_lbl: dict[str, str] = {}
    subtype_n: Counter = Counter()
    dir_n: Counter = Counter()
    for x in entries:
        st = record_status(x["kind"], x["rec"])
        if st:
            status_n[st] += 1
            status_lbl.setdefault(st, status_filter_label(x["kind"], st))
        sub = subtype_value(x["kind"], x["rec"])
        if sub:
            subtype_n[sub] += 1
        if with_direction:
            dir_n[asset_direction(x["rec"])] += 1
    facets = [
        {"key": "project", "label": t("project"), "icon": "projects",
         "options": [{"value": p, "label": projects.get(p, p), "count": n}
                     for p, n in proj_n.most_common()]},
        {"key": "status", "label": t("status_h"), "icon": "flag",
         "options": [{"value": s, "label": status_lbl[s], "count": n}
                     for s, n in status_n.most_common()]},
        {"key": "subtype", "label": t("subtype_h"), "icon": "tag",
         "options": [{"value": s, "label": subtype_label(s), "count": n}
                     for s, n in subtype_n.most_common()]},
    ]
    if with_direction:
        dir_label = {"in": t("asset_dir_in"), "out": t("asset_dir_out")}
        facets.append({"key": "direction", "label": t("direction_h"), "icon": "exchange",
                       "options": [{"value": d, "label": dir_label.get(d, d), "count": n}
                                   for d, n in dir_n.most_common()]})
    return facets


def _entry_blob(x: dict, store: Store) -> str:
    """The searchable text of one library row (V1 `?q=`): what the row visibly shows — its
    title fields, the muted desc/subject line, the persona name (sessions title with it) and
    the status chip label. Mirrors the row, so search never matches invisible data."""
    rec = x["rec"]
    parts = [rec.get("prompt"), rec.get("title"), rec.get("name"), rec.get("text"),
             rec.get("filename"), (rec.get("subject") or {}).get("label"), x.get("desc")]
    if rec.get("persona_id"):
        parts.append((store.get_persona(rec["persona_id"]) or {}).get("display_name"))
    st = record_status(x["kind"], rec)
    if st:
        parts.append(status_filter_label(x["kind"], st))
    sub = subtype_value(x["kind"], rec)
    if sub:
        parts.append(subtype_label(sub))
    return " ".join(str(p) for p in parts if p)


def _taxonomy_context(tab: str, kind: str) -> str:
    family = primitive_family(kind)
    purpose = primitive_purpose(kind)
    if not purpose:
        return ""
    return h("div", {"class_": "taxctx", "data-family": family},
             h("span", {"class_": "taxctx__eyebrow"}, t("primitive_h")),
             h("span", {"class_": "taxctx__family"}, family_label(family)),
             h("span", {"class_": "taxctx__dot"}, "·"),
             h("span", {"class_": "taxctx__purpose"}, purpose))


def _library_nav(active_tab: str) -> str:
    """Two-level Library navigation: users first choose the role a primitive plays, then the
    specific primitive inside that role. This keeps the mental model visible instead of showing
    twelve peer tabs that look like implementation details."""
    rows = list(LIBRARY_TABS)
    active_kind = TAB_KIND.get(active_tab, "open_question")
    active_family = primitive_family(active_kind)
    families: list[tuple[str, list[tuple]]] = []
    for row in rows:
        k = row[0]
        fam = primitive_family(TAB_KIND.get(k, "note"))
        bucket = next((items for f, items in families if f == fam), None)
        if bucket is None:
            bucket = []
            families.append((fam, bucket))
        bucket.append(row)
    primary = []
    for fam, items in families:
        first = items[0]
        route = first[1]
        on = fam == active_family
        primary.append(h("a", {"class_": "libnav-family is-active" if on else "libnav-family",
                               "href": route, "aria-current": "page" if on else None},
                         raw(_icon(family_icon(fam))), h("span", {}, family_label(fam))))
    secondary = []
    for row in next(items for fam, items in families if fam == active_family):
        key, route, icon, label, *_ = row
        on = key == active_tab
        secondary.append(h("a", {"class_": "libnav-kind is-active" if on else "libnav-kind",
                                 "href": route, "aria-current": "page" if on else None},
                           raw(_icon(icon)), h("span", {}, label())))
    return fragment(h("div", {"class_": "libnav libnav--family"}, fragment(*primary)),
                    h("div", {"class_": "libnav libnav--kind"}, fragment(*secondary)))


def library_page(tab: str = "questions", store: Store | None = None, *,
                 sessions: list | None = None, pre_extra: str = "",
                 flt: dict | None = None, base: str | None = None, q: str = "") -> str:
    """The one Library browser. `sessions` lets the /sessions route keep its honest
    project/subject query filters; `pre_extra` carries a tab's extra read (the sessions
    funnel, the hypotheses hit-rate strip) between the tab bar and the rows.

    U10/V1 (§8.5, §9 V1): `flt` = {project/status/direction -> [values]} from the URL applies
    the shared FilterBar semantics (OR within a facet, AND across) server-side; `q` is the
    tab's text search, composing with the facets; `base` is the canonical path the bar's
    links target (defaults to /library?tab=…), so /councils, /sessions … keep their own
    addresses while sharing the one bar."""
    from urllib.parse import quote
    from .._graph_outline import _q_match
    store = store or Store()
    keys = [k for k, *_ in LIBRARY_TABS]
    if tab not in keys:
        tab = keys[0]
    tabs_html = _library_nav(tab)
    _k, _route, icon, tab_label, empty_msg, lead, teach = next(
        row for row in LIBRARY_TABS if row[0] == tab)
    tab_kind = TAB_KIND.get(tab, "note")
    base0 = base or f"/library?tab={tab}"
    base = base0 + (("&" if "?" in base0 else "?") + f"q={quote(q)}" if q else "")
    selected = {k: v for k, v in (flt or {}).items()}
    entries = _tab_entries(tab, store, sessions=sessions)
    facets = _library_facets(entries, store, with_direction=tab == "assets")
    bar = (str(filter_bar(base, facets, selected,
                          search={"value": q,
                                  "placeholder": t("search_tab_ph", tab=tab_label())}))
           if entries else "")
    active = {k: v for k, v in selected.items() if v}
    if active or q:
        def keep(x: dict) -> bool:
            if active.get("project") and x["project_id"] not in active["project"]:
                return False
            if active.get("status") and record_status(x["kind"], x["rec"]) not in active["status"]:
                return False
            if active.get("subtype") and subtype_value(x["kind"], x["rec"]) not in active["subtype"]:
                return False
            if active.get("direction") and asset_direction(x["rec"]) not in active["direction"]:
                return False
            if q and not _q_match(q, _entry_blob(x, store)):
                return False
            return True
        kept = [x for x in entries if keep(x)]
    else:
        kept = entries
    rows = [ui.primitive_row(x["kind"], x["rec"], store, href=x["href"], drawer=True,
                             desc=x["desc"] or None)
            for x in kept]
    if entries and not rows:                       # filters matched nothing — teach (C8/F1)
        return _list_page(store, title=t("library_h"), lead=lead(), rows=[],
                          empty_icon="filter", empty_msg=t("filter_no_matches_h"),
                          empty_teach=t("filter_no_matches"),
                          empty_action=(t("clear_filter"), base0, "filter"),
                          active="library",
                          pre=str(tabs_html) + _taxonomy_context(tab, tab_kind) + bar + pre_extra,
                          count=0)
    return _list_page(store, title=t("library_h"), lead=lead(), rows=rows,
                      empty_icon=icon, empty_msg=empty_msg(), empty_teach=teach(),
                      active="library",
                      pre=str(tabs_html) + _taxonomy_context(tab, tab_kind) + bar + pre_extra,
                      count=len(rows))


def library_filters(project: str = "", status: str = "", direction: str = "",
                    subtype: str = "") -> dict:
    """Parse the shared Library filter params (?project=…&status=…&direction=… — comma = OR)
    into the `flt` dict library_page applies; the canonical tab routes all funnel through
    this so the URL grammar stays identical everywhere."""
    return {"project": parse_multi(project), "status": parse_multi(status),
            "direction": parse_multi(direction), "subtype": parse_multi(subtype)}


def register_library(app) -> None:
    @app.get("/library", response_class=HTMLResponse)
    def library(tab: str = Query(default="questions"), project: str = Query(default=""),
                status: str = Query(default=""), direction: str = Query(default=""),
                subtype: str = Query(default=""), q: str = Query(default="")) -> str:
        return library_page(tab, flt=library_filters(project, status, direction, subtype), q=q)

    @app.get("/open-questions", response_class=HTMLResponse)
    def open_questions_list(project: str = Query(default=""), status: str = Query(default=""),
                            subtype: str = Query(default=""), q: str = Query(default="")) -> str:
        return library_page("questions", flt=library_filters(project, status, subtype=subtype), base="/open-questions", q=q)

    @app.get("/references", response_class=HTMLResponse)
    def references_list(project: str = Query(default=""), status: str = Query(default=""),
                        subtype: str = Query(default=""), q: str = Query(default="")) -> str:
        return library_page("references", flt=library_filters(project, status, subtype=subtype), base="/references", q=q)

    @app.get("/flows", response_class=HTMLResponse)
    def flows_list(project: str = Query(default=""), status: str = Query(default=""),
                   subtype: str = Query(default=""), q: str = Query(default="")) -> str:
        return library_page("flows", flt=library_filters(project, status, subtype=subtype), base="/flows", q=q)

    @app.get("/open-questions/{question_id}", response_class=HTMLResponse)
    def open_question_view(question_id: str) -> str:
        store = Store()
        proj, oq = _find_open_question(store, question_id)
        if oq is None:
            return _layout(t("not_found"), _empty_state(t("open_questions_h"), t("runtime_maybe_cleared"), icon="help"), store, active="library")
        title = oq.get("text", "")[:110] or t("open_question_kind")
        status = oq.get("status", "open")
        status_labels = {"open": t("oq_status_open"), "resolved": t("oq_status_resolved")}
        status_label = status_labels.get(status, status)
        body = ui.section(t("open_question_kind"),
                          h("div", {"class_": "sl-prose"}, ui.clamp(oq.get("text", ""), threshold=ui.SECTION_CLAMP)),
                          id="sec-question")
        return detail_page(
            store, title=title, active="projects",
            crumbs=[(t("projects"), "/projects"), (proj["title"], f'/projects/{proj["id"]}'),
                    (t("open_question_kind"), None)],
            icon="help", kind=t("open_question_kind"),
            pills=[_label(status_label, "var(--amber)" if status == "open" else "var(--green)")],
            body=body,
            prop_rows=[("projects", t("project"), h("a", {"href": f'/projects/{proj["id"]}'}, proj["title"])),
                       ("flag", t("status_h"), status_label),
                       ("dot", t("created"), ui.fmt_date(oq.get("created_at") or ""))],
            rail_sections=[("sec-question", t("open_question_kind"))],
            star=("open_question", oq["id"], title, f'/open-questions/{oq["id"]}'))

    @app.get("/references/{reference_id}", response_class=HTMLResponse)
    def reference_view(reference_id: str) -> str:
        store = Store()
        proj, ref = _find_reference(store, reference_id)
        if ref is None:
            return _layout(t("not_found"), _empty_state(t("references_h"), t("runtime_maybe_cleared"), icon="link"), store, active="library")
        snap = ref.get("snapshot") or {}
        title = ref.get("title") or ref.get("url", "")
        kind_label = t("artifact_kind_" + (ref.get("kind") or "url"))
        headings = snap.get("headings") or []
        body = fragment(
            h("p", {},
              h("a", {"class_": "sl-btn", "href": ref.get("url", "#"), "target": "_blank", "rel": "noopener"},
                raw(_icon("external")), " ", t("open_in_new_tab"))),
            ui.section(t("reference_snapshot_h"),
                       h("div", {"class_": "sl-prose"},
                         h("p", {}, snap.get("description", "")) if snap.get("description") else None,
                         h("p", {"class_": "muted"}, " · ".join(headings[:8])) if headings else None,
                         ui.clamp(snap.get("text", "") or snap.get("error", "") or t("artifact_capture_failed"),
                                  threshold=ui.SECTION_CLAMP)),
                       id="sec-snapshot"))
        return detail_page(
            store, title=title, active="projects",
            crumbs=[(t("projects"), "/projects"), (proj["title"], f'/projects/{proj["id"]}'),
                    (t("reference_kind"), None)],
            icon="link", kind=t("reference_kind"),
            pills=[_label(kind_label, "var(--blue)"), _reference_status_pill(ref)],
            body=body,
            prop_rows=[("projects", t("project"), h("a", {"href": f'/projects/{proj["id"]}'}, proj["title"])),
                       ("tag", t("variant_label_h"), ref.get("label", "")),
                       ("link", t("url_h"), h("a", {"href": ref.get("url", "#"), "target": "_blank", "rel": "noopener"}, ref.get("url", ""))),
                       ("dot", t("created"), ui.fmt_date(ref.get("created_at") or ""))],
            rail_sections=[("sec-snapshot", t("reference_snapshot_h"))],
            star=("reference", ref["id"], title, f'/references/{ref["id"]}'))

    @app.get("/flows/{flow_id}", response_class=HTMLResponse)
    def flow_view(flow_id: str) -> str:
        store = Store()
        proj, flow = _find_flow(store, flow_id)
        if flow is None:
            return _layout(t("not_found"), _empty_state(t("flows_h"), t("runtime_maybe_cleared"), icon="compass"), store, active="library")
        sessions = services.list_usability_sessions(
            project_id=proj["id"], subject={"kind": "flow", "id": flow["id"]}, store=store)
        body = fragment(
            ui.section(t("steps_h"), _flow_steps_html(flow, proj), id="sec-steps"),
            raw(_sessions_section(store, sessions, sid="sec-replays", shots=True,
                                  heading=t("replays_h"))))
        return detail_page(
            store, title=flow["title"], active="projects",
            crumbs=[(t("projects"), "/projects"), (proj["title"], f'/projects/{proj["id"]}'),
                    (flow["title"], None)],
            icon="compass", kind=t("flow_kind"),
            body=body,
            prop_rows=[("projects", t("project"), h("a", {"href": f'/projects/{proj["id"]}'}, proj["title"])),
                       ("list", t("steps_h"), str(len(flow.get("steps") or []))),
                       ("activity", t("sessions"), str(len(sessions))),
                       ("dot", t("created"), ui.fmt_date(flow.get("created_at") or ""))],
            rail_sections=[("sec-steps", t("steps_h")), ("sec-replays", t("replays_h"))],
            star=("flow", flow["id"], flow["title"], f'/flows/{flow["id"]}'))

    @app.get("/sections/{section_id}", response_class=HTMLResponse)
    def section_view(section_id: str) -> str:
        store = Store()
        from ... import presentation as _pres
        try:
            data = services.section_members(section_id, store=store)
        except KeyError:
            return _layout(t("not_found"), _empty_state(t("section"), t("runtime_maybe_cleared"), icon="squareGrid"), store, active="projects")
        sec, proj, members = data["section"], data["project"], data["members"]
        pr = _pres.present(sec.get("kind", "theme"), sec.get("presentation"))
        chip = h("span", {"class_": "pill", "style": f'border-color:{pr["color"]};color:{pr["color"]}'},
                 ((pr.get("glyph") + " ") if pr.get("glyph") else ""), pr.get("short", sec.get("kind", "")))
        rows = []
        for m in members:
            head = h("a", {"href": m["href"]}, m["title"]) if m["href"] else m["title"]
            rows.append(h("div", {"class_": "strow"}, h("b", {}, head), " ", h("span", {"class_": "muted small"}, m["kind"]),
                          h("div", {"class_": "muted small", "style": "margin-top:3px"}, (m["summary"] or "")[:240])))
        note_sub = h("p", {"class_": "sub"}, sec.get("note", "")) if sec.get("note") else ""
        sec_sub = fragment(chip, " ", h("span", {"class_": "muted small"}, t("n_nodes", n=len(members))))
        body = fragment(note_sub, h("div", {"style": "margin-top:8px"},
                        fragment(*rows) if rows else raw(_empty_state(t("section"), t("no_members"), icon="squareGrid"))))
        return detail_page(
            store, title=sec["title"], active="projects",
            crumbs=[(t("projects"), "/projects"), (proj["title"], f'/projects/{proj["id"]}'), (sec["title"], None)],
            icon="squareGrid", kind=t("section"), sub=sec_sub, body=body,
            prop_rows=[("dot", t("type_h"), pr.get("short", sec.get("kind", ""))),
                       ("projects", t("project"), h("a", {"href": f'/projects/{proj["id"]}'}, proj["title"]))],
            star=("section", sec["id"], sec["title"], f'/sections/{sec["id"]}'),
            # V10: the "…" overflow — edit as a dialog over this page + the confirm delete
            actions=section_actions(sec))

    @app.get("/notes/{note_id}", response_class=HTMLResponse)
    def note_view(note_id: str) -> str:
        store = Store()
        try:
            data = services.get_note(note_id, store=store)
        except KeyError:
            return _layout(t("not_found"), _empty_state(t("not_found"), t("runtime_maybe_cleared"), icon="panel"), store, active="projects")
        note, proj = data["note"], data["project"]
        klabel = t("notes_h")                                          # ONE note entity (concepts merged in)
        ntitle = note.get("title") or klabel
        from ... import presentation as _pres
        # the eyebrow presents the note's OWN kind tag through the data vocabulary (a concept
        # note says "concept"; the section-kind label gate bans hardcoding these in web/)
        nkind = _pres.present(note.get("kind") or "note")["label"]
        return detail_page(
            store, title=ntitle, active="projects",   # G5: notes are project-rooted
            crumbs=[(t("projects"), "/projects"), (proj["title"], f'/projects/{proj["id"]}'), (ntitle, None)],
            icon="panel", kind=nkind, hid="sec-content",
            body=h("div", {"class_": "sl-prose", "style": "margin-top:4px"}, raw(_md(note.get("text", "")))),
            # Rail order is the §8.2 anatomy: project → dates.
            prop_rows=[("projects", t("project"), h("a", {"href": f'/projects/{proj["id"]}'}, proj["title"])),
                       ("dot", t("created"), ui.fmt_date(note.get("created_at", "")))],
            rel_study_id=f"note:{note_id}", rel_proj_id=proj["id"],
            rail_sections=[("sec-content", klabel)],
            star=("note", note_id, ntitle, f'/notes/{note_id}'),
            # V10: the "…" overflow — edit as a dialog over this page + the confirm delete
            actions=note_actions(note))

    @app.get("/prototypes/{slug}", response_class=HTMLResponse)
    def prototype_view(slug: str) -> str:
        store = Store()
        try:
            p = services.get_prototype_artifact(slug, store=store)
        except Exception:
            return _layout(t("not_found"), _empty_state(t("prototypes_h"), t("runtime_maybe_cleared"), icon="prototype"), store, active="projects")
        # The route accepts slug OR id (⌘K and ref chips link by id) — every file URL and
        # sibling route below must use the CANONICAL slug, or the iframe/raw links 404.
        slug = p.get("slug") or slug
        crumbs = [(t("projects"), "/projects")]
        proj = store.get_research_project(p["project_id"]) if p.get("project_id") else None
        if proj:
            crumbs.append((proj["title"], f"/projects/{proj['id']}"))
        crumbs.append((p["name"], None))
        _ap = _artifact_present(p)
        fid = h("span", {"class_": "pill"}, _ap["disc"] or _ap["label"])
        src = f'/proto-files/{slug}/{p.get("entry", "index.html")}'
        # Recorded prototype reactions are first-class sessions now (UX U7, §8.2): each renders
        # as ONE session row (the §3.2 vocabulary) deep-linking into its /sessions/{id} detail
        # page — verdict, timeline, screenshots and predicted behaviors live THERE, the
        # prototype page stays the structural index.
        from .sessions import LIGHTBOX_JS, proto_session_vm, session_shot_strip
        sessions = store.list_prototype_sessions(prototype_id=p["id"])
        if sessions:
            # each session row carries its first/last step-shot strip (ux-contract §9 V4) —
            # the walk is visible at a glance, the lightbox/replay one click away
            sessions_html = fragment(*(
                fragment(ui.primitive_row("session", proto_session_vm(s, store), store,
                                          href=f'/sessions/{s["id"]}', drawer=True),
                         raw(session_shot_strip(s)))
                for s in sessions))
        else:
            sessions_html = h("div", {"class_": "muted small"}, f'— {t("no_sessions")} —')
        # Replayable usability sessions of THIS prototype (subject.id is the prototype id or slug) —
        # each row deep-links into the session replay view (and carries its shot strip, V4).
        useen, usess = set(), []
        for key in (p["id"], p.get("slug")):
            for s in (services.list_usability_sessions(subject=key, store=store) if key else []):
                if s["id"] not in useen:
                    useen.add(s["id"]); usess.append(s)
        # G1: plain, distinct section names — replayable walks are "Replays", the recorded
        # reaction sessions below are "Prototype sessions" (never "Prototypes · Sessions").
        replay_html = _sessions_section(store, usess, sid="sec-replays", shots=True,
                                        heading=t("replays_h"))
        body = fragment(
            h("p", {"style": "margin:8px 0 16px"},
              h("a", {"class_": "sl-btn", "href": src, "target": "_blank"},
                raw(_icon("projects")), " ", t("open_in_new_tab"), " ", raw(_icon("external")))),
            h("div", {"class_": "protoframe"}, h("iframe", {"src": src, "title": p["name"], "loading": "lazy"})),
            raw(replay_html),
            h("div", {"class_": "sec", "id": "sec-sessions", "style": "margin-top:22px"},
              h("h2", {}, f'{t("proto_sessions_h")} ({len(sessions)})'),
              h("div", {"style": "margin-top:8px"}, sessions_html)),
            raw(LIGHTBOX_JS))
        concept_in = []
        if proj:                                              # the concept that realises this prototype
            try:
                g = services.get_project_graph(p["project_id"], store=store)
                concept_in = [n for n in g["nodes"] if p["id"] in (n.get("prototype_ids") or [])]
            except Exception:
                concept_in = []
        n_grounded = sum(1 for s in sessions if s.get("grounded_verified"))
        proj_link = (h("a", {"href": f'/projects/{proj["id"]}'}, proj["title"]) if proj else "—")
        # Detail-header attribution (ux-contract §10 W11): the personas who drove this
        # prototype's sessions — BOTH kinds (reactions + usability walks) — as the one
        # avatar-group anatomy, leading the meta line.
        driver_pids = [pid for pid in dict.fromkeys(
            [s.get("persona_id", "") for s in sessions] + [s.get("persona_id", "") for s in usess]) if pid]
        crew = ui.avatar_group((store.get_persona(pid) for pid in driver_pids[:4]),
                               total=len(driver_pids), size=22)
        sub = (h("span", {"class_": "syn-meta"}, crew,
                 h("span", {"class_": "muted"}, p.get("version", "")) if p.get("version") else None)
               if crew else p.get("version", ""))
        return detail_page(
            store, title=p["name"], crumbs=crumbs,
            # G5: sidebar active follows the crumb root (project-rooted → Projects)
            active="projects" if proj else "library",
            # meta line: drivers + the version only — the slug is an address, not information
            # (V12: no terminal-flavored identifiers in UI copy; the URL bar already shows it)
            hero=_hero(p["name"], icon="prototype", sub=sub,
                       top=detail_eyebrow(t("prototype_kind"), [fid])),
            body=body,
            # Rail order is the §8.2 anatomy: project → kind-specifics → dates; the grounded
            # tally rides the static "Grounding" label (the session-rail convention).
            prop_rows=[("projects", t("project"), proj_link),
                       ("square", t("fidelity"), _ap.get("disc") or _ap.get("label") or ""),
                       ("personas", t("sessions"), str(len(sessions))),
                       ("check", t("grounding_h"), f"{n_grounded}/{len(sessions)}" if sessions else "—"),
                       ("dot", t("created"), ui.fmt_date(p.get("created_at") or ""))],
            rel_study_id=f"prototype:{p['id']}", rel_proj_id=p.get("project_id"), rel_extra_in=concept_in,
            rail_sections=(([("sec-replays", t("replays_h"))] if replay_html else [])
                           + [("sec-sessions", t("proto_sessions_h"))]),
            star=("prototype", p["id"], p["name"], f'/prototypes/{slug}'),
            # delete-only (no content editing): prototypes are recorded artifacts — the
            # subtle header overflow (U9 §8.4), never a danger zone
            actions=overflow_delete(f'/prototypes/{slug}/delete', t("delete_prototype")))


register_css(
    ".libnav{display:flex;align-items:center;gap:6px;flex-wrap:wrap}"
    ".libnav--family{margin:0 0 8px;padding:4px;background:var(--panel-2);"
    "border:1px solid var(--line);border-radius:8px;width:max-content;max-width:100%}"
    ".libnav-family{display:inline-flex;align-items:center;gap:7px;padding:6px 10px;"
    "border-radius:6px;color:var(--muted);font-size:var(--t-sm);font-weight:600;"
    "text-decoration:none;white-space:nowrap}"
    ".libnav-family svg{width:15px;height:15px;color:var(--faint)}"
    ".libnav-family.is-active{background:var(--panel);color:var(--ink);box-shadow:0 0 0 1px var(--line)}"
    ".libnav-family.is-active svg{color:var(--accent)}"
    ".libnav--kind{margin:0 0 6px;border-bottom:1px solid var(--line)}"
    ".libnav-kind{display:inline-flex;align-items:center;gap:6px;padding:8px 2px 9px;"
    "margin-right:22px;color:var(--muted);font-size:var(--t-sm);font-weight:650;"
    "text-decoration:none;border-bottom:2px solid transparent;white-space:nowrap}"
    ".libnav-kind svg{width:15px;height:15px;color:var(--faint)}"
    ".libnav-kind.is-active{color:var(--accent);border-bottom-color:var(--accent)}"
    ".libnav-kind.is-active svg{color:var(--accent)}"
    ".taxctx{display:flex;align-items:center;gap:7px;margin:10px 0 0;color:var(--muted);"
    "font-size:var(--t-sm);line-height:1.45;flex-wrap:wrap}"
    ".taxctx__eyebrow{font-size:var(--t-xs);text-transform:uppercase;letter-spacing:.06em;"
    "color:var(--faint);font-weight:650}"
    ".taxctx__family{color:var(--ink);font-weight:650}"
    ".taxctx__dot{color:var(--faint)}"
    ".taxctx__purpose{max-width:78ch}"
)
