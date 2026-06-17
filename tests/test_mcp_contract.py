"""Item 1 (part A): the MCP tool surface — every result is enveloped, and the
gather→author→write-back tools (incl. the new cohort + critic tools) are
registered. This pins the contract the host agent depends on."""
from __future__ import annotations

import asyncio

from sonaloop.mcp_server import build_server, _env


def test_envelope_shape():
    env = _env("demo_tool", {"x": 1}, 0.0)
    assert env["ok"] is True
    assert env["data"] == {"x": 1}
    assert set(env) == {"ok", "data", "next_recommended_tool", "_meta"}
    assert env["_meta"]["tool"] == "demo_tool"
    assert "latency_ms" in env["_meta"] and "schema_version" in env["_meta"]


def test_next_recommended_dag():
    # The decision DAG points each gather step at its write-back step.
    env = _env("brief_synthesis", {}, 0.0)
    assert env["next_recommended_tool"]["name"] == "record_synthesis"
    env2 = _env("brief_cohort_critic", {}, 0.0)
    assert env2["next_recommended_tool"]["name"] == "record_cohort_critic"


def test_next_recommended_tool_respects_trace_contract():
    env = _env("run_step", {"kind": "act", "must_link_before_complete": True}, 0.0)
    assert env["next_recommended_tool"]["name"] == "link_evidence"
    env2 = _env("complete_task", {"trace_nudge": {
        "next_tool": "link_evidence",
        "message": "link produced evidence before continuing",
    }}, 0.0)
    assert env2["next_recommended_tool"]["name"] == "link_evidence"


def test_expected_tools_registered():
    server = build_server()
    tools = asyncio.run(server.list_tools())
    names = {t.name for t in tools}
    # Core gather→author→write-back pairs the host relies on.
    expected = {
        "brief_persona", "record_persona", "get_persona", "list_personas",
        "prepare_persona_agent_context",
        "brief_day", "put_day_plan", "record_day",
        "brief_consolidation", "record_memory_deltas",
        "brief_synthesis", "record_synthesis", "export_synthesis",
        # the shareable read-only static HTML bundle (token-in-path share secret):
        "export_synthesis_html",
        "record_council",
        "brief_eval_critic", "record_eval_critic", "evaluate_simulation_full",
        # the tracker's new tools:
        "evaluate_cohort_diversity", "brief_cohort_critic", "record_cohort_critic",
        # research graph + report (a report IS a project-scope synthesis):
        "create_research_project", "list_research_projects", "get_project_graph",
        "available_project_icons", "set_project_icon", "generate_project_icon",
        "brief_synthesis_outline", "record_synthesis_outline", "brief_synthesis_section",
        "record_synthesis_section",
        # deletes (CRUD complete via MCP):
        "delete_research_project",
        "delete_synthesis", "delete_council", "delete_persona",
        # methodologies = plan SEEDS (the single runtime engine is the plan; HX3):
        "list_methodologies", "get_methodology", "register_methodology",
        "list_frameworks", "describe_framework",
        "set_project_methodology", "brief_next", "record_judgment",
        # research-plan engine (analyze/act/verify):
        "start_project", "get_plan", "add_task", "record_frame", "link_evidence",
        "complete_task", "iterate_task", "next_action", "assess_project", "assess_progress",
        # prototypes + Playwright harness:
        "scaffold_prototype", "register_prototype", "list_prototypes", "get_prototype",
        "run_prototype", "stop_prototype", "delete_prototype",
        "proto_open", "proto_act", "proto_read", "proto_close", "list_proto_sessions",
        "brief_prototype_session", "record_prototype_session",
        # usability sessions (the durable, replayable trace):
        "brief_usability_session", "record_usability_session", "get_usability_session",
        "list_usability_sessions", "suggest_friction_levels", "get_session_funnel",
        # surveys (the outbound instrument: author → export → import real responses → evidence):
        "brief_survey", "record_survey", "get_survey", "list_surveys", "export_survey",
        "import_survey_responses", "survey_results", "attach_survey_evidence",
        # hypotheses (falsifiable predictions scored against reality → eval_reports):
        "brief_hypothesis", "record_hypothesis", "record_hypothesis_result", "drop_hypothesis", "eval_scorecard",
        "get_hypothesis", "list_hypotheses",
        # authoring vocabularies (the stance scale is the CLOSED set every stance resolves onto):
        "suggest_stances", "suggest_finding_kinds",
        # primitive/form taxonomy registry:
        "list_primitives", "list_forms", "get_form", "suggest_forms",
    }
    missing = expected - names
    assert not missing, f"MCP tools missing: {sorted(missing)}"
    # M1 — the pre-HX3 constellation study-graph tools + the start_methodology_project alias are
    # RETIRED from the agent surface (the plan engine is the single graph path). Guard against regress.
    retired = {"add_study_to_project", "set_study_themes", "link_studies", "remove_study_from_project",
               "unlink_studies", "start_methodology_project"}
    # M2 — admin/maintenance actions are CLI-only, off the agent surface.
    admin = {"purge_runtime_data", "clear_simulations", "prune_memory", "backfill_embeddings",
             "backfill_project_from_syntheses", "import_snapshot", "export_snapshot", "export_logs"}
    leaked = (retired | admin) & names
    assert not leaked, f"retired/admin tools still on the agent surface: {sorted(leaked)}"


