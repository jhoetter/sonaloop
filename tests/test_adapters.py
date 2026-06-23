"""Phase 1 — record→primitive adapters (spec/unified-artifact-schema-rollout.md §1A)."""
from __future__ import annotations

from sonaloop import artifacts as A


def test_council_prompts_built_from_canonical_fields():
    # prompts are derived from the council's canonical question/proposal fields (not compatibility)
    c = {"prompt": "P?", "questions": ["q0?", "q1?"], "proposal": ""}
    assert [p["id"] for p in A.council_prompts(c)] == ["prompt", "q0", "q1"]


def test_session_adapter_one_statement_with_refs():
    se = {"persona_id": "p1", "observed_state_refs": ["saw X"], "grounded_verified": True,
          "reaction": {"persona": "Aylin", "verdict": "**good**", "focus": "does it work?",
                       "fidelity": "hi-fi", "version": "v0.2"}}
    sts = A.session_statements(se)
    assert len(sts) == 1
    assert sts[0]["text"] == "**good**"                       # markdown kept (rendered later via _prose)
    assert sts[0]["refs"][0] == {"kind": "prototype_state", "text": "saw X"}
    assert sts[0]["about"] == {"kind": "prompt", "id": "focus"}   # focus → the prompt banner
    assert sts[0]["meta"]["grounded"] is True and "hi-fi" in sts[0]["meta"]["context"]
    assert "focus" not in sts[0]["meta"]                      # focus is the banner now, not a card line
    assert A.session_focus(se) == "does it work?"


def test_adapters_prefer_native_primitive_fields():
    # forward-compat: if a record already carries primitives, the adapter returns them verbatim
    native = [A.statement("p9", "native")]
    assert A.council_statements({"statements": native, "turns": [{"persona_id": "x", "content": "y"}]}) == native
    assert A.synthesis_findings({"findings": [A.finding("f", kind="risk")], "key_problems": ["ignored"]})[0]["kind"] == "risk"


def test_heal_text_decodes_literal_unicode_escapes():
    # Owner round 5: a council title authored by a remote agent on a sibling store surfaced
    # the LITERAL "–" instead of "–". heal_text decodes at read time.
    assert A.heal_text("Premium \\u2013 Pricing") == "Premium – Pricing"
    # surrogate pairs re-join; text without the pattern passes through untouched (no decode pass)
    assert A.heal_text("\\ud83d\\ude00 ok") == "\U0001f600 ok"
    assert A.heal_text("plain – text") == "plain – text"
    assert A.heal_text("") == ""
    # a malformed escape never raises and never mangles the rest
    assert A.heal_text("broken \\uZZZZ tail") == "broken \\uZZZZ tail"


def test_council_prompts_heal_literal_escapes():
    c = {"prompt": "Caf\\u00e9 \\u2013 pricing?", "questions": [], "proposal": ""}
    assert A.council_prompts(c)[0]["text"] == "Café – pricing?"


def test_store_read_layer_heals_title_fields(store):
    # the heal applies where the PAGES read (storage get/list) — title/prompt fields only;
    # the stored bytes stay untouched.
    store.insert_council_session({
        "id": "c-esc", "created_at": "2026-06-01T00:00:00+00:00",
        "prompt": "Launch \\u2013 review", "persona_ids": [], "votes": [],
        "summary": "", "exec_summary": "", "selection_reason": "", "proposal": ""})
    assert store.get_council_session("c-esc")["prompt"] == "Launch – review"
    assert store.list_council_sessions()[0]["prompt"] == "Launch – review"
    store.upsert_synthesis({"id": "s-esc", "title": "Findings \\u2013 wave 1",
                            "created_at": "2026-06-01T00:00:00+00:00"})
    assert store.get_synthesis("s-esc")["title"] == "Findings – wave 1"
    assert store.list_syntheses()[0]["title"] == "Findings – wave 1"
