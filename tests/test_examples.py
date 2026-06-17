"""Loadable example projects (ticket loadable-example-projects).

The contract: shipped example projects live INSIDE the wheel as committed
fixtures, load on demand through the real record_* layer (so every inspector page
is non-empty afterwards), re-load idempotently (stable example-namespaced ids,
keyed upserts — no duplicates), and remove cleanly without touching user data.
Surfaces: services (load/remove/list), CLI-backed service calls, MCP tools, and
the one-click affordance on the empty-DB home checklist (POST + 303 + CSRF)."""
from __future__ import annotations

import asyncio
import json
import re

from sonaloop import services
from sonaloop.storage import Store
from conftest import create_persona

PREMIUM = "premium-pricing-study"
POSITIONING = "positioning-council"
ONBOARDING = "onboarding-showcase"


def _client():
    from starlette.testclient import TestClient
    from sonaloop import web
    client = TestClient(web.create_app())
    client.get("/projects?lang=en")            # primes the sl_csrf double-submit cookie
    return client


def _post(client, url: str, **data):
    payload = {"csrf_token": client.cookies.get("sl_csrf"), **data}
    return client.post(url, data=payload, follow_redirects=False)


# ----------------------------------------------------------- fixtures in the wheel

def test_fixtures_ship_inside_the_package_via_importlib_resources():
    # The SAME access path the loader uses — i.e. what a wheel install exercises.
    from importlib import resources
    examples = resources.files("sonaloop").joinpath("examples")
    names = {e.name for e in examples.iterdir() if e.name.endswith(".json")}
    assert names == {f"{ONBOARDING}.json", f"{PREMIUM}.json", f"{POSITIONING}.json"}
    for name in names:
        fx = json.loads(examples.joinpath(name).read_text(encoding="utf-8"))
        assert fx["schema"] == "sonaloop_example/1"
        assert fx["slug"] and fx["project"]["title"] and fx["tagline"]
        assert len(fx["personas"]) >= 4 and len(fx["councils"]) >= 1


def test_list_examples_names_both_and_tracks_loaded_state(store):
    examples = services.list_examples(store=store)
    assert [e["slug"] for e in examples] == [ONBOARDING, POSITIONING, PREMIUM]  # sorted by filename
    assert all(e["loaded"] is False for e in examples)
    services.load_example(PREMIUM, store=store)
    by_slug = {e["slug"]: e for e in services.list_examples(store=store)}
    assert by_slug[PREMIUM]["loaded"] is True
    assert by_slug[POSITIONING]["loaded"] is False
    assert by_slug[ONBOARDING]["loaded"] is False


def test_unknown_slug_raises_keyerror_listing_available(store):
    try:
        services.load_example("nope", store=store)
        assert False, "expected KeyError"
    except KeyError as exc:
        assert PREMIUM in str(exc)


# ------------------------------------------------- the full value arc, per fixture

