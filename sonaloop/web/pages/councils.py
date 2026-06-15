"""Council pages: list + detail (spec/roadmap.md R2)."""
from __future__ import annotations

from ._ctx import *  # noqa: F401,F403  (shared render toolkit)
from .. import ui
from .._forms import overflow_delete as _overflow_delete
from .._keymap import sibling_attrs, sibling_urls
from .._render import render_statements
from .._html import register_css
from ... import artifacts as _A


# Head-to-Head verdict block: the preference headline + the option/segment tally tables.
register_css(r"""
.h2h-pref{font-size:var(--t-body);margin:0 0 12px}
.h2h-table{width:100%;border-collapse:collapse;margin:0 0 8px;font-size:var(--t-sm)}
.h2h-table th{text-align:left;color:var(--muted);font-weight:600;padding:5px 10px;border-bottom:1px solid var(--line-2)}
.h2h-table td{padding:5px 10px;border-bottom:1px solid var(--line-2)}
.h2h-table tr:last-child td{border-bottom:0}
""")


def _h2h_result_html(result: dict) -> str:
    """The deterministic head-to-head verdict: the overall preference + margin headline, the per-option
    vote tally, and the segment-splits (who-prefers-what) table. The server computes these; the prose
    verdict lives in the exec_summary above. UI language is German by default (match the surrounding UI)."""
    options = result.get("options", [])
    title_by = {o["label"]: o.get("title", o["label"]) for o in options}
    pref = result.get("preference")
    decisive = t("h2h_decisive_" + (result.get("decisive") or "tie"))
    if pref:
        headline = h("div", {"class_": "h2h-pref"},
                     h("strong", {}, f"{t('h2h_preference')}: {pref} — {result.get('preference_title') or ''}"),
                     h("span", {"class_": "muted small"}, f" · {decisive} · {t('h2h_margin')} {result.get('margin')}"))
    else:
        headline = h("div", {"class_": "h2h-pref"}, h("strong", {}, t("h2h_no_pref")))

    # Per-option vote tally.
    opt_rows = [h("tr", {}, h("th", {}, t("h2h_options")), h("th", {}, t("h2h_votes")))]
    for o in options:
        is_win = o["label"] == pref
        opt_rows.append(h("tr", {"style": ("font-weight:600" if is_win else "")},
                          h("td", {}, f"{o['label']} — {o.get('title', '')}"),
                          h("td", {}, str(o.get("votes", 0)))))
    opt_table = h("table", {"class_": "h2h-table"}, *opt_rows)

    # Segment-splits: who prefers what, broken down by persona segment/archetype.
    splits = result.get("segment_splits", [])
    seg_html = ""
    if splits:
        labels = [o["label"] for o in options]
        head = [h("th", {}, t("h2h_segment")), h("th", {}, t("h2h_voters"))]
        head += [h("th", {}, lab) for lab in labels]
        head.append(h("th", {}, t("h2h_prefers")))
        seg_rows = [h("tr", {}, *head)]
        for s in splits:
            cells = [h("td", {}, s.get("segment", "")), h("td", {}, str(s.get("voters", 0)))]
            cells += [h("td", {}, str((s.get("tally") or {}).get(lab, 0))) for lab in labels]
            prefers = s.get("prefers")
            cells.append(h("td", {}, (f"{prefers} — {title_by.get(prefers, '')}" if prefers else t("h2h_tie"))))
            seg_rows.append(h("tr", {}, *cells))
        seg_html = fragment(h("h3", {"style": "margin:14px 0 6px"}, t("h2h_segments")),
                            h("table", {"class_": "h2h-table"}, *seg_rows))
    return str(fragment(headline, opt_table, seg_html))


