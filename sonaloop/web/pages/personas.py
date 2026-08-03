"""Persona pages: list, detail, memory, activity (spec/roadmap.md R2)."""
from __future__ import annotations

from urllib.parse import quote

from fastapi import Request
from fastapi.responses import Response

from ._ctx import *  # noqa: F401,F403  (shared render toolkit)
from ._calendar import _calendar_tabs, _period_calendar_html
from .sessions import _sessions_section
from .._render import render_findings
from .._html import register_css
from .._keymap import sibling_attrs, sibling_urls
from ... import artifacts as _artifacts

# Memory panel — a temporal knowledge graph (entities + fact timelines, superseded facts struck).
register_css(r"""
.mem-bar{display:flex;gap:10px;flex-wrap:wrap;margin:0 0 22px}
.mem-tool{display:flex;align-items:center;gap:8px;border:1px solid var(--line);border-radius:var(--radius);padding:6px 10px;background:var(--panel)}
.mem-tool svg{width:15px;height:15px;color:var(--muted);flex:none}
.mem-tool input{border:0;background:transparent;padding:2px 0;font-size:var(--t-body);color:var(--ink)}
.mem-tool input:focus{outline:none}.mem-tool input[type=text]{min-width:236px}
.mem-group{margin:0 0 22px}
.mem-group-h{display:flex;align-items:center;gap:7px;font-size:var(--t-xs);text-transform:uppercase;letter-spacing:.05em;color:var(--muted);font-weight:600;margin:0 0 10px}
.mem-n{color:var(--faint);font-weight:550}
.mem-ents{display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:12px}
.mem-ent{border:1px solid var(--line);border-radius:var(--radius);background:var(--panel);padding:13px 15px}
.mem-ent-h{display:flex;align-items:center;gap:8px;margin:0 0 11px}
.mem-ent-h svg{width:15px;height:15px;color:var(--muted);flex:none}.mem-ent-h b{font-size:var(--t-body)}
.mem-status{margin-left:auto;font-size:var(--t-xs);color:var(--accent);background:var(--accent-weak);border-radius:var(--radius-full);padding:1px 9px;font-weight:500;white-space:nowrap}
.mem-tl{display:flex;flex-direction:column;gap:8px;position:relative;padding-left:15px}
.mem-tl::before{content:"";position:absolute;left:3px;top:5px;bottom:5px;border-left:1.5px solid var(--line-2)}
.mem-fact{display:flex;gap:9px;font-size:var(--t-sm);position:relative}
.mem-fact::before{content:"";position:absolute;left:-15px;top:5px;width:7px;height:7px;border-radius:50%;background:var(--accent);box-shadow:0 0 0 2px var(--panel)}
.mem-fact.sup::before{background:var(--line-2)}
.mem-date{flex:none;color:var(--muted);font-variant-numeric:tabular-nums;min-width:74px}
.mem-fx{color:var(--ink)}
.mem-fact.sup .mem-fx{color:var(--faint);text-decoration:line-through;text-decoration-color:var(--line-2)}
.mem-loops{border:1px solid var(--line);border-radius:var(--radius);background:var(--panel)}
.mem-loop{display:flex;align-items:center;gap:9px;padding:9px 13px;font-size:var(--t-body)}
.mem-loop+.mem-loop{border-top:1px solid var(--line)}
.mem-loop-dot{flex:none;width:6px;height:6px;border-radius:50%;background:var(--amber)}
.mem-pane{border:1px solid var(--line);border-radius:var(--radius);background:var(--panel-2);padding:12px 15px;margin:0 0 16px}
.mem-pane-h{font-size:var(--t-xs);text-transform:uppercase;letter-spacing:.05em;color:var(--muted);font-weight:600;margin:0 0 8px}
.mem-hit{padding:7px 0;font-size:var(--t-sm)}.mem-hit+.mem-hit{border-top:1px solid var(--line-2)}
.cap-row{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin:0 0 10px}
.sl-catalog-note{border:1px solid var(--line);border-radius:var(--radius);background:var(--panel-2);padding:9px 12px;margin:0 0 12px;color:var(--muted);font-size:var(--t-sm)}
.sl-catalog-form{margin-left:auto;display:flex;align-items:center;gap:6px;flex-shrink:0}
.sl-catalog-form .sl-btn{white-space:nowrap}
.sl-catalog-row-title{display:flex;align-items:center;gap:8px;min-width:0}
.sl-catalog-row-title .sl-catalog-slug{font-weight:400;color:var(--faint);font-size:var(--t-xs)}
.sl-catalog-avatar{width:28px;height:28px;border-radius:50%;object-fit:cover;background:var(--panel-2);border:1px solid var(--line-2);flex-shrink:0}
.sl-catalog-facets{display:flex;flex-direction:column;gap:9px;margin:0 0 14px}
.sl-catalog-facet{display:flex;align-items:center;gap:7px;flex-wrap:wrap}
.sl-catalog-facet__label{min-width:118px;color:var(--muted);font-size:var(--t-xs);font-weight:650;text-transform:uppercase;letter-spacing:.05em}
.sl-catalog-chip{display:inline-flex;align-items:center;gap:5px;border:1px solid var(--line);border-radius:var(--radius-full);padding:3px 9px;color:var(--muted);font-size:var(--t-xs);text-decoration:none;background:var(--panel)}
.sl-catalog-chip:hover{background:var(--hover);color:var(--ink)}
.sl-catalog-chip.is-active{border-color:var(--accent);color:var(--accent);background:var(--accent-weak)}
.sl-catalog-chip__count{color:var(--faint);font-variant-numeric:tabular-nums}
""")


