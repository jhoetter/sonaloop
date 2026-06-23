from __future__ import annotations

import re
from collections import Counter, defaultdict

from .. import services
from ..storage import Store
from ._i18n import t
from ._components import (
    _esc, _icon, _avatar, _label, _md, _md_inline, _srcchips, _prose, _rec_row_n,
    _effort_impact, _star, _study_lead,
)
from ._render import render_findings, render_statement, render_statements
from .. import artifacts as _A
from . import ui
from ._vm import study_head
from ._html import h, raw, fragment, register_css


# Co-located CSS (spec/roadmap.md R3): analytics charts + voices/Stimmen cockpit.
register_css(r"""
/* ---- analytics (Linear-style insight cards) ---- */
/* Since §11 T5 (J1) the charts row is ONE insight card; it spans the full content column —
   the old 2-col .insights grid left the lone card beside a column of whitespace (Round 5). */
.insight{border:1px solid var(--line);border-radius:var(--radius);background:var(--panel);padding:16px}
.insight h3{margin:0 0 2px;font-size:var(--t-body)}
.ihint{color:var(--muted);font-size:var(--t-sm);margin:0 0 14px}
.kpi{display:flex;align-items:baseline;gap:6px;margin:2px 0 10px}
.kpi b{font-size:var(--t-xl);font-weight:700;letter-spacing:-.01em}.kpi span{color:var(--muted);font-size:var(--t-sm)}
.stacked{display:flex;height:12px;border-radius:var(--radius-sm);overflow:hidden;background:var(--line-2);border:1px solid var(--line)}
.stacked i{display:block;height:100%}
.stacked.thin{height:8px}
.legend{display:flex;flex-wrap:wrap;gap:12px;margin:11px 0 0;font-size:var(--t-sm);color:var(--muted)}
.legend span{display:inline-flex;align-items:center;gap:6px}
.legend i{width:9px;height:9px;border-radius:2px;display:inline-block}
.brow{display:grid;grid-template-columns:118px 1fr 30px;gap:8px;align-items:center;padding:5px 0;font-size:var(--t-sm)}
.brow .blab{color:var(--ink);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.brow .btrack{height:9px;border-radius:var(--radius-sm);background:var(--line-2);overflow:hidden}
.brow .btrack i{display:block;height:100%}
.brow .bval{text-align:right;color:var(--muted);font-variant-numeric:tabular-nums}
/* per-persona enthusiasm rows (V3): plain rows — avatar · name · diverging bar · score.
   The bar is zero-CENTERED; its length encodes |score|, its color the stance sign. */
.prow{display:grid;grid-template-columns:150px 1fr 42px;gap:12px;align-items:center;padding:6px 0}
.prow .pwho{display:flex;align-items:center;gap:8px;overflow:hidden;text-decoration:none;color:var(--ink)}
.prow .pwho:hover span{color:var(--accent)}
.prow .pwho span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:var(--t-sm)}
.prow .ps{text-align:right;font-size:var(--t-sm);font-weight:600;font-variant-numeric:tabular-nums}
.dvg{position:relative;display:block;height:7px;border-radius:var(--radius-full);background:var(--line-2);overflow:hidden}
.dvg i{position:absolute;top:0;bottom:0;border-radius:var(--radius-full)}
.dvg::after{content:"";position:absolute;left:50%;top:-1px;bottom:-1px;width:1px;background:var(--faint);opacity:.55}
.area svg{display:block;width:100%;height:140px}
.area .ln{fill:none;stroke:var(--accent);stroke-width:2}
.area .fl{fill:var(--accent);opacity:.10}
.area .dot{fill:var(--accent)}
.axis{display:flex;justify-content:space-between;color:var(--muted);font-size:var(--t-xs);margin-top:4px}
""")

