"""Surveys — the outbound instrument (author → export sendable form → import real responses).

Model validation (derived_from refs must resolve; stance_mapped scales must map cleanly onto
stance_scale.json), the export-form payload shape round-tripping through import (JSON + CSV),
the per-question aggregation math incl. the predicted-vs-actual comparison, the evidence
loop-back (source_type='survey'), and the inspector detail page.
"""
from __future__ import annotations

import json

import pytest

from conftest import create_persona
from sonaloop import artifacts, services


def _project(store, title="Pension awareness"):
    return services.create_research_project(title, goal="How do people plan retirement?",
                                            store=store)


# A stance_mapped scale: every option is a canonical term or a declared alias of one.
_SCALE_OPTS = ["oppose", "skeptical", "neutral", "conditional", "support"]


def _questions():
    return [
        {"id": "q1", "text": "How do you save for retirement today?", "kind": "single",
         "options": ["Not at all", "Bank savings", "Stocks/ETF", "Insurance product"]},
        {"id": "q2", "text": "Which channels do you use?", "kind": "multi",
         "options": ["App", "Branch", "Phone", "Mail"]},
        {"id": "q3", "text": "A digital pension check would help me.", "kind": "scale",
         "options": list(_SCALE_OPTS), "stance_mapped": True},
        {"id": "q4", "text": "What would make you switch?", "kind": "text"},
    ]


def _record(store, project_id, **kw):
    args = {"title": "Retirement readiness", "questions": _questions(),
            "intro": "Five minutes, anonymous."}
    args.update(kw)
    return services.record_survey(project_id, store=store, **args)["survey"]


def _council_with_stances(store, project_id, values):
    pid = create_persona(store, "Stancy Source")
    statements = [{"persona_id": pid, "text": f"view {i}", "stance": {"value": v}}
                  for i, v in enumerate(values)]
    return services.record_council(project_id, "Would a digital pension check help?", [pid],
                                   statements=statements, summary="mixed", store=store)


def _form_payload(survey, *, key="r_abc123", value="support"):
    """A payload shaped EXACTLY like the export form's submission (= a SurveyResponse row)."""
    return {"id": "", "survey_id": survey["id"], "respondent_key": key,
            "submitted_at": "2026-06-10T10:00:00Z",
            "answers": [{"question_id": "q1", "value": "Stocks/ETF"},
                        {"question_id": "q2", "value": ["App", "Mail"]},
                        {"question_id": "q3", "value": value},
                        {"question_id": "q4", "value": "lower fees"}],
            "source": "html_form"}


# --------------------------------------------------------------- record: validation + persistence

def test_record_get_roundtrip_and_slug(store):
    proj = _project(store)
    s = _record(store, proj["id"])
    got = services.get_survey(s["slug"], store=store)        # readable by slug AND id
    assert got["id"] == s["id"] and got["title"] == "Retirement readiness"
    assert got["status"] == "draft" and got["response_count"] == 0
    assert [q["id"] for q in got["questions"]] == ["q1", "q2", "q3", "q4"]
    assert got["questions"][2]["stance_mapped"] is True
    assert services.get_survey(s["id"], store=store)["slug"] == s["slug"]
    with pytest.raises(KeyError):
        services.get_survey("survey_missing", store=store)


def test_rerecording_the_same_slug_updates_in_place(store):
    proj = _project(store)
    s1 = _record(store, proj["id"])
    s2 = _record(store, proj["id"], intro="Now with a better intro.")
    assert s2["id"] == s1["id"] and s2["created_at"] == s1["created_at"]
    assert len(services.list_surveys(store=store)) == 1
    assert services.list_surveys(proj["id"], store=store)[0]["intro"] == "Now with a better intro."


def test_question_shape_validation(store):
    proj = _project(store)

    def rec(qs):
        return services.record_survey(proj["id"], "T", qs, store=store)

    with pytest.raises(ValueError, match="non-empty list"):
        rec([])
    with pytest.raises(ValueError, match="kind"):
        rec([{"text": "x", "kind": "ranking", "options": ["a", "b"]}])
    with pytest.raises(ValueError, match=">= 2"):
        rec([{"text": "x", "kind": "single", "options": ["only"]}])
    with pytest.raises(ValueError, match="duplicate options"):
        rec([{"text": "x", "kind": "single", "options": ["a", "a"]}])
    with pytest.raises(ValueError, match="takes no options"):
        rec([{"text": "x", "kind": "text", "options": ["a", "b"]}])
    with pytest.raises(ValueError, match="unique"):
        rec([{"id": "q1", "text": "x", "kind": "text"}, {"id": "q1", "text": "y", "kind": "text"}])
    with pytest.raises(ValueError, match="status"):
        services.record_survey(proj["id"], "T", _questions(), status="archived", store=store)
    with pytest.raises(KeyError):
        services.record_survey("rproject_missing", "T", _questions(), store=store)


