"""Council votes are unified onto the stance scale (suggestions/stance_scale.json — the ONE
positivity vocabulary). Guards the invariants:
  - record_council normalizes every vote through the scale (canonical `vote` term + a `stance`
    {value,label}; an unresolvable token survives as stance.label_raw — never silently dropped).
  - the vote charts bucket by stance VALUE in scale order (+2 → −2) with scale colors/labels —
    all five terms representable, so a "conditional" vote can no longer vanish from the charts.
  - the web stance distribution is ONE encoding (ux-contract §10 W9 + §11 T5): the scaled
    stance BARS — no donut and no proportional strip re-encoding the same distribution
    (the deck keeps its single donut card).
  - compatibility stored uppercase tokens (SUPPORT/MAYBE/ABSTAIN/OPPOSE) chart identically via the aliases.
  - the per-persona score is the MEAN of the resolved stance values (−2..+2), its color the nearest
    scale value's — no token-specific coefficients, no label-keyword matching.
"""
from __future__ import annotations

from sonaloop import artifacts as A
from sonaloop import services
from sonaloop.web._i18n import t
from sonaloop.web._synthesis import _personas_by_sentiment_html, _vote_parts


def _sessions(votes):
    return [{"votes": [{"persona_id": "p1", "vote": v} for v in votes]}]


def test_record_council_normalizes_votes_onto_the_scale(store):
    pid = services.start_project("M", "hmw?", None, persona_ids=[], store=store)["id"]
    c = services.record_council(pid, "Bauen?", [], [], proposal="X", store=store, key="v",
                                votes=[{"persona_id": "pa", "vote": "MAYBE"},
                                       {"persona_id": "pb", "vote": "lieber nicht??"}])
    v1, v2 = c["votes"]
    # compatibility token → canonical term + resolved stance; the reader-compatible shape is kept
    assert v1["persona_id"] == "pa" and v1["vote"] == "conditional"
    assert v1["stance"] == {"value": 1, "label": "conditional"}
    # unresolvable token → neutral VALUE bucket, the raw token traced — never silently dropped
    assert v2["vote"] == "neutral"
    assert v2["stance"] == {"value": 0, "label": "neutral", "label_raw": "lieber nicht??"}


def test_conditional_vote_appears_in_the_distribution():
    # "conditional" — the canonical stance term! — used to be dropped from legend/stacked bars
    tot, parts = _vote_parts(_sessions(["conditional"]))
    assert tot[1] == 1
    cnt, color, label = next(p for p in parts if p[0] == 1)
    assert color == A.stance_meta(1)["color"] and label == t(A.stance_meta(1)["label_key"])


def test_compatibility_uppercase_votes_bucket_identically():
    # the pre-change stored shape: uppercase tokens in `vote`, no stance sub-dict
    tot, parts = _vote_parts(_sessions(["SUPPORT", "SUPPORT", "MAYBE", "ABSTAIN", "OPPOSE"]))
    assert dict(tot) == {2: 2, 1: 1, 0: 1, -2: 1}                  # token → value bucket via aliases
    assert [c for c, _, _ in parts] == [2, 1, 1, 0, 1]             # scale order +2 → −2, all five terms
    assert [c for _, c, _ in parts] == [A.stance_meta(v)["color"] for v in (2, 1, 0, -1, -2)]


def test_unresolvable_vote_token_does_not_vanish_from_the_charts():
    tot, parts = _vote_parts(_sessions(["banana!!"]))
    assert tot[0] == 1                                             # neutral value bucket (label_raw path)
    assert sum(c for c, _, _ in parts) == 1


def test_persona_score_is_the_mean_of_stance_values(store):
    html = _personas_by_sentiment_html(store, _sessions(["SUPPORT", "conditional", "OPPOSE"]))
    assert "+0.3" in html                                          # mean(+2, +1, −2) = +0.333
    # 0.33 sits nearest the neutral scale value → its color (value bucket, not keyword matching)
    assert f'color:{A.stance_meta(0)["color"]}' in html


def test_vote_tally_keys_are_canonical_terms():
    tally = A.vote_tally([{"vote": "SUPPORT"}, {"vote": "conditional"}, {"vote": ""}])
    assert tally == {"support": 1, "conditional": 1, "neutral": 0, "skeptical": 0, "oppose": 0}
    assert list(tally) == ["support", "conditional", "neutral", "skeptical", "oppose"]   # +2 → −2


