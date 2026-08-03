"""Shareable read-only report bundle (ticket shareable-report-bundle).

export_synthesis_html renders the SAME inspector document (web/_report.render_report — the one
render path the synthesis page and the PDF exporter also use) into
`data/export/share/<token>/index.html`: self-contained (CSS + charts + figures + avatars inlined),
zero external requests, opens from file://, no app chrome, internal anchors intact, footer stamped
with project · generated date · sonaloop version. Self-containment is the TESTED invariant here.
"""
from __future__ import annotations

import base64
import re

import pytest

from conftest import create_persona
from sonaloop import services

_PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==")

# The app-chrome markers of web/_components._layout — none may leak into the bundle's MARKUP.
# (The inlined stylesheet legitimately still carries .sl-sidebar etc. as dormant selectors.)
_CHROME = ('class="sl-sidebar', 'class="sl-topbar', "sl-sb-search", "data-cmdk-open",
           "data-sidebar-toggle", "<script")


def _body(html: str) -> str:
    """The rendered markup after the inlined <style> head — where chrome could actually leak."""
    return html.split("</head>", 1)[1]


def _data_dir(tmp_path, monkeypatch):
    from sonaloop import config
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    return tmp_path


def _assert_self_contained(html: str) -> None:
    """Walk every reference the browser would resolve: src/href attributes and CSS url() values.
    External (http(s)://, protocol-relative //) and absolute (/static/, /data/, …) refs are
    forbidden; data: URIs and #anchors are fine."""
    for m in re.finditer(r'(?:src|href)="(?!#|data:)([^"]*)"', html):
        ref = m.group(1)
        assert not ref.startswith(("http://", "https://", "//", "/")), f"non-self-contained ref: {ref}"
    for m in re.finditer(r"url\(\s*['\"]?(?!data:)([^)'\"]+)", html):
        ref = m.group(1)
        assert not ref.startswith(("http", "//", "/")), f"non-self-contained css url: {ref}"


def _convergence_synthesis(store, tmp_path):
    """A convergence synthesis citing a council whose persona HAS an avatar file — exercises
    findings, the recommendation 2×2, sentiment analytics (avatar <img>) and council ref links."""
    proj = services.create_research_project("Pension navigator", goal="Plan retirement?", store=store)
    pid = create_persona(store, "Ava Tester")
    p = store.get_persona(pid)
    av = tmp_path / "personas" / "ava" / "avatar.png"
    av.parent.mkdir(parents=True, exist_ok=True)
    av.write_bytes(_PNG_1X1)
    p["avatar"] = {"path": "data/personas/ava/avatar.png"}
    store.upsert_persona(p)
    c = services.record_council(
        proj["id"], "Would a digital pension check help?", [pid],
        statements=[{"persona_id": pid, "text": "I would **try** it", "stance": {"value": 1}}],
        votes=[{"persona_id": pid, "vote": "support"}], summary="mixed", store=store)
    return services.record_synthesis(
        "Pension check potential", "hmw", [c["id"]],
        {"gesamtbild": "Overall **positive** across the chain.", "positionierung": "Niche first.",
         "findings": [
             {"kind": "key_problem", "text": "Evenings are the bottleneck"},
             {"kind": "recommendation", "text": "Auto shopping list", "score": {"effort": 2, "value": 5}},
             {"kind": "open_question", "text": "Does it survive week 3?"}]},
        goal="Is a pension check valuable?", store=store)


# ----------------------------------------------------------------- the bundle: content + chrome