def test_stance_mapped_must_map_cleanly_onto_the_canonical_scale(store):
    proj = _project(store)
    # only a scale question may be stance_mapped
    with pytest.raises(ValueError, match="only valid on a scale"):
        services.record_survey(proj["id"], "T", [{"text": "x", "kind": "single",
                                                  "options": ["a", "b"], "stance_mapped": True}],
                               store=store)
    # an option that doesn't resolve onto the scale is rejected (no silent neutral-bucketing)
    with pytest.raises(ValueError, match="does not map onto"):
        services.record_survey(proj["id"], "T", [{"text": "x", "kind": "scale",
                                                  "options": ["support", "meh-ish"],
                                                  "stance_mapped": True}], store=store)
    # two options landing on the SAME stance value make the mapping ambiguous — rejected
    with pytest.raises(ValueError, match="both map onto"):
        services.record_survey(proj["id"], "T", [{"text": "x", "kind": "scale",
                                                  "options": ["support", "SUPPORT"],
                                                  "stance_mapped": True}], store=store)
    # declared aliases (incl. the DE display labels in stance_scale.json) map cleanly
    ok = services.record_survey(proj["id"], "T", [{"text": "x", "kind": "scale",
                                                   "options": ["dagegen", "skeptisch", "neutral",
                                                               "bedingt", "dafür"],
                                                   "stance_mapped": True}], store=store)
    assert ok["survey"]["questions"][0]["stance_mapped"] is True
    # the same options without stance_mapped are fine — no scale constraint applies
    free = services.record_survey(proj["id"], "T2", [{"text": "x", "kind": "scale",
                                                      "options": ["meh-ish", "great-ish"]}],
                                  store=store)
    assert free["survey"]["questions"][0]["stance_mapped"] is False


def test_derived_from_refs_must_resolve(store):
    proj = _project(store)
    with pytest.raises(ValueError, match="does not resolve"):
        _record(store, proj["id"], derived_from=[{"kind": "council", "id": "council_missing"}])
    with pytest.raises(ValueError, match="unknown open question"):
        _record(store, proj["id"], derived_from=[{"kind": "open_question", "id": "oq_missing"}])
    with pytest.raises(ValueError, match="needs an id"):
        _record(store, proj["id"], derived_from=[{"kind": "external", "text": "a hunch"}])
    # an unresolvable KIND rejects the same way (resolve_ref has no getter for it)
    with pytest.raises(ValueError, match="does not resolve"):
        _record(store, proj["id"], derived_from=[{"kind": "vibes", "id": "x1"}])


def test_derived_from_resolves_councils_and_open_questions(store):
    proj = _project(store)
    council = _council_with_stances(store, proj["id"], [2, -1])
    oq = services.record_open_questions(proj["id"], ["What stops non-savers?"], store=store)[0]
    s = _record(store, proj["id"],
                derived_from=[{"kind": "council", "id": council["id"]},
                              {"kind": "open_question", "id": oq["id"]}])
    refs = s["derived_from"]
    assert [r["kind"] for r in refs] == ["council", "open_question"]
    assert all(r["role"] == "derived_from" for r in refs)
    assert refs[1]["quote"] == "What stops non-savers?"       # cached display hint for the chip
    # the council ref resolves LIVE through the shared resolver (the chips use this)
    assert artifacts.resolve_ref(refs[0], store)["exists"] is True


# --------------------------------------------------------------- export: the sendable form

def test_export_emits_self_contained_form_and_opens_the_survey(store, tmp_path, monkeypatch):
    from sonaloop import config
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    proj = _project(store)
    s = _record(store, proj["id"])
    out = services.export_survey(s["id"], post_url="https://collect.example/s1", store=store)
    html = (tmp_path / "exports" / "surveys" / f'{s["slug"]}.html').read_text(encoding="utf-8")
    assert out["path"].endswith(f'{s["slug"]}.html')
    # self-contained: the full instrument + runtime ride inside; no external fetches needed
    concept = json.loads(html.split('<script id="concept" type="application/json">', 1)[1]
                         .split("</script>", 1)[0].replace("<\\/", "</"))
    assert concept["survey"]["id"] == s["id"]
    assert [q["id"] for q in concept["survey"]["questions"]] == ["q1", "q2", "q3", "q4"]
    assert concept["post_url"] == "https://collect.example/s1"
    assert 'src="http' not in html and "href=\"http" not in html
    # the runtime builds the SurveyResponse-shaped payload (download or POST)
    for marker in ("respondent_key", "submitted_at", "question_id", "survey-response-"):
        assert marker in html
    # sending it out flips draft → open
    assert out["status"] == "open"
    assert services.get_survey(s["id"], store=store)["status"] == "open"


