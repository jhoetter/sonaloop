"""Read-only inspector for the server-owned Reaction Test cohort gate."""
from __future__ import annotations

from ..cohort_integrity import current_cohort_preflight, preflight_satisfies_project
from ._components import _icon, _label
from ._html import fragment, h, raw, register_css
from ._i18n import t
from . import ui


register_css(r"""
.sl-cohort-card{border:1px solid var(--line);border-left:3px solid var(--green);border-radius:var(--radius);background:var(--panel);padding:12px 14px;margin:14px 0}.sl-cohort-card--warn,.sl-cohort-card--missing{border-left-color:var(--amber)}.sl-cohort-card--blocked{border-left-color:var(--red)}
.sl-cohort-head{display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap}.sl-cohort-head strong{display:flex;align-items:center;gap:7px}.sl-cohort-pills{display:flex;gap:6px;flex-wrap:wrap}.sl-cohort-meta{color:var(--muted);font-size:var(--t-sm);margin-top:5px}.sl-cohort-grid{display:grid;grid-template-columns:repeat(3,minmax(110px,1fr));gap:8px;margin:11px 0}.sl-cohort-stat{border:1px solid var(--line);border-radius:var(--radius-sm);padding:8px;background:var(--panel-2);font-size:var(--t-sm)}.sl-cohort-stat strong{display:block;font-size:var(--t-lg)}.sl-cohort-list{margin:9px 0 0;padding-left:18px;font-size:var(--t-sm)}.sl-cohort-personas{margin:8px 0 0;padding-left:18px;font-size:var(--t-xs);color:var(--muted)}.sl-cohort-limitation{border-left:2px solid var(--amber);padding-left:9px;margin-top:10px;color:var(--muted);font-size:var(--t-sm)}@media(max-width:640px){.sl-cohort-grid{grid-template-columns:1fr}}
""")


def _maximum_score(rows: list[dict]) -> float:
    return max((float(row.get("score") or 0) for row in rows), default=0.0)


