"""Customer-facing job state and result-first project presentation.

The governed run remains the operational truth.  This module derives a second,
strictly presentational truth from durable outputs: what a customer can use now.
An interrupted engine is therefore never relabelled "healthy"; when it already
produced a report, synthesis or prototype, the customer sees that result while
operators retain the exact recovery state on ``/runs``.
"""
from __future__ import annotations

from typing import Any

from ._html import fragment, h, raw, register_css
from ._i18n import t
from ._components import _icon, _label


def job_experience_state(record: dict[str, Any]) -> str:
    """Return one small customer vocabulary derived from durable outputs first."""
    outputs = sum(int(record.get(key) or 0) for key in (
        "reports", "job_outcomes", "studies", "prototypes", "deliverables"
    ))
    if outputs:
        return "result_ready"
    run = record.get("run_state") or record.get("health") or {}
    state = str(run.get("canonical_state") or run.get("state") or "").casefold()
    if state in {"active", "running"}:
        return "in_progress"
    if state == "waiting":
        return "input_required"
    if state == "finished":
        return "completed"
    if state in {"stalled", "expired", "unverified"}:
        return "paused"
    return "created"


_STATE_LABELS = {
    "result_ready": lambda: t("job_exp_result_ready"),
    "in_progress": lambda: t("job_exp_in_progress"),
    "input_required": lambda: t("job_exp_input_required"),
    "completed": lambda: t("job_exp_completed"),
    "paused": lambda: t("job_exp_paused"),
    "created": lambda: t("job_exp_created"),
}

_STATE_DESCRIPTIONS = {
    "result_ready": lambda: t("job_exp_result_ready_desc"),
    "in_progress": lambda: t("job_exp_in_progress_desc"),
    "input_required": lambda: t("job_exp_input_required_desc"),
    "completed": lambda: t("job_exp_completed_desc"),
    "paused": lambda: t("job_exp_paused_desc"),
    "created": lambda: t("job_exp_created_desc"),
}

_STATE_COLORS = {
    "result_ready": "var(--green)",
    "in_progress": "var(--accent)",
    "input_required": "var(--amber)",
    "completed": "var(--green)",
    "paused": "var(--muted)",
    "created": "var(--muted)",
}


def job_experience_badge(record: dict[str, Any]) -> str:
    state = job_experience_state(record)
    return _label(_STATE_LABELS[state](), _STATE_COLORS[state])


def _result_candidates(project_id: str, graph: dict[str, Any]) -> list[dict[str, str]]:
    candidates: list[dict[str, str]] = []
    for row in graph.get("reports") or []:
        candidates.append({
            "kind": t("synthesis_kind"), "title": row.get("title") or t("synthesis_kind"),
            "url": f'/syntheses/{row["id"]}', "created_at": row.get("created_at", ""),
            "priority": "50",
        })
    for row in graph.get("job_outcomes") or []:
        candidates.append({
            "kind": t("job_outcome_kind"), "title": row.get("title") or t("job_outcome_kind"),
            "url": f'/jobs/{project_id}/outcomes/{row["id"]}',
            "created_at": row.get("created_at", ""), "priority": "45",
        })
    for row in graph.get("nodes") or []:
        if row.get("kind") != "synthesis":
            continue
        sid = str(row.get("study_id") or row.get("id") or "").removeprefix("synthesis:")
        if sid:
            candidates.append({
                "kind": t("synthesis_kind"),
                "title": row.get("title") or t("synthesis_kind"),
                "url": f"/syntheses/{sid}", "created_at": row.get("created_at", ""),
                "priority": "40",
            })
    for row in graph.get("prototypes") or []:
        if row.get("id"):
            candidates.append({
                "kind": t("prototype_kind"),
                "title": row.get("title") or t("prototype_kind"),
                "url": f'/prototypes/{row["id"]}', "created_at": row.get("created_at", ""),
                "priority": "30",
            })
    for row in graph.get("assets") or []:
        if row.get("id") and row.get("direction") == "out":
            candidates.append({
                "kind": t("asset_dir_out"), "title": row.get("title") or row.get("filename") or t("asset_dir_out"),
                "url": f'/assets/{row["id"]}', "created_at": row.get("created_at", ""),
                "priority": "20",
            })
    return sorted(candidates, key=lambda row: (row["priority"], row["created_at"]), reverse=True)


