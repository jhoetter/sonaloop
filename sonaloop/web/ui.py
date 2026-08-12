"""The sanctioned presentation-composition layer (spec/ux-contract.md C9 + §3.7).

This module is the ONLY way pages compose presentation: every helper is a thin, 1:1
Python counterpart of a design-system class contract (styles/components.css, vendored
as sonaloop/_components_css.py) and mirrors the React wrapper of the same name in
sonaloop-design/src/components.tsx — so the SSR app and the React surfaces can never
drift. Pages call these helpers (or emit bare `sl-*` classes); they do NOT invent
inline `style=` attributes or new CSS classes — tests/test_ux_contract.py gates both
(ratchet: existing violations may only burn down).

Helpers return Safe html strings via the h()/raw()/fragment() element builder
(web/_html.py), so everything is auto-escaped and composes with the page components.
"""
from __future__ import annotations

import re as _re
from typing import Any, Iterable
from urllib.parse import quote as _quote

from ._html import Safe, h, raw, fragment, register_css
from ._i18n import t

# Long authored bodies (ADRs, exec summaries) clamp above this many characters; shorter
# text renders plain — no toggle chrome for three lines of prose (UX contract C6).
CLAMP_THRESHOLD = 420
# Detail pages dose prose at higher thresholds (ux-contract §3.6 / P4): a SECTION of a
# report/synthesis/council detail reads naturally up to ~900 chars and collapses beyond
# (genuinely long authored sections), a council TURN clamps at ~600 so a round of voices
# scans as rows. Rows keep the tight CLAMP_THRESHOLD.
SECTION_CLAMP = 900
TURN_CLAMP = 600


def scaffold(body: Any, *, head: Any = "", bar: Any = "", cls: str = "") -> Safe:
    """The page layout contract (`sl-scaffold`, ux-contract §3.1): a column filling its
    container with a fixed `__head` (breadcrumb/title/actions) and optional `__bar`
    (filters, tabs), and `__body` — THE one scroll container on the page. Children of
    the body must never bring their own overflow/flex:1 (two nested scroll traps = bug;
    see the P0 outline-squeeze). Mirrors React <Scaffold>."""
    return h("div", {"class_": f"sl-scaffold {cls}".strip()},
             h("div", {"class_": "sl-scaffold__head"}, head) if head else None,
             h("div", {"class_": "sl-scaffold__bar"}, bar) if bar else None,
             h("div", {"class_": "sl-scaffold__body"}, body))


def section(title: Any, *content: Any, id: str | None = None) -> Safe:
    """A quiet, content-sized section (`sl-section`, ux-contract §3.7) for below-content
    groups (decision records, assets, open questions): the page's centered 900px
    measure, plain document flow — never flexed, never internally scrolled; anchor
    arrivals clear sticky phase headers via scroll-margin. Group labels inside a
    section use the `sl-section__h` idiom (the old app-local `.oqp-h`). Mirrors
    React <Section>."""
    return h("section", {"class_": "sl-section", "id": id},
             h("h2", {}, title) if title is not None else None,
             fragment(*content))


def clamp(text: Any, *, threshold: int = CLAMP_THRESHOLD, id: str | None = None) -> Safe:
    """Dosed long-form text (`sl-clamp`, ux-contract C6): authored prose at/below the
    threshold renders plain; longer text clamps to 5 lines with an accent "more/less"
    toggle that reveals it in place. Accepts plain text (escaped, a <p>) or pre-rendered
    Safe html — e.g. a _md() body — which keeps block children legal in a <div> and
    measures the threshold on the VISIBLE characters (tags stripped). The localized
    labels ride data-more/data-less so the tiny inline handler stays i18n-clean.
    Mirrors React <Clamp> (which holds the open state in React instead)."""
    is_html = isinstance(text, Safe)
    content: Any = text if is_html else ("" if text is None else str(text))
    visible = _re.sub(r"<[^>]+>", "", content) if is_html else content
    tag = "div" if is_html else "p"
    if len(visible) <= threshold:
        return h(tag, {"id": id}, content)
    return fragment(
        h(tag, {"class_": "sl-clamp", "id": id}, content),
        h("button", {"class_": "sl-clamp-toggle", "type": "button",
                     "data-more": t("more"), "data-less": t("less"),
                     "onclick": "var p=this.previousElementSibling;p.classList.toggle('open');"
                                "this.textContent=p.classList.contains('open')?this.dataset.less:this.dataset.more;"},
          t("more")))


