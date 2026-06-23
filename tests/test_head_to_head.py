"""Head-to-Head Format (taxonomy id head_to_head): run a council on a DIRECT comparison of two (or
more) options and return a reasoned, SEGMENTED preference — preference + margin + deciding factors +
who-prefers-what. Built on top of the artifacts/variant plumbing. Covers: a TEXT-option head-to-head,
an ARTIFACT-variant head-to-head, the deterministic aggregation (preference / margin / segment-split
math), and persistence (it is a queryable CouncilSession carrying a head_to_head block).

Capture is stubbed (no network) by monkeypatching sonaloop.capture.capture_url, mirroring the rest of
the suite (host/IO output supplied inline; no server-side text-LLM calls)."""
from __future__ import annotations

from sonaloop import services
from sonaloop import capture as _capture
from conftest import create_persona


def _fake_capture(mapping):
    def _cap(url, *, timeout=12.0):
        snap = mapping.get(url)
        if snap is None:
            return {"ok": False, "mode": "unavailable", "url": url, "captured_at": "2026-06-09T00:00:00Z",
                    "title": "", "description": "", "headings": [], "text": "", "status": None,
                    "final_url": url, "bytes": 0, "content_hash": "deadbeef", "error": "boom"}
        return {"ok": True, "mode": "text", "url": url, "final_url": url, "status": 200,
                "captured_at": "2026-06-09T00:00:00Z", "bytes": len(snap["text"]),
                "content_hash": snap["hash"], "title": snap["title"], "description": snap.get("desc", ""),
                "headings": snap.get("headings", []), "text": snap["text"]}
    return _cap


def _project(store, personas=("Alpha",), **kw):
    pids = [create_persona(store, n, **kw) for n in personas]
    proj = services.create_research_project("Pricing study", goal="what should I charge",
                                            persona_ids=pids, store=store)
    return proj["id"], pids


# --------------------------------------------------------------------------- text-option head-to-head

def test_text_option_head_to_head_briefs_both_options_side_by_side(store):
    pid, [persona] = _project(store)
    brief = services.brief_head_to_head(
        pid, "Which price lands better?", ["$29/mo", "$49/mo"], persona_ids=[persona], store=store)
    assert brief["schema"] == "head_to_head"
    assert [o["label"] for o in brief["options"]] == ["A", "B"]
    assert brief["options"][0]["kind"] == "text" and brief["options"][0]["text"] == "$29/mo"
    ctx = brief["participants"][0]["agent_context"]
    # Both options are present, labelled, and side-by-side in the participant's context.
    assert "OPTION A" in ctx and "OPTION B" in ctx
    assert "$29/mo" in ctx and "$49/mo" in ctx
    assert "HEAD-TO-HEAD" in ctx
    assert "opt:A" in brief["instructions"]


def test_head_to_head_needs_two_options(store):
    import pytest
    pid, [persona] = _project(store)
    with pytest.raises(ValueError):
        services.brief_head_to_head(pid, "?", ["only one"], persona_ids=[persona], store=store)


# --------------------------------------------------------------------------- artifact-variant head-to-head

def test_artifact_variant_head_to_head_reuses_captured_variants(store, monkeypatch):
    monkeypatch.setattr(_capture, "capture_url", _fake_capture({
        "https://a.test": {"title": "Variant A", "text": "Calm minimalist page.", "hash": "ha"},
        "https://b.test": {"title": "Variant B", "text": "Loud high-contrast page.", "hash": "hb"}}))
    pid, [persona] = _project(store)
    a = services.add_artifact(pid, "https://a.test", kind="variant", store=store)
    b = services.add_artifact(pid, "https://b.test", kind="variant", store=store)
    assert {a["label"], b["label"]} == {"A", "B"}

    # Options referenced by label resolve to the labelled, captured variant briefs.
    brief = services.brief_head_to_head(pid, "Which landing page wins?", ["A", "B"],
                                        persona_ids=[persona], store=store)
    kinds = {o["label"]: o["kind"] for o in brief["options"]}
    assert kinds == {"A": "artifact", "B": "artifact"}
    ctx = brief["participants"][0]["agent_context"]
    assert "Calm minimalist page." in ctx and "Loud high-contrast page." in ctx
    assert "OPTION A" in ctx and "OPTION B" in ctx