# Co-located CSS (spec/roadmap.md R3): the synthesis report styles (was _SYN_STYLE in body).
register_css(r"""

.syn-head h1{font-size:var(--t-xl);line-height:1.2;letter-spacing:-.02em;font-weight:650;margin:0 0 8px;display:-webkit-box;-webkit-box-orient:vertical;-webkit-line-clamp:3;overflow:hidden}
.syn-head h1 svg{width:21px;height:21px;color:var(--accent);margin-right:8px;vertical-align:-2px}
.syn-goal{color:var(--muted);font-size:var(--t-md);line-height:1.5;max-width:var(--measure-prose);margin:0 0 14px}
.syn-meta{display:flex;flex-wrap:wrap;gap:7px;align-items:center}
.mchip{font-size:var(--t-sm);color:var(--muted);border:1px solid var(--line);background:var(--panel-2);border-radius:var(--radius-sm);padding:3px 10px}
.block{margin:40px 0 0;padding-top:24px;border-top:1px solid var(--line)}
.block>.bh{font-size:var(--t-sm);text-transform:uppercase;letter-spacing:.06em;color:var(--muted);font-weight:600;margin:0 0 16px;display:flex;align-items:center;gap:8px}
.block>.bh .cnt{color:var(--accent);background:var(--accent-weak);border-radius:var(--radius-sm);padding:1px 9px;font-size:var(--t-xs)}details.block>summary.bh{cursor:pointer;margin-bottom:0}details.block[open]>summary.bh{margin-bottom:16px}
.syn-main section{padding:0;overflow:visible}
.syn-main .block{margin-top:40px;padding-top:24px}
.cgrid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}
.ref-list{display:flex;flex-direction:column;gap:6px}
.ref-row{display:flex;align-items:center;gap:8px;padding:8px 12px;border:1px solid var(--line);border-radius:var(--radius);background:var(--panel);text-decoration:none;color:var(--ink)}
.ref-row:hover{border-color:var(--accent)}
.ref-n{font-weight:700;color:var(--accent);font-size:var(--t-sm);flex:none;width:26px}
.ref-t{flex:1;font-size:var(--t-body);line-height:1.35;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.ref-bar{flex:0 0 150px}
.ref-meta{flex:none;color:var(--muted);font-size:var(--t-sm);line-height:1.5;font-variant-numeric:tabular-nums}
.ref-go{flex:none;color:var(--muted)}
.ccard{border:1px solid var(--line);border-radius:var(--radius-lg);padding:14px 16px;background:var(--panel);display:flex;flex-direction:column;gap:9px}
.cc-top{display:flex;align-items:center;gap:8px}
.cc-n{font-weight:700;color:var(--accent);font-size:var(--t-sm);letter-spacing:.03em}
.cc-bar{flex:1}
.cc-title{font-size:var(--t-md);line-height:1.35;margin:0;font-weight:600}
.cc-title a{color:var(--ink)}.cc-title a:hover{color:var(--accent)}
.cc-take{color:var(--muted);font-size:var(--t-body);line-height:1.5;margin:0}
.cc-chips{display:flex;gap:6px;flex-wrap:wrap}
.cc-more>summary{cursor:pointer;color:var(--muted);font-size:var(--t-sm);list-style:none}
.cc-more>summary::-webkit-details-marker{display:none}
.cc-more>summary::before{content:"\25B8 Exec-Summary";color:var(--muted)}
.cc-more[open]>summary::before{content:"\25BE Exec-Summary"}
.cc-es{font-size:var(--t-sm);line-height:1.6;margin-top:8px;border-top:1px dashed var(--line);padding-top:8px}
.cc-es h3{font-size:var(--t-sm);text-transform:uppercase;letter-spacing:.04em;color:var(--muted);margin:10px 0 4px}
.cc-es p{margin:0 0 7px}.cc-es ul{margin:0 0 7px;padding-left:18px}
.cc-jump{font-weight:600;color:var(--accent);font-size:var(--t-body)}
.syn-main [id]{scroll-margin-top:26px}
/* verdict/POV card — the structural opener of every report (ux-contract §3.6a). The card
   carries the LEAD layer of the §11 T3 hierarchy: headline finding at t-lg/600, the opening
   sentences at the t-prose reading voice, wrapped at the prose measure. */
.syn-verdict{margin:8px 0 24px}
.syn-verdict .sl-card__title{font-size:var(--t-lg);line-height:1.35;margin-top:.5em;max-width:var(--measure-prose)}
.syn-verdict .sl-card__body{margin-top:.4em;font-size:var(--t-prose);line-height:1.6}
.syn-verdict .sl-card__body p{margin:0;max-width:var(--measure-prose)}
/* effort·impact chart is a design-system component now (.sl-quad/.sl-legend, vendored from
   sonaloop-design via _components_css.py) — no local chart CSS here. */
.reclist .rec{display:flex;gap:12px;padding:8px;border-bottom:1px solid var(--line-2);scroll-margin-top:72px}
.reclist .rec:last-child{border-bottom:none}
.recnum{flex:0 0 auto;width:22px;height:22px;border-radius:50%;background:var(--accent-weak);color:var(--accent);font-size:var(--t-sm);font-weight:700;display:flex;align-items:center;justify-content:center}
.reclist .rec:target{background:var(--accent-weak);border-radius:var(--radius)}
.axchip{display:inline-block;margin-top:6px;font-size:var(--t-xs);color:var(--muted);border:1px solid var(--line);border-radius:var(--radius-sm);padding:1px 7px}
@media(max-width:1180px){.syn-rail{display:none}}
@media(max-width:740px){.cgrid{grid-template-columns:1fr}.syn-head h1{font-size:var(--t-xl)}}
""")