# The row-action contract (UX U8): a row whose trailing slot carries its OWN link (e.g. an
# asset's direct file download) cannot stay one <a> — anchors don't nest. The olrow funnel-chip
# idiom, generalized: the row becomes a positioned container whose main target is a stretched
# overlay link (carrying the href + the slide-over arming) layered UNDER the action link.
register_css(".sl-entity{position:relative}"
             ".sl-entity__stretch{position:absolute;inset:0;border-radius:inherit}"
             ".sl-entity__action{position:relative;z-index:1;display:inline-flex;align-items:center;"
             "line-height:0;color:var(--muted)}"
             ".sl-entity__action:hover{color:var(--accent)}")

# The avatar-group overflow chip ("+n") — rides the vendored `.sl-avatar-group` contract.
register_css(".sl-avatar-group__more{font-size:var(--t-xs);color:var(--faint);"
             "margin-left:4px;align-self:center;white-space:nowrap}")
register_css(".sl-avatar-group--linked{flex-wrap:wrap;row-gap:4px;padding-left:8px}"
             ".sl-avatar-group--linked .sl-avatar-group__person{display:inline-flex;"
             "margin-left:-8px;border-radius:50%;text-decoration:none;position:relative}"
             ".sl-avatar-group--linked .sl-avatar-group__person:first-child{margin-left:0}"
             ".sl-avatar-group--linked .sl-avatar{margin-left:0}"
             ".sl-avatar-group--linked .sl-avatar-group__person:hover{z-index:1}"
             ".sl-avatar-group--linked .sl-avatar-group__person:focus-visible{z-index:2;"
             "outline:2px solid var(--accent);outline-offset:2px}")


def avatar_group(personas: Iterable[Any], *, total: int | None = None, size: int = 18,
                 limit: int | None = 4, linked: bool = False) -> Safe:
    """THE persona-participation avatar group (ux-contract §10 W11) — ONE rule app-wide:
    wherever an artifact's DATA carries persona participation (council participants, session
    subjects, prototype session drivers, survey respondents, report voices, a project's
    cohort), the row AND the detail header render this group — identical anatomy everywhere:
    the vendored `.sl-avatar-group` overlap cluster, normally max 4 avatars, then one quiet
    `.sl-avatar-group__more` "+n" overflow chip. `personas` = resolved persona dicts (the
    services crew stubs or full records; falsy entries drop); `total` = the full participation
    count when the caller already truncated. Rows render at 18px, detail headers at 22px —
    same classes and overflow behavior at both sizes. A project header may deliberately pass
    `limit=None, linked=True`: its cohort is the subject of the page, so every involved persona
    stays visible and each portrait opens that persona. Dense rows keep the four-person default.

    NEGATIVE rule (deliberate, pinned by tests/test_persona_attribution.py): decision /
    hypothesis / note / asset records carry NO direct persona participation — their persona
    link is indirect, via the evidence they cite — so those rows and detail headers never
    render an avatar group. Returns "" for an empty cohort (a chip-less row, never a husk)."""
    from ._components import _avatar
    all_ps = [p for p in personas if p]
    ps = all_ps if limit is None else all_ps[:max(int(limit), 0)]
    if not ps:
        return raw("")
    n_more = max((total if total is not None else len(all_ps)) - len(ps), 0)

    def portrait(p: dict) -> Safe:
        avatar = raw(_avatar(p, size))
        persona_id = str(p.get("id") or "")
        name = str(p.get("display_name") or persona_id or t("persona"))
        if not linked or not persona_id:
            return avatar
        return h("a", {"class_": "sl-avatar-group__person",
                       "href": f"/personas/{_quote(persona_id, safe='')}",
                       "title": name, "aria-label": name}, avatar)

    return h("span", {"class_": "sl-avatar-group" + (" sl-avatar-group--linked" if linked else "")},
             fragment(*(portrait(p) for p in ps)),
             h("span", {"class_": "sl-avatar-group__more"}, f"+{n_more}") if n_more else None)


