"""Phase 1 — the ONE renderer per primitive (spec/unified-artifact-schema-rollout.md).

Every artifact draws its content through these functions, so a Statement / Finding / Prompt / Ref / Stance
looks identical everywhere (consistency by construction). Reads the primitives produced by the adapters in
`sonaloop.artifacts`; emits HTML via the existing h()/_prose toolkit.
"""
from __future__ import annotations

import re as _re

from .. import artifacts as _A
from ._i18n import t
from ._html import h, raw, fragment, register_css
from ._components import _prose, _avatar, _label, _icon

# Co-located CSS for the §3.6 dosing affordances this renderer emits: collapsible prompt
# rounds (the banner doubles as the <summary>) and expandable verbatim quotes on a statement.
register_css(r"""
details.qround>summary{position:relative;list-style:none;cursor:pointer;display:flex;flex-direction:column;gap:12px}
details.qround>summary::-webkit-details-marker{display:none}
details.qround>summary .qround-q{padding-right:48px}
.qround-cnt{position:absolute;right:12px;top:12px;color:var(--accent);background:var(--panel);border:1px solid var(--line);border-radius:var(--radius-sm);padding:1px 8px;font-size:var(--t-xs);font-weight:600}
details.qround>summary:hover .qround-q{border-color:var(--accent)}
/* Council threading (ux-contract §10 W5): the answers indent one step under their question and
   a file-tree connector links them — a hairline spine descends from the question banner's
   underside and ELBOWS (rounded corner) into each answer card at its header line. Each card
   draws its own elbow (::before: border-left + border-bottom + a radius corner, reaching up
   through the 12px gap above); every non-last card continues the spine down its own height
   (::after), so the line runs question → card → card and ENDS curving into the last one.
   Geometry is connector drawing (not rhythm); the indent itself is the 28px token. Hairline
   var(--line) keeps it quiet in light AND dark; a one-answer round degrades to one elbow. */
.qround-a{position:relative;margin-left:28px}
.qround-a>.turn{position:relative}
.qround-a>.turn::before{content:"";position:absolute;left:-16px;top:-12px;width:15px;height:37px;
  border-left:1px solid var(--line);border-bottom:1px solid var(--line);
  border-bottom-left-radius:10px;pointer-events:none}
.qround-a>.turn:not(:last-child)::after{content:"";position:absolute;left:-16px;top:25px;bottom:-12px;
  width:1px;background:var(--line);pointer-events:none}
/* The turn TEXT is running prose (§11 T2/T4): the dense reading voice (t-md at the 1.6
   rhythm — the same body layer as the report base), wrapped at the --measure-prose reading
   width, left-aligned; the card itself keeps the structural measure. */
.turn-text{font-size:var(--t-md);line-height:1.6;max-width:var(--measure-prose)}
.turn-text p{margin:0}
.turn-quotes{margin:8px 0 0}
.turn-quotes>summary{cursor:pointer;list-style:none}
.turn-quotes>summary::-webkit-details-marker{display:none}
.turn-quotes>summary::before{content:"▸ "}
.turn-quotes[open]>summary::before{content:"▾ "}
/* Verbatim quote typography (§11 T3/T4 — the design system's prose-blockquote idiom is the
   loud Markdown callout; evidence quotes stay RESTRAINED): quiet hairline, italic body at
   t-body/1.6, and the opening „ HANGS into the gutter (negative first-line indent) so the
   quoted words stay optically aligned. */
.turn-quote{margin:8px 0 0;padding:2px 0 2px 16px;border-left:2px solid var(--line-2);font-size:var(--t-body);line-height:1.6;color:var(--muted);max-width:var(--measure-prose)}
.turn-quote p{margin:0 0 3px;font-style:italic;text-indent:-.62ch}
/* Grounding-chip lines (§10 W4): one explicit rhythm under a turn/finding — quiet faint lead
   label, consistent 4px/8px wrap spacing for the chips (the base .srcchip margin-left is the
   inline-citation idiom; inside a refs LINE the chips space themselves). */
.turn-refs{margin:12px 0 0;line-height:1.6}
.turn-refs .srcchip{margin:2px 8px 2px 0;vertical-align:middle}
.turn-refs__lbl{color:var(--faint)}
.srcchip-ts{font-family:var(--mono);font-size:var(--t-xs);color:var(--faint);margin-right:4px;white-space:nowrap}
.srcchip-mark{color:var(--faint);font-style:italic;margin-right:4px}
""")