_MEM_KINDS = [("project", "briefcase"), ("person", "contact"), ("topic", "tag"), ("tool", "settings")]
_CATALOG_FACETS = ("tier", "lebensphase", "einstellung", "role_family", "seniority",
                   "decision_power", "age_band", "region", "has_avatar")
_CATALOG_FACET_LABELS = {
    "tier": "Access", "lebensphase": "Life phase", "einstellung": "Attitude",
    "role_family": "Role family", "seniority": "Seniority",
    "decision_power": "Decision power", "age_band": "Age band",
    "region": "Region", "has_avatar": "Avatar",
}
_CATALOG_VALUE_LABELS = {
    "tier": {"free": "Free", "premium": "Premium"},
    "has_avatar": {"yes": "Avatar", "no": "No avatar"},
}


def _cap_provenance_label(prov: str) -> str:                # explicit t() calls so the i18n usage scan sees them
    return {"derived": t("cap_derived"), "authored": t("cap_authored"),
            "evidence": t("cap_evidence")}.get(prov, prov)


def _capabilities_html(caps: dict) -> str:
    """The capability profile card: rung badges (which session fidelities are on/off), the
    tech-comfort chip (data-driven label/color/hint via tech_comfort.json), devices, accessibility
    notes — with the derived-vs-authored provenance marked."""
    rungs = caps.get("rungs") or {}
    rung_labels = [("see", t("cap_rung_see")), ("walk", t("cap_rung_walk")),
                   ("drive", t("cap_rung_drive")), ("login", t("cap_rung_login"))]
    badges = [raw(_label(lbl, "var(--green)" if rungs.get(k) else "var(--muted)",
                         "soft" if rungs.get(k) else "outline", title=f"rungs.{k}"))
              for k, lbl in rung_labels]
    meta = _artifacts.tech_comfort_meta(caps.get("tech_comfort"))
    chip = raw(_label(f'{t("cap_tech_comfort")}: {t(meta["label_key"])} · {caps.get("tech_comfort", "—")}/5',
                      meta["color"], title=meta["hint"]))
    prov = h("span", {"class_": "muted small"}, _cap_provenance_label(caps.get("provenance") or ""))
    return h("div", {"class_": "sec", "id": "caps"},
             h("h2", {}, t("capabilities_h")),
             h("div", {"class_": "cap-row"}, fragment(*badges), chip, prov),
             h("p", {"class_": "muted small"},
               f'{t("cap_devices")}: {", ".join(caps.get("devices") or []) or "—"}'),
             (h("p", {}, h("strong", {}, t("cap_accessibility")), ": ", caps["accessibility"])
              if caps.get("accessibility") else None))


def _mem_kind_label(kind: str) -> str:                      # explicit t() calls so the i18n usage scan sees them
    return {"project": t("active_projects"), "person": t("mem_people"),
            "topic": t("mem_topics"), "tool": t("mem_tools")}.get(kind, kind)


