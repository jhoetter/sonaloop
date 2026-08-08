"""CLI parity for Product Understanding and claim/dispatch integrity."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import services

COMMANDS = ("product-understanding-brief", "product-understanding-record",
            "product-understanding-get", "cohort-preflight-brief",
            "cohort-preflight-record", "cohort-preflight-get",
            "project-health", "run-resume",
            "project-supersede", "project-archive")


def add_integrity_parsers(sub) -> None:
    p = sub.add_parser(
        "product-understanding-brief",
        help="Gather the mandatory evidence-bound Reaction Test product preflight.")
    p.add_argument("project_id")
    p = sub.add_parser(
        "product-understanding-record",
        help="Append an immutable Product Understanding JSON version.")
    p.add_argument("project_id")
    p.add_argument("file", help="JSON: target, revision, routes, flows, states, capabilities, evidence_refs?, stimulus_manifest?, coverage_checklist?, observed_at?")
    p.add_argument("--key")
    p.add_argument("--dispatch-token")
    p = sub.add_parser("product-understanding-get")
    p.add_argument("project_id")
    p.add_argument("--version", dest="version_id")
    p = sub.add_parser(
        "cohort-preflight-brief",
        help="Gather deterministic cohort depth/leakage inputs and remediation preview.")
    p.add_argument("project_id")
    p.add_argument("--hypothesis", action="append", dest="hypotheses")
    p = sub.add_parser(
        "cohort-preflight-record",
        help="Persist an immutable cohort gate; failed gates inject required plan work.")
    p.add_argument("project_id")
    p.add_argument("file", help="JSON: hypotheses?, representation, semantic_feature?, override_rationale?, persona_ids?")
    p.add_argument("--key")
    p.add_argument("--dispatch-token")
    p = sub.add_parser("cohort-preflight-get")
    p.add_argument("project_id")
    p.add_argument("--version", dest="version_id")
    p = sub.add_parser("project-health", help="Canonical evidence/run health and safe next action.")
    p.add_argument("project_id")
    p = sub.add_parser("run-resume", help="Resume exactly one existing active run; never creates/finishes.")
    p.add_argument("project_id")
    p.add_argument("run_id")
    p.add_argument("--operation-id", default="")
    p = sub.add_parser("project-supersede", help="Preserve explicit old→new project lineage; deletes nothing.")
    p.add_argument("project_id", help="The canonical/new project.")
    p.add_argument("supersedes_project_id", help="The obsolete predecessor.")
    p.add_argument("--operation-id", required=True)
    p.add_argument("--reason", required=True)
    p = sub.add_parser("project-archive", help="Explicit non-destructive archive; active runs are blocked.")
    p.add_argument("project_id")
    p.add_argument("--operation-id", required=True)
    p.add_argument("--reason", required=True)


def run_integrity_command(args) -> Any:
    if args.command == "project-health":
        return services.project_health(args.project_id)
    if args.command == "run-resume":
        return services.resume_project_run(args.project_id, args.run_id, args.operation_id)
    if args.command == "project-supersede":
        return services.supersede_project(
            args.project_id, args.supersedes_project_id, args.operation_id, args.reason)
    if args.command == "project-archive":
        return services.archive_project(args.project_id, args.operation_id, args.reason)
    if args.command == "product-understanding-brief":
        return services.brief_product_understanding(args.project_id)
    if args.command == "product-understanding-get":
        return services.get_product_understanding(args.project_id, args.version_id)
    if args.command == "cohort-preflight-brief":
        return services.brief_cohort_preflight(args.project_id, args.hypotheses)
    if args.command == "cohort-preflight-get":
        return services.get_cohort_preflight(args.project_id, args.version_id)
    payload = json.loads(Path(args.file).read_text(encoding="utf-8"))
    if args.command == "cohort-preflight-record":
        return services.record_cohort_preflight(
            args.project_id,
            hypotheses=payload.get("hypotheses") or [],
            representation=payload.get("representation") or [],
            semantic_feature=payload.get("semantic_feature"),
            override_rationale=payload.get("override_rationale") or "",
            persona_ids=payload.get("persona_ids"),
            selection_rationale=payload.get("selection_rationale") or "",
            evaluated_at=payload.get("evaluated_at"),
            key=args.key or payload.get("key"),
            dispatch_token=args.dispatch_token or payload.get("dispatch_token"),
        )
    return services.record_product_understanding(
        args.project_id,
        target=payload.get("target") or {},
        revision=payload.get("revision") or "",
        routes=payload.get("routes") or [],
        flows=payload.get("flows") or [],
        states=payload.get("states") or [],
        capabilities=payload.get("capabilities") or [],
        evidence_refs=payload.get("evidence_refs") or [],
        stimulus_manifest=payload.get("stimulus_manifest"),
        coverage_checklist=payload.get("coverage_checklist"),
        observed_at=payload.get("observed_at"),
        key=args.key or payload.get("key"),
        dispatch_token=args.dispatch_token or payload.get("dispatch_token"),
    )