def test_bundle_renders_the_document_without_chrome_and_self_contained(store, tmp_path, monkeypatch):
    data = _data_dir(tmp_path, monkeypatch)
    syn = _convergence_synthesis(store, tmp_path)
    out = services.export_synthesis_html(syn["id"], store=store)
    # path: data/export/share/<token>/index.html, token an unguessable uuid4 hex (no timestamps)
    assert re.fullmatch(r"[0-9a-f]{32}", out["token"])
    bundle = data / "export" / "share" / out["token"] / "index.html"
    assert str(bundle) == out["path"] and bundle.is_file()
    html = bundle.read_text(encoding="utf-8")
    # the document content is there (one render path: the report shell + findings + analytics)
    assert "Pension check potential" in html
    assert "Evenings are the bottleneck" in html and "Auto shopping list" in html
    assert "<strong>positive</strong>" in html            # markdown rendered, not raw
    assert "rp-cover" in html                             # the report shell, same as the inspector
    # zero external/absolute refs; the avatar <img> rides inline as a data: URI
    _assert_self_contained(html)
    assert 'src="data:image/png;base64,' in html
    # no nav/sidebar/search/edit chrome (and no scripts at all) in the bundle's markup
    for marker in _CHROME:
        assert marker not in _body(html), f"chrome leaked into the bundle: {marker}"
    # inspector deep-links (council ref rows, persona links) became plain text, not dead routes
    assert 'href="/' not in html
    assert "share-unlinked" in html
    assert "Would a digital pension check help?" in html  # the unwrapped ref kept its text
    # footer stamps project · generated date · sonaloop version
    from sonaloop import __version__
    from sonaloop.config import utc_now_iso
    foot = html.split('<footer class="share-foot">', 1)[1].split("</footer>", 1)[0]
    assert "Pension navigator" in foot and f"sonaloop {__version__}" in foot
    assert utc_now_iso()[:10] in foot


def test_project_report_bundle_keeps_internal_anchors_and_inlines_figures(store, tmp_path, monkeypatch):
    _data_dir(tmp_path, monkeypatch)
    from sonaloop import assets
    monkeypatch.setattr(assets, "ASSETS_DIR", tmp_path / "assets")
    aid = assets.put_asset(_PNG_1X1, "png")
    store.upsert_synthesis({
        "id": "rep1", "title": "Demo — Report", "scope": "project", "project_id": "",
        "created_at": "2026-06-08T00:00:00+00:00", "lead": "How it was built.", "council_ids": [],
        "findings": [], "statements": [], "prompts": [], "graph_snapshot": None,
        "sections": [
            {"id": "s1", "heading": "Findings", "markdown": "Body one. ![[fig:1]]",
             "citations": [{"study_id": "s_x", "quote": "verbatim quote"}], "source_study_ids": [],
             "figures": [{"kind": "asset", "id": aid, "caption": "Shot"},
                         {"kind": "chart", "of": "pie",
                          "series": [{"label": "A", "value": 3}, {"label": "B", "value": 1}]}]},
            {"id": "s2", "heading": "Next steps", "markdown": "Body two.", "citations": [],
             "source_study_ids": [], "figures": []}]})
    out = services.export_synthesis_html("rep1", store=store)
    html = (tmp_path / "export" / "share" / out["token"] / "index.html").read_text(encoding="utf-8")
    _assert_self_contained(html)
    # TOC anchors keep working from file://: the #href and its target id both survive
    assert 'href="#rp-s1"' in html and 'id="rp-s1"' in html
    assert 'href="#rp-s2"' in html and 'id="rp-s2"' in html
    # citations render (footnote-style) and the asset figure rides inline; charts are inline SVG/CSS
    assert "verbatim quote" in html
    assert 'src="data:image/png;base64,' in html
    assert "conic-gradient" in html
    for marker in _CHROME:
        assert marker not in _body(html)


