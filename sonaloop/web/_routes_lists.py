"""Index/list-page builders, split out of _routes_pages (spec/component-ssr-architecture.md C5 — keep
route modules small). Each renders rows through the shared _list_page() shell. Markup via h().

The documentation hub (a dedicated multi-page area) lives in its own module, `_docs.py`; this module
just wires its routes in alongside the global Prototypes/Notes lists.
"""
from __future__ import annotations

from fastapi import Request

from .. import config, services
from ..storage import Store
from ._i18n import t
from ._components import _icon, _avatar, _label, _star, _list_page, _layout
from ._project_icons import project_icon_html
from ._pager import _list_filter_box, _page_window, _pager
from ._html import h, raw, fragment, register_css
from ._docs import register_docs


def _row(href: str, ric, title, right=None, *, color: str | None = None, sub=None) -> str:
    """A list row: leading icon/avatar (`ric`), title (+ optional muted `sub`), right-aligned meta."""
    lead = ric if color is None else h("span", {"class_": "rico", "style": f"color:{color}"}, raw(_icon(ric)))
    return h("a", {"class_": "row", "href": href}, lead,
             h("span", {"class_": "title"}, title,
               h("span", {"class_": "muted small"}, f" · {sub}") if sub else None),
             h("span", {"class_": "right"}, right))


def _first_steps_html() -> str:
    """The first-steps checklist shown on the home page while the database is EMPTY
    (ticket one-sentence-mcp-install): install/register → create or load a project →
    run a first council. The inspector running locally proves step 1, so it renders
    checked; the open steps tell the user what to ask their agent. Disappears as soon
    as the first project or persona exists (the normal empty-list states take over)."""
    from .._diagnostics import DOCS_GETTING_STARTED_URL, REGISTER_CLAUDE_CODE

    steps = (
        (True, t("fs_step_install_h"), fragment(t("fs_step_install_d"), " ",
                                                h("code", {}, REGISTER_CLAUDE_CODE))),
        # Creation belongs to the agent (U9, ux-contract §8.4) — the step TELLS, it never links
        # a browser create form (the UI is an inspector: inspect + edit, never create).
        (False, t("fs_step_project_h"), t("fs_step_project_d")),
        (False, t("fs_step_council_h"), t("fs_step_council_d")),
    )
    rows = fragment(*(
        h("div", {"class_": "fsrow" + (" fsdone" if done else "")},
          h("span", {"class_": "fsmark"}, raw(_icon("check" if done else "circle"))),
          h("span", {"class_": "fsbody"}, h("b", {}, head), h("span", {"class_": "muted"}, body)))
        for done, head, body in steps))
    # One-click example projects (ticket loadable-example-projects): POST + 303 via the
    # _forms kit — load lands on the populated project page; removable via remove_example.
    from ._forms import csrf_field
    examples = services.list_examples()
    if not config.product_tour_enabled():
        examples = [e for e in examples if e["slug"] != "onboarding-showcase"]
    example_rows = fragment(*(
        h("form", {"class_": "fsrow fsex", "method": "post",
                   "action": f'/examples/{e["slug"]}/load'},
          raw(csrf_field()),
          h("span", {"class_": "fsmark"}, raw(_icon("projects"))),
          h("span", {"class_": "fsbody"}, h("b", {}, e["title"]),
            h("span", {"class_": "muted"}, e["tagline"])),
          h("button", {"class_": "sl-btn sl-btn--primary", "type": "submit"},
            t("load_example_btn")))
        for e in examples))
    # "Take the tour" sits beside the load-example card in local/single-user mode.
    tour = ""
    if config.product_tour_enabled():
        from ._tour import tour_link
        tour = tour_link("sl-btn")
    return h("div", {"class_": "page"},
             h("h1", {"class_": "h1"}, t("first_steps_h")),
             h("p", {"class_": "lead"}, t("first_steps_lead")),
             h("div", {"class_": "fscard"}, rows),
             h("h2", {"class_": "fsex-h"}, t("fs_example_h")),
             h("p", {"class_": "muted"}, t("fs_example_d")),
             h("div", {"class_": "fscard"}, example_rows),
             h("p", {"style": "margin-top:16px"},
               h("a", {"class_": "sl-btn", "href": DOCS_GETTING_STARTED_URL,
                       "target": "_blank", "rel": "noopener"},
                 raw(_icon("external")), " ", t("fs_docs_link")),
               " ", raw(tour)))


