"""Phase 3 backfill — write the unified primitives onto existing records (spec/unified-artifact-schema-
rollout.md §3). Idempotent + loss-free: the primitives are exactly what the Phase-1 adapters already
derive from the compatibility fields, and the adapters PREFER native fields, so rendering is unchanged after the
backfill (golden-identical). It only ADDS fields — nothing is deleted.

Run a dry-run first:        uv run python scripts/migrate_to_primitives.py
Then snapshot + apply:      make snapshot && uv run python scripts/migrate_to_primitives.py --apply
"""
from __future__ import annotations

import sys

from sonaloop import artifacts as A
from sonaloop import services as S
from sonaloop.storage import Store


def main() -> None:
    apply = "--apply" in sys.argv
    st = Store()
    n = {"council": 0, "synthesis": 0, "session": 0}

    for c in S.list_councils(store=st):
        rec = st.get_council_session(c["id"])
        if not rec or rec.get("statements") or rec.get("prompts"):
            continue
        rec["statements"] = A.council_statements(rec)
        rec["prompts"] = A.council_prompts(rec)
        n["council"] += 1
        if apply:
            st.insert_council_session(rec)

    for s in st.list_syntheses():
        if s.get("statements") or s.get("findings") or s.get("prompts"):
            continue
        s["statements"] = A.synthesis_statements(s)
        s["findings"] = A.synthesis_findings(s)
        s["prompts"] = A.synthesis_prompts(s)
        n["synthesis"] += 1
        if apply:
            st.upsert_synthesis(s)

    for pr in st.list_prototypes():
        for se in st.list_prototype_sessions(pr["id"]):
            if se.get("statements"):
                continue
            se["statements"] = A.session_statements(se)
            n["session"] += 1
            if apply:
                st.insert_prototype_session(se)

    print(("APPLIED" if apply else "DRY-RUN — re-run with --apply to write"), n)


if __name__ == "__main__":
    main()