def test_web_stance_bars_are_the_single_encoding():
    # §11 T5 (J1 decided, finishing W9's spirit): the council/synthesis sentiment blocks carry
    # ONE distribution encoding — the scaled stance BARS (length ∝ count). The proportional
    # strip + legend that co-encoded the same numbers retired with the donut (the DECK keeps
    # its single donut card — services/_synthesis_pptx, deliberately untouched).
    import sonaloop.web._synthesis as S
    assert not hasattr(S, "_overview_html")
    sess = {"votes": [], "statements": [
        {"persona_id": "p1", "text": "x", "stance": {"value": 2, "label": "support"}},
        {"persona_id": "p2", "text": "y", "stance": {"value": 2, "label": "support"}},
        {"persona_id": "p3", "text": "z", "stance": {"value": -2, "label": "oppose"}}]}
    html = str(S._dist_bars([sess]))
    assert 'class="brow"' in html and html.count("btrack") == 2          # bars, one per stance bucket
    assert 'class="stacked"' not in html and 'class="legend"' not in html
    assert "donut" not in html and "conic-gradient" not in html
    # statements without stances → the votes still chart ONCE (votes ARE stances)
    html2 = str(S._dist_bars(_sessions(["SUPPORT", "OPPOSE"])))
    assert 'class="brow"' in html2 and 'class="stacked"' not in html2


def test_council_and_synthesis_pages_carry_no_distribution_strip(store):
    # the page-level strip is gone end-to-end: council detail opener + sentiment block render no
    # .stacked strip; the bars remain. (On the synthesis the only strips left are the per-council
    # COMPARISON strips on the cited-council reference rows — pinned in the Round-5 test below.)
    from sonaloop import services
    pid = services.start_project("M", "hmw?", None, persona_ids=[], store=store)["id"]
    c = services.record_council(pid, "Bauen?", [], [], proposal="X", store=store, key="t5",
                                votes=[{"persona_id": "pa", "vote": "SUPPORT"},
                                       {"persona_id": "pb", "vote": "OPPOSE"}])
    from sonaloop.web import create_app
    from starlette.testclient import TestClient
    client = TestClient(create_app())
    page = client.get(f"/councils/{c['id']}").text
    assert 'class="stacked' not in page and 'class="brow"' in page


def test_synthesis_page_names_each_cited_council_once(store):
    # Round 5 finish: the cited-councils reference rows are the ONE place the chain's councils
    # are named — the per-council breakdown rows that named the same councils a second time
    # retired; their comparison strip (>1 cited councils = N DIFFERENT distributions) rides the
    # reference rows instead, and the charts row is ONE full-width card (no half-width orphan).
    from sonaloop import services
    pid = services.start_project("M", "hmw?", None, persona_ids=[], store=store)["id"]
    c1 = services.record_council(pid, "Erster Council?", [], [], proposal="X", store=store,
                                 key="r5a", votes=[{"persona_id": "pa", "vote": "SUPPORT"}])
    c2 = services.record_council(pid, "Zweiter Council?", [], [], proposal="X", store=store,
                                 key="r5b", votes=[{"persona_id": "pb", "vote": "OPPOSE"}])
    syn = services.record_synthesis("S", "hmw", [c1["id"], c2["id"]],
                                    {"gesamtbild": "One short answer."}, store=store)
    from sonaloop.web import create_app
    from starlette.testclient import TestClient
    page = TestClient(create_app()).get(f"/syntheses/{syn['id']}").text
    # each cited council is linked + named exactly once: its reference row
    assert page.count('class="ref-row"') == 2
    assert page.count(f'/councils/{c1["id"]}') == 1 and page.count(f'/councils/{c2["id"]}') == 1
    assert page.count('class="stacked thin"') == 2            # the comparison rides the ref rows
    # one full-width insight card — the 2-col grid that beached the lone card half-width retired
    assert 'class="insights"' not in page and page.count('class="insight"') == 1


def test_verdict_headline_never_ellipsizes_mid_sentence():
    # Round 5 finish: a long first key_problem used to hard-truncate at 180 chars with '…'. The
    # headline now ends at a clean clause boundary (the full finding still renders verbatim in
    # its findings section) or — boundary-less — renders whole and wraps within the measure.
    from sonaloop.web._synthesis import _headline
    short = "The €29 dead zone"
    assert _headline(short) == short                            # short → whole, untouched
    long = ("The €29 dead zone: a single mid-price tier is too expensive for the reach segments "
            "(ladder acceptance 0.4) and too thin to carry the coaching that justifies the trust "
            "segments' expectations across every cohort we asked in the study.")
    assert _headline(long) == "The €29 dead zone" and "…" not in _headline(long)
    two = "First sentence ends here. Second sentence carries on for quite a while afterwards."
    assert _headline(two, cap=40) == "First sentence ends here."
    # the _verdict_split guard carries over: '+40 Min. wegen …' is an abbreviation, not a cut —
    # and with no clean boundary inside the cap the FULL headline wraps instead of ellipsizing
    de = ("Das Fenster rutscht sichtbar nach hinten, +40 Min. wegen eskalierender Kundenabgabe, "
          "und bleibt damit für alle Beteiligten nachvollziehbar im Team verankert.")
    assert _headline(de, cap=80) == de