def test_catalogue_covers_every_tool_grouped_by_domain():
    """The auto-generated catalogue resource indexes EVERY registered tool, grouped by domain, so it
    can't drift from the live registry (spec/mcp-surface-cleanup.md M5)."""
    import asyncio, re
    from sonaloop.mcp_server import build_server
    from sonaloop.mcp_server._catalogue import catalogue_md
    srv = build_server()
    live = {t.name for t in asyncio.run(srv.list_tools())}
    md = catalogue_md()
    listed = set(re.findall(r"- \*\*([a-z_]+)\*\*", md))
    assert live.issubset(listed), f"catalogue missing tools: {sorted(live - listed)}"
    # grouped under the right domain headers + the resource is registered
    assert "## Plan engine & run loop" in md and "- **run_step**" in md
    assert "## Councils & syntheses" in md and "- **record_council**" in md
    uris = {str(r.uri) for r in asyncio.run(srv.list_resources())}
    assert "sonaloop://guide/catalogue" in uris


def _call(server, name: str, args: dict):
    """Call a tool through the live server; FastMCP returns (content, structured) — the
    structured result is the `_env` envelope the host agent sees."""
    _, structured = asyncio.run(server.call_tool(name, args))
    return structured


def test_register_methodology_roundtrip_over_mcp():
    """The 'author a Design Sprint' story, entirely over MCP: register a custom NON-alternating
    constellation (fan→fan, no decide in between), read it back, and immediately seed a study's
    plan with it — the fan→fan edge survives seeding (ordering preserved)."""
    server = build_server()
    spec = {
        "key": "design_sprint_lite", "name": "Design Sprint (lite)", "description": "d",
        "when_to_use": "w",
        "steps": [
            {"id": "map", "name": "Map", "tags": ["explore"], "intent": "map the problem"},
            {"id": "sketch", "name": "Sketch", "tags": ["explore", "build"], "consumes": ["map"],
             "intent": "sketch solutions"},                       # fan→fan, no decide between
            {"id": "decide", "name": "Decide", "tags": ["decide"], "consumes": ["sketch"],
             "requires": {"min_inputs": 2, "gate_tag": "divergence_complete"},
             "produces": {"role": "pov"}},
        ],
    }
    env = _call(server, "register_methodology", {"spec": spec})
    assert env["ok"] and env["data"]["key"] == "design_sprint_lite"
    assert env["next_recommended_tool"]["name"] == "start_project"
    got = _call(server, "get_methodology", {"key": "design_sprint_lite"})["data"]
    assert [s["id"] for s in got["steps"]] == ["map", "sketch", "decide"]
    proj = _call(server, "start_project",
                 {"title": "DS", "goal": "g", "methodology": "design_sprint_lite"})["data"]
    plan = _call(server, "get_plan", {"project_id": proj["id"]})["data"]
    tasks = {t["id"]: t for t in plan["tasks"]}
    assert tasks["frame__sketch"]["consumes"] == ["frame__map"]   # fan→fan edge kept
    assert tasks["verify__decide"]["consumes"] == ["frame__sketch"]
    assert tasks["verify__decide"]["requires"]["gate_tag"] == "divergence_complete"


def test_register_methodology_errors_carry_stable_code_over_mcp():
    """Bad specs and built-in shadowing fail with the stable MethodologyError code in the tool
    error text, so an agent can match the code, fix the spec, and retry."""
    import pytest
    from mcp.server.fastmcp.exceptions import ToolError
    server = build_server()
    with pytest.raises(ToolError, match="BAD_SPEC"):              # missing steps
        asyncio.run(server.call_tool("register_methodology", {"spec": {
            "key": "x", "name": "X", "description": "d", "when_to_use": "w"}}))
    with pytest.raises(ToolError, match="RESERVED_KEY"):          # built-in keys are reserved
        asyncio.run(server.call_tool("register_methodology", {"spec": {
            "key": "double_diamond", "name": "Shadow", "description": "d", "when_to_use": "w",
            "steps": [{"id": "a", "name": "A"}, {"id": "b", "name": "B", "consumes": ["a"]}]}}))


