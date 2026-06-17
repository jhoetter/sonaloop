"""Keyboard shortcuts: ONE registry, the JS layer and the `?` cheat sheet generated from it.

Self-contained (CSS + markup + JS, the _palette.py pattern), injected once by _layout so
every page gets the same bindings. Every binding is declared exactly once in BINDINGS —
key/chord, scope (global | lists | detail), i18n description (a lambda so it resolves per
request), and the action (navigate a URL, or a named JS hook implemented in KEYMAP_JS).
The cheat-sheet overlay AND the client keymap config are both rendered FROM the registry,
so adding a binding here automatically shows it in the overlay and arms it in the browser.

Behaviour contract (mirrored by the React apps — see docs/keyboard-conventions.md):
  - all bindings are disabled while typing (input/textarea/select/contenteditable);
  - bindings never fire with a modifier held, so Cmd/Ctrl+K (the palette) is untouched;
  - `g` chords have a ~900 ms window; Esc cancels a pending chord and closes overlays;
  - modifier keys render platform-correct glyphs (⌘ on macOS, Ctrl elsewhere — JS swaps);
  - list row-focus (j/k/Enter) targets the page's [data-keynav] rows container and skips
    gracefully when there is none; sibling nav ([ / ]) reads the server-provided
    #km-siblings marker (sibling_attrs below) and skips when the page doesn't emit one.
"""
from __future__ import annotations

import json

from ._i18n import t
from ._html import h, raw

# ------------------------------------------------------------------- the registry
# keys: space-separated chord tokens ("g h"), "mod+" prefix for the platform modifier.
# scope: "global" | "lists" | "detail" (the cheat sheet groups by these).
# desc: lambda -> localized description (literal t() calls keep the i18n scan honest).
# action: {"nav": url} (navigate) or {"hook": name} (a named handler in KEYMAP_JS).
#         {"hook": "palette"} is display-only here — web/_palette.py owns Cmd/Ctrl+K.

BINDINGS: list[dict] = [
    {"keys": "?", "scope": "global", "desc": lambda: t("kbd_open_cheatsheet"),
     "action": {"hook": "cheatsheet"}},
    {"keys": "mod+k", "scope": "global", "desc": lambda: t("kbd_open_palette"),
     "action": {"hook": "palette"}},
    {"keys": "g h", "scope": "global", "desc": lambda: t("kbd_go_home"), "action": {"nav": "/"}},
    {"keys": "g p", "scope": "global", "desc": lambda: t("kbd_go_personas"), "action": {"nav": "/personas"}},
    {"keys": "g l", "scope": "global", "desc": lambda: t("kbd_go_library"), "action": {"nav": "/library"}},
    {"keys": "g c", "scope": "global", "desc": lambda: t("kbd_go_councils"), "action": {"nav": "/councils"}},
    {"keys": "g s", "scope": "global", "desc": lambda: t("kbd_go_syntheses"), "action": {"nav": "/syntheses"}},
    {"keys": "g a", "scope": "global", "desc": lambda: t("kbd_go_activity"), "action": {"nav": "/activity"}},
    {"keys": "g r", "scope": "global", "desc": lambda: t("kbd_go_runs"), "action": {"nav": "/runs"}},
    {"keys": "g d", "scope": "global", "desc": lambda: t("kbd_go_docs"), "action": {"nav": "/documentation"}},
    {"keys": "esc", "scope": "global", "desc": lambda: t("kbd_close_overlays"), "action": {"hook": "close"}},
    {"keys": "j", "scope": "lists", "desc": lambda: t("kbd_list_next"), "action": {"hook": "list-next"}},
    {"keys": "k", "scope": "lists", "desc": lambda: t("kbd_list_prev"), "action": {"hook": "list-prev"}},
    {"keys": "enter", "scope": "lists", "desc": lambda: t("kbd_list_open"), "action": {"hook": "list-open"}},
    {"keys": "o", "scope": "lists", "desc": lambda: t("kbd_list_open_full"), "action": {"hook": "list-open-full"}},
    {"keys": "[", "scope": "detail", "desc": lambda: t("kbd_sib_prev"), "action": {"hook": "sib-prev"}},
    {"keys": "]", "scope": "detail", "desc": lambda: t("kbd_sib_next"), "action": {"hook": "sib-next"}},
]

_SCOPES = ("global", "lists", "detail")


def _scope_labels() -> dict[str, str]:
    return {"global": t("kbd_scope_global"), "lists": t("kbd_scope_lists"),
            "detail": t("kbd_scope_detail")}


# --------------------------------------------------- server-provided sibling URLs

def sibling_urls(urls: list[str], current: str) -> tuple[str | None, str | None]:
    """(prev, next) of `current` within the ordered sibling `urls`; (None, None) when
    the page can't place itself (deleted record, filtered list)."""
    try:
        i = urls.index(current)
    except ValueError:
        return None, None
    return (urls[i - 1] if i > 0 else None,
            urls[i + 1] if i + 1 < len(urls) else None)