@pytest.mark.parametrize("tenant", [False, True], ids=["sqlite-data-url", "postgres-opaque-url"])
def test_project_asset_is_inlined_for_html_and_pdf(store, tmp_path, monkeypatch, tenant):
    """Both browser URL modes are resolved to bytes before either file:// export is handed off."""
    from pathlib import Path
    from urllib.parse import unquote, urlparse

    from sonaloop import browser, config
    from sonaloop.services import _synthesis as S

    _data_dir(tmp_path, monkeypatch)
    project = services.create_research_project("Tenant report", goal="g", store=store)
    asset = services.attach_asset(
        project["id"], content_base64=base64.b64encode(_PNG_1X1).decode(),
        filename="shot.png", store=store)
    store.upsert_synthesis({
        "id": "tenant-rep", "title": "Tenant — Report", "scope": "project",
        "project_id": project["id"], "created_at": "2026-06-08T00:00:00+00:00",
        "lead": "", "council_ids": [], "findings": [], "statements": [], "prompts": [],
        "graph_snapshot": None,
        "sections": [{"id": "s1", "heading": "H", "markdown": "Body.", "citations": [],
                      "source_study_ids": [],
                      "figures": [{"kind": "asset", "id": asset["id"], "caption": "Shot"}]}],
    })

    # Keep the file partition hermetic while toggling only the browser-URL strategy.
    partition_token = config.set_request_partition(config.DATA_DIR)
    monkeypatch.setattr(config, "postgres_row_tenancy_enabled", lambda: tenant)
    try:
        out = services.export_synthesis_html("tenant-rep", store=store)
        html = Path(out["path"]).read_text(encoding="utf-8")
        _assert_self_contained(html)
        assert 'src="data:image/png;base64,' in html
        assert f"/assets/{asset['id']}/content" not in html

        # An opaque route is denied without the exact project context.
        tag = f'<img src="/assets/{asset["id"]}/content">'
        assert "share-missing" in S._share_inline_images(tag, store=store)
        other = services.create_research_project("Other", goal="g", store=store)
        assert "share-missing" in S._share_inline_images(
            tag, store=store, project_id=other["id"])

        rendered_pdf_html = {}

        class _Page:
            def goto(self, url, **_kwargs):
                rendered_pdf_html["value"] = Path(unquote(urlparse(url).path)).read_text(
                    encoding="utf-8")

            def emulate_media(self, **_kwargs):
                pass

            def wait_for_timeout(self, _milliseconds):
                pass

            def pdf(self, **_kwargs):
                return b"%PDF-tenant"

        class _Browser:
            def new_page(self):
                return _Page()

            def close(self):
                pass

        class _Playwright:
            chromium = type("Chromium", (), {"launch": staticmethod(lambda: _Browser())})()

        class _PlaywrightContext:
            def __enter__(self):
                return _Playwright()

            def __exit__(self, *_args):
                pass

        monkeypatch.setattr(browser, "available", lambda: True)
        monkeypatch.setattr("playwright.sync_api.sync_playwright", lambda: _PlaywrightContext())
        assert services.export_synthesis_pdf("tenant-rep", store=store) == b"%PDF-tenant"
        assert 'src="data:image/png;base64,' in rendered_pdf_html["value"]
        assert f"/assets/{asset['id']}/content" not in rendered_pdf_html["value"]
    finally:
        config.reset_request_partition(partition_token)


def test_postgres_persona_avatar_route_is_inlined_without_project_context(
        store, tmp_path, monkeypatch):
    from sonaloop import config
    from sonaloop.services import _synthesis as S

    _data_dir(tmp_path, monkeypatch)
    pid = create_persona(store, "Cloud Avatar")
    persona = store.get_persona(pid)
    target = tmp_path / "avatars" / "cloud-avatar.png"
    target.parent.mkdir(parents=True)
    target.write_bytes(_PNG_1X1)
    persona["avatar"] = {"path": "data/avatars/cloud-avatar.png"}
    store.upsert_persona(persona)

    partition_token = config.set_request_partition(tmp_path)
    monkeypatch.setattr(config, "postgres_row_tenancy_enabled", lambda: True)
    try:
        tag = f'<img src="/personas/{pid}/avatar">'
        html = S._share_inline_images(tag, store=store)
        assert 'src="data:image/png;base64,' in html
        assert f"/personas/{pid}/avatar" not in html
        assert "share-missing" in S._share_inline_images(
            '<img src="/personas/../../secret/avatar">', store=store)
    finally:
        config.reset_request_partition(partition_token)