def _memory_html(store: Store, persona_id: str, as_of: str | None, q: str | None) -> str:
    p = store.get_persona(persona_id)
    if not p:
        return _empty_state(t("profile_not_found"), t("runtime_maybe_cleared"), icon="memory")
    pid = p["id"]
    sup_label = _label(t("outdated"), "var(--muted)", "outline", False)        # superseded fact tag

    # --- the knowledge graph: entities grouped by kind, each a timeline of facts (newest first;
    #     superseded facts dimmed + struck so the persona's belief CHANGES read at a glance) ---
    by_kind: dict[str, list] = {}
    for e in store.list_entities(pid):
        by_kind.setdefault(e.get("kind", ""), []).append(e)

    def _ent_card(e: dict, icon: str) -> str:
        facts = sorted(store.list_entity_facts(e["id"]), key=lambda f: f.get("t_valid", ""), reverse=True)
        rows = []
        for f in facts:
            sup = bool(f.get("t_invalid"))
            rows.append(h("div", {"class_": "mem-fact" + (" sup" if sup else "")},
                          h("span", {"class_": "mem-date"}, ui.fmt_date(f.get("t_valid") or "")),
                          h("span", {"class_": "mem-fx"}, f.get("fact", ""),
                            (fragment(" ", sup_label) if sup else None))))
        status = h("span", {"class_": "mem-status"}, e["status"]) if e.get("status") else None
        return h("div", {"class_": "mem-ent"},
                 h("div", {"class_": "mem-ent-h"}, raw(_icon(icon)), h("b", {}, e.get("name", "—")), status),
                 h("div", {"class_": "mem-tl"}, fragment(*rows)) if rows else h("p", {"class_": "muted small"}, "—"))

    know_secs = []
    for kind, icon in _MEM_KINDS:
        ents = by_kind.get(kind) or []
        if ents:
            know_secs.append(h("div", {"class_": "mem-group"},
                               h("div", {"class_": "mem-group-h"}, _mem_kind_label(kind), h("span", {"class_": "mem-n"}, str(len(ents)))),
                               h("div", {"class_": "mem-ents"}, fragment(*(_ent_card(e, icon) for e in ents)))))
    knowledge = fragment(*know_secs) if know_secs else h("p", {"class_": "muted"}, t("none"))

    # --- open threads (loops) ---
    loops = [h("div", {"class_": "mem-loop"}, h("span", {"class_": "mem-loop-dot"}), th["text"],
               h("span", {"class_": "muted small"}, f' · {t("since")} {ui.fmt_date(th.get("opened_on") or "")}'))
             for th in store.list_threads(pid, "open")[:20]]

    # --- compact toolbar: recall search + time-travel (one row, not two big cards) ---
    toolbar = h("div", {"class_": "mem-bar"},
        h("form", {"method": "get", "class_": "mem-tool"}, raw(_icon("search")),
          h("input", {"type": "text", "name": "q", "value": q or "", "placeholder": t("recall_placeholder")})),
        h("form", {"method": "get", "class_": "mem-tool"}, raw(_icon("clock")),
          h("input", {"type": "date", "name": "as_of", "value": as_of or ""}),
          h("button", {"class_": "sl-btn sl-btn--sm"}, t("show_state"))))
    panes = []
    if as_of:
        sa = services.get_state_at(pid, as_of, store=store)
        rows = [h("div", {"class_": "mem-fact"}, h("span", {"class_": "mem-date"}, e["kind"]),
                  h("span", {"class_": "mem-fx"}, h("b", {}, e["name"]), " → ", e.get("status_at") or "—"))
                for e in sa["entities"] if e.get("status_at")]
        panes.append(h("div", {"class_": "mem-pane"}, h("div", {"class_": "mem-pane-h"}, t("state_at", date=as_of)),
                       fragment(*rows) if rows else h("p", {"class_": "muted small"}, t("nothing_valid")),
                       h("p", {"class_": "muted small"}, t("open_threads_count", n=len(sa.get("open_threads", []))))))
    if q:
        hits = services.recall_memory(pid, q, store=store, k=8)["hits"]
        rows = [h("div", {"class_": "mem-hit"}, h("span", {"class_": "muted small"}, f'{hit["obj_type"]} · {hit.get("when") or ""}'),
                  h("div", {}, hit["text"])) for hit in hits]
        panes.append(h("div", {"class_": "mem-pane"}, h("div", {"class_": "mem-pane-h"}, t("recall")),
                       fragment(*rows) if rows else h("p", {"class_": "muted small"}, t("nothing"))))

    main = fragment(
        _hero(t("memory_title", name=p["display_name"]), sub=t("memory_sub"), icon="memory"),
        toolbar, fragment(*panes),
        h("div", {"class_": "sec"}, h("h2", {}, t("knowledge")), knowledge),
        h("div", {"class_": "sec"}, h("h2", {}, t("open_threads")),
          h("div", {"class_": "mem-loops"}, fragment(*loops)) if loops else h("p", {"class_": "muted"}, t("none"))))
    return _doc(main)


