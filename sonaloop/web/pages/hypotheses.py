"""Hypotheses: the real /hypotheses/{id} detail page (UX U7, spec/ux-contract.md §8.2), the
cross-project list page + the shared bet renderers.

A hypothesis ALSO lives on its project page — an outline row in its phase context (UX P2, §3.4 /
decision §7.1) — and the detail page keeps that anchor as the secondary "view in project" link.
This module owns everything bet-shaped that is shared between the global /hypotheses index, the
detail page and the hypothesis slide-over (the detail's ?slide=1 variant, §8.1): the predicted/observed reads and the
hit-rate strip (the lifecycle pills live in web/_presence, shared with the outline chips).
READ-ONLY like every page. /hypotheses and /hypotheses/{id} have distinct path shapes, so the
list route never shadows the detail route."""
from __future__ import annotations

from ._ctx import *  # noqa: F401,F403  (shared render toolkit)
from .._html import register_css
from .._presence import HYP_STATUS_COLORS, hypothesis_status_label, hypothesis_status_pill
from .._render import _refs_line

# Card CSS shared by hypothesis AND decision rows (.hyp is the generic artifact card; decisions.py
# reuses it — co-located here with its primary owner).
register_css(r"""
.hyp{border:1px solid var(--line-2);border-radius:9px;padding:10px 14px;margin:8px 0;background:var(--panel)}
.hyp p{margin:4px 0 0}
.hypvals{display:flex;gap:16px;flex-wrap:wrap;margin-top:4px;font-size:var(--t-sm)}
.hyprate{display:flex;gap:10px;align-items:center;margin:6px 0 12px}
.hypstrip{display:flex;height:14px;border-radius:7px;overflow:hidden;background:var(--line-2);flex:1;max-width:340px}
.hypseg{height:100%}
""")


def _hyp_predicted_text(pred: dict) -> str:
    """metric → expectation (value ±tolerance, or the direction word) · confidence."""
    if "expected_value" in pred:
        expected = str(pred.get("expected_value"))
        if pred.get("tolerance"):
            expected += f' ±{pred["tolerance"]:g}'
    else:
        expected = (t("hyp_dir_increase") if pred.get("expected_direction") == "increase"
                    else t("hyp_dir_decrease"))
    out = f'{pred.get("metric", "")} → {expected}'
    conf = pred.get("confidence")
    if conf is not None:
        out += f' · {t("hyp_confidence")} {conf:.0%}'
    return out


def _hypothesis_reads(hx: dict, store):
    """The bet's record reads, shared by the row card and the detail page: predicted vs observed
    values, the resolution note, the observation's source chip and the derived-from chips."""
    pred = hx.get("prediction") or {}
    res = hx.get("result") or {}
    vals = [h("span", {}, h("span", {"class_": "muted"}, t("hyp_predicted"), ": "),
              _hyp_predicted_text(pred))]
    if res:
        vals.append(h("span", {}, h("span", {"class_": "muted"}, t("hyp_observed"), ": "),
                      str(res.get("observed_value", ""))))
    note = (h("p", {"class_": "muted small"}, res["note"])
            if res.get("note") else None)
    src = (raw(_refs_line([res["source"]], t("hyp_observed"), store))
           if res.get("source") else None)
    derived = (raw(_refs_line(hx["derived_from"], t("rel_based_on"), store))
               if hx.get("derived_from") else None)
    return h("div", {"class_": "hypvals"}, fragment(*vals)), note, src, derived


def _hypothesis_row(hx: dict, store, *, title_href: str | None = None,
                    project_title: str | None = None) -> str:
    """One bet card. On the project page the card is the anchor target (plain bold title); on the
    cross-project list `title_href` links the title into that anchor and `project_title` names
    where the bet lives."""
    status = hx.get("status", "open")
    title = h("b", {}, hx.get("text", ""))
    if title_href:
        title = h("a", {"href": title_href}, title)
    proj = (h("span", {"class_": "muted small", "style": "margin-left:8px"}, project_title)
            if project_title else None)
    vals, note, src, derived = _hypothesis_reads(hx, store)
    return h("div", {"class_": "hyp", "id": f'hyp-{hx["id"]}'},
             h("div", {}, raw(hypothesis_status_pill(status)), " ", title, proj),
             vals, note, src, derived)