def entity_row(title: Any, *, href: str | None = None, visual: Any = "", badges: Iterable[Any] = (),
               meta: Iterable[Any] = (), desc: Any = "", id: str | None = None,
               drawer: bool = False, action: dict | None = None) -> Safe:
    """THE row atom (`sl-entity`, ux-contract §3.2 / C1): leading `visual` (icon/avatar,
    pass Safe html) · one-line ellipsized `title` with its status `badges` · optional
    muted `desc` line · right-aligned `meta` (counts, date, persona chips) in the
    trailing slot. Identical anatomy in the outline, the library, and search.

    Implementation over the vendored `.sl-entity` contract (visual / content(title,
    desc) / trailing): badges lead the trailing slot so a long, ellipsized title can
    never clip a status pill (the title span owns the overflow). `href` makes the row
    a link (`--button` hover affordance); `drawer=True` additionally opens that SAME
    canonical URL as the Notion-style slide-over (§8.1 — see slideover()). The
    per-kind visual/badge/meta mapping lives in primitive_row (the §3.2 table).

    `action` = {href, label, icon?, download?, target?} ends the trailing slot with the row's
    OWN secondary link (UX U8: an asset row's direct file download stays one click away).
    Anchors can't nest, so the row renders as a positioned <div> whose main target is a
    stretched overlay link — the same pattern as the outline's funnel chip."""
    from ._components import _icon
    badges = list(badges)
    meta = list(meta)
    content = h("div", {"class_": "sl-entity__content"},
                h("div", {"class_": "sl-entity__title"}, title),
                h("div", {"class_": "sl-entity__desc"}, desc) if desc else None)
    trailing = badges + meta
    if href and action:
        trailing.append(h("a", {"class_": "sl-entity__action", "href": action.get("href", "#"),
                                "download": action.get("download"), "target": action.get("target"),
                                "rel": "noopener" if action.get("target") else None,
                                "title": action.get("label"), "aria-label": action.get("label")},
                          raw(_icon(action.get("icon", "download")))))
    inner = fragment(
        h("span", {"class_": "sl-entity__visual"}, visual) if visual else None,
        content,
        h("span", {"class_": "sl-entity__trailing"}, fragment(*trailing)) if trailing else None)
    if href and action:
        plain = _re.sub(r"<[^>]+>", "", str(title))
        stretch = h("a", {"class_": "sl-entity__stretch", "href": href,
                          "aria-label": plain[:90] or None,
                          "data-drawer": href if drawer else None,
                          "data-drawer-title": plain[:90] if drawer else None})
        return h("div", {"class_": "sl-entity sl-entity--button", "id": id}, stretch, inner)
    if href:
        return h("a", {"class_": "sl-entity sl-entity--button", "id": id, "href": href,
                       "data-drawer": href if drawer else None, "data-drawer-title": None}, inner)
    return h("div", {"class_": "sl-entity", "id": id}, inner)