# --------------------------------------------------------------- import: round-trip + validation

def test_form_payload_roundtrips_through_import(store):
    proj = _project(store)
    s = _record(store, proj["id"])
    out = services.import_survey_responses(
        s["id"], [_form_payload(s), _form_payload(s, key="r_def456", value="skeptical")],
        store=store)
    assert out["imported"] == 2 and out["total_responses"] == 2
    rows = store.list_survey_responses(s["id"])
    assert {r["respondent_key"] for r in rows} == {"r_abc123", "r_def456"}
    assert all(r["survey_id"] == s["id"] and r["source"] == "html_form" for r in rows)
    assert rows[0]["answers"][1] == {"question_id": "q2", "value": ["App", "Mail"]}
    # re-importing the SAME batch is idempotent (deterministic ids), not a double count
    again = services.import_survey_responses(s["id"], [_form_payload(s)], store=store)
    assert again["total_responses"] == 2
    assert services.get_survey(s["id"], store=store)["response_count"] == 2


def test_csv_batch_imports_with_multi_split(store):
    proj = _project(store)
    s = _record(store, proj["id"])
    csv_text = (
        "respondent_key,submitted_at,q1,q2,q3,q4\n"
        "p1,2026-06-09T09:00:00Z,Bank savings,App;Branch,neutral,\n"
        "p2,2026-06-09T10:00:00Z,Not at all,Phone,oppose,too complicated\n")
    out = services.import_survey_responses(s["id"], csv_text=csv_text, source="street-panel",
                                           store=store)
    assert out["imported"] == 2
    rows = {r["respondent_key"]: r for r in store.list_survey_responses(s["id"])}
    assert rows["p1"]["answers"][1]["value"] == ["App", "Branch"]
    assert rows["p1"]["source"] == "street-panel"
    assert {a["question_id"] for a in rows["p1"]["answers"]} == {"q1", "q2", "q3"}  # empty q4 skipped
    with pytest.raises(ValueError, match="not a question id"):
        services.import_survey_responses(s["id"], csv_text="respondent_key,q9\np3,x\n", store=store)


def test_import_validates_answers_against_the_instrument(store):
    proj = _project(store)
    s = _record(store, proj["id"])
    base = _form_payload(s)
    bad_q = {**base, "answers": [{"question_id": "q99", "value": "x"}]}
    with pytest.raises(ValueError, match="unknown question"):
        services.import_survey_responses(s["id"], [bad_q], store=store)
    off_option = {**base, "answers": [{"question_id": "q1", "value": "Crypto"}]}
    with pytest.raises(ValueError, match="not an option"):
        services.import_survey_responses(s["id"], [off_option], store=store)
    off_multi = {**base, "answers": [{"question_id": "q2", "value": ["App", "Fax"]}]}
    with pytest.raises(ValueError, match="not in the options"):
        services.import_survey_responses(s["id"], [off_multi], store=store)
    with pytest.raises(ValueError, match="non-empty list"):
        services.import_survey_responses(s["id"], [{**base, "answers": []}], store=store)
    with pytest.raises(ValueError, match="nothing to import"):
        services.import_survey_responses(s["id"], store=store)
    with pytest.raises(KeyError):
        services.import_survey_responses("survey_missing", [base], store=store)
    # a failing row anywhere rejects the WHOLE batch before any write
    with pytest.raises(ValueError):
        services.import_survey_responses(s["id"], [_form_payload(s, key="r_new"), bad_q], store=store)
    assert store.count_survey_responses(s["id"]) == 0


# --------------------------------------------------------------- aggregation + predicted-vs-actual