def _hyp_hit_rate_strip(hyps: list) -> str:
    """The hit-rate strip over RESOLVED bets only — open ones haven't been scored by reality yet,
    and dropped ones aren't scored at all. Honest line when nothing is resolved."""
    scored = [x for x in hyps if x.get("status") not in ("open", "dropped")]
    if not scored:
        return h("p", {"class_": "muted small"}, t("hyp_no_resolved"))
    decisive = [x for x in scored if x.get("status") in ("validated", "refuted")]
    hits = sum(1 for x in decisive if x["status"] == "validated")
    segs = []
    for status in ("validated", "refuted", "inconclusive"):
        n = sum(1 for x in scored if x["status"] == status)
        if n:
            segs.append(h("span", {"class_": "hypseg",
                                   "style": (f"width:{n / len(scored) * 100:.1f}%;"
                                             f"background:{HYP_STATUS_COLORS[status]}"),
                                   "title": f"{hypothesis_status_label(status)}: {n}"}))
    rate = (f"{hits}/{len(decisive)} · {hits / len(decisive) * 100:.0f}%" if decisive
            else t("hyp_no_decisive"))
    return h("div", {"class_": "hyprate"},
             h("span", {"class_": "muted small"}, t("hyp_hit_rate"), f": {rate}"),
             h("div", {"class_": "hypstrip"}, fragment(*segs)))


def register_hypotheses(app) -> None:
    @app.get("/hypotheses", response_class=HTMLResponse)
    def hypotheses_list(project: str = Query(default=""), status: str = Query(default=""),
                        subtype: str = Query(default=""), trace: str = Query(default=""),
                        q: str = Query(default="")) -> str:
        """Every bet across all projects — the Library's Hypotheses tab (ux-contract §3.5),
        keeping the GLOBAL hit-rate strip: how often do our predictions survive reality?
        Filterable by project + status (U10, the shared FilterBar grammar)."""
        from .library import library_filters, library_page
        store = Store()
        hyps = services.list_hypotheses(store=store)
        strip = str(_hyp_hit_rate_strip(hyps)) if hyps else ""
        return library_page("hypotheses", store, pre_extra=strip,
                            flt=library_filters(project, status, subtype=subtype, trace=trace),
                            base="/hypotheses", q=q)

    @app.get("/hypotheses/{hypothesis_id}", response_class=HTMLResponse)
    def hypothesis_detail(hypothesis_id: str) -> str:
        """A hypothesis's REAL detail page (UX U7 — every kind, one scaffold; supersedes the old
        redirect into the project anchor, which stays reachable as the secondary 'view in
        project' link): the bet on the shared anatomy — kind eyebrow + lifecycle pill header,
        predicted vs observed, the resolution note, source + derived-from chips — with the
        properties rail (project, dates)."""
        store = Store()
        try:
            hx = services.get_hypothesis(hypothesis_id, store=store)
        except KeyError:
            return _layout(t("not_found"),
                           _empty_state(t("hypotheses_h"), t("runtime_maybe_cleared"), icon="target"),
                           store, active="library")
        proj = (store.get_research_project(hx.get("project_id")) if hx.get("project_id") else None)
        vals, note, src, derived = _hypothesis_reads(hx, store)
        body = h("div", {"class_": "sec", "id": "sec-bet"}, vals, note, src, derived)
        # Project-rooted crumb (§8.2 — the council pattern); kind root only for orphans.
        crumbs = ([(t("projects"), "/projects"), (proj["title"], f'/projects/{proj["id"]}')]
                  if proj else [(t("hypotheses_h"), "/hypotheses")])
        crumbs.append((_display_title(hx.get("text", "")), None))
        anchor = (f'/projects/{hx["project_id"]}#hyp-{hx["id"]}' if hx.get("project_id") else "")
        # The rail's project link lands ON the bet's row (the #hyp- anchor) — replaces the old
        # "View in project" meta-line link, which no other kind carried (round 2, §8.2).
        proj_link = (h("a", {"href": anchor or f'/projects/{proj["id"]}'}, proj["title"]) if proj else "")
        prop_rows = [
            ("projects", t("project"), proj_link),
            *detail_form_rows("hypothesis", hx),
            ("dot", t("created"), ui.fmt_date(hx.get("created_at") or "")),
        ]
        return detail_page(
            store, title=hx.get("text", ""), crumbs=crumbs,
            # G5: sidebar active follows the crumb root (project-rooted → Projects)
            active="projects" if proj else "library",
            icon="target", kind=t("hypothesis_kind"),
            pills=[hypothesis_status_pill(hx.get("status", "open"))],
            hid="sec-head", body=body, prop_rows=prop_rows,
            rel_study_id=f"hypothesis:{hx['id']}", rel_proj_id=(proj["id"] if proj else None),
            rail_sections=[("sec-bet", t("hypothesis_kind"))],
            star=("hypothesis", hx["id"], hx.get("text", "")[:60], f'/hypotheses/{hx["id"]}'))
