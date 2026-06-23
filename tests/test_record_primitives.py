"""Phase 2 — native primitive authoring round-trips + dual-read (spec/unified-…-rollout.md §2)."""
from __future__ import annotations

from sonaloop import services, artifacts as A
from sonaloop.web import _render as R


def test_council_native_primitives_roundtrip_and_render(store):
    proj = services.create_research_project("P", store=store)
    res = services.record_council(
        proj["id"], "Q?", ["persona_x"],
        statements=[{"persona_id": "persona_x", "text": "**hi**", "stance": {"value": 1},
                     "about": {"kind": "prompt", "id": "q0"}, "refs": [{"kind": "memory", "text": "m"}]}],
        findings=[{"text": "the **finding**", "kind": "summary"}],
        prompts=[{"text": "Q?", "kind": "question", "id": "q0"}], key="k1", store=store)
    c = store.get_council_session(res["id"])
    # persisted natively (validated through the constructors)
    assert c["statements"][0]["text"] == "**hi**" and c["statements"][0]["stance"] == {"value": 1, "label": "conditional"}
    assert c["findings"][0]["kind"] == "summary" and c["prompts"][0]["id"] == "q0"
    # adapter PREFERS the native fields (dual-read)
    assert A.council_statements(c) == c["statements"]
    # renders through the one renderer (markdown applied)
    assert "<strong>" in R.render_statements(A.council_statements(c), store)


def test_synthesis_native_primitives_via_payload(store):
    res = services.record_synthesis(
        "Deliver", "in", goal="g", council_ids=[],
        payload={"statements": [{"persona_id": "p1", "text": "voice", "stance": {"value": -2}}],
                 "findings": [{"text": "kp", "kind": "key_problem"}],
                 "prompts": [{"text": "goal", "kind": "goal", "id": "goal"}]},
        key="s1", store=store)
    s = store.get_synthesis(res["id"])
    assert s["statements"][0]["stance"]["label"] == "oppose"
    assert s["findings"][0]["kind"] == "key_problem"
    # dual-read: adapter returns the native statements/findings verbatim
    assert A.synthesis_statements(s) == s["statements"]
    assert A.synthesis_findings(s) == s["findings"]


def test_council_primitives_only_no_turns(store):
    """Authoring is primitives-only: statements are stored, there is no compatibility `turns` field."""
    proj = services.create_research_project("L", store=store)
    res = services.record_council(proj["id"], "Q?", ["p1"],
                                  statements=[{"persona_id": "p1", "text": "an answer"}], key="k2", store=store)
    c = store.get_council_session(res["id"])
    assert "turns" not in c                            # compatibility field gone
    assert c["statements"][0]["text"] == "an answer"
    assert A.council_statements(c) == c["statements"]