def test_missing_media_drops_instead_of_shipping_broken_refs(store, tmp_path, monkeypatch):
    _data_dir(tmp_path, monkeypatch)
    store.upsert_synthesis({
        "id": "rep2", "title": "G — Report", "scope": "project", "project_id": "",
        "created_at": "2026-06-08T00:00:00+00:00", "lead": "", "council_ids": [],
        "findings": [], "statements": [], "prompts": [], "graph_snapshot": None,
        "sections": [{"id": "s1", "heading": "H", "markdown": "Body.", "citations": [],
                      "source_study_ids": [],
                      "figures": [{"kind": "asset", "id": "assets/nope.png", "caption": "gone"}]}]})
    out = services.export_synthesis_html("rep2", store=store)
    html = (tmp_path / "export" / "share" / out["token"] / "index.html").read_text(encoding="utf-8")
    _assert_self_contained(html)
    assert "<img" not in _body(html)                       # the unresolvable figure dropped honestly


# ----------------------------------------------------------------- token + path containment

def test_each_export_mints_a_fresh_unguessable_token(store, tmp_path, monkeypatch):
    _data_dir(tmp_path, monkeypatch)
    syn = _convergence_synthesis(store, tmp_path)
    a = services.export_synthesis_html(syn["id"], store=store)
    b = services.export_synthesis_html(syn["id"], store=store)
    assert a["token"] != b["token"]                        # a new share link per export, never reused
    assert re.fullmatch(r"[0-9a-f]{32}", b["token"])


def test_out_dir_must_stay_inside_the_data_dir(store, tmp_path, monkeypatch):
    _data_dir(tmp_path / "data", monkeypatch)
    (tmp_path / "data").mkdir()
    syn = _convergence_synthesis(store, tmp_path / "data")
    with pytest.raises(ValueError, match="escapes the data dir"):
        services.export_synthesis_html(syn["id"], out_dir=str(tmp_path / "elsewhere"), store=store)
    with pytest.raises(ValueError, match="escapes the data dir"):
        services.export_synthesis_html(syn["id"], out_dir="../outside", store=store)
    # a RELATIVE dir resolves under DATA_DIR and is fine
    out = services.export_synthesis_html(syn["id"], out_dir="export/custom", store=store)
    assert (tmp_path / "data" / "export" / "custom" / out["token"] / "index.html").is_file()


# --------------------------------------------------------------- review fixes (post-processors)

def test_inliner_unescapes_attr_src_and_caps_size(tmp_path, monkeypatch):
    from sonaloop import config
    from sonaloop.services import _synthesis as S
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    (tmp_path / "figs").mkdir(parents=True)
    (tmp_path / "figs" / "a&b.png").write_bytes(_PNG_1X1)
    # the renderer attribute-escapes src — the file on disk is a&b.png, the markup says a&amp;b.png
    out = S._share_inline_images('<img src="/data/figs/a&amp;b.png">', missing_label="gone")
    assert out.startswith('<img src="data:image/png;base64,')
    # past the per-file budget: a visible note, never an empty husk or a 40 MB index.html
    monkeypatch.setattr(S, "_SHARE_INLINE_MAX_BYTES", 4)
    out = S._share_inline_images('<img src="/data/figs/a&amp;b.png">', missing_label="gone")
    assert out == '<span class="share-missing">[gone]</span>'


def test_inliner_denies_external_src_by_default():
    from sonaloop.services import _synthesis as S
    for src in ("https://evil.example/x.png", "//evil.example/x.png", "relative.png"):
        out = S._share_inline_images(f'<IMG SRC="{src}">', missing_label="gone")
        assert "evil.example" not in out
        assert out == '<span class="share-missing">[gone]</span>'
    keep = '<img src="data:image/png;base64,AAAA">'
    assert S._share_inline_images(keep) == keep


def test_unwrapped_links_keep_their_class(tmp_path):
    from sonaloop.services import _synthesis as S
    out = S._share_rewrite_links('<a class="ref-row" href="/councils/c1">cited</a>')
    assert out == '<span class="ref-row share-unlinked">cited</span>'   # layout class survives
    out = S._share_rewrite_links("<A HREF='https://evil.example'>live</A>")
    assert "evil.example" not in out and "share-unlinked" in out        # case/quote-insensitive
    anchor = '<a href="#rp-s1">toc</a>'
    assert S._share_rewrite_links(anchor) == anchor                     # internal anchors live