def test_results_aggregate_per_question(store):
    proj = _project(store)
    s = _record(store, proj["id"])
    services.import_survey_responses(s["id"], [
        _form_payload(s, key="r1", value="support"),
        _form_payload(s, key="r2", value="support"),
        {**_form_payload(s, key="r3", value="skeptical"),
         "answers": [{"question_id": "q1", "value": "Not at all"},
                     {"question_id": "q3", "value": "skeptical"}]},
    ], store=store)
    res = services.survey_results(s["id"], store=store)
    assert res["responses"] == 3 and res["respondents"] == 3
    by_q = {q["question_id"]: q for q in res["questions"]}
    assert by_q["q1"]["counts"] == {"Not at all": 1, "Bank savings": 0, "Stocks/ETF": 2,
                                    "Insurance product": 0}
    assert by_q["q2"]["counts"] == {"App": 2, "Branch": 0, "Phone": 0, "Mail": 2}
    assert by_q["q2"]["answered"] == 2                       # r3 skipped q2
    assert by_q["q4"]["answers"] == ["lower fees", "lower fees"]


def test_predicted_vs_actual_for_stance_mapped_questions(store):
    proj = _project(store)
    # the council PREDICTED: 2× support, 1× skeptical, 1× oppose
    council = _council_with_stances(store, proj["id"], [2, 2, -1, -2])
    s = _record(store, proj["id"], derived_from=[{"kind": "council", "id": council["id"]}])
    # reality ANSWERED: 1× support, 2× skeptical
    services.import_survey_responses(s["id"], [
        _form_payload(s, key="r1", value="support"),
        _form_payload(s, key="r2", value="skeptical"),
        _form_payload(s, key="r3", value="skeptical"),
    ], store=store)
    res = services.survey_results(s["id"], store=store)
    q3 = next(q for q in res["questions"] if q["question_id"] == "q3")
    comp = q3["comparison"]
    assert comp["predicted"]["counts"] == {"support": 2, "conditional": 0, "neutral": 0,
                                           "skeptical": 1, "oppose": 1}
    assert comp["predicted"]["n"] == 4
    assert comp["predicted"]["refs"] == [{"kind": "council", "id": council["id"],
                                          "role": "predicted_by"}]
    assert comp["actual"]["counts"] == {"support": 1, "conditional": 0, "neutral": 0,
                                        "skeptical": 2, "oppose": 0}
    assert comp["actual"]["n"] == 3
    # every canonical term is present in both tallies (legend-stable, scale-driven)
    terms = [t["term"] for t in artifacts.stance_terms()]
    assert list(comp["predicted"]["counts"]) == terms == list(comp["actual"]["counts"])
    # non-stance-mapped questions carry no comparison
    assert "comparison" not in next(q for q in res["questions"] if q["question_id"] == "q1")


# --------------------------------------------------------------- evidence loop-back

def test_responses_attach_to_a_persona_as_survey_evidence(store):
    proj = _project(store)
    pid = create_persona(store, "Carla Calibrated")
    s = _record(store, proj["id"])
    with pytest.raises(ValueError, match="no responses imported"):
        services.attach_survey_evidence(s["id"], pid, store=store)
    services.import_survey_responses(s["id"], [_form_payload(s)], store=store)
    out = services.attach_survey_evidence(s["id"], pid, store=store)
    ev = store.list_evidence(pid)
    assert any(e["source_type"] == "survey" for e in ev)
    rec = next(e for e in ev if e["source_type"] == "survey")
    assert rec["id"] == out["evidence"]["id"]
    payload = json.loads(rec["content_or_path"])
    assert payload["survey_id"] == s["id"] and payload["responses"] == 1
    assert {q["question_id"] for q in payload["questions"]} == {"q1", "q2", "q3", "q4"}


# --------------------------------------------------------------- the brief (gather, no server text)

def test_brief_gathers_open_questions_contested_findings_and_the_scale(store):
    proj = _project(store)
    services.record_open_questions(proj["id"], ["What stops non-savers?"], store=store)
    contested = _council_with_stances(store, proj["id"], [2, -2])        # support AND oppose → contested
    unanimous = _council_with_stances(store, proj["id"], [1, 2])         # one-sided → not contested
    brief = services.brief_survey(proj["id"], store=store)
    assert brief["schema"] == "survey"
    assert [o["text"] for o in brief["open_questions"]] == ["What stops non-savers?"]
    ids = [c["council_id"] for c in brief["contested_findings"]]
    assert contested["id"] in ids and unanimous["id"] not in ids
    row = brief["contested_findings"][0]
    assert row["stance_tally"]["support"] == 1 and row["stance_tally"]["oppose"] == 1
    assert [i["term"] for i in brief["stance_scale"]["items"]] == \
        [t["term"] for t in artifacts.stance_terms()]
    assert "record_survey" in brief["instructions"]
    with pytest.raises(KeyError):
        services.brief_survey("rproject_missing", store=store)


# --------------------------------------------------------------- inspector detail page

