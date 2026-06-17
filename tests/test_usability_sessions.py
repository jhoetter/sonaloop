"""Usability sessions — the durable, replayable session trace (the session IS the deliverable).

Record/read round-trip losslessness across all three fidelity rungs, session-ref validation,
the data-driven friction vocabulary (incl. alias resolution), funnel math across sessions of
one subject, the validation failures, and groundedness against the browser session log.
Back-compat: the PrototypeSession path keeps its own tests (test_browser_harness/test_research_plan).
"""
from __future__ import annotations

import pytest

from sonaloop import artifacts, browser, services


_FLOW = {"kind": "flow", "id": "flow-signup", "label": "Signup flow"}
_PROTO = {"kind": "prototype", "id": "proto-signup", "label": "Signup prototype"}
_LIVE = {"kind": "live_url", "url": "https://example.test/signup", "label": "Signup live"}
_VARIANT = {"kind": "variant", "id": "variant-a", "label": "Signup variant A"}


def _step(i, *, friction="none", would_continue=True, reason="", screen=None, **state):
    return {
        "index": i,
        "action": {"type": "click", "target": f"button-{i}", "detail": f"clicked button {i}"},
        "monologue": f"thinking aloud at step {i}",
        "state": {"screen": screen or f"screen-{i}", **state},
        "friction": {"level": friction, "note": ""},
        "verdict": {"would_continue": would_continue, "reason": reason},
    }


def _outcome(completed=True, dropoff=None, summary="walked the flow"):
    return {"completed": completed, "dropoff_step": dropoff, "summary": summary,
            "predicted_behaviors": []}


def _record(store, subject, fidelity, steps=None, outcome=None, **kw):
    return services.record_usability_session(
        "pX", subject, fidelity, "2026-06-10",
        steps if steps is not None else [_step(0), _step(1)],
        outcome if outcome is not None else _outcome(), store=store, **kw)


def test_session_form_classifies_subjects_and_legacy_reactions():
    assert services.session_form({"subject": _FLOW}) == "walkthrough"
    assert services.session_form({"subject": _PROTO}) == "prototype_use"
    assert services.session_form({"subject": _LIVE}) == "live_use"
    assert services.session_form({"prototype_id": "proto_1"}) == "prototype_use"
    assert services.session_form({
        "subject": _VARIANT,
        "variants": ["A", "B"],
        "assignment": {"persona": "A"},
        "order_shown": ["A", "B"],
    }) == "variant_test"


# --------------------------------------------------------------- round-trip across the three rungs

@pytest.mark.parametrize("subject,fidelity", [(_FLOW, "artifact"), (_PROTO, "prototype"), (_LIVE, "live")])
def test_record_read_roundtrip_is_lossless(store, subject, fidelity):
    steps = [
        _step(0, friction="none"),
        _step(1, friction="hesitation", reason="label was ambiguous",
              url="https://example.test/signup", title="Signup"),
        _step(2, friction="confusion", would_continue=False, reason="lost the thread"),
    ]
    outcome = {"completed": False, "dropoff_step": 2, "summary": "dropped at the summary screen",
               "predicted_behaviors": [{"action": "ask a colleague", "step": 2,
                                        "likelihood": "likely", "trigger": "unclear copy"}]}
    res = _record(store, subject, fidelity, steps, outcome, project_id="proj-1")
    sess = services.get_usability_session(res["usability_session"]["id"], store=store)
    # the trace survives byte-for-byte: the dual timeline, the outcome, the subject, the fidelity.
    # The one canonicalization: predicted_behaviors validate through the primitive
    # (ticket behavioral-prediction-output) — likelihood resolves onto the scale, a part id lands.
    assert sess["steps"] == steps
    assert {k: v for k, v in sess["outcome"].items() if k != "predicted_behaviors"} \
        == {k: v for k, v in outcome.items() if k != "predicted_behaviors"}
    pb = sess["outcome"]["predicted_behaviors"][0]
    assert pb["action"] == "ask a colleague" and pb["step"] == 2 and pb["id"] == "pb1"
    assert pb["likelihood"] == {"value": 0.7, "label": "likely"} and pb["trigger"] == "unclear copy"
    assert sess["subject"] == subject and sess["fidelity"] == fidelity
    assert sess["project_id"] == "proj-1" and sess["persona_id"] == "pX" and sess["date"] == "2026-06-10"