def render_stance(st: dict | None) -> str:
    """The one stance chip — label + color resolved from the canonical VALUE via the data-driven scale
    (artifacts.stance_meta → i18n label_key). Stored label strings never pick the key: a compatibility free
    label ('mixed') is ignored, an unresolvable host token (`label_raw`) only surfaces as the tooltip."""
    if not st:
        return ""
    meta = _A.stance_meta(st.get("value", 0))
    return _label(t(meta["label_key"]), meta["color"], title=st.get("label_raw"))


# Raw memory-ref anatomy (ux-contract §10 W4): host-authored grounding texts often open with
# the memory line's timestamp ("2026-06-11 08:45: …") and/or an "Open loop:" marker. The chip
# renders those as a quiet mono date + a localized quiet marker instead of a grey text slab.
_REF_TS = _re.compile(r"^\s*(\d{4}-\d{2}-\d{2})(?:[ T](\d{2}:\d{2})(?::\d{2})?)?\s*[:·–—-]?\s*")
_REF_LOOP = _re.compile(r"^\s*(?:open\s+loops?|offene[rs]?\s+loops?)\s*[:·–—-]\s*", _re.I)


def _trim(text: str, n: int = 110) -> str:
    """Word-boundary trim with a real ellipsis — chip text stays scannable, the full text
    rides the tooltip."""
    s = " ".join((text or "").split())
    if len(s) <= n:
        return s
    return s[:n].rsplit(" ", 1)[0].rstrip(" ,;:·–—-") + "…"


def render_ref(r: dict, store=None, *, show_role: bool = True) -> str:
    """A cross-reference chip (spec/artifact-cross-references.md). With a `store` and a record-pointing
    Ref, it RESOLVES the addressed artifact/part LIVE — showing the current persona/title + the typed
    role + a deep-link to the part (never a stale copy); a broken ref renders honestly. Without a store
    (or for memory/observed-state/external refs) it falls back to the plain grounding chip — formatted
    quietly (§10 W4): a leading memory timestamp renders as a mono `11 Jun · 08:45` prefix, an
    "Open loop:" marker as a localized quiet label, and the body is word-trimmed with the full text
    on the tooltip. The kind→route mapping lives in the domain layer (artifacts.ref_href) so no kind
    literal is hardcoded here. `show_role=False` drops the typed-role suffix — for chip groups whose
    lead label already states the role ("Based on: …"), where the suffix would just repeat it."""
    role = r.get("role") if show_role else None
    rolebit = (" · " + role.replace("_", " ")) if role else ""
    if store is not None and r.get("id") and _A.ref_href(r):
        res = _A.resolve_ref(r, store)
        who = (store.get_persona(res["persona_id"]) or {}).get("display_name") if res.get("persona_id") else ""
        label = who or res.get("title") or r.get("id")
        cls = "srcchip xref" + ("" if res.get("exists") else " xref-broken")
        return h("a", {"class_": cls, "href": res["href"], "title": (res.get("text") or "")[:240]},
                 raw(_icon("link")), " ", label,
                 h("span", {"class_": "xref-role"}, rolebit) if rolebit else None)
    href = _A.ref_href(r)
    full = str(r.get("quote") or r.get("text") or r.get("id") or "")
    if href:
        return h("a", {"class_": "srcchip", "href": href, "title": full[:240]},
                 raw(_icon("link")), " ", _trim(full), rolebit or None)
    ico = "memory" if r.get("kind") == "memory" else ("compass" if r.get("kind") == "prototype_state" else "link")
    txt, ts_html, loop_html = full, None, None
    m = _REF_TS.match(txt)
    if m:
        from . import ui
        ts = ui.fmt_ts(f"{m.group(1)} {m.group(2)}") if m.group(2) else ui.fmt_day(m.group(1))
        ts_html = h("span", {"class_": "srcchip-ts"}, ts)
        txt = txt[m.end():]
    lm = _REF_LOOP.match(txt)
    if lm:
        loop_html = h("span", {"class_": "srcchip-mark"}, t("ref_open_loop"))
        txt = txt[lm.end():]
    return h("span", {"class_": "srcchip", "title": full[:240] if full != txt or len(full) > 110 else None},
             raw(_icon(ico)), " ", ts_html, loop_html, _trim(txt))


