"""Report pages: list + detail + stakeholder deliverable download.

A report IS a synthesis — one concept, short or exhaustive. Internally
scope=convergence renders the structured view (findings → 2×2) and scope=project
the narrative sections + figures; one detail route serves both. Report export is
an ordinary inspection action: the same stored report is typeset as a concise PDF
or editable PowerPoint and attached back to its project as an outgoing asset.
"""
from __future__ import annotations

from fastapi import Request
from fastapi.responses import RedirectResponse

from ._ctx import *  # noqa: F401,F403  (shared render toolkit)
from .._keymap import sibling_attrs, sibling_urls
from .._render import _refs_line, render_claim_posture_notice
from .._report import render_report
from .._cohort_integrity_view import render_cohort_integrity
from .._html import register_css


register_css(".sl-export-form{display:inline-flex;margin:0}")


def _informed_decisions_html(synthesis_id: str, store) -> str:
    """The reverse edge of a decision's based_on/rejected refs: the decisions THIS synthesis
    informed, as chips deep-linking into the project's decisions section (ticket
    decision-record-artifact). Empty when nothing cites the synthesis."""
    informed = [d for d in store.list_decisions()
                if any(r.get("kind") == ("synth" + "esis") and r.get("id") == synthesis_id
                       for r in (d.get("based_on") or []) + (d.get("rejected") or []))]
    if not informed:
        return ""
    return _refs_line([{"kind": "decision", "id": d["id"]} for d in informed],
                      t("dec_informed_h"), store)


