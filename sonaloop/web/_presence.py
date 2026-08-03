"""Project presence CONTRACT — nothing project-scoped is invisible on the DEFAULT project page
(tracker: sonaloop/project-presence-contract, user decision 2026-06-10).

Two declared layers, enforced by the gate test (tests/test_project_presence_contract.py, the
house pattern of the chip contract / LOC budget / i18n parity):

  - REGISTRY: every core artifact kind that carries a `project_id` declares WHERE it shows on
    the default project page — one of OUTLINE_ROW, NESTED_CHILD, SECTION_WITH_HEADER_CHIP, or
    (later, by explicit user decision only) HIDDEN_WITH_REASON. ALLOWED_HIDDEN is EMPTY: right
    now NO kind may register hidden.
  - LIST_SOURCES: every `list_*(project_id=…)` function on the services/storage surface maps to
    its registered kind — or to an explicit NotAnArtifact sentinel naming WHY that listing
    carries no artifact kind (so the mapping stays an inventory, not a loophole). The gate
    enumerates the surface (project_scoped_list_functions) and fails on an unmapped function:
    a new project-scoped artifact kind cannot ship without declaring where it shows.

presence_violations() is the single check the gate asserts empty.

Since UX P2 (spec/ux-contract.md §3.4) every kind is an OUTLINE ROW in its phase context — the
tier-3 appendix sections + header jump-chips retired (the row items are built by
web/_graph_outline_extras). The module keeps the SHARED pill/row renderers (survey lifecycle,
decision + hypothesis status pills, asset rows) used by the outline chips, the detail pages and the
cross-project list pages alike."""
from __future__ import annotations

import inspect

from ._components import _icon, _label
from ._html import fragment, h, raw, register_css
from ._i18n import t

# ------------------------------------------------------------------ the presence declarations

OUTLINE_ROW = "outline_row"                          # a row in the round-grouped outline
NESTED_CHILD = "nested_child"                        # an indented child row under its parent
SECTION_WITH_HEADER_CHIP = "section_with_header_chip"  # an anchored section + header jump-chip
HIDDEN_WITH_REASON = "hidden_with_reason"            # forbidden today (ALLOWED_HIDDEN is empty)
PRESENCES = (OUTLINE_ROW, NESTED_CHILD, SECTION_WITH_HEADER_CHIP, HIDDEN_WITH_REASON)

# Kinds permitted to register hidden. EMPTY by user decision (2026-06-10): the user is mapping
# the product's flows and must not miss an artifact — adding a kind here requires an explicit
# user decision recorded on the tracker, never a layout convenience.
ALLOWED_HIDDEN: frozenset[str] = frozenset()


class Declared:
    """One kind's declared presence on the default project page: the presence class + a `where`
    note naming the concrete affordance that carries it (so the registry reads as a map of the
    page, not a checkbox)."""

    def __init__(self, presence: str, where: str, reason: str = ""):
        self.presence, self.where, self.reason = presence, where, reason


class NotAnArtifact:
    """Explicit 'this project-scoped listing is no artifact kind' declaration, with the reason
    (what the records are and which affordance carries their signal instead)."""

    def __init__(self, reason: str):
        self.reason = reason


