"""Component-SSR burndown ratchet (spec/component-ssr-architecture.md §11.4).

Counts legacy hand-written-HTML units per web/ file — hand-escapes (`_esc(`/`html.escape(`) and inline
HTML f-strings (`f'<` / `f"<`). The baseline below is the remaining surface; the test asserts no file
ever goes UP. As a module is converted to the h() builder, LOWER its baseline here (that's the ratchet
— the numbers are the live to-do for "componentize the rest of the app"). _html.py (the builder
itself) is excluded.
"""
from __future__ import annotations

import re
from pathlib import Path

from sonaloop import web

# Remaining legacy-HTML units per file (esc + inline). LOWER as modules convert; never raise.
#
# C1–C4 are COMPLETE: every page/component renders through the h() builder. The numbers below are the
# LEGITIMATE FLOOR — raw HTML PRODUCERS, not page hand-HTML, and intentionally not converted:
#   _components.py 32 — the _md/_md_inline markdown->HTML renderer (a text transformer) + _effort_impact's
#                       SVG quadrant chart (self-closing <rect/>/<line/>/<text>) + _srcchips(_esc(...)).
#   _synthesis.py 3   — _srcchips(_esc(...)) x2 + voices_meta(s=_esc(...)) i18n-format text-escaping.
# These go through raw() by design (h() can't emit self-closing SVG; a markdown/citation transformer
# legitimately produces HTML strings). The ratchet stays so nothing NEW creeps in.
BASELINE = {
    "_components.py": 32,
    "_graph.py": 0,
    "_palette.py": 0,
    "_rail.py": 0,
    "_routes_lists.py": 0,
    "_routes_pages.py": 0,
    "_synthesis.py": 1,
    "_vm.py": 0,
    "_detail.py": 0,
    "_i18n.py": 0,
    "_routes_api.py": 0,
    "__init__.py": 0,
    "methodologies.py": 8,  # methodology graph SVG producer; page chrome still uses h()
}


def _legacy_units(src: str) -> int:
    return len(re.findall(r"_esc\(|html\.escape\(", src)) + len(re.findall(r"""f'<|f\"<""", src))


def test_legacy_html_burndown_ratchet():
    web_dir = Path(web.__file__).parent
    regressions = []
    for f in sorted(web_dir.rglob("*.py")):          # rglob: also covers the web/pages/ package (R2)
        if f.name == "_html.py":
            continue
        n = _legacy_units(f.read_text())
        base = BASELINE.get(f.name, 0)
        if n > base:
            regressions.append(f"{f.name}: {n} legacy-HTML units > baseline {base} "
                               f"(convert to h() or, if intentional, raise the baseline)")
    assert not regressions, "component-SSR burndown went UP:\n  " + "\n  ".join(regressions)