def register_syntheses(app) -> None:
    @app.get("/syntheses", response_class=HTMLResponse)
    def syntheses(project: str = Query(default=""), status: str = Query(default=""),
                  subtype: str = Query(default=""), trace: str = Query(default=""),
                  q: str = Query(default="")) -> str:
        # ONE concept — a Report; the list is the Library's Reports tab (ux-contract §3.5),
        # filterable by project (U10, the shared FilterBar grammar).
        from .library import library_filters, library_page
        return library_page("reports", flt=library_filters(project, status, subtype=subtype, trace=trace),
                            base="/syntheses", q=q)

    @app.get("/syntheses/{synthesis_id}", response_class=HTMLResponse)
    def synthesis_detail(synthesis_id: str) -> str:
        store = Store()
        syn = store.get_synthesis(synthesis_id)
        if not syn:
            return _layout(t("not_found"), _empty_state(t("synthesis_not_found"), t("runtime_maybe_cleared"), icon="syntheses"), store, active="library")
        # ONE renderer for every scope (spec/unified-synthesis-report.md §3): the report shell — a
        # convergence synthesis shows its structured analysis (findings → 2×2, voices), a project report
        # its narrative sections; both report-grade + PDF-exportable.
        is_project = syn.get("scope") == "project"
        proj = (store.get_research_project(syn.get("project_id")) if (is_project and syn.get("project_id"))
                else services.parent_project_of_synthesis(synthesis_id, store))
        if proj:
            # Reverse lookup returns lean breadcrumb metadata; evidence-health
            # needs the tenant-authorized full Product Understanding versions.
            proj = store.get_research_project(proj["id"]) or proj
        short_title = _display_title(syn["title"])
        crumbs = [(t("projects"), "/jobs")]
        if proj:
            crumbs.append((proj["title"], f"/jobs/{proj['id']}"))
        crumbs.append((short_title, None))
        # One renderer, plus the section list → the right-edge scrollspy rail (§3.6c): the
        # report's structure stays navigable even when the clamped prose sections are short.
        report_html, toc = render_report(syn, store, with_toc=True)
        from .projects import _product_understanding_html
        body = fragment(raw(render_claim_posture_notice(syn, store)),
                        raw(_product_understanding_html(proj or {}, store)),
                        raw(render_cohort_integrity(proj or {}, store)), raw(report_html),
                        raw(_informed_decisions_html(synthesis_id, store)),
                        # server-provided prev/next sibling URLs for the keymap's [ / ] bindings
                        raw(sibling_attrs(*sibling_urls(
                            [f'/syntheses/{x["id"]}' for x in store.list_syntheses()],
                            f'/syntheses/{synthesis_id}'))))
        # The shared detail scaffold (UX U7, §8.2): the report shell keeps its own cover (the
        # REPORT eyebrow + title + meta line ARE the header anatomy), detail_page adds what the
        # page was missing — the properties rail (project, sources, dates) beside the document.
        proj_link = (h("a", {"href": f'/jobs/{proj["id"]}'}, proj["title"]) if proj else "")
        n_sources = (len({x for sec in syn.get("sections") or [] for x in sec.get("source_study_ids", [])})
                     if is_project else len(syn.get("council_ids") or []))
        # Rail order is the §8.2 anatomy (project → kind-specifics → dates); no "Type: Report"
        # row — the cover's REPORT eyebrow already states the kind (round-2 audit, TX).
        prop_rows = [
            ("projects", t("project"), proj_link),
            *detail_form_rows("synthesis", syn),
            ("link", t("rel_based_on"), raw(_label(t("chip_sources_n", n=n_sources)))),
            ("clock", t("created"), ui.local_date(syn.get("created_at") or "")),
        ]
        from .._forms import csrf_field, overflow_delete
        def export_form(fmt: str, label: str, quiet: bool = False) -> str:
            return h(
                "form", {"class_": "sl-export-form", "method": "post",
                         "action": f"/syntheses/{synthesis_id}/export/{fmt}"},
                raw(csrf_field()),
                h("button", {"class_": "sl-btn" + (" sl-btn--quiet" if quiet else ""),
                             "type": "submit", "title": label},
                  raw(_icon("download")), " ", label))
        export_actions = fragment(
            export_form("pdf", t("export_pdf")),
            export_form("pptx", t("export_pptx"), quiet=True),
            raw(overflow_delete(f'/syntheses/{synthesis_id}/delete', t("delete_synthesis"))),
        )
        return detail_page(
            store, title=short_title, crumbs=crumbs,
            # G5: sidebar active follows the crumb root (project-rooted → Projects)
            active="projects" if proj else "library",
            hero="", body=body, prop_rows=prop_rows,
            rel_study_id=(f"report:{synthesis_id}" if is_project
                          else f"synthesis:{synthesis_id}"),
            rel_proj_id=(proj["id"] if proj else None),
            rel_include_in=not bool(syn.get("council_ids")),
            rail_sections=toc,
            star=("synthesis", synthesis_id, short_title, f"/syntheses/{synthesis_id}"),
            actions=export_actions)

    @app.post("/syntheses/{synthesis_id}/export/{fmt}", include_in_schema=False)
    async def synthesis_export(synthesis_id: str, fmt: str, request: Request):
        """Create a presentation-ready hand-off and immediately download it.

        The page deliberately defaults PDF to the stakeholder audience: every
        section remains represented, while citations and long prose stay in the
        inspectable report. PPTX already uses the concise slide budget.
        """
        fmt = str(fmt or "").lower()
        if fmt not in {"pdf", "pptx"}:
            return HTMLResponse(t("not_found"), status_code=404)
        store = Store()
        syn = store.get_synthesis(synthesis_id)
        if not syn:
            return HTMLResponse(t("synthesis_not_found"), status_code=404)
        form = await request.form()
        from .._forms import write_gate
        if (gate := write_gate(
                form, "export_synthesis",
                {"synthesis_id": synthesis_id, "project_id": syn.get("project_id") or "",
                 "format": fmt})) is not None:
            return gate
        try:
            from .._ext import export_synthesis_deliverable
            result = export_synthesis_deliverable(
                synthesis_id, fmt, store=store,
                audience="stakeholder" if fmt == "pdf" else "presentation")
        except (KeyError, RuntimeError, ValueError):
            return HTMLResponse(
                _layout(t("export_failed"), _empty_state(
                    t("export_failed"), t("runtime_maybe_cleared"), icon="download"),
                    store, active="library"), status_code=500)
        target = (f'/assets/{result["asset_id"]}/content'
                  if result.get("asset_id") else str(result.get("url") or ""))
        if not target:
            return HTMLResponse(t("export_failed"), status_code=500)
        return RedirectResponse(target, status_code=303)