def test_deterministic_key_is_idempotent_upsert(store):
    r1 = _record(store, _FLOW, "artifact", key="run:step:angle")
    r2 = _record(store, _FLOW, "artifact", key="run:step:angle")
    assert r1["usability_session"]["id"] == r2["usability_session"]["id"]
    assert len(services.list_usability_sessions(store=store)) == 1


def test_list_filters_by_persona_project_and_subject(store):
    _record(store, _FLOW, "artifact", project_id="proj-a")
    _record(store, _PROTO, "prototype", project_id="proj-b")
    assert len(services.list_usability_sessions(store=store)) == 2
    assert len(services.list_usability_sessions(project_id="proj-a", store=store)) == 1
    assert len(services.list_usability_sessions(subject={"kind": "prototype"}, store=store)) == 1
    assert len(services.list_usability_sessions(subject="flow-signup", store=store)) == 1
    assert services.list_usability_sessions(persona_id="nobody", store=store) == []


# --------------------------------------------------------------- friction vocabulary (data-driven)

def test_friction_aliases_resolve_to_canonical_levels(store):
    res = _record(store, _FLOW, "artifact",
                  steps=[_step(0, friction="stuck", would_continue=False, reason="dead end")],
                  outcome=_outcome(completed=False, dropoff=0))
    assert res["usability_session"]["steps"][0]["friction"]["level"] == "blocked"
    # numeric + case/whitespace-insensitive resolution mirror resolve_stance
    assert artifacts.resolve_friction(" Verwirrt ") == {"value": 2, "label": "confusion"}
    assert artifacts.resolve_friction(1) == {"value": 1, "label": "hesitation"}


def test_unknown_friction_level_is_rejected_not_bucketed(store):
    assert artifacts.resolve_friction("totally-fine-i-guess") is None
    with pytest.raises(ValueError, match="friction"):
        _record(store, _FLOW, "artifact", steps=[_step(0, friction="totally-fine-i-guess")])


def test_suggest_friction_levels_matches_scale_data():
    out = services.suggest_friction_levels()
    assert [(i["term"], i["value"]) for i in out["items"]] == \
        [(r["term"], r["value"]) for r in artifacts.friction_terms()]
    assert [i["value"] for i in out["items"]] == sorted(i["value"] for i in out["items"])
    by_term = {i["term"]: i for i in out["items"]}
    assert "stuck" in by_term["blocked"]["aliases"]


# --------------------------------------------------------------- session refs in statements

def test_statement_ref_to_existing_step_is_accepted_and_backfilled(store):
    res = _record(store, _FLOW, "artifact", statements=[{
        "persona_id": "pX", "text": "The second screen lost me.",
        "refs": [{"kind": "session", "anchor": "step:1"}]}])
    sess = res["usability_session"]
    ref = sess["statements"][0]["refs"][0]
    assert ref["id"] == sess["id"] and ref["anchor"] == "step:1"   # self-id backfilled pre-record
    # the anchor resolves LIVE to the step's monologue (resolve_ref, never a stale copy)
    resolved = artifacts.resolve_ref(ref, store)
    assert resolved["exists"] is True and resolved["text"] == "thinking aloud at step 1"


def test_statement_ref_to_nonexistent_step_is_rejected(store):
    with pytest.raises(ValueError, match="nonexistent step"):
        _record(store, _FLOW, "artifact", statements=[{
            "persona_id": "pX", "text": "x",
            "refs": [{"kind": "session", "anchor": "step:9"}]}])
    with pytest.raises(ValueError, match="unknown session"):
        _record(store, _FLOW, "artifact", statements=[{
            "persona_id": "pX", "text": "x",
            "refs": [{"kind": "session", "id": "usession_missing", "anchor": "step:0"}]}])


def test_broken_step_anchor_resolves_exists_false(store):
    sid = _record(store, _FLOW, "artifact")["usability_session"]["id"]
    assert artifacts.resolve_ref({"kind": "session", "id": sid, "anchor": "step:7"}, store)["exists"] is False


# --------------------------------------------------------------- validation failures