def _refs_line(refs: list, label: str, store=None) -> str:
    if not refs:
        return ""
    return h("p", {"class_": "muted small turn-refs"},
             h("span", {"class_": "turn-refs__lbl"}, label, ": "),
             fragment(*(raw(render_ref(r, store)) for r in refs)))


def render_prompt(p: dict, *, n: int | None = None) -> str:
    """A posed prompt. As a transcript header (question/proposal) with an optional ordinal."""
    ey = {"question": t("question"), "proposal": t("council_motion"),
          "goal": t("question"), "focus": t("question"), "hypothesis": t("council_motion")}.get(p.get("kind"), t("question"))
    label = f'{ey} {n}' if (n is not None and p.get("kind") == "question") else ey
    ico = "compass" if p.get("kind") in ("question", "goal", "focus") else "bulb"
    return h("div", {"class_": "qround-q"}, raw(_icon(ico)),
             h("div", {}, h("div", {"class_": "qround-n"}, label),
               h("p", {}, raw(_prose(p.get("text", ""))))))


def _backlinks_line(st: dict, backlinks) -> str:
    """The REVERSE cross-references (spec/artifact-cross-references.md §4): who points AT this part — e.g.
    'cited by <synthesis>'. `backlinks` is {part_id: [{href, label, role}]}."""
    bl = (backlinks or {}).get(st.get("id")) if st.get("id") else None
    if not bl:
        return ""
    chips = [h("a", {"class_": "srcchip xref", "href": r["href"]}, raw(_icon("link")), " ", r.get("label") or "—",
               h("span", {"class_": "xref-role"}, " · " + r["role"].replace("_", " ")) if r.get("role") else None)
             for r in bl]
    return h("p", {"class_": "muted small turn-refs"},
             h("span", {"class_": "turn-refs__lbl"}, t("cited_by"), ": "), fragment(*chips))


def _quotes_details(refs: list, store=None) -> str:
    """Grounding refs that carry verbatim QUOTES, dosed as an expandable list (ux-contract §3.6):
    a quiet summary with the count, each quote as a small blockquote with its source chip. Refs
    without a quote keep the plain chip line (the caller appends it)."""
    return h("details", {"class_": "turn-quotes"},
             h("summary", {"class_": "muted small"}, t("n_quotes", n=len(refs))),
             fragment(*(h("blockquote", {"class_": "turn-quote"},
                          h("p", {}, f"„{r['quote']}“"), raw(render_ref(r, store)))
                        for r in refs)))


def _statement_body(st: dict, store=None, backlinks=None, *, clamp_at: int | None = None,
                    expand_quotes: bool = False) -> str:
    """One utterance's body: optional focus line, input snapshot, the prose, pushback, shift, refs, and
    the reverse cross-refs ('cited by'). The wrapper carries id=<part-id> so other artifacts can
    deep-link to this exact statement. `clamp_at` doses a long turn through ui.clamp (§3.6);
    `expand_quotes` renders quote-bearing refs as an expandable quote list instead of bare chips."""
    from . import ui
    meta = st.get("meta") or {}
    focus = h("p", {"class_": "muted small", "style": "font-style:italic;margin:0 0 4px"}, meta["focus"]) if meta.get("focus") else None
    given = h("details", {"class_": "turn-input"},
              h("summary", {"class_": "muted small"}, t("council_input_given")),
              h("p", {"class_": "muted small", "style": "white-space:pre-wrap"}, meta["input"])) if meta.get("input") else None
    pushback = fragment(*(h("p", {"class_": "muted small"}, f"• {q}") for q in (meta.get("pushback") or [])[:4]))
    shift = st.get("shift") or {}
    shift_html = h("p", {"class_": "muted small"}, raw(_icon("exchange")), " ",
                   f'{shift.get("from","")} → {shift.get("to","")}',
                   (f' · {shift["trigger"]}' if shift.get("trigger") else "")) if shift else None
    attrs = {"class_": "turn-ans"}
    if st.get("id"):
        attrs["id"] = st["id"]
    prose_html = raw(_prose(st.get("text", "")))
    # the utterance itself rides the .turn-text reading layer (§11 T2/T4: t-md/1.6 at the
    # prose measure) — meta/refs/pushback stay in the quiet layer beside it
    text_html = h("div", {"class_": "turn-text"},
                  ui.clamp(prose_html, threshold=clamp_at) if clamp_at
                  else h("p", {}, prose_html))
    refs = st.get("refs") or []
    quoted = [r for r in refs if r.get("quote")] if expand_quotes else []
    plain = [r for r in refs if r not in quoted]
    return h("div", attrs, focus, given, text_html,
             pushback, shift_html,
             raw(_quotes_details(quoted, store)) if quoted else None,
             raw(_refs_line(plain, t("council_drew_on"), store)),
             raw(_backlinks_line(st, backlinks)))


