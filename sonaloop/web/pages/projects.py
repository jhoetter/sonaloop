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
from .._html import register_css
from .._cohort_integrity_view import render_cohort_integrity
# Presence contract (tracker: sonaloop/project-presence-contract) + UX P2 (spec/ux-contract.md
# §3.4): EVERY project-scoped kind is an outline row in its phase context — decisions, surveys,
# hypotheses, open questions and assets included (_graph_outline_extras builds their items).

register_css(r"""
.sl-pu-card{border:1px solid var(--line);border-left:3px solid var(--green);border-radius:var(--radius);background:var(--panel);padding:12px 14px;margin:14px 0}.sl-pu-card--missing{border-left-color:var(--amber)}
.sl-pu-head{display:flex;align-items:center;justify-content:space-between;gap:12px}.sl-pu-head strong{display:flex;align-items:center;gap:7px}.sl-pu-meta{color:var(--muted);font-size:var(--t-sm);margin-top:4px}.sl-pu-caps{margin:9px 0 0;padding-left:18px;font-size:var(--t-sm)}
.sl-project-creator{color:var(--muted);font-size:var(--t-xs);margin:4px 0 0}
""")


def _product_understanding_html(project: dict, store=None,
                                preflight: dict | None = None) -> str:
    """Compact, inspectable preflight state on the job that it governs."""
    policy = project.get("integrity") or {}
    versions = project.get("product_understanding_versions") or []
    current_id = str(project.get("product_understanding_current_id") or "")
    current = next((row for row in versions if str(row.get("id") or "") == current_id), None)
    current = current or (versions[-1] if versions else None)
    if not current:
        if not policy.get("product_understanding_required"):
            return ""
        kind = str((preflight or {}).get("kind") or "")
        help_text = (t("product_flow_manifest_missing_help")
                     if kind == "flow_manifest_required"
                     else t("product_inventory_missing_help")
                     if kind == "product_understanding_required"
                     else t("product_understanding_missing_help"))
        return h("div", {"class_": "sl-pu-card sl-pu-card--missing", "id": "product-understanding",
                         "role": "status", "data-setup-kind": kind or "product_understanding_required",
                         "aria-label": help_text},
                 h("div", {"class_": "sl-pu-head"},
                   h("strong", {}, raw(_icon("warning")), t("product_understanding_h")),
                   raw(_label(t("product_understanding_missing"), "var(--amber)"))),
                 h("div", {"class_": "sl-pu-meta"}, help_text))
    target = current.get("target") or {}
    target_name = target.get("name") or target.get("identity") or target.get("url") or "—"
    status_labels = {
        "observed_present": t("pu_observed_present"),
        "observed_absent": t("pu_observed_absent"),
        "inferred": t("pu_inferred"),
        "unknown": t("pu_unknown"),
    }
    capabilities = current.get("capabilities") or []
    unknowns = sum(1 for row in capabilities if row.get("status") == "unknown")
    verified_absences = sum(1 for row in capabilities if row.get("status") == "observed_absent")
    versions = project.get("product_understanding_versions") or []
    by_key = {}
    for version in versions:
        for row in version.get("capabilities") or []:
            by_key.setdefault(str(row.get("key") or row.get("claim") or ""), set()).add(
                str(row.get("status") or "unknown"))
    conflicts = sum(1 for values in by_key.values()
                    if {"observed_present", "observed_absent"} <= values)
    manifest = current.get("stimulus_manifest") or {}
    meta = (f"{target_name} · {t('pu_revision')} {current.get('revision') or '—'} · "
            f"{ui.fmt_ts(current.get('observed_at') or '')} · v{current.get('version', 1)}")
    if manifest.get("manifest_id"):
        meta += (
            f" · {t('pu_manifest')} {manifest['manifest_id']} "
            f"v{manifest.get('manifest_version') or '—'} · "
            f"{manifest.get('target_revision') or '—'} · "
            f"{manifest.get('manifest_digest') or '—'}"
        )
    from .._render import render_ref
    cap_rows = [h("li", {}, raw(_label(status_labels.get(str(row.get("status")), str(row.get("status"))),
                                             "var(--muted)")), " ", row.get("claim", ""),
                  h("div", {"class_": "sl-claim-sources"},
                    fragment(*(raw(render_ref(ref, store)) for ref in row.get("evidence_refs") or [])))
                  if row.get("evidence_refs") else None)
                for row in capabilities]
    aria = (f'{t("product_understanding_h")}. {target_name}. {t("pu_revision")} '
            f'{current.get("revision") or "—"}. {t("pu_unknown_n", n=unknowns)}.')
    return h("details", {"class_": "sl-pu-card", "id": "product-understanding",
                         "aria-label": aria},
             h("summary", {"class_": "sl-pu-head"},
               h("strong", {}, raw(_icon("target")), t("product_understanding_h")),
               raw(_label(t("pu_capabilities_n", n=len(capabilities)))),
               (raw(_label(t("pu_verified_absences_n", n=verified_absences), "var(--green)"))
                if verified_absences else None),
               (raw(_label(t("pu_unknown_n", n=unknowns), "var(--amber)")) if unknowns else None),
               (raw(_label(t("pu_conflicts_n", n=conflicts), "var(--red)")) if conflicts else None)),
             h("div", {"class_": "sl-pu-meta"}, meta),
             h("ul", {"class_": "sl-pu-caps"}, fragment(*cap_rows)))


