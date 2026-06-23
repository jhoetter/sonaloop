"""Hypotheses — falsifiable predictions scored against reality (the sim-vs-reality calibration
artifact, and the eval_reports table's first writer).

Validation (unfalsifiable predictions and unresolvable refs rejected), the brief's context pack
(contested findings, predicted behaviors, open questions), the result-recording flow (both raw
values kept; status DERIVED from observed vs predicted for value AND direction predictions; the
source ref must resolve), the scorecard math (hit-rate over resolved only, open bets excluded,
eval_reports row written), the resolvable `hypothesis` Ref kind, and the project-page section
(open bets vs resolved, predicted-vs-observed, hit-rate strip).
"""
from __future__ import annotations

import pytest

from conftest import create_persona
from sonaloop import artifacts, services


def _project(store, title="Pension awareness"):
    return services.create_research_project(title, goal="How do people plan retirement?",
                                            store=store)


def _prediction(**kw):
    p = {"metric": "signup_rate", "expected_value": 40, "tolerance": 5, "confidence": 0.7}
    p.update(kw)
    return p


def _record(store, project_id, **kw):
    args = {"text": "At least 40% of invited savers complete the pension check",
            "prediction": _prediction()}
    args.update(kw)
    return services.record_hypothesis(project_id, store=store, **args)["hypothesis"]


def _council_with_stances(store, project_id, values):
    pid = create_persona(store, "Stancy Source")
    statements = [{"persona_id": pid, "text": f"view {i}", "stance": {"value": v}}
                  for i, v in enumerate(values)]
    return services.record_council(project_id, "Would a digital pension check help?", [pid],
                                   statements=statements, summary="mixed", store=store)


# A free observation — the lightest resolvable source (kind external, the text IS the observation).
_OBS = {"kind": "external", "text": "street panel, n=24"}


# --------------------------------------------------------------- record: validation + persistence

def test_record_get_roundtrip_and_list(store):
    proj = _project(store)
    hx = _record(store, proj["id"])
    got = services.get_hypothesis(hx["id"], store=store)
    assert got["status"] == "open" and got["result"] is None
    assert got["prediction"] == {"metric": "signup_rate", "expected_value": 40,
                                 "tolerance": 5.0, "confidence": 0.7}
    assert services.list_hypotheses(proj["id"], store=store)[0]["id"] == hx["id"]
    assert services.list_hypotheses(proj["id"], status="open", store=store)
    assert not services.list_hypotheses(proj["id"], status="validated", store=store)
    with pytest.raises(ValueError, match="status"):
        services.list_hypotheses(proj["id"], status="maybe", store=store)
    with pytest.raises(KeyError):
        services.get_hypothesis("hyp_missing", store=store)
    with pytest.raises(KeyError):
        services.record_hypothesis("rproject_missing", "claim", _prediction(), store=store)


def test_stable_key_upserts_but_a_scored_bet_is_immutable(store):
    proj = _project(store)
    h1 = _record(store, proj["id"], key="bet-1")
    h2 = _record(store, proj["id"], key="bet-1", text="At least 40% complete it (sharper)")
    assert h2["id"] == h1["id"] and h2["created_at"] == h1["created_at"]
    assert len(services.list_hypotheses(proj["id"], store=store)) == 1
    # once reality scored the bet, it cannot be re-authored — the record is the audit trail
    services.record_hypothesis_result(h1["id"], 38, _OBS, store=store)
    with pytest.raises(ValueError, match="already validated"):
        _record(store, proj["id"], key="bet-1")