def render_cohort_integrity(project: dict, store=None, *, show_missing: bool = True,
                            embedded: bool = False) -> str:
    """Render persisted depth, provenance, leakage and remediation state."""
    policy = project.get("integrity") or {}
    current = current_cohort_preflight(project)
    required = bool(policy.get("cohort_preflight_required"))
    if not current:
        if not required:
            return ""
        if not show_missing:
            return ""
        return h(
            "section",
            {"class_": "sl-cohort-card sl-cohort-card--missing", "id": "cohort-integrity",
             "role": "status", "aria-label": t("cohort_integrity_missing_help")},
            h("div", {"class_": "sl-cohort-head"},
              h("strong", {}, raw(_icon("personas")), t("cohort_integrity_h")),
              raw(_label(t("cohort_integrity_missing"), "var(--amber)"))),
            h("div", {"class_": "sl-cohort-meta"}, t("cohort_integrity_missing_help")),
        )

    stale = not preflight_satisfies_project(project, store)
    status = "stale" if stale else str(current.get("status") or "needs_reselection")
    labels = {
        "pass": t("cohort_status_pass"),
        "overridden": t("cohort_status_overridden"),
        "needs_deepening": t("cohort_status_needs_deepening"),
        "needs_reselection": t("cohort_status_needs_reselection"),
        "stale": t("cohort_status_stale"),
    }
    colors = {
        "pass": "var(--green)", "overridden": "var(--amber)",
        "needs_deepening": "var(--amber)", "needs_reselection": "var(--red)",
        "stale": "var(--red)",
    }
    card_state = ("warn" if status in {"overridden", "needs_deepening"}
                  else "blocked" if status in {"needs_reselection", "stale"} else "pass")
    totals = (current.get("depth") or {}).get("totals") or {}
    leakage = current.get("leakage") or {}
    lexical_max = _maximum_score(leakage.get("lexical") or [])
    semantic = leakage.get("semantic") or {}
    semantic_max = _maximum_score(semantic.get("scores") or []) if semantic.get("provided") else None
    representation = current.get("representation") or {}
    required_work = current.get("required_work") or []
    persona_rows = []
    for row in (current.get("depth") or {}).get("personas") or []:
        depth = row.get("depth") or {}
        provenance = row.get("source_provenance") or {}
        age = row.get("profile_age_hours_at_project_start")
        age_text = t("cohort_age_unknown") if age is None else t("cohort_age_hours", n=age)
        persona_rows.append(h(
            "li", {},
            t("cohort_persona_summary", name=row.get("display_name") or row.get("persona_id") or "—",
              items=depth.get("independent_context_items", 0),
              origin=provenance.get("origin") or "unknown", age=age_text),
            (" · " + t("cohort_persona_thin") if row.get("thin") else ""),
        ))
    work_rows = [h(
        "li", {}, h("code", {}, row.get("code") or row.get("kind") or "—"),
        (" · " + ", ".join(row.get("tools") or [])) if row.get("tools") else "",
    ) for row in required_work]
    limitation = current.get("override") or {}
    meta = t("cohort_policy_meta", version=current.get("policy_version") or "—",
             evaluated=ui.fmt_ts(current.get("evaluated_at") or ""))
    aria = f'{t("cohort_integrity_h")}: {labels.get(status, status)}. '
    aria += t("cohort_depth_summary", personas=totals.get("personas", 0),
              items=totals.get("independent_context_items", 0), thin=totals.get("thin", 0))
    tag = "section" if embedded else "details"
    wrapper_class = (f"sl-setup-block sl-setup-block--cohort sl-cohort-card--{card_state}"
                     if embedded else f"sl-cohort-card sl-cohort-card--{card_state}")
    head_tag = "div" if embedded else "summary"
    return h(
        tag, {"class_": wrapper_class, "id": "cohort-integrity", "aria-label": aria},
        h(head_tag, {"class_": "sl-cohort-head"},
          h("strong", {}, raw(_icon("personas")), t("cohort_integrity_h")),
          h("span", {"class_": "sl-cohort-pills"},
            raw(_label(labels.get(status, status), colors.get(status, "var(--muted)"))),
            raw(_label(t("cohort_countervoices_n", n=representation.get("countervoice_count", 0)))),
            (raw(_label(t("cohort_unverified_countervoices_n",
                          n=len(representation.get("unverified_countervoice_persona_ids") or [])),
                        "var(--red)"))
             if representation.get("unverified_countervoice_persona_ids") else None),
            raw(_label(t("cohort_thin_n", n=totals.get("thin", 0)),
                       "var(--amber)" if totals.get("thin") else "var(--green)")))),
        h("div", {"class_": "sl-cohort-meta"},
          t("cohort_integrity_stale_help") if stale else t("cohort_boundary_help")),
        h("div", {"class_": "sl-cohort-meta"}, meta),
        h("div", {"class_": "sl-cohort-grid"},
          h("div", {"class_": "sl-cohort-stat"},
            h("strong", {}, str(totals.get("independent_context_items", 0))),
            t("cohort_independent_items")),
          h("div", {"class_": "sl-cohort-stat"},
            h("strong", {}, f"{lexical_max:.0%}"), t("cohort_lexical_overlap")),
          h("div", {"class_": "sl-cohort-stat"},
            h("strong", {}, "—" if semantic_max is None else f"{semantic_max:.0%}"),
            t("cohort_semantic_overlap"))),
        (fragment(h("div", {"class_": "sl-cohort-meta"}, t("cohort_required_work")),
                  h("ul", {"class_": "sl-cohort-list"}, fragment(*work_rows)))
         if work_rows else None),
        (h("div", {"class_": "sl-cohort-limitation"},
           h("strong", {}, t("cohort_override_limitation")), " ", limitation.get("rationale", ""))
         if limitation else None),
        h("ul", {"class_": "sl-cohort-personas"}, fragment(*persona_rows)),
    )
