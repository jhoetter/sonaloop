"""Evidence and grounded-session gate checks for research-plan verify tasks."""

from __future__ import annotations

from typing import Any

from .storage import Store


def fan_tasks(plan: dict[str, Any], verify_task: dict[str, Any]) -> list[dict[str, Any]]:
    """Act-task fan consolidated by a verify task through shared consumed frames."""
    frames = set(verify_task["consumes"])
    return [task for task in plan["tasks"]
            if task["id"] != verify_task["id"]
            and (set(task["consumes"]) & frames)
            and task["bucket"] != "verify"]


def fan_evidence(plan: dict[str, Any], verify_task: dict[str, Any]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for task in fan_tasks(plan, verify_task):
        for ref in task["produces"]:
            if ref["kind"] != "frame":
                out.append(ref)
    return out


def effective_minimum(verify_task: dict[str, Any]) -> int:
    minimum = verify_task["requires"]["min_inputs"]
    return minimum if minimum is not None else 2


def grounding_verifiable() -> bool:
    """Whether the Playwright harness can distinguish grounded from recorded-only sessions."""
    try:
        from . import browser

        return bool(browser.available())
    except Exception:
        return False


def verify_unmet(plan: dict[str, Any], verify_task: dict[str, Any], store: Store) -> list[str]:
    """Return, without raising, what a verify task still needs before completion."""
    from . import methodology

    project_id = plan["project_id"]
    requirements = verify_task["requires"]
    unmet: list[str] = []
    # Count distinct evidence-producing tasks, not raw refs: one artifact plus many
    # sessions must not masquerade as breadth across distinct research angles.
    evidence_tasks = [
        task for task in fan_tasks(plan, verify_task)
        if any(ref.get("kind") != "frame" for ref in task.get("produces", []))
    ]
    minimum = effective_minimum(verify_task)
    if len(evidence_tasks) < minimum:
        unmet.append(
            f"need >= {minimum} act tasks (distinct angles) with evidence in the fan "
            f"(have {len(evidence_tasks)})"
        )
    if requirements["gate_tag"]:
        scope = {
            verify_task["id"],
            *verify_task["consumes"],
            *[task["id"] for task in fan_tasks(plan, verify_task)],
        }
        decided = any(
            judgment.get("decided")
            and judgment["gate_tag"] == requirements["gate_tag"]
            and judgment["task_id"] in scope
            for judgment in plan.get("judgments", [])
        )
        if not decided:
            unmet.append(f"a decided `{requirements['gate_tag']}` judgment must exist")
    for tag in requirements["artifact_tags"]:
        if not methodology._project_artifacts_with(store, project_id, tag):
            unmet.append(f"need >= 1 artifact tagged `{tag}`")
    for tag in requirements["session_of_tags"]:
        sessions = methodology._sessions_of(store, project_id, tag)
        if not sessions:
            unmet.append(f"need >= 1 recorded session of an artifact tagged `{tag}`")
        elif grounding_verifiable() and not any(s.get("grounded_verified") for s in sessions):
            unmet.append(
                f"need >= 1 GROUNDED session of `{tag}` — {len(sessions)} recorded but none verified "
                "against real observed usage; drive the prototype (proto_open/proto_act) and "
                "cite states you actually saw, then record"
            )
    try:
        from .research_integrity import reaction_task_gaps

        unmet.extend(reaction_task_gaps(project_id, verify_task, plan, store))
    except Exception as exc:
        # Integrity reads fail closed: decode/storage failures never imply permission
        # to call a Reaction Test complete.
        if (plan.get("integrity") or {}).get("claim_posture_required"):
            unmet.append(f"research-integrity evidence unavailable: {exc}")
    return unmet
