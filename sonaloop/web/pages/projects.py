"""Project pages: home/index, detail (outline/graph + hypotheses), report, plan (spec/roadmap.md R2)."""
from __future__ import annotations

from fastapi.responses import RedirectResponse

from ._ctx import *  # noqa: F401,F403  (shared render toolkit)
from .._graph_outline_sessions import outline_session_groups
from .._primitive_taxonomy import PRIMITIVES, primitive_color, subtype_label, subtype_value
# Presence contract (tracker: sonaloop/project-presence-contract) + UX P2 (spec/ux-contract.md
# §3.4): EVERY project-scoped kind is an outline row in its phase context — decisions, surveys,
# hypotheses, open questions and assets included (_graph_outline_extras builds their items).
# asset_rows still feeds the ?view=graph floating panel.
from .._presence import asset_rows


def register_projects(app) -> None:
    @app.get("/", response_class=HTMLResponse)
    def index(page: int = Query(default=1, ge=1), q: str = Query(default="")) -> str:
        # Home is the Projects list (project-centric IA; Overview removed).
        return _projects_page(page, q)
    @app.get("/projects", response_class=HTMLResponse)
    def projects(page: int = Query(default=1, ge=1), q: str = Query(default="")) -> str:
        return _projects_page(page, q)

    @app.get("/projects/{project_id}", response_class=HTMLResponse)
    def project_detail(project_id: str, view: str = "list",
                       kind: str = Query(default=""), phase: str = Query(default=""),
                       persona: str = Query(default=""), status: str = Query(default=""),
                       theme: str = Query(default=""), q: str = Query(default="")) -> str:
        if view == "files":
            # The project FILES lens (UX U8 §8.3): all assets chronologically, in + out —
            # reachable from the header's "N files" chip; same scaffold, same rows.
            from .assets import project_files_page
            return project_files_page(project_id)
        store = Store()
        try:
            graph = services.get_project_graph(project_id, store=store)
        except KeyError:
            return _layout(t("not_found"), _empty_state(t("not_found"), t("runtime_maybe_cleared"), icon="projects"), store, active="projects")
        proj = graph["project"]
        # edge legend (shown in the floating open-questions panel)
        used_types = sorted({e["type"] for e in graph["edges"]})
        edge_leg = fragment(*(h("span", {"class_": "pill", "style": f'border-color:{_EDGE_COLORS.get(ty, "#9aa0a6")}'}, ty)
                              for ty in used_types)) or h("span", {"class_": "muted small"}, "—")
        oqs = [o for o in graph["open_questions"] if o.get("status") == "open"]
        oq_html = fragment(*(h("li", {}, o["text"]) for o in oqs[:30])) or h("li", {"class_": "muted"}, "—")
        # Plan opens in a right drawer. Reports are NOT a top-bar button anymore — they're listed
        # inline in the outline as first-class artifacts (add as many as you like; they flow into the project).
        top_btn = ""
        if services.get_plan(proj["id"], store=store):
            plan_url = f'/projects/{proj["id"]}/plan'
            top_btn = h("a", {"class_": "sl-btn", "href": plan_url, "data-drawer": plan_url, "data-drawer-title": t("plan_h")},
                        raw(_icon("plan")), " ", t("plan_h"))
        protos = graph.get("prototypes") or []
        # Q4: a TYPE filter row (also the LEGEND) — every node KIND present is a colored, glyph'd,
        # toggleable chip that filters the graph by type; capability/theme tags go to a 2nd muted row.
        type_meta: dict[str, tuple] = {}      # type -> (color, label, glyph)
        for n in graph["nodes"]:
            nt = n.get("note_kind") if str(n["study_id"]).startswith("note:") else str(n["study_id"]).split(":", 1)[0]
            if nt and nt not in type_meta:
                type_meta[nt] = (primitive_color(nt), n.get("kind_label", nt), n.get("glyph", ""))
        if protos:
            type_meta["prototype"] = (primitive_color("prototype"), t("prototypes_h"), PRIMITIVES["prototype"].icon)
        type_tagset = set(type_meta)
        type_chips = fragment(*(
            h("button", {"class_": "rgchip", "data-theme": ty, "style": f"--c:{c}"},
              (fragment(raw(_icon(glyph_icon(g))), " ") if g else ""), lab)
            for ty, (c, lab, g) in type_meta.items()))
        node_tags = []
        for n in graph["nodes"]:
            for tgx in n.get("theme_tags", []):
                if tgx not in node_tags and tgx not in type_tagset:
                    node_tags.append(tgx)
        tag_vocab = list(dict.fromkeys((proj.get("themes") or []) + node_tags))
        tag_chips = fragment(*(
            h("button", {"class_": "rgchip tagchip", "data-theme": th, "style": f"--c:{_theme_color(th, tag_vocab)}"}, th)
            for th in tag_vocab))
        left = (fragment(h("span", {"class_": "ptlabel"}, raw(_icon("search")), " ", t("type_h")), type_chips,
                         (fragment(h("span", {"class_": "ptlabel ptlabel-2"}, t("tags_h")), tag_chips) if tag_chips else ""),
                         h("a", {"class_": "rgclear", "style": "display:none"}, t("clear_filter"))) if type_chips else "")
        oqbtn = h("button", {"class_": "sl-btn", "id": "oqbtn"}, f'{t("legend")} · {t("open_questions_h")} ({len(oqs)})')
        toolbar = h("div", {"class_": "ptoolbar"}, left, h("span", {"class_": "spacer"}), oqbtn)  # Plan/Meta now in topbar
        # Artifact viewer: artifacts + recorded persona sessions (read-only).
        proto_html = ""
        if protos:
            rows = []
            for p in protos:
                sess = store.list_prototype_sessions(prototype_id=p["id"])
                sl = []
                for s in sess[:6]:
                    r = s.get("reaction", {})
                    gv = _icon("check") if s.get("grounded_verified") else _icon("circle")
                    nm = r.get("persona") or (store.get_persona(s.get("persona_id", "")) or {}).get("display_name") or s.get("persona_id", "")
                    # the persona name deep-links into the session's detail page (UX U7 §8.2)
                    sl.append(h("li", {}, h("a", {"href": f'/sessions/{s["id"]}'}, h("b", {}, nm)), ": ",
                                raw(_prose(r.get("verdict") or r.get("reaction_text") or "")),
                                " ", h("span", {"class_": "muted small"}, raw(gv), " ", t("grounded_yes"))))
                sl_html = (h("ul", {"style": "margin:4px 0 0 18px"}, fragment(*sl)) if sl
                           else h("div", {"class_": "muted small"}, f'— {t("no_sessions")} —'))
                ap = _artifact_present(p)
                pill = ap["disc"] or ap["label"]
                rows.append(h("div", {"class_": "strow"},
                              h("a", {"href": f'/prototypes/{p["slug"]}'}, raw(_icon("projects")), h("b", {}, p["name"])), " ",
                              h("span", {"class_": "pill"}, pill), " ", h("span", {"class_": "muted small"}, p.get("version", "")), " ",
                              h("a", {"class_": "sl-btn", "style": "padding:2px 8px", "href": f'/prototypes/{p["slug"]}'},
                                t("open"), " ", raw(_icon("external"))), sl_html))
            proto_html = fragment(h("div", {"class_": "oqp-h"}, f'{t("prototypes_h")} ({len(protos)})'),
                                  fragment(*rows))
        # Artifacts in the council pool: real URLs / prototype links / A/B variants, each with its
        # captured-at + grounded snapshot status (ticket artifacts-into-council). Read-only.
        arts = graph.get("artifacts") or []
        arts_html = ""
        if arts:
            arows = []
            for a in arts:
                snap = a.get("snapshot") or {}
                captured = bool(snap.get("ok"))
                cap_icon = _icon("check") if captured else _icon("circle")
                cap_txt = (f'{t("artifact_captured")} · {ui.fmt_ts(a.get("captured_at") or "")}' if captured
                           else t("artifact_capture_failed"))
                kind_label = subtype_label(subtype_value("url_artifact", a))
                arows.append(h("div", {"class_": "strow"},
                               h("span", {"class_": "pill"}, a.get("label", "?")), " ",
                               h("a", {"href": a.get("url", "#"), "target": "_blank", "rel": "noopener"},
                                 raw(_icon("external")), h("b", {}, a.get("title") or a.get("url", ""))), " ",
                               h("span", {"class_": "pill"}, kind_label), " ",
                               h("span", {"class_": "muted small"}, raw(cap_icon), " ", cap_txt)))
            arts_html = fragment(h("div", {"class_": "oqp-h"}, f'{t("artifacts_h")} ({len(arts)})'),
                                 fragment(*arows))
        # Evidence assets: files/images/screenshots attached via MCP (ticket attach-evidence-files-mcp).
        # Read-only; the rows are shared with the default view's #assets section (_presence).
        assets = graph.get("assets") or []
        assets_html = ""
        if assets:
            assets_html = fragment(h("div", {"class_": "oqp-h"}, f'{t("assets_h")} ({len(assets)})'),
                                   raw(asset_rows(assets)))
        # Sections outline (methodology-independent groupings) — a navigable list in the panel.
        from ... import presentation as _pres
        secs = sorted(graph.get("sections") or [], key=lambda s: s.get("order", 0))
        sec_html = ""
        if secs:
            rows = []
            for s in secs:
                pr = _pres.present(s.get("kind", "theme"), s.get("presentation"))
                glyph = (pr.get("glyph") + " ") if pr.get("glyph") else ""
                rows.append(h("div", {"class_": "strow"},
                              h("a", {"href": f'/sections/{s["id"]}'},
                                h("span", {"class_": "pill", "style": f'border-color:{pr["color"]};color:{pr["color"]}'},
                                  glyph, s.get("title", ""))), " ",
                              h("span", {"class_": "muted small"}, f'{pr.get("short", s.get("kind",""))} · {len(s.get("member_ids",[]))}')))
            sec_html = fragment(h("div", {"class_": "oqp-h"}, f'{t("sections")} ({len(secs)})'), fragment(*rows))
        # Project pulse (assess_project) — a self-documenting status line for in-flight long runs.
        pulse_html = ""
        try:
            ap = services.assess_project(proj["id"], store=store)
            cov = ap["coverage"]["evidence_by_kind"]
            cov_str = " · ".join(f"{k}:{v}" for k, v in cov.items())
            gaps = ap.get("gaps") or []
            gap_str = (h("div", {"class_": "muted small", "style": "margin-top:4px"}, f'{t("gaps")}: ', "; ".join(gaps[:4]))
                       if gaps else "")
            # stalled banner: open work, nobody driving — name the ready step + the resume call
            rs = services.project_run_state(proj["id"], store=store)
            stall_html = ""
            if rs and rs.get("state") == "stalled":
                stall_html = h("div", {"class_": "strow"},
                               h("span", {"class_": "pill", "style": "border-color:var(--amber);color:var(--amber)"},
                                 t("stalled")), " ",
                               h("span", {"class_": "muted small"}, rs.get("note", "")))
            pulse_html = fragment(
                h("div", {"class_": "oqp-h"}, t("pulse")), stall_html,
                h("div", {"class_": "strow"}, h("span", {"class_": "pill"}, ap["recommendation"]), " ",
                  h("span", {"class_": "muted small"}, cov_str, f' · {t("saturation")}: {ap["saturation"]["hint"]}'), gap_str))
        except Exception:
            pulse_html = ""
        # Coverage / diversity check — a deterministic indicator over the study's PERSONA SET (is the panel
        # too narrow to trust?) with concrete gaps + recommended archetypes. German UI by default.
        coverage_html = ""
        try:
            cv = services.assess_coverage(proj["id"], store=store)
            ind = cv["indicator"]
            cgaps = cv.get("gaps") or []
            cgap_str = (h("div", {"class_": "muted small", "style": "margin-top:4px"},
                          f'{t("gaps")}: ', "; ".join(g["reason"] for g in cgaps[:3]))
                        if cgaps else "")
            recs = cv.get("recommendations") or []
            rec_str = (h("div", {"class_": "muted small", "style": "margin-top:4px"},
                         f'{t("coverage_recommend")}: ', "; ".join(r["description"] for r in recs[:2]))
                       if recs else "")
            coverage_html = fragment(
                h("div", {"class_": "oqp-h"}, t("coverage_h")),
                h("div", {"class_": "strow"},
                  h("span", {"class_": "pill"}, t("coverage_level_" + ind["level"])), " ",
                  h("span", {"class_": "muted small"},
                    f'{t("coverage_panel")}: {cv["panel_size"]}'
                    + (f' · {ind["reasons"][0]}' if ind.get("reasons") else "")),
                  cgap_str, rec_str))
        except Exception:
            coverage_html = ""
        # Open questions + legend + prototypes live in a floating panel so the graph keeps the canvas.
        panel = h("div", {"class_": "oqpanel", "id": "oqpanel", "hidden": True}, pulse_html, coverage_html,
                  h("div", {"class_": "oqp-h"}, t("build_order_edges_h")),
                  h("div", {"class_": "pills"}, edge_leg), sec_html,
                  h("div", {"class_": "oqp-h"}, t("open_questions_h")),
                  h("ul", {}, oq_html), proto_html, arts_html, assets_html)
        oq_js = ("<script>(function(){var b=document.getElementById('oqbtn'),"
                 "p=document.getElementById('oqpanel');if(!b||!p)return;"
                 "b.addEventListener('click',function(e){e.stopPropagation();p.hidden=!p.hidden;});"
                 "document.addEventListener('click',function(e){"
                 "if(!p.hidden&&!p.contains(e.target)&&e.target!==b)p.hidden=true;});})();</script>")
        # THE project view = the Linear-style ROUND-grouped OUTLINE (clean, chronological, relationships
        # via indentation + hover-highlight). The spatial graph is retired from the UI but still reachable
        # by URL (?view=graph) — code kept, just unlinked — so nothing is destroyed and it's reversible.
        is_graph = view == "graph"
        head_tools = toolbar if is_graph else ""   # graph view keeps the type-filter toolbar; list view has none
        # The project's recorded usability sessions live IN the outline, nested under their subject
        # row (tracker: project-page-sessions-live-under-their-subject-in-the-outlin) — grouped here
        # (the route owns the Store), rendered by _outline_html. The flat section stays on /sessions
        # and the persona/prototype pages only.
        sess_groups = outline_session_groups(
            services.list_usability_sessions(project_id=proj["id"], store=store), store)
        # UX P2 (§3.4): the absorbed kinds enter the outline as phase rows — the page route
        # fetches the lists (it holds the Store), _graph_outline_extras places them. The phase
        # group headers carry the honest counts (C8); the appendix sections + jump chips retired.
        decisions = services.list_decisions(proj["id"], store=store)
        hypotheses = services.list_hypotheses(proj["id"], store=store)
        surveys = services.list_surveys(project_id=proj["id"], store=store)
        # A near-empty outline sizes to content instead of pinning a viewport-high dead zone;
        # a full outline keeps filling the viewport.
        n_rows = (len(graph["nodes"]) + len(protos) + len(graph.get("reports") or []) + len(arts)
                  + len(decisions) + len(hypotheses) + len(surveys) + len(assets)
                  + len(graph["open_questions"])
                  + sum(1 + len(g["sessions"]) for g in sess_groups.values()))
        card_cls = "outlinecard" + ("" if n_rows > 8 else " ol-compact")
        # U10/V1 (§8.5, §9 V1): the Linear-grade FilterBar over the outline — search + facet
        # state live in the URL (?q=…&kind=…&phase=…&persona=…&status=…&theme=…; comma = OR,
        # params AND), the outline filters server-side, and the bar renders the search slot,
        # the facet menu and the removable chips as ONE row INSIDE the content measure.
        from urllib.parse import quote
        from .._filterbar import filter_bar, parse_multi
        selected = {"kind": parse_multi(kind), "phase": parse_multi(phase),
                    "persona": parse_multi(persona), "status": parse_multi(status),
                    "theme": parse_multi(theme)}
        facets: list = []
        outline = _outline_html(graph, sessions=sess_groups, decisions=decisions,
                                hypotheses=hypotheses, surveys=surveys,
                                filters=selected, facets_out=facets,
                                clear_href=f'/projects/{proj["id"]}', q=q)
        base = f'/projects/{proj["id"]}' + (f"?q={quote(q)}" if q else "")
        bar = (filter_bar(base, facets, selected,
                          search={"value": q, "placeholder": t("search_project_ph")})
               if not is_graph else "")
        # data-keynav arms the keymap's j/k row walk on the outline (ux-contract C7).
        main_view = (fragment(h("div", {"class_": "graphcard proj-graph"}, raw(_graph_interactive(graph))), panel, raw(oq_js))
                     if is_graph else h("div", {"class_": card_cls, "data-keynav": True}, raw(outline)))
        # The run-state chip (ux-contract §3.5 / decision §7.4): `▶ Run · state` with a
        # popover (last activity · next-ready/resume hint · /runs journal link). Runs left
        # the nav; this header chip is where a project's driver status now surfaces.
        from .._runs_widget import project_run_chip
        run_chip = project_run_chip(proj["id"], store)
        # The FILES lens entry (UX U8): a status chip next to the run chip — every asset of
        # the project (evidence in + deliverables out) chronologically, the provenance
        # timeline. Both chips share the .sl-toolbtn shape family (W3: one toolbar read).
        files_chip = h("a", {"class_": "sl-toolbtn", "href": f'/projects/{proj["id"]}?view=files'},
                       raw(_icon("file")), " ",
                       t("one_file") if len(assets) == 1 else t("n_files", n=len(assets)))
        chips = h("div", {"class_": "pills"}, raw(run_chip), files_chip)
        # The FilterBar closes the head so it sits INSIDE the 900px measure (V1 — it used to
        # float at the page's far left), aligned with the title/outline left edge.
        body = h("div", {"class_": "proj"},
                 h("div", {"class_": "proj-head"}, h("h1", {"class_": "h1"}, proj["title"]),
                   h("p", {"class_": "lead"}, proj.get("goal", "")), chips,
                   head_tools, bar),
                 main_view)
        # Write affordances (web CRUD, V10 §9): the ONE visible "…" overflow — Edit opens the
        # metadata dialog over the page, Delete the typed-confirm modal. No create buttons
        # (notes/sections/projects are created by the MCP/CLI host).
        from .edit import project_actions
        actions = fragment(top_btn,
                           raw(project_actions(proj)),
                           raw(_star("project", proj["id"], proj["title"], f'/projects/{proj["id"]}')))
        from .._palette import visit_marker   # the palette's recents beacon (UX V6)
        return _layout(proj["title"], body + visit_marker(proj["title"]), store, active="projects",
                       crumbs=[(t("projects"), "/projects"), (proj["title"], None)], actions=actions)

    # ---- Hypotheses/decisions still anchor on their project page (the bets/decisions rows),
    #      but their canonical Ref routes /hypotheses/{id} and /decisions/{id} now serve REAL
    #      detail pages (UX U7, §8.2) — registered with their kind modules (pages/hypotheses,
    #      pages/decisions); the old redirects retired. ----

    # ---- A report is a project-scope synthesis; its canonical URL is /syntheses/{id} (+ .pdf).
    #      /projects/{id}/meta is a convenience → the project's latest report. ----
    @app.get("/projects/{project_id}/meta")
    def project_meta(project_id: str):
        store = Store()
        reports = store.list_reports(project_id)
        if reports:
            return RedirectResponse(f'/syntheses/{reports[0]["id"]}')
        try:
            proj = services.get_research_project(project_id, store=store)
        except KeyError:
            return HTMLResponse(_layout(t("not_found"), _empty_state(t("synthesis_kind"), t("runtime_maybe_cleared"), icon="overview"), store, active="projects"))
        return HTMLResponse(_layout(proj["title"] + " — " + t("synthesis_kind"),
                                    _empty_state(t("synthesis_kind"), t("report_unavailable"), icon="overview"),
                                    store, active="projects",
                                    crumbs=[(t("projects"), "/projects"), (proj["title"], f"/projects/{project_id}"), (t("synthesis_kind"), None)]))

    @app.get("/projects/{project_id}/plan", response_class=HTMLResponse)
    def project_plan(project_id: str) -> str:
        store = Store()
        try:
            proj = services.get_research_project(project_id, store=store)
        except KeyError:
            return _layout(t("not_found"), _empty_state(t("plan_h"), t("runtime_maybe_cleared"), icon="plan"), store, active="projects")
        plan = services.get_plan(project_id, store=store)
        if not plan:
            body = h("div", {"class_": "page"}, raw(_empty_state(t("plan_h"), t("no_plan_yet"), icon="plan")))
        else:
            body = _plan_html(plan, store)
        return _layout(f'{proj["title"]} — {t("plan_h")}', body, store,
                       crumbs=[(t("projects"), "/projects"), (proj["title"], f"/projects/{project_id}"), (t("plan_h"), None)],
                       active="projects")
