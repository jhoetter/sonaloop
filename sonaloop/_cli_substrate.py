"""The queryable-substrate CLI surface (docs/substrate.md), mirroring the MCP
tools 1:1. Split out of cli.py to keep it under the LOC bar."""
from __future__ import annotations

from typing import Any

from . import services

COMMANDS = ("substrate-schema", "query-personas", "query-projects", "query-councils",
            "query-syntheses", "study-result", "predictions-aggregate", "calibration-report", "calibration-trend", "flow-define", "flows-list", "flow-funnel", "chat-brief", "chat-record", "chat-get", "chat-list")


def add_substrate_parsers(sub) -> None:
    sub.add_parser("substrate-schema", help="The versioned substrate contract (envelope, rows, filters).")
    for name, extra in (("query-personas", ()), ("query-projects", ("--status", "--since")),
                        ("query-councils", ("--project", "--persona", "--since")),
                        ("query-syntheses", ("--status", "--since"))):
        p = sub.add_parser(name, help="Paginated lean rows (newest first).")
        p.add_argument("--q")
        for flag in extra:
            p.add_argument(flag)
        p.add_argument("--limit", type=int, default=50)
        p.add_argument("--offset", type=int, default=0)
    p = sub.add_parser("study-result", help="One project's full structured result (the automation shape).")
    p.add_argument("project_id")
    p = sub.add_parser("predictions-aggregate", help="Segment roll-up of every predicted behavior in a project.")
    p.add_argument("project_id")
    p = sub.add_parser("calibration-report", help="Measure + persist a calibration snapshot (Brier, hit rate, reliability).")
    p.add_argument("--project")
    p = sub.add_parser("calibration-trend", help="Calibration quality over time (the Brier delta).")
    p.add_argument("--project")
    p = sub.add_parser("flow-define", help="Define an ordered screenshot flow from a JSON file: {project_id, title, steps:[{asset_id, caption?}], key?}.")
    p.add_argument("file")
    p.add_argument("--dispatch-token")
    p = sub.add_parser("flows-list")
    p.add_argument("project_id")
    p = sub.add_parser("flow-funnel", help="Where the cohort abandons a flow, and why.")
    p.add_argument("project_id")
    p.add_argument("flow_id")
    p = sub.add_parser("chat-brief", help="Gather context to author a persona's chat reply (host-authored).")
    p.add_argument("persona_id")
    p.add_argument("message")
    p.add_argument("--chat-id")
    p = sub.add_parser("chat-record", help="Persist one authored chat exchange.")
    p.add_argument("persona_id")
    p.add_argument("chat_id")
    p.add_argument("user_message")
    p.add_argument("persona_reply")
    p = sub.add_parser("chat-get")
    p.add_argument("chat_id")
    p = sub.add_parser("chat-list")
    p.add_argument("--persona")
    p.add_argument("--limit", type=int, default=50)
    p.add_argument("--offset", type=int, default=0)


def run_substrate_command(args) -> Any:
    if args.command == "substrate-schema":
        return services.substrate_schema()
    if args.command == "query-personas":
        return services.query_personas(args.q, args.limit, args.offset)
    if args.command == "query-projects":
        return services.query_projects(args.status, args.q, args.since, args.limit, args.offset)
    if args.command == "query-councils":
        return services.query_councils(args.project, args.persona, args.q, args.since,
                                       args.limit, args.offset)
    if args.command == "query-syntheses":
        return services.query_syntheses(args.status, args.q, args.since, args.limit, args.offset)
    if args.command == "study-result":
        return services.get_study_result(args.project_id)
    if args.command == "predictions-aggregate":
        return services.aggregate_predictions(args.project_id)
    if args.command == "calibration-report":
        return services.calibration_report(args.project)
    if args.command == "calibration-trend":
        return services.calibration_trend(args.project)
    if args.command == "flow-define":
        import json
        from pathlib import Path
        payload = json.loads(Path(args.file).read_text(encoding="utf-8"))
        payload.setdefault("dispatch_token", args.dispatch_token)
        return services.define_flow(**payload)
    if args.command == "flows-list":
        return services.list_flows(args.project_id)
    if args.command == "flow-funnel":
        return services.flow_funnel(args.project_id, args.flow_id)
    if args.command == "chat-brief":
        return services.chat_with_persona(args.persona_id, args.message, args.chat_id)
    if args.command == "chat-record":
        return services.record_chat_turn(args.persona_id, args.chat_id,
                                         args.user_message, args.persona_reply)
    if args.command == "chat-get":
        return services.get_chat(args.chat_id)
    return services.list_chats(args.persona, args.limit, args.offset)