REGISTRY: dict[str, Declared] = {
    "council": Declared(OUTLINE_ROW, "a plan-graph node row in the round-grouped outline"),
    "synthesis": Declared(OUTLINE_ROW, "a plan-graph node row in the round-grouped outline"),
    "report": Declared(OUTLINE_ROW, "an inline outline row at the end of its round (po=99)"),
    "note": Declared(OUTLINE_ROW, "an observation/concept row; a built concept pairs its prototype beneath"),
    "prototype": Declared(OUTLINE_ROW, "a standalone row, or nested under the concept note that realises it"),
    "url_artifact": Declared(OUTLINE_ROW, "an artifact-style row with the A/B label + capture-status chips"),
    "session": Declared(OUTLINE_ROW, "a session row; prototype sessions may be indented under the prototype"),
    "section": Declared(OUTLINE_ROW, "the theme filter bar + phase/round groupings OVER the outline "
                                     "(an overlay grouping of nodes, not a row of its own)"),
    "hypothesis": Declared(OUTLINE_ROW, "a row (status pill) in the phase active at created_at; "
                                        "anchor #hyp-{id} keeps the /hypotheses/{id} deep link"),
    "decision": Declared(OUTLINE_ROW, "a row in the phase whose gate judgment cites it / whose verify "
                                      "task produced it; anchor #dec-{id} keeps the deep link"),
    "open_question": Declared(OUTLINE_ROW, "a row (open/resolved pill) in the phase active at created_at"),
    "asset": Declared(OUTLINE_ROW, "deliverables (direction out) in the final Deliver group; incoming "
                                   "assets in their phase's Assets sub-group (ux-contract §7.2)"),
    "survey": Declared(OUTLINE_ROW, "a row (lifecycle pill, question/response counts) under the phase "
                                    "of the act task that produced it; links to /surveys/{id}"),
}

# Every list_*(project_id=…) family on the services/storage surface → its registered kind.
# Councils/syntheses have no such family (they ride the plan graph) but are registered above —
# the gate asserts the full core-kind inventory separately.
LIST_SOURCES: dict[str, str | NotAnArtifact] = {
    # the services surface
    "list_artifacts": "url_artifact",
    "list_assets": "asset",
    "list_decisions": "decision",
    "list_flows": NotAnArtifact(
        "session test-script definition, not a product artifact — surfaced through the sessions that use it"),
    "list_hypotheses": "hypothesis",
    # ideas ARE note records (kind 'idea' on the note primitive — services/_ideation.py);
    # list_ideas is a filtered view over list_notes, so their presence rides the note kind.
    "list_ideas": "note",
    "list_notes": "note",
    "list_prototypes_artifacts": "prototype",
    "list_sections": "section",
    "list_surveys": "survey",
    "list_usability_sessions": "session",
    # the storage-only surface
    "list_open_questions": "open_question",
    "list_prototypes": "prototype",
    "list_reports": "report",
    # engine/meta RECORDS, not artifact kinds — each names why and what carries the signal:
    "list_runs": NotAnArtifact(
        "engine run STATE, not an artifact — its products (councils/syntheses/reports) are the "
        "registered kinds; the pulse/stalled strip reads it"),
    "list_methodology_judgments": NotAnArtifact(
        "plan-engine gate metadata riding its verify task — surfaced through the synthesis that "
        "convergence produced, not a standalone artifact"),
    "list_prediction_outcomes": NotAnArtifact(
        "calibration-ledger rows scored against reality — surfaced via calibration_report/"
        "calibration_trend, not project-page artifacts"),
}


def project_scoped_list_functions() -> set[str]:
    """The enumerable surface the gate sweeps: every `list_*` callable on the services package
    and on storage.Store whose signature carries `project_id`. A NEW project-scoped artifact
    kind necessarily extends this family — and then fails the gate until LIST_SOURCES +
    REGISTRY declare it."""
    from .. import services
    from ..storage import Store
    names: set[str] = set()
    for name in dir(services):
        if not name.startswith("list_"):
            continue
        fn = getattr(services, name)
        if not callable(fn):
            continue
        try:
            params = inspect.signature(fn).parameters
        except (TypeError, ValueError):
            continue
        if "project_id" in params:
            names.add(name)
    for name, fn in inspect.getmembers(Store, predicate=inspect.isfunction):
        if name.startswith("list_") and "project_id" in inspect.signature(fn).parameters:
            names.add(name)
    return names