# ----------------------------- chart primitives ----------------------------- #
# Vanilla inline charts (CSS/conic-gradient/SVG) — no build step, dark-mode safe.
# Deliberately NOT sonaloop._charts (the vendored design-system library): those functions emit
# complete <figure class="sl-chart"> blocks with a coupled title/legend and positional series
# colours, while these are bare composable FRAGMENTS — a thin stance-coloured strip that embeds
# inside per-row comparisons (.ref-row, the session funnel), and bars/area sized to the insight
# card. Where a full design-system figure fits, we delegate instead (see _components._effort_impact
# → _charts.effort_impact). The web carries NO donut (§10 W9) and, since §11 T5 (J1 decided), NO
# page-level distribution strip either: the scaled stance BARS are the one distribution encoding
# on council/synthesis blocks; the deck keeps its single donut card (services/_synthesis_pptx).


def _stacked(parts: list[tuple], thin: bool = False) -> str:
    """parts: [(value, color, label)]. Renders a single horizontal stacked bar."""
    total = sum(v for v, _, _ in parts) or 1
    segs = [h("i", {"style": f"width:{v / total * 100:.3f}%;background:{c}", "title": f"{lbl}: {v}"})
            for v, c, lbl in parts if v]
    return h("div", {"class_": f'stacked{" thin" if thin else ""}'}, segs)


def _legend(parts: list[tuple]) -> str:
    """Legend rows for the nonzero parts only (V3: an "Oppose 0" entry is noise — the scale's
    zero categories never earn a legend line)."""
    return h("div", {"class_": "legend"},
             [h("span", {}, h("i", {"style": f"background:{c}"}), f"{lbl} {v}")
              for v, c, lbl in parts if v])


def _diverging(score: float, maxv: float, color: str) -> str:
    """A compact zero-centered diverging bar (V3): the fill grows from the CENTER, its length
    ∝ |score| / maxv, its color the caller's stance color — so the bar ENCODES the value
    instead of painting a full-width line for every row."""
    pct = min(abs(score) / (maxv or 1), 1.0) * 50
    side = "right:50%" if score < 0 else "left:50%"
    return h("span", {"class_": "dvg"},
             h("i", {"style": f"{side};width:{pct:.1f}%;background:{color}"}))


def _hbars(rows: list[tuple], maxv: int | None = None) -> str:
    """rows: [(label, value, color)]. Horizontal bar chart — ALL rows share one max-count
    scale (the longest bar = the largest count; every other length is proportional)."""
    mx = maxv or max((v for _, v, _ in rows), default=0) or 1
    return fragment(*(
        h("div", {"class_": "brow"},
          h("span", {"class_": "blab", "title": lbl}, lbl),
          h("span", {"class_": "btrack"}, h("i", {"style": f"width:{v / mx * 100:.2f}%;background:{c}"})),
          h("span", {"class_": "bval"}, str(v)))
        for lbl, v, c in rows))


def _area(points: list[tuple], w: int = 560, ht: int = 140) -> str:
    """points: [(label, value)]. Area + line chart (SVG, viewBox-scaled)."""
    if not points:
        return h("p", {"class_": "muted small"}, t("no_data"))
    n = len(points); mx = max(v for _, v in points) or 1
    pad = 6
    def x(i): return pad + (i * (w - 2 * pad) / (n - 1 if n > 1 else 1))
    def y(v): return ht - pad - (v / mx * (ht - 2 * pad))
    pts = [(x(i), y(v)) for i, (_, v) in enumerate(points)]
    line = "M" + " L".join(f"{px:.1f},{py:.1f}" for px, py in pts)
    fill = f"M{pts[0][0]:.1f},{ht - pad} L" + " L".join(f"{px:.1f},{py:.1f}" for px, py in pts) + f" L{pts[-1][0]:.1f},{ht - pad} Z"
    dots = [h("circle", {"class_": "dot", "cx": f"{px:.1f}", "cy": f"{py:.1f}", "r": "2"}) for px, py in pts]
    first, last = points[0][0], points[-1][0]
    return fragment(
        h("div", {"class_": "area"}, h("svg", {"viewBox": f"0 0 {w} {ht}", "preserveAspectRatio": "none"},
          h("path", {"class_": "fl", "d": fill}), h("path", {"class_": "ln", "d": line}), fragment(*dots))),
        h("div", {"class_": "axis"}, h("span", {}, first), h("span", {}, last)))