def test_non_contiguous_step_indices_are_rejected(store):
    with pytest.raises(ValueError, match="contiguous"):
        _record(store, _FLOW, "artifact", steps=[_step(0), {**_step(1), "index": 2}])


def test_bad_dropoff_step_and_missing_dropoff_are_rejected(store):
    with pytest.raises(ValueError, match="dropoff_step"):
        _record(store, _FLOW, "artifact", outcome=_outcome(completed=False, dropoff=5))
    with pytest.raises(ValueError, match="dropoff_step"):
        _record(store, _FLOW, "artifact", outcome=_outcome(completed=False, dropoff=None))


def test_step_action_state_and_verdict_shapes_are_enforced(store):
    bad_action = _step(0)
    bad_action["action"]["type"] = "teleport"
    with pytest.raises(ValueError, match="action.type"):
        _record(store, _FLOW, "artifact", steps=[bad_action])
    no_screen = _step(0)
    no_screen["state"] = {}
    with pytest.raises(ValueError, match="state.screen"):
        _record(store, _FLOW, "artifact", steps=[no_screen])
    bad_verdict = _step(0)
    bad_verdict["verdict"] = {"would_continue": "yes"}
    with pytest.raises(ValueError, match="would_continue"):
        _record(store, _FLOW, "artifact", steps=[bad_verdict])
    with pytest.raises(ValueError, match="non-empty"):
        _record(store, _FLOW, "artifact", steps=[])
    with pytest.raises(ValueError, match="subject.kind"):
        _record(store, {"kind": "screenshot", "id": "x", "label": "x"}, "artifact")
    with pytest.raises(ValueError, match="fidelity"):
        _record(store, _FLOW, "hifi")


def test_missing_screenshot_file_is_rejected_and_present_one_accepted(store, tmp_path, monkeypatch):
    from sonaloop import config
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    shot = _step(0)
    shot["state"]["screenshot"] = "step-0.png"
    with pytest.raises(ValueError, match="screenshot"):
        _record(store, _FLOW, "artifact", steps=[shot], key="shots")
    sess_id = services.stable_id("usession", "shots")
    d = config.sessions_dir() / sess_id
    d.mkdir(parents=True)
    (d / "step-0.png").write_bytes(b"png")
    res = _record(store, _FLOW, "artifact", steps=[shot], key="shots")
    assert res["usability_session"]["steps"][0]["state"]["screenshot"] == "step-0.png"


def test_screenshot_path_escaping_the_data_dir_is_rejected(store, tmp_path, monkeypatch):
    from sonaloop import config
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    # an absolute path to a real file outside the data dir is not a session screenshot
    absolute = _step(0)
    absolute["state"]["screenshot"] = "/etc/passwd"
    with pytest.raises(ValueError, match="escapes the data dir"):
        _record(store, _FLOW, "artifact", steps=[absolute])
    # ... and neither is a relative path that traverses out of it
    traversal = _step(0)
    traversal["state"]["screenshot"] = "../" * 12 + "etc/passwd"
    with pytest.raises(ValueError, match="escapes the data dir"):
        _record(store, _FLOW, "artifact", steps=[traversal])


def test_completed_session_with_a_dropoff_step_is_rejected(store):
    with pytest.raises(ValueError, match="dropoff_step must be null"):
        _record(store, _FLOW, "artifact", outcome=_outcome(completed=True, dropoff=1))


def test_bool_step_index_is_rejected(store):
    with pytest.raises(ValueError, match="contiguous"):
        _record(store, _FLOW, "artifact", steps=[_step(0), {**_step(1), "index": True}])


# --------------------------------------------------------------- groundedness vs. the browser log

def test_prototype_states_verify_against_session_log(store, monkeypatch):
    log = [{"kind": "snapshot", "url": "http://127.0.0.1:9/x", "title": "Signup",
            "refs": ["e1"], "text": "Welcome — create your account"}]
    monkeypatch.setitem(browser._RETAINED_LOGS, "sid-ok", log)
    res = _record(store, _PROTO, "prototype",
                  steps=[_step(0, screen="create your account", url="http://127.0.0.1:9/x", title="Signup")],
                  outcome=_outcome(), session_id="sid-ok")
    assert res["grounded_verified"] is True
    assert res["usability_session"]["grounded_verified"] is True
    # a claimed state never seen in the log is rejected
    with pytest.raises(ValueError, match="groundedness"):
        _record(store, _PROTO, "prototype",
                steps=[_step(0, screen="NONEXISTENT-STATE-XYZ")], outcome=_outcome(),
                session_id="sid-ok")


