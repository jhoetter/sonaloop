from __future__ import annotations

import time
from typing import Any

from .. import services
from ..config import MEMORY_SCHEMA_VERSION
from ._env import _env


def register_council(mcp):
    # M3 — persona timeline/activity reads (get_current_state/get_calendar/get_calendar_period/
    # get_activity/summarize_persona_period/extract_pain_points) moved to _tools_simulation (memory).

    # ================= Artifacts (bring a REAL artifact into a council) =================
    @mcp.tool()
    def add_artifact(project_id: str, url: str, kind: str = "url", title: str = "",
                     label: str | None = None, capture: bool = True, key: str | None = None,
                     dispatch_token: str | None = None) -> dict[str, Any]:
        """Bring a REAL artifact into a project's council pool so personas react to what is ACTUALLY
        there — a live URL/website, a prototype link (kind='prototype', e.g. Figma), or one side of an
        A/B comparison (kind='variant'). The page is CAPTURED to a grounded text snapshot (title,
        meta, headings, visible copy) + a captured-at timestamp + content hash, so the run is
        reproducible. Capture degrades gracefully (a dead link still stores the ref). Add TWO+ variants
        to compare them in one council (the head_to_head plumbing). Then run brief_council with
        artifact_ids=[...] (or omit it to include all). Pass `capture=False` to store the ref only.
        During a governed run pass the exact dispatch_token so the artifact is linked automatically."""
        t = time.perf_counter()
        return _env("add_artifact", services.add_artifact(
            project_id, url, kind, title, label, capture, key,
            dispatch_token=dispatch_token), t)

    @mcp.tool()
    def list_artifacts(project_id: str) -> dict[str, Any]:
        """List every artifact ingested into a project (id, label A/B/…, kind, url, capture status)."""
        t = time.perf_counter()
        return _env("list_artifacts", services.list_artifacts(project_id), t)

    @mcp.tool()
    def get_artifact(project_id: str, artifact_id: str) -> dict[str, Any]:
        """One artifact (by id or A/B label) with its full captured snapshot."""
        t = time.perf_counter()
        return _env("get_artifact", services.get_artifact(project_id, artifact_id), t)

    @mcp.tool()
    def delete_artifact(project_id: str, artifact_id: str) -> dict[str, Any]:
        """Remove an artifact (by id or label) from a project's pool."""
        t = time.perf_counter()
        return _env("delete_artifact", services.delete_artifact(project_id, artifact_id), t)

    # ================= Council =================
    @mcp.tool()
    def suggest_stances() -> dict[str, Any]:
        """The CANONICAL stance vocabulary — call this before authoring statement stances, votes, or
        head-to-head/red-team reactions. Every stance is
        {value -2..2, label?: support|conditional|neutral|skeptical|oppose}:
        the five terms in scale order (+2 support … −2 oppose) with each
        term's value, i18n label_key and accepted aliases (EN/DE compatibility tokens). Unlike the other
        suggest_* vocabularies this set is CLOSED: `label` is optional when `value` is given, a known
        alias resolves to its term, and an unknown label buckets at neutral but is preserved as
        `label_raw` — never invent stance words when these five fit. Derived live from the scale data
        (suggestions/stance_scale.json); council votes use the same terms."""
        t = time.perf_counter()
        return _env("suggest_stances", services.suggest_stances(), t)

    @mcp.tool()
    def suggest_finding_kinds() -> dict[str, Any]:
        """SUGGESTED Finding kinds (summary/key_problem/pain_solver/open_question/recommendation/
        cluster/segment/shortlist/ranking/pain_point) for a `findings` item's `kind`, with the section
        id + label each renders under. Recommendations only — an invented kind still renders with a
        generic fallback."""
        t = time.perf_counter()
        return _env("suggest_finding_kinds", services.suggest_finding_kinds(), t)

    @mcp.tool()
    def brief_council(project_id: str, prompt: str, persona_ids: list[str] | None = None, filters: dict[str, Any] | None = None,
                      count: int = 3, context: str | None = None, artifact_ids: list[str] | None = None) -> dict[str, Any]:
        """Gather a council. A council is scoped to a research project, so `project_id` is
        REQUIRED (create one first with create_research_project; personas are global and need
        no project). Without persona_ids: returns candidate personas to select from. With
        persona_ids: returns each participant's loaded agent context (SOUL + memory) to author
        turns against. Pass `artifact_ids` (or omit to include every project artifact) to ground
        the council in the CAPTURED artifact(s) — a URL/website, a prototype link, or A/B variants
        present side-by-side. Then author proposal/votes/exec_summary and call record_council. See
        the run-council skill."""
        t = time.perf_counter()
        return _env("brief_council", services.brief_council(project_id, prompt, persona_ids, filters, count, context, artifact_ids), t)

    @mcp.tool()
    def brief_ask(persona_id: str, question: str, context: str | None = None) -> dict[str, Any]:
        """Gather one persona's loaded context (SOUL + recent events + task-keyed memory)
        so you can author an honest, in-character answer. No server-side generation."""
        t = time.perf_counter()
        return _env("brief_ask", services.brief_ask(persona_id, question, context), t)

    @mcp.tool()
    def record_council(project_id: str, prompt: str, persona_ids: list[str], statements: list[dict[str, Any]] | None = None, votes: list[dict[str, Any]] | None = None, proposal: str = "", summary: str = "", exec_summary: str = "", selection_reason: str = "", questions: list[str] | None = None, key: str | None = None, findings: list[dict[str, Any]] | None = None, prompts: list[dict[str, Any]] | None = None, claims: list[dict[str, Any]] | None = None, dispatch_token: str | None = None) -> dict[str, Any]:
        """Persist a host-authored council. Shape it by what you pass (the UI derives the mode):
        DISCOVERY = `questions` (open user-research questions), NO proposal/votes; EVALUATION =
        `proposal` (a concept reacted to) + stances; DECISION = `proposal` + `votes`.

        Author the voices as `statements` (the ONE voice primitive): one per persona utterance —
        {persona_id, text, stance:{value -2..2, label?: support|conditional|neutral|skeptical|oppose}
        (the closed scale — see suggest_stances), about:{kind:'prompt', id:'q0'|'proposal'},
        refs:[{kind,id,anchor,role}|{kind:'memory',text}]}. For a DISCOVERY council set each
        statement's about.id to the question it answers ('q0','q1',…) so the page renders a moderated
        Q→A transcript. `findings` is the optional analysis ({text, kind, score, refs}); `prompts` are
        derived from questions/proposal when omitted. A council MUST belong to a research project.
        `claims` covers every factual assertion in summary/exec_summary as
        {text, posture: observed|memory_grounded|inferred|simulated|unsupported, refs}. Reaction
        Tests reject observed-behavior claims without a grounded session step and remain an
        unverified draft while prose is uncovered. In a governed run pass run_step's dispatch_token;
        the council is written, linked and checkpointed atomically when all gates pass. Pass a stable
        `key` outside a run for a deterministic id."""
        t = time.perf_counter()
        return _env("record_council", services.record_council(
            project_id, prompt, persona_ids, statements, votes, proposal, summary,
            exec_summary, selection_reason, questions, key, findings, prompts,
            claims=claims, dispatch_token=dispatch_token), t)

    @mcp.tool()
    def get_council(session_id: str) -> dict[str, Any]:
        """Fetch one council session by id (prompt, turns/statements, votes, summary)."""
        t = time.perf_counter()
        return _env("get_council", services.get_council(session_id), t)

    # ================= Head-to-Head (X vs Y Format) =================
    @mcp.tool()
    def brief_head_to_head(project_id: str, prompt: str, options: list[Any], persona_ids: list[str] | None = None,
                           filters: dict[str, Any] | None = None, count: int = 4, context: str | None = None) -> dict[str, Any]:
        """Gather a HEAD-TO-HEAD (X vs Y) — run the panel on a DIRECT comparison of two (or more) concrete
        options and get a reasoned, segmented preference, NOT two separate yes/no councils. `options` are
        the things compared: an ARTIFACT already ingested via add_artifact (pass its id or A/B label — e.g.
        two captured variants) OR a plain TEXT option (a string, or {label?, title?, text} for "$29/mo" vs
        "$49/mo"). They are labelled A/B/… and folded into each participant's context side-by-side. Without
        persona_ids: returns a segment-diverse candidate panel. With persona_ids: returns each participant's
        loaded context + the labelled options to author per-option stances and a per-persona preference
        against; then call record_head_to_head. Build the two options first (add_artifact, or pass text)."""
        t = time.perf_counter()
        return _env("brief_head_to_head", services.brief_head_to_head(project_id, prompt, options, persona_ids, filters, count, context), t)

    @mcp.tool()
    def record_head_to_head(project_id: str, prompt: str, options: list[Any], preferences: list[dict[str, Any]] | None = None,
                            persona_ids: list[str] | None = None, statements: list[dict[str, Any]] | None = None,
                            summary: str = "", exec_summary: str = "", selection_reason: str = "",
                            findings: list[dict[str, Any]] | None = None, key: str | None = None,
                            variant_meta: dict[str, Any] | None = None,
                            claims: list[dict[str, Any]] | None = None,
                            dispatch_token: str | None = None) -> dict[str, Any]:
        """Persist a host-authored HEAD-TO-HEAD (stored as a CouncilSession with a `head_to_head` block).
        Pass the labelled `options`, each persona's `preferences` ([{persona_id, choice (an option label
        'A'|'B'|…), intensity?, reason}]), the authored `statements` (one per persona+option, stance:{value -2..2,
        label?: support|conditional|neutral|skeptical|oppose} — see suggest_stances,
        about={kind:'prompt', id:'opt:A'|'opt:B'}), and the prose verdict in exec_summary/summary. The
        SERVER deterministically tallies overall preference + margin (how decisive) + abstentions +
        segment-splits (who prefers what, by persona segment) — you author the qualitative synthesis.
        For an A/B TEST (taxonomy job `ab_test`) also pass `variant_meta`: {variants: {label: {id, …}},
        order_shown: {persona_id: [labels] — the order actually shown, from the brief's per-participant
        option_order}, hypothesis_id: the ONE bet stamped BEFORE exposure (record_hypothesis)}. It is
        validated (orders must be permutations; the hypothesis must resolve) and persisted with the
        result — queryable via get_head_to_head. Returns the session incl. head_to_head.result.
        Pass a stable `key` for a deterministic id (idempotent upsert)."""
        t = time.perf_counter()
        return _env("record_head_to_head", services.record_head_to_head(
            project_id, prompt, options, preferences, persona_ids, statements, summary,
            exec_summary, selection_reason, findings, key, variant_meta,
            claims=claims, dispatch_token=dispatch_token), t)

    @mcp.tool()
    def get_head_to_head(session_id: str) -> dict[str, Any]:
        """Fetch one head-to-head result by session id — its options, per-persona preferences, the
        deterministic aggregate (preference + margin + abstentions + segment-splits) and, when recorded
        with the A/B protocol, its variant_meta (variant ids, per-persona order shown, hypothesis ref)."""
        t = time.perf_counter()
        return _env("get_head_to_head", services.get_head_to_head(session_id), t)

    # ================= Price Ladder (pricing Job protocol) =================
    @mcp.tool()
    def brief_price_ladder(project_id: str, prompt: str, price_points: list[Any],
                           persona_ids: list[str] | None = None, filters: dict[str, Any] | None = None,
                           count: int = 4, context: str | None = None) -> dict[str, Any]:
        """Gather a PRICE LADDER (pricing Job protocol — willingness-to-pay): a FIXED ascending ladder of
        price points every persona reacts to, one van-Westendorp anchor band per rung (too_cheap | bargain |
        getting_expensive | too_expensive), grounded in the persona's profile budget/constraints.
        `price_points` are numbers, price strings ('$29/mo') or {label, amount}. Without persona_ids:
        returns a candidate panel — span willingness-to-pay and include the budget holder. With
        persona_ids: returns each participant's loaded context with the ladder folded in; author one
        banded reaction + grounding quote per persona per rung, then call record_price_ladder."""
        t = time.perf_counter()
        return _env("brief_price_ladder", services.brief_price_ladder(project_id, prompt, price_points, persona_ids, filters, count, context), t)

    @mcp.tool()
    def record_price_ladder(project_id: str, prompt: str, price_points: list[Any],
                            responses: list[dict[str, Any]] | None = None,
                            persona_ids: list[str] | None = None, statements: list[dict[str, Any]] | None = None,
                            summary: str = "", exec_summary: str = "", selection_reason: str = "",
                            findings: list[dict[str, Any]] | None = None, key: str | None = None,
                            claims: list[dict[str, Any]] | None = None,
                            dispatch_token: str | None = None) -> dict[str, Any]:
        """Persist a host-authored PRICE LADDER (stored as a CouncilSession with a `price_ladder` block).
        `responses` is the structured willingness-to-pay payload — one row per persona per rung:
        {persona_id, price (rung label or amount), band (too_cheap|bargain|getting_expensive|too_expensive
        — closed vocabulary, off-scale rejected), quote (the persona's words, grounded in their
        budget/constraints)}. The SERVER deterministically derives acceptance per rung, the
        acceptable-price range and the cliff point — overall AND per segment — you author the pricing
        story in exec_summary/summary. Tier comparisons reuse record_head_to_head with price as
        variant_meta. Pass a stable `key` for a deterministic id (idempotent upsert)."""
        t = time.perf_counter()
        return _env("record_price_ladder", services.record_price_ladder(
            project_id, prompt, price_points, responses, persona_ids, statements,
            summary, exec_summary, selection_reason, findings, key,
            claims=claims, dispatch_token=dispatch_token), t)

    @mcp.tool()
    def get_price_ladder(session_id: str) -> dict[str, Any]:
        """Fetch one price-ladder result by session id — the ladder, the raw per-persona/per-rung banded
        responses (persona, price point, band, quote) and the derived result (acceptance per rung,
        acceptable range + cliff, overall and per segment)."""
        t = time.perf_counter()
        return _env("get_price_ladder", services.get_price_ladder(session_id), t)

    @mcp.tool()
    def price_ladder_analysis(session_id: str) -> dict[str, Any]:
        """The analytics shape of a recorded price ladder: acceptable-price range + cliff points, overall
        and one row per segment (pricing protocol step range_and_cliffs) — the deterministic numbers the
        host's pricing story stands on."""
        t = time.perf_counter()
        return _env("price_ladder_analysis", services.price_ladder_analysis(session_id), t)

    # ================= Red-Team (falsification Format) =================
    @mcp.tool()
    def brief_red_team(project_id: str, prompt: str, persona_ids: list[str] | None = None,
                       filters: dict[str, Any] | None = None, count: int = 4, context: str | None = None,
                       stance: str = "against", artifact_ids: list[str] | None = None) -> dict[str, Any]:
        """Gather a RED-TEAM (falsification) — run the panel to ATTACK the idea instead of flattering it
        ("why would this segment NOT adopt / NOT pay / churn?"), so the output stress-tests it. It REFRAMES a
        normal council toward DISCONFIRMATION and assigns each persona an explicit, deterministic adversarial
        lens (skeptic / blocker / switching-cost / status-quo / risk). Ground it in a REAL artifact with
        `artifact_ids` (a captured URL/price page/prototype). `stance` runs the SAME question in both
        directions: 'against' (default — case against), 'for' (confirming), or 'both'. Without persona_ids:
        returns a segment-diverse candidate panel. With persona_ids: returns each participant's loaded
        context (with its adversarial role stamped in) to author concrete objections, plus `prior_themes`
        (this project's earlier red-team themes) and `suggested_themes` (common blocker families) — REUSE
        one when it fits so a shared blocker doesn't fragment across near-duplicate labels — then call
        record_red_team."""
        t = time.perf_counter()
        return _env("brief_red_team", services.brief_red_team(project_id, prompt, persona_ids, filters, count, context, stance, artifact_ids), t)

    @mcp.tool()
    def record_red_team(project_id: str, prompt: str, objections: list[dict[str, Any]] | None = None,
                        endorsements: list[dict[str, Any]] | None = None, stance: str = "against",
                        persona_ids: list[str] | None = None, statements: list[dict[str, Any]] | None = None,
                        summary: str = "", exec_summary: str = "", selection_reason: str = "",
                        findings: list[dict[str, Any]] | None = None, key: str | None = None,
                        claims: list[dict[str, Any]] | None = None,
                        dispatch_token: str | None = None) -> dict[str, Any]:
        """Persist a host-authored RED-TEAM (stored as a CouncilSession with a `red_team` block). Pass the
        per-persona `objections` ([{persona_id, theme (a short blocker label), text (the objection in voice),
        severity 'low'|'medium'|'high'|'critical'}]) — the case AGAINST — plus the authored `statements`
        (about={kind:'prompt', id:'red_team'},
        stance:{value -2..2, label?: support|conditional|neutral|skeptical|oppose} — see
        suggest_stances) and the prose verdict in exec_summary/summary. The SERVER
        deterministically groups objections by theme (case/whitespace-insensitive — reuse the brief's
        prior_themes/suggested_themes labels) into the structured case-against (how many personas raise
        each blocker + worst severity) — you author the qualitative synthesis. With stance='both', pass
        `endorsements` ([{persona_id, theme, text}]) to also store the case FOR side by side. Returns the
        session incl. red_team.case_against, plus `hints` when the case looks fragmented (mostly
        single-persona themes). Pass a stable `key` for a deterministic id (idempotent upsert)."""
        t = time.perf_counter()
        return _env("record_red_team", services.record_red_team(
            project_id, prompt, objections, endorsements, stance, persona_ids,
            statements, summary, exec_summary, selection_reason, findings, key,
            claims=claims, dispatch_token=dispatch_token), t)

    @mcp.tool()
    def get_red_team(session_id: str) -> dict[str, Any]:
        """Fetch one red-team result by session id — its stance, adversarial roles, per-persona objections
        and the deterministic case-against (themes grouped by blocker, count + worst severity)."""
        t = time.perf_counter()
        return _env("get_red_team", services.get_red_team(session_id), t)

    @mcp.tool()
    def list_councils(limit: int = 25, cursor: str | None = None) -> dict[str, Any]:
        """List council sessions (id, prompt, persona count, votes), newest first.
        Paginated per the shared convention (docs/pagination.md): `limit` (default 25) +
        opaque `cursor`; answers {items, total, has_more, next_cursor}. No params → the
        first page (backward compatible)."""
        t = time.perf_counter()
        def key(c: dict[str, Any]) -> str:
            return f'{c.get("created_at") or ""}\x1f{c.get("id") or ""}'
        rows = sorted(services.list_councils(), key=key, reverse=True)
        page = services.paginate(rows, key, limit=limit, cursor=cursor, reverse=True)
        return _env("list_councils", page, t)

    # M3 — attach_evidence / export_persona (persona-scoped) moved to _tools_personas.

    # M2 — export_logs / export_snapshot / import_snapshot are operator backup/debug actions, CLI-only.

    @mcp.tool()
    def export_council_session(session_id: str, format: str = "json") -> dict[str, Any]:
        """Export one council session as a document (md|json) for sharing."""
        t = time.perf_counter()
        return _env("export_council_session", services.export_council_session(session_id, format), t)

    # ----- Synthesis (study arc over a chain of councils) -----
    @mcp.tool()
    def brief_synthesis(council_ids: list[str], title: str | None = None, start_input: str | None = None, goal: str | None = None) -> dict[str, Any]:
        """GATHER an ordered chain of councils (their exec_summaries/votes) so you can author
        a cross-council synthesis (arc, gesamtbild, recommendations, positioning, pain-solvers)."""
        t = time.perf_counter()
        return _env("brief_synthesis", services.brief_synthesis(council_ids, title, start_input, goal), t)

    @mcp.tool()
    def record_synthesis(title: str, start_input: str, council_ids: list[str] | None = None, payload: dict[str, Any] | None = None, goal: str = "", synthesis_id: str | None = None, key: str | None = None, project_id: str = "", dispatch_token: str | None = None) -> dict[str, Any]:
        """Persist/UPDATE a host-authored synthesis. A synthesis is DECOUPLED from councils:
        `council_ids` is OPTIONAL (may be empty — affinity over notes, a synthesis over syntheses, or
        a standalone analysis); councils are cited evidence, not sub-parts. Pass `project_id` when the
        synthesis answers one project's inquiry so it lists on that project's page. Pass the same
        synthesis_id (or a stable `key`) to update in place / make a long run resumable. Link it to
        its verify task with link_evidence. In a governed run pass run_step's dispatch_token; the
        report is auto-linked, and remains linked-but-open until the verify judgment passes. Reaction
        Test payloads must include `claims` with explicit posture+refs for report prose."""
        t = time.perf_counter()
        return _env("record_synthesis", services.record_synthesis(
            title, start_input, council_ids, payload, goal, synthesis_id, key,
            project_id=project_id, dispatch_token=dispatch_token), t)

    @mcp.tool()
    def get_synthesis(synthesis_id: str) -> dict[str, Any]:
        """Fetch one report (synthesis) by id — its findings/sections/scope and metadata."""
        t = time.perf_counter()
        return _env("get_synthesis", services.get_synthesis(synthesis_id), t)

    @mcp.tool()
    def list_syntheses() -> dict[str, Any]:
        """List all reports (syntheses) — id, title, scope, date — for browsing."""
        t = time.perf_counter()
        return _env("list_syntheses", services.list_syntheses(), t)

    @mcp.tool()
    def export_synthesis(synthesis_id: str, format: str = "md", out_path: str | None = None) -> dict[str, Any]:
        """Export a report (synthesis). format: `md`|`json` returned inline · `pdf`|`pptx` rendered as a
        presentation-grade file and attached to the owning project as a deliverable asset; the result's
        `url` is the DOWNLOAD LINK — hand THAT to the user (the `path` is the server's own filesystem,
        unreachable for remote hosts). Compose with the authoring tools (record_synthesis_outline →
        record_synthesis_section, attach chart/figure figures) to shape the report from a request,
        then export it to share — no UI button needed."""
        t = time.perf_counter()
        fmt = (format or "md").lower()
        if fmt in ("pdf", "pptx"):
            # the one deliverable seam: relative paths land under data/exports/, and the file is
            # recorded on the owning project as a direction:out asset (deliverables on the page).
            return _env("export_synthesis",
                        services.export_synthesis_deliverable(synthesis_id, fmt, out_path), t)
        content = services.export_synthesis(synthesis_id, fmt)
        if out_path:
            return _env("export_synthesis", {"path": services.write_export(content, out_path), "format": fmt}, t)
        return _env("export_synthesis", content, t)

    @mcp.tool()
    def export_synthesis_html(synthesis_id: str, out_dir: str | None = None) -> dict[str, Any]:
        """Export a report (synthesis) as a SHAREABLE read-only static HTML bundle —
        `data/export/share/<token>/index.html`: the exact inspector document minus app chrome, all
        assets inlined (CSS, charts, figures, avatars), zero external requests, opens from file://.
        The result's `url` is the LIVE LINK to hand the user (auth-gated /data route); host the
        directory anywhere else if needed (S3, GitHub Pages, an intranet share) — the unguessable
        token directory name is the share secret. `out_dir` (optional) must stay inside the data dir."""
        t = time.perf_counter()
        return _env("export_synthesis_html", services.export_synthesis_html(synthesis_id, out_dir), t)

    # ================= Resources & prompts =================
    @mcp.resource("sonaloop://schema/memory")
    def memory_schema() -> str:
        """Read-only: the memory object model + the simulate->consolidate->digest loop."""
        return (
            "Sonaloop memory model (schema v%d):\n"
            "- entities(kind: project|person|org|building|authority|topic, status)\n"
            "- entity_facts(fact, status, t_valid, t_invalid, importance)  # bi-temporal, time-travel\n"
            "- threads(open loops with identity), event_entities(links), embeddings(semantic recall)\n"
            "- plans(day|week|month|quarter|year), memory_digests, persona_revisions, world_context\n"
            "Loop per day: brief_day -> put_day_plan -> simulate_day -> brief_consolidation -> "
            "record_memory_deltas -> (brief_digest/put_digest periodically) -> evaluate_simulation.\n"
            "Long horizons: brief_period -> put_period_plan (with sample_days) -> simulate only those days.\n"
            "All text is authored by you (the MCP host). The server gathers context and persists."
            % MEMORY_SCHEMA_VERSION
        )

    @mcp.resource("sonaloop://guide/research")
    def research_guide() -> str:
        """THE FRONT DOOR — read this first: the canonical path to drive a research project via MCP."""
        return (
            "Sonaloop — the canonical research path (ESV). The PLAN is the single engine; a\n"
            "deterministic run loop drives it, an independent critic decides when it's DONE.\n"
            "\n"
            "0. PERSONAS FIRST. Ensure a richly-segmented cohort with simulated memory exists\n"
            "   (list_personas; if thin, build via the simulate-cohort skill: brief_day/brief_period →\n"
            "   record_day / record_month_bundle). Councils are only as deep as the lives behind them.\n"
            "\n"
            "1. START. If begin_research_job is exposed, call that ONE cloud front door with the full\n"
            "   request, methodology=auto|freeform|exact name and one stable operation_id; repeat the\n"
            "   exact call on retry and never also call start_project/start_run. Otherwise use\n"
            "   start_project(... stable operation_id) then start_run(... stable operation_id).\n"
            "\n"
            "2. LOOP (you are the thin host over the engine). Repeat:\n"
            "     s = run_step(run_id)\n"
            "     - s.kind == 'done'   -> stop (status finished|capped|stopped).\n"
            "     - s.kind == 'critic' -> spawn an INDEPENDENT critic on s.brief; it authors the verdict,\n"
            "       calls record_completeness_critic + record_critic_round. (Loops until exhaustive.)\n"
            "     - s.step_id == '__report_handoff__' -> follow s.blocking_action; keep its exact\n"
            "       report_id + dispatch_token and brief/author every incomplete section. Partial\n"
            "       sections are progress; the final one checkpoints. Never create another report.\n"
            "     - else (analyze|act|verify) -> author ONE step grounded in s.next_action and pass\n"
            "       s.dispatch_token to its recorder. Token-aware recorders auto-link + checkpoint;\n"
            "       do not checkpoint twice. Resumable: re-run start_run(run_id=...).\n"
            "\n"
            "3. AUTHOR a step:\n"
            "   - analyze: Product Understanding preflight when requested; otherwise read cited memory\n"
            "       -> record_frame. Reaction Tests cannot bypass real stimulus/revision/capability refs.\n"
            "   - act: run a COUNCIL or build+test a PROTOTYPE.\n"
            "       COUNCIL has three shapes (derived; the UI branches): pass `questions=[...]` for\n"
            "       open DISCOVERY ('Welche Versicherungen hast du? Wie sparst du gerade?') with NO\n"
            "       proposal/votes (you are LISTENING — hypotheses come LATER, in Define); a `proposal`\n"
            "       to REACT to a concept (evaluation); proposal+votes only for an explicit DECISION.\n"
            "       Flow: brief_council -> author turns (set each turn's persona_id, content, stance,\n"
            "       memory_refs, input; for DISCOVERY also question_index = which question it answers,\n"
            "       one turn per persona+question) -> record_council.\n"
            "       PROTOTYPE: scaffold_prototype(concept) -> run_prototype -> a grounded proband session\n"
            "       (proto_open -> proto_act -> proto_read -> proto_close) -> record_prototype_session.\n"
            "       Then add_task + link_evidence + complete_task.\n"
            "   - verify: consolidate the fan -> record_synthesis (structured: clusters/key_problems/\n"
            "       ranking/shortlist) -> record_judgment(gate) -> complete_task.\n"
            "\n"
            "4. FINISH (the engine drives this on recommendation=='finish'): derive_sections (organize)\n"
            "   + one resumable report-handoff dispatch -> brief_synthesis_section/\n"
            "   record_synthesis_section for every section + a rich terminal Deliver\n"
            "   synthesis. score_run(project_id) snapshots quality. DONE only when assess_project.finish\n"
            "   is finished AND the completeness critic passes.\n"
            "   After DONE: brief_presentation(report_id) -> author + record_presentation_plan ->\n"
            "   export_synthesis. Build a visual decision story with native speaker notes and an\n"
            "   appendix; never mirror report sections one-for-one.\n"
            "\n"
            "PRINCIPLES: personas are STATELESS per council (each prompt stands alone); stay\n"
            "anti-steering (rejection is valid — don't nudge toward a product); honest unknowns become\n"
            "open questions, never fake progress. INSPECT anytime: list_research_projects ->\n"
            "get_project_graph -> assess_project (the pulse: recommendation, gaps, novelty, finish).\n"
            "Browse EVERY tool by domain: the `sonaloop://guide/catalogue` resource.\n"
            "Richer playbooks live in the skills: compose-research-plan / autonomous-research-run."
        )

    @mcp.prompt()
    def simulate_persona_day(persona_id: str, date: str) -> str:
        """Playbook: drive one persona-day through the full memory loop."""
        return (
            f"Simulate persona {persona_id} on {date} with memory:\n"
            f"1. brief_day({persona_id}, {date}) -> author a day plan grounded in the briefing -> put_day_plan.\n"
            f"2. simulate_day({persona_id}, {date}).\n"
            f"3. brief_consolidation({persona_id}, {date}) -> author memory_deltas -> record_memory_deltas.\n"
            f"4. Periodically brief_digest/put_digest; run evaluate_simulation to check quality.\n"
            "Author all text yourself; ground it in SOUL + recalled memory; never steer toward a product thesis."
        )
