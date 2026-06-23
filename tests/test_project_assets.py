"""Project assets: attach files/images as citable evidence, feed them to councils,
persist them in the snapshot (ticket attach-evidence-files-mcp)."""
from __future__ import annotations

import base64

import pytest

from sonaloop import config
from sonaloop import services
from sonaloop.services import _hooks

from conftest import create_persona


@pytest.fixture(autouse=True)
def _quiet_hooks(monkeypatch):
    monkeypatch.setattr(_hooks, "_HANDLERS", {})
    monkeypatch.setattr(_hooks, "_ENTRY_POINTS_LOADED", True)
    yield


PNG_BYTES = base64.b64decode(  # a 1x1 transparent PNG
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==")


@pytest.fixture
def project(store):
    return services.start_project("Asset study", "ground reactions in real material", store=store)


def test_attach_from_path_is_idempotent_and_typed(store, project, tmp_path):
    shot = tmp_path / "onboarding.png"
    shot.write_bytes(PNG_BYTES)
    a1 = services.attach_asset(project["id"], path=str(shot), title="Onboarding step 2", store=store)
    a2 = services.attach_asset(project["id"], path=str(shot), notes="updated note", store=store)
    assert a1["id"] == a2["id"]                       # content-addressed, idempotent
    assert a2["kind"] == "image" and a2["media_type"] == "image/png"
    assert a2["title"] == "Onboarding step 2"         # kept across re-attach
    assert a2["notes"] == "updated note"
    assert len(services.list_assets(project["id"], store=store)) == 1


def test_attach_from_base64_with_document_excerpt(store, project):
    text = "## Interview notes\nThe approval flow confuses the Bauleiter persona."
    rec = services.attach_asset(project["id"],
                                content_base64=base64.b64encode(text.encode()).decode(),
                                filename="interview-01.md", store=store)
    assert rec["kind"] == "document"
    assert "approval flow" in rec["text_excerpt"]
    full = services.get_asset(project["id"], "interview-01.md", store=store)  # by filename too
    assert full["id"] == rec["id"]


def test_attach_validation(store, project, tmp_path):
    with pytest.raises(ValueError):
        services.attach_asset(project["id"], store=store)  # neither path nor content
    with pytest.raises(ValueError):
        services.attach_asset(project["id"], path="x", content_base64="eA==", store=store)  # both
    with pytest.raises(FileNotFoundError):
        services.attach_asset(project["id"], path=str(tmp_path / "missing.png"), store=store)
    with pytest.raises(ValueError):
        services.attach_asset(project["id"], content_base64="eA==", store=store)  # no filename


def test_get_asset_content_roundtrip_and_containment(store, project, tmp_path):
    shot = tmp_path / "screen.png"
    shot.write_bytes(PNG_BYTES)
    rec = services.attach_asset(project["id"], path=str(shot), kind="screenshot", store=store)
    data, meta = services.get_asset_content(project["id"], rec["id"], store=store)
    assert data == PNG_BYTES and meta["id"] == rec["id"]
    # A tampered record path must not read outside the asset store.
    p = store.get_research_project(project["id"])
    p["assets"][0]["asset_path"] = "../../etc/passwd"
    store.upsert_research_project(p)
    with pytest.raises(ValueError):
        services.get_asset_content(project["id"], rec["id"], store=store)


def test_remove_asset(store, project, tmp_path):
    f = tmp_path / "doc.txt"
    f.write_text("evidence")
    rec = services.attach_asset(project["id"], path=str(f), store=store)
    assert services.remove_asset(project["id"], rec["id"], store=store)["deleted"] == 1
    assert services.list_assets(project["id"], store=store) == []
    assert services.remove_asset(project["id"], rec["id"], store=store)["deleted"] == 0


def test_asset_attached_event_emitted(store, project, tmp_path):
    seen = []
    services.add_hook_handler("asset.attached", seen.append)
    f = tmp_path / "shot.png"
    f.write_bytes(PNG_BYTES)
    rec = services.attach_asset(project["id"], path=str(f), store=store)
    assert seen and seen[0]["data"] == {"project_id": project["id"], "asset_id": rec["id"],
                                        "kind": "image", "filename": "shot.png"}


def test_assets_ride_the_council_brief(store, project, tmp_path):
    pid = create_persona(store, "Evidence Reader")
    shot = tmp_path / "pricing-page.png"
    shot.write_bytes(PNG_BYTES)
    img = services.attach_asset(project["id"], path=str(shot), title="Pricing page", store=store)
    services.attach_asset(project["id"],
                          content_base64=base64.b64encode(b"churn risk: price reveal").decode(),
                          filename="notes.txt", store=store)
    brief = services.brief_council(project["id"], "React to our pricing page", [pid], store=store)
    assert [a["id"] for a in brief["assets"]] == [img["id"],
                                                  services.get_asset(project["id"], "notes.txt", store=store)["id"]]
    ctx = brief["participants"][0]["agent_context"]
    assert "EVIDENCE ASSETS IN THE ROOM" in ctx
    assert f"view_asset('{project['id']}', '{img['id']}')" in ctx   # image → host must LOOK first
    assert "churn risk: price reveal" in ctx                        # document excerpt inline
    assert "EVIDENCE ASSETS ARE IN THE ROOM" in brief["instructions"]


def test_assets_survive_the_snapshot_roundtrip(store, project, tmp_path, monkeypatch):
    shot = tmp_path / "evidence.png"
    shot.write_bytes(PNG_BYTES)
    rec = services.attach_asset(project["id"], path=str(shot), title="The evidence", store=store)
    out = services.export_snapshot(store=store)
    assert out["counts"]["projects"] >= 1 and out["counts"]["assets"] == 1
    # Wipe runtime state: fresh DB + empty asset store, then import the snapshot.
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'restored.db'}")
    from sonaloop.storage import Store
    binary = config.ROOT / rec["asset_path"]
    binary.unlink()
    store2 = Store()
    services.import_snapshot(store=store2, embed=False)
    restored = services.get_asset(project["id"], rec["id"], store=store2)
    assert restored["title"] == "The evidence"
    data, _ = services.get_asset_content(project["id"], rec["id"], store=store2)
    assert data == PNG_BYTES