def presence_violations() -> list[str]:
    """Every way the contract can be broken, as human-readable findings (the gate asserts this
    empty): an unmapped list function, a stale mapping, a kind without a declaration, a missing
    `where`/reason, an unknown presence value, or a hidden registration outside ALLOWED_HIDDEN."""
    out: list[str] = []
    surface = project_scoped_list_functions()
    for name in sorted(surface - set(LIST_SOURCES)):
        out.append(f"{name}(project_id=…) is on the surface but unmapped in LIST_SOURCES — declare "
                   "its kind's project-page presence (or an explicit NotAnArtifact reason)")
    for name in sorted(set(LIST_SOURCES) - surface):
        out.append(f"LIST_SOURCES maps {name}() which is no longer on the surface — drop the stale entry")
    for name, target in LIST_SOURCES.items():
        if isinstance(target, NotAnArtifact):
            if not target.reason:
                out.append(f"NotAnArtifact for {name}() must carry a reason")
            continue
        if target not in REGISTRY:
            out.append(f"kind {target!r} (listed by {name}) has no presence declaration in REGISTRY")
    for kind, d in REGISTRY.items():
        if d.presence not in PRESENCES:
            out.append(f"kind {kind!r} declares an unknown presence {d.presence!r}")
        if not d.where:
            out.append(f"kind {kind!r} must name WHERE it shows on the default project page")
        if d.presence == HIDDEN_WITH_REASON and kind not in ALLOWED_HIDDEN:
            out.append(f"kind {kind!r} registers hidden — forbidden (user decision 2026-06-10: "
                       "nothing project-scoped is invisible on the default project page)")
    return out


# ------------------------------------------------- shared per-kind pill / row renderers


def synthesis_status_pill(status: str) -> str:
    """Report lifecycle pill (ux-contract §10 W10 / audit G2 — the one kind that carried its
    lifecycle only as meta text): done (green) or in progress (amber). Shared by the report
    rows, the report cover's eyebrow line and the Library status facet."""
    pills = {"done": (t("syn_status_done"), "var(--green)"),
             "in_progress": (t("syn_status_in_progress"), "var(--amber)")}
    label, color = pills.get(status, pills["done"])
    return _label(label, color)


def synthesis_status_label(status: str) -> str:
    return t("syn_status_in_progress") if status == "in_progress" else t("syn_status_done")


def survey_status_pill(status: str) -> str:
    """Survey lifecycle pill (a lifecycle, not a vocabulary). Resolved per request so the labels
    follow the active UI language. Shared by the survey pages and the outline chips."""
    pills = {"draft": (t("survey_status_draft"), "var(--muted)"),
             "open": (t("survey_status_open"), "var(--green)"),
             "closed": (t("survey_status_closed"), "var(--violet)")}
    label, color = pills.get(status, pills["draft"])
    return _label(label, color)


# Decision / hypothesis lifecycle pill colors (lifecycles, not vocabularies — labels are i18n
# keys resolved per request). Shared by the outline chips, the detail pages, the project rows and the
# cross-project /decisions + /hypotheses lists, so a status reads identically everywhere.
_DEC_STATUS_COLORS = {"proposed": "var(--accent)", "adopted": "var(--green)",
                      "superseded": "var(--muted)"}
HYP_STATUS_COLORS = {"open": "var(--accent)", "validated": "var(--green)", "refuted": "var(--red)",
                     "inconclusive": "var(--amber)", "dropped": "var(--muted)"}


def decision_status_label(status: str) -> str:
    labels = {"proposed": t("dec_status_proposed"), "adopted": t("dec_status_adopted"),
              "superseded": t("dec_status_superseded")}
    return labels.get(status, status)


def decision_status_pill(status: str) -> str:
    return _label(decision_status_label(status), _DEC_STATUS_COLORS.get(status, "var(--muted)"))


def hypothesis_status_label(status: str) -> str:
    labels = {"open": t("hyp_status_open"), "validated": t("hyp_status_validated"),
              "refuted": t("hyp_status_refuted"), "inconclusive": t("hyp_status_inconclusive"),
              "dropped": t("hyp_status_dropped")}
    return labels.get(status, status)


def hypothesis_status_pill(status: str) -> str:
    return _label(hypothesis_status_label(status), HYP_STATUS_COLORS.get(status, "var(--muted)"))


