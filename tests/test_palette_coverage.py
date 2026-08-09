"""THE CANARY — the Cmd+K palette must never fall behind the app
(ticket cmdk-registry-driven-coverage).

Walks the live route table, the nav registry and the presence-contract entity kinds,
and fails — naming exactly what to add — whenever something exists that the palette's
coverage registry (sonaloop/web/_palette_registry.py) cannot reach. Plus behavioral
tests for the newly searchable entity types (sessions, hypotheses, decisions, surveys).
"""
from __future__ import annotations

import re

from starlette.testclient import TestClient

from conftest import create_persona
from sonaloop import services, web
from sonaloop.web._ext import nav_model
from sonaloop.web._palette_registry import (
    KIND_SEARCH, NON_SEARCHABLE_ROUTES, SEARCH_SOURCES, NotSearchable,
    nav_commands, search_rows,
)

# a top-level detail route: one literal prefix segment + one path parameter
_DETAIL_ROUTE = re.compile(r"^(/[a-z-]+)/\{[^/}]+\}$")


def test_canary_every_nav_item_is_a_palette_command(store):
    """Every registered nav item (core seeds + anything an extension registers) must
    surface as a palette jump command — derived, not hand-copied."""
    web.create_app()                                   # seeds the nav registry + extensions
    urls = {c["url"] for c in nav_commands()}
    missing = [it["href"] for _sec, items in nav_model() for it in items
               if it["href"] not in urls]
    assert not missing, (
        "palette fell behind the nav registry — these nav items have no jump command: "
        f"{missing}. nav_commands() derives from nav_model(), so this means someone "
        "bypassed register_nav_item or filtered commands; fix the derivation in "
        "sonaloop/web/_palette_registry.py, do not hand-add commands.")
    # the chrome surfaces the ticket names explicitly
    for required in ("/activity", "/runs", "/documentation", "#settings", "#shortcuts"):
        assert required in urls, f"palette misses the required jump command {required!r}"


def test_canary_every_detail_route_is_searchable_or_excused(store):
    """Every GET /{prefix}/{id} page route must be reachable through entity search —
    or carry an explicit reason in NON_SEARCHABLE_ROUTES."""
    app = web.create_app()
    prefixes = {src.url_prefix for src in SEARCH_SOURCES.values()}
    offenders = []
    for r in app.routes:
        path = getattr(r, "path", "")
        methods = getattr(r, "methods", None) or set()
        m = _DETAIL_ROUTE.match(path)
        if not m or "GET" not in methods or path.startswith("/api/"):
            continue
        prefix = m.group(1)
        if prefix in prefixes or prefix in NON_SEARCHABLE_ROUTES:
            continue
        offenders.append(
            f"{path}: add a SEARCH_SOURCES entry with url_prefix '{prefix}' in "
            "sonaloop/web/_palette_registry.py (label, icon, color, rows reader) — or, "
            "if its records are genuinely not palette targets, excuse the prefix in "
            "NON_SEARCHABLE_ROUTES with the reason")
    assert not offenders, "palette fell behind the app's routes:\n  " + "\n  ".join(offenders)


def test_canary_every_entity_kind_is_searchable_or_excused():
    """Every presence-contract kind (the app's entity inventory — web/_presence.REGISTRY)
    must map to a search source or an explicit NotSearchable reason; no stale mappings."""
    from sonaloop.web._presence import REGISTRY
    problems = []
    for kind in REGISTRY:
        target = KIND_SEARCH.get(kind)
        if target is None:
            problems.append(f"kind {kind!r} is missing from KIND_SEARCH — map it to its "
                            "SEARCH_SOURCES type or declare NotSearchable(reason) in "
                            "sonaloop/web/_palette_registry.py")
        elif isinstance(target, NotSearchable):
            if not target.reason:
                problems.append(f"NotSearchable for kind {kind!r} must carry a reason")
        elif target not in SEARCH_SOURCES:
            problems.append(f"kind {kind!r} maps to unknown search source {target!r}")
    for kind in set(KIND_SEARCH) - set(REGISTRY):
        problems.append(f"KIND_SEARCH maps {kind!r} which is no longer a presence kind — "
                        "drop the stale entry")
    assert not problems, "palette fell behind the entity kinds:\n  " + "\n  ".join(problems)