def test_mixed_text_and_artifact_options(store, monkeypatch):
    monkeypatch.setattr(_capture, "capture_url", _fake_capture({
        "https://a.test": {"title": "Variant A", "text": "Captured copy.", "hash": "ha"}}))
    pid, [persona] = _project(store)
    services.add_artifact(pid, "https://a.test", kind="variant", store=store)   # label A
    brief = services.brief_head_to_head(pid, "Compare", ["A", "a plain-text option"],
                                        persona_ids=[persona], store=store)
    kinds = {o["label"]: o["kind"] for o in brief["options"]}
    assert kinds["A"] == "artifact"
    # the text option gets the next free label (B) and is rendered as its literal text.
    text_opt = next(o for o in brief["options"] if o["kind"] == "text")
    assert text_opt["label"] == "B"
    assert "a plain-text option" in brief["participants"][0]["agent_context"]


# --------------------------------------------------------------------------- aggregation math

def test_aggregation_preference_margin_and_segment_splits(store):
    # Two segments: 3 architects (2 prefer A, 1 prefers B), 2 engineers (both prefer B).
    arch = [create_persona(store, f"Arch{i}", customer_type="Architect") for i in range(3)]
    eng = [create_persona(store, f"Eng{i}", customer_type="Engineer") for i in range(2)]
    pids = arch + eng
    proj = services.create_research_project("seg study", goal="g", persona_ids=pids, store=store)
    pid = proj["id"]

    prefs = [
        {"persona_id": arch[0], "choice": "A", "reason": "cheaper"},
        {"persona_id": arch[1], "choice": "A", "reason": "fits budget"},
        {"persona_id": arch[2], "choice": "B", "reason": "more value"},
        {"persona_id": eng[0], "choice": "B", "reason": "scales"},
        {"persona_id": eng[1], "choice": "B", "reason": "scales"},
    ]
    session = services.record_head_to_head(
        pid, "$29 vs $49?", ["$29/mo", "$49/mo"], preferences=prefs,
        exec_summary="Host-authored verdict.", summary="TL;DR.", store=store)

    res = session["head_to_head"]["result"]
    # Overall: A=2, B=3 → B wins by a margin of (3-2)/5 = 0.2 (narrow).
    assert res["tally"] == {"A": 2, "B": 3}
    assert res["preference"] == "B"
    assert res["voters"] == 5
    assert res["margin"] == 0.2
    assert res["decisive"] == "narrow"

    # Segment splits: architects lean A (2 vs 1), engineers unanimous B.
    by_seg = {s["segment"]: s for s in res["segment_splits"]}
    assert by_seg["Architect"]["prefers"] == "A"
    assert by_seg["Architect"]["tally"] == {"A": 2, "B": 1}
    assert by_seg["Engineer"]["prefers"] == "B"
    assert by_seg["Engineer"]["voters"] == 2


def test_aggregation_tie_has_no_preference(store):
    a = create_persona(store, "A", customer_type="X")
    b = create_persona(store, "B", customer_type="Y")
    proj = services.create_research_project("tie", goal="g", persona_ids=[a, b], store=store)
    session = services.record_head_to_head(
        proj["id"], "?", ["opt one", "opt two"],
        preferences=[{"persona_id": a, "choice": "A"}, {"persona_id": b, "choice": "B"}], store=store)
    res = session["head_to_head"]["result"]
    assert res["preference"] is None
    assert res["margin"] == 0.0
    assert res["decisive"] == "tie"