register_css(r"""
.sl-job-exp{display:flex;align-items:center;justify-content:space-between;gap:18px;margin:14px 0 4px;padding:14px 16px;border:1px solid var(--line);border-radius:var(--radius);background:var(--panel)}
.sl-job-exp__copy{min-width:0}.sl-job-exp__copy strong{display:block;font-size:var(--t-md)}
.sl-job-exp__copy p{margin:3px 0 0;color:var(--muted);font-size:var(--t-sm);line-height:1.45}
.sl-job-exp__actions{display:flex;align-items:center;gap:8px;flex:none}
.sl-job-results{margin:16px auto 0;width:100%;max-width:900px;padding:0 24px}
.sl-job-results h2{font-size:var(--t-md);margin:0 0 8px}.sl-job-results__rows{display:grid;gap:7px}
.sl-job-result{display:flex;align-items:center;gap:10px;padding:10px 12px;border:1px solid var(--line);border-radius:var(--radius);background:var(--panel);color:var(--ink);text-decoration:none}
.sl-job-result:hover{background:var(--hover)}.sl-job-result svg{width:16px;color:var(--accent)}
.sl-job-result__title{flex:1;min-width:0;font-weight:600}.sl-job-result__kind{color:var(--muted);font-size:var(--t-sm)}
.sl-job-details{width:100%;max-width:900px;margin:14px auto 0;padding:0 24px}.sl-job-details>summary{cursor:pointer;color:var(--muted);font-size:var(--t-sm);font-weight:600;margin-bottom:10px}
.sl-job-details .outlinecard{padding-left:0;padding-right:0}
@media(max-width:640px){.sl-job-exp{align-items:flex-start;flex-direction:column}.sl-job-exp__actions{width:100%}.sl-job-exp__actions .sl-btn{width:100%;justify-content:center}.sl-job-results,.sl-job-details{padding:0 16px}}
""")


def customer_job_header(project: dict[str, Any], graph: dict[str, Any],
                        health: dict[str, Any] | None = None) -> str:
    candidates = _result_candidates(project["id"], graph)
    record = {
        "reports": len(graph.get("reports") or []),
        "job_outcomes": len(graph.get("job_outcomes") or []),
        "studies": sum(1 for row in graph.get("nodes") or [] if row.get("kind") == "synthesis"),
        "prototypes": len(graph.get("prototypes") or []),
        "deliverables": sum(1 for row in graph.get("assets") or [] if row.get("direction") == "out"),
        "health": health or {},
    }
    state = job_experience_state(record)
    primary = candidates[0] if candidates else None
    action = (h("a", {"class_": "sl-btn sl-btn--primary", "href": primary["url"]},
                raw(_icon("arrowRight")), " ", t("job_exp_open_result")) if primary else None)
    return h(
        "div", {"class_": f"sl-job-exp sl-job-exp--{state}", "data-job-experience": state},
        h("div", {"class_": "sl-job-exp__copy"},
          h("strong", {}, _STATE_LABELS[state]()),
          h("p", {}, _STATE_DESCRIPTIONS[state]())),
        h("div", {"class_": "sl-job-exp__actions"}, raw(action or "")),
    )


def customer_results(project_id: str, graph: dict[str, Any]) -> str:
    candidates = _result_candidates(project_id, graph)
    if not candidates:
        return ""
    rows = [h("a", {"class_": "sl-job-result", "href": row["url"]},
              raw(_icon("overview")),
              h("span", {"class_": "sl-job-result__title"}, row["title"]),
              h("span", {"class_": "sl-job-result__kind"}, row["kind"]),
              raw(_icon("arrowRight"))) for row in candidates]
    return h("section", {"class_": "sl-job-results", "aria-label": t("job_exp_results_h")},
             h("h2", {}, t("job_exp_results_h")),
             h("div", {"class_": "sl-job-results__rows"}, fragment(*rows)))