def _persona_card(sts: list, store, *, head_extra=None, backlinks=None, show_persona=True,
                  clamp_at: int | None = None, expand_quotes: bool = False) -> str:
    """The ONE .turn statement card — a persona's avatar + name + stance + life-context, then one or more
    utterance bodies (a persona answering several questions merges into a single card, not repeated heads).
    `show_persona=False` drops the avatar/name/life-context — used on the persona's OWN page where the
    identity is implied and repeating it on every card is pure noise."""
    head_st = sts[0]
    pid = head_st.get("persona_id", "")
    p = store.get_persona(pid) if (pid and show_persona) else None
    who = ctx_html = None
    if show_persona:
        name = (p or {}).get("display_name") or pid or "—"
        seg = (p or {}).get("segment") or {}
        ctx = (head_st.get("meta") or {}).get("context") \
            or " · ".join(x for x in [seg.get("lebensphase"), seg.get("einstellung")] if x)[:130] \
            or ((p or {}).get("source_description") or "")[:130]
        who = (h("a", {"href": f'/personas/{p["id"]}', "class_": "turn-who"}, _avatar(p, 26), h("b", {}, name))
               if p else h("span", {"class_": "turn-who"}, h("b", {}, name)))
        ctx_html = h("div", {"class_": "muted small turn-ctx"}, ctx) if ctx else None
    st_with_stance = next((s for s in sts if s.get("stance")), None)
    stance_chip = raw(render_stance(st_with_stance["stance"])) if st_with_stance else None
    gmeta = head_st.get("meta") or {}
    grounded_chip = None
    if "grounded" in gmeta:                            # prototype sessions: a grounded badge in the stance slot
        g = bool(gmeta["grounded"])
        grounded_chip = raw(_label(t("grounded_yes") if g else t("grounded_no"), "var(--green)" if g else "var(--muted)"))
    rel = head_st.get("relevance")
    rel_html = h("span", {"class_": "muted small"}, f" · {rel}") if rel else None
    head = h("div", {"class_": "hd"}, who, (" " if who else ""), stance_chip, grounded_chip, head_extra, rel_html, ctx_html)
    return h("div", {"class_": "turn" + ("" if show_persona else " turn-bare")},
             head, fragment(*(_statement_body(s, store, backlinks, clamp_at=clamp_at,
                                              expand_quotes=expand_quotes) for s in sts)))


def render_statement(st: dict, store, *, head_extra=None, show_persona=True,
                     clamp_at: int | None = None, expand_quotes: bool = False) -> str:
    """A single persona statement → the .turn card (used by prototype sessions). `head_extra` is an extra
    header chip (e.g. a session's grounded badge); `show_persona=False` drops the persona header."""
    return _persona_card([st], store, head_extra=head_extra, show_persona=show_persona,
                         clamp_at=clamp_at, expand_quotes=expand_quotes)


def _by_persona(items: list) -> list:
    order, by = [], {}
    for s in items:
        pid = s.get("persona_id")
        if pid not in by:
            by[pid] = []; order.append(pid)
        by[pid].append(s)
    return [by[pid] for pid in order]