# ------------------------------------------------------------------ direction in/out +
# deliverable auto-attach (ticket project-assets-direction-deliverables-page-section)


def test_direction_defaults_in_and_validates(store, project, tmp_path):
    f = tmp_path / "note.txt"
    f.write_text("evidence")
    rec = services.attach_asset(project["id"], path=str(f), store=store)
    assert rec["direction"] == "in"                    # evidence is the default
    out = services.attach_asset(project["id"], path=str(f), direction="out", store=store)
    assert out["direction"] == "out"                   # explicit deliverable
    kept = services.attach_asset(project["id"], path=str(f), notes="refresh", store=store)
    assert kept["direction"] == "out"                  # re-attach without direction keeps it
    with pytest.raises(ValueError):
        services.attach_asset(project["id"], path=str(f), direction="sideways", store=store)


def test_directionless_compatibility_records_read_as_evidence(store, project, tmp_path):
    f = tmp_path / "old.txt"
    f.write_text("pre-direction record")
    rec = services.attach_asset(project["id"], path=str(f), store=store)
    p = store.get_research_project(project["id"])      # simulate a record written before the field
    p["assets"][0].pop("direction")
    store.upsert_research_project(p)
    from sonaloop.web._presence import asset_direction
    compatibility = services.get_asset(project["id"], rec["id"], store=store)
    assert "direction" not in compatibility and asset_direction(compatibility) == "in"


def _project_synthesis(store, project):
    syn = services.record_synthesis("Component finder", "start", [], {}, store=store)
    syn["project_id"] = project["id"]
    store.upsert_synthesis(syn)
    return syn


def test_export_synthesis_deliverable_attaches_out_asset(store, project, tmp_path, monkeypatch):
    monkeypatch.setattr("sonaloop.services._synthesis_pptx.export_synthesis_pptx",
                        lambda sid, store=None: b"PK\x03\x04 fake deck bytes")
    syn = _project_synthesis(store, project)
    out = tmp_path / "deck.pptx"
    res = services.export_synthesis_deliverable(syn["id"], "pptx", str(out), store=store)
    assert res["path"] == str(out) and out.read_bytes().startswith(b"PK")
    assert res["project_id"] == project["id"]
    rec = services.get_asset(project["id"], res["asset_id"], store=store)
    assert rec["direction"] == "out" and rec["kind"] == "document"
    assert rec["source"] == f'synthesis:{syn["id"]}'
    assert rec["title"] == "Component finder (PPTX)"
    with pytest.raises(ValueError):
        services.export_synthesis_deliverable(syn["id"], "docx", store=store)