def test_unparseable_preference_is_not_counted(store):
    a = create_persona(store, "A", customer_type="X")
    b = create_persona(store, "B", customer_type="X")
    proj = services.create_research_project("p", goal="g", persona_ids=[a, b], store=store)
    session = services.record_head_to_head(
        proj["id"], "?", ["o1", "o2"],
        preferences=[{"persona_id": a, "choice": "A"}, {"persona_id": b, "choice": "torn"}], store=store)
    res = session["head_to_head"]["result"]
    assert res["voters"] == 1 and res["preference"] == "A"
    # ab_test protocol (forced_preference): a 'torn' is an ABSTENTION and is counted as one —
    # overall and on the abstainer's segment row — never silently dropped.
    assert res["abstentions"] == 1
    seg = {s["segment"]: s for s in res["segment_splits"]}["X"]
    assert seg["abstentions"] == 1 and seg["voters"] == 1


# --------------------------------------------------------------------------- ab_test protocol: variant metadata

def test_brief_randomizes_option_order_per_persona(store):
    """Position-bias guard (ab_test protocol `randomized_order`): each participant carries a
    deterministic per-persona option_order — a permutation of the labels — and their context
    presents the options in THAT order."""
    pids = [create_persona(store, f"P{i}") for i in range(6)]
    proj = services.create_research_project("ab", goal="g", persona_ids=pids, store=store)
    brief = services.brief_head_to_head(proj["id"], "Which variant wins?",
                                        ["calm landing page", "loud landing page"],
                                        persona_ids=pids, store=store)
    orders = []
    for part in brief["participants"]:
        assert sorted(part["option_order"]) == ["A", "B"]
        first = part["option_order"][0]
        # The participant's context block lists their first option first.
        ctx = part["agent_context"].split("=== HEAD-TO-HEAD OPTIONS ===")[1]
        assert ctx.index(f"OPTION {first}") < ctx.index(
            "OPTION " + ({"A", "B"} - {first}).pop())
        orders.append(tuple(part["option_order"]))
    # Across a 6-persona panel both orders occur (randomized, not fixed) …
    assert len(set(orders)) == 2
    # … and the assignment is deterministic (same brief → same orders; resumable).
    again = services.brief_head_to_head(proj["id"], "Which variant wins?",
                                        ["calm landing page", "loud landing page"],
                                        persona_ids=pids, store=store)
    assert [p["option_order"] for p in again["participants"]] == [list(o) for o in orders]


def test_variant_metadata_round_trips(store):
    """ab_test recording: variant ids, per-persona order shown and the pre-exposure hypothesis
    ref persist on the head_to_head block and come back from get_head_to_head."""
    a = create_persona(store, "Arch", customer_type="Architect")
    b = create_persona(store, "Eng", customer_type="Engineer")
    proj = services.create_research_project("ab", goal="g", persona_ids=[a, b], store=store)
    hyp = services.record_hypothesis(
        proj["id"], "Variant B lifts signup intent",
        {"metric": "signup_intent", "expected_direction": "increase"}, store=store)["hypothesis"]

    meta = {"variants": {"A": {"id": "var-calm"}, "B": "var-loud"},
            "order_shown": {a: ["B", "A"], b: ["A", "B"]},
            "hypothesis_id": hyp["id"]}
    session = services.record_head_to_head(
        proj["id"], "calm vs loud", ["calm page", "loud page"],
        preferences=[{"persona_id": a, "choice": "B", "intensity": 2, "reason": "clearer"},
                     {"persona_id": b, "choice": "B", "intensity": 1, "reason": "faster"}],
        variant_meta=meta, exec_summary="Host verdict.", store=store)

    stored = session["head_to_head"]["variant_meta"]
    assert stored["variants"] == {"A": {"id": "var-calm"}, "B": {"id": "var-loud"}}  # bare str → {id}
    assert stored["order_shown"] == {a: ["B", "A"], b: ["A", "B"]}
    assert stored["hypothesis_id"] == hyp["id"]
    # Queryable round-trip — and the intensity rides on the stored preferences verbatim.
    ht = services.get_head_to_head(session["id"], store=store)
    assert ht["variant_meta"] == stored
    assert ht["preferences"][0]["intensity"] == 2


