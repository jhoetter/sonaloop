"""Survey pages: list + detail (the outbound instrument's inspector surface).

READ-ONLY like every page: authoring/export/import happen through MCP/CLI. The detail page opens
with structure (ux-contract §3.6): the questions as rows — kind icon + text + the answer-distribution
strip where responses exist — each expanding to the full per-question charts (option bars, collected
texts, the predicted-vs-actual strip for stance_mapped questions in the canonical stance colors —
artifacts.stance_meta, nothing stance-y hardcoded); then the responses as rows with persona chips,
each expanding to that respondent's per-question answers."""
from __future__ import annotations

from ._ctx import *  # noqa: F401,F403  (shared render toolkit)
from .._html import register_css
from .._presence import survey_status_pill as _status_pill
from ... import artifacts as _A


register_css(r"""
.svq{border:1px solid var(--line-2);border-radius:9px;padding:12px 14px;margin:0 0 10px;background:var(--panel)}
.svq>summary{list-style:none;cursor:pointer}
.svq>summary::-webkit-details-marker{display:none}
.svq[open]>summary{border-bottom:1px solid var(--line-2);padding-bottom:10px;margin-bottom:10px}
.svq>summary:hover .sl-entity__title{color:var(--accent)}
.svq .sl-entity__trailing .pvbar{width:120px;flex:none}
.svq .qhead{display:flex;gap:8px;align-items:baseline}
.svq .qnum{color:var(--muted);font-size:var(--t-sm)}
.svq p.small{margin:4px 0;line-height:1.5}
.svq p.small>.muted{display:block}
.svopts{margin:6px 0 0;display:flex;flex-wrap:wrap;gap:6px}
.svbar{position:relative;height:18px;border-radius:5px;background:var(--line-2);overflow:hidden;flex:1}
.svbar i{position:absolute;inset:0 auto 0 0;background:var(--accent);opacity:.35}
.svrow{display:grid;grid-template-columns:minmax(120px,1fr) 3fr 44px;gap:10px;align-items:center;margin:4px 0;font-size:var(--t-sm)}
.svrow>span:last-child{text-align:right;color:var(--muted);font-variant-numeric:tabular-nums}
.pvlbl{color:var(--muted);font-size:var(--t-sm);min-width:130px}
.pvbar{display:flex;height:14px;border-radius:7px;overflow:hidden;background:var(--line-2);flex:1}
.pvseg{height:100%}
.pvline{display:flex;gap:10px;align-items:center;margin:5px 0}
""")


def _stance_strip(counts: dict, total: int) -> str:
    """One distribution strip — segments ordered/colored by the canonical scale (stance_terms +
    stance_meta), labels resolved through t(label_key). Nothing stance-y is hardcoded."""
    segs = []
    for term in _A.stance_terms():
        n = counts.get(term["term"], 0)
        if not n:
            continue
        meta = _A.stance_meta(term["value"])
        segs.append(h("span", {"class_": "pvseg",
                               "style": f'width:{n / total * 100:.1f}%;background:{meta["color"]}',
                               "title": f'{t(meta["label_key"])}: {n}'}))
    return h("div", {"class_": "pvbar"}, fragment(*segs))


def _option_strip(options: list, counts: dict, total: int) -> str:
    """The answer-distribution strip for a NON-stance question (the row's at-a-glance result):
    one segment per answered option in authored order, a graded accent ramp (options carry no
    canonical colors — the ramp encodes order, the title carries the truth)."""
    segs = []
    steps = max(1, len(options) - 1)
    for i, opt in enumerate(options):
        n = counts.get(opt, 0)
        if not n:
            continue
        segs.append(h("span", {"class_": "pvseg",
                               "style": f"width:{n / total * 100:.1f}%;background:var(--accent);"
                                        f"opacity:{0.95 - i * 0.7 / steps:.2f}",
                               "title": f"{opt}: {n}"}))
    if not segs:
        return ""
    return h("div", {"class_": "pvbar"}, fragment(*segs))


def _predicted_vs_actual(comparison: dict, _store) -> str:
    pred, act = comparison.get("predicted") or {}, comparison.get("actual") or {}
    rows = []
    for label, dist in ((t("survey_predicted"), pred), (t("survey_actual"), act)):
        n = dist.get("n", 0)
        bar = _stance_strip(dist.get("counts") or {}, n) if n else h("div", {"class_": "pvbar"})
        rows.append(h("div", {"class_": "pvline"},
                      h("span", {"class_": "pvlbl"}, f"{label} ({n})"), raw(bar)))
    return h("div", {}, fragment(*rows))