def _catalog_notice(status: str = "") -> str:
    return h("div", {"class_": "sl-catalog-note"}, status) if status else ""


def _catalog_tier_label(tier: str) -> str:
    return {"free": t("catalog_tier_free"), "premium": t("catalog_tier_premium")}.get(tier, tier)


def _catalog_status_label(status: str) -> str:
    return {
        "up_to_date": t("catalog_status_up_to_date"),
        "behind": t("catalog_status_behind"),
        "possibly_behind": t("catalog_status_possibly_behind"),
        "locally_modified": t("catalog_status_locally_modified"),
        "diverged": t("catalog_status_diverged"),
        "removed_upstream": t("catalog_status_removed_upstream"),
    }.get(status, status)


def _catalog_avatar(entry: dict) -> str:
    name = entry.get("display_name") or entry.get("slug") or "?"
    if entry.get("has_avatar") and entry.get("slug"):
        return h("img", {"class_": "sl-catalog-avatar", "src": f'/personas/catalog/avatar/{entry["slug"]}',
                         "alt": "", "loading": "lazy", "width": "28", "height": "28",
                         "style": "width:28px;height:28px;object-fit:cover"})
    return raw(_avatar({"display_name": name}, 28))


def _catalog_row(entry: dict, store: Store, local: dict[str, dict], status_by_slug: dict[str, dict]) -> str:
    from .._forms import csrf_field

    slug = entry.get("slug") or ""
    existing = local.get(slug)
    tier = entry.get("tier") or "free"
    status = (status_by_slug.get(slug) or {}).get("status")
    meta = [_label(_catalog_tier_label(tier),
                   "var(--amber)" if tier == "premium" else "var(--green)",
                   "soft" if tier == "premium" else "outline")]
    if existing:
        meta.append(_label(t("catalog_imported"), "var(--accent)", "soft"))
    if status and status != "up_to_date":
        meta.append(_label(_catalog_status_label(status), "var(--amber)", "outline"))

    if existing:
        action = h("a", {"class_": "sl-btn", "href": f'/personas/{existing["id"]}'}, t("open"))
        if status in {"behind", "possibly_behind"}:
            action = fragment(
                action,
                h("form", {"class_": "sl-catalog-form", "method": "post", "action": "/personas/catalog/pull"},
                  raw(csrf_field()),
                  h("input", {"type": "hidden", "name": "slug", "value": slug}),
                  h("button", {"class_": "sl-btn", "type": "submit"}, t("catalog_update"))))
    else:
        action = h("form", {"class_": "sl-catalog-form", "method": "post", "action": "/personas/catalog/pull"},
                   raw(csrf_field()),
                   h("input", {"type": "hidden", "name": "slug", "value": slug}),
                   h("button", {"class_": "sl-btn sl-btn--primary", "type": "submit"}, t("catalog_add")))

    title = h("span", {"class_": "sl-catalog-row-title"},
              h("span", {}, entry.get("display_name") or slug),
              h("span", {"class_": "sl-catalog-slug"}, slug))
    return h("div", {"class_": "row"},
             _catalog_avatar(entry),
             h("span", {"class_": "title"}, title,
               h("span", {"class_": "muted small"}, f' · {entry.get("role") or "—"}')),
             h("span", {"class_": "right"}, fragment(*(meta + [action]))))


def _catalog_parse_facets(params) -> dict[str, list[str]]:
    facets: dict[str, list[str]] = {}
    for key in _CATALOG_FACETS:
        raw_val = params.get(key)
        if raw_val:
            facets[key] = [v.strip() for v in raw_val.split(",") if v.strip()]
    return facets


