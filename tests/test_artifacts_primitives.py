"""Phase 0 — unified artifact primitives (spec/unified-artifact-schema-rollout.md)."""
from __future__ import annotations

import json

from sonaloop import artifacts as A


def test_constructors_drop_empties_and_serialize():
    st = A.statement("p1", "hi")
    assert st == {"persona_id": "p1", "text": "hi"}          # empties (stance/about/refs/…) dropped
    assert json.loads(json.dumps(st)) == st                  # JSON round-trips
    f = A.finding("x", kind="key_problem")
    assert f == {"text": "x", "kind": "key_problem"}
    r = A.ref("memory", id="m1")
    assert r == {"kind": "memory", "id": "m1"}
    p = A.prompt("Q?")
    assert p == {"text": "Q?", "kind": "question"}


def test_full_statement_keeps_fields():
    st = A.statement("p1", "t", stance=A.stance(1), about=A.ref("council", id="c1"),
                     refs=[A.ref("memory", id="m1")], relevance="strong", meta={"input": "ctx"})
    assert st["stance"] == {"value": 1, "label": "conditional"}
    assert st["about"]["id"] == "c1" and st["refs"][0]["id"] == "m1"
    assert st["relevance"] == "strong" and st["meta"]["input"] == "ctx"


def test_session_ref_resolves_prototype_session_when_needed():
    class Store:
        def get_usability_session(self, _):
            return None

        def get_prototype_session(self, sid):
            return {"id": sid, "reaction": {"summary": "grounded"}, "created_at": "2026-06-16"}

    out = A.resolve_ref({"kind": "session", "id": "protosession_1"}, Store())
    assert out["exists"]
    assert out["href"] == "/sessions/protosession_1"


def test_stance_alias_resolution_covers_legacy_vocab():
    # every legacy vote/stance/sentiment token resolves to a canonical value
    cases = {"SUPPORT": 2, "dafür": 2, "positiv": 2, "MAYBE": 1, "bedingt": 1,
             "ABSTAIN": 0, "skeptisch": -1, "OPPOSE": -2, "dagegen": -2, "ablehnend": -2}
    for token, val in cases.items():
        assert A.resolve_stance(token)["value"] == val, token
    assert A.resolve_stance(2)["value"] == 2                 # numeric passthrough
    assert A.resolve_stance("")  is None                     # empty → None
    unknown = A.resolve_stance("totally-unknown")            # unknown → neutral VALUE, raw kept (visible)
    assert unknown == {"value": 0, "label": "neutral", "label_raw": "totally-unknown"}


def test_validate_stance_dict_path_canonicalizes_free_labels():
    # the host-authored dict path ({value, label}) resolves the label through the alias map —
    # no free label survives the validator (the `stance_mixed` inspector-chip bug)
    assert A.validate_stance({"value": 1, "label": "mixed"}) == {"value": 1, "label": "conditional"}
    # label/value disagreement → the explicit value wins for the canonical term
    assert A.validate_stance({"value": 2, "label": "mixed"}) == {"value": 2, "label": "support"}
    # unknown label → value decides, raw token preserved on the stance dict
    st = A.validate_stance({"value": -1, "label": "kinda meh"})
    assert st == {"value": -1, "label": "skeptical", "label_raw": "kinda meh"}
    assert A.validate_stance(st) == st                       # re-validation is idempotent (read-normalizer)
    # already-canonical stored records read back unchanged
    assert A.validate_stance({"value": 1, "label": "conditional"}) == {"value": 1, "label": "conditional"}