def sibling_attrs(prev_url: str | None, next_url: str | None) -> str:
    """The hidden marker a detail page emits when it KNOWS its siblings — the [ / ]
    bindings read it; pages that don't emit it are skipped gracefully."""
    if not (prev_url or next_url):
        return ""
    return h("span", {"id": "km-siblings", "hidden": True,
                      "data-prev": prev_url or None, "data-next": next_url or None})


# ------------------------------------------------------------- overlay + JS config

_KEY_GLYPHS = {"enter": "↵", "esc": "Esc"}


def _kbd_html(keys: str) -> str:
    """`"g h"` → two <kbd>; `"mod+k"` → the platform-modifier <kbd> (JS swaps ⌘→Ctrl
    off-mac) + the key. Named keys map to their glyph."""
    parts = []
    for tok in keys.split(" "):
        if tok.startswith("mod+"):
            parts.append(h("kbd", {"class_": "km-mod"}, "⌘"))
            tok = tok[len("mod+"):]
        parts.append(h("kbd", {}, _KEY_GLYPHS.get(tok, tok)))
    return h("span", {"class_": "km-keys"}, *parts)


def keymap_markup() -> str:
    """Per-request cheat-sheet overlay (localised, grouped by scope) + the keymap JSON
    config — BOTH generated from BINDINGS, so the sheet can never miss a binding."""
    labels = _scope_labels()
    groups = []
    for scope in _SCOPES:
        rows = [h("div", {"class_": "km-row"},
                  h("span", {"class_": "km-d"}, b["desc"]()), raw(_kbd_html(b["keys"])))
                for b in BINDINGS if b["scope"] == scope]
        if rows:
            groups.append(h("div", {"class_": "km-grp"},
                            h("h3", {}, labels[scope]), *rows))
    overlay = h("div", {"class_": "kmov", "id": "kmov", "hidden": True},
                h("div", {"class_": "kmov-bd", "data-km-close": True}),
                h("div", {"class_": "km-panel", "role": "dialog", "aria-modal": "true",
                          "aria-label": t("kbd_cheatsheet_h"), "tabindex": "-1"},
                  h("div", {"class_": "km-head"},
                    h("h2", {}, t("kbd_cheatsheet_h")),
                    h("button", {"type": "button", "class_": "sl-overlay-close", "data-km-close": True,
                                 "aria-label": t("cmdk_close")},
                      raw('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"'
                          ' stroke-linecap="round"><path d="M6 6l12 12M18 6L6 18"/></svg>'))),
                  *groups))
    cfg = json.dumps({"bindings": [{"keys": b["keys"], "action": b["action"]} for b in BINDINGS]})
    return overlay + h("script", {"id": "km-cfg", "type": "application/json"}, raw(cfg))


KEYMAP_CSS = r"""
.kmov[hidden]{display:none}
.kmov{position:fixed;inset:0;z-index:210;display:flex;align-items:flex-start;justify-content:center}
.kmov-bd{position:absolute;inset:0;background:rgba(0,0,0,.5)}
.km-panel{position:relative;margin-top:9vh;width:min(540px,92vw);max-height:80vh;overflow:auto;background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);box-shadow:0 24px 70px rgba(0,0,0,.45);padding:16px 20px 20px}
.km-head{display:flex;align-items:center;justify-content:space-between;gap:10px}
.km-head h2{margin:0;font-size:var(--t-md)}
.km-grp{margin:16px 0 0}
.km-grp h3{margin:0 0 4px;font-size:var(--t-xs);color:var(--faint);font-weight:600;letter-spacing:.05em;text-transform:uppercase}
.km-row{display:flex;align-items:center;justify-content:space-between;gap:14px;padding:5px 0;font-size:var(--t-body)}
.km-d{flex:1;min-width:0}
.km-keys{display:inline-flex;gap:4px;flex:none}
.km-keys kbd{font-family:var(--mono);background:var(--panel-2);border:1px solid var(--line);border-radius:var(--radius-sm);padding:1px 6px;font-size:var(--t-xs);color:var(--ink);min-width:18px;text-align:center}
/* the j/k row focus on list pages + the project outline — visible, distinct from hover */
.row.kfocus,.olrow.kfocus,.sl-entity.kfocus{background:var(--hover);box-shadow:inset 2px 0 0 var(--accent)}
"""


def keymap_hint() -> str:
    """Legacy footer helper for the shortcuts sheet. The core shell now exposes this
    from the user menu, but extensions can still reuse the row."""
    return h("button", {"type": "button", "class_": "pi-hover", "data-km-open": True},
             h("kbd", {"class_": "sl-kbd"}, "?"), h("span", {}, t("kbd_hint")))


