"""Project pages: home/index, detail (outline/graph + hypotheses), report, plan (spec/roadmap.md R2)."""
from __future__ import annotations

from fastapi import Request
from fastapi.responses import RedirectResponse

from ... import result_outcomes
from ._ctx import *  # noqa: F401,F403  (shared render toolkit)
from .._graph_outline_sessions import outline_session_groups
from .._job_outcomes import render_schema_outcomes
from .._project_graph_view import augment_project_graph
from .._project_icons import project_icon_edit_script, project_icon_html
# Presence contract (tracker: sonaloop/project-presence-contract) + UX P2 (spec/ux-contract.md
# §3.4): EVERY project-scoped kind is an outline row in its phase context — decisions, surveys,
# hypotheses, open questions and assets included (_graph_outline_extras builds their items).


def register_projects(app) -> None:
    def _redirect_legacy(request: Request, target: str) -> RedirectResponse:
        query = request.url.query
        return RedirectResponse(target + (f"?{query}" if query else ""), status_code=308)

    @app.get("/", response_class=HTMLResponse)
    def index(page: int = Query(default=1, ge=1), q: str = Query(default="")) -> str:
        # Home is the Projects list (project-centric IA; Overview removed).
        return _projects_page(page, q)

    @app.get("/jobs", response_class=HTMLResponse)
    def projects(page: int = Query(default=1, ge=1), q: str = Query(default="")) -> str:
        return _projects_page(page, q)

    @app.get("/projects", include_in_schema=False)
    def legacy_projects_redirect(request: Request):
        return _redirect_legacy(request, "/jobs")

    @app.get("/projects/{project_path:path}", include_in_schema=False)
    def legacy_project_path_redirect(project_path: str, request: Request):
        return _redirect_legacy(request, f"/jobs/{project_path}")

    @app.get("/jobs/{project_id}", response_class=HTMLResponse)
    def project_detail(project_id: str,
                       kind: str = Query(default=""), phase: str = Query(default=""),
                       persona: str = Query(default=""), status: str = Query(default=""),
                       theme: str = Query(default=""), trace: str = Query(default=""),
                       q: str = Query(default="")) -> str:
        store = Store()
        try:
            graph = services.get_project_graph(project_id, store=store)
        except KeyError:
            return _layout(t("not_found"), _empty_state(t("not_found"), t("runtime_maybe_cleared"), icon="projects"), store, active="projects")
        proj = graph["project"]
        plan = services.get_plan(proj["id"], store=store)
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

        # Plan opens in a right drawer. Reports are NOT a top-bar button anymore — they're listed
        # inline in the outline as first-class artifacts (add as many as you like; they flow into the project).
        top_btn = ""
        if plan:
            plan_url = f'/jobs/{proj["id"]}/plan'
            top_btn = h("a", {"class_": "sl-toolbtn tour-plan-chip", "href": plan_url,
                              "data-drawer": plan_url, "data-drawer-title": t("plan_h")},
                        raw(_icon("target")), " ", _methodology_name())
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
                    "theme": parse_multi(theme), "trace": parse_multi(trace)}
        facets: list = []
        display_graph = dict(graph)
        display_graph["outline_edges"] = augment_project_graph(
            graph, sessions=sess_groups, decisions=decisions, hypotheses=hypotheses,
            surveys=surveys, assets=assets).get("edges", [])
        outline = _outline_html(display_graph, sessions=sess_groups, decisions=decisions,
                                hypotheses=hypotheses, surveys=surveys,
                                filters=selected, facets_out=facets,
                                clear_href=f'/jobs/{proj["id"]}', q=q)
        base = f'/jobs/{proj["id"]}' + (f"?q={quote(q)}" if q else "")
        bar = filter_bar(base, facets, selected,
                         search={"value": q, "placeholder": t("search_project_ph")})
        # data-keynav arms the keymap's j/k row walk on the outline (ux-contract C7).
        main_view = h("div", {"class_": card_cls, "data-keynav": True}, raw(outline))
        # The project run-state chip (`▶ Run · state`) belongs to the project head, not
        # the topbar: the topbar already has the global runs widget.
        from .._runs_widget import project_run_chip
        run_chip = project_run_chip(proj["id"], store)
        # The FilterBar closes the head so it sits INSIDE the 900px measure (V1 — it used to
        # float at the page's far left), aligned with the title/outline left edge.
        body = h("div", {"class_": "proj"},
                 h("div", {"class_": "proj-head"},
                   h("h1", {"class_": "h1 project-title"},
                     raw(project_icon_html(proj, edit_project_id=proj["id"],
                                           edit_label=t("f_project_icon"))),
                     proj["title"]),
                   h("p", {"class_": "lead"}, proj.get("goal", "")),
                   h("div", {"class_": "pills"}, raw(run_chip)),
                   bar),
                 main_view) + raw(project_icon_edit_script())
        # Write affordances (web CRUD, V10 §9): the ONE visible "…" overflow — Edit opens the
        # metadata dialog over the page, Delete the typed-confirm modal. No create buttons
        # (notes/sections/jobs are created by the MCP/CLI host).
        from .edit import project_actions
        actions = fragment(top_btn,
                           raw(project_actions(proj)),
                           raw(_star("project", proj["id"], proj["title"], f'/jobs/{proj["id"]}')))
        from .._palette import visit_marker   # the palette's recents beacon (UX V6)
        return _layout(proj["title"], body + visit_marker(proj["title"]), store, active="projects",
                       crumbs=[(t("projects"), "/jobs"), (proj["title"], None)], actions=actions)

    # ---- Hypotheses/decisions still anchor on their project page (the bets/decisions rows),
    #      but their canonical Ref routes /hypotheses/{id} and /decisions/{id} now serve REAL
    #      detail pages (UX U7, §8.2) — registered with their kind modules (pages/hypotheses,
    #      pages/decisions); the old redirects retired. ----

    @app.get("/jobs/{project_id}/outcomes/{outcome_id}", response_class=HTMLResponse)
    def project_job_outcome(project_id: str, outcome_id: str) -> str:
        store = Store()
        try:
            proj = services.get_research_project(project_id, store=store)
        except KeyError:
            return _layout(t("not_found"), _empty_state(t("not_found"), t("runtime_maybe_cleared"), icon="projects"),
                           store, active="projects")
        outcome = result_outcomes.get_project_schema_outcome(store, project_id, outcome_id)
        if not outcome:
            return _layout(t("not_found"), _empty_state(t("job_outcome_kind"), t("runtime_maybe_cleared"), icon="target"),
                           store, active="projects",
                           crumbs=[(t("projects"), "/jobs"), (proj["title"], f'/jobs/{project_id}'),
                                   (t("job_outcome_kind"), None)])
        body = h("div", {"class_": "syn-main"}, raw(render_schema_outcomes([outcome], store, project_id)))
        evidence_refs = outcome.get("evidence_refs") or []
        result_kind = str(outcome.get("result_kind") or "").replace("_", " ").strip()
        result_kind = result_kind[:1].upper() + result_kind[1:] if result_kind else ""
        prop_rows = [
            ("target", t("result_schema_h"), outcome.get("name") or outcome.get("schema_id", "")),
            ("tag", t("result_kind_h"), result_kind),
            ("link", t("evidence_refs_h"), str(len(evidence_refs))),
            ("clock", t("created"), ui.fmt_day(outcome.get("created_at", ""))),
        ]
        title = outcome.get("name") or outcome.get("schema_id", "")
        return detail_page(
            store, title=title, active="projects",
            crumbs=[(t("projects"), "/jobs"), (proj["title"], f'/jobs/{project_id}'),
                    (t("job_outcome_kind"), None)],
            body=body, icon="target", kind=t("job_outcome_kind"),
            sub=(outcome.get("schema") or {}).get("summary", ""),
            prop_rows=prop_rows,
            rel_proj_id=project_id,
            star=("job_outcome", outcome["id"], title, f'/jobs/{project_id}/outcomes/{outcome["id"]}'))

    # ---- A report is a project-scope synthesis; its canonical URL is /syntheses/{id} (+ .pdf).
    #      /jobs/{id}/meta is a convenience → the project's latest report. ----
    @app.get("/jobs/{project_id}/meta")
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
                                    crumbs=[(t("projects"), "/jobs"), (proj["title"], f"/jobs/{project_id}"), (t("synthesis_kind"), None)]))

    @app.get("/jobs/{project_id}/plan", response_class=HTMLResponse)
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
                       crumbs=[(t("projects"), "/jobs"), (proj["title"], f"/jobs/{project_id}"), (t("plan_h"), None)],
                       active="projects")