def test_variant_metadata_is_validated(store):
    import pytest
    pid, [persona] = _project(store)
    common = dict(prompt="?", options=["o1", "o2"],
                  preferences=[{"persona_id": persona, "choice": "A"}], store=store)
    with pytest.raises(ValueError, match="permutation"):
        services.record_head_to_head(pid, **common,
                                     variant_meta={"order_shown": {persona: ["A"]}})
    with pytest.raises(ValueError, match="hypothesis_id does not resolve"):
        services.record_head_to_head(pid, **common, variant_meta={"hypothesis_id": "hyp_nope"})
    with pytest.raises(ValueError, match="option labels"):
        services.record_head_to_head(pid, **common, variant_meta={"variants": {"Z": "v1"}})
    with pytest.raises(ValueError, match="unknown variant_meta keys"):
        services.record_head_to_head(pid, **common, variant_meta={"surprise": 1})


def test_recordings_without_variant_metadata_stay_loadable(store):
    """Backward compatibility: pre-metadata recordings (no variant_meta, no abstentions/margin on
    segment rows) still load, and segmented_verdict derives the missing numbers from the stored
    tallies."""
    a = create_persona(store, "A", customer_type="X")
    proj = services.create_research_project("compatibility", goal="g", persona_ids=[a], store=store)
    session = services.record_head_to_head(
        proj["id"], "old", ["o1", "o2"],
        preferences=[{"persona_id": a, "choice": "A"}], store=store)
    # Strip the block down to the COMPATIBILITY shape (as recorded before this ticket) and re-persist.
    compatibility = store.get_council_session(session["id"])
    ht = compatibility["head_to_head"]
    ht.pop("variant_meta", None)
    ht["result"].pop("abstentions")
    for seg in ht["result"]["segment_splits"]:
        seg.pop("margin"), seg.pop("abstentions")
    store.insert_council_session(compatibility)

    fetched = services.get_head_to_head(session["id"], store=store)
    assert "variant_meta" not in fetched
    verdict = services.segmented_verdict(session["id"], store=store)
    assert verdict["overall"] == {"winner": "A", "winner_title": "o1", "margin": 1.0,
                                  "decisive": "decisive", "voters": 1, "abstentions": 0}
    assert verdict["segments"] == [{"segment": "X", "winner": "A", "voters": 1,
                                    "margin": 1.0, "abstentions": 0}]
    assert verdict["hypothesis_id"] is None and verdict["variants"] == {}


def test_segmented_verdict_derivation(store):
    """The segmented verdict (ab_test protocol `segmented_verdict`): overall + per-segment winner,
    margin and abstentions, plus the hypothesis ref the verdict answers."""
    arch = [create_persona(store, f"Arch{i}", customer_type="Architect") for i in range(3)]
    eng = [create_persona(store, f"Eng{i}", customer_type="Engineer") for i in range(2)]
    proj = services.create_research_project("seg", goal="g", persona_ids=arch + eng, store=store)
    hyp = services.record_hypothesis(
        proj["id"], "B wins overall", {"metric": "preference_share", "expected_direction": "increase"},
        store=store)["hypothesis"]
    session = services.record_head_to_head(
        proj["id"], "A vs B", ["v1", "v2"],
        preferences=[{"persona_id": arch[0], "choice": "A"},
                     {"persona_id": arch[1], "choice": "A"},
                     {"persona_id": arch[2], "choice": "torn"},     # abstains
                     {"persona_id": eng[0], "choice": "B"},
                     {"persona_id": eng[1], "choice": "B"}],
        variant_meta={"hypothesis_id": hyp["id"], "variants": {"A": "v1", "B": "v2"}}, store=store)

    v = services.segmented_verdict(session["id"], store=store)
    assert v["overall"]["winner"] is None and v["overall"]["decisive"] == "tie"  # 2:2 with 1 out
    assert v["overall"]["voters"] == 4 and v["overall"]["abstentions"] == 1
    by_seg = {s["segment"]: s for s in v["segments"]}
    assert by_seg["Architect"] == {"segment": "Architect", "winner": "A", "voters": 2,
                                   "margin": 1.0, "abstentions": 1}
    assert by_seg["Engineer"]["winner"] == "B" and by_seg["Engineer"]["margin"] == 1.0
    assert v["hypothesis_id"] == hyp["id"]
    assert v["variants"]["B"] == {"id": "v2"}