def test_palette_markup_seeds_registry_commands_and_groups(store):
    """The rendered chrome carries the registry-derived structured nav (every nav item,
    incl. /runs and /activity — each WITH an icon), the actions, and the per-type group
    labels/icons/order as JSON (UX V6)."""
    html = TestClient(web.create_app()).get("/?lang=en").text
    cfg = html.split('id="cmdk-cfg" type="application/json">')[1].split("</script>")[0]
    for url in ("/jobs", "/personas", "/activity", "/runs", "/documentation",
                "/surveys", "/hypotheses", "/decisions", "#settings", "#shortcuts"):
        assert f'"url": "{url}"' in cfg or f'"{url}"' in cfg, f"palette command {url} missing"
    import json
    parsed = json.loads(cfg)
    assert parsed["order"] == list(SEARCH_SOURCES)
    assert {"recent", "go", "actions", "closest", "empty", "teach",
            *SEARCH_SOURCES} <= set(parsed["labels"])
    assert set(parsed["icons"]) == {"go", *SEARCH_SOURCES}
    for it in parsed["nav"]:
        assert it.get("ico"), f"nav item {it['url']} carries no icon (V6: icons everywhere)"
    assert [a["act"] for a in parsed["actions"]] == ["theme", "tour", "feedback"]


def test_palette_consolidates_library_kinds_under_one_entry(store):
    """C10/V6: the kind lists are CHILDREN of the one /formats entry — the palette never
    re-exposes the retired flat IA as top-level commands."""
    import json
    from sonaloop.web.pages.library import LIBRARY_TABS
    html = TestClient(web.create_app()).get("/?lang=en").text
    cfg = html.split('id="cmdk-cfg" type="application/json">')[1].split("</script>")[0]
    parsed = json.loads(cfg)
    tops = [n["url"] for n in parsed["nav"]]
    lib = next(n for n in parsed["nav"] if n["url"] == "/formats")
    assert [c["url"] for c in lib["children"]] == [route for _k, route, *_ in LIBRARY_TABS]
    for _k, route, *_rest in LIBRARY_TABS:
        assert route not in tops, (
            f"{route} is a flat top-level palette entry again — kind lists must ride the "
            "/formats item's `children` (web/_palette_registry.palette_nav)")
    # /runs stays searchable but quiet (retired from the IA — it must not read like nav)
    runs = next(n for n in parsed["nav"] if n["url"] == "/runs")
    assert runs.get("quiet") is True


# ------------------------------------------------------------- new searchable types

_STEP = {"index": 0, "action": {"type": "click", "target": "b0", "detail": "clicked"},
         "monologue": "thinking aloud", "state": {"screen": "start screen"},
         "friction": {"level": "none", "note": ""},
         "verdict": {"would_continue": True, "reason": ""}}
_OUTCOME = {"completed": True, "dropoff_step": None, "summary": "walked it",
            "predicted_behaviors": []}


def _seed_new_entities(store):
    proj = services.create_research_project("Pension awareness",
                                            goal="How do people plan retirement?", store=store)
    pid = proj["id"]
    services.record_hypothesis(
        pid, text="Savers complete the digital pension check",
        prediction={"metric": "signup_rate", "expected_value": 40, "tolerance": 5,
                    "confidence": 0.7}, store=store)
    per = create_persona(store, "Evi Dence")
    council = services.record_council(
        pid, "Would a digital pension check help?", [per],
        statements=[{"persona_id": per, "text": "it would help", "stance": {"value": 1}}],
        summary="useful", store=store)
    services.record_decision(
        pid, title="Ship the pension check standalone",
        decision="Own flow, not a portal plugin.",
        based_on=[{"kind": "council", "id": council["id"]}], store=store)
    services.record_survey(
        pid, title="Retirement readiness pulse",
        questions=[{"id": "q1", "text": "How do you save today?", "kind": "text"}], store=store)
    services.record_open_questions(pid, ["Which pension proof builds confidence?"], store=store)
    services.add_artifact(pid, "https://example.test/pension-proof", title="Pension proof reference",
                          capture=False, store=store)
    asset = services.attach_asset(pid, content_base64="c2NyZWVu", filename="pension-flow.png",
                                  kind="screenshot", title="Pension flow screen", store=store)
    services.define_flow(pid, "Pension proof flow",
                         [{"asset_id": asset["id"], "caption": "proof screen"}], store=store)
    services.record_usability_session(
        per, {"kind": "flow", "id": "flow-check", "label": "Pension check walkthrough"},
        "artifact", "2026-06-10", [_STEP], _OUTCOME, project_id=pid, store=store)
    return pid