def primitive_row(kind: str, record: dict, store: Any = None, *, href: str | None = None,
                  drawer: bool = False, desc: Any = None) -> Safe:
    """THE per-kind row vocabulary (ux-contract §3.2 — one table, used everywhere): maps a
    primitive's record onto the entity_row anatomy (leading visual · title · status badges ·
    right meta). Library lists and search render through this; the dense
    project outline uses its own tag-free olrow variant: kind icon, title, avatar participation
    and timestamp, with status/form/count details deferred to filters and detail pages.

    The V2 craft pass (ux-contract §9 V2) capped every row at ≤2 trailing chips + the date —
    counts that duplicate the avatars/visual or repeat the kind label moved to the detail page.
    Persona ATTRIBUTION follows the one §10 W11 rule: every kind whose data carries persona
    participation leads its meta with the avatar_group (council participants, report voices,
    survey respondents, session subject, prototype session drivers); decision / hypothesis /
    note / asset carry none — see avatar_group's negative rule.

    | kind            | visual                | badges                  | meta right            |
    | council         | councils icon         | mode/round tag          | avatars · date        |
    | report/synthesis| report icon           | `Report`                | avatars · count · date|
    | decision        | flag                  | status pill             | evidence count · date |
    | survey          | plan icon             | lifecycle pill          | avatars · n responses |
    | session         | activity icon         | grounding · visual trace | avatar group · date  |
    | prototype       | prototype icon        | fidelity tag            | avatars · sessions n  |
    | asset           | the `.sl-file` FILE atom (V9): ext badge/thumb · filename+ext ·       |
    |                 | size · date meta · direction pill · ONE download/open affordance;     |
    |                 | compact row in Library, responsive gallery card in project detail     |
    | note / hypothesis| panel / target icon  | — / status pill         | date                  |

    Late imports keep this module's import graph a leaf (pages → ui, never the reverse). The
    per-kind dispatch + icon map use dict() kwargs / `in (…)` membership — the kind-vocabulary
    grep gates ban kind-literal dict heads and `== "<kind>"` comparisons in web/*.py.

    `desc` overrides the muted description line — cross-project lists (the Library) pass
    the owning project's title here; in a project-scoped context the per-kind default
    stands (e.g. the session's walked subject)."""
    from .. import presentation as _pres
    from ._components import _display_title, _icon, _label
    from ._presence import (decision_status_pill, hypothesis_status_pill, survey_status_pill,
                            synthesis_status_pill)
    rec = record or {}
    date = local_day(rec.get("created_at") or "") if rec.get("created_at") else ""
    icons = dict(council="councils", synthesis="syntheses", report="syntheses", decision="flag",
                 survey="plan", session="activity", prototype="prototype", flow="compass",
                 url_artifact="link", live_url="external", note="panel",
                 hypothesis="target", open_question="help")
    visual: Any = raw(_icon(icons.get(kind, "square")))
    title: Any = rec.get("title") or rec.get("text") or rec.get("name") or rec.get("id", "")
    kind_desc: Any = ""
    badges: list[Any] = []
    meta: list[Any] = [date] if date else []
    if kind in ("council",):
        title = _display_title(rec.get("prompt") or rec.get("title") or "")
        mode = rec.get("mode") or ""
        if mode in ("discovery", "evaluation", "decision"):
            badges.append(raw(_label(t("council_mode_" + mode), "var(--blue)")))
        pids = [p for p in dict.fromkeys(s.get("persona_id", "")
                                         for s in rec.get("statements") or []) if p]
        if store is not None and pids:
            meta.insert(0, avatar_group((store.get_persona(p) for p in pids[:4]),
                                        total=len(pids)))
    elif kind in ("synthesis", "report"):
        badges.append(raw(_label(t("synthesis_kind"), "var(--violet)")))
        # G2: the lifecycle pill — reports carry one (in_progress | done) like every
        # lifecycled kind; rows and the report cover show the same words.
        badges.append(raw(synthesis_status_pill(rec.get("status", "done"))))
        if rec.get("sections") is not None:
            meta.insert(0, raw(_label(t("n_sections", n=len(rec.get("sections") or [])))))
        else:
            meta.insert(0, raw(_label(t("chip_sources_n", n=len(rec.get("council_ids") or [])))))
        # the voices' personas (statements) lead the meta — same anatomy as council rows (W11)
        vpids = [p for p in dict.fromkeys(s.get("persona_id", "")
                                          for s in rec.get("statements") or []) if p]
        if store is not None and vpids:
            meta.insert(0, avatar_group((store.get_persona(p) for p in vpids[:4]),
                                        total=len(vpids)))
    elif kind == "decision":
        badges.append(raw(decision_status_pill(rec.get("status", "proposed"))))
        meta.insert(0, raw(_label(t("chip_evidence_n", n=len(rec.get("based_on") or [])))))
    elif kind == "survey":
        # V2: status + response count (≤2 trailing chips + date) — the question count
        # lives on the detail page. Persona-sourced respondents lead as the avatar group
        # (W11; the `personas`/`voices` crew rides services.list_surveys records).
        badges.append(raw(survey_status_pill(rec.get("status", "draft"))))
        meta.insert(0, raw(_label(t("n_responses", n=int(rec.get("response_count") or 0)))))
        if rec.get("personas"):
            meta.insert(0, avatar_group(rec["personas"], total=int(rec.get("voices") or 0)))
    elif kind == "session":
        persona = (store.get_persona(rec.get("persona_id", "")) or {}) if store is not None else {}
        title = persona.get("display_name") or rec.get("persona_id", "")
        # The subject walked (prototype/flow label): in the outline a session nests under its
        # subject row, but in a flat list (Library) the persona name alone says nothing.
        kind_desc = (rec.get("subject") or {}).get("label", "")
        if rec.get("grounded_verified"):
            badges.append(raw(_label(t("grounded_yes"), "var(--green)")))
        steps = list(rec.get("steps") or [])
        visual_trace = str(rec.get("visual_trace") or "")
        if not visual_trace and steps:
            captured = sum(bool((step.get("state") or {}).get("screenshot")) for step in steps)
            visual_trace = ("screen_replay" if captured == len(steps)
                            else "screen_partial" if captured else "text_only")
        trace_meta = ((t("session_screen_replay"), "var(--blue)")
                      if visual_trace == "screen_replay" else
                      (t("session_screen_partial"), "var(--amber)")
                      if visual_trace == "screen_partial" else
                      (t("session_text_only"), "var(--muted)")
                      if visual_trace == "text_only" else None)
        if trace_meta:
            badges.append(raw(_label(trace_meta[0], trace_meta[1])))
        # V2: the step count moved to the detail/slide-over — the avatar + grounded check +
        # date are what the row reader scans for. The subject persona renders through the ONE
        # avatar_group anatomy (W11) — a group of one, same classes as every other kind.
        meta = [avatar_group([persona]) if persona else None] + meta
    elif kind == "prototype":
        # fidelity tag · the session DRIVERS' avatar group (W11 — the `personas`/`voices`
        # crew rides services.prototype_participation) · the honest sessions count.
        if rec.get("fidelity"):
            badges.append(raw(_label(_pres.present(rec["fidelity"])["short"], "#00897b")))
        meta = [avatar_group(rec.get("personas") or [], total=int(rec.get("voices") or 0)),
                raw(_label(t("sessions_n", n=int(rec.get("n_sessions") or 0))))]
    elif kind == "url_artifact":
        title = rec.get("title") or rec.get("url") or rec.get("id", "")
        badges.append(raw(_label(t("artifact_kind_" + (rec.get("kind") or "url")), "var(--blue)")))
        snap = rec.get("snapshot") or {}
        badges.append(raw(_label(t("artifact_captured") if snap.get("ok") else t("artifact_capture_failed"),
                                 "var(--green)" if snap.get("ok") else "var(--muted)")))
        if rec.get("label"):
            meta.insert(0, raw(_label(rec["label"])))
        kind_desc = rec.get("url", "")
    elif kind == "live_url":
        title = rec.get("title") or rec.get("label") or rec.get("url") or rec.get("id", "")
        badges.append(raw(_label(t("live_surface"), "var(--green)")))
        kind_desc = rec.get("url", "")
    elif kind == "asset":
        # V9 (ux-contract §9): assets are FILES, not generic rows — the compact
        # `.sl-file--row` variant (ext badge/thumb identity, filename+ext title,
        # size · date · context meta, direction pill, ONE download/open affordance).
        from ._presence import file_card
        return raw(file_card(rec, store, row=True, href=href, drawer=drawer,
                             desc="" if desc is None else _re.sub(r"<[^>]+>", "", str(desc))))
    elif kind == "hypothesis":
        badges.append(raw(hypothesis_status_pill(rec.get("status", "open"))))
    elif kind == "open_question":
        status = rec.get("status", "open")
        labels = {"open": t("oq_status_open"), "resolved": t("oq_status_resolved")}
        if status in labels:
            badges.append(raw(_label(labels[status],
                                     "var(--amber)" if status == "open" else "var(--green)")))
    if rec.get("trace_health") == "orphaned":
        badges.append(raw(_label(t("chip_unused_after_phase_close"), "var(--amber)")))
    elif rec.get("trace_health") == "parked":
        badges.append(raw(_label(t("chip_parked"), "var(--muted)")))
    return entity_row(title, href=href, visual=visual, badges=badges,
                      desc=desc if desc is not None else kind_desc,
                      meta=[m for m in meta if m], drawer=drawer)