def test_missing_session_log_records_unverified_with_warning(store):
    res = _record(store, _LIVE, "live", session_id="sid-gone")
    assert res["grounded_verified"] is False
    assert any("UNVERIFIED_SESSION" in w for w in res["warnings"])


def test_artifact_fidelity_needs_no_browser_log(store):
    res = _record(store, _FLOW, "artifact")
    assert "grounded_verified" not in res and "warnings" not in res


# --------------------------------------------------------------- the funnel

def test_funnel_math_across_three_sessions_with_different_dropoffs(store):
    # A completes all 3 steps; B drops at step 1; C drops at step 2
    _record(store, _PROTO, "prototype",
            steps=[_step(0), _step(1), _step(2)], outcome=_outcome(completed=True), key="A")
    _record(store, _PROTO, "prototype",
            steps=[_step(0), _step(1, friction="blocked", would_continue=False,
                                   reason="could not find the next button")],
            outcome=_outcome(completed=False, dropoff=1, summary="gave up"), key="B")
    _record(store, _PROTO, "prototype",
            steps=[_step(0), _step(1), _step(2, friction="confusion", would_continue=False,
                                             reason="price table made no sense")],
            outcome=_outcome(completed=False, dropoff=2, summary="bounced"), key="C")
    funnel = services.get_session_funnel("prototype", "proto-signup", store=store)
    assert funnel["sessions"] == 3 and funnel["completed"] == 1
    rows = {r["step"]: r for r in funnel["rows"]}
    assert rows[0] == {"step": 0, "entered": 3, "continued": 3, "dropped": 0, "drop_reasons": []}
    assert rows[1]["entered"] == 3 and rows[1]["dropped"] == 1 and rows[1]["continued"] == 2
    assert rows[1]["drop_reasons"] == ["could not find the next button"]
    assert rows[2]["entered"] == 2 and rows[2]["dropped"] == 1 and rows[2]["continued"] == 1
    assert rows[2]["drop_reasons"] == ["price table made no sense"]
    # an unknown subject yields an honest empty funnel
    empty = services.get_session_funnel("prototype", "never-tested", store=store)
    assert empty["sessions"] == 0 and empty["rows"] == []


# --------------------------------------------------------------- the brief (gather, no server text)

def test_brief_gathers_persona_context_and_friction_vocabulary(store):
    from conftest import create_persona
    pid = create_persona(store, "Greta Tester")
    brief = services.brief_usability_session(pid, _FLOW, "artifact", store=store)
    assert brief["schema"] == "usability_session" and brief["subject"] == _FLOW
    assert brief["agent_context"] and "SOUL" in brief["agent_context"]
    assert [i["term"] for i in brief["friction_levels"]["items"]] == \
        [r["term"] for r in artifacts.friction_terms()]
    assert "Anti-steering" in brief["instructions"]
    # no declared capabilities -> the DERIVED profile rides along (never persisted back)
    assert brief["capabilities"]["provenance"] == "derived"
    assert store.get_persona(pid)["capabilities"] is None


def test_brief_includes_capabilities_when_the_persona_carries_them(store):
    from conftest import create_persona
    pid = create_persona(store, "Carl Capable")
    persona = store.get_persona(pid)
    # legacy free-form keys survive normalization; canonical fields fill from the defaults
    persona["capabilities"] = {"vision": "low", "tech_comfort": "high"}
    store.upsert_persona(persona, reason="test: capabilities profile")
    brief = services.brief_usability_session(pid, _LIVE, "live", store=store)
    caps = brief["capabilities"]
    assert caps["vision"] == "low" and caps["tech_comfort"] == 4      # alias resolved on read
    assert caps["rungs"] == {"see": True, "walk": True, "drive": True, "login": False}
    assert caps["provenance"] == "authored"
    with pytest.raises(KeyError):
        services.brief_usability_session("nobody", _FLOW, "artifact", store=store)
