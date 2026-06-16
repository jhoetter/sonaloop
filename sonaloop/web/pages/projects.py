"""Project pages: home/index, detail (outline/graph + hypotheses), report, plan (spec/roadmap.md R2)."""
from __future__ import annotations

from fastapi.responses import RedirectResponse

from ._ctx import *  # noqa: F401,F403  (shared render toolkit)
from .._graph_outline_sessions import outline_session_groups
from .._project_graph_view import augment_project_graph
# Presence contract (tracker: sonaloop/project-presence-contract) + UX P2 (spec/ux-contract.md
# §3.4): EVERY project-scoped kind is an outline row in its phase context — decisions, surveys,
# hypotheses, open questions and assets included (_graph_outline_extras builds their items).


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
        plan = services.get_plan(proj["id"], store=store)
        # Plan opens in a right drawer. Reports are NOT a top-bar button anymore — they're listed
        # inline in the outline as first-class artifacts (add as many as you like; they flow into the project).
        top_btn = ""
        if plan:
            plan_url = f'/projects/{proj["id"]}/plan'
            top_btn = h("a", {"class_": "sl-btn", "href": plan_url, "data-drawer": plan_url, "data-drawer-title": t("plan_h")},
                        raw(_icon("plan")), " ", t("plan_h"))
        protos = graph.get("prototypes") or []
        arts = graph.get("artifacts") or []
        # Evidence assets: files/images/screenshots attached via MCP (ticket attach-evidence-files-mcp).
        assets = graph.get("assets") or []
        # THE project view = the Linear-style ROUND-grouped OUTLINE (clean, chronological, relationships
        # via indentation + hover-highlight).
        # The project's recorded usability sessions live IN the outline, nested under their subject
        # row (tracker: project-page-sessions-live-under-their-subject-in-the-outlin) — grouped here
        # (the route owns the Store), rendered by _outline_html. The flat section stays on /sessions
        # and the persona/prototype pages only.
        proto_ids = {p.get("id") for p in protos}
        proto_sessions = [s for s in store.list_prototype_sessions() if s.get("prototype_id") in proto_ids]
        sess_groups = outline_session_groups(
            services.list_usability_sessions(project_id=proj["id"], store=store), store,
            prototype_sessions=proto_sessions)
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
        display_graph = dict(graph)
        display_graph["outline_edges"] = augment_project_graph(
            graph, sessions=sess_groups, decisions=decisions, hypotheses=hypotheses,
            surveys=surveys, assets=assets).get("edges", [])
        outline = _outline_html(display_graph, sessions=sess_groups, decisions=decisions,
                                hypotheses=hypotheses, surveys=surveys,
                                filters=selected, facets_out=facets,
                                clear_href=f'/projects/{proj["id"]}', q=q)
        base = f'/projects/{proj["id"]}' + (f"?q={quote(q)}" if q else "")
        bar = filter_bar(base, facets, selected,
                         search={"value": q, "placeholder": t("search_project_ph")})
        # data-keynav arms the keymap's j/k row walk on the outline (ux-contract C7).
        main_view = h("div", {"class_": card_cls, "data-keynav": True}, raw(outline))
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
        def _methodology_name() -> str:
            key = (plan or {}).get("methodology") or proj.get("methodology") or ""
            if not key:
                return t("plan_freeform")
            try:
                from ... import job_taxonomy as _jt
                return _jt.get_framework_description(key, store).get("name", key)
            except Exception:
                try:
                    return services.get_methodology(key, store=store).get("name", key)
                except Exception:
                    return key

        method_chip = h("a", {"class_": "sl-toolbtn", "href": f'/projects/{proj["id"]}/plan',
                              "data-drawer": f'/projects/{proj["id"]}/plan',
                              "data-drawer-title": t("plan_h")},
                        raw(_icon("target")), " ",
                        t("methodology_h"), " · ", _methodology_name())
        chips = h("div", {"class_": "pills"}, raw(run_chip), method_chip, files_chip)
        # The FilterBar closes the head so it sits INSIDE the 900px measure (V1 — it used to
        # float at the page's far left), aligned with the title/outline left edge.
        body = h("div", {"class_": "proj"},
                 h("div", {"class_": "proj-head"}, h("h1", {"class_": "h1"}, proj["title"]),
                   h("p", {"class_": "lead"}, proj.get("goal", "")), chips, bar),
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