def test_unfalsifiable_predictions_are_rejected(store):
    proj = _project(store)

    def rec(pred):
        return services.record_hypothesis(proj["id"], "claim", pred, store=store)

    with pytest.raises(ValueError, match="metric"):
        rec({"expected_value": 1})
    with pytest.raises(ValueError, match="unfalsifiable"):
        rec({"metric": "signup_rate"})                       # neither value nor direction → no bet
    with pytest.raises(ValueError, match="not both"):
        rec({"metric": "m", "expected_value": 1, "expected_direction": "increase"})
    with pytest.raises(ValueError, match="not scoreable"):
        rec({"metric": "m", "expected_direction": "sideways"})
    with pytest.raises(ValueError, match="confidence"):
        rec(_prediction(confidence=1.4))
    with pytest.raises(ValueError, match="tolerance"):
        rec(_prediction(tolerance=-1))
    with pytest.raises(ValueError, match="prediction must be a dict"):
        rec("it will go well")
    with pytest.raises(ValueError, match="text is required"):
        services.record_hypothesis(proj["id"], "  ", _prediction(), store=store)


def test_derived_from_refs_must_resolve(store):
    proj = _project(store)
    with pytest.raises(ValueError, match="does not resolve"):
        _record(store, proj["id"], derived_from=[{"kind": "council", "id": "council_missing"}])
    council = _council_with_stances(store, proj["id"], [2, -1])
    oq = services.record_open_questions(proj["id"], ["What stops non-savers?"], store=store)[0]
    hx = _record(store, proj["id"],
                 derived_from=[{"kind": "council", "id": council["id"]},
                               {"kind": "open_question", "id": oq["id"], "role": "answers"}])
    refs = hx["derived_from"]
    assert refs[0]["role"] == "derived_from"                 # default role
    assert refs[1]["role"] == "answers"                      # the edge to the question it settles
    assert refs[1]["quote"] == "What stops non-savers?"      # cached display hint for the chip
    assert artifacts.resolve_ref(refs[0], store)["exists"] is True


# --------------------------------------------------------------- the brief (gather, no server text)

def test_brief_gathers_bets_worth_making(store):
    proj = _project(store)
    services.record_open_questions(proj["id"], ["What stops non-savers?"], store=store)
    contested = _council_with_stances(store, proj["id"], [2, -2])
    unanimous = _council_with_stances(store, proj["id"], [1, 2])
    store.insert_usability_session({
        "id": "usess_1", "project_id": proj["id"], "persona_id": "p1", "date": "2026-06-01",
        "subject": {"kind": "prototype", "id": "proto_1", "label": "Pension check"},
        "fidelity": "prototype", "steps": [], "statements": [],
        "created_at": "2026-06-01T00:00:00Z",
        "outcome": {"completed": True, "dropoff_step": None, "summary": "",
                    "predicted_behaviors": [{"action": "would invite their partner", "step": None,
                                             "likelihood": 0.6, "trigger": "the result screen"}]},
    })
    brief = services.brief_hypothesis(proj["id"], store=store)
    assert brief["schema"] == "hypothesis"
    assert [o["text"] for o in brief["open_questions"]] == ["What stops non-savers?"]
    ids = [c["council_id"] for c in brief["contested_findings"]]
    assert contested["id"] in ids and unanimous["id"] not in ids
    pb = brief["predicted_behaviors"][0]
    assert pb["action"] == "would invite their partner"
    assert pb["ref"] == {"kind": "session", "id": "usess_1", "role": "derived_from"}
    assert "record_hypothesis" in brief["instructions"]
    with pytest.raises(KeyError):
        services.brief_hypothesis("rproject_missing", store=store)


# --------------------------------------------------------------- resolution (reality answers)