def test_search_covers_sessions_hypotheses_decisions_surveys(store):
    _seed_new_entities(store)
    client = TestClient(web.create_app())

    def hit(q, typ, url_prefix):
        rows = client.get(f"/api/search?q={q}").json()["rows"]
        matches = [r for r in rows if r["type"] == typ]
        assert matches, f"no {typ} hit for q={q!r}: {rows}"
        assert matches[0]["url"].startswith(url_prefix + "/")
        return matches[0]

    hit("Savers complete", "hypothesis", "/hypotheses")
    hit("Ship the pension", "decision", "/decisions")
    hit("Retirement readiness", "survey", "/surveys")
    hit("Pension check walkthrough", "session", "/sessions")
    hit("Pension check walkthrough", "session", "/sessions")
    hit("Pension proof reference", "reference", "/references")
    hit("Which pension proof", "open_question", "/open-questions")


def test_search_rows_matches_api_contract(store):
    """search_rows is the same read the API serves: typed rows with the V6 row anatomy —
    kind, title, the OWNING PROJECT as the desc line, url, date for the right-aligned meta."""
    _seed_new_entities(store)
    rows = search_rows("pension", store=store)
    types = {r["type"] for r in rows}
    assert {"project", "hypothesis", "decision", "session"} <= types
    for r in rows:
        assert set(r) == {"type", "title", "subtitle", "url", "date"}
    hyp = next(r for r in rows if r["type"] == "hypothesis")
    assert hyp["subtitle"] == "Pension awareness", "desc line must be the owning project"
    assert next(r for r in rows if r["type"] == "session")["date"] == "10 Jun"


# ----------------------------------------------------------- V6: ranking + fold + limits

def test_search_ranking_title_prefix_then_word_prefix_then_substring(store):
    proj = services.create_research_project("Ranking fixture", goal="rank", store=store)
    pid = proj["id"]
    services.create_note(pid, "x", title="Antipause artifact", store=store)   # substring
    services.create_note(pid, "x", title="Lunch pause flow", store=store)     # word-prefix
    services.create_note(pid, "x", title="Pause screen design", store=store)  # title-prefix
    rows = [r["title"] for r in search_rows("pause", store=store) if r["type"] == "note"]
    assert rows == ["Pause screen design", "Lunch pause flow", "Antipause artifact"]


def test_search_is_diacritic_and_case_insensitive(store):
    proj = services.create_research_project("Überstunden im Schichtdienst", goal="g", store=store)
    for q in ("überst", "uberst", "ÜBERST"):
        rows = search_rows(q, store=store)
        assert any(r["url"] == f'/jobs/{proj["id"]}' for r in rows), f"no hit for {q!r}"


def test_archived_job_is_not_an_ordinary_palette_result(store):
    project = services.create_research_project(
        "Archived palette fixture", goal="preserved evidence", store=store)
    services.archive_project(
        project["id"], "archive:palette-fixture", "Hide historical work", store=store)

    rows = search_rows("Archived palette fixture", store=store)
    assert not any(
        row["type"] == "project" and row["url"] == f'/jobs/{project["id"]}'
        for row in rows
    )


