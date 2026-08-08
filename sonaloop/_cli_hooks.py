"""The grounding + automation CLI surface: lifecycle hooks, evidence, project assets.

Split out of cli.py to keep it under the LOC bar (tests/test_loc_budget.py). The
hook commands mirror the MCP tools 1:1 (docs/lifecycle-hooks.md); evidence-attach
and the asset commands live here too — attaching evidence/assets emits the
`evidence.attached`/`asset.attached` events, so the seam that produces events and
the seam that subscribes to them stay together."""
from __future__ import annotations

from typing import Any

from . import services

COMMANDS = ("evidence-attach", "hooks-events", "hooks-list",
            "hook-register", "hook-remove", "hook-test",
            "asset-attach", "asset-list", "asset-get", "asset-remove",
            "corpus-ingest", "corpora-list", "corpus-search", "grounding-record", "evidence-trace")


def add_hook_parsers(sub) -> None:
    p = sub.add_parser("evidence-attach")
    p.add_argument("persona_id")
    p.add_argument("source_type")
    p.add_argument("content_or_path")
    p.add_argument("--notes")

    sub.add_parser("hooks-events", help="The documented lifecycle-event catalogue (names + payload contracts).")
    sub.add_parser("hooks-list", help="All durable hook registrations.")
    p = sub.add_parser("hook-register", help="Subscribe a command/webhook to a lifecycle event.")
    p.add_argument("event", help="Exact event name, 'domain.*', or '*' (see hooks-events).")
    p.add_argument("kind", choices=["command", "webhook"])
    p.add_argument("target", help="Shell command (envelope JSON on stdin) or URL to POST to.")
    p.add_argument("--label")
    p = sub.add_parser("hook-remove")
    p.add_argument("hook_id")
    p = sub.add_parser("hook-test", help="Fire a sample envelope through one hook to verify delivery.")
    p.add_argument("hook_id")

    p = sub.add_parser("asset-attach", help="Attach a file to a project: evidence in (default) or a deliverable out.")
    p.add_argument("project_id")
    p.add_argument("path")
    p.add_argument("--kind", choices=["image", "screenshot", "document", "file"])
    p.add_argument("--title")
    p.add_argument("--notes")
    p.add_argument("--direction", choices=["in", "out"],
                   help="in = evidence brought into the project (default) · out = deliverable produced from it")
    p.add_argument("--dispatch-token")
    p = sub.add_parser("asset-list")
    p.add_argument("project_id")
    p = sub.add_parser("asset-get")
    p.add_argument("project_id")
    p.add_argument("asset_id")
    p = sub.add_parser("asset-remove")
    p.add_argument("project_id")
    p.add_argument("asset_id")

    p = sub.add_parser("corpus-ingest", help="Ingest a real document (transcript/tickets/reviews) as citable chunks.")
    p.add_argument("content_or_path")
    p.add_argument("source_type")
    p.add_argument("--title")
    p.add_argument("--notes")
    sub.add_parser("corpora-list")
    p = sub.add_parser("corpus-search")
    p.add_argument("query")
    p.add_argument("--corpus", action="append", dest="corpora")
    p.add_argument("--limit", type=int, default=12)
    p = sub.add_parser("grounding-record", help="Persist authored grounding from a JSON file: {persona_id, corpus_ids, provenance, patch?, reason?}.")
    p.add_argument("file")
    p = sub.add_parser("evidence-trace", help="Resolve a cited chunk id back to its source + grounded claims.")
    p.add_argument("chunk_id")


def run_hook_command(args) -> Any:
    if args.command == "evidence-attach":
        return services.attach_evidence(args.persona_id, args.source_type, args.content_or_path, args.notes)
    if args.command == "hooks-events":
        return services.list_lifecycle_events()
    if args.command == "hooks-list":
        return services.list_hooks()
    if args.command == "hook-register":
        return services.register_hook(args.event, args.kind, args.target, args.label or "")
    if args.command == "hook-remove":
        return services.unregister_hook(args.hook_id)
    if args.command == "hook-test":
        return services.test_hook(args.hook_id)
    if args.command == "asset-attach":
        return services.attach_asset(args.project_id, path=args.path, kind=args.kind,
                                     title=args.title or "", notes=args.notes or "",
                                     direction=args.direction,
                                     dispatch_token=args.dispatch_token)
    if args.command == "asset-list":
        return services.list_assets(args.project_id)
    if args.command == "asset-get":
        return services.get_asset(args.project_id, args.asset_id)
    if args.command == "asset-remove":
        return services.remove_asset(args.project_id, args.asset_id)
    if args.command == "corpus-ingest":
        return services.ingest_corpus(args.content_or_path, args.source_type, args.title, args.notes)
    if args.command == "corpora-list":
        return services.list_corpora()
    if args.command == "corpus-search":
        return services.search_corpus(args.query, args.corpora, args.limit)
    if args.command == "grounding-record":
        import json
        from pathlib import Path
        return services.record_grounding(**json.loads(Path(args.file).read_text(encoding="utf-8")))
    return services.trace_evidence(args.chunk_id)