def test_premium_loads_a_complete_project_with_derived_results(store):
    out = services.load_example(PREMIUM, store=store)
    c = out["counts"]
    assert c["personas"] == 5 and c["councils"] == 3 and c["syntheses"] == 1
    assert c["hypotheses"] == 3 and c["decisions"] == 1 and c["sections"] == 2
    assert c["open_questions"] >= 3 and c["notes"] >= 2

    # The price ladder carries the server-derived analysis (range + cliff).
    ladder = store.get_council_session(
        services.stable_id("council", f"example:{PREMIUM}:price-ladder"))["price_ladder"]
    assert ladder["result"]["overall"]["acceptable_range"]["low"] == "€19"
    assert ladder["result"]["overall"]["cliff"]["from"] == "€19"
    assert len(ladder["responses"]) == 25         # 5 personas × 5 rungs, every band grounded

    # The head-to-head carries variant metadata: ids, per-persona order, the bet.
    h2h = store.get_council_session(
        services.stable_id("council", f"example:{PREMIUM}:lite-vs-pro"))["head_to_head"]
    assert h2h["result"]["preference"] == "A" and h2h["result"]["decisive"] == "narrow"
    meta = h2h["variant_meta"]
    assert meta["variants"]["A"]["id"] == "klar-lite-19"
    assert len(meta["order_shown"]) == 5
    hyp = store.get_hypothesis(meta["hypothesis_id"])
    assert hyp["status"] == "validated"           # the pre-registered segment-split bet, resolved

    # Hypotheses span the statuses the demo should show: resolved AND still-open bets.
    statuses = sorted(h["status"] for h in services.list_hypotheses(out["project_id"], store=store))
    assert statuses == ["open", "validated", "validated"]

    # The decision cites the runs (resolvable refs by construction).
    (dec,) = services.list_decisions(out["project_id"], store=store)
    assert dec["status"] == "adopted" and len(dec["based_on"]) == 4 and dec["rejected"]

    # Personas carry the removal stamp (mirrors sonaloop-data's provenance.catalog).
    assert all((p.get("provenance") or {}).get("example") == PREMIUM
               for p in store.list_personas())

    # Loading emitted real lifecycle events — the Activity feed is non-empty.
    events = store.list_recent_events(limit=200)
    names = {e["event"] for e in events}
    assert {"project.created", "persona.created", "council.recorded",
            "synthesis.recorded", "example.loaded"} <= names


def test_positioning_loads_red_team_hmw_and_ideation(store):
    out = services.load_example(POSITIONING, store=store)
    pid = out["project_id"]
    assert out["counts"]["personas"] == 4 and out["counts"]["ideas"] == 9

    rt = store.get_council_session(
        services.stable_id("council", f"example:{POSITIONING}:red-team-time-back"))["red_team"]
    assert rt["case_against"]["worst_severity"] == "critical"
    assert rt["case_against"]["top_blocker"] == "Optimization reads as surveillance"

    ideation = services.get_ideation(
        services.stable_id("council", f"example:{POSITIONING}:converge-shortlist"), store=store)
    assert len(ideation["hmw"]) == 3 and len(ideation["shortlist"]) == 3
    assert [p["rank"] for p in ideation["shortlist"]] == [1, 2, 3]

    # Every idea note is attributed (persona + hmw_ref) — the diverge protocol held.
    ideas = services.list_ideas(pid, store=store)
    assert all((n["data"].get("persona_id") and n["data"].get("hmw_ref")) for n in ideas)
    # Both open bets stay open (B2B — reality hasn't answered yet).
    assert [h["status"] for h in services.list_hypotheses(pid, store=store)] == ["open", "open"]