# --------------------- contextual analytics (council / synthesis) --------------------- #
# Charts live ON the council and the synthesis, computed from that scope's sessions.
# Votes ARE stances (suggestions/stance_scale.json — the ONE positivity vocabulary): chart order
# (+2 → −2), colors and labels all come from the scale; no hardcoded vote vocabulary here.
def _vote_chart_parts(cnt: Counter) -> list[tuple]:
    """Counter keyed by stance VALUE → [(count, color, label)] in scale order — every term representable."""
    return [(cnt.get(r["value"], 0), r["color"], t(r["label_key"])) for r in _A.stance_terms()]


def _vote_parts(sessions: list[dict]) -> tuple[Counter, list[tuple]]:
    """Bucket votes by canonical stance VALUE (compatibility tokens resolve via the scale's aliases; an
    unresolvable token lands in its value bucket via label_raw — never dropped from the charts)."""
    tot: Counter = Counter()
    for s in sessions:
        for v in s.get("votes", []):
            st = _A.vote_stance(v)
            if st is not None:
                tot[st["value"]] += 1
    return tot, _vote_chart_parts(tot)


def _dist_bars(sessions: list[dict]) -> str:
    """The ONE distribution encoding on council/synthesis blocks (ux-contract §11 T5 — J1
    decided in the W9 direction): scaled stance BARS, length ∝ count. Bucketed from the
    statements' stances; a chain whose statements carry no stances falls back to the votes
    (votes ARE stances), so the distribution still shows exactly once. The proportional
    strip + legend that co-encoded the same numbers beside the bars retired; per-row
    comparison strips (one DIFFERENT distribution per cited council) are a comparison,
    not a re-encoding, and stay."""
    bars = _stance_dist_html(sessions)
    if bars:
        return bars
    _tot, parts = _vote_parts(sessions)
    rows = [(lbl, n, c) for n, c, lbl in parts if n]
    return _hbars(rows) if rows else ""


def _session_parts(s: dict) -> list[tuple]:
    """One session's stance distribution as chart parts: the votes where they exist, else the
    statements' stances (a discovery council carries no votes) — so a comparison row never
    paints an EMPTY track as if the data were missing."""
    _tot, parts = _vote_parts([s])
    if any(n for n, _, _ in parts):
        return parts
    cnt: Counter = Counter(int((st.get("stance") or {}).get("value") or 0)
                           for st in _A.council_statements(s) if st.get("stance"))
    return _vote_chart_parts(cnt)


def _personas_by_sentiment_html(store: Store, sessions: list[dict]) -> str:
    """Per-persona enthusiasm rows (V3 redesign): avatar · name · a compact zero-centered
    DIVERGING bar (length ∝ |score|, color from the nearest stance bucket) · the score at
    the bar's end. Replaces the full-width stacked strips (whose length encoded nothing)
    and the boxed persona cards."""
    pv: dict = defaultdict(list)                     # persona → resolved stance VALUES
    for s in sessions:
        for v in s.get("votes", []):
            st = _A.vote_stance(v)
            if st is not None:
                pv[v.get("persona_id")].append(st["value"])
    if not pv:
        return ""
    personas = {p["id"]: p for p in services.list_personas(store=store)}
    # score = the MEAN of the stance values (−2..+2) — no token-specific coefficients
    data = sorted(((pid, sum(vals) / len(vals)) for pid, vals in pv.items()),
                  key=lambda x: x[1], reverse=True)
    maxv = max((abs(r["value"]) for r in _A.stance_terms()), default=2) or 2
    rows = []
    for pid, score in data:
        p = personas.get(pid)
        name = p["display_name"] if p else pid
        av = _avatar(p, 22) if p else ""
        # the score's color = the NEAREST scale value's color (value-bucketed, no keyword matching)
        col = min(_A.stance_terms(), key=lambda r: abs(r["value"] - score))["color"]
        rows.append(h("div", {"class_": "prow"},
                      h("a", {"class_": "pwho", "href": f'/personas/{pid}'}, av, h("span", {}, name)),
                      raw(_diverging(score, maxv, col)),
                      h("span", {"class_": "ps", "style": f"color:{col}"}, f"{score:+.1f}")))
    return fragment(*rows)


