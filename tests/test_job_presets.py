"""Job presets + the "sharpen the question" helper (the taxonomy's JOB layer; sonaloop/job_presets.py).

A preset exists for every website Job and is DERIVED from the canonical taxonomy (framework +
formats + coverage — never re-declared by hand); the sharpen helper is deterministic/structural
(checklist + clarifying questions + transparent keyword job-matching + a study spec the host
fills in — no server-side text-LLM call); start_job_study seeds a plan from a preset but never
blocks the general engine (framework swappable, off-menu studies untouched)."""
from __future__ import annotations

import pytest

from sonaloop import job_presets as JP
from sonaloop import job_taxonomy as T
from sonaloop import services


# ----------------------------------------------------------------------------- the preset library

def test_one_preset_per_taxonomy_job_in_order(store):
    presets = JP.job_presets(store)
    assert [p["id"] for p in presets] == [j["id"] for j in T.jobs()]
    assert {"positioning", "pricing", "jtbd_demand",
            "ideation_hmw", "continuous_discovery", "churn_reasons"} <= {p["id"] for p in presets}


def test_presets_derive_from_the_taxonomy_mapping(store):
    """Framework, formats and coverage are read from taxonomy.json — never duplicated by hand."""
    for preset, job in zip(JP.job_presets(store), T.jobs()):
        assert preset["framework"]["id"] == job["default_framework"]
        assert preset["framework"]["stages"], preset["id"]          # the full plain-language shape
        assert preset["framework_options"] == job["frameworks"]
        assert [f["id"] for f in preset["formats"]] == job["formats"]
        assert preset["coverage"] == job["coverage"]
        assert preset["sells_as"] == job["sells_as"] and preset["user_question"] == job["user_question"]


def test_preset_formats_carry_real_brief_record_tools(store):
    """Every suggested Format names the gather/write-back pair that actually runs it (e.g. the
    pricing preset suggests head-to-head via brief_head_to_head/record_head_to_head)."""
    for preset in JP.job_presets(store):
        for fmt in preset["formats"]:
            tools = fmt["tools"]
            assert tools["brief"] and tools["record"], (preset["id"], fmt["id"])
            assert callable(getattr(services, tools["brief"])), tools["brief"]
            assert callable(getattr(services, tools["record"])), tools["record"]
    pricing = JP.get_job_preset("pricing", store)
    h2h = next(f for f in pricing["formats"] if f["id"] == "head_to_head")
    assert h2h["tools"] == {"brief": "brief_head_to_head", "record": "record_head_to_head"}


def test_get_job_preset_round_trips_and_unknown_raises(store):
    assert JP.get_job_preset("positioning", store)["framework"]["id"] == "double_diamond"
    with pytest.raises(KeyError):
        JP.get_job_preset("nope", store)


def test_job_signals_cover_every_taxonomy_job():
    """The keyword matcher knows every Job — a new taxonomy Job must get signals too."""
    assert set(JP._JOB_SIGNALS) == {j["id"] for j in T.jobs()}


# ----------------------------------------------------------------------------- sharpen the question

def test_fuzzy_pricing_goal_matches_the_pricing_preset(store):
    out = services.sharpen_question("What should I charge for my SaaS?", store=store)
    assert out["schema"] == "sharpen_question"
    assert out["job_matches"][0]["job"] == "pricing"
    assert out["job_matches"][0]["matched"]                      # transparent: the terms that fired
    assert out["preset"]["id"] == "pricing"
    assert out["study_spec"]["framework"] == "lean_jtbd"         # from the taxonomy mapping
    assert out["study_spec"]["coverage"]["min_personas"] == 4


def test_checklist_names_the_well_formed_study_fields(store):
    out = services.sharpen_question("Is my product good?", store=store)
    assert [e["id"] for e in out["checklist"]] == ["decision", "audience", "comparator", "success_signal"]
    # Nothing answered yet → every field yields a targeted clarifying question, spec not ready.
    assert len(out["clarifying_questions"]) == 4
    assert out["ready"] is False and out["study_spec"]["ready"] is False
    assert all(e["question"] and e["why"] for e in out["checklist"])


def test_goal_cues_become_hints_not_answers(store):
    out = services.sharpen_question("Should we charge $29 vs $49 for SMB customers?", store=store)
    by_id = {e["id"]: e for e in out["checklist"]}
    assert by_id["decision"]["status"] == "hinted" and "should we" in by_id["decision"]["hints"]
    assert by_id["comparator"]["status"] == "hinted"             # " vs " detected
    # Hints never auto-answer: the field still appears in the clarifying questions.
    assert any(q["field"] == "comparator" for q in out["clarifying_questions"])


