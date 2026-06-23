"""Keyboard shortcuts + ? cheat sheet (ticket keyboard-shortcuts-cheatsheet).

The registry (web/_keymap.py BINDINGS) is the single source of truth: the overlay and
the client keymap config are generated from it, so these tests assert the generated
surfaces stay complete rather than re-listing bindings by hand."""
from __future__ import annotations

import json

from starlette.testclient import TestClient

from sonaloop import web
from sonaloop.web._keymap import BINDINGS, keymap_markup, sibling_urls
from sonaloop.web._i18n import STRINGS

from conftest import create_persona


def _client() -> TestClient:
    return TestClient(web.create_app())


def test_every_binding_renders_in_the_cheat_sheet():
    """Registry → overlay completeness: each binding's localised description AND its
    keys appear in the overlay, and the JSON config arms exactly the registry."""
    html = keymap_markup()
    for b in BINDINGS:
        assert b["desc"]() in html, f"binding {b['keys']!r} missing from the cheat sheet"
    cfg = json.loads(html.split('id="km-cfg" type="application/json">')[1].split("</script>")[0])
    assert [c["keys"] for c in cfg["bindings"]] == [b["keys"] for b in BINDINGS]
    # required chords are all declared (the ticket's g-roster)
    keys = {b["keys"] for b in BINDINGS}
    for chord in ("g h", "g p", "g c", "g s", "g a", "g r", "g d", "?", "j", "k", "[", "]"):
        assert chord in keys, f"required binding {chord!r} not in the registry"
    # a11y: the overlay is a modal dialog
    assert 'aria-modal="true"' in html and 'role="dialog"' in html


def test_binding_descriptions_exist_in_both_languages():
    for b in BINDINGS:
        en = b["desc"]()                                  # default test language is en
        assert en and isinstance(en, str)
    for key in ("kbd_hint", "kbd_cheatsheet_h", "kbd_scope_global", "kbd_scope_lists",
                "kbd_scope_detail", "kbd_open_cheatsheet", "kbd_open_palette"):
        assert key in STRINGS["de"] and key in STRINGS["en"]


def test_chrome_includes_keymap_overlay_hint_and_script(store):
    html = _client().get("/?lang=en").text
    assert 'id="kmov"' in html and 'id="km-cfg"' in html      # overlay + generated config
    assert "data-km-open" in html and STRINGS["en"]["kbd_hint"] in html   # ? discovery hint
    assert "km-mod" in html                                   # platform-modifier glyph hook
    assert STRINGS["en"]["kbd_scope_lists"] in html           # grouped by scope
    # the palette carries a jump command for the cheat sheet
    assert "#shortcuts" in html and STRINGS["en"]["kbd_cheatsheet_h"] in html


def test_list_pages_carry_the_row_focus_hook(store):
    create_persona(store, "Key Nav")
    client = _client()
    for path in ("/personas", "/councils", "/sessions", "/activity", "/syntheses"):
        assert "data-keynav" in client.get(path).text, f"{path} misses the j/k rows hook"


def test_detail_pages_emit_server_provided_sibling_urls(store):
    a = create_persona(store, "Alpha Person")
    b = create_persona(store, "Beta Person")
    html = _client().get(f"/personas/{a}").text
    assert 'id="km-siblings"' in html
    assert f'data-next="/personas/{b}"' in html
    assert "data-prev" not in html.split('id="km-siblings"')[1][:120]   # first record: no prev
    html_b = _client().get(f"/personas/{b}").text
    assert f'data-prev="/personas/{a}"' in html_b


def test_sibling_urls_skip_gracefully():
    assert sibling_urls(["/a", "/b"], "/missing") == (None, None)   # page can't place itself
    assert sibling_urls(["/a"], "/a") == (None, None)               # no siblings to walk
    assert sibling_urls(["/a", "/b", "/c"], "/b") == ("/a", "/c")


def test_old_inline_g_chord_nav_is_gone():
    """The ad-hoc 'g then o/p' jump map in APP_JS must not survive beside the registry
    (it would shadow the registry's `g r` with /jobs)."""
    from sonaloop.web._components import APP_JS
    assert "o:'/jobs'" not in APP_JS