def open_question_status_pill(status: str) -> str:
    """Open questions are a two-state lifecycle: open (amber — work to do) or resolved (muted)."""
    if status == "open":
        return _label(t("oq_status_open"), "var(--amber)")
    return _label(t("oq_status_resolved"), "var(--muted)")


def record_status(kind: str, rec: dict) -> str:
    """The honest status a record ACTUALLY carries — the U10 filter facet's value extractor
    (ux-contract §8.5: no dead options, no invented lifecycle). Kinds without a lifecycle
    (councils, notes, prototypes, assets) return "" and simply don't fill the facet.
    Sessions read their grounding (verified against real observed usage or not)."""
    if kind in ("decision",):
        return rec.get("status") or "proposed"
    if kind in ("synthesis", "report"):       # G2: reports DO carry one (in_progress | done)
        return rec.get("status") or "done"
    if kind in ("hypothesis",):
        return rec.get("status") or "open"
    if kind in ("survey",):
        return rec.get("status") or "draft"
    if kind in ("open_question",):
        return "open" if (rec.get("status") or "open") == "open" else "resolved"
    if kind in ("session",):
        return "verified" if rec.get("grounded_verified") else "unverified"
    return ""


def status_filter_label(kind: str, status: str) -> str:
    """The display label for a record_status value — the SAME words the kind's status pill
    shows, so the filter menu and the rows always agree."""
    if kind in ("decision",):
        return decision_status_label(status)
    if kind in ("synthesis", "report"):
        return synthesis_status_label(status)
    if kind in ("hypothesis",):
        return hypothesis_status_label(status)
    if kind in ("survey",):
        labels = {"draft": t("survey_status_draft"), "open": t("survey_status_open"),
                  "closed": t("survey_status_closed")}
        return labels.get(status, status)
    if kind in ("open_question",):
        return t("oq_status_open") if status == "open" else t("oq_status_resolved")
    if kind in ("session",):
        return t("grounded_yes") if status == "verified" else t("grounded_no")
    return status


def asset_direction(asset: dict) -> str:
    """An asset record's flow direction: `out` (deliverable produced from the project) or `in`
    (evidence brought into it). Direction-less records predate the field and ARE evidence —
    back-compat without a migration (ticket project-assets-direction-deliverables-page-section)."""
    return "out" if asset.get("direction") == "out" else "in"


def asset_kind_pill(asset: dict) -> str:
    """The asset's kind pill (image/screenshot/document/file) — one label everywhere (§3.2)."""
    return _label(t("asset_kind_" + (asset.get("kind") or "file")))


def asset_direction_pill(asset: dict) -> str:
    """The asset's direction pill: deliverable out (green) vs evidence in (quiet) — shared by the
    outline chips, primitive_row, the asset detail page and the asset library surface (UX U8)."""
    return (_label(t("asset_dir_out"), "var(--green)") if asset_direction(asset) == "out"
            else _label(t("asset_dir_in")))


def asset_size(asset: dict) -> str:
    """'12 KB' — a unit, not a UI string; the one size format every asset surface shows."""
    return f'{max(1, int(asset.get("bytes") or 0) // 1024)} KB'


def asset_source_chip(asset: dict, store=None) -> str:
    """The asset's PROVENANCE source as a chip (UX U8 §8.3): a record-pointing source
    ('synthesis:<id>' / 'prototype:<id>' — the part_address format) resolves LIVE through
    render_ref (current title, deep link, honest broken state); a free source (the attach-time
    file path, an MCP note) renders as quiet text — honest, never invented. Empty source → ''."""
    source = asset.get("source") or ""
    if ":" in source:
        from .. import artifacts as _A
        from ._render import render_ref
        ref = _A.parse_address(source)
        if ref.get("id") and _A.ref_href(ref):
            return render_ref(ref, store)
    return h("span", {"class_": "muted small"}, source) if source else ""