def _stance_dist_html(sessions: list[dict]) -> str:
    # Bucketed by the canonical stance VALUE (the five scale buckets via artifacts.stance_meta) —
    # stored label strings (compatibility free labels, label_raw tokens) never classify a contribution.
    sb: Counter = Counter()
    for s in sessions:
        for st in _A.council_statements(s):
            stv = st.get("stance")
            if not stv:
                continue
            sb[int(stv.get("value") or 0)] += 1
    rows = [(t(_A.stance_meta(v)["label_key"]), n, _A.stance_meta(v)["color"]) for v, n in sb.most_common()]
    return _hbars(rows) if rows else ""


def _sentiment_section(store: Store, sessions: list[dict], sid: str = "sentiment",
                       title: str | None = None, chain: bool = False,
                       overview: bool = True) -> str | None:
    """Reusable sentiment analytics block, embedded ON a council or synthesis. `overview=False`
    keeps only the per-persona breakdown — used when the page already opened with the
    sentiment/stance charts row (§3.6), so nothing renders twice. `chain=True` words the hint
    for a council chain instead of a single session. The per-council comparison rows moved
    onto the cited-councils reference rows (Round 5: councils are named ONCE per page)."""
    if title is None:
        title = t("sentiment_block")
    sessions = [s for s in sessions if s]
    tot, parts = _vote_parts(sessions)
    nvotes = sum(v for v, _, _ in parts)
    has_turns = any(_A.council_statements(s) for s in sessions)
    if not nvotes and not has_turns:
        return None
    scope = t("sentiment_scope_chain") if chain else t("sentiment_scope_session")
    blocks = [h("p", {"class_": "ihint"}, t("sentiment_intro", scope=scope))]
    if overview:                                   # the ONE distribution encoding (§11 T5): scaled bars
        sd = _dist_bars(sessions)
        if sd:
            blocks.append(sd)
    pbs = _personas_by_sentiment_html(store, sessions)
    if pbs:
        blocks.append(fragment(h("p", {"class_": "ihint", "style": "margin-top:18px"}, t("personas_by_sentiment")), pbs))
    if len(blocks) == 1:                       # nothing but the intro hint → no block at all
        return None
    return h("div", {"class_": "sec", "id": sid}, h("h2", {}, title), fragment(*blocks))


def _verdict_split(syn: dict) -> tuple[str, str]:
    """The ONE splitter for the verdict lead vs the remaining exec prose (round-3 H1): returns
    (lead, rest). The verdict card renders `lead` (2-3 sentences cut from the executive opening,
    sentence boundaries only before an uppercase start, so 'Min.' or '+40 Min. wegen …' never
    splits); the exec-summary section renders `rest` — the same sentences never appear twice on
    one screen. Both consumers MUST go through this function so the split can't drift apart."""
    text = (syn.get("gesamtbild") or "").strip()
    first_para, _, tail = text.partition("\n\n")
    sentences = [s for s in re.split(r"(?<=[.!?])\s+(?=[«„\"'(]?[A-ZÄÖÜ])", first_para.strip()) if s]
    lead, used = "", 0
    if sentences:
        lead, used = sentences[0], 1
        for s in sentences[1:3]:
            if len(lead) + len(s) > 460:
                break
            lead = f"{lead} {s}"
            used += 1
    rest_first = " ".join(sentences[used:]).strip()
    rest = "\n\n".join(p for p in (rest_first, tail.strip()) if p)
    return lead, rest


# Clause boundaries the headline may end on: a sentence end BEFORE an uppercase start (the
# `_verdict_split` guard — '+40 Min. wegen …' never splits), a colon/semicolon, a spaced dash.
_HEADLINE_CUT = re.compile(r"(?<=[.!?])\s+(?=[«„\"'(]?[A-ZÄÖÜ])|(?<=[:;])\s+|\s+[—–]\s+")


def _headline(text: str, cap: int = 200) -> str:
    """The verdict headline (Round 5 craft finish): never an ellipsized mid-sentence cut. Short
    text renders whole; long text ends at the LAST clean clause boundary inside the cap — the
    full finding always follows verbatim further down the page, so nothing is lost. Only when
    no boundary exists at all does the full headline render and simply wrap within the prose
    measure (`.syn-verdict .sl-card__title` carries max-width) instead of truncating to '…'."""
    s = " ".join((text or "").split())
    if len(s) <= cap:
        return s
    cuts = [m.start() for m in _HEADLINE_CUT.finditer(s) if m.start() <= cap]
    return s[:cuts[-1]].rstrip(" ,;:") if cuts else s


