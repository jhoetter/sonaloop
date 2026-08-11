"""Bounded Inspector thumbnails keep originals private and workspace-scoped."""
from __future__ import annotations

import base64
import io

from PIL import Image
from starlette.testclient import TestClient

from conftest import create_persona
from sonaloop import config, services, web


def _png(width: int, height: int, color: tuple[int, int, int]) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (width, height), color).save(out, format="PNG")
    return out.getvalue()


def _image(response) -> Image.Image:
    image = Image.open(io.BytesIO(response.content))
    image.load()
    return image


def test_avatar_atoms_use_bounded_webp_but_detail_keeps_original(store):
    pid = create_persona(store, "Thumbnail Persona")
    persona = store.get_persona(pid)
    original = _png(1024, 768, (180, 60, 40))
    target = config.partition_dir() / "avatars" / "thumbnail-persona.png"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(original)
    persona["avatar"] = {"path": "data/avatars/thumbnail-persona.png"}
    store.upsert_persona(persona)

    client = TestClient(web.create_app())
    listing = client.get("/personas?lang=en").text
    assert f'src="/personas/{pid}/avatar/thumbnail"' in listing

    thumb = client.get(f"/personas/{pid}/avatar/thumbnail")
    assert thumb.status_code == 200
    assert thumb.headers["content-type"] == "image/webp"
    assert thumb.headers["cache-control"] == "private, no-store"
    thumb_image = _image(thumb)
    assert thumb_image.format == "WEBP"
    assert max(thumb_image.size) == 96
    assert len(thumb.content) < len(original)

    full = client.get(f"/personas/{pid}/avatar")
    assert full.status_code == 200 and full.headers["content-type"] == "image/png"
    assert _image(full).size == (1024, 768)
    detail = client.get(f"/personas/{pid}?lang=en").text
    assert 'src="/data/avatars/thumbnail-persona.png"' in detail
    assert f'src="/personas/{pid}/avatar/thumbnail"' not in detail.split(
        'class="identity"', 1)[-1].split("</section>", 1)[0]


def test_asset_gallery_uses_thumbnail_and_open_action_keeps_original(store):
    project = services.create_research_project("Thumbnail assets", goal="g", store=store)
    original = _png(1600, 900, (30, 100, 180))
    asset = services.attach_asset(
        project["id"], content_base64=base64.b64encode(original).decode(),
        filename="wide-screen.png", kind="screenshot", store=store)

    client = TestClient(web.create_app())
    page = client.get(f'/jobs/{project["id"]}?lang=en').text
    assert f'src="/assets/{asset["id"]}/thumbnail"' in page
    assert f'href="{asset["url"]}"' in page, "opening still targets the original"

    thumb = client.get(f'/assets/{asset["id"]}/thumbnail')
    assert thumb.status_code == 200
    assert thumb.headers["content-type"] == "image/webp"
    assert thumb.headers["cache-control"] == "private, no-store"
    thumb_image = _image(thumb)
    assert thumb_image.format == "WEBP"
    assert thumb_image.size == (640, 360)
    assert len(thumb.content) < len(original)
    # The binary route is opaque-id-only; the detail-page filename compatibility
    # must not become an alternate thumbnail capability.
    assert client.get("/assets/wide-screen.png/thumbnail").status_code == 404


def test_same_opaque_thumbnail_urls_re_resolve_active_workspace(
        tmp_path, monkeypatch):
    """Stable catalog ids cannot replay alpha's pixels after switching to beta."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://unused/thumbnail-tenancy")
    monkeypatch.setenv("SONALOOP_PG_TENANT", "1")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "runtime")
    monkeypatch.setattr(web, "DATA_DIR", tmp_path / "runtime")

    avatar_record = {
        "id": "persona_shared", "slug": "shared", "display_name": "Shared",
        "avatar": {"path": "data/avatars/shared.png"},
    }
    asset_record = {
        "id": "asset_shared", "kind": "screenshot", "filename": "shared.png",
        "media_type": "image/png", "asset_path": "data/assets/shared.png",
        "url": "/data/assets/shared.png",
    }
    project = {"id": "rproject_shared", "title": "Shared", "assets": [asset_record]}

    class _ScopedStore:
        def get_persona(self, persona_id):
            return dict(avatar_record) if persona_id == "persona_shared" else None

        def list_research_projects(self):
            return [dict(project)]

        def get_research_project(self, project_id):
            return dict(project) if project_id == "rproject_shared" else None

        def close(self):
            pass

    from sonaloop.web.pages import assets as assets_page
    from sonaloop.web.pages import personas as personas_page
    monkeypatch.setattr(assets_page, "Store", _ScopedStore)
    monkeypatch.setattr(personas_page, "Store", _ScopedStore)

    colours = {"ws_alpha": (210, 30, 30), "ws_beta": (30, 30, 210)}
    for workspace_id, colour in colours.items():
        token = config.set_request_tenant_scope([workspace_id], workspace_id)
        try:
            partition = config.partition_dir()
            for folder in ("avatars", "assets"):
                target = partition / folder / "shared.png"
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(_png(400, 300, colour))
        finally:
            config.reset_request_tenant_scope(token)

    client = TestClient(web.create_app())
    # No authenticated active workspace: fail before touching a record or file.
    assert client.get("/personas/persona_shared/avatar/thumbnail").status_code == 404
    assert client.get("/assets/asset_shared/thumbnail").status_code == 404

    seen: dict[str, tuple[int, int, int]] = {}
    for workspace_id in colours:
        token = config.set_request_tenant_scope([workspace_id], workspace_id)
        try:
            avatar = client.get("/personas/persona_shared/avatar/thumbnail")
            asset = client.get("/assets/asset_shared/thumbnail")
        finally:
            config.reset_request_tenant_scope(token)
        assert avatar.status_code == asset.status_code == 200
        assert avatar.headers["cache-control"] == asset.headers["cache-control"] == \
            "private, no-store"
        pixel = _image(avatar).convert("RGB").getpixel((20, 20))
        seen[workspace_id] = pixel
        asset_pixel = _image(asset).convert("RGB").getpixel((20, 20))
        assert max(abs(pixel[i] - asset_pixel[i]) for i in range(3)) < 5

    assert seen["ws_alpha"][0] > seen["ws_alpha"][2]
    assert seen["ws_beta"][2] > seen["ws_beta"][0]