def test_detail_page_renders_questions_chips_and_predicted_vs_actual(store):
    from starlette.testclient import TestClient
    from sonaloop import web
    from sonaloop.web._i18n import STRINGS
    proj = _project(store)
    council = _council_with_stances(store, proj["id"], [2, -1])
    s = _record(store, proj["id"], derived_from=[{"kind": "council", "id": council["id"]}])
    client = TestClient(web.create_app())
    html = client.get(f'/surveys/{s["id"]}?lang=en').text
    assert "Retirement readiness" in html and "Stocks/ETF" in html
    assert f'/councils/{council["id"]}' in html               # derived-from chip links to the council
    assert STRINGS["en"]["no_survey_responses"] in html       # honest empty state pre-import
    # responses arrive → aggregates + the predicted-vs-actual strip in the canonical stance colors
    services.import_survey_responses(s["id"], [_form_payload(s)], store=store)
    html = client.get(f'/surveys/{s["id"]}?lang=en').text
    assert STRINGS["en"]["survey_predicted"] in html and STRINGS["en"]["survey_actual"] in html
    for v in (2, -1):                                         # predicted segments use stance_meta colors
        assert artifacts.stance_meta(v)["color"] in html
    assert STRINGS["en"]["no_survey_responses"] not in html
    # list page + not-found stay honest
    assert "Retirement readiness" in client.get("/surveys?lang=en").text
    assert STRINGS["en"]["runtime_maybe_cleared"] in client.get("/surveys/nope?lang=en").text


def test_survey_detail_extra_seam_is_noop_in_core_and_pluggable(store):
    """The render_detail_extra("survey", …) seam injects extension chrome into the aside
    (sonaloop-cloud's share link). The public core registers nothing, so the page renders
    without it; a registered provider's HTML appears and is handed the survey record."""
    from starlette.testclient import TestClient
    from sonaloop import web
    from sonaloop.web import _ext
    proj = _project(store)
    s = _record(store, proj["id"])
    client = TestClient(web.create_app())
    assert "SHARE-EXTRA-MARKER" not in client.get(f'/surveys/{s["id"]}').text   # no-op in core

    seen = {}
    _ext.register_detail_extra("survey",
                               lambda st, e: seen.setdefault("id", e["id"]) and "" or
                               f'<div>SHARE-EXTRA-MARKER {e["id"]}</div>')
    try:
        html = client.get(f'/surveys/{s["id"]}').text
        assert f'SHARE-EXTRA-MARKER {s["id"]}' in html
        assert seen["id"] == s["id"]                                            # gets the record
    finally:
        _ext._DETAIL_EXTRAS.pop("survey", None)


def test_csv_reimport_without_timestamps_is_idempotent(store):
    proj = _project(store)
    s = _record(store, proj["id"])
    csv_text = ("respondent_key,q1,q3\n"
                "p1,Bank savings,neutral\n"
                "p2,Not at all,oppose\n")
    first = services.import_survey_responses(s["id"], csv_text=csv_text, store=store)
    assert first["total_responses"] == 2
    again = services.import_survey_responses(s["id"], csv_text=csv_text, store=store)
    assert again["total_responses"] == 2  # same batch, same ids — never double-counted


def test_ragged_csv_row_is_a_clean_validation_error(store):
    proj = _project(store)
    s = _record(store, proj["id"])
    ragged = "respondent_key,q1\np1,Bank savings,EXTRA\n"
    with pytest.raises(ValueError, match="more fields"):
        services.import_survey_responses(s["id"], csv_text=ragged, store=store)


def test_export_out_path_must_stay_inside_the_data_dir(store, tmp_path, monkeypatch):
    from sonaloop import config
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    proj = _project(store)
    s = _record(store, proj["id"])
    with pytest.raises(ValueError, match="escapes the data dir"):
        services.export_survey(s["id"], out=str(tmp_path / "evil.html"), store=store)
    with pytest.raises(ValueError, match="escapes the data dir"):
        services.export_survey(s["id"], out="../outside.html", store=store)


def test_export_fills_sentinels_in_one_pass(store, tmp_path, monkeypatch):
    from pathlib import Path

    from sonaloop import config
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    proj = _project(store)
    s = _record(store, proj["id"], title="__CONCEPT_JSON__")
    out = services.export_survey(s["id"], store=store)
    html = Path(out["path"]).read_text(encoding="utf-8")
    assert html.count('"post_url"') == 1  # the concept JSON lands exactly once, in its slot
    assert ">__CONCEPT_JSON__<" in html   # the hostile title stays literal text in the heading