def _question_row(q: dict, result: dict | None, store, show_count: bool = True) -> str:
    """One question as an expandable ROW (§3.6): the summary line carries the kind icon, the
    (ellipsized) text, the distribution strip + answered count; the body keeps the full question
    text and the result charts exactly where they already rendered. `show_count=False` when every
    question shares the same answered count — the section states it ONCE instead of every row
    repeating "5 responses" (round-3 H4); per-question counts stay only when they DIFFER."""
    icons = dict(single="dot", multi="list", scale="analytics", text="quote")
    res = result or {}
    answered = res.get("answered", 0)
    strip = ""
    if answered and q.get("stance_mapped") and res.get("comparison"):
        actual = (res.get("comparison") or {}).get("actual") or {}
        strip = _stance_strip(actual.get("counts") or {}, actual.get("n") or answered)
    elif answered and q.get("options"):
        strip = _option_strip(q.get("options") or [], res.get("counts") or {}, answered)
    head = h("summary", {"class_": "sl-entity"},
             h("span", {"class_": "sl-entity__visual"}, raw(_icon(icons.get(q.get("kind", ""), "help")))),
             h("div", {"class_": "sl-entity__content"},
               h("div", {"class_": "sl-entity__title", "title": q.get("text", "")}, q.get("text", ""))),
             h("span", {"class_": "sl-entity__trailing"},
               raw(strip) if strip else None,
               h("span", {"class_": "pill"}, q.get("kind", "")),
               (h("span", {"class_": "pill"}, t("survey_stance_mapped"))
                if q.get("stance_mapped") else None),
               (h("span", {"class_": "muted small"}, t("n_responses", n=answered))
                if answered and show_count else None)))
    body = [h("div", {"class_": "qhead"}, h("span", {"class_": "qnum"}, q.get("id", "")),
            h("b", {}, q.get("text", "")))]
    if answered and q.get("kind") == "text":
        body += [h("p", {"class_": "muted small"}, f"„{a}“")
                 for a in (res.get("answers") or [])[:8]]
    elif answered:
        counts = res.get("counts") or {}
        for opt in q.get("options") or []:
            n = counts.get(opt, 0)
            pct = (n / answered * 100) if answered else 0
            body.append(h("div", {"class_": "svrow"}, h("span", {}, opt),
                          h("div", {"class_": "svbar"}, h("i", {"style": f"width:{pct:.1f}%"})),
                          h("span", {}, str(n))))
    elif q.get("options"):
        body.append(h("div", {"class_": "svopts"},
                      fragment(*(h("span", {"class_": "pill"}, o) for o in q["options"]))))
    if answered and q.get("stance_mapped") and res.get("comparison"):
        body.append(raw(_predicted_vs_actual(res["comparison"], store)))
    return h("details", {"class_": "svq"}, head, fragment(*body))


def _response_row(resp: dict, qmap: dict, store) -> str:
    """One imported response as an expandable ROW: the persona chip (avatar + name, resolved from
    the `persona:<id>` respondent key) + answer count + date in the summary; the body lists that
    respondent's per-question answers."""
    key = resp.get("respondent_key") or ""
    pid = key.split(":", 1)[1] if key.startswith("persona:") else ""
    p = (store.get_persona(pid) or {}) if pid else {}
    name = p.get("display_name") or key or "—"
    visual = raw(_avatar(p, 22)) if p else raw(_icon("avatar"))
    answers = resp.get("answers") or []
    head = h("summary", {"class_": "sl-entity"},
             h("span", {"class_": "sl-entity__visual"}, visual),
             h("div", {"class_": "sl-entity__content"},
               h("div", {"class_": "sl-entity__title"}, name)),
             h("span", {"class_": "sl-entity__trailing"},
               h("span", {"class_": "muted small"}, t("n_answers", n=len(answers))),
               h("span", {"class_": "muted small"}, ui.fmt_day(resp.get("submitted_at") or ""))))
    rows = []
    for a in answers:
        q = qmap.get(a.get("question_id", "")) or {}
        val = a.get("value")
        val = ", ".join(str(x) for x in val) if isinstance(val, list) else str(val or "")
        rows.append(h("p", {"class_": "small"},
                      h("span", {"class_": "muted"}, q.get("text") or a.get("question_id", "")),
                      val))
    return h("details", {"class_": "svq"}, head, fragment(*rows))