def likelihood(term: Any) -> Safe:
    """The vendored `.sl-likelihood` contract (ux-contract §9 V3): a labeled percentage +
    a 40px mini-bar whose FILL encodes the probability, toned at the design-system
    thresholds (≥70 high/green, ≥40 mid/amber, else low/red). Accepts a canonical level
    term ("likely"), an alias, or a raw 0..1 number (the bare "0.6" the owner flagged);
    the level's localized name rides the tooltip. An unresolvable token renders as a quiet
    plain label — a page never crashes over a chip. Mirrors the DS Likelihood docs entry."""
    from .. import artifacts as _A
    if isinstance(term, dict):                  # the canonical stored shape {value, label}
        term = term.get("value", term.get("label"))
    res = _A.resolve_likelihood(term)
    if res is None:
        return h("span", {"class_": "lbl lbl-soft"}, str(term))
    p = round(float(res["value"]) * 100)
    tone = "high" if p >= 70 else "mid" if p >= 40 else "low"
    meta = next((r for r in _A.likelihood_terms() if r["term"] == res.get("label")), None)
    return h("span", {"class_": f"sl-likelihood sl-likelihood--{tone}", "style": f"--p:{p}",
                      "title": t(meta["label_key"]) if meta else None},
             h("span", {"class_": "sl-likelihood__val"}, f"{p} %"),
             h("span", {"class_": "sl-likelihood__bar"},
               h("span", {"class_": "sl-likelihood__fill"})))