def _red_team_result_html(rt: dict) -> str:
    """The deterministic red-team verdict: the case-against headline (blocker themes + worst severity), the
    per-theme blocker table (how many personas raise each blocker + severity), and — when the run captured
    both directions — a compact case-for table beside it. The server computes these; the prose verdict lives
    in the exec_summary above. UI language is German by default (match the surrounding UI)."""
    against = rt.get("case_against") or {}
    themes = against.get("themes", [])
    top = against.get("top_blocker")
    worst = against.get("worst_severity")
    if themes:
        headline = h("div", {"class_": "h2h-pref"},
                     h("strong", {}, f"{t('rt_case_against')}: {against.get('theme_count', 0)} {t('rt_blockers')}"),
                     h("span", {"class_": "muted small"},
                       f" · {against.get('voices', 0)} {t('rt_voices')}"
                       + (f" · {t('rt_top_blocker')}: {top}" if top else "")
                       + (f" · {t('rt_severity')} {t('rt_sev_' + worst)}" if worst else "")))
    else:
        headline = h("div", {"class_": "h2h-pref"}, h("strong", {}, t("rt_no_objections")))

    rows = [h("tr", {}, h("th", {}, t("rt_blocker")), h("th", {}, t("rt_personas")), h("th", {}, t("rt_severity")))]
    for th in themes:
        sev = th.get("severity")
        rows.append(h("tr", {},
                      h("td", {}, th.get("theme", "")),
                      h("td", {}, str(th.get("count", 0))),
                      h("td", {}, t("rt_sev_" + sev) if sev else "")))
    against_table = h("table", {"class_": "h2h-table"}, *rows)

    # The optional case FOR, beside the case against (both-directions run).
    for_html = ""
    case_for = rt.get("case_for")
    if case_for and case_for.get("themes"):
        fr = [h("tr", {}, h("th", {}, t("rt_pull")), h("th", {}, t("rt_personas")))]
        for th in case_for["themes"]:
            fr.append(h("tr", {}, h("td", {}, th.get("theme", "")), h("td", {}, str(th.get("count", 0)))))
        for_html = fragment(h("h3", {"style": "margin:14px 0 6px"}, t("rt_case_for")),
                            h("table", {"class_": "h2h-table"}, *fr))
    return str(fragment(headline, against_table, for_html))