def _cohort_selection_html(preflight: dict) -> str:
    """Render the server-projected between-gates setup action, if current."""
    if preflight.get("state") != "waiting" or preflight.get("gate") != "cohort_selection":
        return ""
    return h(
        "section",
        {"class_": "sl-pu-card sl-pu-card--missing", "id": "cohort-selection",
         "role": "status", "aria-label": t("cohort_selection_help")},
        h("div", {"class_": "sl-pu-head"},
          h("strong", {}, raw(_icon("personas")), t("cohort_selection_h")),
          raw(_label(t("cohort_integrity_missing"), "var(--amber)"))),
        h("div", {"class_": "sl-pu-meta"}, t("cohort_selection_help")),
    )


def _project_lineage_html(project: dict, store) -> str:
    predecessor = str(project.get("supersedes_project_id") or "")
    successor = str(project.get("superseded_by_project_id") or "")
    archived = str(project.get("status") or "") == "archived"
    if not (predecessor or successor or archived):
        return ""
    rows = []
    for label, pid in ((t("lineage_supersedes"), predecessor),
                       (t("lineage_superseded_by"), successor)):
        if not pid:
            continue
        target = store.get_research_project(pid)
        # Tenant-scoped Store lookup decides existence; never disclose a title
        # from an inaccessible workspace.
        rows.append(h("li", {}, label, ": ",
                      h("a", {"href": f"/jobs/{pid}"}, target.get("title") or pid)
                      if target else h("code", {}, pid)))
    if archived:
        rows.append(h("li", {}, t("archive_non_destructive")))
    return h("section", {"class_": "sl-pu-card", "id": "project-lineage",
                         "aria-label": t("lineage_h")},
             h("strong", {}, raw(_icon("link")), " ", t("lineage_h")),
             h("ul", {"class_": "sl-pu-caps"}, fragment(*rows)))


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
            top_btn = h("a", {"class_": "sl-toolbtn sl-tour-plan-chip", "href": plan_url,
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
        try:
            health = services.project_health(proj["id"], store=store)
        except Exception:
            health = {}
        preflight = health.get("preflight") or {}
        run_chip = project_run_chip(proj["id"], store, run_state=health)
        # The graph projection is deliberately lean and does not carry request-boundary
        # attribution. Read the canonical project row for this one presentation field;
        # only its display snapshot is rendered (never the opaque actor id).
        creator = services.get_research_project(proj["id"], store=store).get("created_by")
        creator_label = (
            str(creator.get("label") or "").strip() if isinstance(creator, dict) else ""
        )
        # The FilterBar closes the head so it sits INSIDE the 900px measure (V1 — it used to
        # float at the page's far left), aligned with the title/outline left edge.
        body = h("div", {"class_": "proj"},
                 h("div", {"class_": "proj-head"},
                   h("h1", {"class_": "h1 sl-project-title"},
                     raw(project_icon_html(proj, edit_project_id=proj["id"],
                                           edit_label=t("f_project_icon"))),
                     proj["title"]),
                   h("p", {"class_": "lead"}, proj.get("goal", "")),
                   (h("p", {"class_": "sl-project-creator"},
                      t("project_created_by", label=creator_label)) if creator_label else None),
                   h("div", {"class_": "pills"}, raw(run_chip)),
                   bar),
                 raw(_product_understanding_html(proj, store, preflight)),
                 raw(_cohort_selection_html(preflight)),
                 raw(render_cohort_integrity(
                     proj, store,
                     show_missing=(preflight.get("state") == "waiting"
                                   and preflight.get("gate") == "cohort_integrity"),
                 )),
                 raw(_project_lineage_html(proj, store)),
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
        body = h("div", {"class_": "sl-syn-main"}, raw(render_schema_outcomes([outcome], store, project_id)))
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