def _catalog_url(*, q: str, facets: dict[str, list[str]], cursor: str | None = None) -> str:
    from urllib.parse import urlencode

    qs: dict[str, str] = {}
    if q:
        qs["q"] = q
    for key in _CATALOG_FACETS:
        vals = facets.get(key) or []
        if vals:
            qs[key] = ",".join(vals)
    if cursor:
        qs["cursor"] = cursor
    return "/personas/catalog" + (("?" + urlencode(qs)) if qs else "")


def _catalog_toggle(facets: dict[str, list[str]], key: str, value: str) -> dict[str, list[str]]:
    nxt = {k: list(v) for k, v in facets.items()}
    vals = nxt.get(key, [])
    nxt[key] = [v for v in vals if v != value] if value in vals else vals + [value]
    if not nxt[key]:
        nxt.pop(key, None)
    return nxt


def _catalog_value_label(key: str, value: str) -> str:
    return _CATALOG_VALUE_LABELS.get(key, {}).get(value, value)


def _catalog_facets_html(data: dict, q: str, selected: dict[str, list[str]]) -> str:
    summary = data.get("facet_summary") or {}
    groups = []
    for key in _CATALOG_FACETS:
        vals = summary.get(key) or {}
        if len(vals) <= 1 and not selected.get(key):
            continue
        chips = []
        for value, count in sorted(vals.items(), key=lambda kv: (-kv[1], kv[0]))[:12]:
            active = value in (selected.get(key) or [])
            chips.append(h("a", {"class_": "sl-catalog-chip" + (" is-active" if active else ""),
                                 "href": _catalog_url(q=q, facets=_catalog_toggle(selected, key, value))},
                           (raw(_icon("check")) if active else None),
                           _catalog_value_label(key, value),
                           h("span", {"class_": "sl-catalog-chip__count"}, str(count))))
        if chips:
            groups.append(h("div", {"class_": "sl-catalog-facet"},
                            h("span", {"class_": "sl-catalog-facet__label"},
                              _CATALOG_FACET_LABELS.get(key, key.replace("_", " "))),
                            fragment(*chips)))
    if not groups:
        return ""
    return h("div", {"class_": "sl-catalog-facets"},
             fragment(*groups),
             h("a", {"class_": "sl-btn", "href": _catalog_url(q=q, facets={})}, t("clear_filter")))


def _catalog_page(store: Store, *, q: str = "", cursor: str | None = None,
                  status: str = "", facets: dict[str, list[str]] | None = None) -> str:
    from .._forms import not_found
    from .._pager import _list_filter_box

    facets = facets or {}
    try:
        data = services.catalog_search(q or None, facets=facets or None, limit=25, cursor=cursor)
    except Exception:
        return not_found("personas", "personas")
    local = {p.get("slug"): p for p in services.list_personas(store=store) if p.get("slug")}
    cstat = services.catalog_status(store=store)
    status_by_slug = {i.get("slug"): i for i in cstat.get("items") or []}
    rows = [_catalog_row(e, store, local, status_by_slug) for e in data.get("items") or []]

    def link(label: str, cur: str | None) -> str:
        if not cur:
            return h("span", {"class_": "sl-btn", "aria-disabled": "true"}, label)
        return h("a", {"class_": "sl-btn", "href": _catalog_url(q=q, facets=facets, cursor=cur)}, label)

    after = h("nav", {"class_": "sl-pager"},
              link(t("pager_next"), data.get("next_cursor"))) if data.get("has_more") else ""
    return _list_page(
        store, title=t("catalog_h"), lead=t("catalog_lead"), rows=rows,
        empty_icon="personas", empty_msg=t("catalog_empty"), active="personas",
        pre=fragment(_catalog_notice(status),
                     raw(_list_filter_box("/personas/catalog", q)),
                     raw(_catalog_facets_html(data, q, facets))),
        count=data.get("total", len(rows)), after=after)