def register_councils(app) -> None:
    @app.get("/councils", response_class=HTMLResponse)
    def councils(project: str = Query(default=""), status: str = Query(default=""),
                 subtype: str = Query(default=""), q: str = Query(default="")) -> str:
        # The URL stays canonical; the content is the Library with the Councils tab
        # active (ux-contract §3.5 — one browser, no redirects) + the shared FilterBar (U10).
        from .library import library_filters, library_page
        return library_page("councils", flt=library_filters(project, status, subtype=subtype),
                            base="/councils", q=q)

    @app.get("/councils/{session_id}", response_class=HTMLResponse)
    def council_detail(session_id: str) -> str:
        store = Store()
        session = store.get_council_session(session_id)
        if not session:
            return _layout(t("not_found"), _empty_state(t("council_not_found"), t("runtime_maybe_cleared"), icon="councils"), store, active="library")
        proposal_short_h = t("proposal_short_summary")
        proposal_h = t("proposal"); summary_h = t("summary")
        sentiment_title = t("sentiment_this_council")
        vote_h = t("vote"); personas_h = t("personas"); created_h = t("created")
        councils_crumb = t("councils"); council_title = t("councils")
        # Each voice shows WHO the persona is + the life-context that shaped them (the per-persona
        # "input") and any recorded input snapshot, so you can see what each was given → what they said.
        pmap = {pid: store.get_persona(pid) for pid in session.get("persona_ids", [])}

        # Voices render through the ONE statement renderer (spec/unified-artifact-schema): discovery
        # groups the .turn cards under question headers (group_by="prompt"), evaluation/decision show a
        # flat per-persona list — same card either way.
        statements = _A.council_statements(session)
        prompts = _A.council_prompts(session)
        n_voices = len(session.get("persona_ids", []))
        vm = study_head(session)                       # shared study view-model (question/answer/mode)
        mode = vm["mode"]
        exec_html = _md(vm["answer_md"])
        # Head-to-Head Format: a council carrying a deterministic X-vs-Y aggregate (preference + margin +
        # segment-splits). When present we surface the verdict block above the voices.
        is_h2h = services.is_head_to_head(session)
        h2h_html = (_h2h_result_html(session["head_to_head"]["result"]) if is_h2h else "")
        # Red-Team Format: a council carrying a deterministic case-against (blocker themes + severity). When
        # present we surface the verdict block above the voices.
        is_rt = services.is_red_team(session)
        rt_html = (_red_team_result_html(session["red_team"]) if is_rt else "")
        # The Voices section carries the framing for EVERY mode: each persona card is grouped under the
        # prompt it answers — the discovery QUESTIONS or the evaluation/decision PROPOSAL (rendered as
        # Markdown via render_prompt) — so "what was asked" always sits right above the cards. One
        # consistent structure across all councils (no separate lead block to drift out of sync).
        referenced = {(s.get("about") or {}).get("id") for s in statements if s.get("about")}
        group_prompts = [p for p in prompts if p.get("id") in referenced]
        help_text = (t("council_questions_help", n=n_voices) if mode == "discovery"
                     else t("council_eval_help", n=n_voices) if mode == "evaluation"
                     else t("council_motion_help", n=n_voices))
        intro = h("p", {"class_": "ihint"}, help_text)
        # Reverse cross-refs: each statement learns who cites it (e.g. the synthesis that derives from it).
        _idx = services.ref_backlinks(session.get("project_id", ""), store) if session.get("project_id") else {}
        backlinks = {s["id"]: _idx.get(_A.part_address("council", session["id"], s["id"]), [])
                     for s in statements if s.get("id")}
        backlinks = {k: v for k, v in backlinks.items() if v}
        # Rounds collapse per prompt and long turns clamp (§3.6): the transcript scans as rows,
        # every word stays one toggle away.
        voices_html = (render_statements(statements, store, group_by="prompt", prompts=group_prompts,
                                         backlinks=backlinks, clamp_at=ui.TURN_CLAMP, collapsible=True)
                       if group_prompts else
                       render_statements(statements, store, group_by="persona", backlinks=backlinks,
                                         clamp_at=ui.TURN_CLAMP))
        # Every mode keeps its stance distribution — as the ONE encoding, the scaled bars
        # (§11 T5): evaluation/decision charts the votes' stances, discovery the statements'
        # stance lean (the opener strip that used to carry it retired).
        sentiment = _sentiment_section(store, [session], title=sentiment_title) or ""
        kicker = (t("rt_kicker", n=n_voices) if is_rt else t("h2h_kicker", n=n_voices) if is_h2h
                  else t("council_kicker_" + mode, n=n_voices))
        council_sub = f'{kicker} · {session["selection_reason"]}'
        short_title = _display_title(session["prompt"])        # short form for breadcrumb / tab / favourite only
        # Structure before prose (§3.6): the hero IS the prompt header; directly under it the
        # participants avatar row opens the page, and only then the authored summaries follow
        # (clamped at the section threshold). The opener's distribution STRIP retired (§11 T5 —
        # J1): the sentiment block's scaled stance bars are the page's one distribution encoding.
        # the ONE participation avatar-group anatomy (ux-contract §10 W11 — ui.avatar_group)
        avgroup = ui.avatar_group(pmap.values(), total=n_voices, size=22)
        names = ", ".join((p or {}).get("display_name") or pid for pid, p in pmap.items())
        opener = ui.entity_row(names, visual=avgroup, id="sec-participants",
                               meta=[f"{n_voices} {personas_h}"])
        # Executive Summary (the short TL;DR) sits at the TOP — same block/name as the synthesis.
        has_summary = bool((session.get("summary") or "").strip())
        summary_lead = (raw(_study_lead(ui.clamp(raw(_md(session["summary"])), threshold=ui.SECTION_CLAMP),
                                        t("answer_exec_summary"), qid="sec-summary"))
                        if has_summary else "")
        h2h_block = (h("div", {"class_": "sec", "id": "h2h"}, h("h2", {}, t("h2h_title")),
                       h("p", {"class_": "ihint"}, t("h2h_lead")),
                       raw(h2h_html)) if is_h2h else "")
        rt_block = (h("div", {"class_": "sec", "id": "red-team"}, h("h2", {}, t("rt_title")),
                      h("p", {"class_": "ihint"}, t("rt_lead")),
                      raw(rt_html)) if is_rt else "")
        body = fragment(
            opener,
            summary_lead,
            raw(_study_lead(ui.clamp(raw(exec_html), threshold=ui.SECTION_CLAMP), vm["answer_label"])),
            h2h_block, rt_block, raw(sentiment),
            h("div", {"class_": "sec", "id": "stimmen"}, h("h2", {}, t("voices")), intro, raw(voices_html)),
            # server-provided prev/next sibling URLs for the keymap's [ / ] bindings
            raw(sibling_attrs(*sibling_urls(
                [f'/councils/{c["id"]}' for c in services.list_councils(store=store)],
                f'/councils/{session_id}'))))
        # Forward, project-rooted crumb: Projects > [Project] > [Council]. (A Discover council FEEDS
        # the Define synthesis — it is not nested under it; and the project lookup must work for
        # plan-based projects, where the council is scoped directly to the project.)
        crumbs = [(t("projects"), "/projects")]
        proj = (services.parent_project_of_council(session_id, store)
                or (services.parent_project_of_synthesis(ps["id"], store)
                    if (ps := services.parent_study_of_council(session_id, store)) else None))
        if proj:
            crumbs.append((proj["title"], f"/projects/{proj['id']}"))
        crumbs.append((short_title, None))
        # Rail order is the §8.2 anatomy: project → kind-specifics → dates.
        proj_link = (h("a", {"href": f'/projects/{proj["id"]}'}, proj["title"]) if proj else "")
        # No rail "Type" row: the header mode pill already states it — with the pill the rail row
        # became an echo (round-3 H3, reversing the round-2 keep; assets keep Type = real info).
        prop_rows = [("projects", t("project"), proj_link),
                     ("personas", personas_h, str(n_voices))]
        if mode != "discovery":                               # the vote panel only where a vote/reaction exists
            # value-bucketed via the scale (votes ARE stances; legacy tokens resolve through the
            # aliases); zero buckets drop (V3 — an "Oppose 0" row is noise, not data)
            vals = [st["value"] for x in session["votes"] if (st := _A.vote_stance(x)) is not None]
            prop_rows += [("dot", t(r["label_key"]), str(n))
                          for r in _A.stance_terms() if (n := vals.count(r["value"]))]
        prop_rows.append(("dot", created_h, ui.fmt_date(session["created_at"])))
        mode_pill = _label(t("council_mode_" + mode), "var(--blue)") if mode in (
            "discovery", "evaluation", "decision") else None
        return detail_page(
            store, title=short_title, active="projects", crumbs=crumbs,
            hero=_hero(session["prompt"], icon="councils", sub=council_sub, hid="sec-question",
                       top=detail_eyebrow(t("council_kind"), [mode_pill] if mode_pill else [])),
            body=body,
            prop_rows=prop_rows,
            rel_study_id=f"council:{session_id}", rel_proj_id=(proj["id"] if proj else None),
            rail_sections=([("sec-question", t("question")),
                            ("sec-participants", t("participants"))]
                           + ([("sec-summary", t("answer_exec_summary"))] if has_summary else [])
                           + ([("h2h", t("h2h_title"))] if is_h2h else [])
                           + ([("red-team", t("rt_title"))] if is_rt else [])
                           + [("stimmen", t("voices"))]),
            star=("council", session_id, short_title, f"/councils/{session_id}"),
            # delete-only (no content editing — the statements are generated prose):
            # the subtle header overflow (U9 §8.4), never a danger zone
            actions=_overflow_delete(f'/councils/{session_id}/delete', t("delete_council")))