def _fmt_day(iso: str) -> str:
    """'11 Jun' — the same compact day the outline rows show (_graph_outline._fmt_ts), so a
    primitive carries ONE date format in every surface (library, outline — C5/C10).
    Falls back to the raw YYYY-MM-DD prefix for non-ISO input."""
    try:
        from datetime import datetime
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return f"{dt.day} {dt:%b}"
    except Exception:
        return iso[:10]


fmt_day = _fmt_day                       # public alias (palette/result rows etc.)


def fmt_date(iso: str) -> str:
    """'11 Jun 2026' — absolute dates outside rows (rail Created, provenance). One human
    date language app-wide (round-3 craft pass): rows say '11 Jun', metadata adds the year,
    nothing prints raw ISO."""
    try:
        from datetime import datetime
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return f"{dt.day} {dt:%b} {dt:%Y}"
    except Exception:
        return iso[:10]


def fmt_ts(iso: str) -> str:
    """'11 Jun · 05:47' — day + time, the outline rows' timestamp idiom (_graph_outline._fmt_ts),
    for feeds and provenance lines that need the minute."""
    try:
        from datetime import datetime
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return f"{dt.day} {dt:%b} · {dt:%H:%M}"
    except Exception:
        return iso[:16].replace("T", " ")


def _local_time(iso: str, *, mode: str, fallback: str, cls: str = "") -> Safe:
    """Semantic instant with an honest UTC fallback and browser-local enhancement."""
    value = str(iso or "")
    canonical = value
    valid_instant = False
    try:
        from datetime import datetime, timezone
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        canonical = dt.isoformat()
        valid_instant = True
    except Exception:
        pass
    classes = "sl-local-time" + (f" {cls}" if cls else "")
    return h("time", {"class_": classes, "datetime": canonical,
                      "data-local-time": mode if valid_instant else None},
             t("time_utc", value=fallback) if valid_instant else fallback)


