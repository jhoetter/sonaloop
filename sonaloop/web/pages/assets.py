"""Assets as a first-class surface (UX U8, spec/ux-contract.md §8.3): which input files the
project RECEIVED (evidence in — possibly across many MCP messages over time) and which documents
the software GENERATED (deliverables out — possibly several versions, the supersede chain).

Three routes on the shared anatomy, zero new presentation:
  - /assets             — the Library's Assets tab (cross-project rows, §3.5).
  - /assets/{id}        — the asset detail page (U7 scaffold: preview / file card, provenance
                          block, properties rail). GLOBAL id resolution across projects, like
                          every other kind's detail route (get_asset is project-scoped, so the
                          lookup scans the project records — assets ride the project JSON blob).
  - /projects/{id}?view=files — the project FILES lens (project_files_page, dispatched by the
                          project route): ALL of the project's assets chronologically, in + out
                          interleaved with day separators — the across-many-messages story,
                          reachable from the project header's "N files" chip.

The shared pill/size/source-chip/preview renderers live in web/_presence (the house pattern);
rows are ui.primitive_row, so the slide-over (§8.1) works from every surface."""
from __future__ import annotations

from ._ctx import *  # noqa: F401,F403  (shared render toolkit)
from .. import ui
from .._presence import (
    asset_direction, asset_direction_pill, asset_file_card, asset_kind_pill,
    asset_preview_html, asset_source_chip, file_card,
)


def find_asset(store, asset_id: str) -> tuple[dict | None, dict | None]:
    """(project, asset) for an asset id (or filename) resolved ACROSS projects — the global
    /assets/{id} route's lookup. Returns (None, None) when nothing matches."""
    for proj in store.list_research_projects():
        for a in proj.get("assets") or []:
            if a.get("id") == asset_id or a.get("filename") == asset_id:
                return proj, a
    return None, None


def _provenance_section(a: dict, store) -> str:
    """The PROVENANCE block (§8.3): received/generated timestamp · source resolved as a chip ·
    the supersede chain when recorded · notes — the sl-props row contract, so provenance reads
    like structure, not prose. The Generated/Received verb already states the direction; the
    header pill is the page's ONE direction encoding (round-4 J2: no repeats)."""
    is_out = asset_direction(a) == "out"
    when = ui.fmt_ts(a.get("created_at") or "")
    chain = a.get("supersedes") or []
    chain_html = fragment(*(
        h("div", {"class_": "muted small"},
          f'{s.get("filename", "") or s.get("id", "")} · {ui.fmt_ts(s.get("created_at") or "")}')
        for s in chain)) if chain else None
    rows = [
        ("dot", t("asset_generated") if is_out else t("asset_received"), when),
        ("link", t("asset_source"), raw(asset_source_chip(a, store))),
        ("download", t("asset_supersedes"), chain_html),
        ("panel", t("notes_h"), a.get("notes", "")),
    ]
    props = [h("div", {"class_": "sl-prop"},
               h("span", {"class_": "sl-prop__k"}, raw(_icon(ic)), lbl),
               h("span", {"class_": "sl-prop__v"}, val))
             for ic, lbl, val in rows if val not in (None, "", "—")]
    # The same .sec/h2 heading idiom as the page's other sections (sec-file, sec-excerpt);
    # the rows ride the QUIET frameless props contract (V9: the file card is the hero,
    # provenance reads as quiet structure below it).
    return h("div", {"class_": "sec", "id": "sec-provenance"},
             h("h2", {}, t("provenance_h")),
             h("div", {"class_": "sl-props sl-props--quiet"}, fragment(*props)))


