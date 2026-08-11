"""Project pages: home/index, detail (outline/graph + hypotheses), report, plan (spec/roadmap.md R2)."""
from __future__ import annotations

from fastapi import Request
from fastapi.responses import RedirectResponse

from ... import result_outcomes
from ...creator_attribution import public_creator_projection, public_project_client_origin
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
.sl-pu-claim{color:var(--ink);line-height:1.5}.sl-pu-claim .lbl{margin-right:5px}.sl-pu-claim .sl-claim-sources{margin-top:3px}.sl-pu-technical code{font-size:inherit;overflow-wrap:anywhere}
.sl-project-creator{color:var(--muted);font-size:var(--t-xs);margin:4px 0 0}
.sl-project-meta{color:var(--muted);font-size:var(--t-xs);margin:4px 0 0}
.sl-project-setup{flex:none;width:100%;max-width:900px;margin:0 auto;padding:0 24px 10px;border:0;background:transparent}
.sl-project-setup>summary,.sl-project-lineage>summary{list-style:none;cursor:pointer;color:var(--muted);font-size:var(--t-xs);font-weight:500;display:flex;align-items:center;gap:6px;width:max-content}
.sl-project-setup>summary::-webkit-details-marker,.sl-project-lineage>summary::-webkit-details-marker{display:none}
.sl-project-setup[open]>summary,.sl-project-lineage[open]>summary{color:var(--ink)}
.sl-project-setup__body{padding:8px 0 6px}
.sl-project-lineage{margin:5px 0 0;border:0;background:transparent;font-size:var(--t-xs)}
.sl-project-lineage ul{margin:6px 0 0;padding-left:18px;color:var(--muted)}
""")


def _product_understanding_html(project: dict, store=None,
                                preflight: dict | None = None, *,
                                show_missing: bool = True,
                                embedded: bool = False) -> str:
    """Compact, inspectable preflight state on the job that it governs."""
    policy = project.get("integrity") or {}
    versions = project.get("product_understanding_versions") or []
    current_id = str(project.get("product_understanding_current_id") or "")
    current = next((row for row in versions if str(row.get("id") or "") == current_id), None)
    current = current or (versions[-1] if versions else None)
    if not current:
        if not policy.get("product_understanding_required") or not show_missing:
            return ""
        kind = str((preflight or {}).get("kind") or "")
        help_text = (t("product_flow_manifest_missing_help")
                     if kind == "flow_manifest_required"
                     else t("product_capture_review_missing_help")
                     if kind == "capture_review_required"
                     else t("product_inventory_missing_help")
                     if kind == "product_understanding_required"
                     else t("product_understanding_missing_help"))
        return h("section", {"class_": "sl-integrity sl-integrity-attention",
                              "id": "product-understanding", "role": "status",
                              "data-setup-kind": kind or "product_understanding_required",
                              "aria-label": help_text},
                 h("div", {"class_": "sl-integrity-heading"},
                   raw(_icon("warning")),
                   h("span", {"class_": "sl-integrity-heading-copy"},
                     h("strong", {"class_": "sl-integrity-title"},
                       t("product_understanding_h")),
                     h("span", {"class_": "sl-integrity-summary"}, help_text))),
                 raw(_label(t("product_understanding_missing"), "var(--amber)")))
    target = current.get("target") or {}
    target_name = target.get("name") or target.get("identity") or target.get("url") or "—"
    status_labels = {
        "observed_present": t("pu_observed_present"),
        "observed_absent": t("pu_observed_absent"),
        "inferred": t("pu_inferred"),
        "unknown": t("pu_unknown"),
    }
    capabilities = current.get("capabilities") or []
    unknowns = sum(1 for row in capabilities
                   if str(row.get("status") or "unknown") == "unknown")
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
    observed_value = current.get("observed_at") or ""
    observed_at = ui.local_ts(observed_value)
    time_marker = "__SONALOOP_LOCAL_TIME__"
    context_text = t(
        "pu_context_summary", target=target_name,
        revision=current.get("revision") or "—", observed=time_marker,
    )
    context_before, _, context_after = context_text.partition(time_marker)
    context = fragment(context_before, observed_at, context_after)
    from .._render import render_ref
    def capability_row(row: dict, *, show_status: bool = True):
        status = str(row.get("status") or "unknown")
        return h(
            "li", {"class_": "sl-pu-claim"},
            (raw(_label(status_labels.get(status, status), "var(--muted)"))
             if show_status else None),
            row.get("claim", ""),
            (h("div", {"class_": "sl-claim-sources"},
               fragment(*(raw(render_ref(ref, store))
                          for ref in row.get("evidence_refs") or [])))
             if row.get("evidence_refs") else None),
        )

    known_capabilities = [
        row for row in capabilities if str(row.get("status") or "unknown") != "unknown"
    ]
    unknown_capabilities = [
        row for row in capabilities if str(row.get("status") or "unknown") == "unknown"
    ]
    compact_summary = (
        t("pu_compact_summary_open", reviewed=len(known_capabilities), total=len(capabilities),
          unknown=len(unknown_capabilities))
        if unknown_capabilities else
        t("pu_compact_summary_complete_one") if len(capabilities) == 1 else
        t("pu_compact_summary_complete", total=len(capabilities))
    )
    technical_rows = [
        h("div", {}, h("dt", {}, t("pu_target")), h("dd", {}, target_name)),
        h("div", {}, h("dt", {}, t("pu_revision")),
          h("dd", {"class_": "sl-integrity-technical"}, current.get("revision") or "—")),
        h("div", {}, h("dt", {}, t("pu_observed_at")), h("dd", {}, observed_at)),
        h("div", {}, h("dt", {}, t("pu_record_version")),
          h("dd", {}, f"v{current.get('version', 1)}")),
    ]
    if manifest.get("manifest_id"):
        manifest_value = (
            f"{manifest['manifest_id']} v{manifest.get('manifest_version') or '—'} · "
            f"{manifest.get('target_revision') or '—'}"
        )
        technical_rows.extend([
            h("div", {}, h("dt", {}, t("pu_manifest")),
              h("dd", {"class_": "sl-integrity-technical"}, manifest_value)),
            h("div", {}, h("dt", {}, t("pu_manifest_digest")),
              h("dd", {"class_": "sl-integrity-technical"},
                h("code", {}, manifest.get("manifest_digest") or "—"))),
        ])
    aria = (f'{t("product_understanding_h")}. {target_name}. {t("pu_revision")} '
            f'{current.get("revision") or "—"}. {t("pu_unknown_n", n=unknowns)}.')
    wrapper_class = "sl-integrity sl-integrity--product"
    if embedded:
        wrapper_class += " sl-integrity--embedded"
    return h(
        "details", {"class_": wrapper_class, "id": "product-understanding",
                    "aria-label": aria},
        h("summary", {},
          h("span", {"class_": "sl-integrity-heading"},
            raw(_icon("target")),
            h("span", {"class_": "sl-integrity-heading-copy"},
              h("strong", {"class_": "sl-integrity-title"}, t("product_understanding_h")),
              h("span", {"class_": "sl-integrity-summary"}, compact_summary))),
          h("span", {"class_": "sl-integrity-badges"},
            (raw(_label(t("pu_verified_absences_n", n=verified_absences), "var(--green)"))
             if verified_absences else None),
            (raw(_label(t("pu_conflicts_n", n=conflicts), "var(--red)"))
             if conflicts else None))),
        h("div", {"class_": "sl-integrity-body"},
          h("p", {"class_": "sl-integrity-context"}, context),
          (h("details", {"class_": "sl-integrity-nested"},
             h("summary", {}, t("pu_evidenced_n", n=len(known_capabilities))),
             h("ul", {"class_": "sl-integrity-list"},
               fragment(*(capability_row(row) for row in known_capabilities))))
           if known_capabilities else None),
          (h("details", {"class_": "sl-integrity-nested"},
             h("summary", {}, t("pu_open_areas_n", n=len(unknown_capabilities))),
             h("ul", {"class_": "sl-integrity-list"},
               fragment(*(capability_row(row, show_status=False)
                          for row in unknown_capabilities))))
           if unknown_capabilities else None),
          h("details", {"class_": "sl-integrity-nested sl-pu-technical"},
            h("summary", {}, t("pu_technical_details")),
            h("dl", {"class_": "sl-integrity-metrics"}, fragment(*technical_rows))),
        ),
    )


def _project_lineage_html(project: dict, store) -> str:
    predecessor = str(project.get("supersedes_project_id") or "")
    successor = str(project.get("superseded_by_project_id") or "")
    if not (predecessor or successor):
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
    return h("details", {"class_": "sl-project-lineage", "id": "project-lineage",
                         "aria-label": t("lineage_h")},
             h("summary", {}, raw(_icon("link")), t("lineage_h")),
             h("ul", {"class_": "sl-pu-caps"}, fragment(*rows)))


def _project_setup_details_html(project: dict, store) -> str:
    """One quiet project-head-width disclosure for already persisted setup evidence.

    Missing setup belongs to the run chip and its recovery popover.  This block is
    intentionally absent until there is durable evidence worth inspecting.
    """
    product = _product_understanding_html(
        project, store, show_missing=False, embedded=True,
    )
    cohort = render_cohort_integrity(
        project, store, show_missing=False, embedded=True,
    )
    if not (product or cohort):
        return ""
    return h(
        "details",
        {"class_": "sl-project-setup", "id": "research-setup-details"},
        h("summary", {}, raw(_icon("target")), t("research_setup_details_h")),
        h("div", {"class_": "sl-project-setup__body"}, raw(product), raw(cohort)),
    )


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
        run_chip = project_run_chip(proj["id"], store, run_state=health)
        # The graph projection is deliberately lean and does not carry request-boundary
        # attribution. Read the canonical project row for this one presentation field;
        # only its display snapshot is rendered (never the opaque actor id).
        project_record = services.get_research_project(proj["id"], store=store)
        creator = public_creator_projection(project_record.get("created_by")) or {}
        creator_label = str(creator.get("label") or "")
        origin = public_project_client_origin(project_record) or {}
        origin_label = str(origin.get("label") or "")
        creator_text = (
            t("project_created_by_via", label=creator_label, client=origin_label)
            if creator_label and origin_label
            else t("project_created_by", label=creator_label) if creator_label
            else ""
        )
        origin_hint = (
            t("project_created_via_hint", client=origin_label) if origin_label else ""
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
                   (h("p", {
                       "class_": "sl-project-creator",
                       **({"title": origin_hint,
                           "aria-label": f"{creator_text}. {origin_hint}"}
                          if origin_hint else {}),
                   }, creator_text) if creator_label else None),
                   (h("p", {"class_": "sl-project-meta", "data-project-archived": True},
                      t("archive_non_destructive"))
                    if str(project_record.get("status") or "") == "archived" else None),
                   raw(_project_lineage_html(project_record, store)),
                   h("div", {"class_": "pills"}, raw(run_chip)),
                   bar),
                 raw(_project_setup_details_html(project_record, store)),
                 main_view) + raw(project_icon_edit_script())
        # Write affordances (web CRUD, V10 §9): the ONE visible "…" overflow — Edit opens the
        # metadata dialog over the page, Delete the typed-confirm modal. No create buttons
        # (notes/sections/jobs are created by the MCP/CLI host).
        from .edit import project_actions
        archived = str(project_record.get("status") or "active").strip().casefold() == "archived"
        actions = fragment(
            top_btn,
            raw(project_actions(proj)),
            (raw(_star("project", proj["id"], proj["title"], f'/jobs/{proj["id"]}'))
             if not archived else None),
        )
        from .._palette import visit_marker   # the palette's recents beacon (UX V6)
        beacon = visit_marker(proj["title"]) if not archived else ""
        return _layout(proj["title"], body + beacon, store, active="projects",
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
            ("clock", t("created"), ui.local_day(outcome.get("created_at", ""))),
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
