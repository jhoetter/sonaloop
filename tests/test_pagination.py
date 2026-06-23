"""Pagination as a concept (cross-repo convention, sonaloop-data docs/pagination.md;
core adoption documented in docs/pagination.md): the shared cursor helper, the MCP
list tools' envelopes ({items, total, has_more, next_cursor}; no params → first page,
backward compatible) and the web lists' ?page=N controls composing with ?q=."""
from __future__ import annotations

import asyncio

import pytest
from starlette.testclient import TestClient

from sonaloop import services, web
from sonaloop.mcp_server import build_server
from sonaloop.storage import Store

from conftest import create_persona


# --------------------------------------------------------------------------- #
# the shared helper (services/_pagination.py)                                  #
# --------------------------------------------------------------------------- #

def _items(n):
    return [{"slug": f"item-{i:03d}"} for i in range(n)]


def test_envelope_fields_and_first_page_default():
    out = services.paginate(_items(30), lambda x: x["slug"])
    assert set(out) == {"items", "total", "has_more", "next_cursor"}
    assert len(out["items"]) == 25 and out["total"] == 30 and out["has_more"] is True
    last = services.paginate(_items(10), lambda x: x["slug"])
    assert last["has_more"] is False and "next_cursor" not in last   # exactly-when contract


def test_cursor_walk_covers_everything_exactly_once():
    items, key = _items(8), (lambda x: x["slug"])
    seen, cursor = [], None
    for _ in range(10):
        page = services.paginate(items, key, limit=3, cursor=cursor)
        seen += [i["slug"] for i in page["items"]]
        if not page["has_more"]:
            break
        cursor = page["next_cursor"]
    assert seen == [i["slug"] for i in items]


def test_cursor_is_stable_under_inserts_and_deletes():
    """Key-based, not offset-based: rows added/removed between calls never make the
    next page skip or repeat the rows that were already there."""
    items, key = _items(6), (lambda x: x["slug"])
    page1 = services.paginate(items, key, limit=3)
    grown = sorted(items + [{"slug": "item-000a"}], key=key)         # insert inside page 1
    page2 = services.paginate(grown, key, limit=3, cursor=page1["next_cursor"])
    assert [i["slug"] for i in page2["items"]] == ["item-003", "item-004", "item-005"]
    shrunk = [i for i in items if i["slug"] != "item-003"]           # the cursor row vanished
    page2b = services.paginate(shrunk, key, limit=3, cursor=services.encode_cursor("item-002"))
    assert [i["slug"] for i in page2b["items"]] == ["item-004", "item-005"]


def test_reverse_order_paging():
    items = sorted(_items(5), key=lambda x: x["slug"], reverse=True)
    key = lambda x: x["slug"]  # noqa: E731
    page1 = services.paginate(items, key, limit=2, reverse=True)
    page2 = services.paginate(items, key, limit=2, cursor=page1["next_cursor"], reverse=True)
    assert [i["slug"] for i in page2["items"]] == ["item-002", "item-001"]


def test_cursor_rejects_a_changed_filter_set_and_garbage():
    cursor = services.paginate(_items(30), lambda x: x["slug"], filters={"q": "a"})["next_cursor"]
    with pytest.raises(ValueError, match="different filter set"):
        services.decode_cursor(cursor, filters={"q": "b"})
    with pytest.raises(ValueError, match="opaque"):
        services.decode_cursor("not-a-cursor!!", filters=None)


def test_limit_is_clamped():
    assert len(services.paginate(_items(500), lambda x: x["slug"], limit=9999)["items"]) == 200
    assert len(services.paginate(_items(5), lambda x: x["slug"], limit=0)["items"]) == 5


# --------------------------------------------------------------------------- #
# MCP list tools                                                               #
# --------------------------------------------------------------------------- #

def _call(server, name, args):
    _, env = asyncio.run(server.call_tool(name, args))
    return env