# Co-located CSS for the U8 asset-detail content blocks (the house pattern: shared asset
# renderers live HERE, used by the detail page and asset rows alike).
register_css(".assetprev{margin:6px 0 18px}"
             ".assetprev img{max-width:100%;border:1px solid var(--line);border-radius:var(--radius);display:block}")


def asset_content_url(asset: dict, *, preview: bool = False) -> str:
    """Return the browser URL for an asset binary.

    Local SQLite keeps the historical ``/data`` mount.  A shared Postgres
    deployment must never put a workspace path in an ``img``/download URL: that
    mount is intentionally blocked because filesystem paths have no RLS.  Its
    authenticated asset route resolves the opaque asset id inside the active
    workspace instead.  Deriving this at render time also repairs records that
    predate that route without a data migration.
    """
    from urllib.parse import quote

    from .. import config

    if config.postgres_row_tenancy_enabled() and asset.get("id"):
        variant = "preview" if preview else "content"
        return f'/assets/{quote(str(asset["id"]), safe="")}/{variant}'
    return str(asset.get("preview_url") if preview else asset.get("url") or "")


def asset_preview_html(asset: dict) -> str:
    """The detail page's content lead (UX U8): image assets render a full-width preview from the
    static /data mount; documents with a first-page render (W6 `preview_url`) show their title
    page the same way (no link — the file card below is the ONE download affordance, V9); other
    kinds render nothing here (the file card carries the download)."""
    if asset.get("kind") in ("image", "screenshot") and asset.get("url"):
        url = asset_content_url(asset)
        return h("div", {"class_": "assetprev"},
                 h("a", {"href": url, "target": "_blank", "rel": "noopener"},
                   h("img", {"src": url, "alt": asset.get("title") or asset.get("filename", ""),
                             "loading": "lazy"})))
    if asset.get("preview_url"):
        preview_url = asset_content_url(asset, preview=True)
        return h("div", {"class_": "assetprev"},
                 h("img", {"src": preview_url,
                           "alt": asset.get("title") or asset.get("filename", ""), "loading": "lazy"}))
    return ""


# ── V9: the file-first asset presentation (ux-contract §9 V9, the vendored `.sl-file`
# contract). An asset renders as a FILE — a prominent type identity (uppercase extension
# badge toned by family, or an image thumbnail), the filename WITH extension as the title,
# a faint size · date meta line, and exactly ONE download/open affordance; the card body is
# the OPEN target (the canonical /assets/{id} detail, slide-over armed). Shared by the
# Library tab grid cards + the outline Assets/Deliver rows (--row
# variant), and the asset detail hero. ──────────────────────────────────────────────────

# Extension → badge tone, the design-system family map (components.css: red docs that
# print, amber decks, green sheets/data, blue text, violet images; unknown stays neutral).
_EXT_TONES = (("red", ("pdf",)),
              ("amber", ("ppt", "pptx", "key", "odp")),
              ("green", ("csv", "tsv", "xls", "xlsx", "ods", "parquet")),
              ("blue", ("txt", "md", "markdown", "doc", "docx", "rtf", "json", "html", "yaml", "yml")),
              ("violet", ("png", "jpg", "jpeg", "gif", "webp", "svg", "heic", "avif")))

# The file-card composition layer: the vendored contract styles the parts; app-side are
# the overlay-link geometry (the body-opens-detail target — anchors cannot nest, the
# entity_row/funnel idiom), the container hover, and a wider grid floor — the inspector's
# cards carry a direction pill + provenance source line on top of the DS default anatomy,
# so full filenames need more than the 180px floor to read as file identity (V9).
register_css(".sl-file{position:relative}"
             ".sl-file__open{position:absolute;inset:0;border-radius:inherit}"
             ".sl-file:has(.sl-file__open:hover){background:var(--sl-hover);"
             "border-color:color-mix(in srgb,var(--sl-ink) 14%,var(--sl-line))}"
             ".sl-file-grid{grid-template-columns:repeat(auto-fill,minmax(240px,1fr))}"
             ".sl-file__meta .lbl{margin-left:2px}"
             ".sl-file__meta .srcchip{margin-left:0}")


