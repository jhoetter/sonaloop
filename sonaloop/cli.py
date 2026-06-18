from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .avatar import generate_persona_avatar
from .config import load_env
from . import services, _cli_hooks, _cli_substrate, _cli_data, _cli_feedback, _cli_catalog


def _pkg_version() -> str:
    try:
        from importlib.metadata import version
        return version("sonaloop")
    except Exception:
        return "0.0.0+local"


def _print(data: Any, as_json: bool = True) -> None:
    if as_json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        print(data)


def _read_descriptions(path: str) -> list[str]:
    text = Path(path).read_text(encoding="utf-8")
    if "\n\n" in text:
        return [chunk.strip(" -\n\t") for chunk in text.split("\n\n") if chunk.strip()]
    return [line.strip(" -\t") for line in text.splitlines() if line.strip()]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sonaloop")
    sub = parser.add_subparsers(dest="command", required=True)

    # Onboarding: setup + the agent-facing guide + diagnostics (matter most for a fresh install).
    sub.add_parser("setup", help="Fetch the headless-browser binary (prototype screenshots + PDF export).")
    sub.add_parser("guide", help="Print the agent operating contract + first-run recipe (read & follow it).")
    sub.add_parser("info", help="Diagnostics: data dir, DB, optional providers, and MCP wiring "
                                "(prints the exact per-host register one-liners when missing).")

    p = sub.add_parser("persona-create")
    p.add_argument("description")
    p.add_argument("--segment")
    p.add_argument("--evidence")
    p.add_argument("--avatar", action="store_true")

    # host-authored persona creation (gather -> author -> persist)
    p = sub.add_parser("brief-persona")
    p.add_argument("description")
    p.add_argument("--segment")
    p.add_argument("--evidence")
    p = sub.add_parser("record-persona")
    p.add_argument("file", help="JSON: {description, profile, segment_hint?, evidence?, generate_avatar?}")

    p = sub.add_parser("persona-bulk")
    p.add_argument("file")
    p.add_argument("--segment")
    p.add_argument("--avatar", action="store_true")

    p = sub.add_parser("persona-list")
    p.add_argument("--filter")
    p.add_argument("--full", action="store_true")  # full profiles; default is the compact summary (F1)

    p = sub.add_parser("persona-get")
    p.add_argument("persona_id")

    p = sub.add_parser("persona-soul")
    p.add_argument("persona_id")
    p.add_argument("--path-only", action="store_true")

    p = sub.add_parser("persona-context")
    p.add_argument("persona_id")
    p.add_argument("--task")
    p.add_argument("--recent-events", type=int, default=8)
    p.add_argument("--text", action="store_true")

    p = sub.add_parser("persona-update")
    p.add_argument("persona_id")
    p.add_argument("patch_json")
    p.add_argument("--reason", default="cli update")

    p = sub.add_parser("persona-refresh", help="Re-pull a catalog persona from its source "
                                               "(drift-safe; --force overwrites local edits).")
    p.add_argument("persona_id"); p.add_argument("--force", action="store_true")
    _cli_catalog.add_catalog_parsers(sub)     # `sonaloop catalog-*`: browse/recommend/status/pull

    p = sub.add_parser("avatar-generate")
    p.add_argument("persona_id")
    p.add_argument("--style")

    sub.add_parser("simulate-clear")

    p = sub.add_parser("purge-runtime-data")
    p.add_argument("--keep-files", action="store_true")

    p = sub.add_parser("state")
    p.add_argument("persona_id")

    p = sub.add_parser("calendar")
    p.add_argument("persona_id")
    p.add_argument("--date")
    p.add_argument("--view", choices=["day", "week", "month", "year"], default="day")

    p = sub.add_parser("activity")
    p.add_argument("activity_id")

    p = sub.add_parser("summary")
    p.add_argument("persona_id")
    p.add_argument("--start")
    p.add_argument("--end")

    p = sub.add_parser("pain-points")
    p.add_argument("persona_id")
    p.add_argument("--start")
    p.add_argument("--end")

    p = sub.add_parser("council-run")
    p.add_argument("prompt")
    p.add_argument("--persona", action="append", dest="personas")
    p.add_argument("--rounds", type=int, default=3)

    p = sub.add_parser("brief-council")
    p.add_argument("project_id")
    p.add_argument("prompt")
    p.add_argument("--persona", action="append", dest="personas")
    p.add_argument("--count", type=int, default=3)
    p.add_argument("--context")

    p = sub.add_parser("brief-ask")
    p.add_argument("persona_id")
    p.add_argument("question")
    p.add_argument("--context")

    p = sub.add_parser("ask")
    p.add_argument("persona_id")
    p.add_argument("question")

    p = sub.add_parser("compare")
    p.add_argument("prompt")
    p.add_argument("personas", nargs="+")

    sub.add_parser("taxonomy-lint", help="Validate taxonomy.json structural completeness (framework/"
                   "format keys, coverage, protocol blocks, doc sections). Exit code 1 on problems.")
    sub.add_parser("primitive-list", help="List registered Library primitives from primitive_taxonomy.json.")
    p = sub.add_parser("form-list", help="List registered primitive forms, optionally for one primitive.")
    p.add_argument("--primitive")
    p = sub.add_parser("form-get", help="Inspect one registered primitive form by primitive and form/alias id.")
    p.add_argument("primitive")
    p.add_argument("form_id")
    p = sub.add_parser("forms-suggest", help="Show forms and payload shapes for one primitive.")
    p.add_argument("primitive")
    sub.add_parser("result-schema-list", help="List result schemas and registry validation errors.")
    p = sub.add_parser("result-schema-get", help="Inspect one result schema.")
    p.add_argument("schema_id")
    sub.add_parser("result-contract-list", help="List Job and methodology result contracts.")
    p = sub.add_parser("result-contract-job", help="Inspect one Job result contract.")
    p.add_argument("job_id")
    p = sub.add_parser("result-contract-methodology", help="Inspect one methodology result contract.")
    p.add_argument("methodology_key")

    _cli_hooks.add_hook_parsers(sub)
    _cli_substrate.add_substrate_parsers(sub)

    p = sub.add_parser("export-persona"); p.add_argument("persona_id"); p.add_argument("--format", choices=["json", "md"], default="json"); p.add_argument("--out")

    p = sub.add_parser("export-logs")
    p.add_argument("persona_id")
    p.add_argument("--start")
    p.add_argument("--end")
    p.add_argument("--format", choices=["json", "csv", "md"], default="json")
    p.add_argument("--out")

    p = sub.add_parser("logs")
    p.add_argument("persona_id")
    p.add_argument("--start")
    p.add_argument("--end")
    p.add_argument("--format", choices=["json", "csv", "md"], default="md")
    p.add_argument("--out")

    p = sub.add_parser("export-council"); p.add_argument("session_id"); p.add_argument("--format", choices=["json", "md"], default="json"); p.add_argument("--out")

    # ---- memory & multi-resolution loop ----
    p = sub.add_parser("recall")
    p.add_argument("persona_id")
    p.add_argument("query")
    p.add_argument("--as-of")
    p.add_argument("--k", type=int, default=8)

    p = sub.add_parser("projects")
    p.add_argument("persona_id")

    p = sub.add_parser("project")
    p.add_argument("persona_id")
    p.add_argument("entity_id")
    p.add_argument("--as-of")

    p = sub.add_parser("state-at")
    p.add_argument("persona_id")
    p.add_argument("as_of")

    p = sub.add_parser("timeline")
    p.add_argument("persona_id")
    p.add_argument("--start")
    p.add_argument("--end")
    p.add_argument("--entity")

    p = sub.add_parser("entities")
    p.add_argument("persona_id")
    p.add_argument("--kind")
    p.add_argument("--name")

    p = sub.add_parser("loops")
    p.add_argument("persona_id")
    p.add_argument("--status", default="open")

    p = sub.add_parser("memory")
    p.add_argument("persona_id")

    p = sub.add_parser("digests")
    p.add_argument("persona_id")
    p.add_argument("--scope")

    p = sub.add_parser("plans")
    p.add_argument("persona_id")
    p.add_argument("--scope")

    p = sub.add_parser("evaluate")
    p.add_argument("--persona")
    p.add_argument("--start")
    p.add_argument("--end")

    p = sub.add_parser("anomalies")
    p.add_argument("--persona")

    p = sub.add_parser("backfill-embeddings")
    p.add_argument("--persona")

    p = sub.add_parser("prune-memory")
    p.add_argument("persona_id")
    p.add_argument("--keep-days", type=int, default=120)
    p.add_argument("--as-of")

    p = sub.add_parser("world-get")
    p.add_argument("--as-of")

    p = sub.add_parser("world-set")
    p.add_argument("file", help="JSON file: list of {category, fact, valid_from, valid_to?, relevance_tags?}")

    sub.add_parser("language")
    p = sub.add_parser("set-language")
    p.add_argument("--content", choices=["de", "en"])
    p.add_argument("--ui", choices=["de", "en"])

    # brief_* (gather → print instructions+frame for authoring)
    for name in ["brief-day", "brief-consolidation", "brief-digest", "brief-period", "brief-revision"]:
        bp = sub.add_parser(name)
        bp.add_argument("persona_id")
        if name in ("brief-digest", "brief-period"):
            bp.add_argument("scope")
        bp.add_argument("--date")

    # record/put (read authored JSON from file → persist)
    p = sub.add_parser("put-day-plan")
    p.add_argument("persona_id"); p.add_argument("date"); p.add_argument("file")
    p = sub.add_parser("record-day")
    p.add_argument("persona_id"); p.add_argument("date")
    p.add_argument("file", help="JSON: {day_plan, plan, activities, deltas?, workday_start_hour?, seed?}")
    p = sub.add_parser("put-period-plan")
    p.add_argument("persona_id"); p.add_argument("scope"); p.add_argument("date"); p.add_argument("file")
    p = sub.add_parser("record-deltas")
    p.add_argument("persona_id"); p.add_argument("date"); p.add_argument("file")
    p = sub.add_parser("put-digest")
    p.add_argument("persona_id"); p.add_argument("scope"); p.add_argument("date"); p.add_argument("file")
    p = sub.add_parser("record-revision")
    p.add_argument("persona_id"); p.add_argument("file")

    # F2 critic / F3 driver / F5 evidence
    p = sub.add_parser("brief-critic")
    p.add_argument("persona_id"); p.add_argument("--start"); p.add_argument("--end"); p.add_argument("--k", type=int, default=None)
    p = sub.add_parser("record-critic")
    p.add_argument("persona_id"); p.add_argument("file"); p.add_argument("--start"); p.add_argument("--end")
    p = sub.add_parser("evaluate-full")
    p.add_argument("persona_id"); p.add_argument("--start"); p.add_argument("--end")
    # Cohort quality: diversity gate + cross-persona critic
    p = sub.add_parser("cohort-diversity")
    p.add_argument("--persona", action="append", dest="personas", help="restrict to these persona ids/slugs (repeatable)")
    p = sub.add_parser("brief-cohort-critic")
    p.add_argument("--persona", action="append", dest="personas"); p.add_argument("--start"); p.add_argument("--end")
    p = sub.add_parser("record-cohort-critic")
    p.add_argument("file")
    p = sub.add_parser("brief-month")
    p.add_argument("persona_id"); p.add_argument("month")
    p = sub.add_parser("record-month")
    p.add_argument("persona_id"); p.add_argument("month"); p.add_argument("file")
    p = sub.add_parser("brief-evidence")
    p.add_argument("persona_id")
    p = sub.add_parser("record-evidence")
    p.add_argument("persona_id"); p.add_argument("file")
    # Portable data: snapshot export/import + shipped example projects (split module).
    _cli_data.add_data_parsers(sub)
    _cli_feedback.add_feedback_parsers(sub)   # `sonaloop feedback` (split module)
    p = sub.add_parser("brief-synthesis")
    p.add_argument("council_ids", nargs="+")
    p.add_argument("--title"); p.add_argument("--start"); p.add_argument("--goal")
    p = sub.add_parser("record-synthesis")
    p.add_argument("title"); p.add_argument("file")
    p.add_argument("--start", default=""); p.add_argument("--council", action="append", dest="councils", required=True)
    p.add_argument("--goal", default=""); p.add_argument("--id", dest="synthesis_id")
    p = sub.add_parser("record-council")
    p.add_argument("file", help="JSON: {prompt, persona_ids, turns, votes?, proposal?, summary?, exec_summary?, selection_reason?}")
    p = sub.add_parser("councils")
    p = sub.add_parser("council")
    p.add_argument("session_id"); p.add_argument("--format", choices=["json", "md"], default="json"); p.add_argument("--out")
    p = sub.add_parser("syntheses")
    p = sub.add_parser("synthesis")
    p.add_argument("synthesis_id"); p.add_argument("--format", choices=["md", "json", "pptx", "pdf", "html"], default="md"); p.add_argument("--out")
    # Research graph (Project container + edges + tags) + Report
    p = sub.add_parser("research-create")
    p.add_argument("title"); p.add_argument("--goal", default=""); p.add_argument("--persona", action="append", dest="personas")
    p.add_argument("--icon", default=None, help="Existing icon name, or 'random' (default).")
    p = sub.add_parser("project-icons")
    p = sub.add_parser("project-icon-set")
    p.add_argument("project_id"); p.add_argument("--icon"); p.add_argument("--svg"); p.add_argument("--random", action="store_true", dest="randomize")
    p = sub.add_parser("project-icon-generate")
    p.add_argument("project_id"); p.add_argument("--prompt", default="")
    p = sub.add_parser("research-list")
    p = sub.add_parser("research-graph"); p.add_argument("project_id")
    p = sub.add_parser("research-frontier"); p.add_argument("project_id")
    # Sections (methodology-independent overlay groupings of graph nodes)
    p = sub.add_parser("section-list"); p.add_argument("project_id")
    p = sub.add_parser("section-get"); p.add_argument("section_id")
    p = sub.add_parser("section-create")
    p.add_argument("project_id"); p.add_argument("title"); p.add_argument("--kind", default="theme")
    p.add_argument("--member", action="append", dest="members"); p.add_argument("--parent"); p.add_argument("--note", default="")
    p = sub.add_parser("section-update"); p.add_argument("section_id"); p.add_argument("file")  # JSON patch
    p = sub.add_parser("section-add"); p.add_argument("section_id"); p.add_argument("--node", action="append", dest="nodes", required=True)
    p = sub.add_parser("section-remove"); p.add_argument("section_id"); p.add_argument("--node", action="append", dest="nodes", required=True)
    p = sub.add_parser("section-set"); p.add_argument("section_id"); p.add_argument("--node", action="append", dest="nodes", default=[])
    p = sub.add_parser("section-reorder"); p.add_argument("project_id"); p.add_argument("--id", action="append", dest="ids", required=True)
    p = sub.add_parser("section-delete"); p.add_argument("section_id")
    p = sub.add_parser("section-kinds")
    p = sub.add_parser("section-members"); p.add_argument("section_id")
    p = sub.add_parser("section-export"); p.add_argument("section_id"); p.add_argument("--format", choices=["md", "json"], default="md"); p.add_argument("--out")
    p = sub.add_parser("note-create"); p.add_argument("project_id"); p.add_argument("text"); p.add_argument("--title", default="")
    p = sub.add_parser("note-list"); p.add_argument("project_id")
    p = sub.add_parser("note-delete"); p.add_argument("project_id"); p.add_argument("note_id")
    p = sub.add_parser("report-brief"); p.add_argument("project_id")
    p = sub.add_parser("report-outline"); p.add_argument("project_id"); p.add_argument("file")
    p = sub.add_parser("report-section-brief"); p.add_argument("project_id"); p.add_argument("section_id"); p.add_argument("--report")
    p = sub.add_parser("report-section"); p.add_argument("project_id"); p.add_argument("section_id"); p.add_argument("file"); p.add_argument("--report")
    p = sub.add_parser("report-export")
    p.add_argument("project_id"); p.add_argument("--format", choices=["md", "json"], default="md"); p.add_argument("--out"); p.add_argument("--report")
    p = sub.add_parser("template-deck", help="Render the PPTX master template (every layout, placeholder content) — the demo deck."); p.add_argument("--out", default="master-template.pptx")
    # Methodology engine (data-driven, structure+LLM-judged)
    p = sub.add_parser("methodology-list")
    p = sub.add_parser("methodology-get"); p.add_argument("key")
    p = sub.add_parser("methodology-start")
    p.add_argument("title"); p.add_argument("--goal", default=""); p.add_argument("--methodology", required=True)
    p.add_argument("--persona", action="append", dest="personas"); p.add_argument("--description", default="")
    p.add_argument("--icon", default=None, help="Existing icon name, or 'random' (default).")
    p = sub.add_parser("methodology-suggest")
    p.add_argument("kind", nargs="?", default="capabilities",
                   choices=["capabilities", "roles", "artifact-types", "methodologies"])
    # plan router (the single engine); gate-judgment on a verify task
    p = sub.add_parser("next-brief"); p.add_argument("project_id")
    p = sub.add_parser("step-judge")
    p.add_argument("project_id"); p.add_argument("step_id"); p.add_argument("gate_tag")
    p.add_argument("--decided", default="true"); p.add_argument("--rationale", default=""); p.add_argument("--ref", action="append", dest="refs")
    # Research-plan engine (plan-driven analyze/act/verify)
    p = sub.add_parser("project-start")
    p.add_argument("title"); p.add_argument("--goal", default=""); p.add_argument("--methodology")
    p.add_argument("--persona", action="append", dest="personas"); p.add_argument("--description", default="")
    p.add_argument("--icon", default=None, help="Existing icon name, or 'random' (default).")
    # Governed run loop (ESV) — CLI parity with the MCP tools, so a CLI-driven host can follow
    # the front door (AGENTS.md) instead of freestyling plan-next until it "feels answered".
    p = sub.add_parser("run-start")
    p.add_argument("project_id"); p.add_argument("--budget", type=int); p.add_argument("--run-id", dest="run_id")
    p = sub.add_parser("run-step"); p.add_argument("run_id")
    p = sub.add_parser("run-checkpoint")
    p.add_argument("run_id"); p.add_argument("file")  # file = {task_id, bucket, key, evidence, summary}
    p = sub.add_parser("run-critic-round")
    p.add_argument("run_id"); p.add_argument("--passed", default="false"); p.add_argument("--missing", type=int, default=0)
    p = sub.add_parser("run-finish"); p.add_argument("run_id"); p.add_argument("--status", default="finished")
    p = sub.add_parser("run-journal"); p.add_argument("run_id")
    p = sub.add_parser("plan-get"); p.add_argument("project_id")
    p = sub.add_parser("plan-md"); p.add_argument("project_id")
    p = sub.add_parser("plan-brief"); p.add_argument("project_id")
    p = sub.add_parser("plan-task-add")
    p.add_argument("project_id"); p.add_argument("bucket"); p.add_argument("capability"); p.add_argument("title")
    p.add_argument("--intent", default=""); p.add_argument("--consume", action="append", dest="consumes")
    p.add_argument("--step", default=""); p.add_argument("--note", default="")
    p = sub.add_parser("plan-frame")
    p.add_argument("project_id"); p.add_argument("task_id"); p.add_argument("file")  # file = {questions,hypotheses,memory_refs}
    p = sub.add_parser("plan-link")
    p.add_argument("project_id"); p.add_argument("task_id"); p.add_argument("kind"); p.add_argument("evidence_id")
    p = sub.add_parser("plan-judge")
    p.add_argument("project_id"); p.add_argument("task_id"); p.add_argument("gate_tag")
    p.add_argument("--decided", default="true"); p.add_argument("--rationale", default=""); p.add_argument("--ref", action="append", dest="refs")
    p = sub.add_parser("plan-complete"); p.add_argument("project_id"); p.add_argument("task_id")
    p = sub.add_parser("plan-progress")
    p.add_argument("project_id"); p.add_argument("task_id"); p.add_argument("--rationale", default=""); p.add_argument("--delta", default=""); p.add_argument("--ref", action="append", dest="refs")
    p = sub.add_parser("plan-assess"); p.add_argument("project_id")
    p = sub.add_parser("plan-next"); p.add_argument("project_id")
    # Prototypes + Playwright harness
    p = sub.add_parser("prototype-scaffold")
    p.add_argument("slug"); p.add_argument("name"); p.add_argument("file"); p.add_argument("--project")
    p.add_argument("--template", default=None); p.add_argument("--fidelity")
    p = sub.add_parser("prototype-register")
    p.add_argument("slug"); p.add_argument("name"); p.add_argument("path"); p.add_argument("--entry", default="index.html")
    p.add_argument("--run", default="static"); p.add_argument("--run-cmd", dest="run_cmd"); p.add_argument("--version", default="v0.1")
    p.add_argument("--project"); p.add_argument("--notes", default="")
    p = sub.add_parser("prototype-list"); p.add_argument("--project")
    p = sub.add_parser("prototype-get"); p.add_argument("prototype_id")
    p = sub.add_parser("prototype-run"); p.add_argument("prototype_id")
    p = sub.add_parser("prototype-stop"); p.add_argument("prototype_id")
    p = sub.add_parser("prototype-delete"); p.add_argument("prototype_id")
    p = sub.add_parser("proto-open"); p.add_argument("--prototype"); p.add_argument("--url"); p.add_argument("--persona")
    p = sub.add_parser("proto-drive")  # one-process proband session: open → actions → read → close (+record)
    p.add_argument("script")  # JSON file: [{type,ref,…},…] or {"actions":[…]}
    p.add_argument("--prototype"); p.add_argument("--url"); p.add_argument("--persona")
    p.add_argument("--record")  # reaction JSON file → record_prototype_session in-process (grounded)
    p.add_argument("--date", default="")
    p = sub.add_parser("proto-act"); p.add_argument("session_id"); p.add_argument("action")
    p = sub.add_parser("proto-read"); p.add_argument("session_id")
    p = sub.add_parser("proto-close"); p.add_argument("session_id")
    p = sub.add_parser("proto-sessions")
    p = sub.add_parser("session-brief"); p.add_argument("persona_id"); p.add_argument("prototype_id")
    p = sub.add_parser("session-record")
    p.add_argument("persona_id"); p.add_argument("prototype_id"); p.add_argument("session_id"); p.add_argument("date"); p.add_argument("file")
    # Usability sessions (the durable, replayable trace)
    p = sub.add_parser("session-list")
    p.add_argument("--project"); p.add_argument("--persona"); p.add_argument("--subject")
    p = sub.add_parser("session-get"); p.add_argument("session_id")
    # Deletes (CRUD: delete via CLI/MCP only)
    p = sub.add_parser("research-delete"); p.add_argument("project_id")
    p = sub.add_parser("synthesis-delete"); p.add_argument("synthesis_id")
    p = sub.add_parser("council-delete"); p.add_argument("session_id")
    p = sub.add_parser("persona-delete"); p.add_argument("persona_id")
    return parser