def test_export_synthesis_deliverable_relative_path_lands_in_data_exports(store, project, tmp_path, monkeypatch):
    # the CWD fix: a relative/omitted out path goes to DATA_DIR/exports/, not the caller's CWD
    from sonaloop import config as config_mod
    monkeypatch.setattr(config_mod, "DATA_DIR", tmp_path / "dd")
    monkeypatch.setattr("sonaloop.services._synthesis_pptx.export_synthesis_pdf", lambda sid, store=None: b"%PDF-1.7 fake")
    syn = _project_synthesis(store, project)
    res = services.export_synthesis_deliverable(syn["id"], "pdf", store=store)
    assert res["path"] == str(tmp_path / "dd" / "exports" / f'{syn["id"]}.pdf')
    assert (tmp_path / "dd" / "exports" / f'{syn["id"]}.pdf').read_bytes().startswith(b"%PDF")


def test_export_synthesis_deliverable_reexport_supersedes_stale_record(store, project, tmp_path, monkeypatch):
    # renders are not byte-stable: a re-export gets a fresh content hash, so the bytes-keyed
    # attach upsert can't dedupe it — the deliverable seam must supersede the stale record
    renders = iter([b"PK\x03\x04 deck v1", b"PK\x03\x04 deck v2 (new timestamps)"])
    monkeypatch.setattr("sonaloop.services._synthesis_pptx.export_synthesis_pptx",
                        lambda sid, store=None: next(renders))
    syn = _project_synthesis(store, project)
    first = services.export_synthesis_deliverable(syn["id"], "pptx", str(tmp_path / "d.pptx"), store=store)
    second = services.export_synthesis_deliverable(syn["id"], "pptx", str(tmp_path / "d.pptx"), store=store)
    assert first["asset_id"] != second["asset_id"]
    deliverables = [a for a in services.list_assets(project["id"], store=store)
                    if a.get("source") == f'synthesis:{syn["id"]}']
    assert [a["id"] for a in deliverables] == [second["asset_id"]]
    # ... and the survivor RECORDS the chain (UX U8 provenance: which version it replaced)
    chain = deliverables[0].get("supersedes") or []
    assert [s["id"] for s in chain] == [first["asset_id"]]
    assert chain[0]["filename"] == "d.pptx" and chain[0]["created_at"]


def test_export_synthesis_deliverable_without_project_skips_attach(store, tmp_path, monkeypatch):
    monkeypatch.setattr("sonaloop.services._synthesis_pptx.export_synthesis_pptx", lambda sid, store=None: b"PK bytes")
    syn = services.record_synthesis("Standalone", "start", [], {}, store=store)
    res = services.export_synthesis_deliverable(syn["id"], "pptx", str(tmp_path / "d.pptx"), store=store)
    assert "asset_id" not in res and "project_id" not in res