def test_value_prediction_resolution_keeps_both_values(store):
    proj = _project(store)
    hit = _record(store, proj["id"])                          # expects 40 ±5
    out = services.record_hypothesis_result(hit["id"], 38, _OBS, note="within tolerance",
                                            store=store)
    assert out["status"] == "validated"
    got = services.get_hypothesis(hit["id"], store=store)
    assert got["status"] == "validated"
    assert got["prediction"]["expected_value"] == 40          # BOTH raw values kept — auditable
    assert got["result"]["observed_value"] == 38
    assert got["result"]["note"] == "within tolerance"        # the host's argued verdict
    assert got["result"]["recorded_at"]
    miss = _record(store, proj["id"], key="miss")
    assert services.record_hypothesis_result(miss["id"], 12, _OBS, store=store)["status"] == "refuted"
    odd = _record(store, proj["id"], key="odd")
    assert services.record_hypothesis_result(
        odd["id"], "n/a — panel collapsed", _OBS, store=store)["status"] == "inconclusive"
    # a non-numeric expectation compares case-insensitively
    cat = _record(store, proj["id"], key="cat",
                  prediction={"metric": "majority_stance", "expected_value": "skeptical"})
    assert services.record_hypothesis_result(cat["id"], "Skeptical", _OBS,
                                             store=store)["status"] == "validated"
    cat2 = _record(store, proj["id"], key="cat2",
                   prediction={"metric": "majority_stance", "expected_value": "skeptical"})
    assert services.record_hypothesis_result(cat2["id"], "support", _OBS,
                                             store=store)["status"] == "refuted"


def test_direction_prediction_resolution(store):
    proj = _project(store)

    def bet(key):
        return _record(store, proj["id"], key=key,
                       prediction={"metric": "weekly_active", "expected_direction": "increase"})

    res = services.record_hypothesis_result  # numeric observations score by sign
    assert res(bet("d1")["id"], "+12%", _OBS, store=store)["status"] == "validated"
    assert res(bet("d2")["id"], -3, _OBS, store=store)["status"] == "refuted"
    assert res(bet("d3")["id"], 0, _OBS, store=store)["status"] == "inconclusive"  # no movement
    # direction tokens compare directly; an unreadable observation stays inconclusive
    assert res(bet("d4")["id"], "down", _OBS, store=store)["status"] == "refuted"
    assert res(bet("d5")["id"], "sideways-ish", _OBS, store=store)["status"] == "inconclusive"
    # direction aliases normalize onto the canonical terms at record time
    up = _record(store, proj["id"], key="d6",
                 prediction={"metric": "weekly_active", "expected_direction": "UP"})
    assert up["prediction"]["expected_direction"] == "increase"


def test_result_source_ref_must_resolve(store):
    proj = _project(store)
    hx = _record(store, proj["id"])
    with pytest.raises(ValueError, match="source does not resolve"):
        services.record_hypothesis_result(hx["id"], 38, {"kind": "council", "id": "council_missing"},
                                          store=store)
    with pytest.raises(ValueError, match="source does not resolve"):
        services.record_hypothesis_result(hx["id"], 38, {"kind": "external"}, store=store)
    with pytest.raises(ValueError, match="source must be a Ref"):
        services.record_hypothesis_result(hx["id"], 38, "I saw it on the street", store=store)
    with pytest.raises(ValueError, match="observed_value is required"):
        services.record_hypothesis_result(hx["id"], None, _OBS, store=store)
    assert services.get_hypothesis(hx["id"], store=store)["status"] == "open"  # nothing written
    # a survey is the natural source: its id resolves through the shared resolver
    survey = services.record_survey(proj["id"], "Readiness", [
        {"id": "q1", "text": "Would it help?", "kind": "scale",
         "options": ["oppose", "neutral", "support"]}], store=store)["survey"]
    out = services.record_hypothesis_result(hx["id"], 38, {"kind": "survey", "id": survey["id"]},
                                            store=store)
    assert out["hypothesis"]["result"]["source"]["kind"] == "survey"
    assert out["hypothesis"]["result"]["source"]["role"] == "observed_in"
    # attached evidence resolves too (kind 'evidence' became a resolvable Ref kind)
    pid = create_persona(store, "Carla Calibrated")
    ev = services.attach_evidence(pid, "interview", "transcript …", "follow-up call", store)
    hx2 = _record(store, proj["id"], key="ev")
    out2 = services.record_hypothesis_result(hx2["id"], 33, {"kind": "evidence", "id": ev["id"]},
                                             store=store)
    assert out2["status"] == "refuted"                       # |33 - 40| > 5
    with pytest.raises(KeyError):
        services.record_hypothesis_result("hyp_missing", 1, _OBS, store=store)


