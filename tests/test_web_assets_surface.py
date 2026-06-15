"""UX U8 — assets as a first-class surface (spec/ux-contract.md §8.3, ticket
sonaloop/ux-u8-assets-surface): the Library's Assets tab, the global /assets/{id} detail page
(U7 anatomy + provenance block), and the project FILES lens (?view=files) — the
across-many-MCP-messages story: which input files were received, which documents were
generated, in one chronological provenance timeline."""
from __future__ import annotations

import base64

import pytest
from starlette.testclient import TestClient

from sonaloop import services, web


def _client():
    return TestClient(web.create_app())


@pytest.fixture
def project(store):
    return services.create_research_project("Asset surface", goal="g", store=store)


def _attach(store, pid, name: str, data: bytes, **kw):
    return services.attach_asset(pid, content_base64=base64.b64encode(data).decode(),
                                 filename=name, store=store, **kw)


@pytest.fixture
def both_directions(store, project):
    """One received input (in, with a free MCP-ish source) + one generated deliverable (out,
    with a record-pointing synthesis source) — the two halves of the §8.3 story."""
    ev = _attach(store, project["id"], "interview-01.md", b"## Notes\nthe approval flow confuses",
                 title="Interview notes", source="mcp: attached by the host", notes="from the user")
    syn = services.record_synthesis("Findings", "q", [], {}, store=store)
    syn["project_id"] = project["id"]
    store.upsert_synthesis(syn)
    out = _attach(store, project["id"], "findings.pptx", b"PK\x03\x04 deck",
                  title="Findings (PPTX)", direction="out", source=f'synthesis:{syn["id"]}')
    return {"in": ev, "out": out, "syn": syn}


# ------------------------------------------------------------------- the detail page (§8.3)

def test_asset_detail_page_full_anatomy(store, project, both_directions):
    a = both_directions["in"]
    html = _client().get(f'/assets/{a["id"]}?lang=en').text
    # U7 anatomy: ASSET eyebrow + kind/direction pills + filename · size · media_type sub
    assert ">Asset</span>" in html or ">ASSET<" in html.upper()
    assert "Document" in html and "Evidence" in html
    assert "interview-01.md" in html and "text/markdown" in html
    # provenance block: received stamp, the free source rendered honestly, notes
    assert "Provenance" in html and "Received" in html
    assert "mcp: attached by the host" in html
    assert "from the user" in html
    # the hero FILE card (V9: ext badge identity, the whole card = the one open affordance)
    assert 'class="sl-file"' in html and ">md</span>" in html
    assert f'href="{a["url"]}"' in html
    # the rail names the project + the files lens
    assert f'/projects/{project["id"]}' in html
    assert f'/projects/{project["id"]}?view=files' in html
    # the document's text excerpt is quoted on the page
    assert "the approval flow confuses" in html


def test_asset_detail_generated_deliverable_resolves_source_chip(store, both_directions):
    out, syn = both_directions["out"], both_directions["syn"]
    html = _client().get(f'/assets/{out["id"]}?lang=en').text
    assert "Generated" in html and "Deliverable" in html
    # the record-pointing source resolves LIVE through render_ref: title + deep link
    assert f'/syntheses/{syn["id"]}' in html and "Findings" in html
    # the download affordance carries the download attribute (a deliverable is handed over)
    assert f'href="{out["url"]}" download="{out["filename"]}"' in html


def test_asset_detail_resolves_globally_across_projects(store, project, both_directions):
    other = services.create_research_project("Other project", goal="g", store=store)
    b = _attach(store, other["id"], "other.txt", b"other evidence")
    html = _client().get(f'/assets/{b["id"]}?lang=en').text
    assert "Other project" in html and "other.txt" in html


def test_asset_detail_slide_variant_is_a_fragment(store, both_directions):
    r = _client().get(f'/assets/{both_directions["in"]["id"]}?slide=1')
    assert r.status_code == 200
    assert r.text.startswith('<div class="sl-slide">') and "sl-sidebar" not in r.text


def test_asset_detail_renders_supersede_chain(store, project, both_directions):
    out = both_directions["out"]
    services.record_asset_supersession(
        project["id"], out["id"],
        [{"id": "asset_old", "filename": "findings-v1.pptx", "created_at": "2026-06-01T08:00:00+00:00"}],
        store=store)
    html = _client().get(f'/assets/{out["id"]}?lang=en').text
    assert "Supersedes" in html and "findings-v1.pptx" in html


def test_unknown_asset_renders_not_found(store):
    html = _client().get("/assets/asset_nope?lang=en").text
    assert "sl-empty" in html


# ------------------------------------------------------------------- the Library tab (§3.5)

