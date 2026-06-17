"""R1 — research-plan model + storage + plan.md render (spec/research-plan-engine.md §9 R1).

A hand-authored plan persists, round-trips, and renders a bucketed plan.md; buckets/capabilities
are validated by REFERENCE (no closed enum in code).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from sonaloop import methodology as M
from sonaloop import plan as P
from sonaloop import services, web


def _plan(pid="proj1"):
    return P.new_plan(pid, goal="How might we test the plan?", methodology="double_diamond_deep", tasks=[
        {"id": "frame1", "title": "Frame the inquiry", "bucket": "analyze", "capability": "frame",
         "intent": "understand before concluding", "plan_note": "read persona memory first"},
        {"id": "c1", "title": "Pain council", "bucket": "act", "capability": "explore",
         "consumes": ["frame1"], "produces": [{"kind": "council", "id": "council_abc"}]},
        {"id": "c2", "title": "Provider council", "bucket": "act", "capability": "explore",
         "consumes": ["frame1"], "produces": [{"kind": "council", "id": "council_def"}]},
        {"id": "v1", "title": "Key problems", "bucket": "verify", "capability": "synthesize",
         "consumes": ["c1", "c2"], "requires": {"min_inputs": 2, "gate_tag": "divergence_complete"}},
    ])


def test_plan_roundtrips_through_store(store):
    p = _plan()
    P.save_plan(p, store=store)
    got = P.get_plan("proj1", store=store)
    assert got is not None
    assert got["goal"] == "How might we test the plan?"
    assert [t["id"] for t in got["tasks"]] == ["frame1", "c1", "c2", "v1"]
    assert got["tasks"][1]["produces"][0] == {"kind": "council", "id": "council_abc"}
    # the verify task carries its gate
    v1 = next(t for t in got["tasks"] if t["id"] == "v1")
    assert v1["requires"]["min_inputs"] == 2 and v1["requires"]["gate_tag"] == "divergence_complete"


def test_ready_frontier_and_completion(store):
    p = _plan()
    ready = {t["id"] for t in P.ready_tasks(p)}
    assert ready == {"frame1"}                      # only the root frame is ready
    P.task(p, "frame1")["status"] = "done"
    assert {t["id"] for t in P.ready_tasks(p)} == {"c1", "c2"}   # both act councils unlock (branch)
    for t in p["tasks"]:
        t["status"] = "done"
    assert P.is_complete(p)


def test_render_plan_md_is_bucketed(store):
    md = P.render_plan_md(_plan())
    assert "# Research plan — How might we test the plan?" in md
    assert "## Next (ready)" in md
    for section in ("## Analyze", "## Act", "## Verify"):
        assert section in md, section
    assert "council:council_abc" in md          # evidence ref rendered
    assert "gate=divergence_complete" in md       # gate rendered
    # export via services
    services.save_plan(_plan(), store=store)
    assert "## Analyze" in services.export_plan_md("proj1", store=store)


def test_bad_plan_rejected(store):
    with pytest.raises(P.PlanError):                # missing bucket tag
        P.validate_plan({"project_id": "x", "tasks": [{"id": "a", "title": "A"}]})
    with pytest.raises(P.PlanError):                # consumes unknown
        P.validate_plan({"project_id": "x", "tasks": [
            {"id": "a", "bucket": "act"}, {"id": "b", "bucket": "act", "consumes": ["ghost"]}]})
    with pytest.raises(P.PlanError):                # cycle
        P.validate_plan({"project_id": "x", "tasks": [
            {"id": "a", "bucket": "act", "consumes": ["b"]}, {"id": "b", "bucket": "act", "consumes": ["a"]}]})


def test_no_hardcoded_bucket_or_capability_set():
    """R1 acceptance: the plan engine must not encode a closed bucket/capability/kind vocabulary."""
    src = Path(P.__file__).read_text()
    for banned in ("BUCKETS =", "CAPABILITIES =", "KINDS =", "ALLOWED_BUCKETS", "VALID_CAPABILITIES"):
        assert banned not in src, banned
    # an invented bucket + capability + evidence kind validate fine
    P.validate_plan({"project_id": "x", "tasks": [
        {"id": "a", "bucket": "ponder", "capability": "divine", "produces": [{"kind": "omen", "id": "o1"}]}]})


# --------------------------------------------------------------------------- R2: seeding

def test_methodology_seeds_plan_with_gated_verify_tasks(store):
    proj = services.start_project("Deep", "How might we test seeding?", "double_diamond_deep",
                                  persona_ids=["p1"], store=store)
    plan = services.get_plan(proj["id"], store=store)
    by = {t["id"]: t for t in plan["tasks"]}
    # a frame (analyze) per fan step, a verify per decide step
    assert by["frame__discover"]["bucket"] == "analyze" and by["frame__discover"]["consumes"] == []
    assert by["verify__define"]["bucket"] == "verify"
    assert by["verify__define"]["requires"]["min_inputs"] == 2
    assert by["verify__define"]["requires"]["gate_tag"] == "divergence_complete"
    # session gates carried from the constellation (lofi at lofi_select, midfi at deliver)
    assert by["verify__lofi_select"]["requires"]["session_of_tags"] == ["lofi"]
    assert by["verify__deliver"]["requires"]["session_of_tags"] == ["midfi"]
    # the DAG threads frame -> verify -> frame -> ...
    assert by["verify__define"]["consumes"] == ["frame__discover"]
    assert by["frame__ideate"]["consumes"] == ["verify__define"]
    # only the root frame is ready at the start
    assert {t["id"] for t in services.ready_tasks(plan)} == {"frame__discover"}


def test_freeform_seeds_single_root_frame(store):
    proj = services.start_project("Freeform", "What do users want?", None,
                                  persona_ids=["p1"], store=store)
    plan = services.get_plan(proj["id"], store=store)
    assert len(plan["tasks"]) == 1
    t = plan["tasks"][0]
    assert t["bucket"] == "analyze" and t["capability"] == "frame" and t["consumes"] == []
    assert "## Analyze" in services.export_plan_md(proj["id"], store=store)


# ------------------------------------------------- R2b: non-alternating constellation shapes
# The seeder maps EVERY constellation edge 1:1 onto a seeded edge — same-type ones (fan→fan,
# decide→decide) included, so a non-alternating DAG keeps its ordering instead of silently
# dropping edges.

def _seed(steps):
    """Validate + seed a throwaway constellation (no registry needed for shape tests)."""
    spec = {"key": "shape", "name": "Shape", "description": "d", "when_to_use": "w", "steps": steps}
    M.validate_methodology_spec(spec)
    return P.seed_plan_from_methodology("proj", "g", M._normalize_spec(spec))


def _edges(plan):
    return {t["id"]: t["consumes"] for t in plan["tasks"]}


def test_builtin_methodologies_seed_exactly_as_before():
    """Regression pin (id/consumes/loop_back captured from main BEFORE the same-type-edge fix):
    the four alternating built-ins must seed byte-identically — for them every edge is
    cross-type, so the 1:1 edge mapping reproduces the old wiring by construction."""
    pinned = {
        "double_diamond": [
            ("frame__discover", [], ""), ("verify__define", ["frame__discover"], ""),
            ("frame__develop", ["verify__define"], ""),
            ("verify__deliver", ["frame__develop"], "frame__develop")],
        "double_diamond_deep": [
            ("frame__discover", [], ""), ("verify__define", ["frame__discover"], ""),
            ("frame__ideate", ["verify__define"], ""),
            ("verify__lofi_select", ["frame__ideate"], ""),
            ("frame__refine", ["verify__lofi_select"], ""),
            ("verify__deliver", ["frame__refine"], "frame__refine")],
        "dschool_micro": [
            ("frame__understand_observe", [], ""),
            ("verify__define_pov", ["frame__understand_observe"], ""),
            ("frame__ideate", ["verify__define_pov"], ""),
            ("verify__prototype_test", ["frame__ideate"], "frame__ideate")],
        "lean_jtbd": [
            ("frame__problem_explore", [], ""),
            ("verify__problem_pick", ["frame__problem_explore"], ""),
            ("frame__solution_explore", ["verify__problem_pick"], ""),
            ("verify__validate", ["frame__solution_explore"], "frame__solution_explore")],
    }
    specs = M._load_builtin_specs()
    # The pinned built-ins must still ship and seed byte-identically; newer methodologies may be
    # added alongside them (they are not part of this regression pin).
    assert set(pinned) <= set(specs)
    for key, expected in pinned.items():
        p = P.seed_plan_from_methodology("proj", "g", specs[key])
        assert [(t["id"], t["consumes"], t["loop_back"]) for t in p["tasks"]] == expected, key


def test_seeder_preserves_fan_to_fan_edge():
    """Design-Sprint-like Map→Sketch (two consecutive fans): the fan→fan edge survives as
    frame__sketch consumes frame__map — NOT two parallel roots."""
    plan = _seed([
        {"id": "map", "name": "Map", "tags": ["explore"]},
        {"id": "sketch", "name": "Sketch", "tags": ["explore"], "consumes": ["map"]},
        {"id": "decide", "name": "Decide", "tags": ["decide"], "consumes": ["sketch"],
         "requires": {"min_inputs": 2, "gate_tag": "divergence_complete"}},
    ])
    assert _edges(plan) == {"frame__map": [], "frame__sketch": ["frame__map"],
                            "verify__decide": ["frame__sketch"]}
    assert {t["id"] for t in P.ready_tasks(plan)} == {"frame__map"}   # ordering preserved


def test_seeder_preserves_decide_to_decide_edge():
    """A decide→decide refinement chain: verify__pick consumes verify__shortlist."""
    plan = _seed([
        {"id": "scan", "name": "Scan", "tags": ["explore"]},
        {"id": "shortlist", "name": "Shortlist", "tags": ["decide"], "consumes": ["scan"],
         "requires": {"min_inputs": 2, "gate_tag": "scanned"}},
        {"id": "pick", "name": "Pick", "tags": ["decide"], "consumes": ["shortlist"],
         "requires": {"min_inputs": 1, "gate_tag": "picked"}},
    ])
    assert _edges(plan)["verify__pick"] == ["verify__shortlist"]
    assert {t["id"] for t in P.ready_tasks(plan)} == {"frame__scan"}


def _diamond_steps():
    # users → {pov (decide), sketch (fan)} → converge: one fan→fan edge plus a MIXED
    # multi-consume list on the join (verify__pov same-type + frame__sketch cross-type).
    return [
        {"id": "users", "name": "Users", "tags": ["explore"]},
        {"id": "pov", "name": "PoV", "tags": ["decide"], "consumes": ["users"],
         "requires": {"min_inputs": 1, "gate_tag": "pov_clear"}},
        {"id": "sketch", "name": "Sketch", "tags": ["explore"], "consumes": ["users"]},
        {"id": "converge", "name": "Converge", "tags": ["decide"], "consumes": ["pov", "sketch"],
         "requires": {"min_inputs": 1, "gate_tag": "converged"}},
    ]


def test_seeder_preserves_multi_consume_diamond():
    plan = _seed(_diamond_steps())
    assert _edges(plan) == {"frame__users": [], "verify__pov": ["frame__users"],
                            "frame__sketch": ["frame__users"],
                            "verify__converge": ["verify__pov", "frame__sketch"]}


def test_seeder_preserves_multi_root_spec():
    """Two roots joined by one decide: both roots stay roots, the join keeps both edges."""
    plan = _seed([
        {"id": "users", "name": "Users", "tags": ["explore"]},
        {"id": "market", "name": "Market", "tags": ["explore"]},
        {"id": "pov", "name": "PoV", "tags": ["decide"], "consumes": ["users", "market"],
         "requires": {"min_inputs": 2, "gate_tag": "g"}},
    ])
    assert _edges(plan) == {"frame__users": [], "frame__market": [],
                            "verify__pov": ["frame__users", "frame__market"]}
    assert {t["id"] for t in P.ready_tasks(plan)} == {"frame__users", "frame__market"}


def test_same_type_edges_do_not_count_toward_verify_breadth(store):
    """The new edges must not leak into verify gating: a frame sibling sharing the verify's
    consumed frame produces only `frame` refs, and an upstream verify is excluded by bucket —
    neither counts as an act angle toward min_inputs."""
    plan = _seed(_diamond_steps())
    plan["project_id"] = "projx"
    P.save_plan(plan, store=store)
    # discharge frame__sketch — it shares frame__users with verify__pov's fan
    P.record_frame("projx", "frame__sketch", ["q?"], memory_refs=["m1"], store=store)
    # give verify__pov a non-frame produce — verify__converge consumes it but must not count it
    P.link_evidence("projx", "verify__pov", {"kind": "synthesis", "id": "s1"}, store=store)
    plan = P.get_plan("projx", store=store)
    for vid in ("verify__pov", "verify__converge"):
        unmet = P.verify_unmet(plan, P.task(plan, vid), store)
        assert any("(have 0)" in u for u in unmet), (vid, unmet)


def test_two_verifies_consuming_one_frame_share_the_fan():
    """Documented `_fan_tasks` behavior: a verify's fan is scoped by SHARED consumed frames, so
    two verify tasks consuming the same frame each see (and fully count) the same act tasks —
    the evidence is shared, not split between them."""
    plan = P.new_plan("proj", tasks=[
        {"id": "f", "bucket": "analyze", "capability": "frame"},
        {"id": "a1", "bucket": "act", "consumes": ["f"], "produces": [{"kind": "council", "id": "c1"}]},
        {"id": "v1", "bucket": "verify", "consumes": ["f"], "requires": {"min_inputs": 1, "gate_tag": "g1"}},
        {"id": "v2", "bucket": "verify", "consumes": ["f"], "requires": {"min_inputs": 1, "gate_tag": "g2"}},
    ])
    for vid in ("v1", "v2"):
        assert [t["id"] for t in P._fan_tasks(plan, P.task(plan, vid))] == ["a1"]


# --------------------------------------------------------------------------- R3: frame

def test_act_blocked_until_frame_discharged(store):
    proj = services.start_project("Deep", "hmw?", "double_diamond_deep", persona_ids=["p1"], store=store)
    pid = proj["id"]
    # orchestrator adds an act council under the discover frame
    services.add_task(pid, "act", "explore", "Pain council", consumes=["frame__discover"], store=store)
    plan = services.get_plan(pid, store=store)
    ready = {t["id"] for t in services.ready_tasks(plan)}
    assert "frame__discover" in ready and not any(t.startswith("act__") for t in ready)  # act blocked

    # frame requires >=1 question AND >=1 memory ref (can't silently skip)
    import pytest
    with pytest.raises(services.PlanError):
        services.record_frame(pid, "frame__discover", ["q?"], memory_refs=[], store=store)
    with pytest.raises(services.PlanError):
        services.record_frame(pid, "frame__discover", [], memory_refs=["fact:1"], store=store)

    # a minimal honest frame discharges it; act now unlocks
    services.record_frame(pid, "frame__discover",
                          questions=["Welche Versicherungen haben sie schon?", "Vorsorge-Bewusstsein?"],
                          hypotheses=["KFZ-Moment ist Pflichtakt"], memory_refs=["persona:aylin/day:2026-05-20"],
                          store=store)
    plan = services.get_plan(pid, store=store)
    fr = next(t for t in plan["tasks"] if t["id"] == "frame__discover")
    assert fr["status"] == "done" and fr["frame"]["memory_refs"] == ["persona:aylin/day:2026-05-20"]
    assert fr["produces"] == [{"kind": "frame", "id": "frame__discover"}]
    ready = {t["id"] for t in services.ready_tasks(plan)}
    assert any(t.startswith("act__") for t in ready)   # the act council is now ready


# --------------------------------------------------------------------------- R4: router + gates

def test_verify_gated_until_breadth_and_judgment(store):
    proj = services.start_project("Deep", "hmw?", "double_diamond_deep", persona_ids=["p1"], store=store)
    pid = proj["id"]
    services.record_frame(pid, "frame__discover", ["q1?", "q2?"], memory_refs=["persona:p1/day:1"], store=store)
    # one act council so far
    a1 = services.add_task(pid, "act", "explore", "Council A", consumes=["frame__discover"], store=store)
    services.link_evidence(pid, a1["id"], {"kind": "council", "id": "c1"}, store=store)

    # verify is on the frontier (frame done) but GATED: needs >=2 fan evidence + a gate judgment
    b = services.brief_next(pid, store=store)
    assert "verify__define" in b["ready"]
    import pytest
    with pytest.raises(services.PlanError) as e:
        services.complete_task(pid, "verify__define", store=store)
    assert e.value.code == "GATE_UNMET"

    # add the second council → breadth ok, but still no judgment
    a2 = services.add_task(pid, "act", "explore", "Council B", consumes=["frame__discover"], store=store)
    services.link_evidence(pid, a2["id"], {"kind": "council", "id": "c2"}, store=store)
    with pytest.raises(services.PlanError):
        services.complete_task(pid, "verify__define", store=store)   # missing divergence_complete

    # record the evidence-backed gate judgment → verify can complete
    services.record_judgment(pid, "verify__define", "divergence_complete", True,
                             "two distinct pain clusters; saturating", evidence_refs=["c1", "c2"], store=store)
    services.complete_task(pid, "verify__define", store=store)
    plan = services.get_plan(pid, store=store)
    assert next(t for t in plan["tasks"] if t["id"] == "verify__define")["status"] == "done"
    # next frame unlocks
    assert "frame__ideate" in {t["id"] for t in services.ready_tasks(plan)}


def test_brief_next_dispatches_to_plan(store):
    proj = services.start_project("F", "what?", None, persona_ids=["p1"], store=store)
    b = services.brief_next(proj["id"], store=store)
    assert b["task"] == "frame__root" and b["bucket"] == "analyze" and not b["complete"]


# --------------------------------------------------- R4b: host-driven iteration rounds (loop_back)

def _seed_dschool_done_through_test(store, pid="loop_proj"):
    """A seeded dschool_micro plan with every task done — the state right after the looping verify
    (verify__prototype_test, loop_back → frame__ideate) completed its first round."""
    spec = M._load_builtin_specs()["dschool_micro"]
    plan = P.seed_plan_from_methodology(pid, "hmw loop?", spec)
    for t in plan["tasks"]:
        t["status"] = "done"
    P.save_plan(plan, store=store)
    return plan


def test_iterate_task_opens_a_coherent_second_round(store):
    _seed_dschool_done_through_test(store)
    rec = P.iterate_task("loop_proj", "verify__prototype_test", note="probands rejected the flow", store=store)
    assert rec["round"] == 2 and rec["entry"] == "frame__ideate__r2"
    assert rec["tasks"] == ["frame__ideate__r2", "verify__prototype_test__r2"]
    plan = P.get_plan("loop_proj", store=store)            # re-validates: still a DAG
    by = {t["id"]: t for t in plan["tasks"]}
    # ordering preserved: the round's entry consumes the DONE looping verify (plus the original edge)
    assert by["frame__ideate__r2"]["consumes"] == ["verify__define_pov", "verify__prototype_test"]
    assert by["verify__prototype_test__r2"]["consumes"] == ["frame__ideate__r2"]
    # the cloned verify loops back at the CLONED target, so the next iteration works too
    assert by["verify__prototype_test__r2"]["loop_back"] == "frame__ideate__r2"
    # statuses reset, evidence/frames not carried over, gates preserved, note on the entry
    for tid in rec["tasks"]:
        assert by[tid]["status"] == "todo" and by[tid]["produces"] == [] and by[tid]["frame"] is None
    assert by["verify__prototype_test__r2"]["requires"]["min_inputs"] == 2
    assert by["verify__prototype_test__r2"]["requires"]["session_of_tags"] == ["prototype"]
    assert by["frame__ideate__r2"]["plan_note"] == "probands rejected the flow"
    # the original looping verify stays done (history); the new round becomes ready in order
    assert by["verify__prototype_test"]["status"] == "done"
    assert {t["id"] for t in P.ready_tasks(plan)} == {"frame__ideate__r2"}
    P.record_frame("loop_proj", "frame__ideate__r2", ["q?"], memory_refs=["m1"], store=store)
    plan = P.get_plan("loop_proj", store=store)
    assert {t["id"] for t in P.ready_tasks(plan)} == {"verify__prototype_test__r2"}


def test_iterate_task_without_loop_back_raises_stable_code(store):
    _seed_dschool_done_through_test(store, pid="loop_proj2")
    with pytest.raises(P.PlanError) as e:
        P.iterate_task("loop_proj2", "frame__ideate", store=store)
    assert e.value.code == "NO_LOOP_BACK"
    with pytest.raises(P.PlanError) as e2:                  # unknown task keeps its existing code
        P.iterate_task("loop_proj2", "ghost", store=store)
    assert e2.value.code == "BAD_TASK"


def test_iterate_task_requires_done_or_ready(store):
    spec = M._load_builtin_specs()["dschool_micro"]
    P.save_plan(P.seed_plan_from_methodology("loop_proj3", "g", spec), store=store)
    with pytest.raises(P.PlanError) as e:                   # blocked deep in a fresh plan
        P.iterate_task("loop_proj3", "verify__prototype_test", store=store)
    assert e.value.code == "TASK_NOT_READY"


def test_repeated_iteration_yields_r3_and_stays_acyclic(store):
    _seed_dschool_done_through_test(store, pid="loop_proj4")
    P.iterate_task("loop_proj4", "verify__prototype_test", store=store)
    plan = P.get_plan("loop_proj4", store=store)
    for tid in ("frame__ideate__r2", "verify__prototype_test__r2"):
        P.task(plan, tid)["status"] = "done"
    P.save_plan(plan, store=store)
    rec = P.iterate_task("loop_proj4", "verify__prototype_test__r2", store=store)
    assert rec["round"] == 3 and rec["tasks"] == ["frame__ideate__r3", "verify__prototype_test__r3"]
    plan = P.get_plan("loop_proj4", store=store)            # validate_plan would raise on a cycle
    by = {t["id"]: t for t in plan["tasks"]}
    assert by["frame__ideate__r3"]["consumes"] == ["verify__define_pov", "verify__prototype_test__r2"]
    assert by["verify__prototype_test__r3"]["loop_back"] == "frame__ideate__r3"
    assert {t["id"] for t in P.ready_tasks(plan)} == {"frame__ideate__r3"}


def test_render_plan_md_renders_a_looped_plan(store):
    _seed_dschool_done_through_test(store, pid="loop_proj5")
    P.iterate_task("loop_proj5", "verify__prototype_test", note="loop", store=store)
    md = P.render_plan_md(P.get_plan("loop_proj5", store=store))
    assert "frame__ideate__r2" in md and "verify__prototype_test__r2" in md


def test_brief_next_surfaces_iterate_option_on_loop_back_verify(store):
    spec = M._load_builtin_specs()["dschool_micro"]
    plan = P.seed_plan_from_methodology("loop_proj6", "g", spec)
    for t in plan["tasks"]:
        if t["id"] != "verify__prototype_test":
            t["status"] = "done"
    P.save_plan(plan, store=store)
    b = services.brief_next("loop_proj6", store=store)
    assert b["task"] == "verify__prototype_test" and "iterate_task" in b["instructions"]
    n = services.next_action("loop_proj6", store=store)
    assert "iterate_task" in n["verify"]["guidance"]


# --------------------------------------------------------------------------- R5: evidence graph

def _council(store, cid):
    store.insert_council_session({"id": cid, "created_at": f"2026-06-0{cid[-1]}T00:00:00+00:00",
        "prompt": f"Council {cid}", "persona_ids": ["p1"], "turns": [], "votes": [], "proposal": "",
        "summary": "", "exec_summary": "e", "selection_reason": "x"})
    return cid


def test_heterogeneous_graph_councils_and_synthesis(store):
    proj = services.start_project("Deep", "hmw?", "double_diamond_deep", persona_ids=["p1"], store=store)
    pid = proj["id"]
    services.record_frame(pid, "frame__discover", ["q?"], memory_refs=["m1"], store=store)
    # three real act councils as first-class evidence (NOT wrapped in syntheses)
    for i in (1, 2, 3):
        _council(store, f"cc{i}")
        a = services.add_task(pid, "act", "explore", f"Council {i}", consumes=["frame__discover"], store=store)
        services.link_evidence(pid, a["id"], {"kind": "council", "id": f"cc{i}"}, store=store)
    # one optional verify synthesis consolidating them
    syn = services.record_synthesis("Key problems", "hmw", ["cc1", "cc2", "cc3"],
                                    {"gesamtbild": "clustered"}, store=store)
    services.link_evidence(pid, "verify__define", {"kind": "synthesis", "id": syn["id"]}, store=store)

    g = services.get_project_graph(pid, store=store)
    kinds = sorted(n["kind"] for n in g["nodes"])
    assert kinds == ["council", "council", "council", "synthesis"]   # 3 councils + 1 synthesis, not 3 wrappers
    # the synthesis consolidates all three councils (refines edges)
    refines = [(e["from_study"], e["to_study"]) for e in g["edges"] if e["type"] == "refines"]
    assert (f"council:cc1", f"synthesis:{syn['id']}") in refines
    assert len([e for e in refines if e[1] == f"synthesis:{syn['id']}"]) == 3
    # colors come from data (present(kind)), not code
    council_node = next(n for n in g["nodes"] if n["kind"] == "council")
    assert council_node["color"] == "#6b7cff"          # from suggestions/evidence_kinds.json


def test_no_hardcoded_evidence_kind_literal_in_web():
    from pathlib import Path
    src = "\n".join(f.read_text() for f in sorted(Path(web.__file__).parent.glob("*.py")))
    for lit in ('== "council"', '== "synthesis"', '== "frame"', '{"council"', '{"synthesis"',
                '"kind": "council"', '"kind": "synthesis"'):
        assert lit not in src, f"web.py must not hardcode evidence-kind literal {lit}"


# --------------------------------------------------------------------------- R6: progress

def test_assess_progress_is_evidence_cited_no_metric(store):
    proj = services.start_project("Deep", "Win young KFZ buyers for LV?", "double_diamond_deep",
                                  persona_ids=["p1"], store=store)
    pid = proj["id"]
    services.record_frame(pid, "frame__discover", ["q?"], memory_refs=["m1"], store=store)
    _council(store, "cx1")
    a = services.add_task(pid, "act", "explore", "Council", consumes=["frame__discover"], store=store)
    services.link_evidence(pid, a["id"], {"kind": "council", "id": "cx1"}, store=store)
    import pytest
    with pytest.raises(services.PlanError):              # must cite evidence
        services.assess_progress(pid, "verify__deliver", "we are closer", [], store=store)
    rec = services.assess_progress(pid, "verify__deliver",
                                   "Problem space framed; one pain council in. The surprising core "
                                   "segment is emerging.", evidence_refs=["cx1"], delta="näher",
                                   store=store)
    assert rec["delta"] == "näher" and rec["evidence_refs"] == ["cx1"]
    assert rec["coverage"]["evidence_by_kind"]["council"] == 1   # descriptive count, not a score
    plan = services.get_plan(pid, store=store)
    assert plan["progress"][0]["goal"] == "Win young KFZ buyers for LV?"


def test_no_hardcoded_progress_metric_threshold():
    from pathlib import Path
    import re
    src = Path(P.__file__).read_text()
    # the coverage/progress code must not compare a count to a hardcoded score threshold
    fn = src[src.index("def assess_progress"):src.index("def brief_next")]
    assert not re.search(r">=\s*0\.\d|score\s*=", fn), "no hardcoded progress score/threshold allowed"


# --------------------------------------------------------------------------- R8: migration + gate

def test_grep_gate_no_hardcoded_bucket_kind_vocabulary():
    """R8: no closed bucket/capability/kind VOCABULARY in the engine, and no kind PRESENTATION
    literal in the UI (kind presentation comes from suggestions/evidence_kinds.json via present()).
    (Storage dispatch — which table a council vs synthesis lives in — is legitimate, not vocabulary.)"""
    from pathlib import Path
    psrc = Path(P.__file__).read_text()
    for banned in ("BUCKETS =", "CAPABILITIES =", "KINDS ="):
        assert banned not in psrc, banned
    wsrc = "\n".join(f.read_text() for f in sorted(Path(web.__file__).parent.glob("*.py")))
    for lit in ('== "council"', '== "synthesis"', '{"council"', '{"synthesis"',
                '"kind": "council"', '"kind": "synthesis"'):
        assert lit not in wsrc, f"web.py must not hardcode evidence-kind literal {lit}"


# --------------------------------------------------------------------------- GAP-5: groundedness

def test_browser_log_retained_past_close_for_grounding():
    """GAP-5: a session's observed-state log survives close() so a proband reaction recorded AFTER
    closing the browser still verifies (the clean drive→close→record order no longer loses evidence)."""
    from sonaloop import browser
    browser._RETAINED_LOGS.clear()
    sid = "psession_test_retain"
    browser._retain_log(sid, [{"kind": "snapshot", "refs": ["r1"], "text": "Du hast die Hand drauf"}])
    log = browser.session_log(sid)            # not in _SESSIONS, but retained
    assert log and log[0]["refs"] == ["r1"]


def test_ungrounded_proband_session_warns_and_blocks_gate(store, tmp_path, monkeypatch):
    """GAP-5: an unverified proband session (no observed-state log) is flagged on write AND does not
    satisfy a session_of_tags gate when the harness can verify; a grounded session clears it."""
    import sonaloop.prototypes as P
    monkeypatch.setattr(P, "prototypes_dir", lambda: tmp_path / "protos")
    from sonaloop import plan as PL, services, browser
    monkeypatch.setattr(browser, "available", lambda: True)
    proj = services.start_project("G", "hmw?", None, persona_ids=["p1"], store=store)
    pid = proj["id"]
    concept = {"title": "P", "summary": "", "start": "a", "screens": [
        {"id": "a", "title": "A", "elements": [{"kind": "text", "id": "t", "label": "x"}]}]}
    art = services.scaffold_artifact("g5-proto", "G5", concept, type="prototype", tags=["lofi"],
                                     project_id=pid, store=store)
    # record a session with a session_id that has NO browser log -> grounded False + warning
    out = services.record_prototype_session("p1", art["id"], "no-such-session", "2026-06-05",
        {"summary": "ok", "observed_state_refs": ["x"], "verdict": "ok"}, store=store)
    assert out["grounded_verified"] is False
    assert any("UNVERIFIED_SESSION" in w for w in out.get("warnings", []))
    # a verify task requiring a session of `lofi` is blocked while only the ungrounded session exists
    vtask = {"id": "v", "bucket": "verify", "capability": "decide", "consumes": [],
             "requires": {"min_inputs": 0, "session_of_tags": ["lofi"]}}
    plan = {"project_id": pid, "tasks": [vtask]}
    PL.validate_plan(plan)
    unmet = PL.verify_unmet(plan, PL.task(plan, "v"), store)
    assert any("GROUNDED" in u for u in unmet), unmet
    # a verified session of the same artifact clears the groundedness gap
    store.insert_prototype_session({"id": "ps_grounded", "persona_id": "p1", "prototype_id": art["id"],
        "session_id": "s", "date": "2026-06-05", "reaction": {}, "observed_state_refs": ["x"],
        "created_at": "2026-06-05T00:00:00+00:00", "grounded_verified": True})
    unmet2 = PL.verify_unmet(plan, PL.task(plan, "v"), store)
    assert not any("GROUNDED" in u for u in unmet2), unmet2


def test_usability_session_satisfies_session_of_tag_gate(store, tmp_path, monkeypatch):
    """The current Session primitive is usability_sessions. A session_of_tags gate must count a
    usability session whose subject is a tagged prototype in the project."""
    import sonaloop.prototypes as proto_mod
    monkeypatch.setattr(proto_mod, "prototypes_dir", lambda: tmp_path / "protos")
    from sonaloop import browser
    monkeypatch.setattr(browser, "available", lambda: False)
    proj = services.start_project("G", "hmw?", None, persona_ids=["p1"], store=store)
    pid = proj["id"]
    concept = {"title": "P", "summary": "", "start": "a", "screens": [
        {"id": "a", "title": "A", "elements": [{"kind": "text", "id": "t", "label": "x"}]}]}
    art = services.scaffold_artifact("session-gate-proto", "Gate proto", concept, type="prototype",
                                     tags=["lofi"], project_id=pid, store=store)
    services.record_usability_session("p1", {"kind": "prototype", "id": art["id"], "label": "Gate proto"},
        "prototype", "2026-06-05",
        [{"index": 0, "action": {"type": "look", "target": "screen"},
          "state": {"screen": "A"}, "friction": {"level": "none", "note": ""},
          "verdict": {"would_continue": True, "reason": "clear"}}],
        {"completed": True, "summary": "used it", "predicted_behaviors": []},
        project_id=pid, store=store)
    vtask = {"id": "v", "bucket": "verify", "capability": "decide", "consumes": [],
             "requires": {"min_inputs": 0, "session_of_tags": ["lofi"]}}
    plan = {"project_id": pid, "tasks": [vtask]}
    P.validate_plan(plan)
    assert not P.verify_unmet(plan, P.task(plan, "v"), store)


def test_next_action_act_surfaces_artifact_palette_and_divergence_nudges(store):
    """GAP-2/SPEC-A: an act step surfaces the artifact archetype PALETTE (from data, incl. the
    interactive `model`) + methodology-agnostic divergence nudges (diversify KIND, a dark-horse,
    a disconfirmation council) — so concept breadth is reliable, not luck of a disciplined agent."""
    proj = services.start_project("G", "hmw?", None, persona_ids=["p1"], store=store)
    pid = proj["id"]
    services.record_frame(pid, "frame__root", ["q?"], memory_refs=["m1"], store=store)
    services.add_task(pid, "act", "explore", "angle", consumes=["frame__root"], store=store)
    act = services.next_action(pid, store=store)["act"]
    tags = {p["tag"] for p in act["artifact_palette"]}
    assert {"flow", "comparison", "model"} <= tags          # varied non-form archetypes, incl. model
    nudges = " ".join(act["divergence"]).lower()
    assert "dark-horse" in nudges and "disconfirmation" in nudges and "model" in nudges


def test_next_action_act_surfaces_ideation_lenses_for_innovation(store):
    """Innovation: an act step surfaces data-driven creativity lenses (analogy, make-the-invisible-
    EXPERIENCEABLE→simulation, reversal, …) so ideation pushes for non-obvious concepts, not tweaks."""
    proj = services.start_project("G", "hmw?", None, persona_ids=["p1"], store=store)
    pid = proj["id"]
    services.record_frame(pid, "frame__root", ["q?"], memory_refs=["m1"], store=store)
    services.add_task(pid, "act", "ideate", "ideas", consumes=["frame__root"], store=store)
    act = services.next_action(pid, store=store)["act"]
    lenses = {l["tag"] for l in act["ideation_lenses"]}
    assert {"analogy", "experienceable", "reversal"} <= lenses
    exp = next(l for l in act["ideation_lenses"] if l["tag"] == "experienceable")
    assert "model" in exp["prompt"].lower() or "simulation" in exp["prompt"].lower()


def test_assess_project_surfaces_novelty_signal(store, tmp_path, monkeypatch):
    """Innovation reliability: assess_project reports concept-KIND diversity + whether an interactive
    model exists, and flags a narrow (forms-only) space so a run can push for a bolder concept."""
    import sonaloop.prototypes as PP
    monkeypatch.setattr(PP, "prototypes_dir", lambda: tmp_path / "p")
    proj = services.start_project("G", "hmw?", None, persona_ids=["p1"], store=store)
    pid = proj["id"]
    concept = {"title": "T", "start": "a", "screens": [{"id": "a", "title": "A", "elements": [
        {"kind": "text", "id": "t", "label": "x"}]}]}
    services.scaffold_artifact("only-form", "F", concept, type="survey", tags=["lofi"], project_id=pid, store=store)
    n = services.assess_project(pid, store=store)["novelty"]
    assert n["has_interactive_model"] is False and n["hint"].startswith("narrow")
    services.scaffold_artifact("a-model", "M", concept, type="model", tags=["lofi"], project_id=pid, store=store)
    n2 = services.assess_project(pid, store=store)["novelty"]
    assert n2["has_interactive_model"] is True and n2["hint"] == "diverse"


def test_assess_project_finish_readiness_gate(store, tmp_path, monkeypatch):
    """A run must not stop at 'gates passed'. assess_project reports FINISH readiness (organized +
    concluded + handed-off); when the plan is complete but unfinished, the recommendation is 'finish'."""
    import sonaloop.prototypes as PP
    monkeypatch.setattr(PP, "prototypes_dir", lambda: tmp_path / "p")
    proj = services.start_project("G", "hmw?", None, persona_ids=["p1"], store=store)
    pid = proj["id"]
    services.record_frame(pid, "frame__root", ["q?"], memory_refs=["m1"], store=store)  # completes it -> plan complete
    concept = {"title": "T", "start": "a", "screens": [{"id": "a", "title": "A", "elements": [
        {"kind": "text", "id": "t", "label": "x"}]}]}
    services.scaffold_artifact("p", "P", concept, type="prototype", tags=["lofi"], project_id=pid, store=store)  # substantial
    a = services.assess_project(pid, store=store)
    assert a["complete"] is True and a["recommendation"] == "finish"
    assert a["finish"]["organized"] is False and a["finish"]["finished"] is False
    assert any("organized" in g for g in a["gaps"])


def test_completeness_critic_surfaces_gaps_and_refuses_dishonest_pass(store):
    """ESV2: brief_completeness_critic computes concrete `missing` candidates (un-prototyped concepts,
    un-sampled segments via OD-3 concept notes); record_completeness_critic refuses a passed=true that
    still lists missing or has a sub-threshold rubric dim (honesty gate)."""
    import pytest
    proj = services.start_project("ESV2", "hmw?", None, persona_ids=[], store=store)
    pid = proj["id"]
    services.create_note(pid, "a bold concept", "Dark-horse", kind="concept",
                         data={"lens": "reversal", "artifact_kind": "flow", "prototype_id": None}, store=store)
    b = services.brief_completeness_critic(pid, store=store)
    assert "breadth_candidates" in b["frame"] and "rubric" in b["frame"]
    assert b["frame"]["breadth_candidates"]["concepts_not_prototyped"] == ["Dark-horse"]
    with pytest.raises(ValueError):                               # can't pass with open missing
        services.record_completeness_critic(pid, {"passed": True, "missing": [{"kind": "concept", "what": "x"}],
                                                  "scores": {}}, store=store)
    with pytest.raises(ValueError):                               # can't pass with a sub-threshold dim
        services.record_completeness_critic(pid, {"passed": True, "missing": [],
                                                  "scores": {"exploration_depth": 1}}, store=store)
    rec = services.record_completeness_critic(pid, {"passed": False, "missing": [
        {"kind": "concept", "what": "build the dark-horse", "suggested_action": "scaffold + test it"}],
        "scores": {"exploration_depth": 3}, "rationale": "thin"}, store=store)
    assert rec["passed"] is False and rec["missing"][0]["kind"] == "concept"
    # once the idea note is marked built, it drops out of the gap
    note = [n for n in services.list_notes(pid, store=store) if (n.get("data") or {}).get("artifact_kind")][0]
    services.set_note_data(note["id"], {"prototype_id": "prototype_x"}, store=store)
    b2 = services.brief_completeness_critic(pid, store=store)
    assert b2["frame"]["breadth_candidates"]["concepts_not_prototyped"] == []


def test_resumable_run_object_and_keyed_session(store, tmp_path, monkeypatch):
    """ESV3: keyed prototype sessions upsert idempotently (same id); the run object journals steps +
    resumes (start_run with the same run_id returns the existing journal, not a fresh run)."""
    import sonaloop.prototypes as PP
    monkeypatch.setattr(PP, "prototypes_dir", lambda: tmp_path / "p")
    proj = services.start_project("ESV3", "hmw?", None, persona_ids=["p1"], store=store)
    pid = proj["id"]
    concept = {"title": "T", "start": "a", "screens": [{"id": "a", "title": "A", "elements": [
        {"kind": "text", "id": "t", "label": "x"}]}]}
    art = services.scaffold_artifact("a", "A", concept, type="prototype", tags=["lofi"], project_id=pid, store=store)
    k = "run1:proto:p1"
    r1 = services.record_prototype_session("p1", art["id"], "s", "2026-06-05",
        {"summary": "ok", "observed_state_refs": ["x"], "verdict": "ok"}, key=k, store=store)
    r2 = services.record_prototype_session("p1", art["id"], "s", "2026-06-05",
        {"summary": "ok2", "observed_state_refs": ["x"], "verdict": "ok"}, key=k, store=store)
    assert r1["prototype_session"]["id"] == r2["prototype_session"]["id"]          # idempotent upsert
    assert len([x for x in store.list_prototype_sessions() if x["prototype_id"] == art["id"]]) == 1
    # run object
    run = services.start_run(pid, budget=10, store=store)
    rid = run["run_id"]
    services.checkpoint_step(rid, {"task_id": "frame__root", "bucket": "analyze", "key": services.run_key(rid, "frame__root"),
                                   "evidence": [{"kind": "frame", "id": "frame__root"}], "summary": "framed"}, store=store)
    j = services.run_journal(rid, store=store)
    assert j["cursor"] == 1 and j["steps"][0]["task_id"] == "frame__root"
    assert services.start_run(pid, run_id=rid, store=store)["cursor"] == 1          # resume returns the journal
    assert services.finish_run(rid, store=store)["status"] == "finished"
