"""The cross-host retrieval contract (search/fetch) + URL coverage on the read/record tools.

Two things a remote agent (claude.ai / ChatGPT) needs and didn't have: (1) ChatGPT requires
`search`+`fetch` with a fixed shape, and (2) every project/council/synthesis result must carry
the link to hand the user — absent before, so the agent knew titles but not where to look."""
from __future__ import annotations

import pytest

from sonaloop import services


@pytest.fixture(autouse=True)
def _base_url(monkeypatch):
    monkeypatch.setenv("SONALOOP_PUBLIC_BASE_URL", "https://app.sonaloop.test")
    yield


def _seed(store):
    p = services.start_project("Confidential AI Awareness", "reach data-sensitive firms", store=store)
    c = services.record_council(p["id"], "What would make you notice confidential AI?", [],
                                [{"persona_id": "x", "text": "a trigger event"}], store=store, key="c")
    syn = services.record_synthesis("Awareness strategy", "arc", council_ids=[c["id"]],
                                    project_id=p["id"], payload={"gesamtbild": "Trigger beats message."},
                                    store=store)
    h = services.record_hypothesis(p["id"], "Trigger-anchored content outperforms cold category messaging",
                                   {"metric": "reply_rate", "expected_direction": "up", "confidence": 0.6},
                                   store=store, key="h")
    return p, c, syn, h


# --- URL coverage ---------------------------------------------------------------------

def test_every_research_result_carries_its_link(store):
    p, c, syn, h = _seed(store)
    base = "https://app.sonaloop.test"
    assert p["url"] == f"{base}/jobs/{p['id']}"
    assert c["url"] == f"{base}/councils/{c['id']}" and c["project_url"] == f"{base}/jobs/{p['id']}"
    assert syn["url"] == f"{base}/syntheses/{syn['id']}" and syn["project_url"] == f"{base}/jobs/{p['id']}"
    assert h["url"] == f"{base}/hypotheses/{h['hypothesis']['id']}"
    # the read side an agent uses to answer "what are my projects" / "show me this project"
    listed = next(x for x in services.list_research_projects(store=store) if x["id"] == p["id"])
    assert listed["url"] == f"{base}/jobs/{p['id']}"
    assert services.get_project_graph(p["id"], store=store)["project"]["url"] == f"{base}/jobs/{p['id']}"
    assert services.assess_project(p["id"], store=store)["url"] == f"{base}/jobs/{p['id']}"
    assert services.get_council(c["id"], store=store)["url"] == f"{base}/councils/{c['id']}"
    assert services.get_synthesis(syn["id"], store=store)["url"] == f"{base}/syntheses/{syn['id']}"
    assert all(x.get("url") for x in services.list_councils(store=store))
    assert all(x.get("url") for x in services.list_syntheses(store=store))


# --- search (OpenAI shape) ------------------------------------------------------------

def test_search_returns_openai_shape_and_ranks_the_match(store):
    p, c, syn, h = _seed(store)
    res = services.retrieval_search("confidential awareness")
    assert set(res.keys()) == {"results"}
    for r in res["results"]:
        assert set(r) >= {"id", "title", "url"}        # the required OpenAI keys
        assert r["url"].startswith("https://app.sonaloop.test/")
    ids = [r["id"] for r in res["results"]]
    assert p["id"] in ids and c["id"] in ids           # project + council both surfaced
    assert res["results"][0]["id"] == p["id"]          # the project title is the strongest match


def test_search_empty_query_lists_projects_not_an_error(store):
    p, *_ = _seed(store)
    res = services.retrieval_search("")
    assert any(r["id"] == p["id"] for r in res["results"])


def test_persona_list_carries_links(store):
    from conftest import create_persona
    pid = create_persona(store, "Dr. Reuter")
    row = next(x for x in services.list_personas(compact=True, store=store) if x["id"] == pid)
    assert row["url"] == f"https://app.sonaloop.test/personas/{pid}"


# --- fetch (OpenAI shape) -------------------------------------------------------------

@pytest.mark.parametrize("which", ["project", "council", "synthesis", "hypothesis"])
def test_fetch_resolves_each_kind(store, which):
    p, c, syn, h = _seed(store)
    target = {"project": p["id"], "council": c["id"], "synthesis": syn["id"],
              "hypothesis": h["hypothesis"]["id"]}[which]
    doc = services.retrieval_fetch(target)
    assert set(doc) == {"id", "title", "text", "url", "metadata"}
    assert doc["id"] == target and doc["text"] and doc["url"].startswith("https://app.sonaloop.test/")
    assert doc["metadata"]["kind"] == which


def test_fetch_unknown_id_raises(store):
    with pytest.raises(KeyError):
        services.retrieval_fetch("rproject_doesnotexist")


# --- the MCP tools are named exactly search/fetch and return the BARE shape -----------

def test_mcp_exposes_search_and_fetch_unwrapped(store):
    import asyncio

    from sonaloop.mcp_server import build_server
    _seed(store)
    server = build_server()
    names = {t.name for t in asyncio.run(server.list_tools())}
    assert "search" in names and "fetch" in names
    _, structured = asyncio.run(server.call_tool("search", {"query": "confidential"}))
    assert "results" in structured and "ok" not in structured   # NOT the _env envelope