def test_archived_job_prunes_browser_discovery_without_hiding_retained_evidence(store):
    """Archive removes the Project entity from persistent browser discovery too.

    The exact detail URL and child evidence remain inspectable; only Project
    recents/favorites are denied, including stale legacy ``/projects`` URLs.
    """
    import json

    current = services.create_research_project(
        "Current browser discovery fixture", goal="current", store=store)
    archived = services.create_research_project(
        "Archived browser discovery fixture", goal="retained evidence", store=store)
    note = services.create_note(
        archived["id"], "Retained archived evidence body",
        title="Retained archived evidence", store=store,
    )
    client = TestClient(web.create_app())
    slug_detail = client.get(f'/jobs/{archived["slug"]}?lang=en').text
    slug_visit = json.loads(
        slug_detail.split("data-cmdk-visit>", 1)[1].split("</script>", 1)[0]
    )
    assert slug_visit["url"] == f'/jobs/{archived["slug"]}'
    before_archive = client.get("/personas?lang=en").text
    before_token = before_archive.split('data-sonaloop-shell="', 1)[1].split('"', 1)[0]
    services.archive_project(
        archived["id"], "archive:browser-discovery", "Hide historical Job", store=store)

    shell = client.get("/personas?lang=en").text
    after_token = shell.split('data-sonaloop-shell="', 1)[1].split('"', 1)[0]
    assert after_token != before_token  # a kept SPA shell must reload the new denylist
    marker = '<script id="cmdk-cfg" type="application/json">'
    cfg = json.loads(shell.split(marker, 1)[1].split("</script>", 1)[0])
    assert set(cfg["hiddenProjectUrls"]) == {
        f'/jobs/{archived["id"]}', f'/projects/{archived["id"]}',
        f'/jobs/{archived["slug"]}', f'/projects/{archived["slug"]}',
    }
    assert f'"project:{archived["id"]}"' in shell
    assert "if(HF[k]||(f.type==='project'&&HU[path]))" in shell
    assert "if(HR[String(v.url).split(/[?#]/)[0]]) return" in shell
    assert "recents();  // prune on shell load" in shell

    archived_detail = client.get(f'/jobs/{archived["id"]}?lang=en')
    assert archived_detail.status_code == 200
    assert archived["title"] in archived_detail.text
    assert "data-project-archived" in archived_detail.text
    assert f'data-star="project:{archived["id"]}"' not in archived_detail.text
    assert "data-cmdk-visit>" not in archived_detail.text
    archived_slide = client.get(f'/jobs/{archived["id"]}?slide=1&lang=en').text
    assert f'data-star="project:{archived["id"]}"' not in archived_slide
    assert "data-cmdk-visit>" not in archived_slide
    archived_slug_detail = client.get(f'/jobs/{archived["slug"]}?lang=en').text
    assert archived["title"] in archived_slug_detail
    assert f'data-star="project:{archived["id"]}"' not in archived_slug_detail
    assert "data-cmdk-visit>" not in archived_slug_detail

    current_detail = client.get(f'/jobs/{current["id"]}?lang=en').text
    assert f'data-star="project:{current["id"]}"' in current_detail
    assert "data-cmdk-visit>" in current_detail

    # Archive keeps authored evidence in the global evidence browser/search.
    evidence = search_rows("Retained archived evidence", store=store)
    assert any(row["type"] == "note" and row["url"] == f'/notes/{note["id"]}'
               for row in evidence)


def test_search_caps_results_per_kind(store):
    proj = services.create_research_project("Caps", goal="g", store=store)
    for i in range(8):
        services.record_hypothesis(
            proj["id"], text=f"Pricing bet number {i}",
            prediction={"metric": "m", "expected_value": 1, "tolerance": 1,
                        "confidence": 0.5}, store=store)
    rows = [r for r in search_rows("pricing", store=store) if r["type"] == "hypothesis"]
    assert len(rows) == 6, "the palette endpoint must stay capped at 6 rows per kind"


def test_api_empty_result_offers_closest_matches(store):
    """No hits never dead-ends: the API carries the nearest titles (the DS-site ⌘K idea)."""
    _seed_new_entities(store)
    client = TestClient(web.create_app())
    data = client.get("/api/search?q=pensoin").json()       # a typo near 'pension'
    assert data["rows"] == []
    assert data["closest"], "closest matches missing for a near-miss query"
    assert any("pension" in r["title"].lower() for r in data["closest"])
    # honest nothing: a query near nothing returns no fabricated suggestions
    far = client.get("/api/search?q=xqzwvjkpt").json()
    assert far["rows"] == [] and far["closest"] == []


# --------------------------------------------------------------- V6: the recents beacon

def test_detail_pages_stamp_the_recents_beacon(store):
    """Detail renders (full page AND ?slide=1 slide-over fragment) carry the inert
    data-cmdk-visit JSON the palette JS records into localStorage — kind, title, owning
    project, canonical url. List pages stay beacon-free."""
    import json
    pid = _seed_new_entities(store)
    client = TestClient(web.create_app())
    cid = store.list_council_sessions()[0]["id"]

    def beacon(html):
        # the rendered element, not the bare attribute name (PALETTE_JS quotes the selector)
        assert "data-cmdk-visit>" in html, "recents beacon missing"
        return json.loads(html.split("data-cmdk-visit>")[1].split("</script>")[0])

    v = beacon(client.get(f"/councils/{cid}").text)
    assert v["type"] == "council" and v["url"] == f"/councils/{cid}"
    assert v["title"] and v["project"] == "Pension awareness"
    # the slide-over fragment stamps the SAME visit (peek counts as a visit)
    assert beacon(client.get(f"/councils/{cid}?slide=1").text)["url"] == f"/councils/{cid}"
    # project + persona pages stamp their own kind
    assert beacon(client.get(f"/jobs/{pid}").text)["type"] == "project"
    per = store.list_personas()[0]
    assert beacon(client.get(f'/personas/{per["id"]}').text)["type"] == "persona"
    # list pages never pollute the recents
    assert "data-cmdk-visit>" not in client.get("/councils").text