# --------------------------------------------------------------------------- persistence + queryable seam

def test_head_to_head_persists_as_queryable_council(store):
    pid, [persona] = _project(store)
    session = services.record_head_to_head(
        pid, "A vs B", ["price one", "price two"],
        preferences=[{"persona_id": persona, "choice": "A", "reason": "cheaper"}],
        exec_summary="The host's verdict.", store=store)
    sid = session["id"]

    # It is a real CouncilSession (reuses council persistence + the project graph).
    assert services.is_head_to_head(session)
    fetched = services.get_council(sid, store=store)
    assert fetched["head_to_head"]["result"]["preference"] == "A"
    # Registered on its project so the project owns it (same as any council).
    proj = services.get_research_project(pid, store=store)
    assert sid in proj["council_ids"]

    # get_head_to_head returns the structured result directly.
    ht = services.get_head_to_head(sid, store=store)
    assert ht["result"]["preference"] == "A"
    assert ht["options"][0]["label"] == "A"

    # The result is ALSO a queryable finding (the analytics/calibration seam).
    from sonaloop import artifacts as _A
    kinds = [f.get("kind") for f in _A.council_statements(fetched)] + [f.get("kind") for f in fetched.get("findings", [])]
    assert "head_to_head" in kinds


def test_head_to_head_renders_in_the_inspector(store):
    """The inspector council page surfaces the head-to-head verdict (preference + margin) and the
    who-prefers-what segment table (German UI strings — match the surrounding language)."""
    from starlette.testclient import TestClient
    from sonaloop import web

    arch = [create_persona(store, f"Arch{i}", customer_type="Architect") for i in range(2)]
    eng = create_persona(store, "Eng", customer_type="Engineer")
    proj = services.create_research_project("render", goal="g", persona_ids=arch + [eng], store=store)
    session = services.record_head_to_head(
        proj["id"], "$29 vs $49?", ["$29/mo", "$49/mo"],
        preferences=[{"persona_id": arch[0], "choice": "A"}, {"persona_id": arch[1], "choice": "A"},
                     {"persona_id": eng, "choice": "B"}],
        exec_summary="Host verdict.", store=store)

    client = TestClient(web.create_app())
    html = client.get(f"/councils/{session['id']}?lang=de").text
    assert "Kopf-an-Kopf" in html                       # the head-to-head section title (German UI)
    assert "Präferenz" in html and "Vorsprung" in html  # preference + margin headline
    assert "Architect" in html and "Engineer" in html   # segment-split rows


def test_head_to_head_idempotent_on_key(store):
    pid, [persona] = _project(store)
    common = dict(prompt="A vs B", options=["o1", "o2"],
                  preferences=[{"persona_id": persona, "choice": "A"}], key="run1", store=store)
    s1 = services.record_head_to_head(pid, **common)
    s2 = services.record_head_to_head(pid, **common)
    assert s1["id"] == s2["id"]
    assert len([c for c in services.list_councils(store=store) if c["id"] == s1["id"]]) == 1