def asset_ext(asset: dict) -> str:
    """The asset's file extension token ('pptx', 'md', …): from the filename, falling back
    to the media-type subtype; '' when neither says anything."""
    name = asset.get("filename") or ""
    ext = name.rsplit(".", 1)[1].lower() if "." in name.strip(".") else ""
    if not ext:
        ext = (asset.get("media_type") or "").rpartition("/")[2].lower()
    return ext[:6]


def file_ext_badge(asset: dict) -> str:
    """The uppercase extension badge (`.sl-file__ext`), toned by type family."""
    ext = asset_ext(asset) or "file"          # extension-less: the neutral generic token
    tone = next((tn for tn, exts in _EXT_TONES if ext in exts), "")
    return h("span", {"class_": "sl-file__ext" + (f" sl-file__ext--{tone}" if tone else "")},
             ext)


def file_stage(asset: dict, *, thumb: bool = True) -> str:
    """The card's identity stage: the image thumbnail when the asset IS an image (and the
    caller wants it), the first-page render for documents that carry one (W6 `preview_url` —
    the PPTX card shows its title slide), else the extension badge on the quiet stage."""
    src = (asset_content_url(asset) if asset.get("kind") in ("image", "screenshot")
           else asset_content_url(asset, preview=True) if asset.get("preview_url") else "")
    if thumb and src:
        return h("span", {"class_": "sl-file__stage"},
                 h("img", {"class_": "sl-file__thumb", "src": src, "alt": "",
                           "loading": "lazy"}))
    return h("span", {"class_": "sl-file__stage"}, raw(file_ext_badge(asset)))


def _file_action(asset: dict) -> str:
    """The ONE trailing affordance (V9 — never duplicated): download for deliverables,
    open-in-tab for evidence. '' when the binary has no URL."""
    url = asset_content_url(asset)
    if not url:
        return ""
    is_out = asset_direction(asset) == "out"
    label = t("download") if is_out else t("open")
    link = ({"href": url, "download": asset.get("filename", "")} if is_out
            else {"href": url, "target": "_blank", "rel": "noopener"})
    return h("span", {"class_": "sl-file__action"},
             h("a", {"class_": "sl-entity__action", **link, "title": label, "aria-label": label},
               raw(_icon("download" if is_out else "external"))))


def file_card(asset: dict, store=None, *, row: bool = False, href: str | None = None,
              drawer: bool = False, desc: str = "", source: bool = False,
              show_direction: bool = True, attrs: dict | None = None) -> str:
    """An asset as a FILE card (`.sl-file`) or compact row (`.sl-file--row`): identity stage ·
    filename+ext title · `size · date[ · desc]` meta · direction pill · one action. The card
    BODY opens the canonical /assets/{id} detail (`drawer=True` arms the slide-over via the
    stretched overlay link); `source=True` adds the quiet provenance source line (grid cards);
    `desc` joins the meta line (the Library's owning-project title); `show_direction=False`
    lets the project outline keep rows tag-free; `attrs` extends the container."""
    from .ui import _fmt_day
    open_href = href or f'/assets/{asset.get("id", "")}'
    name = asset.get("filename") or asset.get("title") or asset.get("id", "")
    meta = " · ".join(x for x in (asset_size(asset), _fmt_day(asset.get("created_at") or ""),
                                  desc) if x)
    src = asset_source_chip(asset, store) if source else ""
    pill = raw(asset_direction_pill(asset)) if show_direction else ""
    # GRID cards keep the filename on its own full-width line (file identity first — the
    # pill joins the meta line); the compact ROW variant trails the pill beside the action.
    info = h("div", {"class_": "sl-file__info"},
             h("span", {"class_": "sl-file__name", "title": name}, name),
             h("span", {"class_": "sl-file__meta"}, meta, None if row or not pill else fragment(" ", pill)),
             h("span", {"class_": "sl-file__meta"}, raw(str(src))) if src else None)
    stretch = h("a", {"class_": "sl-file__open", "href": open_href, "aria-label": name[:90],
                      "data-drawer": open_href if drawer else None,
                      "data-drawer-title": (asset.get("title") or name)[:90] if drawer else None})
    return h("div", {"class_": "sl-file" + (" sl-file--row" if row else ""), **(attrs or {})},
             stretch, raw(file_stage(asset)),
             h("div", {"class_": "sl-file__body"}, info, pill if row else None,
               raw(_file_action(asset))))


