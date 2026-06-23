"""Q quality bar (spec/refactor-plan.md): no source module is a god-file.

The behavior-preserving package split (S/Q phase) brought every source file under the
~800-LOC target. This guard keeps it that way — if a module grows past the bar, split it
(or record a justified exception here with a reason).
"""
from __future__ import annotations

from pathlib import Path

LOC_BAR = 800
# Justified exceptions (path -> reason). Remove entries as the follow-up splits land.
EXCEPTIONS: dict[str, str] = {
    "sonaloop/cli.py": "taxonomy and compatibility CLI command groups still share one module; split command groups in a follow-up",
    "sonaloop/services/_engines.py": "pre-existing plan/run engine dispatch module; split runner/assessment helpers in a follow-up",
    "sonaloop/web/_components.py": "shared renderer helpers and markdown/chart producers; split renderer utilities in a follow-up",
    "sonaloop/web/_i18n_strings.py": "central bilingual string table; split by product area in a follow-up",
    "sonaloop/web/pages/formats.py": "taxonomy/formats browser currently owns multiple primitive detail surfaces; split detail routes in a follow-up",
}


def test_no_source_file_exceeds_loc_bar():
    pkg = Path(__file__).resolve().parent.parent / "sonaloop"
    offenders = []
    for f in sorted(pkg.rglob("*.py")):
        rel = str(f.relative_to(pkg.parent))
        if rel in EXCEPTIONS:
            continue
        n = sum(1 for _ in f.open(encoding="utf-8"))
        if n > LOC_BAR:
            offenders.append(f"{rel}: {n} LOC")
    assert not offenders, "god-file(s) over the LOC bar — split them:\n  " + "\n  ".join(offenders)