def _projects_page(page: int = 1, q: str = "") -> str:
    """The Projects list — the app's home (project-centric IA). Paginated per the shared
    convention (docs/pagination.md): ?page=N in the URL next to the ?q= filter, ~25 rows
    per page, the h1 count over the FULL filtered set."""
    store = Store()
    # Lean metadata only — NO graph builds for the full list. Enrich only the visible page.
    projects = services.list_research_project_summaries(store=store)
    if q:
        needle = q.strip().casefold()
        projects = [p for p in projects
                    if needle in p.get("title", "").casefold() or needle in p.get("slug", "").casefold()]
    visible, page, pages = _page_window(projects, page)
    # Enrich only the 25 visible rows with graph counts + run state.
    batch = services._research._project_count_batch(store)
    visible = [services._research.enrich_research_project(p, store, _batch=batch) for p in visible]
    rows = []
    for p in visible:
        plan = services.get_plan(p["id"], store=store)

        def _methodology_name() -> str:
            key = (plan or {}).get("methodology") or p.get("methodology") or ""
            if not key:
                return t("plan_freeform")
            try:
                from .. import job_taxonomy as _jt
                return _jt.get_framework_description(key, store).get("name", key)
            except Exception:
                try:
                    return services.get_methodology(key, store=store).get("name", key)
                except Exception:
                    return key

        def _run_label() -> str | None:
            state = (p.get("run_state") or services.project_run_state(p["id"], store=store) or {}).get("state")
            if not state:
                return None
            label = {
                "active": t("runs_active_h"),
                "stalled": t("runs_stalled_h"),
                "finished": t("runs_finished_h"),
            }.get(state, state.replace("_", " ").title())
            color = {
                "active": "var(--green)",
                "stalled": "var(--amber)",
                "finished": "var(--muted)",
            }.get(state, "var(--faint)")
            return _label(f"{t('run_chip')} · {label}", color)

        # the cohort avatar-group (ux-contract §10 W11): the project's persona participation
        # leads the row meta — the ONE anatomy every participation surface renders
        from . import ui
        pids = p.get("persona_ids") or []
        cohort = ui.avatar_group((store.get_persona(x) for x in pids[:4]), total=len(pids))
        meta = fragment(cohort if cohort else None,
                        _label(f'{t("methodology_h")} · {_methodology_name()}', "var(--accent)"),
                        raw(_run_label() or ""),
                        raw(_star("project", p["id"], p["title"], f'/jobs/{p["id"]}')))
        rows.append(_row(f'/jobs/{p["id"]}', raw(project_icon_html(p)), p["title"], meta))
    if not rows and not q and not store.list_personas():
        # Truly fresh database (no projects AND no personas): orient instead of an empty list.
        return _layout(t("first_steps_h"), _first_steps_html(), store,
                       crumbs=[(t("projects"), None)], active="projects")
    # No "New project" affordance (U9, ux-contract §8.4): creation belongs to the MCP/CLI
    # host — the empty state TEACHES the agent verb instead of offering a form.
    # The tour entry lives in the user menu — no second, floating link under the list
    # (round-3 craft: every concept appears in exactly one place, C10).
    return _list_page(store, title=t("projects"), lead=t("projects_lead"), rows=rows,
                      empty_icon="projects", empty_msg=t("no_projects"), active="projects",
                      empty_teach=t("fs_step_project_d"),
                      pre=_list_filter_box("/jobs", q) if (q or pages > 1) else "",
                      count=len(projects), after=_pager("/jobs", page, pages, q))


def _persona_row(p: dict, store: Store) -> str:
    pid = p["id"]
    try:
        proj = services.list_active_projects(pid, store=store)
    except Exception:
        proj = []
    loops = len(store.list_threads(pid, "open"))
    meta = fragment(
        _label(t("n_projects", n=len(proj)), "var(--accent)") if proj else None,
        _label(t("n_open", n=loops), "var(--amber)") if loops else None)
    right = fragment(h("span", {"class_": "muted small"}, p["company_context"]["industry"]), meta,
                     raw(_star("persona", pid, p["display_name"], f"/personas/{pid}")))
    return _row(f'/personas/{pid}', _avatar(p, 22), p["display_name"], right, sub=p["role"]["title"])