def test_onboarding_showcase_loads_every_tour_artifact(store):
    out = services.load_example(ONBOARDING, store=store)
    c = out["counts"]
    assert c["personas"] == 4
    assert c["councils"] == 3 and c["syntheses"] == 2 and c["surveys"] == 1
    assert c["prototypes"] == 1 and c["sessions"] == 3 and c["references"] == 3
    assert c["hypotheses"] == 1 and c["decisions"] == 1
    assert c["assets"] == 3 and c["flows"] == 0 and c["notes"] == 2 and c["sections"] == 2
    from sonaloop import config
    project = store.get_research_project(out["project_id"])
    for pid in project["persona_ids"]:
        p = store.get_persona(pid)
        avatar_path = (p.get("avatar") or {}).get("path")
        assert avatar_path and avatar_path.startswith("data/avatars/")
        assert (config.ROOT / avatar_path).read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert services.list_surveys(out["project_id"], store=store)[0]["response_count"] == 4
    assert services.list_prototypes_artifacts(out["project_id"], store=store)
    assert services.list_usability_sessions(project_id=out["project_id"], store=store)
    assets = services.list_assets(out["project_id"], store=store)
    assert len(assets) == 3
    shots = [a for a in assets if a["kind"] == "screenshot"]
    assert len(shots) == 2
    for shot in shots:
        data, _meta = services.get_asset_content(out["project_id"], shot["id"], store=store)
        assert data.startswith(b"\x89PNG\r\n\x1a\n"), shot["filename"]
    html = _client().get(f'{out["url"]}?lang=en').text
    assert 'data-rkind="flow"' not in html
    assert 'data-rkind="live_url"' not in html
    assert "WALKTHROUGH" not in html and "LIVE SURFACE" not in html
    assert ">Flow<" not in html
    ref_rows = [chunk for chunk in html.split('class="olrow')[1:]
                if 'data-rkind="url_artifact"' in chunk.split(">", 1)[0]]
    assert ref_rows
    for chunk in ref_rows:
        ptag = re.search(r'<span class="ol-ptag[^"]*">([^<]*)</span>', chunk)
        assert ptag and ptag.group(1) == "Reference"
    plan = services.get_plan(out["project_id"], store=store)
    assert plan["methodology"] == "double_diamond"
    assert all(t["status"] == "done" for t in plan["tasks"])
    projects_html = _client().get("/projects?lang=en").text
    assert "Clinic QuickCheck — assisted pre-visit check-in" in projects_html
    assert "Methodology · Double Diamond" in projects_html
    assert "Run · Finished" in projects_html
    for noisy in ("3 Councils", "2 Reports", "1 Prototype", "3 Sessions", "1 Survey",
                  "1 Hypothesis", "1 Decision", "3 Open questions", "3 References",
                  "3 Assets", "2 Notes"):
        assert noisy not in projects_html

    from sonaloop.project_trace import trace_node_health
    from sonaloop.web._graph_outline_sessions import outline_session_groups
    from sonaloop.web._project_graph_view import augment_project_graph

    graph = services.get_project_graph(out["project_id"], store=store)
    proto_ids = {p.get("id") for p in graph.get("prototypes") or []}
    sessions = outline_session_groups(
        services.list_usability_sessions(project_id=out["project_id"], store=store), store,
        prototype_sessions=[s for s in store.list_prototype_sessions() if s.get("prototype_id") in proto_ids],
    )
    full_graph = augment_project_graph(
        graph, sessions=sessions,
        decisions=services.list_decisions(out["project_id"], store=store),
        hypotheses=services.list_hypotheses(out["project_id"], store=store),
        surveys=services.list_surveys(project_id=out["project_id"], store=store),
        assets=assets,
    )
    health = trace_node_health(full_graph["nodes"], full_graph["edges"], plan)
    assert {k: v for k, v in health.items() if v == "orphaned"} == {}
    assert {"source", "consumed", "terminal", "parked"} <= set(health.values())

    from sonaloop.web.pages.library import (
        LIBRARY_TABS, TAB_KIND, _annotate_library_trace, _entry_trace_keys, _tab_entries,
    )

    outline_kinds = {n.get("kind") for n in full_graph["nodes"] if n.get("kind")}
    library_tabs = {TAB_KIND[key]: key for key, *_ in LIBRARY_TABS}
    missing_tabs = outline_kinds - set(library_tabs)
    assert missing_tabs == set()
    library_kinds = {
        x["kind"]
        for key, *_ in LIBRARY_TABS
        for x in _tab_entries(key, store)
        if x.get("project_id") == out["project_id"]
    }
    assert outline_kinds <= library_kinds

    outline_health_by_key = {}
    for n in full_graph["nodes"]:
        sid = n.get("study_id")
        if not sid:
            continue
        state = health.get(sid)
        if not state:
            continue
        outline_health_by_key[sid] = state
        kind, rid = sid.split(":", 1) if ":" in sid else ("", sid)
        outline_health_by_key.setdefault(rid, state)
        if kind == "report":
            outline_health_by_key.setdefault(f"synthesis:{rid}", state)
        if kind == "url_artifact":
            outline_health_by_key.setdefault(f"artifact:{rid}", state)
    library_entries = _annotate_library_trace(
        [x for key, *_ in LIBRARY_TABS for x in _tab_entries(key, store)
         if x.get("project_id") == out["project_id"]],
        store,
    )
    for x in library_entries:
        expected = next((outline_health_by_key[k] for k in _entry_trace_keys(x)
                         if k in outline_health_by_key), "")
        if expected:
            assert x.get("trace_health") == expected, x
    assert "parked" in {x.get("trace_health") for x in library_entries}