# --------------------------------------------------------------- scorecard (the calibration record)

def test_scorecard_hit_rate_over_resolved_only_and_eval_report_written(store):
    proj = _project(store)
    res = services.record_hypothesis_result
    res(_record(store, proj["id"], key="h1")["id"], 40, _OBS, store=store)       # validated
    res(_record(store, proj["id"], key="h2")["id"], 41, _OBS, store=store)       # validated
    res(_record(store, proj["id"], key="h3")["id"], 10, _OBS, store=store)       # refuted
    res(_record(store, proj["id"], key="h4")["id"], "n/a", _OBS, store=store)    # inconclusive
    _record(store, proj["id"], key="h5")                                         # open — excluded
    card = services.eval_scorecard(proj["id"], store=store)["scorecard"]
    assert card["counts"] == {"open": 1, "validated": 2, "refuted": 1,
                              "inconclusive": 1, "dropped": 0}
    assert card["resolved"] == 4 and card["decisive"] == 3
    assert card["hit_rate"] == pytest.approx(2 / 3)          # over decisive resolutions only
    assert card["green"] is True and card["scope"] == proj["id"]
    assert {x["status"] for x in card["resolved_hypotheses"]} == {"validated", "refuted",
                                                                  "inconclusive"}
    # the orphaned eval_reports table finally gets its row — the sim-vs-reality calibration record
    reports = [r for r in store.list_eval_reports() if r.get("kind") == "hypothesis_scorecard"]
    assert reports and reports[0]["id"] == card["id"] and reports[0]["green"] is True
    # global scope aggregates across projects with a per-project breakdown
    other = _project(store, "Other study")
    res(_record(store, other["id"], key="o1")["id"], 0, _OBS, store=store)       # refuted
    g = services.eval_scorecard(store=store)["scorecard"]
    assert g["scope"] == "global" and g["resolved"] == 5
    assert g["hit_rate"] == pytest.approx(2 / 4)
    assert g["by_project"][proj["id"]]["hit_rate"] == pytest.approx(2 / 3)
    assert g["by_project"][other["id"]]["hit_rate"] == 0.0
    with pytest.raises(KeyError):
        services.eval_scorecard("rproject_missing", store=store)


def test_scorecard_with_no_decisive_resolutions_is_not_green(store):
    proj = _project(store)
    _record(store, proj["id"], key="h1")                                         # open only
    card = services.eval_scorecard(proj["id"], store=store)["scorecard"]
    assert card["hit_rate"] is None and card["green"] is False
    assert card["resolved"] == 0 and card["counts"]["open"] == 1


# --------------------------------------------------------------- graph: the resolvable Ref kind

def test_hypothesis_is_a_resolvable_ref_kind(store):
    proj = _project(store)
    hx = _record(store, proj["id"])
    ref = {"kind": "hypothesis", "id": hx["id"]}
    assert artifacts.ref_href(ref) == f'/hypotheses/{hx["id"]}'
    res = artifacts.resolve_ref(ref, store)
    assert res["exists"] is True and res["title"] == hx["text"]
    assert artifacts.resolve_ref({"kind": "hypothesis", "id": "hyp_missing"}, store)["exists"] is False


# ---------------------------------------- inspector: project rows + the hypothesis slide-over