def project_files_page(project_id: str) -> str:
    """The project FILES lens (?view=files): every asset of the project chronologically as
    FILE CARDS (ux-contract §9 V9 — the `.sl-file-grid` of `.sl-file` cards: type identity
    first, filename+ext as the title, size · date meta, direction pill, the quiet source
    chip; exactly ONE download/open affordance — the card body opens the detail/slide-over).
    Evidence in and deliverables out interleave by created_at; day separators stay as grid
    section headers. The across-many-MCP-messages story (§8.3)."""
    store = Store()
    try:
        proj = services.get_research_project(project_id, store=store)
    except KeyError:
        return _layout(t("not_found"), _empty_state(t("not_found"), t("runtime_maybe_cleared"), icon="projects"),
                       store, active="projects")
    assets = sorted(services.list_assets(project_id, store=store),
                    key=lambda a: a.get("created_at", ""))
    sections: list = []
    day, cards = None, []
    for a in assets:
        if (a.get("created_at") or "")[:10] != day:
            if cards:
                sections.append(h("div", {"class_": "sl-file-grid"}, fragment(*(raw(str(c)) for c in cards))))
            day, cards = (a.get("created_at") or "")[:10], []
            sections.append(ui.group_header(ui._fmt_day(day)))
        cards.append(file_card(a, store, drawer=True, source=True))
    if cards:
        sections.append(h("div", {"class_": "sl-file-grid"}, fragment(*(raw(str(c)) for c in cards))))
    if sections:
        rows_html = h("div", {"class_": "rows", "data-keynav": True},
                      fragment(*(raw(str(s)) for s in sections)))
    else:
        rows_html = h("div", {"class_": "sl-empty"},
                      h("div", {"class_": "sl-empty__icon"}, raw(_icon("clipboard"))),
                      h("h2", {"class_": "sl-empty__title"}, t("no_assets")),
                      h("p", {"class_": "sl-empty__body"}, t("assets_teach")))
    body = h("div", {"class_": "page"},
             h("h1", {"class_": "h1"}, t("files_h"),
               h("span", {"class_": "h1cnt"}, str(len(assets))) if assets else None),
             h("p", {"class_": "lead"}, t("files_lead")),
             rows_html)
    return _layout(f'{proj["title"]} — {t("files_h")}', body, store, active="projects",
                   crumbs=[(t("projects"), "/projects"), (proj["title"], f'/projects/{project_id}'),
                           (t("files_h"), None)])


def register_assets(app) -> None:
    @app.get("/assets", response_class=HTMLResponse)
    def assets_list(project: str = Query(default=""), status: str = Query(default=""),
                    direction: str = Query(default=""), subtype: str = Query(default=""),
                    q: str = Query(default="")) -> str:
        # The Library's Assets tab under the canonical URL (ux-contract §3.5), with the
        # shared FilterBar (U10): project + status + direction, same URL grammar.
        from .library import library_filters, library_page
        return library_page("assets", flt=library_filters(project, status, direction, subtype),
                            base="/assets", q=q)

    @app.get("/assets/{asset_id}", response_class=HTMLResponse)
    def asset_detail(asset_id: str) -> str:
        """An asset's REAL detail page (UX U8 — the U7 anatomy): ASSET eyebrow + kind/direction
        pills, image preview / file card with download, the text excerpt for documents, the
        PROVENANCE block (when received/generated, source chip, supersede chain, notes), and
        the properties rail (project · files lens · created).

        Round-4 J2 (ux-audit): the page reads ONCE top to bottom — filename, size and
        mimetype live only on the file card (no H1 sub line), the rail carries no
        Type/Direction/Size rows (the header pills + the card state them), and the card
        drops its extension-badge stage when the real first-page preview leads the page."""
        store = Store()
        proj, a = find_asset(store, asset_id)
        if a is None:
            return _layout(t("not_found"),
                           _empty_state(t("assets_h"), t("runtime_maybe_cleared"), icon="clipboard"),
                           store, active="library")
        title = a.get("title") or a.get("filename", "")
        excerpt = (a.get("text_excerpt") or "").strip()
        preview = asset_preview_html(a)
        body = fragment(
            raw(preview),
            h("div", {"class_": "sec", "id": "sec-file"},
              raw(asset_file_card(a, stage=not preview))),
            (h("div", {"class_": "sec", "id": "sec-excerpt"},
               h("h2", {}, t("asset_excerpt_h")),
               ui.clamp(excerpt, threshold=ui.SECTION_CLAMP)) if excerpt else None),
            raw(_provenance_section(a, store)))
        proj_link = h("a", {"href": f'/projects/{proj["id"]}'}, proj["title"])
        n_proj_files = len(proj.get("assets") or [])
        files_link = h("a", {"href": f'/projects/{proj["id"]}?view=files'},
                       t("one_file") if n_proj_files == 1 else t("n_files", n=n_proj_files))
        prop_rows = [
            ("projects", t("project"), proj_link),
            ("file", t("files_h"), files_link),
            ("dot", t("created"), ui.fmt_date(a.get("created_at") or "")),
        ]
        return detail_page(
            store, title=title, active="projects",   # G5: an asset always lives on a project
            # Project-rooted crumb (§8.2 — the council pattern; an asset always has a project).
            crumbs=[(t("projects"), "/projects"), (proj["title"], f'/projects/{proj["id"]}'),
                    (title, None)],
            icon="file", kind=t("asset_kind"),
            pills=[asset_kind_pill(a), asset_direction_pill(a)],
            body=body, prop_rows=prop_rows,
            rail_sections=([("sec-excerpt", t("asset_excerpt_h"))] if excerpt else [])
                          + [("sec-provenance", t("provenance_h"))],
            star=("asset", a["id"], title[:60], f'/assets/{a["id"]}'))