def test_assets_render_as_tag_free_outline_rows(store, project, tmp_path, monkeypatch):
    """UX P2 (spec/ux-contract.md §3.4 / §7.2): assets are outline rows — incoming files in their phase
    flow, the deliverable at the END (the Deliver group). Since UX U8 the row deep-links to the
    asset's DETAIL page (slide-over armed, §8.1); the file itself stays one click away as the
    row's trailing download/open action."""
    monkeypatch.setattr("sonaloop.services._synthesis_pptx.export_synthesis_pptx", lambda sid, store=None: b"PK deck")
    evidence = tmp_path / "field-note.txt"
    evidence.write_text("observed in the field")
    ev = services.attach_asset(project["id"], path=str(evidence), title="Field note", store=store)
    syn = _project_synthesis(store, project)
    services.export_synthesis_deliverable(syn["id"], "pptx", str(tmp_path / "finder.pptx"), store=store)
    from starlette.testclient import TestClient
    from sonaloop import web
    client = TestClient(web.create_app())
    html = client.get(f'/jobs/{project["id"]}?lang=en').text
    assert html.count('data-rkind="asset"') == 2
    assert "Deliverable</span>" not in html and "Evidence</span>" not in html
    assert ">Assets (1)<" in html
    # the evidence row sits in the flow; the deliverable closes the outline (Deliver group)
    assert html.index("Field note") < html.index("Component finder (PPTX)")
    deliverable = next(a for a in services.list_assets(project["id"], store=store)
                       if a.get("direction") == "out")
    # the rows open the detail pages as slide-overs (U8)...
    assert f'data-drawer="/assets/{ev["id"]}"' in html
    assert f'data-drawer="/assets/{deliverable["id"]}"' in html
    # ...while the file itself stays one click away (the trailing chip: download / open)
    assert f'href="{deliverable["url"]}"' in html and f'href="{ev["url"]}"' in html
    # and there is no separate project files lens chip anymore.
    assert f'/jobs/{project["id"]}?view=files' not in html


def test_attach_prototype_shot_uses_capture(store, project, monkeypatch, tmp_path):
    # capture_prototype_shot is Playwright-backed; stub it to a stored file like the real one.
    from sonaloop import assets as assets_mod
    monkeypatch.setattr(assets_mod, "ASSETS_DIR", tmp_path / "captured")
    (tmp_path / "captured").mkdir()
    (tmp_path / "captured" / "abc.png").write_bytes(PNG_BYTES)
    monkeypatch.setattr(assets_mod, "capture_prototype_shot",
                        lambda prototype_id, store=None: "assets/abc.png")
    rec = services.attach_prototype_shot(project["id"], "proto-x", store=store)
    assert rec["kind"] == "screenshot" and rec["source"] == "prototype:proto-x"

# ---------------------------------------------------------------- W6: first-slide previews


def _deck_bytes() -> bytes:
    """A real one-slide deck through the production renderer (the W6 preview's input)."""
    from sonaloop import _deck, _pptx
    return _pptx.render(_deck.SAMPLE_SLIDES[:1], title="Preview test deck")


def test_render_first_slide_pngs_the_title_slide():
    import io
    from PIL import Image
    from sonaloop._pptx_preview import PREVIEW_WIDTH, render_first_slide
    png = render_first_slide(_deck_bytes())
    assert png and png.startswith(b"\x89PNG")
    with Image.open(io.BytesIO(png)) as im:
        assert im.width == PREVIEW_WIDTH and im.height > 0
    # graceful: bytes that aren't a deck yield None, never an exception (badge fallback)
    assert render_first_slide(b"PK\x03\x04 not a real deck") is None


def test_attach_asset_writes_pptx_preview_beside_binary(store, project):
    from pathlib import Path
    from sonaloop.services._project_assets import _assets_dir
    rec = services.attach_asset(project["id"], content_base64=base64.b64encode(_deck_bytes()).decode(),
                                filename="positioning-deck.pptx", direction="out", store=store)
    assert rec["preview_url"].endswith(".preview.png")
    sha = Path(rec["asset_path"]).stem
    assert rec["preview_url"] == f"/data/assets/{sha}.preview.png"
    assert (_assets_dir() / f"{sha}.preview.png").read_bytes().startswith(b"\x89PNG")
    # non-PPTX documents keep the badge: no preview_url content
    txt = services.attach_asset(project["id"], content_base64=base64.b64encode(b"plain notes").decode(),
                                filename="notes.txt", store=store)
    assert txt["preview_url"] == ""
    # a PPTX that doesn't open as a deck degrades the same way (graceful, no crash)
    fake = services.attach_asset(project["id"], content_base64=base64.b64encode(b"PK fake").decode(),
                                 filename="broken.pptx", store=store)
    assert fake["preview_url"] == ""