def register_surveys(app) -> None:
    @app.get("/surveys", response_class=HTMLResponse)
    def surveys(project: str = Query(default=""), status: str = Query(default=""),
                subtype: str = Query(default=""), trace: str = Query(default=""),
                q: str = Query(default="")) -> str:
        # The Library's Surveys tab under the canonical URL (ux-contract §3.5),
        # filterable by project + status (U10, the shared FilterBar grammar).
        from .library import library_filters, library_page
        return library_page("surveys", flt=library_filters(project, status, subtype=subtype, trace=trace),
                            base="/surveys", q=q)

    @app.get("/surveys/{survey_id}", response_class=HTMLResponse)
    def survey_detail(survey_id: str) -> str:
        store = Store()
        try:
            s = services.get_survey(survey_id, store=store)
        except KeyError:
            return _layout(t("not_found"), _empty_state(t("surveys_h"), t("runtime_maybe_cleared"),
                                                        icon="plan"), store, active="library")
        results = services.survey_results(s["id"], store=store)
        by_q = {r["question_id"]: r for r in results["questions"]}
        qmap = {q["id"]: q for q in s["questions"]}
        proj = store.get_research_project(s.get("project_id")) if s.get("project_id") else None
        crumbs = [(t("projects"), "/projects")]
        if proj:
            crumbs.append((proj["title"], f'/projects/{proj["id"]}'))
        crumbs.append((s["title"], None))
        intro_html = (h("p", {"class_": "sub"}, s.get("intro", "")) if s.get("intro") else None)
        # When every question shares one answered count, state it ONCE at section level instead
        # of repeating "5 responses" on every row (round-3 H4); differing counts stay per-row.
        answered_counts = [(by_q.get(q["id"]) or {}).get("answered", 0) for q in s["questions"]]
        uniform_n = answered_counts[0] if len(set(answered_counts)) == 1 and answered_counts else None
        questions_html = h("div", {"class_": "sec", "id": "sec-questions"},
                           h("h2", {}, t("n_questions", n=len(s["questions"]))),
                           (h("p", {"class_": "ihint"}, t("n_responses_each", n=uniform_n))
                            if uniform_n else None),
                           fragment(*(_question_row(q, by_q.get(q["id"]), store,
                                                    show_count=uniform_n is None)
                                      for q in s["questions"])))
        n_resp = results["responses"]
        responses = store.list_survey_responses(s["id"]) if n_resp else []
        responses_html = h("div", {"class_": "sec", "id": "sec-responses"},
                           h("h2", {}, t("n_responses", n=n_resp)),
                           (h("p", {"class_": "muted small"}, t("no_survey_responses"))
                            if not n_resp else
                            fragment(*(_response_row(r, qmap, store) for r in responses))))
        body = fragment(intro_html, questions_html, responses_html)
        proj_link = (h("a", {"href": f'/projects/{proj["id"]}'}, proj["title"]) if proj else "—")
        # Detail-header attribution (ux-contract §10 W11): the persona-sourced respondents
        # as the one avatar-group anatomy, leading the meta line.
        resp_pids = services.survey_respondent_personas(s["id"], store=store)
        crew = ui.avatar_group((store.get_persona(pid) for pid in resp_pids[:4]),
                               total=len(resp_pids), size=22)
        counts_txt = f'{t("n_questions", n=len(s["questions"]))} · {t("n_responses", n=n_resp)}'
        sub = (h("span", {"class_": "syn-meta"}, crew, h("span", {"class_": "muted"}, counts_txt))
               if crew else counts_txt)
        return detail_page(
            store, title=s["title"], crumbs=crumbs,
            # G5: sidebar active follows the crumb root (project-rooted → Projects)
            active="projects" if proj else "library",
            icon="plan", kind=t("survey_kind"), pills=[_status_pill(s.get("status", "draft"))],
            sub=sub,
            body=body,
            # label/value discipline: "5 responses → 5" duplicated the number (P5 finding);
            # rail order is the §8.2 anatomy (project → kind-specifics → dates) and the
            # "Type: Survey" row retired — the SURVEY eyebrow already states the kind (round 2).
            prop_rows=[("projects", t("project"), proj_link),
                       *detail_form_rows("survey", s),
                       ("personas", t("respondents_h"), str(results["respondents"])),
                       ("clock", t("created"), ui.fmt_date(s.get("created_at", "")))],
            rel_study_id=f"survey:{s['id']}", rel_proj_id=(proj["id"] if proj else None),
            rail_sections=[("sec-questions", t("n_questions", n=len(s["questions"]))),
                           ("sec-responses", t("n_responses", n=n_resp))],
            star=("survey", s["id"], s["title"], f'/surveys/{s["id"]}'),
            # Cloud's share-link block plugs in here (render_detail_extra seam); "" in the
            # public core, so the aside renders bit-identically without the extension.
            aside_extra=render_detail_extra("survey", store, s))