def main(argv: list[str] | None = None) -> int:
    load_env()
    args = build_parser().parse_args(argv)
    try:
        if args.command == "setup":
            import subprocess
            print("Installing the chromium browser for prototype screenshots + PDF export…")
            rc = subprocess.call([sys.executable, "-m", "playwright", "install", "chromium"])
            if rc == 0:
                print("Done. Prototype screenshots and report PDF export are now available.")
            else:
                print("playwright install failed; you can retry with:\n  python -m playwright install chromium",
                      file=sys.stderr)
            return rc
        elif args.command == "guide":
            from .mcp_server._prompts import getting_started
            _print(getting_started(), as_json=False)
            return 0
        elif args.command == "info":
            from ._diagnostics import info_payload, register_hint_text
            payload = info_payload(_pkg_version())
            _print(payload)                                   # stdout stays pure JSON
            hint = register_hint_text(payload["mcp"])
            if hint:
                print(hint, file=sys.stderr)                  # the exact per-host one-liners
            return 0
        elif args.command == "persona-create":
            _print(services.create_persona(args.description, args.segment, args.evidence, args.avatar))
        elif args.command == "brief-persona":
            _print(services.brief_persona(args.description, args.segment, args.evidence))
        elif args.command == "record-persona":
            _print(services.record_persona(**json.loads(Path(args.file).read_text(encoding="utf-8"))))
        elif args.command == "persona-bulk":
            _print(services.bulk_create_personas(_read_descriptions(args.file), args.segment, args.avatar))
        elif args.command == "persona-list":
            _print(services.list_personas({"q": args.filter} if args.filter else None,
                                          compact=not args.full))
        elif args.command == "persona-get":
            _print(services.get_persona(args.persona_id))
        elif args.command == "persona-soul":
            soul = services.get_persona_soul(args.persona_id)
            _print(soul["path"] if args.path_only else soul["content"], as_json=False)
        elif args.command == "persona-context":
            ctx = services.prepare_persona_agent_context(args.persona_id, args.task, args.recent_events)
            _print(ctx["agent_context"] if args.text else ctx, as_json=not args.text)
        elif args.command == "persona-update":
            _print(services.update_persona(args.persona_id, json.loads(args.patch_json), args.reason))
        elif args.command == "persona-refresh":
            _print(services.refresh_persona_from_source(args.persona_id, force=args.force))
        elif args.command in _cli_catalog.COMMANDS:
            _print(_cli_catalog.run_catalog_command(args))
        elif args.command == "avatar-generate":
            _print(generate_persona_avatar(args.persona_id, args.style))
        elif args.command == "simulate-clear":
            _print(services.clear_simulations())
        elif args.command == "purge-runtime-data":
            _print(services.purge_runtime_data(remove_files=not args.keep_files))
        elif args.command == "state":
            _print(services.get_current_state(args.persona_id))
        elif args.command == "calendar":
            if args.view == "day":
                _print(services.get_calendar(args.persona_id, args.date))
            else:
                _print(services.get_calendar_period(args.persona_id, args.date, args.view))
        elif args.command == "activity":
            _print(services.get_activity(args.activity_id))
        elif args.command == "summary":
            _print(services.summarize_persona_period(args.persona_id, args.start, args.end))
        elif args.command == "pain-points":
            _print(services.extract_pain_points(args.persona_id, args.start, args.end))
        elif args.command == "council-run":
            _print(services.run_council(args.prompt, args.personas, rounds=args.rounds))
        elif args.command == "brief-council":
            _print(services.brief_council(args.project_id, args.prompt, args.personas, count=args.count, context=args.context))
        elif args.command == "brief-ask":
            _print(services.brief_ask(args.persona_id, args.question, args.context))
        elif args.command == "ask":
            _print(services.ask_persona(args.persona_id, args.question))
        elif args.command == "compare":
            _print(services.compare_personas(args.prompt, args.personas))
        elif args.command == "taxonomy-lint":
            from . import job_taxonomy
            problems = job_taxonomy.lint_taxonomy()
            _print({"ok": not problems, "problems": problems})
            if problems:
                sys.exit(1)
        elif args.command == "primitive-list":
            _print(services.list_primitives())
        elif args.command == "form-list":
            _print(services.list_forms(args.primitive))
        elif args.command == "form-get":
            _print(services.get_form(args.primitive, args.form_id))
        elif args.command == "forms-suggest":
            _print(services.suggest_forms(args.primitive))
        elif args.command == "result-schema-list":
            _print(services.list_result_schemas())
        elif args.command == "result-schema-get":
            _print(services.get_result_schema(args.schema_id))
        elif args.command == "result-contract-list":
            _print(services.list_result_contracts())
        elif args.command == "result-contract-job":
            _print(services.result_contract_for_job(args.job_id))
        elif args.command == "result-contract-methodology":
            _print(services.result_contract_for_methodology(args.methodology_key))
        elif args.command in _cli_hooks.COMMANDS:
            _print(_cli_hooks.run_hook_command(args))
        elif args.command in _cli_substrate.COMMANDS:
            _print(_cli_substrate.run_substrate_command(args))
        elif args.command == "export-persona":
            content = services.export_persona(args.persona_id, args.format)
            _print({"path": services.write_export(content, args.out)} if args.out else content, as_json=bool(args.out))
        elif args.command == "export-logs":
            content = services.export_logs(args.persona_id, args.start, args.end, args.format)
            _print({"path": services.write_export(content, args.out)} if args.out else content, as_json=bool(args.out))
        elif args.command == "logs":
            content = services.export_logs(args.persona_id, args.start, args.end, args.format)
            _print({"path": services.write_export(content, args.out)} if args.out else content, as_json=bool(args.out))
        elif args.command == "export-council":
            content = services.export_council_session(args.session_id, args.format)
            _print({"path": services.write_export(content, args.out)} if args.out else content, as_json=bool(args.out))
        elif args.command == "recall":
            _print(services.recall_memory(args.persona_id, args.query, args.as_of, args.k))
        elif args.command == "projects":
            _print(services.list_active_projects(args.persona_id))
        elif args.command == "project":
            _print(services.get_project(args.persona_id, args.entity_id, args.as_of))
        elif args.command == "state-at":
            _print(services.get_state_at(args.persona_id, args.as_of))
        elif args.command == "timeline":
            _print(services.get_timeline(args.persona_id, args.start, args.end, args.entity))
        elif args.command == "entities":
            _print(services.search_entities(args.persona_id, args.kind, args.name))
        elif args.command == "loops":
            _print(services.get_open_loops(args.persona_id, args.status))
        elif args.command == "memory":
            _print(services.get_persona_memory(args.persona_id)["content"], as_json=False)
        elif args.command == "digests":
            _print(services.list_digests(args.persona_id, args.scope))
        elif args.command == "plans":
            _print(services.list_period_plans(args.persona_id, args.scope))
        elif args.command == "evaluate":
            _print(services.evaluate_simulation(args.persona, args.start, args.end))
        elif args.command == "anomalies":
            _print(services.list_memory_anomalies(args.persona))
        elif args.command == "backfill-embeddings":
            _print(services.backfill_embeddings(args.persona))
        elif args.command == "prune-memory":
            _print(services.prune_memory(args.persona_id, args.keep_days, args.as_of))
        elif args.command == "world-get":
            _print(services.get_world_context(args.as_of))
        elif args.command == "world-set":
            _print(services.set_world_context(json.loads(Path(args.file).read_text(encoding="utf-8"))))
        elif args.command == "language":
            from .config import content_language, ui_language
            _print({"content_language": content_language(), "ui_language": ui_language()})
        elif args.command == "set-language":
            from . import config as _cfg
            if args.content:
                _cfg.set_content_language(args.content, also_ui=args.ui is None)
            if args.ui:
                _cfg.set_ui_language(args.ui)
            _print({"content_language": _cfg.content_language(), "ui_language": _cfg.ui_language()})
        elif args.command == "brief-day":
            _print(services.brief_day(args.persona_id, args.date))
        elif args.command == "brief-consolidation":
            _print(services.brief_consolidation(args.persona_id, args.date))
        elif args.command == "brief-digest":
            _print(services.brief_digest(args.persona_id, args.scope, args.date))
        elif args.command == "brief-period":
            _print(services.brief_period(args.persona_id, args.scope, args.date))
        elif args.command == "brief-revision":
            _print(services.brief_persona_revision(args.persona_id, args.date))
        elif args.command == "put-day-plan":
            _print(services.put_day_plan(args.persona_id, args.date, json.loads(Path(args.file).read_text(encoding="utf-8"))))
        elif args.command == "record-day":
            _print(services.record_day(args.persona_id, args.date, **json.loads(Path(args.file).read_text(encoding="utf-8"))))
        elif args.command == "put-period-plan":
            _print(services.put_period_plan(args.persona_id, args.scope, args.date, json.loads(Path(args.file).read_text(encoding="utf-8"))))
        elif args.command == "record-deltas":
            _print(services.record_memory_deltas(args.persona_id, args.date, json.loads(Path(args.file).read_text(encoding="utf-8"))))
        elif args.command == "put-digest":
            _print(services.put_digest(args.persona_id, args.scope, args.date, json.loads(Path(args.file).read_text(encoding="utf-8"))))
        elif args.command == "record-revision":
            _print(services.record_persona_revision(args.persona_id, json.loads(Path(args.file).read_text(encoding="utf-8"))))
        elif args.command == "brief-critic":
            _print(services.brief_eval_critic(args.persona_id, args.start, args.end, args.k))
        elif args.command == "record-critic":
            _print(services.record_eval_critic(args.persona_id, json.loads(Path(args.file).read_text(encoding="utf-8")), args.start, args.end))
        elif args.command == "evaluate-full":
            _print(services.evaluate_simulation_full(args.persona_id, args.start, args.end))
        elif args.command == "cohort-diversity":
            _print(services.evaluate_cohort_diversity(args.personas))
        elif args.command == "brief-cohort-critic":
            _print(services.brief_cohort_critic(args.personas, args.start, args.end))
        elif args.command == "record-cohort-critic":
            _print(services.record_cohort_critic(json.loads(Path(args.file).read_text(encoding="utf-8"))))
        elif args.command == "brief-month":
            _print(services.brief_month(args.persona_id, args.month))
        elif args.command == "record-month":
            _print(services.record_month_bundle(args.persona_id, args.month, json.loads(Path(args.file).read_text(encoding="utf-8"))))
        elif args.command == "brief-evidence":
            _print(services.brief_evidence_check(args.persona_id))
        elif args.command == "record-evidence":
            _print(services.record_evidence_check(args.persona_id, json.loads(Path(args.file).read_text(encoding="utf-8"))))
        elif args.command in _cli_data.COMMANDS:
            _print(_cli_data.run_data_command(args))
        elif args.command in _cli_feedback.COMMANDS:
            _print(_cli_feedback.run_feedback_command(args))
        elif args.command == "brief-synthesis":
            _print(services.brief_synthesis(args.council_ids, args.title, args.start, args.goal))
        elif args.command == "record-synthesis":
            _print(services.record_synthesis(args.title, args.start, args.councils, json.loads(Path(args.file).read_text(encoding="utf-8")), args.goal, args.synthesis_id))
        elif args.command == "record-council":
            _print(services.record_council(**json.loads(Path(args.file).read_text(encoding="utf-8"))))
        elif args.command == "councils":
            _print(services.list_councils())
        elif args.command == "council":
            content = services.export_council_session(args.session_id, args.format) if args.format == "md" else services.get_council(args.session_id)
            _print({"path": services.write_export(content, args.out)} if args.out and args.format == "md" else content, as_json=not (args.out and args.format=="md"))
        elif args.command == "syntheses":
            _print(services.list_syntheses())
        elif args.command == "synthesis":
            if args.format == "html":   # shareable read-only bundle: data/export/share/<token>/index.html
                _print(services.export_synthesis_html(args.synthesis_id, args.out))
            elif args.format in ("pptx", "pdf"):
                # one deliverable seam: data/exports/ for relative paths + a direction:out
                # asset on the owning project (ticket project-assets-direction-…-section)
                _print(services.export_synthesis_deliverable(args.synthesis_id, args.format, args.out))
            else:
                content = services.export_synthesis(args.synthesis_id, args.format)
                _print({"path": services.write_export(content, args.out)} if args.out else content, as_json=bool(args.out) or args.format == "json")
        elif args.command == "research-create":
            _print(services.create_research_project(args.title, args.goal, args.personas,
                                                    icon=args.icon))
        elif args.command == "project-icons":
            _print(services.available_project_icons())
        elif args.command == "project-icon-set":
            _print(services.set_project_icon(args.project_id, args.icon, svg=args.svg,
                                             randomize=args.randomize))
        elif args.command == "project-icon-generate":
            _print(services.generate_project_icon(args.project_id, args.prompt))
        elif args.command == "research-list":
            _print(services.list_research_projects())
        elif args.command == "research-graph":
            _print(services.get_project_graph(args.project_id))
        elif args.command == "research-frontier":
            _print(services.get_research_frontier(args.project_id))
        elif args.command == "section-list":
            _print(services.list_sections(args.project_id))
        elif args.command == "section-get":
            _print(services.get_section(args.section_id))
        elif args.command == "section-create":
            _print(services.create_section(args.project_id, args.title, args.kind,
                                           args.members or [], args.parent, note=args.note))
        elif args.command == "section-update":
            _print(services.update_section(args.section_id, json.loads(Path(args.file).read_text(encoding="utf-8"))))
        elif args.command == "section-add":
            _print(services.add_to_section(args.section_id, args.nodes))
        elif args.command == "section-remove":
            _print(services.remove_from_section(args.section_id, args.nodes))
        elif args.command == "section-set":
            _print(services.set_section_members(args.section_id, args.nodes))
        elif args.command == "section-reorder":
            _print(services.reorder_sections(args.project_id, args.ids))
        elif args.command == "section-delete":
            _print(services.delete_section(args.section_id))
        elif args.command == "section-kinds":
            _print(services.suggest_section_kinds())
        elif args.command == "section-members":
            _print(services.section_members(args.section_id))
        elif args.command == "section-export":
            content = services.export_section(args.section_id, args.format)
            _print({"path": services.write_export(content, args.out)} if args.out else content,
                   as_json=bool(args.out) or args.format == "json")
        elif args.command == "note-create":
            _print(services.create_note(args.project_id, args.text, args.title))
        elif args.command == "note-list":
            _print(services.list_notes(args.project_id))
        elif args.command == "note-delete":
            _print(services.delete_note(args.project_id, args.note_id))
        elif args.command == "report-brief":
            _print(services.brief_synthesis_outline(args.project_id))
        elif args.command == "report-outline":
            _print(services.record_synthesis_outline(args.project_id, json.loads(Path(args.file).read_text(encoding="utf-8"))))
        elif args.command == "report-section-brief":
            _print(services.brief_synthesis_section(args.project_id, args.section_id, args.report))
        elif args.command == "report-section":
            _print(services.record_synthesis_section(args.project_id, args.section_id, json.loads(Path(args.file).read_text(encoding="utf-8")), args.report))
        elif args.command == "report-export":
            content = services.export_report(args.project_id, args.report, args.format)
            _print({"path": services.write_export(content, args.out)} if args.out else content, as_json=bool(args.out) or args.format == "json")
        elif args.command == "template-deck":
            _print(services.export_template_deck(args.out), as_json=True)
        elif args.command == "methodology-list":
            _print(services.list_methodologies())
        elif args.command == "methodology-get":
            _print(services.get_methodology(args.key))
        elif args.command == "methodology-start":
            _print(services.start_project(args.title, args.goal, args.methodology, args.personas,
                                          args.description, icon=args.icon))
        elif args.command == "methodology-suggest":
            fn = {"capabilities": services.suggest_capabilities, "roles": services.suggest_roles,
                  "artifact-types": services.suggest_artifact_types,
                  "methodologies": services.suggest_methodologies}[args.kind]
            _print(fn())
        elif args.command == "next-brief":
            _print(services.brief_next(args.project_id))
        elif args.command == "step-judge":
            _print(services.record_judgment(args.project_id, args.step_id, args.gate_tag,
                                            args.decided.lower() == "true", args.rationale, args.refs))
        elif args.command == "project-start":
            _print(services.start_project(args.title, args.goal, args.methodology, args.personas,
                                          args.description, icon=args.icon))
        elif args.command == "run-start":
            _print(services.start_run(args.project_id, args.budget, args.run_id))
        elif args.command == "run-step":
            _print(services.run_step(args.run_id))
        elif args.command == "run-checkpoint":
            _print(services.checkpoint_step(args.run_id, json.loads(Path(args.file).read_text(encoding="utf-8"))))
        elif args.command == "run-critic-round":
            _print(services.record_critic_round(args.run_id, args.passed.lower() == "true", args.missing))
        elif args.command == "run-finish":
            _print(services.finish_run(args.run_id, args.status))
        elif args.command == "run-journal":
            _print(services.run_journal(args.run_id))
        elif args.command == "plan-get":
            _print(services.get_plan(args.project_id))
        elif args.command == "plan-md":
            print(services.export_plan_md(args.project_id))
        elif args.command == "plan-brief":
            _print(services.brief_next(args.project_id))
        elif args.command == "plan-task-add":
            _print(services.add_task(args.project_id, args.bucket, args.capability, args.title,
                                     intent=args.intent, consumes=args.consumes, step=args.step, plan_note=args.note))
        elif args.command == "plan-frame":
            d = json.loads(Path(args.file).read_text(encoding="utf-8"))
            _print(services.record_frame(args.project_id, args.task_id, d.get("questions", []),
                                         d.get("hypotheses"), d.get("memory_refs")))
        elif args.command == "plan-link":
            _print(services.link_evidence(args.project_id, args.task_id, {"kind": args.kind, "id": args.evidence_id}))
        elif args.command == "plan-judge":
            _print(services.record_judgment(args.project_id, args.task_id, args.gate_tag,
                                            args.decided.lower() == "true", args.rationale, args.refs))
        elif args.command == "plan-complete":
            _print(services.complete_task(args.project_id, args.task_id))
        elif args.command == "plan-progress":
            _print(services.assess_progress(args.project_id, args.task_id, args.rationale, args.refs or [], args.delta))
        elif args.command == "plan-assess":
            _print(services.assess_project(args.project_id))
        elif args.command == "plan-next":
            _print(services.next_action(args.project_id))
        elif args.command == "prototype-scaffold":
            _print(services.scaffold_prototype(args.slug, args.name, json.loads(Path(args.file).read_text(encoding="utf-8")),
                                               template=args.template, project_id=args.project, fidelity=args.fidelity))
        elif args.command == "prototype-register":
            _print(services.register_prototype(args.slug, args.name, args.path, args.entry, args.run, args.run_cmd, args.version, args.project, args.notes))
        elif args.command == "prototype-list":
            _print(services.list_prototypes_artifacts(args.project))
        elif args.command == "prototype-get":
            _print(services.get_prototype_artifact(args.prototype_id))
        elif args.command == "prototype-run":
            _print(services.run_prototype(args.prototype_id))
        elif args.command == "prototype-stop":
            _print(services.stop_prototype(args.prototype_id))
        elif args.command == "prototype-delete":
            _print(services.delete_prototype_artifact(args.prototype_id))
        elif args.command == "proto-open":
            _print(services.proto_open(args.prototype, args.url, args.persona))
        elif args.command == "proto-drive":
            script = json.loads(Path(args.script).read_text(encoding="utf-8"))
            actions = script.get("actions") if isinstance(script, dict) else script
            reaction = json.loads(Path(args.record).read_text(encoding="utf-8")) if args.record else None
            _print(services.proto_drive(args.prototype, args.url, args.persona, actions,
                                        reaction=reaction, date_value=args.date or None))
        elif args.command == "proto-act":
            _print(services.proto_act(args.session_id, json.loads(args.action)))
        elif args.command == "proto-read":
            _print(services.proto_read(args.session_id))
        elif args.command == "proto-close":
            _print(services.proto_close(args.session_id))
        elif args.command == "proto-sessions":
            _print(services.list_proto_sessions())
        elif args.command == "session-brief":
            _print(services.brief_prototype_session(args.persona_id, args.prototype_id))
        elif args.command == "session-record":
            _print(services.record_prototype_session(args.persona_id, args.prototype_id, args.session_id, args.date, json.loads(Path(args.file).read_text(encoding="utf-8"))))
        elif args.command == "session-list":
            _print(services.list_usability_sessions(args.project, args.persona, args.subject))
        elif args.command == "session-get":
            _print(services.get_usability_session(args.session_id))
        elif args.command == "research-delete":
            _print(services.delete_research_project(args.project_id))
        elif args.command == "synthesis-delete":
            _print(services.delete_synthesis(args.synthesis_id))
        elif args.command == "council-delete":
            _print(services.delete_council(args.session_id))
        elif args.command == "persona-delete":
            _print(services.delete_persona(args.persona_id))
        return 0
    except Exception as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