def test_ensure_asset_preview_backfills_compatibility_records(store, project):
    from pathlib import Path
    from sonaloop.services._project_assets import _assets_dir
    rec = services.attach_asset(project["id"], content_base64=base64.b64encode(_deck_bytes()).decode(),
                                filename="compatibility-deck.pptx", store=store)
    sha = Path(rec["asset_path"]).stem
    # simulate a pre-W6 record: no preview field, no preview file
    (_assets_dir() / f"{sha}.preview.png").unlink()
    proj = store.get_research_project(project["id"])
    for a in proj["assets"]:
        a.pop("preview_url", None)
    store.upsert_research_project(proj)
    updated = services.ensure_asset_preview(project["id"], store=store)
    assert [a["id"] for a in updated] == [rec["id"]]
    fresh = services.get_asset(project["id"], rec["id"], store=store)
    assert fresh["preview_url"] == f"/data/assets/{sha}.preview.png"
    assert (_assets_dir() / f"{sha}.preview.png").exists()
    # idempotent: a second run finds nothing to do
    assert services.ensure_asset_preview(project["id"], store=store) == []


def test_file_cards_use_the_preview_as_thumb_stage(store, project):
    from sonaloop.web._presence import file_stage
    rec = services.attach_asset(project["id"], content_base64=base64.b64encode(_deck_bytes()).decode(),
                                filename="deck.pptx", direction="out", store=store)
    stage = file_stage(rec)
    assert rec["preview_url"] in stage and "sl-file__thumb" in stage
    # no preview (a pdf, a plain doc): the extension badge stays
    txt = services.attach_asset(project["id"], content_base64=base64.b64encode(b"x").decode(),
                                filename="brief.pdf", store=store)
    assert "sl-file__ext" in file_stage(txt) and "img" not in file_stage(txt)


def test_asset_binary_lives_in_the_served_data_tree(store, project):
    """The record's `url` must be REAL: the binary lands under config.DATA_DIR — the
    tree the web app mounts at /data — not under ROOT (= site-packages on an installed
    package: unserved, and erased by the next reinstall)."""
    from pathlib import Path

    from sonaloop import config
    rec = services.attach_asset(project["id"], content_base64=base64.b64encode(b"hello").decode(),
                                filename="note.txt", store=store)
    name = Path(rec["asset_path"]).name
    assert (Path(config.DATA_DIR) / "assets" / name).read_bytes() == b"hello"
    assert rec["url"] == f"/data/assets/{name}"
    data, _ = services.get_asset_content(project["id"], rec["id"], store=store)
    assert data == b"hello"


def test_export_synthesis_deliverable_returns_download_url(store, project, monkeypatch):
    """The hand-off contract for remote (MCP) hosts: the result's `url` is the absolute,
    auth-gated DOWNLOAD link (the supersede-managed asset URL once attached) and
    `project_url` points at the owning project — a server filesystem path alone is not a
    hand-off ('Datei liegt auf dem Sonaloop-Server' was the whole bug)."""
    from pathlib import Path

    from sonaloop import config
    monkeypatch.setenv("SONALOOP_PUBLIC_BASE_URL", "https://app.sonaloop.test")
    monkeypatch.setattr("sonaloop.services._synthesis_pptx.export_synthesis_pptx", lambda sid, store=None: b"PK deck")
    syn = _project_synthesis(store, project)
    res = services.export_synthesis_deliverable(syn["id"], "pptx", store=store)
    rec = services.get_asset(project["id"], res["asset_id"], store=store)
    assert res["url"] == "https://app.sonaloop.test" + rec["url"]
    assert res["project_url"] == f'https://app.sonaloop.test/jobs/{project["id"]}'
    assert (Path(config.DATA_DIR) / "assets" / Path(rec["asset_path"]).name).read_bytes() == b"PK deck"


def test_export_synthesis_deliverable_without_project_still_links_the_export(store, monkeypatch):
    monkeypatch.setenv("SONALOOP_PUBLIC_BASE_URL", "https://app.sonaloop.test")
    monkeypatch.setattr("sonaloop.services._synthesis_pptx.export_synthesis_pptx", lambda sid, store=None: b"PK bytes")
    syn = services.record_synthesis("Standalone", "start", [], {}, store=store)
    res = services.export_synthesis_deliverable(syn["id"], "pptx", store=store)
    assert res["url"] == f'https://app.sonaloop.test/data/exports/{syn["id"]}.pptx'
