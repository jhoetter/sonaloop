"""Research-plan preflight task seeds (kept out of the core plan engine)."""
from __future__ import annotations

from typing import Any


def seed_preflight_tasks(integrity: dict[str, Any], root_frame_ids: list[str]) -> tuple[
        list[dict[str, Any]], bool, bool, str, str]:
    product = bool(integrity.get("product_understanding_required"))
    cohort = bool(integrity.get("cohort_preflight_required"))
    product_id = "preflight__product_understanding"
    cohort_id = "preflight__cohort_integrity"
    tasks: list[dict[str, Any]] = []
    if product:
        tasks.append({
            "id": product_id, "title": "Preflight · Product understanding",
            "bucket": "analyze", "capability": "product_understanding",
            "step": "__preflight__", "consumes": [],
            "intent": (
                "Inspect and inventory the actual target before personas react: record its identity, "
                "revision/time, routes/flows/states, observed-present/observed-absent/inferred/unknown "
                "capabilities and exact evidence refs via record_product_understanding."
            ),
            "produces": [],
        })
    if cohort:
        tasks.append({
            "id": cohort_id, "title": "Preflight · Cohort integrity",
            "bucket": "analyze", "capability": "cohort_integrity",
            "step": "__preflight__",
            # Final gate follows the root frame so actual hypotheses are server-bound inputs.
            "consumes": root_frame_ids or ([product_id] if product else []),
            "intent": (
                "Measure persona memory/event/evidence depth and source/age provenance; compare "
                "the framed research hypotheses and external product stimulus with persona claims "
                "using the versioned lexical feature; declare grounded skeptical/indifferent/"
                "non-target representation; then persist the server-owned cohort gate."
            ),
            "produces": [],
        })
    return tasks, product, cohort, product_id, cohort_id


def seed_work_item_tasks(step: dict[str, Any], frame_id: str,
                         barrier_id: str = "") -> list[dict[str, Any]]:
    """Expand optional methodology-authored Act todos without domain vocabularies."""
    consumes = [frame_id] + ([barrier_id] if barrier_id else [])
    return [{
        "id": f"act__{step['id']}__{item['id']}", "title": item["title"],
        "bucket": "act", "capability": item["capability"], "step": step["id"],
        "expected_output_kind": item["expected_output_kind"],
        "intent": item["intent"], "consumes": consumes, "produces": [],
        "presentation": item.get("presentation") or step.get("presentation") or {},
    } for item in step.get("work_items") or []]