def asset_file_card(asset: dict, *, stage: bool = True) -> str:
    """The asset detail page's hero file card (V9): the `.sl-file` card front and center —
    extension badge stage, filename+ext title, size · media-type meta (the page's ONE place
    for both, round-4 J2). The WHOLE card is the one download/open affordance (download for
    deliverables, open-in-tab for evidence). `stage=False` drops the extension-badge stage
    when the real preview (image / first-page render) already leads the page above the card
    (J2: no empty PPTX stage right under the rendered title slide)."""
    is_out = asset_direction(asset) == "out"
    url = asset_content_url(asset) or "#"
    link = ({"href": url, "download": asset.get("filename", "")} if is_out
            else {"href": url, "target": "_blank", "rel": "noopener"})
    meta = " · ".join(x for x in (asset_size(asset), asset.get("media_type", "")) if x)
    return h("a", {"class_": "sl-file", **link},
             raw(file_stage(asset, thumb=False)) if stage else None,
             h("div", {"class_": "sl-file__body"},
               h("div", {"class_": "sl-file__info"},
                 h("span", {"class_": "sl-file__name"}, asset.get("filename", "")),
                 h("span", {"class_": "sl-file__meta"}, meta)),
               h("span", {"class_": "sl-file__action"},
                 h("span", {"class_": "sl-entity__action"},
                   raw(_icon("download" if is_out else "external"))))))


def asset_rows(assets: list, store=None) -> str:
    """Asset rows (files/images/screenshots, ticket attach-evidence-files-mcp): image assets
    render a thumbnail from the static /data mount; every row carries kind + direction pills and
    `filename · size`. Since UX U8 the title deep-links to the asset's detail page (slide-over
    armed); the file itself stays one click away on the thumb / the trailing download link.
    Used by the graph view's floating panel (the default view shows assets as outline rows)."""
    rows = []
    for a in assets:
        is_img = a.get("kind") in ("image", "screenshot")
        is_out = asset_direction(a) == "out"
        detail = f'/assets/{a.get("id", "")}'
        url = asset_content_url(a) or "#"
        link = {"href": url, "target": "_blank", "rel": "noopener"}
        if is_out:  # a deliverable file: hand it to the user, don't render it in a tab
            link = {"href": url, "download": a.get("filename", "")}
        thumb = (h("a", dict(link),
                   h("img", {"src": url, "alt": a.get("title", ""), "loading": "lazy",
                             "style": "max-height:64px;max-width:120px;border-radius:6px;display:block"}))
                 if is_img else raw(_icon("download" if is_out else "file")))
        rows.append(h("div", {"class_": "strow"},
                      thumb, " ",
                      h("a", {"href": detail, "data-drawer": detail,
                              "data-drawer-title": a.get("title") or a.get("filename", "")},
                        h("b", {}, a.get("title") or a.get("filename", ""))), " ",
                      raw(asset_kind_pill(a)), " ",
                      raw(asset_direction_pill(a)), " ",
                      h("span", {"class_": "muted small"}, f'{a.get("filename", "")} · {asset_size(a)}'
                        + (f' · {a.get("notes")}' if a.get("notes") else "")), " ",
                      h("a", dict(link), raw(_icon("download" if is_out else "external")))))
    return "".join(rows)


# The former tier-3 rescue sections (assets_section_html / open_questions_section_html /
# surveys_section_html) retired with UX P2 — these kinds are outline rows now (§3.4, C3).