KEYMAP_JS = r"""<script>(function(){
var ov=document.getElementById('kmov'); if(!ov) return;
var CFG={bindings:[]}; try{ CFG=JSON.parse(document.getElementById('km-cfg').textContent)||CFG; }catch(e){}
// platform-correct modifier glyph: ⌘ on macOS, Ctrl elsewhere
if(!/Mac|iPhone|iPad|iPod/.test(navigator.platform||'')){
  ov.querySelectorAll('.km-mod').forEach(function(k){ k.textContent='Ctrl'; }); }
var chords={}, singles={}, starts={};
CFG.bindings.forEach(function(b){
  if(b.keys.indexOf(' ')>=0){ chords[b.keys]=b; starts[b.keys.split(' ')[0]]=1; }
  else singles[b.keys]=b;
});
function openOv(){ ov.hidden=false; var p=ov.querySelector('.km-panel'); if(p) p.focus(); }
function closeOv(){ ov.hidden=true; }
function typing(e){ var el=e.target, tag=(el.tagName||'').toLowerCase();
  return tag==='input'||tag==='textarea'||tag==='select'||el.isContentEditable; }
function rows(){ var c=document.querySelector('[data-keynav]');
  // list rows (a.row), outline rows (.olrow), entity rows (.sl-entity) and file cards/rows
  // (.sl-file, V9) share the walk (C7)
  return c?[].slice.call(c.querySelectorAll('a.row,.olrow,.sl-entity,.sl-file')):[]; }
var ri=-1;
document.addEventListener('spa:load',function(){ ri=-1; });
function focusRow(d){ var rs=rows(); if(!rs.length) return;
  if(ri>=0&&rs[ri]) rs[ri].classList.remove('kfocus');
  ri=(ri<0)?(d>0?0:rs.length-1):Math.min(rs.length-1,Math.max(0,ri+d));
  rs[ri].classList.add('kfocus'); rs[ri].scrollIntoView({block:'nearest'}); }
function run(b){ var a=b.action||{};
  if(a.nav){ location.href=a.nav; return true; }
  switch(a.hook){
    case 'cheatsheet': if(ov.hidden) openOv(); else closeOv(); return true;
    case 'list-next': focusRow(1); return true;
    case 'list-prev': focusRow(-1); return true;
    case 'list-open': var rs=rows(); if(ri>=0&&rs[ri]){
      // Enter opens the focused row: its slide-over (data-drawer) or its href — a funnel-chip
      // row's / file card's main target is the stretched overlay link, so click that when present.
      var el=rs[ri].querySelector('.ol-stretch,.sl-file__open')||rs[ri]; el.click(); return true; } return false;
    case 'list-open-full': var rf=rows(); if(ri>=0&&rf[ri]){
      // 'o' skips the slide-over: navigate straight to the row's full detail page.
      var af=rf[ri].matches&&rf[ri].matches('a[href]')?rf[ri]:rf[ri].querySelector('a[href]');
      if(af&&af.getAttribute('href')){ location.href=af.getAttribute('href'); return true; } } return false;
    case 'sib-prev': case 'sib-next':
      var s=document.getElementById('km-siblings'); if(!s) return false;   // no siblings: skip gracefully
      var u=s.getAttribute(a.hook==='sib-prev'?'data-prev':'data-next');
      if(u){ location.href=u; return true; } return false;
    case 'close': if(!ov.hidden){ closeOv(); return true; } return false;
  }
  return false;   // display-only entries (the palette's mod+k is owned by _palette.js)
}
var pend=null, pt=null;
window.addEventListener('keydown',function(e){
  if(e.key==='Escape'){ pend=null; clearTimeout(pt);
    if(!ov.hidden){ e.preventDefault(); closeOv(); } return; }
  if(typing(e)) return;                              // never steal keys from a field
  if(e.metaKey||e.ctrlKey||e.altKey) return;         // never shadow ⌘K / native shortcuts
  var k=(e.key==='Enter')?'enter':e.key;
  if(pend){ var c=chords[pend+' '+k]; pend=null; clearTimeout(pt);
    if(c&&run(c)) e.preventDefault(); return; }
  if(starts[k]){ pend=k; clearTimeout(pt); pt=setTimeout(function(){ pend=null; },900); return; }
  var b=singles[k]; if(b&&run(b)) e.preventDefault();
});
// the sidebar hint + the palette's cheat-sheet command both open the overlay
document.addEventListener('click',function(e){
  if(e.target.closest&&e.target.closest('[data-km-open],a[href="#shortcuts"]')){ e.preventDefault(); openOv(); return; }
  if(e.target.closest&&e.target.closest('[data-km-close]')){ e.preventDefault(); closeOv(); }
});
})();</script>"""