def test_answers_complete_the_spec_iteratively(store):
    answers = {"decision": "pick the launch price", "audience": "solo architects",
               "comparator": "$29 vs $49", "success_signal": "stated willingness to pay at $49"}
    out = services.sharpen_question("What should I charge?", answers=answers, store=store)
    assert out["ready"] is True and out["clarifying_questions"] == []
    spec = out["study_spec"]
    assert spec["ready"] is True and spec["fields"] == answers
    assert spec["job"] == "pricing" and spec["off_menu"] is False
    assert "start_job_study" in out["next"]                      # hand-off into the matched preset


def test_explicit_job_overrides_the_keyword_match(store):
    out = services.sharpen_question("What should I charge?", job="positioning", store=store)
    assert out["preset"]["id"] == "positioning"
    assert out["job_matches"] == [{"job": "positioning", "name": "Positioning",
                                   "score": None, "matched": ["explicit"]}]
    with pytest.raises(ValueError):
        services.sharpen_question("goal", job="nope", store=store)


def test_unmatched_goal_stays_off_menu_not_blocked(store):
    answers = {"decision": "d", "audience": "a", "comparator": "c", "success_signal": "s"}
    out = services.sharpen_question("Ein völlig anderes Thema", answers=answers, store=store)
    assert out["job_matches"] == [] and out["preset"] is None
    spec = out["study_spec"]
    assert spec["job"] is None and spec["off_menu"] is True and spec["ready"] is True
    assert "start_project" in out["next"]                        # the general engine still cooks it


def test_sharpen_validates_inputs(store):
    with pytest.raises(ValueError):
        services.sharpen_question("", store=store)
    with pytest.raises(ValueError):
        services.sharpen_question("goal", answers={"typo_field": "x"}, store=store)


# ----------------------------------------------------------------------------- preset → plan seeding

def test_start_job_study_seeds_the_plan_from_the_preset(store):
    out = services.start_job_study("positioning", "Positioning study",
                                   "Does our value land against the incumbent?", store=store)
    proj = out["project"]
    assert proj["job"] == "positioning" and proj["methodology"] == "double_diamond"
    plan = services.get_plan(proj["id"], store=store)
    assert plan["methodology"] == "double_diamond" and plan["job"] == "positioning"
    assert plan["tasks"], "the preset seeded a real plan"
    assert out["suggested_formats"] == ["council", "head_to_head", "red_team"]
    assert out["coverage"]["min_personas"] == 4
    assert "note" not in out                                     # on-menu framework → no off-menu note


def test_start_job_study_accepts_existing_icon(store):
    out = services.start_job_study("positioning", "Icon study",
                                   "Does our value land?", icon="positioning", store=store)
    assert out["project"]["icon"] == {"kind": "regular", "name": "positioning"}


def test_start_job_study_framework_is_swappable_never_enforced(store):
    out = services.start_job_study("positioning", "Off-menu", "goal",
                                   framework="dschool_micro", store=store)
    assert out["project"]["methodology"] == "dschool_micro"      # the engine cooked it anyway
    assert out["project"]["job"] == "positioning"
    assert "off the preset's menu" in out["note"]


def test_start_job_study_unknown_job_raises(store):
    with pytest.raises(ValueError):
        services.start_job_study("nope", "t", "g", store=store)


def test_job_study_feeds_the_coverage_check(store):
    """The stamped Job is exactly what assess_coverage(job=...) checks declared coverage against."""
    out = services.start_job_study("positioning", "Cov", "goal", store=store)
    cov = services.assess_coverage(out["project"]["id"], job=out["project"]["job"], store=store)
    assert cov["job"] == "positioning"
    assert cov["declared_coverage"]["min_personas"] == 4
    assert any(g["kind"] == "below_declared_min" for g in cov["gaps"])   # empty panel < declared 4


# ----------------------------------------------------------------------------- MCP + inspector surfaces

def test_mcp_tools_registered_with_next_hints():
    import asyncio
    from sonaloop.mcp_server import build_server, _env
    names = {t.name for t in asyncio.run(build_server().list_tools())}
    assert {"list_job_presets", "get_job_preset", "sharpen_question", "start_job_study"} <= names
    assert _env("sharpen_question", {}, 0.0)["next_recommended_tool"]["name"] == "start_job_study"
    assert _env("start_job_study", {}, 0.0)["next_recommended_tool"]["name"] == "assess_coverage"


def test_job_renders_in_the_inspector_plan_page(store):
    """The plan page shows the Job the study was seeded from, above the framework strip."""
    from starlette.testclient import TestClient
    from sonaloop import web

    out = services.start_job_study("positioning", "Render", "goal", store=store)
    html = TestClient(web.create_app()).get(f"/projects/{out['project']['id']}/plan").text
    assert "plan-fw-job" in html and "Positioning" in html
    assert "Double Diamond" in html                              # the framework strip still renders