def local_ts(iso: str, *, cls: str = "") -> Safe:
    """Render a timestamp in the reader's actual browser timezone.

    Stored Sonaloop timestamps are UTC. Formatting them on the server made a Swiss
    user's 15:50 activity look like 13:50 whenever the host ran in UTC. ``APP_JS``
    replaces the explicit UTC no-JS fallback with a locale-aware value and timezone
    tooltip. Naive persisted values are historical UTC values, never browser-local.
    """
    value = str(iso or "")
    return _local_time(value, mode="datetime", fallback=fmt_ts(value), cls=cls)


def local_date(iso: str, *, cls: str = "") -> Safe:
    """Local calendar date for an absolute timestamp; true YYYY-MM-DD values stay fixed."""
    value = str(iso or "")
    if "T" not in value and not _re.search(r"\d{2}:\d{2}", value):
        return h("time", {"class_": ("sl-local-time" + (f" {cls}" if cls else "")),
                          "datetime": value}, fmt_date(value))
    return _local_time(value, mode="date", fallback=fmt_date(value), cls=cls)


def local_day(iso: str, *, cls: str = "") -> Safe:
    """Compact local day/month for an instant; true date-only domain values stay fixed."""
    value = str(iso or "")
    if "T" not in value and not _re.search(r"\d{2}:\d{2}", value):
        return h("time", {"class_": ("sl-local-time" + (f" {cls}" if cls else "")),
                          "datetime": value}, fmt_day(value))
    return _local_time(value, mode="day", fallback=fmt_day(value), cls=cls)


def slideover(url: str, trigger: Any, *, title: str = "") -> Safe:
    """The Notion-style slide-over (`sl-drawer--wide`, ux-contract §8.1 / C2): wrap `trigger`
    so a click opens `url` — the CANONICAL detail URL — as a slide-over with the page's FULL
    content. The drawer JS (web/_components.py) fetches the route's `?slide=1` fragment
    variant (same renderer, web/_slide.py) and pushState's the canonical URL: reload/direct
    load renders the full page, Esc/scrim/back restores the previous URL, and the header's
    expand control is a real navigation. The plain href keeps the deep link, so the
    slide-over is navigation sugar, never the only address (middle-click / no-JS follow it)."""
    return h("a", {"href": url, "data-drawer": url, "data-drawer-title": title or None}, trigger)


def group_header(label: Any, count: int | None = None) -> Safe:
    """A quiet group separator between list rows (the linear-list `.group` contract — G3,
    co-located in web/_routes_lists.py): a muted heading + optional count. Used wherever rows
    interleave with date/section groups."""
    return h("div", {"class_": "group"}, label,
             h("span", {"class_": "cnt"}, str(count)) if count is not None else None)


def tabs(items: Iterable[dict[str, Any]], active: str) -> Safe:
    """Underline tabs (`sl-tabs`) for in-page surface switching (the Library browser,
    detail bodies). `items`: dicts with `key`, `label`, `href` (+ optional `icon`,
    Safe html); `active` selects by key. Mirrors React <Tabs variant="underline">."""
    return h("div", {"class_": "sl-tabs", "role": "tablist"},
             fragment(*(h("a", {"class_": "sl-tab" + (" is-active" if it["key"] == active else ""),
                                "href": it["href"], "role": "tab",
                                "aria-selected": "true" if it["key"] == active else "false"},
                          raw(it["icon"]) if it.get("icon") else None, it["label"])
                        for it in items)))