def test_project_page_rows_and_hypothesis_slideover(store):
    """UX P2 (spec/ux-contract.md §3.4) + U6 (§8.1): a hypothesis is an outline ROW like
    everything else (status pill, anchor); its data-drawer carries the CANONICAL detail URL,
    whose ?slide=1 fragment renders the FULL predicted-vs-observed detail content."""
    from starlette.testclient import TestClient
    from sonaloop import web
    from sonaloop.web._i18n import STRINGS
    proj = _project(store)
    council = _council_with_stances(store, proj["id"], [2, -1])
    open_bet = _record(store, proj["id"], key="b1",
                       derived_from=[{"kind": "council", "id": council["id"]}])
    resolved = _record(store, proj["id"], key="b2",
                       text="Half of savers would pay for the check")
    services.record_hypothesis_result(resolved["id"], 38, {"kind": "external",
                                                           "text": "street panel"},
                                      note="close enough", store=store)
    client = TestClient(web.create_app())
    html = client.get(f'/jobs/{proj["id"]}?lang=en').text
    assert html.count('data-rkind="hypothesis"') == 2    # both bets are rows
    assert open_bet["text"] in html and resolved["text"] in html
    assert STRINGS["en"]["hyp_status_open"] in html      # lifecycle pills on the rows
    assert STRINGS["en"]["hyp_status_validated"] in html
    assert f'id="hyp-{resolved["id"]}"' in html          # the row IS the anchor target
    assert f'data-drawer="/hypotheses/{resolved["id"]}"' in html   # canonical URL (§8.1)
    # the slide-over fragment = the SAME detail renderer, content only: predicted vs
    # observed + the derived-from chip, no app shell
    slide = client.get(f'/hypotheses/{resolved["id"]}?slide=1&lang=en').text
    assert slide.startswith('<div class="sl-slide">') and "sl-sidebar" not in slide
    assert STRINGS["en"]["hyp_predicted"] in slide and STRINGS["en"]["hyp_observed"] in slide
    assert "38" in slide and "close enough" in slide
    open_slide = client.get(f'/hypotheses/{open_bet["id"]}?slide=1&lang=en').text
    assert f'/councils/{council["id"]}' in open_slide    # derived-from chip via render_ref
    # the Ref route serves a REAL detail page on the shared anatomy (UX U7, §8.2): kind
    # eyebrow + lifecycle pill + predicted/observed + the rail's project-anchor link
    r = client.get(f'/hypotheses/{resolved["id"]}?lang=en')
    assert r.status_code == 200
    detail = r.text
    assert STRINGS["en"]["hypothesis_kind"] in detail and STRINGS["en"]["hyp_status_validated"] in detail
    assert resolved["text"] in detail
    assert STRINGS["en"]["hyp_predicted"] in detail and STRINGS["en"]["hyp_observed"] in detail
    assert "38" in detail and "close enough" in detail
    # the rail's Project link lands ON the bet's row (round-2 audit: the old
    # "View in project" meta-line link retired — no other kind carried one)
    assert f'/jobs/{proj["id"]}#hyp-{resolved["id"]}' in detail
    assert STRINGS["en"]["runtime_maybe_cleared"] in client.get("/hypotheses/nope?lang=en").text
    # a project without hypotheses shows no hypothesis rows (and no empty chrome)
    other = _project(store, "Quiet study")
    assert 'data-rkind="hypothesis"' not in client.get(f'/jobs/{other["id"]}?lang=en').text


# --------------------------------------------------------------- inspector: the cross-project list