def test_onboarding_showcase_timeline_is_authored_not_load_time(store):
    out = services.load_example(ONBOARDING, store=store)
    pid = out["project_id"]
    project = store.get_research_project(pid)
    refs = project["artifacts"]
    oqs = store.list_open_questions(pid)
    councils = [store.get_council_session(cid) for cid in project["council_ids"]]
    first_council = min(councils, key=lambda c: c["created_at"])
    survey = services.list_surveys(pid, store=store)[0]
    sessions = services.list_usability_sessions(project_id=pid, store=store)
    decision = services.list_decisions(project_id=pid, store=store)[0]

    assert refs[0]["created_at"] == "2026-06-10T09:26:00Z"
    assert oqs[0]["created_at"] == "2026-06-10T09:10:00Z"
    assert oqs[0]["created_at"] < refs[0]["created_at"] < first_council["created_at"]
    assert first_council["created_at"] < survey["created_at"] < sessions[0]["created_at"]
    assert max(s["created_at"] for s in sessions) < decision["created_at"]


def test_double_load_is_idempotent_for_both_examples(store):
    for slug in (ONBOARDING, PREMIUM, POSITIONING):
        first = services.load_example(slug, store=store)
        second = services.load_example(slug, store=store)
        assert first["project_id"] == second["project_id"]
        assert first["counts"] == second["counts"]
        assert services.get_plan(first["project_id"], store=store)
    assert len(store.list_research_projects()) == 3
    assert len(store.list_personas()) == 13
    assert len(store.list_council_sessions()) == 9
    assert len(store.list_syntheses()) == 4
    assert len(store.list_hypotheses()) == 6
    assert len(store.list_decisions()) == 3


# ----------------------------------------------------------------------- removal

def test_remove_deletes_only_the_examples_entities(store):
    # User data FIRST — the removal must not touch any of it.
    user_pid = create_persona(store, "Ulla User")
    project = services.create_research_project("My real study", goal="real",
                                               persona_ids=[user_pid], store=store)
    note = services.create_note(project["id"], "a real observation", store=store)
    council = services.record_council(project["id"], "real question?", [user_pid],
                                      statements=[{"persona_id": user_pid, "text": "real talk"}],
                                      store=store)
    hyp = services.record_hypothesis(project["id"], "users do X",
                                     {"metric": "x rate", "expected_direction": "increase"},
                                     store=store)["hypothesis"]

    services.load_example(PREMIUM, store=store)
    services.load_example(POSITIONING, store=store)
    services.load_example(ONBOARDING, store=store)
    services.remove_example(PREMIUM, store=store)
    services.remove_example(POSITIONING, store=store)
    services.remove_example(ONBOARDING, store=store)

    # Example data: gone, fully.
    assert services.list_examples(store=store) and \
        all(e["loaded"] is False for e in services.list_examples(store=store))
    assert len(store.list_research_projects()) == 1
    assert len(store.list_personas()) == 1
    assert len(store.list_council_sessions()) == 1
    assert not store.list_syntheses() and len(store.list_hypotheses()) == 1
    assert not store.list_decisions()
    assert not store.list_surveys() and not store.list_prototypes() and not store.list_usability_sessions()

    # User data: untouched.
    assert store.get_persona(user_pid)
    kept = store.get_research_project(project["id"])
    assert kept and [n["id"] for n in kept.get("notes", [])] == [note["id"]]
    assert store.get_council_session(council["id"])
    assert store.get_hypothesis(hyp["id"])


