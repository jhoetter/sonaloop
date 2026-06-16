#!/usr/bin/env python3
"""Type-conformance harness (spec/ux-contract.md §11 T1) — the DOM-measured typography sweep.

Sibling of scripts/ux_spacing.py: boots the same seeded app (scripts/ux_shots.py, same
canonical screens) and walks the RENDERED DOM — for every structural TEXT element (headings,
leads, body prose, row titles, chips, meta lines, eyebrows, kbd) it reads the computed
font-size / font-weight / line-height and classifies each against the design system's type
scale + the documented roles (sonaloop-design tokens.data.mjs `scales`, ux-audit Round 5):

  font-size    token  exactly one of the t-* steps — 11/12/13/15/16/18/24/32 px
               em     an em-derived size that RESOLVES onto the scale (within 0.5px of a
                      step) — the density-adaptive layer (.sl-entity, .sl-tab, .sl-kbd …)
                      deliberately rides em and lands back on the scale at the app's 13px base
  font-weight  token  one of the documented weight roles — 400 regular · 500 medium (chips,
                      tabs, eyebrows) · 550 row-title (the em layer's medium) · 600 semibold
                      (card/section/question titles) · 650 display (page + prose headings) ·
                      700 strong (counts, numerics, <b>)
  line-height  token  the computed/font-size RATIO is one of the documented roles —
                      1.0 solid (controls) · 1.2 display · 1.35 title/heading ·
                      1.5 UI/body · 1.6 reading prose (±0.035 ratio tolerance)
  exempt       an explicitly documented per-rule exemption (EXEMPT below, with the reason)
  FLAG         everything else — an off-scale value that must be fixed or documented

Usage:  uv run python scripts/ux_type.py [--out /tmp/ux/t-type-table.txt]
Exit 1 while any FLAG remains. The final zero-flag table is committed into
spec/ux-audit.md (Round 5 · type conformance).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ux_shots  # noqa: E402  (env + temp store configured on import)

SIZE_TOKENS = (11, 12, 13, 15, 16, 18, 24, 32)          # --t-xs…--t-xl + --t-2xl (report cover)
WEIGHT_TOKENS = {400, 500, 550, 600, 650, 700}
LH_ROLES = (1.0, 1.2, 1.35, 1.5, 1.6)
LH_TOL = 0.035

# Structural TEXT selectors (label, css selector) — the typographic anatomy the owner's
# screenshots judge: display/lead/body/quiet on every canonical screen. Decorative SVG text
# (graph labels) and form internals are not reading typography; they stay out.
SELECTORS: list[tuple[str, str]] = [
    # display / headings
    ("h1", ".h1"),
    ("page-title", ".sl-page-header__title"),
    ("report-title", ".rp-title"),
    ("report-h2", ".rp-sec h2"),
    ("report-num", ".rp-num"),
    # leads
    ("lead", ".lead"),
    ("page-sub", ".sl-page-header__sub"),
    ("report-lead", ".rp-lead"),
    ("study-question", ".qa-q"),
    ("verdict-title", ".syn-verdict .sl-card__title"),
    ("verdict-body", ".syn-verdict .sl-card__body p"),
    ("qround-q", ".qround-q p"),
    # body prose
    ("prose", ".sl-prose"),
    ("prose-p", ".sl-prose p"),
    ("prose-h3", ".sl-prose h3"),
    ("prose-h4", ".sl-prose h4"),
    ("prose-strong", ".sl-prose strong"),
    ("report-p", ".rp-sec > p, .rp-sec > .sl-clamp"),
    ("turn-text", ".turn-text"),
    ("turn-quote", ".turn-quote p"),
    ("finding-text", ".fitem .fbody"),
    ("rec-text", ".rec .fbody"),
    # row titles
    ("entity-title", ".sl-entity__title"),
    ("entity-desc", ".sl-entity__desc"),
    ("ol-title", ".olrow .ol-title"),
    ("ref-title", ".ref-t"),
    ("rel-title", ".relrow .relt"),
    ("turn-name", ".turn-who b"),
    # chips
    ("pill", ".pill"),
    ("mchip", ".mchip"),
    ("srcchip", ".srcchip"),
    ("label-chip", ".lbl"),
    ("kbd", ".sl-kbd"),
    ("axchip", ".axchip"),
    ("count-chip", ".ol-cnt"),
    ("qround-cnt", ".qround-cnt"),
    ("toolbtn", ".sl-toolbtn"),
    # meta / quiet
    ("muted-small", ".muted.small"),
    ("turn-ctx", ".turn-ctx"),
    ("turn-refs", ".turn-refs"),
    ("ihint", ".ihint"),
    ("legend", ".legend"),
    ("ol-date", ".olrow .ol-ts"),
    ("stat-num", ".stat b"),
    ("stat-label", ".stat span"),
    ("kpi-num", ".kpi b"),
    ("report-metaline", ".rp-metaline"),
    ("report-cite", ".rp-cites li"),
    ("prop-label", ".sl-prop__k"),
    ("prop-value", ".sl-prop__v"),
    ("breadcrumb", ".sl-breadcrumb"),
    ("tab", ".sl-tab"),
    ("nav-row", ".sl-nav a"),
    # eyebrows / section labels
    ("eyebrow", ".eyebrow"),
    ("sl-eyebrow", ".sl-eyebrow"),
    ("report-eyebrow", ".rp-eyebrow"),
    ("block-heading", ".block > .bh"),
    ("section-heading", ".sec > h2"),
    ("section-quiet-h", ".sl-section__h"),
    ("rail-h4", ".rail h4"),
    ("round-label", ".ol-rlabel"),
    ("phase-tag", ".ol-ptag"),
    ("qround-kicker", ".qround-n"),
    ("rel-heading", ".relh"),
    ("rel-group-label", ".rellbl"),
    ("toc-heading", ".toc .th"),
]

# Documented per-rule exemptions (selector-label, property) -> reason. Every entry is a
# deliberate decision recorded in spec/ux-audit.md, not an escape hatch.
EXEMPT: dict[tuple[str, str], str] = {}

_MEASURE_JS = """
(sels) => {
  const out = [];
  for (const [label, sel] of sels) {
    const seen = new Set();
    let taken = 0;
    for (const el of document.querySelectorAll(sel)) {
      if (taken >= 4) break;
      const cs = getComputedStyle(el);
      if (cs.display === 'none' || !el.offsetParent && cs.position !== 'fixed') continue;
      const vals = {'font-size': cs.fontSize, 'font-weight': cs.fontWeight,
                    'line-height': cs.lineHeight};
      const key = JSON.stringify(vals);
      if (seen.has(key)) continue;
      seen.add(key); taken++;
      out.push({label, sel, vals});
    }
  }
  return out;
}
"""


def _classify_size(px: float) -> str:
    best = min(SIZE_TOKENS, key=lambda tkn: abs(px - tkn))
    d = abs(px - best)
    if d < 0.02:
        return "token"
    if d <= 0.5:
        return "em"
    return "FLAG"


def _classify_weight(w: float) -> str:
    return "token" if round(w) in WEIGHT_TOKENS else "FLAG"


def _classify_lh(lh: str, fs: float) -> tuple[str, str]:
    """Returns (display value, status). Computed line-height is px (the app body sets a
    unitless 1.5, so 'normal' never reaches structural text)."""
    if lh == "normal":
        return "normal", "FLAG"
    ratio = float(lh.replace("px", "")) / (fs or 1)
    best = min(LH_ROLES, key=lambda r: abs(ratio - r))
    status = "token" if abs(ratio - best) <= LH_TOL else "FLAG"
    return f"{ratio:.2f}", status


def main() -> int:
    out_path = Path("/tmp/ux/t-type-table.txt")
    if "--out" in sys.argv:
        out_path = Path(sys.argv[sys.argv.index("--out") + 1])
    out_path.parent.mkdir(parents=True, exist_ok=True)

    ids = ux_shots.seed()
    port = ux_shots.free_port()
    proc = ux_shots.boot(port)
    base = f"http://127.0.0.1:{port}"
    rows: list[tuple[str, str, str, str, str]] = []   # screen, label, prop, value, status
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            ctx = browser.new_context(viewport=ux_shots.VIEWPORT, device_scale_factor=1)
            page = ctx.new_page()
            for name, path, *click in ux_shots.screens(ids):
                page.goto(base + path, wait_until="load")
                page.wait_for_timeout(300)
                if click:
                    page.click(click[0] + " >> nth=0")
                    page.wait_for_selector(click[1] if len(click) > 1
                                           else "#drawer.is-open .sl-slide")
                    page.wait_for_timeout(300)
                for m in page.evaluate(_MEASURE_JS, [list(s) for s in SELECTORS]):
                    fs = float(m["vals"]["font-size"].replace("px", ""))
                    fw = float(m["vals"]["font-weight"])
                    checks = [("font-size", f"{fs:g}px", _classify_size(fs)),
                              ("font-weight", f"{fw:g}", _classify_weight(fw))]
                    lh_val, lh_status = _classify_lh(m["vals"]["line-height"], fs)
                    checks.append(("line-height", lh_val, lh_status))
                    for prop, val, status in checks:
                        if (m["label"], prop) in EXEMPT:
                            status = "exempt"
                        rows.append((name, m["label"], prop, val, status))
            ctx.close()
            browser.close()
    finally:
        proc.terminate()
        proc.wait(timeout=10)

    # ---- the table: per screen, the distinct (selector, prop, value, status) tuples ----
    lines = ["T1 type conformance — DOM-measured (1440x900, light)",
             "size tokens: 11/12/13/15/16/18/24/32 px (t-xs…t-2xl; em-derived values resolving "
             "onto the scale conform) · weights: 400/500/550/600/650/700 · "
             "line-height roles: 1.0/1.2/1.35/1.5/1.6 (ratio)",
             ""]
    flags = 0
    per_screen: dict[str, int] = {}
    seen_globally: set = set()
    for name in dict.fromkeys(r[0] for r in rows):
        screen_rows = sorted({(r[1], r[2], r[3], r[4]) for r in rows if r[0] == name})
        n_flags = sum(1 for r in screen_rows if r[3] == "FLAG")
        per_screen[name] = n_flags
        lines.append(f"## {name}  ({n_flags} flags)")
        for label, prop, val, status in screen_rows:
            key = (label, prop, val, status)
            mark = " *" if key not in seen_globally else ""
            seen_globally.add(key)
            if status in ("FLAG", "exempt") or mark:
                lines.append(f"  {status:<8} {label:<18} {prop:<12} {val}{mark}")
        flags += n_flags
        lines.append("")
    lines.append("summary: " + " · ".join(f"{k}={v}" for k, v in per_screen.items()))
    lines.append(f"TOTAL FLAGS: {flags}")
    lines.append("exemptions: " + ("; ".join(f"{k[0]}/{k[1]}: {v}" for k, v in EXEMPT.items()) or "none"))
    text = "\n".join(lines)
    out_path.write_text(text, encoding="utf-8")
    print(text)
    print(f"\nwrote {out_path}")
    return 1 if flags else 0


if __name__ == "__main__":
    raise SystemExit(main())
