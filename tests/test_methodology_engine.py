"""Methodologies — tag-driven constellation specs (spec/methodology-constellations.md).

Since HX3 (spec/hx3-engine-collapse.md) a methodology is a SPEC + REGISTRY that SEEDS the plan
engine — the single runtime engine is the plan (its analyze/act/verify gating is covered in
test_research_plan.py). Here: specs validate with ZERO hardcoded vocabularies; an invented
capability/role/gate tag loads; a non-alternating DAG with a non-prototype artifact requirement
seeds a correct plan; bad/cyclic specs are rejected.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from sonaloop import methodology as M
from sonaloop import plan as PL
from sonaloop import primitive_taxonomy_registry as TX
from sonaloop import services


# --------------------------------------------------------------------------- C1: tags

def test_builtins_load_and_validate(store):
    keys = {m["key"] for m in M.list_methodologies(store=store)}
    assert {"double_diamond", "double_diamond_deep", "dschool_micro", "lean_jtbd"} <= keys
    dd = M.get_methodology("double_diamond", store=store)
    # shape is derived from structure: explore (fan) then decide (waist), alternating here
    assert [M._is_decide(s) for s in dd["steps"]] == [False, True, False, True]


def test_methodology_registry_surfaces_data_authored_front_door_routing(store):
    rows = {row["key"]: row for row in M.list_methodologies(store=store)}
    reaction = rows["reaction_test"]["routing"]

    assert reaction["schema"] == "methodology_routing.v1"
    assert reaction["threshold"] > 0
    assert any(signal["phrase"] == "screenshot" for signal in reaction["signals"])
    assert all(signal["weight"] > 0 for signal in reaction["signals"])


def test_builtin_stage_guides_use_library_primitives(store):
    """Stage guides are user-facing. They may name Library primitives and explicit
    Council/Session subtypes, but the shown forms must resolve through the registry."""
    library = {
        "Open questions", "References", "Councils", "Reports", "Prototypes", "Sessions",
        "Surveys", "Hypotheses", "Decisions", "Notes", "Assets",
    }
    prefixes = ("Council: ", "Session: ")
    for row in M.list_methodologies(store=store):
        spec = M.get_methodology(row["key"], store=store)
        for step in spec["steps"]:
            pres = step.get("presentation") or {}
            for item in pres.get("library") or []:
                assert item in library, (spec["key"], step["id"], item)
            for item in pres.get("formats") or []:
                assert item == "Council" or item.startswith(prefixes), (spec["key"], step["id"], item)
            registered = pres.get("registered_forms") or []
            assert registered, (spec["key"], step["id"])
            for ref in registered:
                assert TX.get_form(ref["primitive"], ref["form"])
                assert ref["label"] == f"{ref['primitive_label']} / {ref['form_label']}"


def test_reaction_test_seeds_explicit_provider_neutral_act_todos(store):
    project = services.start_project(
        "Reaction harness", "How does the admitted flow land?",
        methodology="Reaction Test", persona_ids=["p1", "p2"], store=store)
    tasks = {task["id"]: task for task in services.get_plan(project["id"], store=store)["tasks"]}

    assert {"act__react__comprehension", "act__react__trust_action"} <= tasks.keys()
    for task_id in ("act__react__comprehension", "act__react__trust_action"):
        task = tasks[task_id]
        assert task["bucket"] == "act"
        assert task["capability"] == "reaction_council"
        assert task["expected_output_kind"] == "council"
        assert task["consumes"] == ["frame__react", "preflight__cohort_integrity"]


def test_no_hardcoded_vocabularies_in_engine_source():
    """C1 acceptance: no closed capability/role/breadth/judgment/artifact SET remains in code, and
    the structural helpers do not special-case any artifact tag."""
    import inspect
    src = Path(M.__file__).read_text()
    for banned in ("DIVERGE_ROLES", "CONVERGE_ROLES", "ROLES =", "JUDGMENT_KINDS", "FIDELITIES", "MODES ="):
        assert banned not in src, banned
    # the structural invariant helper must be artifact-type-generic: no literal artifact string
    # special-cased. (_phases_to_steps may still name old strings — back-compat glue, not an
    # invariant; _artifact_tags may DEFAULT an untyped artifact's type tag — a data default, not a
    # closed set.)
    s = inspect.getsource(M._is_decide)
    for lit in ('"prototype"', "'prototype'", '"prototype_session"', '"survey"', '"lofi"', '"midfi"'):
        assert lit not in s, f"_is_decide hardcodes artifact tag {lit}"


def test_invented_capability_and_gate_tags_load_and_seed(store):
    """An invented capability + an invented FREE gate tag validate, register, and seed a plan where
    the decide step becomes a gated verify task carrying that free gate tag (tag-agnostic)."""
    spec = {
        "key": "invented", "name": "Invented", "description": "d", "when_to_use": "w",
        "steps": [
            {"id": "scout", "name": "Scout", "tags": ["divine-the-vibe"], "intent": "explore",
             "produces": {"role": "vibe-map"}},
            {"id": "land", "name": "Land", "tags": ["crystallize"], "intent": "decide",
             "consumes": ["scout"], "requires": {"min_inputs": 2, "gate_tag": "vibes_are_clear"},
             "produces": {"role": "the-vibe"}},
        ],
    }
    M.register_methodology(spec, store=store)
    got = M.get_methodology("invented", store=store)
    assert [s["tags"] for s in got["steps"]] == [["divine-the-vibe"], ["crystallize"]]
    assert [s["presentation"].get("registered_forms") for s in got["steps"]] == [None, None]
    proj = services.start_project("Inv", "g", methodology="invented", store=store)   # forwards to start_project
    plan = services.get_plan(proj["id"], store=store)
    frame = PL.task(plan, "frame__scout")
    verify = PL.task(plan, "verify__land")
    assert frame["bucket"] == "analyze" and frame["capability"] == "frame"
    assert verify["bucket"] == "verify" and verify["consumes"] == ["frame__scout"]
    assert verify["requires"]["gate_tag"] == "vibes_are_clear"   # the FREE gate tag is carried through
    assert verify["requires"]["min_inputs"] == 2


# --------------------------------------------------------------------------- C2: validation

def test_bad_spec_rejected(store):
    with pytest.raises(M.MethodologyError):  # missing steps
        M.validate_methodology_spec({"key": "x", "name": "x", "description": "d", "when_to_use": "w"})
    with pytest.raises(M.MethodologyError):  # consumes an unknown step
        M.validate_methodology_spec({"key": "x", "name": "x", "description": "d", "when_to_use": "w",
                                     "steps": [{"id": "a", "name": "A"},
                                               {"id": "b", "name": "B", "consumes": ["ghost"]}]})


def test_builtin_key_reserved_on_register(store):
    """Registering under a built-in key is rejected (stable code RESERVED_KEY) at the engine layer,
    so the Python and MCP surfaces behave the same — no silent shadowing of packaged specs."""
    shadow = {"key": "double_diamond", "name": "Shadow", "description": "d", "when_to_use": "w",
              "steps": [{"id": "a", "name": "A"}, {"id": "b", "name": "B", "consumes": ["a"]}]}
    with pytest.raises(M.MethodologyError) as e:
        M.register_methodology(shadow, store=store)
    assert e.value.code == "RESERVED_KEY"
    assert "RESERVED_KEY" in str(e.value)            # the code rides str(exc) across boundaries
    # the built-in is untouched
    assert M.get_methodology("double_diamond", store=store)["name"] != "Shadow"


def test_cycle_rejected(store):
    with pytest.raises(M.MethodologyError):
        M.validate_methodology_spec({"key": "x", "name": "x", "description": "d", "when_to_use": "w",
                                     "steps": [{"id": "a", "name": "A", "consumes": ["b"]},
                                               {"id": "b", "name": "B", "consumes": ["a"]}]})


def test_non_alternating_dag_with_nonprototype_artifact_seeds(store):
    """C2 acceptance: a NON-alternating shape (one fan feeding two parallel decides) and a
    NON-prototype artifact requirement (a `survey`) validate and seed a correct plan — zero code
    changes. Both decides consume the one frame; one carries a session-of-`survey` gate."""
    spec = {
        "key": "branchy", "name": "Branchy", "description": "d", "when_to_use": "w",
        "steps": [
            {"id": "scan", "name": "Scan", "tags": ["explore", "build"], "intent": "explore + build",
             "produces": {"role": "landscape", "artifact_type": "survey", "more_tags": ["survey"]}},
            {"id": "pick_a", "name": "Pick A", "tags": ["decide"], "intent": "branch A",
             "consumes": ["scan"], "requires": {"min_inputs": 2, "gate_tag": "scanned_enough"},
             "produces": {"role": "pov-a"}},
            {"id": "pick_b", "name": "Pick B", "tags": ["decide"], "intent": "branch B (needs a survey response)",
             "consumes": ["scan"],
             "requires": {"min_inputs": 2, "gate_tag": "scanned_enough", "session_of_tags": ["survey"]},
             "produces": {"role": "pov-b"}},
        ],
    }
    M.register_methodology(spec, store=store)
    proj = services.start_project("Br", "g", methodology="branchy", persona_ids=["p1"], store=store)
    plan = services.get_plan(proj["id"], store=store)
    a, b = PL.task(plan, "verify__pick_a"), PL.task(plan, "verify__pick_b")
    assert a["consumes"] == ["frame__scan"] and b["consumes"] == ["frame__scan"]   # two parallel decides
    assert a["requires"]["gate_tag"] == "scanned_enough"
    assert b["requires"]["session_of_tags"] == ["survey"]   # non-prototype artifact requirement carried


def test_no_hardcoded_dynamic_threshold():
    """A4: the module must not encode a numeric saturation/min-count that decides dynamics. The only
    literal is the structural ">= 2 steps" spec check; breadth lives in the plan via `min_inputs`."""
    import re
    src = Path(M.__file__).read_text()
    nums = re.findall(r"len\([^)]*\)\s*<\s*(\d+)", src)
    assert all(n == "2" for n in nums), f"unexpected dynamic threshold literal(s): {nums}"