def _verdict_card(syn: dict) -> str:
    """The verdict/POV card that OPENS a report (ux-contract §3.6a): a crisp headline finding
    (the first key_problem) as the card title where one exists, plus the 2-3 sentence lead the
    shared `_verdict_split` cuts from the executive opening. Without an exec opening the first
    recommendation stands in as the title. Pure derivation from authored data — nothing new is
    written, the NON-consumed prose still follows further down (H1: never the same sentences)."""
    findings = _A.synthesis_findings(syn)
    heads = [f for f in findings if f.get("kind") in ("key_problem",)]
    head_text = heads[0].get("text", "") if heads else ""
    lead, _ = _verdict_split(syn)
    if not lead:                                       # no exec opening → a recommendation stands in
        recs = [f for f in findings if f.get("kind") in ("recommendation",)]
        head_text = head_text or (recs[0].get("text", "") if recs else "")
    if not head_text and not lead:
        return ""
    return h("div", {"class_": "sl-card syn-verdict", "id": "verdict"},
             h("div", {"class_": "sl-eyebrow"}, t("verdict_h")),
             (h("div", {"class_": "sl-card__title"}, raw(_md_inline(_headline(head_text))))
              if head_text else None),
             h("div", {"class_": "sl-card__body"}, raw(_md(lead))) if lead else None)


def _charts_row(sessions: list[dict]) -> str:
    """The stance distribution under the verdict card (§3.6b, single-encoded per §11 T5 — J1):
    ONE insight card with the scaled stance bars over the cited council chain, spanning the
    full content column (Round 5 finish: the retired second card left a lone half-width card
    beside whitespace — with one card there is no grid, the card IS the row). "" when the
    chain carries neither votes nor stanced statements."""
    sessions = [s for s in sessions if s]
    bars = _dist_bars(sessions)
    if not bars:
        return ""
    # card title names the SCOPE (the cited chain) — the section heading above the row
    # already says "Sentiment", repeating it verbatim taught nothing (round-3 craft pass)
    return h("div", {"class_": "insight"}, h("h3", {}, t("sentiment_over_chain")), raw(bars))


def _persona_voices_html(store: Store, pid: str) -> str:
    """This persona's ACTUAL council statements — the ONE place their words live (no synthesis re-host;
    spec/artifact-cross-references.md). Each card carries a cross-ref deep-link back to the council."""
    cards = []
    for c in store.list_council_sessions():
        for st in (c.get("statements") or []):
            if st.get("persona_id") != pid:
                continue
            # On the persona's OWN page the identity is implied — drop the repeated avatar/name/context
            # and lead each card with the VARYING info instead: which council it was said in.
            src = h("a", {"class_": "turn-src", "href": f'/councils/{c["id"]}'},
                    raw(_icon("councils")), " ", (c.get("prompt", "") or "—")[:72])
            cards.append(render_statement(st, store, head_extra=src, show_persona=False))
    if not cards:
        return ""
    return h("div", {"class_": "sec", "id": "stimmen"}, h("h2", {}, t("voices_in_analyses")),
             h("div", {"style": "display:flex;flex-direction:column;gap:12px"}, fragment(*cards)))


# --------------------------- synthesis report --------------------------- #


