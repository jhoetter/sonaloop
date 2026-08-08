from __future__ import annotations

import time
from typing import Any

from .. import services
from ._env import _env


def register_prototypes(mcp):
    # ================= Prototypes (real, minimal, locally-runnable apps) =================
    # NAMING CONVENTION (M4): two deliberate families —
    #   prototype_* / *_prototype  = the ARTIFACT lifecycle: scaffold_prototype, run_prototype,
    #                                stop_prototype, get_prototype, list_prototypes, delete_prototype.
    #   proto_*                     = the LIVE proband SESSION on a running app, in order:
    #                                proto_open → proto_act → proto_read → proto_close
    #                                (then record_prototype_session to persist the grounded result).
    @mcp.tool()
    def scaffold_prototype(slug: str, name: str, concept: dict[str, Any], kind: str = "web",
                           template: str | None = None, project_id: str | None = None,
                           fidelity: str | None = None) -> dict[str, Any]:
        """Generate a real, minimal, runnable web app from a host-authored concept and register it.
        The app is genuinely clickable (real DOM) for Playwright. The renderer template is resolved
        from DATA (suggestions/artifact_types.json): legacy kind="web" creates a normal prototype;
        pass a DATA artifact type as `kind` (canvas, flow, dashboard, cards, comparison, model,
        journey, ...) to avoid forcing every prototype into forms/clickflows. `kind="canvas"` uses
        frames/surface + positioned layers for spatial maps, service-control rooms, boards,
        simulations and other freeform experiences. `template` forces a specific template;
        concept-level `fidelity` themes any template. The scaffolded HTML is tokenized with the active design system (Cloud workspace
        design system when present, otherwise the Sonaloop default): colors, font stacks, radius,
        chart/status colors and optional logo/brand header all come from that contract. Use
        concept.show_brand=true only when a visible logo/wordmark belongs in the tested surface.
        Classic concept = {title, summary, start, screens:[{id,title,elements,...rich blocks}]}.
        Canvas concept = {title, summary, start, frames:[{id,title,layout,layers:[...],actions:[...]}]}
        or {surface:{...}}."""
        t = time.perf_counter()
        return _env("scaffold_prototype",
                    services.scaffold_prototype(slug, name, concept, kind, template, project_id, fidelity), t)

    @mcp.tool()
    def register_prototype(slug: str, name: str, path: str, entry: str = "index.html", run: str = "static",
                           run_cmd: str | None = None, version: str = "v0.1", project_id: str | None = None,
                           notes: str = "", fidelity: str = "midfi") -> dict[str, Any]:
        """Register a hand-authored app under prototypes/ as a runnable artifact (fidelity tag, e.g. lofi|midfi|hifi)."""
        t = time.perf_counter()
        return _env("register_prototype",
                    services.register_prototype(slug, name, path, entry, run, run_cmd, version, project_id, notes, fidelity), t)

    @mcp.tool()
    def list_prototypes(project_id: str | None = None) -> dict[str, Any]:
        """List registered prototype artifacts (optionally for one project)."""
        t = time.perf_counter()
        return _env("list_prototypes", services.list_prototypes_artifacts(project_id), t)

    @mcp.tool()
    def get_prototype(prototype_id: str) -> dict[str, Any]:
        """One prototype artifact by id or slug."""
        t = time.perf_counter()
        return _env("get_prototype", services.get_prototype_artifact(prototype_id), t)

    @mcp.tool()
    def run_prototype(prototype_id: str) -> dict[str, Any]:
        """Start the app on an ephemeral localhost port; returns {url, pid}. Local-only."""
        t = time.perf_counter()
        return _env("run_prototype", services.run_prototype(prototype_id), t)

    @mcp.tool()
    def stop_prototype(prototype_id: str) -> dict[str, Any]:
        """Stop a running prototype."""
        t = time.perf_counter()
        return _env("stop_prototype", services.stop_prototype(prototype_id), t)

    @mcp.tool()
    def delete_prototype(prototype_id: str) -> dict[str, Any]:
        """Delete a prototype artifact record (files on disk are kept)."""
        t = time.perf_counter()
        return _env("delete_prototype", services.delete_prototype_artifact(prototype_id), t)

    # ================= Playwright harness — agents drive the real app =================
    @mcp.tool()
    def proto_open(prototype_id: str | None = None, url: str | None = None,
                   persona_id: str | None = None) -> dict[str, Any]:
        """Open a real running app in a headless browser session; returns {session_id, snapshot}.
        Without the optional browser harness this degrades gracefully (in-band fallback, no error)."""
        t = time.perf_counter()
        from .. import browser as _browser
        fallback = {
            "session_id": None, "unavailable": True,
            "note": "browser harness disabled — run `sonaloop setup` to fetch the headless "
                    "chromium (optional). Every core flow works without it: use the artifact "
                    "rung instead (define_flow + brief_flow_walkthrough need no browser).",
        }
        if not _browser.available():
            # Cold start without the optional browser is normal — answer in-band, never raise.
            return _env("proto_open", fallback, t)
        try:
            return _env("proto_open", services.proto_open(prototype_id, url, persona_id), t)
        except _browser.HarnessError as he:
            if he.code == "PLAYWRIGHT_UNAVAILABLE":   # package present, chromium binary not fetched
                return _env("proto_open", fallback, t)
            raise

    @mcp.tool()
    def proto_act(session_id: str, action: dict[str, Any]) -> dict[str, Any]:
        """Act on the latest snapshot: {type: click|type|select|scroll|key|wait, ref?, text?, value?}."""
        t = time.perf_counter()
        return _env("proto_act", services.proto_act(session_id, action), t)

    @mcp.tool()
    def proto_read(session_id: str) -> dict[str, Any]:
        """Re-read the current snapshot of a session."""
        t = time.perf_counter()
        return _env("proto_read", services.proto_read(session_id), t)

    @mcp.tool()
    def proto_close(session_id: str) -> dict[str, Any]:
        """Close a browser session."""
        t = time.perf_counter()
        return _env("proto_close", services.proto_close(session_id), t)

    @mcp.tool()
    def list_proto_sessions() -> dict[str, Any]:
        """List live browser sessions."""
        t = time.perf_counter()
        return _env("list_proto_sessions", services.list_proto_sessions(), t)

    @mcp.tool()
    def brief_prototype_session(persona_id: str, prototype_id: str) -> dict[str, Any]:
        """GATHER persona context + how-to-drive + anti-steering before a persona uses the app."""
        t = time.perf_counter()
        return _env("brief_prototype_session", services.brief_prototype_session(persona_id, prototype_id), t)

    @mcp.tool()
    def record_prototype_session(persona_id: str, prototype_id: str, session_id: str, date: str,
                                 reaction: dict[str, Any], key: str | None = None,
                                 dispatch_token: str | None = None) -> dict[str, Any]:
        """Persist a persona's grounded prototype use as an experience + memory + artifact; rejects
        claims with no matching observed state in the session log. `reaction.statements` is the ONE
        voice shape: {persona_id, text, stance:{value -2..2,
        label?: support|conditional|neutral|skeptical|oppose} (the closed scale — see
        suggest_stances), about, refs}. Pass a stable `key` for a DETERMINISTIC id so re-running the
        step is an idempotent upsert (resumable runs, ESV). In a governed run pass the issued
        dispatch_token; only a grounded, verified session can close a Reaction Test task."""
        t = time.perf_counter()
        return _env("record_prototype_session",
                    services.record_prototype_session(
                        persona_id, prototype_id, session_id, date, reaction, key,
                        dispatch_token=dispatch_token), t)

    # M3 — the delete_* CRUD tools moved to _tools_research.py (their project/artifact domain).

    # M3 — brief_month/record_month_bundle moved to _tools_simulation; brief_evidence_check/
    # record_evidence_check moved to _tools_eval (their domains).

    # M2 — backfill_embeddings / prune_memory are MAINTENANCE actions, CLI-only (off the agent surface).