def test_validate_stance_off_scale_values_never_lose_signal():
    # an off-scale value is an invalid signal: a resolvable label decides instead, the value survives raw
    assert A.validate_stance({"value": 7, "label": "mixed"}) == \
        {"value": 1, "label": "conditional", "value_raw": 7}
    # no usable label → clamp to the nearest endpoint, value survives raw
    assert A.validate_stance({"value": 7}) == {"value": 2, "label": "support", "value_raw": 7}
    assert A.resolve_stance(-5) == {"value": -2, "label": "oppose", "value_raw": -5}
    # off-scale value AND unresolvable label → both raw signals survive
    st = A.validate_stance({"value": 9, "label": "kinda meh"})
    assert st == {"value": 2, "label": "support", "value_raw": 9, "label_raw": "kinda meh"}
    assert A.validate_stance(st) == st                       # re-validation is idempotent (read-normalizer)
    # the stored value is always on-scale → stance_meta/charts can never miss a bucket
    assert A.stance_meta(A.validate_stance({"value": 7})["value"])["label_key"] == "stance_support"


def test_stance_display_labels_round_trip_via_aliases():
    # echoing the system's own EN/DE display labels (web/_i18n.py stance_*) must not corrupt the scale —
    # the labels are read from i18n so the aliases can never drift from what the UI shows
    from sonaloop.web._i18n import STRINGS
    expect = {"stance_support": 2, "stance_conditional": 1, "stance_neutral": 0,
              "stance_skeptical": -1, "stance_oppose": -2}
    for lang in ("en", "de"):
        for key, val in expect.items():
            st = A.validate_stance(STRINGS[lang][key])
            assert st["value"] == val and "label_raw" not in st, (lang, key)
    assert A.resolve_stance("  skeptical / OPPOSED ")["value"] == -1   # case/whitespace-insensitive lookup
    # retired bucket labels (the old stance_positive/stance_other UI keys) still resolve via aliases —
    # a host echoing the historic display wording must not corrupt the scale
    assert A.validate_stance("Positiv / begeistert")["value"] == 2
    assert A.validate_stance("Positive / enthusiastic")["value"] == 2


def test_stance_meta_is_data_driven():
    m = A.stance_meta(2)
    assert m["label_key"] == "stance_support" and m["color"]
    assert A.stance_meta(-2)["label_key"] == "stance_oppose"


def test_finding_kind_lookup_and_fallback():
    assert A.finding_kind("key_problem")["id"] == "keyproblems"
    assert A.finding_kind("recommendation")["label_key"] == "recommendations"
    inv = A.finding_kind("totally-new-kind")                 # invented kind → generic, no code change
    assert inv["id"] == "totally-new-kind" and inv["label_key"] == "totally-new-kind"


def test_finding_kind_label_keys_exist_in_i18n():
    from sonaloop.web._i18n import STRINGS
    de = STRINGS["de"]
    for kind in ("summary", "key_problem", "pain_solver", "open_question", "recommendation",
                 "cluster", "segment", "shortlist", "ranking"):
        assert A.finding_kind(kind)["label_key"] in de


def test_stance_label_keys_exist_in_i18n():
    from sonaloop.web._i18n import STRINGS
    de = STRINGS["de"]
    for v in (-2, -1, 0, 1, 2):
        assert A.stance_meta(v)["label_key"] in de


def test_event_primitive_and_pain_point_finding():
    e = A.event("p1", "2026-01-01", kind="experience", body="did X", refs=[A.ref("memory", id="m1")])
    assert e == {"persona_id": "p1", "time": "2026-01-01", "kind": "experience", "body": "did X",
                 "refs": [{"kind": "memory", "id": "m1"}]}
    assert A.validate_event({"persona_id": "p1", "time": "t", "kind": "k", "body": "b"})["kind"] == "k"
    # PainPointObservation → persona-scoped Finding (Layer 3, §5b)
    f = A.pain_point_finding({"issue": "slow", "opportunity": "speed it up", "severity": 4,
                              "frequency": 3, "evidence_event_ids": ["e1"]})
    assert f["kind"] == "pain_point" and f["text"] == "slow"
    assert f["score"] == {"severity": 4, "frequency": 3} and f["meta"]["detail"] == "speed it up"
    assert f["refs"][0] == {"kind": "memory", "id": "e1"}
    assert A.finding_kind("pain_point")["id"] == "pains"