def test_global_hypotheses_list_renders_empty_and_populated(store):
    from starlette.testclient import TestClient
    from sonaloop import web
    from sonaloop.web._i18n import STRINGS
    client = TestClient(web.create_app())
    empty = client.get("/hypotheses?lang=en")                 # honest empty state, no chrome
    assert empty.status_code == 200 and STRINGS["en"]["no_hypotheses"] in empty.text
    pa, pb = _project(store, "Project A"), _project(store, "Project B")
    open_bet = _record(store, pa["id"], key="open")
    resolved = _record(store, pb["id"], key="res", text="Half of savers would pay for the check")
    services.record_hypothesis_result(resolved["id"], 38, _OBS, note="close enough", store=store)
    page = client.get("/hypotheses?lang=en")
    assert page.status_code == 200
    html = page.text
    # the URL stays canonical; the content is the LIBRARY with the Hypotheses tab active
    # (ux-contract §3.5) — lifecycle-pilled rows, the slide-over carrying the full detail
    assert STRINGS["en"]["library_h"] in html
    assert STRINGS["en"]["hyp_status_open"] in html and STRINGS["en"]["hyp_status_validated"] in html
    assert open_bet["text"] in html and resolved["text"] in html
    assert f'data-drawer="/hypotheses/{resolved["id"]}"' in html
    # each row's href IS the canonical detail URL (§8.1); the project shows as the desc line
    assert f'href="/hypotheses/{open_bet["id"]}"' in html
    assert f'href="/hypotheses/{resolved["id"]}"' in html
    assert "Project A" in html and "Project B" in html
    # the GLOBAL hit-rate strip (over resolved bets across all projects)
    assert STRINGS["en"]["hyp_hit_rate"] in html and "1/1" in html
    # the list route does not shadow the canonical /hypotheses/{id} DETAIL page (UX U7)
    r = client.get(f'/hypotheses/{resolved["id"]}?lang=en')
    assert r.status_code == 200 and resolved["text"] in r.text
    assert f'/jobs/{pb["id"]}#hyp-{resolved["id"]}' in r.text  # secondary view-in-project link


# --------------------------------------------------------------- review fixes (audit-trail integrity)

def test_a_resolved_verdict_cannot_be_rescored(store):
    proj = _project(store)
    hx = _record(store, proj["id"])
    services.record_hypothesis_result(hx["id"], 41, _OBS, store=store)
    with pytest.raises(ValueError, match="already validated"):
        services.record_hypothesis_result(hx["id"], 999, _OBS, store=store)
    kept = services.get_hypothesis(hx["id"], store=store)
    assert kept["result"]["observed_value"] == 41  # the original observation survives


def test_key_hash_is_project_scoped(store):
    pa, pb = _project(store, "Project A"), _project(store, "Project B")
    ha = _record(store, pa["id"], key="shared-key")
    hb = _record(store, pb["id"], key="shared-key", text="B's own bet on the same key")
    assert ha["id"] != hb["id"]
    assert [x["id"] for x in services.list_hypotheses(pa["id"], store=store)] == [ha["id"]]
    assert services.get_hypothesis(ha["id"], store=store)["text"].startswith("At least 40%")


def test_record_kind_sources_need_an_id(store):
    proj = _project(store)
    hx = _record(store, proj["id"])
    with pytest.raises(ValueError, match="needs an id"):
        services.record_hypothesis_result(
            hx["id"], 41, {"kind": "survey", "text": "trust me, a survey said so"}, store=store)
    # the free-observation escape hatch stays open, but only as kind external
    services.record_hypothesis_result(hx["id"], 41, _OBS, store=store)


def test_drop_hypothesis_retires_open_bets_only(store):
    proj = _project(store)
    hx = _record(store, proj["id"])
    dropped = services.drop_hypothesis(hx["id"], note="metric became unmeasurable", store=store)
    assert dropped["hypothesis"]["status"] == "dropped"
    assert dropped["hypothesis"]["drop_note"] == "metric became unmeasurable"
    with pytest.raises(ValueError, match="not scored"):
        services.record_hypothesis_result(hx["id"], 41, _OBS, store=store)
    scored = _record(store, proj["id"], text="Another bet", key="k2")
    services.record_hypothesis_result(scored["id"], 41, _OBS, store=store)
    with pytest.raises(ValueError, match="only an open bet"):
        services.drop_hypothesis(scored["id"], store=store)
    card = services.eval_scorecard(proj["id"], store=store)
    assert card["scorecard"]["resolved"] == 1  # the dropped bet never enters the scorecard
