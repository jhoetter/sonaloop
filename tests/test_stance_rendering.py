"""Stance rendering is VALUE-driven — the data-driven scale, never label-keyword heuristics.

Guards the `stance_mixed` bug class: every stored Stance carries a canonical value (-2..+2); the web
layer derives chip label, color and distribution bucket from that value via artifacts.stance_meta.
Stored label strings (compatibility free labels, `label_raw` host tokens) never pick an i18n key or a bucket.
"""
from __future__ import annotations

from sonaloop import artifacts as A
from sonaloop.web._i18n import t
from sonaloop.web._render import render_stance
from sonaloop.web._synthesis import _stance_dist_html


def test_compatibility_free_label_renders_the_canonical_chip_from_its_value():
    # constructed dict bypassing the validator — the pre-normalization stored shape
    html = render_stance({"value": 1, "label": "mixed"})
    assert t(A.stance_meta(1)["label_key"]) in html
    assert A.stance_meta(1)["color"] in html
    assert "stance_" not in html                  # no raw i18n key ever reaches the UI


def test_label_raw_renders_canonical_label_with_the_raw_token_as_tooltip():
    html = render_stance({"value": -1, "label": "skeptical", "label_raw": "kinda meh"})
    assert t(A.stance_meta(-1)["label_key"]) in html
    assert 'title="kinda meh"' in html            # the raw host token stays visible, honestly
    assert "stance_" not in html


def _sessions(values):
    return [{"statements": [{"persona_id": f"p{i}", "text": "x", "stance": {"value": v}}
                            for i, v in enumerate(values)]}]


def test_distribution_buckets_match_value_buckets_for_all_canonical_terms():
    html = _stance_dist_html(_sessions([-2, -1, 0, 1, 2]))
    for v in (-2, -1, 0, 1, 2):
        meta = A.stance_meta(v)
        assert t(meta["label_key"]) in html and meta["color"] in html
    assert "stance_" not in html                  # labels resolve through t(), never raw keys


def test_oppose_lands_in_its_own_bucket_not_skepticals():
    html = _stance_dist_html(_sessions([-2]))
    assert t(A.stance_meta(-2)["label_key"]) in html
    assert t(A.stance_meta(-1)["label_key"]) not in html
    assert A.stance_meta(-2)["color"] in html