def register_lists(app) -> None:
    """Library/index routes that aren't project-scoped: the documentation hub + global Prototypes/Notes."""
    from fastapi.responses import HTMLResponse

    from ._forms import not_found, see_other, write_gate

    register_docs(app)   # /documentation + /documentation/{slug}

    @app.post("/examples/{slug}/load")
    async def example_load(slug: str, request: Request):
        """One-click example load (the empty-DB home affordance): POST + CSRF gate +
        303 to the freshly populated project page. Idempotent like the service call."""
        # The tour's bundled showcase is deliberately unreachable in shared Cloud,
        # including by a stale page or a hand-crafted direct request.  Reject before
        # parsing CSRF or opening a Store so this branch cannot mutate tenant data.
        if slug == "onboarding-showcase" and not config.product_tour_enabled():
            return not_found()
        form = await request.form()
        if (gate := write_gate(form, "load_example", {"slug": slug})) is not None:
            return gate
        try:
            out = services.load_example(slug, store=Store())
        except KeyError:
            return not_found()
        return see_other(out["url"])

    from fastapi import Query

    @app.get("/prototypes", response_class=HTMLResponse)
    def prototypes_list(project: str = Query(default=""), status: str = Query(default=""),
                        subtype: str = Query(default=""), trace: str = Query(default=""),
                        q: str = Query(default="")) -> str:
        # The Library's Prototypes tab under the canonical URL (ux-contract §3.5),
        # filterable by project (U10, the shared FilterBar grammar).
        from .pages.library import library_filters, library_page
        return library_page("prototypes", flt=library_filters(project, status, subtype=subtype, trace=trace),
                            base="/prototypes", q=q)

    @app.get("/notes", response_class=HTMLResponse)
    def notes_list(project: str = Query(default=""), status: str = Query(default=""),
                   subtype: str = Query(default=""), trace: str = Query(default=""),
                   q: str = Query(default="")) -> str:
        # The Library's Notes tab — ONE note entity (concepts merged in).
        from .pages.library import library_filters, library_page
        return library_page("notes", flt=library_filters(project, status, subtype=subtype, trace=trace),
                            base="/notes", q=q)

# Co-located CSS (spec/roadmap.md R3): the shared linear list rows used by every index page.
register_css(r"""
/* ---- linear list rows (G3) ---- */
.group{margin:16px 0 2px;display:flex;align-items:center;gap:8px;font-size:var(--t-sm);color:var(--muted);font-weight:600}
.group .cnt{color:var(--muted);font-weight:500}
.rows{border:0;border-top:1px solid var(--line-2);background:transparent}
.row{display:flex;align-items:center;gap:12px;padding:8px 12px;border-bottom:1px solid var(--line-2);min-height:40px;border-radius:var(--radius-sm);transition:background 110ms}
.row:last-child{border-bottom:0}.row:hover{background:var(--hover)}
.row>svg.ic,.row>.ic{color:var(--faint);flex-shrink:0;width:16px;height:16px}.row:hover>svg.ic{color:var(--muted)}
.rico{display:inline-flex;align-items:center;justify-content:center;flex-shrink:0;width:24px;height:24px;border-radius:var(--radius-sm);background:var(--panel-2)}
.rico svg{width:15px;height:15px}
.h1cnt{font-size:var(--t-body);font-weight:500;color:var(--faint);margin-left:8px;vertical-align:middle}
.list-empty{display:flex;flex-direction:column;align-items:center;gap:8px;padding:48px 0;color:var(--muted);text-align:center}.list-empty svg{width:26px;height:26px;color:var(--faint)}
.row .title{font-weight:500;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1;min-width:0}
.row .sub{color:var(--muted);font-size:var(--t-sm);flex-shrink:0}
.row .right{display:flex;align-items:center;gap:8px;flex-shrink:0;color:var(--faint);font-size:var(--t-sm)}
.votebar{display:inline-flex;height:6px;width:88px;border-radius:3px;overflow:hidden;border:1px solid var(--line)}
.votebar i{display:block;height:100%}
/* ---- first-steps checklist (empty-DB home; ticket one-sentence-mcp-install) ---- */
.fscard{border:1px solid var(--line);border-radius:var(--radius);background:var(--panel);max-width:640px}
.fsrow{display:flex;gap:12px;padding:16px;border-bottom:1px solid var(--line-2);align-items:flex-start}
.fsrow:last-child{border-bottom:0}
.fsmark{flex-shrink:0;display:inline-flex;align-items:center;justify-content:center;width:22px;height:22px;border-radius:50%;background:var(--panel-2);color:var(--faint)}
.fsmark svg{width:14px;height:14px}
.fsdone .fsmark{color:var(--green,#34a853)}
.fsbody{display:flex;flex-direction:column;gap:2px;min-width:0}
.fsbody code{font-size:var(--t-sm);word-break:break-all}
.fsex-h{font-size:var(--t-md);margin:24px 0 4px}
.fsex{margin:0}
.fsex .sl-btn{flex-shrink:0;align-self:center;margin-left:auto}
""")
