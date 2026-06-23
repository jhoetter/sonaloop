"""UX-contract grep gates (spec/ux-contract.md §5 item 1, contract C9).

Pages compose presentation through web/ui.py + the design-system `sl-*` class contracts —
no new per-page presentation. Two RATCHETS make drift technically impossible instead of
discouraged: the baselines below were measured on 2026-06-11 and may only ever DECREASE
(P2-P4 burn the existing violations down). Lowering a baseline when you remove a violation
is welcome and expected; a failing gate means a page just invented presentation — move it
into web/ui.py / the design system instead of raising the number.
"""
from __future__ import annotations

import re
from pathlib import Path

PAGES_DIR = Path(__file__).resolve().parent.parent / "sonaloop" / "web" / "pages"

# ---------------------------------------------------------------- inline-style ratchet

# Inline style attributes across web/pages/*.py — both the h() attr form ("style": "…")
# and any literal style="…" in compatibility f-strings. Measured 2026-06-11; lowered by P2
# (the project-page appendix sections retired), P3 (the list pages folded into the
# Library browser's primitive_row rendering), P4 (the survey detail rebuilt on
# question/response rows), U7 (the hyp/decision card margins moved into the
# co-located `.hyp p` rule), U8 (the 7 repeated oqp-h margins moved into the
# .oqp-h rule itself, web_assets.py), U9/U10 (the oqpanel pills/ul margins moved
# into the .oqpanel rules) and V2 (the council section-hint margins folded into the
# now-global `.ihint` rule). ONLY lower it.
STYLE_BASELINE = 23


def _pages() -> list[Path]:
    return sorted(PAGES_DIR.glob("*.py"))


def test_inline_style_ratchet():
    counts = {p.name: len(re.findall(r'"style"\s*:', p.read_text(encoding="utf-8")))
              + len(re.findall(r'style="', p.read_text(encoding="utf-8")))
              for p in _pages()}
    total = sum(counts.values())
    assert total <= STYLE_BASELINE, (
        f"web/pages/ gained inline style= attributes: {total} > baseline {STYLE_BASELINE}.\n"
        f"Per file: { {k: v for k, v in counts.items() if v} }\n"
        "Spacing/layout belongs in a design-system class contract (styles/components.css) or a "
        "co-located register_css fragment — compose via web/ui.py (ux-contract C9)."
    )
    # Keep the ratchet honest: when violations are removed, lower the baseline too.
    assert total > STYLE_BASELINE - 12, (
        f"Nice — inline styles dropped to {total}. Lower STYLE_BASELINE in this test "
        "so the ratchet locks the progress in."
    )


# ---------------------------------------------------------------- class-whitelist ratchet

# Every non-`sl-*` class token that web/pages/*.py may emit, enumerated 2026-06-11.
# This list may ONLY SHRINK: when a page migrates to an `sl-*` contract (P2-P4), delete its
# tokens here. Adding a token is the drift this gate exists to block — new presentation
# needs a design-system contract + a web/ui.py helper, not a new app-local class.
ALLOWED_CLASS_TOKENS = {
    # generic text/layout utilities (web_assets.py "generic" block)
    "muted", "small", "lead", "h1", "h1cnt", "page", "grid", "two", "right", "rows", "row",
    "cnt", "pill", "pills", "sec", "title", "sub", "empty", "avatar",
    "quote", "thought", "lbl", "lbl-soft", "ihint", "identity", "cap-row", "rico",
    # project page: outline chrome (the spatial graph view + its toolbar/panel retired)
    "proj", "proj-head", "protoframe", "strow",
    # hypothesis/decision cards (.hyp co-located in pages/hypotheses.py)
    "hyp", "hyprate", "hypseg", "hypstrip", "hypvals",
    # councils: turns/head-to-head tables (the votebar retired with the P3 Library rows)
    "turn-refs", "turn-who", "h2h-pref", "h2h-table", "qhead", "qnum",
    # persona memory page
    "mem-bar", "mem-date", "mem-ent", "mem-ent-h", "mem-ents", "mem-fact", "mem-fx",
    "mem-group", "mem-group-h", "mem-hit", "mem-loop", "mem-loop-dot", "mem-loops",
    "mem-n", "mem-pane", "mem-pane-h", "mem-status", "mem-tl", "mem-tool",
    # runs journal (run-copy/run-resume markup moved into web/_runs_widget — shared with the chip)
    "run-meta", "runrow", "runrow-head", "runs-fin", "runs-sec",
    # usability sessions
    "sess-act", "sess-act-h", "sess-banner", "sess-cap", "sess-detail", "sess-foot",
    "sess-freason", "sess-frow", "sess-funnel", "sess-mono", "sess-n", "sess-rail",
    "sess-rail-h", "sess-rail-note", "sess-screen", "sess-screen-txt", "sess-shot",
    "sess-step", "sess-steps", "sess-target", "sfl", "sfn",
    # surveys + syntheses
    "svbar", "svopts", "svq", "svrow", "syn-meta", "pvbar", "pvlbl", "pvline", "pvseg",
}


def test_class_whitelist_ratchet():
    tokens: dict[str, set[str]] = {}
    for page in _pages():
        for value in re.findall(r'"class_"\s*:\s*"([^"]*)"', page.read_text(encoding="utf-8")):
            for token in value.split():
                tokens.setdefault(token, set()).add(page.name)
    unknown = {tk: sorted(files) for tk, files in tokens.items()
               if not tk.startswith("sl-") and tk not in ALLOWED_CLASS_TOKENS}
    assert not unknown, (
        f"web/pages/ emits class tokens outside the contract whitelist: {unknown}\n"
        "New presentation needs an `sl-*` design-system contract (+ a web/ui.py helper), "
        "not a new app-local class (ux-contract C9). The ALLOWED set may only shrink."
    )
    # Flag stale whitelist entries so the list genuinely only shrinks.
    stale = ALLOWED_CLASS_TOKENS - set(tokens)
    assert not stale, (
        f"ALLOWED_CLASS_TOKENS contains tokens no page emits anymore: {sorted(stale)} — "
        "delete them so the whitelist ratchets down."
    )
