"""Parking and re-admitting plan evidence without changing the evidence record itself."""
from __future__ import annotations

from typing import Any

from .config import utc_now_iso
from .storage import Store


def _ref_text(raw: Any) -> str:
    if isinstance(raw, dict):
        kind, rid = str(raw.get("kind") or ""), str(raw.get("id") or "")
        return f"{kind}:{rid}" if kind and rid else rid
    return str(raw or "").strip()


def _clean_refs(refs: list[Any] | None, code: str) -> list[str]:
    clean = list(dict.fromkeys(r for r in (_ref_text(x) for x in (refs or [])) if r))
    if not clean:
        from .plan import PlanError
        raise PlanError(code, f"{code.lower()} needs >= 1 evidence ref")
    return clean


def park_evidence(project_id: str, refs: list[Any], reason: str, task_id: str = "",
                  store: Store | None = None) -> dict[str, Any]:
    """Keep evidence visible while deliberately excluding it from a downstream gate."""
    from . import plan as P

    store = store or Store()
    plan = P.get_plan(project_id, store=store)
    if plan is None:
        raise P.PlanError("NO_PLAN", f"project {project_id} has no plan")
    if task_id and P.task(plan, task_id) is None:
        raise P.PlanError("BAD_PARK", f"unknown task '{task_id}'")
    clean = _clean_refs(refs, "BAD_PARK")
    why = str(reason or "").strip()
    if not why:
        raise P.PlanError("BAD_PARK", "park_evidence needs a reason")
    rec = {"task_id": task_id, "refs": clean, "reason": why, "created_at": utc_now_iso()}
    parked = plan.setdefault("parked_refs", [])
    key = (task_id, tuple(sorted(clean)), why)
    if not any((p.get("task_id", ""), tuple(sorted(p.get("refs") or [])), p.get("reason", "")) == key
               for p in parked):
        parked.append(rec)
        P.save_plan(plan, store=store)
    return rec


def unpark_evidence(project_id: str, refs: list[Any], reason: str, task_id: str = "",
                    store: Store | None = None) -> dict[str, Any]:
    """Re-admit exact parked refs and retain an explicit audit record of the correction."""
    from . import plan as P

    store = store or Store()
    plan = P.get_plan(project_id, store=store)
    if plan is None:
        raise P.PlanError("NO_PLAN", f"project {project_id} has no plan")
    if task_id and P.task(plan, task_id) is None:
        raise P.PlanError("BAD_UNPARK", f"unknown task '{task_id}'")
    clean = _clean_refs(refs, "BAD_UNPARK")
    why = str(reason or "").strip()
    if not why:
        raise P.PlanError("BAD_UNPARK", "unpark_evidence needs a reason")
    targets, removed, remaining = set(clean), set(), []
    for row in plan.get("parked_refs") or []:
        if str(row.get("task_id") or "") != task_id:
            remaining.append(row)
            continue
        kept = [ref for ref in (row.get("refs") or []) if str(ref) not in targets]
        removed.update(str(ref) for ref in (row.get("refs") or []) if str(ref) in targets)
        if kept:
            remaining.append({**row, "refs": kept})
    if not removed:
        raise P.PlanError("BAD_UNPARK", "none of the requested refs are parked in that scope")
    plan["parked_refs"] = remaining
    rec = {"task_id": task_id, "refs": sorted(removed), "reason": why,
           "created_at": utc_now_iso()}
    plan.setdefault("unparked_refs", []).append(rec)
    P.save_plan(plan, store=store)
    return rec