def test_remove_without_load_is_a_safe_noop(store):
    out = services.remove_example(PREMIUM, store=store)
    assert out["deleted"]["project"] == 0 and out["deleted"]["personas"] == 0


# --------------------------------------------------------------------- MCP surface

def test_mcp_example_tools_registered():
    from sonaloop.mcp_server import build_server
    server = build_server()
    names = {t.name for t in asyncio.run(server.list_tools())}
    assert {"list_examples", "load_example", "remove_example"} <= names


# ----------------------------------------------------------------------- web layer

def test_empty_home_offers_one_click_example_load_and_303s_to_project():
    client = _client()
    html = client.get("/?lang=en").text
    assert f'action="/examples/{PREMIUM}/load"' in html
    assert f'action="/examples/{POSITIONING}/load"' in html
    assert f'action="/examples/{ONBOARDING}/load"' in html
    assert "Load example" in html

    # CSRF is enforced on the load POST like on every write route.
    assert client.post(f"/examples/{PREMIUM}/load",
                       data={"csrf_token": "forged"}).status_code == 403

    r = _post(client, f"/examples/{PREMIUM}/load")
    assert r.status_code == 303
    project_url = r.headers["location"]
    assert project_url.startswith("/projects/rproject_")
    page = client.get(project_url)
    assert page.status_code == 200 and "Klar money coaching" in page.text

    # Unknown example slug -> 404, not a crash.
    assert _post(client, "/examples/nope/load").status_code == 404

    # Once data exists the checklist (and the example buttons) yield to the real lists.
    home = client.get("/?lang=en").text
    assert 'class="fsrow fsex"' not in home
    assert f'action="/examples/{PREMIUM}/load"' not in home


def test_every_major_inspector_page_is_non_empty_after_loading_both(store):
    p1 = services.load_example(PREMIUM, store=store)
    p2 = services.load_example(POSITIONING, store=store)
    p3 = services.load_example(ONBOARDING, store=store)
    client = _client()
    checks = {
        "/projects": ["Klar money coaching", "Schichtwerk", "Clinic QuickCheck"],
        "/personas": ["Maren Ostendorf", "Birgit Krautmann"],
        "/councils": ["Klar Lite at €19/month", "Position under fire", "better pilot direction"],
        "/syntheses": ["Pricing story", "fair, audit-proof roster", "assisted check-in pilot"],
        "/surveys": ["Appointment prep confidence"],
        "/prototypes": ["QuickCheck assisted pre-visit prototype"],
        "/references": ["patient portal check-in"],
        "/open-questions": ["appointment preparation"],
        "/sessions": ["Luis Rivera", "Evelyn Hart"],
        "/hypotheses": ["€19/month", "works council", "complete appointment prep"],
        "/decisions": ["Ship two tiers", "audit-proof roster", "assisted pre-check-in"],
        "/notes": ["Subscription fatigue", "fairness ledger", "Phone queue is a symptom"],
        "/assets": ["Prototype screen: SMS invite"],
        "/activity": ["example.loaded"],
        p1["url"]: ["Willingness-to-pay evidence"],
        p2["url"]: ["Positioning bets"],
        p3["url"]: ["Clinic QuickCheck"],
    }
    for url, needles in checks.items():
        r = client.get(f"{url}?lang=en")
        assert r.status_code == 200, url
        for needle in needles:
            assert needle in r.text, f"{needle!r} not on {url}"
    # The format detail pages render their blocks.
    for key, needle in ((f"example:{PREMIUM}:price-ladder", "€79"),
                        (f"example:{PREMIUM}:lite-vs-pro", "Klar Pro"),
                        (f"example:{POSITIONING}:red-team-time-back", "surveillance")):
        cid = services.stable_id("council", key)
        r = client.get(f"/councils/{cid}?lang=en")
        assert r.status_code == 200 and needle in r.text, cid
    syn_id = services.stable_id("synthesis", f"example:{PREMIUM}:pricing-story")
    assert client.get(f"/syntheses/{syn_id}?lang=en").status_code == 200