def _synthesis_html(store: Store, syn: dict, *, embed: bool = False):
    # embed=True omits the bespoke syn-head so the content can sit inside the unified report shell
    # (rp-cover + report typography) — spec/unified-synthesis-report.md §3 (one renderer).
    done = syn.get("status", "done") == "done"
    sec = []  # (id, short_label, html)

    def _block(bid, label, inner):                            # the shared section wrapper
        return h("div", {"class_": "block", "id": bid}, h("h2", {"class_": "bh"}, label), inner)

    syn_sessions = [store.get_council_session(cid) for cid in syn.get("council_ids", [])]
    # 1) Structure before prose (ux-contract §3.6): the derived verdict/POV card opens the report,
    # the sentiment + stance charts row follows — only THEN the authored prose (clamped).
    if (verdict := _verdict_card(syn)):
        sec.append(("verdict", t("verdict_h"), verdict))
    if (charts := _charts_row(syn_sessions)):
        sec.append(("charts", t("sentiment_block"), _block("charts", t("sentiment_block"), charts)))
    # 2) Executive Summary — the unified Question → Answer lead (shared with the council 'finding'),
    # fed by the shared study view-model so council/synthesis never branch on field names. Long
    # authored bodies clamp at the section threshold (C6) — depth stays, dosed. When the verdict
    # card above already consumed the opening sentences, the section starts from the first
    # NON-consumed sentence (round-3 H1: one screen never repeats prose verbatim); when the card
    # consumed EVERYTHING, the honest fallback is no echo block at all — the verdict IS the summary.
    if syn.get("gesamtbild"):
        vm = study_head(syn, is_synthesis=True)
        answer_md = vm["answer_md"]
        if verdict:
            lead, rest = _verdict_split(syn)           # the SAME splitter the card rendered from
            if lead:
                answer_md = rest
        if answer_md.strip():
            sec.append(("exec", t("summary"), _study_lead(
                ui.clamp(raw(_md(answer_md)), threshold=ui.SECTION_CLAMP),
                vm["answer_label"], question=vm["question"], qlabel=t("question"))))
    # 2) Cited evidence — councils are DECOUPLED: this synthesis is a standalone answer that may
    # CITE councils (or none). The reference rows are the ONE place the cited councils are named
    # (Round 5 finish: the per-council breakdown rows named the same councils a second time —
    # merged). With >1 cited councils each row carries that council's thin stance strip: N
    # DIFFERENT distributions side by side are a comparison, not the §11 T5 re-encoding (a
    # single cited council's strip WOULD re-encode the chain bars above, so it stays bare).
    belege = None
    cited = [c for c in syn_sessions if c]
    # a comparison needs >1 councils WITH stance data: when only one carries any, its lone
    # strip would just re-encode the chain bars above (the chain IS that one council)
    row_parts = {c["id"]: _session_parts(c) for c in cited}
    compare = sum(1 for p in row_parts.values() if any(v for v, _, _ in p)) > 1
    ref_rows = []
    for i, c in enumerate(cited, 1):
        prompt = c.get("prompt") or c["id"]
        parts = row_parts[c["id"]] if compare else []
        strip = (h("span", {"class_": "ref-bar"}, _stacked(parts, thin=True))
                 if any(v for v, _, _ in parts) else None)
        meta = f'{len(c.get("persona_ids", []))} P · {ui.fmt_day(c.get("created_at", ""))}'
        ref_rows.append(h("a", {"class_": "ref-row", "href": f'/councils/{c["id"]}'},
                          h("span", {"class_": "ref-n"}, f"C{i}"),
                          # full prompt; .ref-t ellipsizes at the row edge (a hard [:96] cut used
                          # to land mid-word once the row widened) — title carries the whole text
                          h("span", {"class_": "ref-t", "title": prompt}, prompt),
                          strip,
                          h("span", {"class_": "ref-meta"}, meta),
                          h("span", {"class_": "ref-go"}, raw(_icon("arrowRight")))))
    if ref_rows:
        # a plain block (no longer collapsed): since the rows carry the per-council comparison,
        # hiding them behind a <details> would hide the one distribution comparison on the page
        belege = ("belege", t("councils"),
                  h("div", {"class_": "block", "id": "belege"},
                    h("h2", {"class_": "bh"},
                      t("councils_overview"), " ", h("span", {"class_": "cnt"}, str(len(ref_rows)))),
                    h("p", {"class_": "muted small", "style": "margin:6px 0 10px"}, t("evidence_decoupled_note")),
                    h("div", {"class_": "ref-list"}, fragment(*ref_rows))))
    # Finding LIST sections (key_problems/pain_solvers/open_questions/shortlist) now render through the
    # ONE finding renderer — id + label from finding_kinds.json, prose via _prose (spec/unified-…).
    _findings = _A.synthesis_findings(syn)

    def _fsec(kind, label, toc=None):        # id from data (finding_kinds.json); label = static i18n
        items = [f for f in _findings if f.get("kind") == kind]
        if not items:
            return None
        sid = _A.finding_kind(kind)["id"]
        return (sid, toc or label, _block(sid, label, render_findings(items, store=store)))

    rec_items = _A.synthesis_recommendations(syn)         # [(text, effort, value)] from recommendation findings
    if rec_items:
        chart = _effort_impact(rec_items)
        if chart:
            body = raw(chart)  # hover popovers replace the list
        else:
            rows = "".join(_rec_row_n(i, txt, a, n) for i, (txt, a, n) in enumerate(rec_items, 1))
            body = h("div", {"class_": "reclist"}, raw(rows))
        sec.append(("empfehlungen", t("recommendations"), _block("empfehlungen", t("recommendations"), body)))
    if syn.get("positionierung"):
        sec.append(("positionierung", t("positioning"),
                    _block("positionierung", t("positioning"),
                           h("div", {"class_": "sl-prose sm"},
                             ui.clamp(raw(_md(syn["positionierung"])), threshold=ui.SECTION_CLAMP)))))
    # Structured convergence blocks (GAP-3): a methodology's key problems / affinity clusters /
    # down-select ranking + shortlist render as first-class answer content when present (data-driven —
    # labels via i18n, content free-text; no methodology value hardcoded).
    if (s := _fsec("key_problem", t("key_problems"))):
        sec.append(s)
    if (s := _fsec("cluster", t("affinity_clusters"))):
        sec.append(s)
    if (s := _fsec("ranking", t("ranking"))):
        sec.append(s)
    if (s := _fsec("shortlist", t("shortlist"))):
        sec.append(s)
    # Voices (Stimmen) — the synthesis' OWN per-persona statements (verdict + shift + quoted
    # evidence; spec/unified-artifact-schema). These are cross-council ANALYSIS, not a re-hosted
    # transcript (spec/artifact-cross-references.md): each row is the persona's distilled key
    # argument, with the verbatim council quotes expandable underneath (§3.6e).
    voices = _A.synthesis_statements(syn)
    if voices:
        sec.append(("stimmen", t("voices"),
                    _block("stimmen", t("voices"),
                           raw(render_statements(voices, store, clamp_at=ui.TURN_CLAMP,
                                                 expand_quotes=True)))))
    # The per-persona sentiment BREAKDOWN across the chain — the aggregate charts already opened
    # the page (charts row) and the per-council comparison rides the cited-council rows below,
    # so overview=False keeps this block duplication-free.
    sent = _sentiment_section(store, syn_sessions, sid="sentiment", title=t("sentiment_over_chain"),
                              chain=True, overview=False)
    if sent:
        sec.append(("sentiment-detail", t("sentiment_over_chain"),
                    h("div", {"class_": "block", "id": "sentiment-detail"}, raw(sent))))
    # supporting analysis (omit when empty — an empty section reads as a broken box)
    if (s := _fsec("segment", t("segments"))):
        sec.append(s)
    if (s := _fsec("pain_solver", t("validated_pain_solvers"))):
        sec.append(s)
    if (s := _fsec("open_question", t("open_questions_next_study"), toc=t("open_questions"))):
        sec.append(s)
    if belege:                       # cited evidence (councils) — demoted, near the end
        sec.append(belege)
    # arc (collapsed) — only when there is a narrative; an empty <details> reads as a broken box
    if (syn.get("arc_narrative") or "").strip():
        sec.append(("bogen", t("course"),
                    h("details", {"class_": "block", "id": "bogen"},
                      h("summary", {"class_": "bh", "style": "cursor:pointer"}, t("arc_course")),
                      h("div", {"class_": "sl-prose sm"}, raw(_md(_srcchips(syn["arc_narrative"])))))))

    # ---- slim meta strip (replaces the old Eigenschaften rail) — omitted when embedded in the report shell
    head = ""
    if not embed:
        cs = _A.synthesis_sentiment_counts(syn, store)        # aggregated over the REAL council voices
        smeta = " · ".join(f"{cs[k]} {k}" for k in ("positiv", "bedingt", "neutral", "skeptisch", "ablehnend") if cs.get(k))
        mchips = [_label(t("completed") if done else t("running"), "var(--green)" if done else "var(--amber)")]
        mchips.append(h("span", {"class_": "mchip"}, f'{len(syn.get("council_ids", []))} {t("councils")}'))
        if syn.get("iterations"):
            mchips.append(h("span", {"class_": "mchip"}, f'{syn["iterations"]} {t("iterations")}'))
        if smeta:
            mchips.append(h("span", {"class_": "mchip"}, raw(t("voices_meta", s=_esc(smeta)))))
        mchips.append(h("span", {"class_": "mchip"}, ui.fmt_date(syn["created_at"])))
        head = h("header", {"class_": "syn-head"},
                 h("h1", {"title": syn["title"]}, raw(_icon("syntheses")), syn["title"]),
                 h("div", {"class_": "syn-meta"}, fragment(*mchips)))

    main = head + raw("".join(str(html) for _, _, html in sec))   # section htmls are all trusted (h() Safe or built strings)
    # Unified detail shell: the caller wraps this content in _doc (content column + Properties/Relations
    # aside) and renders the section minimap via _page_rail(toc) — same as every other detail page.
    toc = [(sid, lbl) for sid, lbl, _ in sec]
    return h("div", {"class_": "syn-main"}, raw(main)), toc
