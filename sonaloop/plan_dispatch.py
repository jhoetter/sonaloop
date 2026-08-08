"""Small plan-dispatch selection helpers."""

from __future__ import annotations

from .storage import Store


def diverse_participants(store: Store, persona_ids: list[str], k: int = 6) -> list[str]:
    """Pick up to ``k`` personas spread across the existing segment axes."""
    buckets: dict[str, list[str]] = {}
    for persona_id in persona_ids:
        persona = store.get_persona(persona_id)
        if not persona:
            continue
        segment = persona.get("segment") or {}
        key = str(
            segment.get("einstellung")
            or segment.get("lebensphase")
            or segment.get("kanal")
            or persona.get("slug")
        )
        buckets.setdefault(key, []).append(persona["slug"])
    pools = list(buckets.values())
    selected: list[str] = []
    index = 0
    while len(selected) < k and any(pools) and index < 500:
        pool = pools[index % len(pools)]
        if pool:
            selected.append(pool.pop(0))
        index += 1
    return selected[:k]
