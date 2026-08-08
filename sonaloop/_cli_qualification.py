"""CLI adapter for the offline/captured provider qualification harness."""
from __future__ import annotations

from typing import Any

from .qualification import (
    RecordedQualificationAdapter,
    list_qualification_fixtures,
    qualification_contracts,
    run_provider_qualification,
    write_qualification_report,
)


COMMANDS = ("qualification-fixtures", "qualification-contract", "qualification-run")


def add_qualification_parsers(sub) -> None:
    sub.add_parser(
        "qualification-fixtures",
        help="List the privacy-safe, held-out provider qualification fixtures.")
    p = sub.add_parser(
        "qualification-contract",
        help="Emit the exact context/tools/assets/budget contract an adapter must use.")
    p.add_argument("--fixture", action="append", dest="fixtures")
    p = sub.add_parser(
        "qualification-run",
        help="Replay one or more recorded provider submissions through real Core contracts.")
    p.add_argument("--submission", action="append", required=True,
                   help="JSON submission (repeat to compare providers under one contract).")
    p.add_argument("--fixture", action="append", dest="fixtures")
    p.add_argument("--out", help="Write the complete versioned JSON report to this path.")


def run_qualification_command(args) -> Any:
    if args.command == "qualification-fixtures":
        return {"fixtures": list_qualification_fixtures()}
    if args.command == "qualification-contract":
        return {"contracts": qualification_contracts(args.fixtures)}
    adapters = [RecordedQualificationAdapter.from_path(path) for path in args.submission]
    report = run_provider_qualification(adapters, args.fixtures)
    if args.out:
        return {"path": write_qualification_report(report, args.out),
                "schema": report["schema"], "summary": report["summary"]}
    return report
