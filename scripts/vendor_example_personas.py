"""Re-vendor the trimmed catalog snapshot the onboarding showcase loads from.

The showcase personas are REAL catalog personas (lived days + the "From catalog"
badge). At load time `load_example` tries a live `catalog_pull` first, then falls
back to the snapshot vendored at `sonaloop/examples/_catalog/` — this script
(re)generates that snapshot so the example loads fully offline (CI, no network,
sonaloop-data not installed).

What it does, per persona slug: copy the lived-days JSON verbatim
(profile/SOUL/MEMORY/calendar/experiences/daily_summaries/memory/eval) and a
DOWNSCALED avatar (256px — the full-res catalog PNGs are 1-2 MB each, far too heavy
for the wheel), then write a trimmed manifest.json.

Source: a local sonaloop-data checkout (SONALOOP_DATA_ROOT, default
~/repos/sonaloop-data). Run from the sonaloop repo root:

    .venv/bin/python scripts/vendor_example_personas.py

Edit CAST below when the showcase cast changes; keep it in sync with the
`catalog_slug` entries in sonaloop/examples/onboarding-showcase.json.
"""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from PIL import Image

# Free-tier German care-work cast (shared theme: protecting a real break/meal window
# under interruptions, commutes, documentation). Must match onboarding-showcase.json.
CAST = ["anna-petersen", "lucia-moreno", "paula-gruber", "amelie-kranz"]

JSON_FILES = ("profile.json", "SOUL.md", "MEMORY.md", "calendar.json",
              "experiences.json", "daily_summaries.json", "memory.json", "eval.json")
AVATAR_PX = 256

REPO = Path(__file__).resolve().parent.parent
DST = REPO / "sonaloop" / "examples" / "_catalog"
SRC = Path(os.environ.get("SONALOOP_DATA_ROOT", str(Path.home() / "repos" / "sonaloop-data")))


def main() -> None:
    if not (SRC / "manifest.json").is_file():
        raise SystemExit(f"sonaloop-data catalog not found at {SRC} "
                         "(set SONALOOP_DATA_ROOT to the checkout)")
    roster = {p.get("slug"): p for p in json.loads((SRC / "manifest.json").read_text())["personas"]}

    if DST.exists():
        shutil.rmtree(DST)
    (DST / "personas").mkdir(parents=True)

    index = []
    for slug in CAST:
        sdir = SRC / "personas" / slug
        if not (sdir / "profile.json").is_file():
            raise SystemExit(f"persona {slug!r} missing in {SRC}")
        ddir = DST / "personas" / slug
        ddir.mkdir(parents=True)
        for name in JSON_FILES:
            if (sdir / name).is_file():
                shutil.copyfile(sdir / name, ddir / name)
        if (sdir / "avatar.png").is_file():
            im = Image.open(sdir / "avatar.png").convert("RGBA")
            im.thumbnail((AVATAR_PX, AVATAR_PX), Image.LANCZOS)
            im.save(ddir / "avatar.png", "PNG", optimize=True)
        prof = json.loads((ddir / "profile.json").read_text())
        role = prof.get("role") or {}
        index.append({
            "slug": slug,
            "display_name": prof.get("display_name"),
            "role": role.get("title") if isinstance(role, dict) else None,
            "has_avatar": (ddir / "avatar.png").is_file(),
            "updated_at": prof.get("updated_at") or (roster.get(slug) or {}).get("updated_at"),
            "tier": "free",
        })
        print(f"vendored {slug}")

    (DST / "manifest.json").write_text(json.dumps({
        "schema_version": json.loads((SRC / "manifest.json").read_text()).get("schema_version"),
        "note": "Trimmed snapshot of the onboarding-showcase catalog cast (downscaled "
                "avatars; lived days intact). Regenerate with scripts/vendor_example_personas.py.",
        "personas": index,
    }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    total = sum(f.stat().st_size for f in DST.rglob("*") if f.is_file())
    print(f"wrote {DST.relative_to(REPO)} ({total // 1024} KB, {len(index)} personas)")


if __name__ == "__main__":
    main()