def test_library_assets_tab_rows_with_project_and_direction(store, project, both_directions):
    html = _client().get("/assets?lang=en").text
    # the scoped primitive tab is active, both directions render as compact FILE rows (V9).
    assert 'class="libnav-kind is-active"' in html and ">Assets<" in html
    assert html.count('class="sl-file sl-file--row"') == 2
    for a in (both_directions["in"], both_directions["out"]):
        assert f'data-drawer="/assets/{a["id"]}"' in html      # slide-over armed (the card body)
        assert f'href="{a["url"]}"' in html                    # download one click away (the ONE action)
    assert "Evidence" in html and "Deliverable" in html        # badged by direction
    assert "Asset surface" in html                             # the owning project on the meta line
    # the canonical route and ?tab= address the same browser
    assert _client().get("/library?tab=assets&lang=en").text.count("sl-file__open") == \
           html.count("sl-file__open")


def test_library_assets_tab_empty_state_teaches_attach_asset(store):
    html = _client().get("/assets?lang=en").text
    assert "attach_asset" in html                              # the F1 teach line


# ------------------------------------------------------------------- the files lens (§8.3)

def test_project_files_lens_chronological_with_day_separators(store, project, both_directions):
    pid = project["id"]
    p = store.get_research_project(pid)                        # spread across two days
    p["assets"][0]["created_at"] = "2026-06-01T09:00:00+00:00"
    p["assets"][1]["created_at"] = "2026-06-03T10:00:00+00:00"
    store.upsert_research_project(p)
    html = _client().get(f"/projects/{pid}?view=files&lang=en").text
    # both directions interleave chronologically: in (1 Jun) before out (3 Jun)
    assert html.index("interview-01.md") < html.index("findings.pptx")
    assert html.count('class="group"') == 2                    # day separators = grid section headers
    # V9: file CARDS in the grid — each slide-over armed (body = open) with its direction
    # pill; the deliverable's source chip resolves on the card body
    assert html.count('class="sl-file-grid"') == 2
    assert html.count('class="sl-file"') == 2
    assert f'data-drawer="/assets/{both_directions["in"]["id"]}"' in html
    assert "Evidence" in html and "Deliverable" in html
    assert f'/syntheses/{both_directions["syn"]["id"]}' in html
    # reachable from the project header chip
    proj_html = _client().get(f"/projects/{pid}?lang=en").text
    assert f'/projects/{pid}?view=files' in proj_html and "2 files" in proj_html


def test_files_lens_cards_carry_file_identity_and_one_affordance(store, project, both_directions):
    """V9 (ux-contract §9): file identity FIRST — the extension badge (type-toned), the
    filename WITH extension as the title, size · date meta — and exactly ONE download/open
    affordance per card (the duplicate left+right download icons are the owner finding)."""
    html = _client().get(f'/projects/{project["id"]}?view=files&lang=en').text
    # the markdown evidence: blue text-family badge, filename title, opens in a tab
    assert ">md</span>" in html and "sl-file__ext--blue" in html
    assert "interview-01.md" in html
    # the deck deliverable: amber badge, download attribute hands the binary over
    assert ">pptx</span>" in html and "sl-file__ext--amber" in html
    ev, out = both_directions["in"], both_directions["out"]
    assert f'href="{out["url"]}" download="{out["filename"]}"' in html
    # exactly ONE affordance per file: each binary URL appears once, in the action slot
    for a in (ev, out):
        card = html.split(f'data-drawer="/assets/{a["id"]}"')[1].split("sl-file-grid")[0]
        assert card.count(f'href="{a["url"]}"') == 1, "duplicate download affordances"
    assert html.count('class="sl-file__action"') == 2


def test_outline_evidence_and_deliver_rows_are_file_rows(store, project, both_directions):
    """V9: the project outline's Evidence/Deliver asset rows use the compact `.sl-file--row`
    — ext badge identity instead of a generic icon, one affordance, slide-over armed."""
    html = _client().get(f'/projects/{project["id"]}?lang=en').text
    assert html.count('data-rkind="asset"') == 2
    assert html.count('class="sl-file sl-file--row" data-rkind="asset"') == 2
    assert ">md</span>" in html and ">pptx</span>" in html
    for a in (both_directions["in"], both_directions["out"]):
        assert f'data-drawer="/assets/{a["id"]}"' in html
        chunk = html.split(f'data-drawer="/assets/{a["id"]}"')[1].split("</div></div>")[0]
        assert chunk.count(f'href="{a["url"]}"') == 1, "one download/open affordance per row"


def test_project_files_lens_empty_state_teaches(store, project):
    html = _client().get(f'/projects/{project["id"]}?view=files&lang=en').text
    assert "attach_asset" in html
    proj_html = _client().get(f'/projects/{project["id"]}?lang=en').text
    assert "0 files" in proj_html                              # the chip is the honest inventory
