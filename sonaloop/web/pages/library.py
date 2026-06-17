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

from collections import Counter

from ._ctx import *  # noqa: F401,F403  (shared render toolkit)
from .sessions import _sessions_section
from .. import ui
from .._html import register_css
from .._filterbar import filter_bar, filter_url, parse_multi
from .._forms import overflow_delete
from .edit import note_actions, section_actions
from .._presence import asset_direction, record_status, status_filter_label
from .._primitive_taxonomy import (
    FAMILIES, family_icon, family_label, primitive_family, primitive_purpose, primitive_subtypes,
    form_label, prototype_fidelity_value, subtype_label, subtype_value,
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
    project_rows = store.list_research_projects()
    projects = {p["id"]: p["title"] for p in project_rows}
    study_projects = {sid: p["id"] for p in project_rows for sid in (p.get("study_ids") or [])}
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
        return [e("synthesis", s, f'/syntheses/{s["id"]}', project_id=study_projects.get(s["id"], ""))
                for s in store.list_syntheses()]
    if key == "prototypes":
        # the W11 crew enrichment (n_sessions BOTH kinds + the drivers' personas/voices) —
        # the same services read the outline rows use, so the avatars never diverge
        return [e("prototype", {**p, **services.prototype_participation(p, store)},
                  f'/prototypes/{p["slug"]}')
                for p in store.list_prototypes()]
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


def _entry_trace_keys(x: dict) -> set[str]:
    rec = x.get("rec") or {}
    kind = str(x.get("kind") or "")
    rid = str(rec.get("id") or "")
    if not kind or not rid:
        return set()
    keys = {rid, f"{kind}:{rid}"}
    if kind == ("synth" + "esis"):
        keys.update((f"report:{rid}",))
    if kind == "url_artifact":
        keys.update((f"artifact:{rid}",))
    return keys


def _library_trace_lookup(store: Store, project_ids: set[str]) -> dict[str, dict[str, str]]:
    """Project outline trace states, keyed for Library rows.

    The Library is cross-project, but trace is project-local. Compute it from the same
    augmented graph the project outline/detail pages use, then only project it onto the flat
    Library rows. This keeps the Library from inventing a second relationship model.
    """
    if not project_ids:
        return {}
    from .._graph_outline_sessions import outline_session_groups
    from .._project_graph_view import augment_project_graph
    from ...project_trace import trace_node_health

    out: dict[str, dict[str, str]] = {}
    for pid in project_ids:
        try:
            graph = services.get_project_graph(pid, store=store)
        except KeyError:
            # Rows recorded before project deletion cascaded can still carry a
            # now-missing project_id. Keep the global Library browsable and skip
            # project-local trace annotation for those orphan rows.
            continue
        proto_ids = {p.get("id") for p in graph.get("prototypes") or []}
        prototype_sessions = [
            s for s in store.list_prototype_sessions()
            if s.get("prototype_id") in proto_ids
        ]
        sessions = outline_session_groups(
            services.list_usability_sessions(project_id=pid, store=store),
            store, prototype_sessions=prototype_sessions,
        )
        full_graph = augment_project_graph(
            graph, sessions=sessions,
            decisions=services.list_decisions(pid, store=store),
            hypotheses=services.list_hypotheses(pid, store=store),
            surveys=services.list_surveys(project_id=pid, store=store),
            assets=services.list_assets(pid, store=store),
        )
        health = trace_node_health(full_graph["nodes"], full_graph["edges"], graph.get("plan"))
        by_key: dict[str, str] = {}
        for node in full_graph["nodes"]:
            sid = str(node.get("study_id") or "")
            if not sid:
                continue
            state = health.get(sid, "")
            if not state:
                continue
            by_key[sid] = state
            kind, rid = sid.split(":", 1) if ":" in sid else ("", sid)
            by_key.setdefault(rid, state)
            if kind == "report":
                by_key.setdefault(f"synthesis:{rid}", state)
            if kind == "url_artifact":
                by_key.setdefault(f"artifact:{rid}", state)
        out[pid] = by_key
    return out


def _annotate_library_trace(entries: list[dict], store: Store) -> list[dict]:
    lookup = _library_trace_lookup(store, {x["project_id"] for x in entries if x.get("project_id")})
    out = []
    for x in entries:
        state = next((lookup.get(x.get("project_id", ""), {}).get(k)
                      for k in _entry_trace_keys(x)
                      if lookup.get(x.get("project_id", ""), {}).get(k)), "")
        if not state:
            out.append(x)
            continue
        rec = {**(x.get("rec") or {}), "trace_health": state}
        out.append({**x, "rec": rec, "trace_health": state})
    return out


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


def _reference_status_pill(ref: dict) -> str:
    snap = ref.get("snapshot") or {}
    if snap.get("ok"):
        return _label(t("artifact_captured"), "var(--green)")
    return _label(t("artifact_capture_failed"), "var(--muted)")


def _trace_filter_label(state: str) -> str:
    labels = {
        "source": t("trace_source"),
        "active": t("trace_active"),
        "consumed": t("trace_consumed"),
        "terminal": t("trace_terminal"),
        "parked": t("trace_parked"),
        "orphaned": t("trace_orphaned"),
    }
    return labels.get(state, state)


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
    trace_n: Counter = Counter()
    trace_lbl: dict[str, str] = {}
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
        tr = str(x.get("trace_health") or "")
        if tr:
            trace_n[tr] += 1
            trace_lbl.setdefault(tr, _trace_filter_label(tr))
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
        {"key": "trace", "label": t("trace_h"), "icon": "link",
         "options": [{"value": s, "label": trace_lbl[s], "count": n}
                     for s, n in trace_n.most_common()]},
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


def _taxo_level_label(value_en: str, value_de: str) -> str:
    return value_de if _lang() == "de" else value_en


def _form_taxonomy_items(tab: str, kind: str, base: str, entries: list[dict],
                         selected: dict[str, list[str]]) -> str:
    """Visible form chips for the active primitive.

    Forms are part of the operative browser model, not a separate explainer:
    Family -> Primitive -> Form -> Records. Counts are over the tab's honest
    unfiltered records, matching the FilterBar's count semantics.
    """
    docs = primitive_subtypes(kind)
    if not docs:
        return ""
    de = _lang() == "de"
    all_label = "Alle" if de else "All"
    active_values = set(selected.get("subtype") or [])
    without_subtype = {k: v for k, v in selected.items() if k != "subtype" and v}
    counts = Counter(subtype_value(x["kind"], x["rec"]) for x in entries)
    total = len(entries)
    chips = [
        h("a", {"class_": "sl-taxo-pill sl-is-active" if not active_values else "sl-taxo-pill",
                "href": filter_url(base, without_subtype),
                "aria-current": "page" if not active_values else None},
          h("span", {"class_": "sl-taxo-pill__label"}, all_label),
          h("span", {"class_": "sl-taxo-pill__count"}, str(total)))
    ]
    for d in docs:
        count = counts.get(d.value, 0)
        on = d.value in active_values
        cls = "sl-taxo-pill"
        if on:
            cls += " sl-is-active"
        if count == 0 and not on:
            cls += " sl-is-disabled"
        attrs = {"class_": cls, "data-value": d.value, "aria-current": "page" if on else None}
        content = fragment(h("span", {"class_": "sl-taxo-pill__label"}, subtype_label(d.value)),
                           h("span", {"class_": "sl-taxo-pill__count"}, str(count)))
        if count == 0 and not on:
            chips.append(h("span", attrs, content))
        else:
            next_selected = {**without_subtype, "subtype": [d.value]}
            chips.append(h("a", {**attrs, "href": filter_url(base, next_selected)}, content))
    return h("div", {"class_": "sl-taxo-items", "data-tab": tab}, fragment(*chips))


def _library_tab_counts(active_tab: str, active_entries: list[dict], store: Store) -> dict[str, int]:
    counts: dict[str, int] = {}
    for key, *_ in LIBRARY_TABS:
        counts[key] = len(active_entries) if key == active_tab else len(_tab_entries(key, store))
    return counts


def _library_nav(active_tab: str, counts: dict[str, int], form_items: str,
                 selected: dict[str, list[str]] | None = None) -> str:
    """Two-level Library navigation: users first choose the role a primitive plays, then the
    specific primitive inside that role. This keeps the mental model visible instead of showing
    twelve peer tabs that look like implementation details."""
    rows = list(LIBRARY_TABS)
    active_kind = TAB_KIND.get(active_tab, "open_question")
    active_family = primitive_family(active_kind)
    buckets: dict[str, list[tuple]] = {fam: [] for fam, _label, _icon in FAMILIES}
    for row in rows:
        k = row[0]
        fam = primitive_family(TAB_KIND.get(k, "note"))
        buckets.setdefault(fam, []).append(row)
    families = [(fam, buckets[fam]) for fam, _label, _icon in FAMILIES if buckets.get(fam)]
    primary = []
    for fam, items in families:
        first = items[0]
        route = first[1]
        on = fam == active_family
        primary.append(h("a", {"class_": "sl-taxo-pill sl-taxo-pill--family sl-is-active" if on
                               else "sl-taxo-pill sl-taxo-pill--family",
                               "href": route, "aria-current": "page" if on else None},
                         raw(_icon(family_icon(fam))),
                         h("span", {"class_": "sl-taxo-pill__label"}, family_label(fam))))
    primitive_tabs = []
    for row in next(items for fam, items in families if fam == active_family):
        key, route, icon, label, *_ = row
        on = key == active_tab
        primitive_tabs.append(
            h("a", {"class_": "sl-taxo-pill sl-taxo-pill--primitive sl-is-active" if on
                    else "sl-taxo-pill sl-taxo-pill--primitive",
                    "href": route, "aria-current": "page" if on else None},
              raw(_icon(icon)),
              h("span", {"class_": "sl-taxo-pill__label"}, label()),
              h("span", {"class_": "sl-taxo-pill__count"}, str(counts.get(key, 0)))))
    return h("section", {"class_": "sl-taxonomy"},
             h("div", {"class_": "sl-taxo-row"},
               h("div", {"class_": "sl-taxo-label"}, _taxo_level_label("Family", "Familie")),
               h("div", {"class_": "sl-taxo-items"}, fragment(*primary))),
             h("div", {"class_": "sl-taxo-row"},
               h("div", {"class_": "sl-taxo-label"}, _taxo_level_label("Primitive", "Primitive")),
               h("div", {"class_": "sl-taxo-field"},
                 h("div", {"class_": "sl-taxo-items"}, fragment(*primitive_tabs)),
                 h("div", {"class_": "sl-taxo-hint"}, primitive_purpose(active_kind)))),
             h("div", {"class_": "sl-taxo-row"},
               h("div", {"class_": "sl-taxo-label"}, _taxo_level_label("Form", "Form")),
               raw(form_items)))


def _first_tab_for_family(family: str) -> str:
    if not family:
        return ""
    for key, *_ in LIBRARY_TABS:
        if primitive_family(TAB_KIND.get(key, "note")) == family:
            return key
    return ""


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
    _k, _route, icon, tab_label, empty_msg, _lead, teach = next(
        row for row in LIBRARY_TABS if row[0] == tab)
    tab_kind = TAB_KIND.get(tab, "note")
    base0 = base or f"/library?tab={tab}"
    base = base0 + (("&" if "?" in base0 else "?") + f"q={quote(q)}" if q else "")
    selected = {k: v for k, v in (flt or {}).items()}
    raw_entries = _tab_entries(tab, store, sessions=sessions)
    entries = _annotate_library_trace(raw_entries, store)
    facets = _library_facets(entries, store, with_direction=tab == "assets")
    form_items = _form_taxonomy_items(tab, tab_kind, base, entries, selected)
    tabs_html = _library_nav(tab, _library_tab_counts(tab, raw_entries, store), form_items, selected)
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
            if active.get("trace") and x.get("trace_health") not in active["trace"]:
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
        return _list_page(store, title=t("library_h"), lead=t("library_lead"), rows=[],
                          empty_icon="filter", empty_msg=t("filter_no_matches_h"),
                          empty_teach=t("filter_no_matches"),
                          empty_action=(t("clear_filter"), base0, "filter"),
                          active="library",
                          pre=(str(tabs_html) + bar + pre_extra),
                          count=0)
    return _list_page(store, title=t("library_h"), lead=t("library_lead"), rows=rows,
                      empty_icon=icon, empty_msg=empty_msg(), empty_teach=teach(),
                      active="library",
                      pre=(str(tabs_html) + bar + pre_extra),
                      count=len(rows))


def library_filters(project: str = "", status: str = "", direction: str = "",
                    subtype: str = "", trace: str = "") -> dict:
    """Parse the shared Library filter params (?project=…&status=…&direction=… — comma = OR)
    into the `flt` dict library_page applies; the canonical tab routes all funnel through
    this so the URL grammar stays identical everywhere."""
    return {"project": parse_multi(project), "status": parse_multi(status),
            "direction": parse_multi(direction), "subtype": parse_multi(subtype),
            "trace": parse_multi(trace)}


def register_library(app) -> None:
    @app.get("/library", response_class=HTMLResponse)
    def library(tab: str = Query(default="questions"), project: str = Query(default=""),
                status: str = Query(default=""), direction: str = Query(default=""),
                subtype: str = Query(default=""), trace: str = Query(default=""),
                family: str = Query(default=""),
                q: str = Query(default="")) -> str:
        tab = _first_tab_for_family(family) or tab
        return library_page(tab, flt=library_filters(project, status, direction, subtype, trace), q=q)

    @app.get("/open-questions", response_class=HTMLResponse)
    def open_questions_list(project: str = Query(default=""), status: str = Query(default=""),
                            subtype: str = Query(default=""), trace: str = Query(default=""),
                            q: str = Query(default="")) -> str:
        return library_page("questions", flt=library_filters(project, status, subtype=subtype, trace=trace), base="/open-questions", q=q)

    @app.get("/references", response_class=HTMLResponse)
    def references_list(project: str = Query(default=""), status: str = Query(default=""),
                        subtype: str = Query(default=""), trace: str = Query(default=""),
                        q: str = Query(default="")) -> str:
        return library_page("references", flt=library_filters(project, status, subtype=subtype, trace=trace), base="/references", q=q)

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
                       *detail_form_rows("open_question", oq),
                       ("flag", t("status_h"), status_label),
                       ("dot", t("created"), ui.fmt_date(oq.get("created_at") or ""))],
            rel_study_id=f"open_question:{oq['id']}", rel_proj_id=proj["id"],
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
                       *detail_form_rows("url_artifact", ref),
                       ("tag", t("variant_label_h"), ref.get("label", "")),
                       ("link", t("url_h"), h("a", {"href": ref.get("url", "#"), "target": "_blank", "rel": "noopener"}, ref.get("url", ""))),
                       ("dot", t("created"), ui.fmt_date(ref.get("created_at") or ""))],
            rel_study_id=f"url_artifact:{ref['id']}", rel_proj_id=proj["id"],
            rail_sections=[("sec-snapshot", t("reference_snapshot_h"))],
            star=("reference", ref["id"], title, f'/references/{ref["id"]}'))

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
                          h("div", {"class_": "muted small sl-note-summary"}, (m["summary"] or "")[:240])))
        note_sub = h("p", {"class_": "sub"}, sec.get("note", "")) if sec.get("note") else ""
        sec_sub = fragment(chip, " ", h("span", {"class_": "muted small"}, t("n_nodes", n=len(members))))
        body = fragment(note_sub, h("div", {"style": "margin-top:8px"},
                        fragment(*rows) if rows else raw(_empty_state(t("section"), t("no_members"), icon="squareGrid"))))
        return detail_page(
            store, title=sec["title"], active="projects",
            crumbs=[(t("projects"), "/projects"), (proj["title"], f'/projects/{proj["id"]}'), (sec["title"], None)],
            icon="squareGrid", kind=t("section"), sub=sec_sub, body=body,
            prop_rows=[*detail_form_rows("section", sec),
                       ("dot", t("type_h"), pr.get("short", sec.get("kind", ""))),
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
                       *detail_form_rows("note", note),
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
        fid = h("span", {"class_": "pill"}, form_label("prototype", p) or _ap["label"])
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
                       *detail_form_rows("prototype", p),
                       ("square", t("fidelity"), prototype_fidelity_value(p)),
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
    ".sl-taxonomy{display:grid;gap:8px;margin:0 0 14px;padding:10px 12px;border:1px solid var(--line);"
    "border-radius:9px;background:color-mix(in srgb,var(--panel) 82%,var(--bg));max-width:100%}"
    ".sl-taxo-row{display:grid;grid-template-columns:78px minmax(0,1fr);align-items:start;gap:10px}"
    ".sl-taxo-label{padding-top:6px;color:var(--faint);font-size:var(--t-xs);font-weight:750;"
    "text-transform:uppercase;letter-spacing:.08em}"
    ".sl-taxo-field{display:grid;gap:4px;min-width:0}"
    ".sl-taxo-items{display:flex;align-items:center;gap:6px;flex-wrap:wrap;min-width:0}"
    ".sl-taxo-hint{color:var(--muted);font-size:var(--t-sm);line-height:1.35;"
    "white-space:nowrap;overflow:hidden;text-overflow:ellipsis}"
    ".sl-taxo-pill{display:inline-flex;align-items:center;gap:7px;height:30px;padding:0 10px;"
    "border:1px solid transparent;border-radius:7px;background:transparent;color:var(--muted);"
    "font-size:var(--t-sm);font-weight:650;text-decoration:none;white-space:nowrap}"
    ".sl-taxo-pill svg{width:15px;height:15px;color:var(--faint)}"
    ".sl-taxo-pill:hover{background:var(--panel-2);border-color:var(--line);color:var(--ink)}"
    ".sl-taxo-pill.sl-is-active{background:var(--panel);border-color:var(--line);color:var(--ink);"
    "box-shadow:0 1px 1px color-mix(in srgb,var(--ink) 4%,transparent)}"
    ".sl-taxo-pill.sl-is-active svg{color:var(--accent)}"
    ".sl-taxo-pill.sl-is-disabled{color:var(--faint);background:transparent}"
    ".sl-taxo-pill__count{color:var(--faint);font-weight:750}"
    ".sl-taxo-pill.sl-is-active .sl-taxo-pill__count{color:var(--accent)}"
    ".sl-taxonomy~.rows{border-top:0}"
    ".sl-note-summary{margin-top:3px}"
    "@media(max-width:760px){.sl-taxo-row{grid-template-columns:1fr}.sl-taxo-label{padding-top:0}"
    ".sl-taxo-hint{white-space:normal}}"
)