def test_list_personas_tool_pages_with_stable_cursor(store):
    for i in range(8):
        create_persona(store, f"Persona {i:03d}")
    server = build_server()

    env = _call(server, "list_personas", {})                         # backward compat: no params
    assert env["ok"] is True
    data = env["data"]
    assert set(data) >= {"items", "total", "has_more"}
    assert data["total"] == 8 and len(data["items"]) == 8 and data["has_more"] is False
    assert {"slug", "display_name", "role"} <= set(data["items"][0])  # still the lean rows

    page1 = _call(server, "list_personas", {"limit": 3})["data"]
    assert page1["has_more"] is True and len(page1["items"]) == 3
    page2 = _call(server, "list_personas", {"limit": 3, "cursor": page1["next_cursor"]})["data"]
    names = [p["display_name"] for p in page1["items"] + page2["items"]]
    assert names == [f"Persona {i:03d}" for i in range(6)]           # name-sorted, no skip/dup

    filtered = _call(server, "list_personas", {"filters": {"q": "Persona 001"}})["data"]
    assert filtered["total"] == 1                                    # total counts the FILTERED set


def test_list_councils_tool_pages_newest_first(store):
    for i in range(5):
        store.insert_council_session({"id": f"c{i}", "prompt": f"prompt {i}", "persona_ids": [],
                                      "votes": [], "created_at": f"2026-06-0{i + 1}T00:00:00"})
    server = build_server()
    page1 = _call(server, "list_councils", {"limit": 2})["data"]
    assert page1["total"] == 5 and [c["id"] for c in page1["items"]] == ["c4", "c3"]
    page2 = _call(server, "list_councils", {"limit": 2, "cursor": page1["next_cursor"]})["data"]
    assert [c["id"] for c in page2["items"]] == ["c2", "c1"]


def test_list_notes_tool_pages_in_creation_order(store):
    project = services.create_research_project("Notes project", store=store)
    for i in range(4):
        services.create_note(project["id"], f"note {i}",
                             created_at=f"2026-06-01T00:00:0{i}", store=store)
    server = build_server()
    page1 = _call(server, "list_notes", {"project_id": project["id"], "limit": 3})["data"]
    assert page1["total"] == 4 and len(page1["items"]) == 3 and page1["has_more"] is True
    page2 = _call(server, "list_notes",
                  {"project_id": project["id"], "limit": 3, "cursor": page1["next_cursor"]})["data"]
    assert [n["text"] for n in page2["items"]] == ["note 3"]


# --------------------------------------------------------------------------- #
# web lists: ?page=N + ?q= compose (docs/pagination.md, human-UI half)         #
# --------------------------------------------------------------------------- #

def test_personas_page_controls_and_filter_compose(store):
    for i in range(27):
        create_persona(store, f"Web Persona {i:02d}")
    client = TestClient(web.create_app())

    p1 = client.get("/personas?lang=en").text
    assert "Page 1 of 2" in p1 and 'href="/personas?page=2"' in p1
    assert '<span class="h1cnt">27</span>' in p1                     # count = the full set
    assert "Web Persona 00" in p1 and "Web Persona 26" not in p1     # 25 rows, name-sorted

    p2 = client.get("/personas?lang=en&page=2").text
    assert "Web Persona 26" in p2 and "Web Persona 00" not in p2
    assert "Page 2 of 2" in p2 and 'href="/personas?page=1"' in p2

    hit = client.get("/personas?lang=en&q=Persona+07").text          # filter composes + resets
    assert '<span class="h1cnt">1</span>' in hit and "Web Persona 07" in hit
    assert "Page 1" not in hit                                       # one page → no pager
    assert client.get("/personas?lang=en&page=999").status_code == 200   # clamped, not 500


def test_projects_page_controls_and_filter(store):
    create_persona(store, "Someone")                                 # skip the first-steps page
    for i in range(26):
        services.create_research_project(f"Project {i:02d}", store=store)
    client = TestClient(web.create_app())
    p1 = client.get("/jobs?lang=en").text
    assert "Page 1 of 2" in p1 and 'name="q"' in p1
    p2 = client.get("/jobs?lang=en&page=2&q=Project").text
    assert "Page 2 of 2" in p2
    assert 'href="/jobs?page=1&amp;q=Project"' in p2             # q rides the page links
    hit = client.get("/jobs?lang=en&q=Project+25").text
    assert '<span class="h1cnt">1</span>' in hit