def register_personas(app) -> None:
    @app.get("/personas", response_class=HTMLResponse)
    def personas_list(page: int = Query(default=1, ge=1), q: str = Query(default="")) -> str:
        # Paginated per the shared convention (docs/pagination.md): ?page=N rides the URL
        # next to ?q=, the count is the FULL filtered set, a changed filter resets the page.
        from .._pager import _list_filter_box, _page_window, _pager
        store = Store()
        personas = services.list_personas(store=store)
        if q:
            needle = q.strip().casefold()
            personas = [p for p in personas
                        if needle in p.get("display_name", "").casefold()
                        or needle in (p.get("role") or {}).get("title", "").casefold()
                        or needle in p.get("slug", "").casefold()]
        visible, page, pages = _page_window(personas, page)
        rows = [_persona_row(p, store) for p in visible]
        actions = h("a", {"class_": "sl-btn", "href": "/personas/catalog"},
                    raw(_icon("search")), " ", t("catalog_open"))
        return _list_page(store, title=t("personas"), lead=t("personas_lead"), rows=rows,
                          empty_icon="personas", empty_msg=t("no_personas"), active="personas",
                          pre=_list_filter_box("/personas", q) if (q or pages > 1) else "",
                          count=len(personas), after=_pager("/personas", page, pages, q),
                          actions=actions)

    @app.get("/personas/catalog", response_class=HTMLResponse)
    def personas_catalog(request: Request, q: str = Query(default=""),
                         cursor: str | None = Query(default=None),
                         status: str = Query(default="")) -> str:
        return _catalog_page(Store(), q=q, cursor=cursor, status=status,
                             facets=_catalog_parse_facets(request.query_params))

    @app.get("/personas/catalog/avatar/{slug}")
    def personas_catalog_avatar(slug: str):
        data = services.catalog_avatar(slug)
        if data is None:
            return Response(status_code=404)
        return Response(content=data, media_type="image/png")

    @app.post("/personas/catalog/pull")
    async def personas_catalog_pull(request: Request):
        from urllib.parse import urlencode

        from .._forms import see_other, write_gate

        form = await request.form()
        slug = str(form.get("slug") or "").strip()
        if (gate := write_gate(form, "catalog_pull_persona", {"slug": slug})) is not None:
            return gate
        if not slug:
            return see_other("/personas/catalog?" + urlencode({"status": t("catalog_missing_slug")}))
        store = Store()
        out = services.catalog_pull(persona_slugs=[slug], store=store)
        if out.get("landed"):
            return see_other(f'/personas/{out["landed"][0]["id"]}')
        skipped = (out.get("skipped_premium") or out.get("skipped_locally_modified") or [])
        msg = skipped[0].get("reason") if skipped else out.get("note") or t("catalog_pull_noop")
        return see_other("/personas/catalog?" + urlencode({"q": slug, "status": msg}))

    @app.get("/personas/{persona_id}/avatar", response_class=Response, include_in_schema=False)
    def persona_avatar(persona_id: str) -> Response:
        """Serve one portrait through the request's exact active workspace.

        Persona ids are stable across catalog pulls, while each workspace may own a
        different local revision.  Therefore the response is deliberately never cached
        and the record plus backing file are both resolved again inside the active scope.
        """
        from ... import config

        tenant_token = None
        if config.postgres_row_tenancy_enabled():
            scope = config.request_tenant_scope()
            if scope is None or not scope[1] or scope[1] not in scope[0]:
                return Response(status_code=404, headers={"Cache-Control": "no-store"})
            active_id = scope[1]
            tenant_token = config.set_request_tenant_scope([active_id], active_id)

        store = Store()
        try:
            try:
                from ...avatar import get_persona_avatar_content
                data, persona = get_persona_avatar_content(persona_id, store=store)
            except (FileNotFoundError, KeyError, ValueError):
                # Collapse absent record, absent file and rejected path into one answer;
                # tenant boundaries must not become an existence oracle.
                return Response(status_code=404, headers={"Cache-Control": "no-store"})
        finally:
            store.close()
            if tenant_token is not None:
                config.reset_request_tenant_scope(tenant_token)

        filename = f'{persona.get("slug") or persona["id"]}.png'
        headers = {
            "Cache-Control": "private, no-store",
            "Content-Disposition": f"inline; filename*=UTF-8''{quote(filename, safe='')}",
            "Content-Security-Policy": "default-src 'none'; sandbox",
            "Cross-Origin-Resource-Policy": "same-origin",
            "X-Content-Type-Options": "nosniff",
        }
        return Response(content=data, media_type="image/png", headers=headers)

    @app.get("/personas/{persona_id}", response_class=HTMLResponse)
    def persona_detail(persona_id: str, date_value: str | None = Query(default=None, alias="date"), view: str = Query(default="month")) -> str:
        store = Store()
        try:
            data = services.get_persona(persona_id, store)
        except KeyError:
            return _layout(t("not_found"), _empty_state(t("profile_not_found"), t("persona_runtime_cleared"), icon="personas"), store, active="personas")
        p = data["persona"]
        state = services.get_current_state(p["id"], store=store)
        selected_date = date_value or (data["daily_summaries"][-1]["date"] if data["daily_summaries"] else date.today().isoformat())
        view = view if view in {"week", "month", "year"} else "month"
        period = services.get_calendar_period(p["id"], selected_date, view, store)
        # _avatar_src guards against avatar records whose image file is missing on this
        # machine (snapshots carry the record, not always the binary) — initials, not a
        # broken <img> frame.
        portrait_src = _avatar_src(p)
        avatar = (h("img", {"class_": "avatar", "src": portrait_src, "alt": ""})
                  if portrait_src else h("div", {}, _avatar(p, 120)))
        has_sim = bool(data["daily_summaries"]) or bool(period.get("days"))
        voices = _persona_voices_html(store, p["id"])
        # This persona's recorded usability sessions — each row deep-links into the replay view.
        usess = services.list_usability_sessions(persona_id=p["id"], store=store)
        sessions_html = _sessions_section(store, usess)
        rel_rows = fragment(*(h("p", {}, h("strong", {}, r["name"]), " ",
                              h("span", {"class_": "muted"}, f'— {r["type"]}: {r["friction"]}')) for r in p["relationships"]))
        cal_section = h("div", {"class_": "sec", "id": "cal"}, h("h2", {}, t("calendar")),
            (fragment(raw(_calendar_tabs(p["id"], selected_date, view, period)),
                      raw(_period_calendar_html(p["id"], selected_date, view, period)))
             if has_sim else h("p", {"class_": "muted"}, t("no_days_yet"))))
        # Catalog provenance is a first-class signal: a persona pulled from sonaloop-data
        # carries its lived days + memory, so mark it so it reads differently from a
        # locally-authored profile. The pulled_at/ref ride the tooltip.
        cat_prov = (p.get("provenance") or {}).get("catalog")
        eyebrow_pills = ()
        if cat_prov:
            tip = " · ".join(x for x in [cat_prov.get("ref"), cat_prov.get("pulled_at")] if x)
            eyebrow_pills = (raw(_label(t("persona_from_catalog"), "var(--accent)", "soft",
                                        True, tip or None)),)
        main = fragment(
            _hero(p["display_name"], sub=f'{p["role"]["title"]} · {p["company_context"]["industry"]}',
                  top=detail_eyebrow(t("persona"), eyebrow_pills)),
            h("div", {"class_": "identity"}, h("div", {}, avatar), h("div", {},
              h("div", {"class_": "sl-card"}, h("h3", {}, t("current_state")),
                h("p", {}, h("strong", {}, state["current_activity"])),
                h("p", {"class_": "muted small"}, " · ".join(x for x in [
                    state.get("current_tool"), state.get("collaboration_mode"),
                    (state["mood"] if state.get("mood") not in (None, "unknown") else None)] if x) or "—"),
                (h("p", {"class_": "thought"}, state["current_thought"])
                 if state.get("current_thought") not in (None, "", "unknown") else "")))),
            # the simulated LIFE (the calendar) is this persona's signature — surface it right after the
            # snapshot, before the analysis voices.
            cal_section,
            raw(voices),
            raw(sessions_html),
            _capabilities_html(p.get("capabilities") or {}),
            h("div", {"class_": "sec", "id": "ziele"}, h("h2", {}, t("goals")), raw(_pills(p["goals"]))),
            h("div", {"class_": "sec", "id": "pains"}, h("h2", {}, t("pain_points")),
              # structured observations (issue + opportunity + severity/evidence) → the SAME finding row
              # as the synthesis; the plain profile list stays compact pills.
              (raw(render_findings([_artifacts.pain_point_finding(x) for x in data["pain_points"]]))
               if data["pain_points"] else raw(_pills(p["pain_points"])))),
            h("div", {"class_": "sec", "id": "tools"}, h("h2", {}, t("tools")), raw(_pills(p["tools"]))),
            h("div", {"class_": "sec", "id": "bez"}, h("h2", {}, t("relationships")), rel_rows),
            # server-provided prev/next sibling URLs for the keymap's [ / ] bindings
            raw(sibling_attrs(*sibling_urls(
                [f'/personas/{pp["id"]}' for pp in services.list_personas(store=store)],
                f'/personas/{p["id"]}'))))
        props = _properties_html([
            ("personas", t("role"), p["role"]["title"]),
            ("projects", t("industry"), p["company_context"]["industry"]),
            ("dot", t("size"), p["company_context"].get("size", "")),
            ("memory", t("memory"), h("a", {"class_": "sl-breadcrumb__link", "href": f'/personas/{p["id"]}/memory'}, raw(_icon("memory")), " ", t("open"))),
        ], aside=True)
        prail = ([("cal", t("calendar"))]
                 + ([("sec-sessions", t("sessions"))] if sessions_html else [])
                 + [("caps", t("capabilities_h")),
                    ("ziele", t("goals")), ("pains", t("pain_points")), ("tools", t("tools")),
                    ("bez", t("relationships")), ("sec-properties", t("properties"))])
        # V10: the "…" overflow — metadata edit as a dialog + the typed-confirm delete;
        # persona CREATE stays MCP-only.
        from .edit import persona_actions
        from .._palette import visit_marker   # the palette's recents beacon (UX V6)
        return _layout(p["display_name"],
                       _doc(main, rail=props) + _page_rail(prail) + visit_marker(p["display_name"]), store,
                       crumbs=[(t("personas"), "/personas"), (p["display_name"], None)], active="personas",
                       actions=fragment(raw(persona_actions(p)),
                                        _star("persona", p["id"], p["display_name"], f'/personas/{p["id"]}')))

    @app.get("/personas/{persona_id}/memory", response_class=HTMLResponse)
    def persona_memory(persona_id: str, as_of: str | None = Query(default=None), q: str | None = Query(default=None)) -> str:
        store = Store()
        pm = store.get_persona(persona_id)
        cr = [(t("personas"), "/personas"), (pm["display_name"] if pm else persona_id, f"/personas/{persona_id}"), (t("memory"), None)]
        return _layout(t("memory"), _memory_html(store, persona_id, as_of, q), store, crumbs=cr, active="personas")

    @app.get("/activities/{activity_id}", response_class=HTMLResponse)
    def activity_detail(activity_id: str) -> str:
        store = Store()
        try:
            data = services.get_activity(activity_id, store)
        except KeyError:
            return _layout(t("not_found"), _empty_state(t("activity_not_found"), t("runtime_maybe_cleared"), icon="overview"), store, active="personas")
        p = data["persona"]; a = data["activity"]
        alone_label = t("alone")
        conv = [h("div", {"class_": "quote"}, h("strong", {}, c.get("speaker", "")), h("br"), c.get("text", ""))
                for c in a.get("conversation", [])]
        main = fragment(
            _hero(a["task"], sub=f'{a["timestamp"]} · {a["event_type"]} · {a.get("collaboration_mode","unknown")}'),
            h("div", {"class_": "grid two"},
              h("div", {"class_": "sl-card"}, h("h3", {}, t("what_happened")), h("p", {}, a.get("what_happened", a["summary"]))),
              h("div", {"class_": "sl-card"}, h("h3", {}, t("thought")), h("p", {"class_": "thought"}, a.get("persona_thought", "—")))),
            h("div", {"class_": "sec"}, h("h2", {}, t("conversation")),
              fragment(*conv) if conv else h("p", {"class_": "muted"}, t("none_f"))),
            h("div", {"class_": "grid"},
              h("div", {"class_": "sl-card"}, h("h3", {}, t("actions")), raw(_pills(a.get("actions_done", [])) or "—")),
              h("div", {"class_": "sl-card"}, h("h3", {}, t("artifacts")), raw(_pills(a.get("artifacts_touched", [])) or "—")),
              h("div", {"class_": "sl-card"}, h("h3", {}, t("open_loops")), raw(_pills(a.get("open_loops", [])) or "—"))))
        props = _properties_html([
            ("personas", t("persona"), h("a", {"class_": "sl-breadcrumb__link", "href": f'/personas/{p["id"]}'}, p["display_name"])),
            ("square", t("tool"), a["tool"]),
            ("dot", t("mood"), a["impact"]["mood"]),
            ("personas", t("participants"), _pills(a.get("participants", []) or [alone_label])),
            ("check", t("decision"), a.get("decision") or ""),
        ], aside=True)
        return _layout(a["task"], _doc(main, rail=props), store,
                       crumbs=[(t("personas"), "/personas"), (p["display_name"], f'/personas/{p["id"]}'), (a["task"][:46], None)], active="personas")