def render_statements(items: list, store, *, group_by: str = "persona", prompts: list | None = None,
                      backlinks=None, clamp_at: int | None = None, expand_quotes: bool = False,
                      collapsible: bool = False) -> str:
    """Render statements as the SAME .turn cards. group_by='prompt' → a moderated transcript (a question
    header from `prompts` + the statements answering it via Statement.about.id, grouped per persona);
    group_by='persona' → a flat list of per-persona cards. `backlinks` ({part_id: [referrers]}) adds the
    reverse 'cited by' cross-references under each statement. `clamp_at`/`expand_quotes` dose long turn
    prose / quote-bearing refs (§3.6); `collapsible` renders each prompt round as a <details> group
    (open, like the outline's ol-phase idiom) so a long transcript collapses per round."""
    items = [s for s in items if s]

    def cards(group):
        return fragment(*(_persona_card(g, store, backlinks=backlinks, clamp_at=clamp_at,
                                        expand_quotes=expand_quotes) for g in _by_persona(group)))

    def round_group(header, group):
        answers = h("div", {"class_": "qround-a"}, cards(group))
        if collapsible:
            return h("details", {"class_": "qround", "open": True},
                     h("summary", {}, raw(header),
                       h("span", {"class_": "qround-cnt"}, str(len({s.get("persona_id") for s in group})))),
                     answers)
        return h("div", {"class_": "qround"}, raw(header), answers)

    if group_by == "prompt" and prompts:
        ids = {p.get("id") for p in prompts}
        single = len(prompts) == 1                     # one prompt (synthesis study-question / session focus)
        rounds = []                                    #   → every statement is its response (no "rest" bucket)
        for n, p in enumerate(prompts, 1):
            qs = items if single else [s for s in items if (s.get("about") or {}).get("id") == p.get("id")]
            if not qs:
                continue
            rounds.append(round_group(render_prompt(p, n=(None if single else n)), qs))
        rest = [] if single else [s for s in items if (s.get("about") or {}).get("id") not in ids]
        if rest:
            rounds.append(round_group(h("div", {"class_": "qround-q"}, raw(_icon("bulb")),
                                        h("div", {}, h("div", {"class_": "qround-n"}, t("further_answers")))),
                                      rest))
        return h("div", {"class_": "qrounds"}, fragment(*rounds))
    return h("div", {"style": "display:flex;flex-direction:column;gap:12px"}, cards(items))


def render_finding(f: dict, *, n: int | None = None, store=None) -> str:
    """One authored finding — the ONE row every finding section uses (key_problem, pain_solver, cluster,
    segment, ranking, recommendation, …): a left block (prose title, optional muted detail, members,
    grounding refs) and right-aligned chips (effort·impact score + stance). Numbered → the .rec form.
    The row carries id=<part-id> so other artifacts can deep-link to this exact finding."""
    meta = f.get("meta") or {}
    score = f.get("score")
    detail = meta.get("detail")
    left = [h("strong", {}, raw(_prose(f.get("text", "")))) if detail else h("span", {}, raw(_prose(f.get("text", ""))))]
    if detail:
        left.append(h("div", {"class_": "muted small", "style": "margin-top:2px"}, raw(_prose(detail))))
    if meta.get("members"):
        left.append(h("div", {"class_": "muted small", "style": "margin-top:2px"}, "· " + ", ".join(str(m) for m in meta["members"])))
    rl = _refs_line(f.get("refs") or [], t("rel_based_on"), store)
    if rl:
        left.append(raw(rl))
    chips = []
    if isinstance(score, dict) and score.get("effort") and score.get("value"):
        chips.append(h("span", {"class_": "axchip"}, t("effort_value", a=score["effort"], n=score["value"])))
    if meta.get("stance"):
        chips.append(raw(render_stance(meta["stance"])))
    num = h("span", {"class_": "recnum"}, str(n)) if n is not None else None
    body = h("div", {"class_": "fbody"}, fragment(*left))
    right = h("div", {"class_": "fchips"}, fragment(*chips)) if chips else None
    attrs = {"class_": "rec" if n is not None else "fitem"}
    if f.get("id"):
        attrs["id"] = f["id"]
    return h("div", attrs, num, body, right)


def render_findings(items: list, *, numbered: bool = False, store=None) -> str:
    """The rows of a finding list section (one render_finding per item). The caller wraps them in a
    section with the data-driven id (artifacts.finding_kind(kind)['id']) and an i18n label."""
    rows = [render_finding(f, n=(i if numbered else None), store=store) for i, f in enumerate(items, 1)]
    return fragment(*rows)