def test_specialized_mcp_council_tools_remain_registry_compatible():
    """Old MCP clients can keep calling the specialized tools; the recorded rows still classify
    through canonical registry forms."""
    from sonaloop import services

    server = build_server()
    proj = _call(server, "start_project", {"title": "Compat", "goal": "g"})["data"]
    h2h = _call(server, "record_head_to_head", {
        "project_id": proj["id"], "prompt": "A or B?", "options": ["A", "B"], "key": "compat-h2h",
    })["data"]
    rt = _call(server, "record_red_team", {
        "project_id": proj["id"], "prompt": "What breaks?", "objections": [], "key": "compat-rt",
    })["data"]
    assert services.council_form(h2h) == "option_comparison"
    assert services.council_form(rt) == "objection_review"
    assert _call(server, "get_head_to_head", {"session_id": h2h["id"]})["ok"]
    assert _call(server, "get_red_team", {"session_id": rt["id"]})["ok"]


def test_suggest_stances_matches_scale_data():
    """suggest_stances over MCP returns EXACTLY the scale's terms/values/aliases in +2→−2 order —
    derived live from suggestions/stance_scale.json (drift-proof: edit the JSON, the tool follows)."""
    import json
    from sonaloop import artifacts
    from sonaloop.config import suggestions_dir
    env = _call(build_server(), "suggest_stances", {})
    items = env["data"]["items"]
    assert [(i["term"], i["value"]) for i in items] == \
        [(r["term"], r["value"]) for r in artifacts.stance_terms()]
    assert [i["value"] for i in items] == sorted((i["value"] for i in items), reverse=True)
    raw = json.loads((suggestions_dir() / "stance_scale.json").read_text(encoding="utf-8"))
    for it in items:                                   # every JSON alias surfaces under its term
        expect = {a for a, t in raw["aliases"].items() if t == it["term"]}
        assert expect.issubset(set(it["aliases"])), it["term"]
        assert it["label_key"]                         # i18n key only — the engine stays web-free
    # The note teaches the authoring contract (optional label, label_raw preservation).
    note = env["data"]["note"]
    assert "label_raw" in note and "|".join(i["term"] for i in items) in note


def test_suggest_finding_kinds_matches_data():
    """suggest_finding_kinds returns the finding_kinds.json vocabulary verbatim."""
    import json
    from sonaloop.config import suggestions_dir
    raw = json.loads((suggestions_dir() / "finding_kinds.json").read_text(encoding="utf-8"))
    env = _call(build_server(), "suggest_finding_kinds", {})
    assert [i["tag"] for i in env["data"]["items"]] == [i["tag"] for i in raw["items"]]


def test_stance_shape_always_names_the_canonical_terms():
    """Docstring drift guard: wherever host-facing text states the stance SHAPE (`value -2..2`), it
    must also name the label vocabulary — one consistent phrasing, derived from the scale data so a
    JSON edit fails this test until every docstring/brief is updated. Hosts invented labels exactly
    because the shape used to appear bare."""
    import pathlib, re
    from sonaloop import artifacts
    vocab = "|".join(r["term"] for r in artifacts.stance_terms())
    canonical = f"value -2..2, label?: {vocab}"
    # Accepted continuations: the canonical vocabulary literal, or the source-level seam that splices
    # it live from stance_terms() (suggestions.py builds the note from the data — it can't go stale).
    bare = re.compile(r"value -2\.\.2(?!" + re.escape(f", label?: {vocab}")
                      + r"|" + re.escape(', label?: " + ') + r")")
    pkg = pathlib.Path(artifacts.__file__).parent
    offenders = []
    for f in (sorted(pkg.glob("*.py")) + sorted((pkg / "mcp_server").glob("*.py"))
              + sorted((pkg / "services").glob("*.py")) + sorted((pkg / "llm_simulation").glob("*.py"))):
        flat = " ".join(f.read_text(encoding="utf-8").split())   # docstrings wrap; compare flattened
        if bare.search(flat):
            offenders.append(str(f.relative_to(pkg.parent)))
    assert not offenders, f"bare stance shape (without '{canonical}') in: {offenders}"
    # And the live tool surface: any tool description stating the shape carries the vocabulary.
    tools = asyncio.run(build_server().list_tools())
    undocumented = [t.name for t in tools
                    if "value -2..2" in " ".join((t.description or "").split())
                    and canonical not in " ".join((t.description or "").split())]
    assert not undocumented, f"tool docstrings missing the stance vocabulary: {undocumented}"


def test_every_tool_documented():
    """Every registered MCP tool carries a docstring → a non-empty description for clients and a real
    one-line entry in the auto-generated catalogue (no `— —` placeholders)."""
    server = build_server()
    tools = asyncio.run(server.list_tools())
    undocumented = sorted(t.name for t in tools if not (t.description or "").strip())
    assert not undocumented, f"MCP tools missing a docstring: {undocumented}"
