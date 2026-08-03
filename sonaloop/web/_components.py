from __future__ import annotations

import html
import json
import re
from collections import Counter, defaultdict
from urllib.parse import quote as _urlquote

from .._icons import icon as _persona_icon, hifi as _persona_hifi, HIFI_ANIM_CSS as _ICON_ANIM_CSS
from .._shell import SHELL_JS  # app-shell behaviour (resize/collapse/user-menu) — vendored from sonaloop-design

from .. import config as _config
from .. import services
from .. import presentation as _pres
from ..storage import Store
from ..web_assets import CSS, HEAD_JS  # noqa: F401  (extracted assets)
from ._i18n import t, _lang
from ._html import h, raw, fragment, register_css, collect_css, _minify_css  # noqa: F401  (component-SSR foundation)
from ._palette import PALETTE_CSS, PALETTE_JS, palette_markup
from ._slide import slide_mode, spa_mode
from ._live import LIVE_CSS, LIVE_JS, live_markup
from ._runs_widget import RUNS_WIDGET_CSS, RUNS_WIDGET_JS, runs_widget_markup
from ._keymap import KEYMAP_CSS, KEYMAP_JS, keymap_markup
from ._ext import (  # noqa: F401  (extension seams; public surface re-exported by web/__init__)
    register_nav_section, register_nav_item, resolve_label, nav_model,
    render_slot, theme_override_css, brand_name, brand_logo, title_brand,
    current_identity,
)


def _esc(value: object) -> str:
    return html.escape(str(value))


def _display_title(text: str, n: int = 90) -> str:
    """A short, header-safe title from possibly-long prose. Some records overload their 'title' with a
    long question-prompt; a title should be a scannable label, so the H1 shows this short form while the
    full text lives in the body (and a real editable title field will supersede it later). Returns the
    first sentence when it fits, else a word-boundary truncation — both with an ellipsis when shortened."""
    s = " ".join((text or "").split())
    if len(s) <= n:
        return s
    first = re.split(r"(?<=[.?!])\s", s, 1)[0]
    if 0 < len(first) <= n:
        return first + ("…" if len(first) < len(s) else "")
    return s[:n].rsplit(" ", 1)[0].rstrip(" ,;:—-") + "…"


def _icon(name: str, animate: bool = False) -> str:
    # Chrome icons come from the shared sonaloop-design library (single source of
    # truth in ../sonaloop-design; geometry authored in icons.data.mjs). Returns
    # "" for unknown names, same as the old inline ICONS lookup. animate=True adds
    # .pi-animate (opt-in hover micro-interaction; needs _ICON_ANIM_CSS, registered below).
    return _persona_icon(name, animate=animate)


def _hifi(name: str, size: int = 44) -> str:
    """A standalone hi-fi display icon (the richer variant) — used as the small 'illustration' in
    empty states. Falls back to the regular icon if no hi-fi variant exists."""
    try:
        return _persona_hifi(name, size) or _persona_icon(name)
    except Exception:
        return _persona_icon(name)


# Icon hover micro-interactions (sonaloop-icons HIFI_ANIM_CSS — covers regular .pi-animate icons too).
register_css(_ICON_ANIM_CSS)


# Sonaloop-mark favicon — the brand loop + nodes (same geometry as the `sonaloop` icon),
# indigo and theme-aware, inlined as a data-URI so the tab icon needs no static route.
_FAVICON_SVG = (
    "<svg xmlns='http://www.w3.org/2000/svg' viewBox='1.5 1 21 21' fill='none'"
    " stroke-width='1.85' stroke-linecap='round' stroke-linejoin='round'>"
    "<style>.s{stroke:#5e6ad2}.f{fill:#5e6ad2}"
    "@media(prefers-color-scheme:dark){.s{stroke:#7c84e8}.f{fill:#7c84e8}}</style>"
    "<path class='s' d='M17 12L17.31 12.62L17.49 13.3L17.51 14.01L17.35 14.69L17 15.29"
    "L16.49 15.77L15.87 16.1L15.19 16.28L14.5 16.33L13.84 16.28L13.25 16.17L12.72 16.07"
    "L12.23 16.01L11.77 16.01L11.28 16.07L10.75 16.17L10.16 16.28L9.5 16.33L8.81 16.28"
    "L8.13 16.1L7.51 15.77L7 15.29L6.65 14.69L6.49 14.01L6.51 13.3L6.69 12.62L7 12"
    "L7.37 11.46L7.76 11L8.12 10.59L8.41 10.2L8.65 9.79L8.83 9.34L9.01 8.83L9.22 8.26"
    "L9.5 7.67L9.88 7.09L10.38 6.59L10.98 6.22L11.65 6.03L12.35 6.03L13.02 6.22L13.62 6.59"
    "L14.12 7.09L14.5 7.67L14.78 8.26L14.99 8.83L15.17 9.34L15.35 9.79L15.59 10.2L15.88 10.59"
    "L16.24 11L16.63 11.46L17 12Z'/>"
    "<circle class='f' cx='12' cy='3.7' r='1.85'/>"
    "<circle class='f' cx='19.19' cy='16.15' r='1.85'/>"
    "<circle class='f' cx='4.81' cy='16.15' r='1.85'/></svg>"
)
_FAVICON_HREF = "data:image/svg+xml," + _urlquote(_FAVICON_SVG, safe="")
_CLOSE_SVG = (
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" '
    'stroke-linecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18"/></svg>'
)


from ._avatar import _avatar, _avatar_src  # noqa: F401,E402  (split out for the LOC bar; re-exported)


def _status_color(s: str) -> str:
    # Status/score words only (done/blocked/läuft, the vote-score buckets) — NEVER Stance data:
    # a stance's color comes from its canonical value via artifacts.stance_meta, not keywords.
    s = (s or "").lower()
    if any(k in s for k in ["positiv", "befürwort", "support", "abgeschloss", "done", "grün", "green", "stark"]):
        return "var(--green)"
    if any(k in s for k in ["skept", "oppose", "nein", "negativ", "rot", "verloren", "abgelehnt", "blocked"]):
        return "var(--red)"
    if any(k in s for k in ["bedingt", "maybe", "neutral", "läuft", "prog", "warn", "teilweise"]):
        return "var(--amber)"
    if any(k in s for k in ["indiff", "abstain", "kaum", "egal"]):
        return "var(--muted)"
    return "var(--accent)"


def _label(text: str, color: str | None = None, variant: str = "soft", dot: bool = True,
           title: str | None = None) -> str:
    d = h("span", {"class_": "sl-dot", "style": f"background:{color or 'var(--muted)'}"}) if dot else None
    attrs = {"class_": f"lbl lbl-{variant}"}
    if title:
        attrs["title"] = title
    return h("span", attrs, d, text)


def _crumbs_html(crumbs: list) -> str:
    parts = []
    for i, (label, href) in enumerate(crumbs):
        last = i == len(crumbs) - 1
        if href and not last:
            parts.append(h("a", {"class_": "sl-breadcrumb__link", "href": href, "title": label}, label))
        else:
            parts.append(h("span", {"class_": "sl-breadcrumb__current", "title": label}, label))
        if not last:
            parts.append(h("span", {"class_": "sl-breadcrumb__sep", "aria-hidden": "true"}))
    return h("nav", {"class_": "sl-breadcrumb", "aria-label": t("breadcrumb_aria")}, parts)



APP_JS = """
<script>
(function(){
  // Sidebar collapse/resize + the bottom user-menu popover are driven by the shared SHELL_JS
  // (sonaloop-design); this file owns the app-specific behaviour below.
  // ---- theme (sun / system / moon) — the switch lives in the sidebar user menu ----
  function curTheme(){ try{return localStorage.getItem('theme')||'system';}catch(e){return 'system';} }
  function markTheme(v){ document.querySelectorAll('[data-theme-set]').forEach(function(b){
    b.classList.toggle('is-active', b.getAttribute('data-theme-set')===v); }); }
  function applyTheme(v){
    if(v==='light'||v==='dark') document.documentElement.dataset.theme=v;
    else delete document.documentElement.dataset.theme;
    try{localStorage.setItem('theme',v);}catch(e){} markTheme(v); }
  document.querySelectorAll('[data-theme-set]').forEach(function(b){
    b.addEventListener('click',function(){ applyTheme(b.getAttribute('data-theme-set')); }); });
  markTheme(curTheme());
  // (the old inline "g then o/p" jump nav moved to the keymap registry — web/_keymap.py)
  var sc=document.querySelector('section'); var tocLinks=[].slice.call(document.querySelectorAll('.toc a'));
  if(sc && tocLinks.length){
    var map={}; tocLinks.forEach(function(a){ map[a.getAttribute('href').slice(1)]=a; });
    var obs=new IntersectionObserver(function(es){ es.forEach(function(en){ if(en.isIntersecting){
      tocLinks.forEach(function(l){l.classList.remove('active');}); if(map[en.target.id]) map[en.target.id].classList.add('active'); } }); },
      {root:sc,rootMargin:'0px 0px -78% 0px',threshold:0});
    document.querySelectorAll('.doc-main [id]').forEach(function(s){ obs.observe(s); });
  }
  // ---- favorites / stars (client-side, localStorage) ----
  var SK=__FAV_STORAGE_KEY__, ICN=__FAV_ICONS__;
  function readStars(){ try{return JSON.parse(localStorage.getItem(SK)||'{}');}catch(e){return {};} }
  function writeStars(m){ try{localStorage.setItem(SK,JSON.stringify(m));}catch(e){} }
  function renderStars(){
    var m=readStars();
    document.querySelectorAll('[data-star]').forEach(function(b){ b.classList.toggle('on', !!m[b.getAttribute('data-star')]); });
    var favs=document.getElementById('favs'); if(!favs) return;
    var favsec=document.getElementById('favsec');
    var keys=Object.keys(m);
    favs.innerHTML='';
    if(!keys.length){ if(favsec) favsec.hidden=true; return; }   // hide the whole section when nothing is starred
    if(favsec) favsec.hidden=false;
    keys.forEach(function(k){ var f=m[k];
      var row=document.createElement('div'); row.className='favrow';
      var a=document.createElement('a'); a.href=f.href||'#'; a.title=f.label||'';
      var ic=document.createElement('span'); ic.className='favic'; ic.innerHTML=ICN[f.type]||''; a.appendChild(ic);
      a.appendChild(document.createTextNode(' '+(f.label||k)));
      var x=document.createElement('button'); x.className='favx'; x.setAttribute('data-unstar',k); x.setAttribute('aria-label',__UNSTAR__); x.title=__UNSTAR__; x.textContent='\\u00d7';
      row.appendChild(a); row.appendChild(x); favs.appendChild(row); });
  }
  document.addEventListener('click',function(e){
    var ux=e.target.closest && e.target.closest('[data-unstar]');
    if(ux){ e.preventDefault(); e.stopPropagation(); var mm=readStars(); delete mm[ux.getAttribute('data-unstar')]; writeStars(mm); renderStars(); return; }
    var b=e.target.closest && e.target.closest('[data-star]'); if(!b) return;
    e.preventDefault(); e.stopPropagation();
    var m=readStars(), k=b.getAttribute('data-star');
    if(m[k]) delete m[k]; else m[k]={href:b.getAttribute('data-href'),label:b.getAttribute('data-label'),type:b.getAttribute('data-type')};
    writeStars(m); renderStars();
  });
  renderStars();
  // After an SPA content swap (sidebar persists), re-apply star states to the new page's buttons.
  document.addEventListener('spa:load', renderStars);
  // Long hero titles/subs clamp to 3 lines; mark the truncated ones clickable to expand inline.
  function initClamp(){ document.querySelectorAll('.sl-page-header__title,.syn-head h1,.sl-page-header__sub').forEach(function(el){
    if(!el.classList.contains('expanded')) el.classList.toggle('is-clamped', el.scrollHeight-el.clientHeight>2); }); }
  document.addEventListener('click',function(e){ var t=e.target.closest&&e.target.closest('.is-clamped'); if(t) t.classList.toggle('expanded'); });
  initClamp(); document.addEventListener('spa:load',initClamp);
  // Outline relation hover: draw real project-graph input/output edges in the quiet left rail.
  function initOutlineRelations(){
    document.querySelectorAll('.outline[data-relgraph]').forEach(function(outline){
      if(outline.dataset.relInit) return; outline.dataset.relInit='1';
      var svg=outline.querySelector('.ol-rel-svg'); if(!svg) return;
      function rows(){ return [].slice.call(outline.querySelectorAll('[data-oid]')); }
      function byId(){ var m={}; rows().forEach(function(r){ m[r.dataset.oid]=r; }); return m; }
      function clear(){ svg.querySelectorAll('path.ol-rel').forEach(function(p){p.remove();});
        outline.classList.remove('is-relating'); rows().forEach(function(r){
          r.classList.remove('ol-rel-source','ol-rel-in-row','ol-rel-out-row');
        }); }
      function anchor(row){
        var a=outline.getBoundingClientRect(), ico=row.querySelector('.ol-ico')||row,
            b=ico.getBoundingClientRect();
        return {
          x: Math.max(2,b.left-a.left-12),
          y: b.top-a.top+b.height/2+outline.scrollTop
        };
      }
      function path(from,to,cls){
        var p=document.createElementNS('http://www.w3.org/2000/svg','path');
        var bend=Math.max(22,Math.min(72,Math.abs(to.y-from.y)*.28));
        var c1=from.x-bend, c2=to.x-bend;
        p.setAttribute('class','ol-rel '+cls);
        p.setAttribute('d','M '+from.x+' '+from.y+' C '+c1+' '+from.y+', '+c2+' '+to.y+', '+to.x+' '+to.y);
        svg.appendChild(p);
      }
      function show(row){
        clear();
        var map=byId(), idsIn=(row.dataset.relIn||'').split(/\\s+/).filter(Boolean),
            idsOut=(row.dataset.relOut||'').split(/\\s+/).filter(Boolean);
        if(!idsIn.length&&!idsOut.length) return;
        outline.classList.add('is-relating'); row.classList.add('ol-rel-source');
        var a=anchor(row);
        idsIn.forEach(function(id){ var r=map[id]; if(r){ r.classList.add('ol-rel-in-row'); path(anchor(r),a,'ol-rel-in'); }});
        idsOut.forEach(function(id){ var r=map[id]; if(r){ r.classList.add('ol-rel-out-row'); path(a,anchor(r),'ol-rel-out'); }});
      }
      outline.addEventListener('mouseover',function(e){ var r=e.target.closest&&e.target.closest('[data-oid]');
        if(r&&outline.contains(r)) show(r); });
      outline.addEventListener('focusin',function(e){ var r=e.target.closest&&e.target.closest('[data-oid]');
        if(r&&outline.contains(r)) show(r); });
      outline.addEventListener('mouseleave',clear);
      outline.addEventListener('focusout',function(e){ if(!outline.contains(e.relatedTarget)) clear(); });
    });
  }
  initOutlineRelations(); document.addEventListener('spa:load',initOutlineRelations);
})();
</script>
"""


from ._drawer import DRAWER_CSS, DRAWER_JS, SPA_JS, drawer_markup  # noqa: F401  (injected by _layout)


from . import _nav_seed  # noqa: F401,E402  (seeds the core sidebar via the public nav registry)


def _nav(active: str, store: Store) -> str:
    # .pi-hover makes the row the animation trigger — the icon plays its micro-interaction on row hover.
    render = lambda items: fragment(*(
        h("a", {"href": it["href"], "class_": "pi-hover is-active" if it["key"] == active else "pi-hover"},
          raw(_icon(it["icon"], animate=True)), h("span", {}, resolve_label(it["label"])))
        for it in items))
    blocks: list = []
    for sec, items in nav_model():
        head = resolve_label(sec["label"])
        if head:
            blocks.append(h("div", {"class_": "sl-navhead"}, head))
        blocks.append(h("nav", {"class_": "sl-nav"}, render(items)))
    # Favorites are stored client-side (localStorage); the section is filled AND shown/hidden by JS
    # (renderStars) — it only appears once something is starred, so an empty sidebar stays clean.
    blocks.append(h("div", {"id": "favsec", "hidden": True},
                    h("div", {"class_": "sl-navhead"}, t("favorites")),
                    h("div", {"class_": "sb-quick", "id": "favs"})))
    return fragment(*blocks)


_USER_MENU_ID_CSS = register_css(r"""
.sl-um-pop{left:8px;right:8px;width:auto;padding:6px;border-radius:var(--radius);
  box-shadow:0 18px 52px rgba(0,0,0,.18),0 1px 2px rgba(0,0,0,.06)}
.sl-um-group{padding:4px 0;border-top:1px solid var(--line)}
.sl-um-group:first-child{border-top:0;padding-top:0}
.sl-um-group:last-child{padding-bottom:0}
.sl-um-row{display:flex;align-items:center;gap:10px;width:100%;min-height:36px;padding:7px 8px;border:0;
  border-radius:var(--radius-sm);background:transparent;color:var(--ink);font:inherit;font-size:var(--t-body);
  font-weight:500;text-align:left;text-decoration:none;cursor:pointer}
.sl-um-row:hover{background:var(--hover)}
.sl-um-row svg{width:17px;height:17px;color:var(--faint);flex:none}
.sl-um-row span{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.sl-um-row--danger{color:var(--ink)}
.sl-um-account{display:grid;grid-template-columns:28px minmax(0,1fr);gap:10px;align-items:center;padding:8px}
.sl-um-ava{display:inline-flex;align-items:center;justify-content:center;width:28px;height:28px;
  border-radius:var(--radius-full);flex:none;overflow:hidden}
.sl-um-ava img{width:100%;height:100%;object-fit:cover;display:block}
.sl-um-ava--initials{background:var(--accent);color:var(--accent-ink);font-size:11px;
  font-weight:650;letter-spacing:.02em}
.sl-um-account-main{min-width:0;display:flex;flex-direction:column;gap:1px}
.sl-um-account-main strong{font-size:var(--t-md);font-weight:600;color:var(--ink);line-height:1.25;
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.sl-um-account-main span{font-size:var(--t-sm);color:var(--muted);line-height:1.25;overflow:hidden;
  text-overflow:ellipsis;white-space:nowrap}
.sl-um-trigger-text{display:flex;flex-direction:column;gap:1px;flex:1;min-width:0;text-align:left}
.sl-um-trigger-text .sl-um-name{display:block;flex:none}
.sl-um-trigger-sub{font-size:var(--t-xs);font-weight:500;color:var(--muted);line-height:1.1;overflow:hidden;
  text-overflow:ellipsis;white-space:nowrap}
.sl-um-control{display:flex;align-items:center;justify-content:space-between;gap:10px;min-height:40px;padding:6px 8px;
  border-radius:var(--radius-sm)}
.sl-um-control:hover{background:var(--hover)}
.sl-um-control-label{display:inline-flex;align-items:center;gap:10px;min-width:0;color:var(--ink);font-size:var(--t-body);
  font-weight:500}
.sl-um-control-label svg{width:17px;height:17px;color:var(--faint);flex:none}
.sl-um-control-label span{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.sl-um-switch{display:inline-flex;align-items:center;gap:2px;padding:2px;border:1px solid var(--line);
  border-radius:var(--radius-sm);background:var(--panel-2);flex:none}
.sl-um-choice{display:inline-flex;align-items:center;justify-content:center;width:28px;height:28px;padding:0;
  border:0;border-radius:5px;background:transparent;color:var(--muted);font:inherit;font-size:var(--t-sm);
  font-weight:600;line-height:1;cursor:pointer;text-decoration:none}
.sl-um-choice svg{width:15px;height:15px}
.sl-um-choice:hover{color:var(--ink)}
.sl-um-choice.is-active{background:var(--panel);color:var(--ink);box-shadow:var(--shadow-sm)}
.sl-um-choice.is-active svg{color:var(--accent)}
""")


def _known_identity() -> dict | None:
    ident = current_identity()
    if not ident:
        return None
    name = str(ident.get("name") or "").strip()
    email = str(ident.get("email") or "").strip()
    sub = str(ident.get("sub") or "").strip()
    local_flags = ident.get("local") or ident.get("is_local") or ident.get("anonymous")
    placeholder = (name.lower() in {"local user", "localuser", "anonymous", "guest"}
                   or sub.lower() in {"local", "local-user", "local_user"})
    if local_flags or (placeholder and not email):
        return None
    if not (name or email or sub):
        return None
    return ident


def _initials(text: str) -> str:
    parts = re.findall(r"[A-Za-z0-9À-ÖØ-öø-ÿ]+", text or "")
    return ("".join(p[0] for p in parts[:2]) or "?").upper()


def _identity_avatar_url(ident: dict | None) -> str | None:
    if not ident:
        return None
    for key in ("picture", "avatar_url", "avatar", "image", "photo_url", "photo"):
        raw_url = ident.get(key)
        if isinstance(raw_url, dict):
            raw_url = raw_url.get("url") or raw_url.get("src")
        url = str(raw_url or "").strip()
        if url.startswith(("https://", "/data/", "/assets/", "/web-assets/")):
            return url
    return None


def _identity_avatar(ident: dict | None, label: str) -> str:
    src = _identity_avatar_url(ident)
    if src:
        return h("span", {"class_": "sl-um-ava"},
                 h("img", {"src": src, "alt": "", "loading": "lazy",
                            "decoding": "async", "referrerpolicy": "no-referrer"}))
    return h("span", {"class_": "sl-um-ava sl-um-ava--initials"}, _initials(label))


def _user_menu_row(label: str, icon: str, *, href: str | None = None,
                   attrs: dict | None = None) -> str:
    base = {"class_": "sl-um-row pi-hover", **(attrs or {})}
    kids = (raw(_icon(icon, animate=True)), h("span", {}, label))
    if href:
        return h("a", {**base, "href": href}, *kids)
    return h("button", {**base, "type": "button"}, *kids)


def _user_menu_control(label: str, icon: str, control: str) -> str:
    return h("div", {"class_": "sl-um-control pi-hover"},
             h("div", {"class_": "sl-um-control-label"}, raw(_icon(icon, animate=True)), h("span", {}, label)),
             raw(control))


def docs_footer_entry(active: str) -> str:
    """Compatibility footer entry helper. The core shell now renders Documentation from the
    user menu so the sidebar footer stays focused."""
    return h("a", {"href": "/documentation",
                   "class_": "pi-hover is-active" if active == "docs" else "pi-hover"},
             raw(_icon("overview", animate=True)), h("span", {}, t("documentation")))


def activity_footer_entry(active: str) -> str:
    """Compatibility footer entry helper. The core shell now renders Activity from the user menu."""
    return h("a", {"href": "/activity",
                   "class_": "pi-hover is-active" if active == "activity" else "pi-hover"},
             raw(_icon("clock", animate=True)), h("span", {}, t("activity_h")))


def _user_menu() -> str:
    """User/settings menu pinned to the bottom of the sidebar.

    Real identities get an account chip; local placeholders from auth-less installs are
    intentionally treated as anonymous so "Local User" never appears as a fake account.
    """
    cur = _lang()
    ident = _known_identity()
    themes = [("light", "sun", t("theme_light")), ("system", "monitor", t("theme_system")), ("dark", "moon", t("theme_dark"))]
    theme_opts = [h("button", {"type": "button", "class_": "sl-um-choice pi-hover", "data-theme-set": val,
                                "title": label, "aria-label": label}, raw(_icon(icon, animate=True)))
                  for val, icon, label in themes]
    langs = [("de", "Deutsch", "DE"), ("en", "English", "EN")]
    lang_opts = [h("a", {"class_": f'sl-um-choice{" is-active" if code == cur else ""}', "href": f"?lang={code}",
                         "title": full, "aria-label": full}, h("span", {}, short)) for code, full, short in langs]
    account_sec = None
    if ident:
        who = ident.get("name") or ident.get("email") or "?"
        account_bits = [h("strong", {}, who)]
        if ident.get("name") and ident.get("email"):
            account_bits.append(h("span", {}, ident["email"]))
        if ident.get("plan") or ident.get("tier"):
            account_bits.append(h("span", {}, ident.get("plan") or ident.get("tier")))
        account_sec = h("div", {"class_": "sl-um-account"},
                        _identity_avatar(ident, who),
                        h("div", {"class_": "sl-um-account-main"}, *account_bits))
    link_sec = h("div", {"class_": "sl-um-group"},
                 _user_menu_row(t("activity_h"), "activity", href="/activity"),
                 _user_menu_row(t("documentation"), "overview", href="/documentation"),
                 _user_menu_row(t("feedback_h"), "chat", attrs={"data-fb-open": True}),
                 _user_menu_row(t("tour_take"), "compass", attrs={"data-tour-start": True}),
                 _user_menu_row(t("kbd_cheatsheet_h"), "command", attrs={"data-km-open": True}))
    controls_sec = h("div", {"class_": "sl-um-group"},
                     _user_menu_control(t("theme"), "sun",
                                        h("div", {"class_": "sl-um-switch"}, theme_opts)),
                     _user_menu_control(t("language"), "globe",
                                        h("div", {"class_": "sl-um-switch"}, lang_opts)))
    logout_sec = (h("div", {"class_": "sl-um-group"},
                    _user_menu_row(t("logout"), "external", href=ident["logout_href"],
                                   attrs={"class_": "sl-um-row sl-um-row--danger pi-hover"}))
                  if ident and ident.get("logout_href") else None)
    if ident:
        who = ident.get("name") or ident.get("email") or "?"
        plan = ident.get("plan") or ident.get("tier")
        trigger_parts = (_identity_avatar(ident, who),
                         h("span", {"class_": "sl-um-trigger-text"},
                           h("span", {"class_": "sl-um-name"}, who),
                           h("span", {"class_": "sl-um-trigger-sub"}, plan) if plan else None),
                         h("span", {"class_": "sl-um-caret"}, raw(_icon("chevron", animate=True))))
    else:
        trigger_parts = (h("span", {"class_": "sl-um-ava"}, raw(_icon("settings", animate=True))),
                         h("span", {"class_": "sl-um-name"}, t("settings")),
                         h("span", {"class_": "sl-um-caret"}, raw(_icon("chevron", animate=True))))
    return h("div", {"class_": "sl-usermenu"},
             h("div", {"class_": "sl-um-pop", "hidden": True},
               account_sec,
               link_sec,
               controls_sec,
               logout_sec),
             h("button", {"type": "button", "class_": "sl-um-trigger pi-hover",
                          "aria-haspopup": "true", "aria-expanded": "false"},
               *trigger_parts))


def _sidebar_footer(store: Store) -> str:
    footer = render_slot("sidebar_footer", store)
    if not footer:
        return ""
    return f'<nav class="sl-nav sl-sb-foot">{footer}</nav>'


def _star(kind: str, ident: str, label: str, href: str) -> str:
    # W3 (one control vocabulary): the favourite star is a ghost icon button like every
    # other header icon action; .starbtn only adds the on-state colours.
    return h("button", {"class_": "sl-iconbtn sl-iconbtn--ghost starbtn", "data-star": f"{kind}:{ident}", "data-href": href,
                        "data-label": label, "data-type": kind, "title": t("favorite"),
                        "aria-label": t("mark_as_favorite")}, raw(_icon("star")))


_FAV_ICONS_JSON = json.dumps({
    "persona": _icon("personas"), "council": _icon("councils"), "synthesis": _icon("syntheses"),
    "project": _icon("projects"), "prototype": _icon("prototype"), "concept": _icon("bulb"),
    "note": _icon("square"), "section": _icon("squareGrid"), "session": _icon("activity"),
})


def _favorites_storage_key() -> str:
    """Return the browser-local favorites bucket for the current data boundary.

    Open-core/SQLite keeps the historical ``pc-stars`` key unchanged.  In shared
    Postgres, the shell is rendered inside an authenticated, request-bound tenant
    scope; using the active workspace id keeps an owner's personal favorites out of
    customer-preview workspaces.  Never fall back to the legacy key in row-tenancy:
    a missing or malformed scope is a boundary error and must fail closed.
    """
    if not _config.postgres_row_tenancy_enabled():
        return "pc-stars"

    scope = _config.request_tenant_scope()
    if scope is None:
        raise RuntimeError("row-tenanted favorites require a request tenant scope")
    accessible_ids, active_id = scope
    active = str(active_id or "")
    if active not in {str(workspace_id) for workspace_id in accessible_ids}:
        raise PermissionError("active favorites workspace is outside the request tenant scope")
    if not re.fullmatch(r"ws_[A-Za-z0-9][A-Za-z0-9_.-]{0,126}", active):
        raise ValueError(f"unsafe active workspace id for favorites: {active!r}")
    return f"pc-stars:{active}"


# Customer brand logo (customer-theme contract): height-capped so any aspect ratio sits
# in the lockup row; the wordmark treatment stays untouched when no logo is set.
_BRAND_LOGO_CSS = register_css(
    ".sl-logo__img{display:block;height:20px;max-width:150px;object-fit:contain}")


def _brand_logo_img(alt: str) -> str:
    """The customer-logo <img> for the sidebar lockup, or "" when none is set. A data:
    URI is emitted as-is. Local file logos use the single-tenant /data mount. Shared
    row-tenancy has no raw runtime-file route, so its workspace branding must use a
    data URI (or fall back to the wordmark)."""
    logo = brand_logo()
    if not logo:
        return ""
    if logo.startswith("data:"):
        src = logo
    else:
        from pathlib import Path
        from .. import config as _config
        try:
            relative = Path(logo).resolve().relative_to(_config.partition_dir().resolve())
        except ValueError:
            return ""
        if _config.postgres_row_tenancy_enabled():
            return ""
        src = "/data/" + relative.as_posix()
    return f'<img class="sl-logo__img" src="{_esc(src)}" alt="{_esc(alt)}">'


def _layout(title: str, body: str, store: Store, crumbs: list | None = None,
            active: str = "", actions: str = "") -> str:
    # The `?slide=1` fragment variant (§8.1, web/_slide.py): the SAME page, content only — the
    # slide-over fetches this while pushState makes the address the canonical URL. The host
    # document already carries the full CSS/JS environment; the drawer re-executes embedded
    # scripts. The page's header ACTIONS (the V10 "…" overflow + its dialogs, the star) ride
    # along hidden — web/_drawer's DRAWER_JS hoists [data-slide-actions] into the panel header
    # (next to expand/close), so edit/delete stay reachable from the peek too.
    if slide_mode():
        acts = (f'<span class="sl-tb-actions" data-slide-actions hidden>{actions}</span>'
                if actions else "")
        return f'<div class="sl-slide">{acts}{body}</div>'
    # SPA fragment: the router fetches with `X-Requested-With: spa` and extracts `#main`
    # via DOMParser. Return only the main content — skip the 465 KB shell (CSS/JS/sidebar).
    if spa_mode():
        return (
            f'<!doctype html><html><head><title>{_esc(title)}</title></head>'
            f'<body><div class="sl-main" id="main">'
            f'<header class="sl-topbar"><button class="sl-iconbtn sl-iconbtn--ghost" id="sbt" '
            f'data-sidebar-toggle title="{t("sidebar")} ([)" aria-label="{t("sidebar")}" '
            f'aria-expanded="true">{_icon("panel")}</button>'
            f'{_crumbs_html(crumbs or [(title, None)])}<span class="sl-spacer"></span>'
            f'{runs_widget_markup(store)}<span class="sl-tb-actions">{actions}</span></header>'
            f'<section>{body}</section>'
            f'</div></body></html>'
        )
    crumbs = crumbs or [(title, None)]
    # Inject per-request translations into the static JS (client renders need them
    # too — same __PLACEHOLDER__ -> t() pattern used for the voices chart).
    app_js = (APP_JS.replace("__FAV_STORAGE_KEY__", json.dumps(_favorites_storage_key()))
              .replace("__FAV_ICONS__", _FAV_ICONS_JSON)
              .replace("__UNSTAR__", json.dumps(t("unstar"))))
    # Brand lockup: the wordmark sets the "loop" of "Sona·loop" in Sona Pixel (the shared
    # .sl-logo treatment). For a product brand ("Sonaloop Cloud" / "Sonaloop Research") the
    # trailing word becomes a muted .sl-logo__sub label beside the wordmark — matching the
    # product apps (data/tracker/design); the bare core ("Sonaloop") renders just the wordmark.
    # A customer logo (theming.validate_customer_theme brand.logo, set via set_brand)
    # replaces mark + wordmark entirely — the customer's identity, not a co-brand.
    _bn = brand_name()
    _lockup = _brand_logo_img(_bn)
    if not _lockup:
        _i = _bn.lower().find("loop")
        if _i != -1:
            _word = f'{_esc(_bn[:_i])}<span class="sl-logo__loop">{_esc(_bn[_i:_i+4])}</span>'
            _sub = _bn[_i + 4:].strip()
        else:
            _word = _esc(_bn)
            _sub = ""
        _brand_word = f'<span class="sl-logo__word">{_word}</span>'
        if _sub:
            _brand_word += f'<span class="sl-logo__sub">{_esc(_sub)}</span>'
        _lockup = f'<span class="sl-logo__mark">{_icon("sonaloop")}</span>{_brand_word}'
    return f"""<!doctype html>
<html lang="{_lang()}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_esc(title_brand() + (" · " + title if title and title.strip() else ""))}</title>
<link rel="icon" type="image/svg+xml" href="{_FAVICON_HREF}">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600;700&family=Geist+Mono:wght@400;500&display=swap" rel="stylesheet">
{HEAD_JS}<style>{_minify_css(CSS)}{_minify_css(PALETTE_CSS)}{_minify_css(LIVE_CSS)}{_minify_css(RUNS_WIDGET_CSS)}{_minify_css(KEYMAP_CSS)}{collect_css()}</style>{theme_override_css()}{render_slot("head_extra", store)}</head>
<body><div class="sl-app-shell" id="app">
  <aside class="sl-sidebar">
    <div class="sl-brand"><a class="sl-logo" href="/">{_lockup}</a><button class="sl-sidebar-close sl-iconbtn sl-iconbtn--ghost" type="button" data-sidebar-close aria-label="{t("cmdk_close")}" title="{t("cmdk_close")}">{_CLOSE_SVG}</button></div>
    <div class="sl-sb-search"><button type="button" class="sl-cmdk-trigger" data-cmdk-open aria-label="{t("search")}">{_icon("search")}<span>{t("search")}</span><kbd class="sl-kbd">⌘K</kbd></button></div>
    <div class="sl-sb-scroll">{_nav(active, store)}{render_slot("sidebar_extra", store)}</div>
    {_sidebar_footer(store)}
    {_user_menu()}
  </aside>
  <button class="sl-sidebar-backdrop" type="button" data-sidebar-close aria-label="{t("cmdk_close")}"></button>
  <div class="sl-resize" id="rz" role="separator" aria-orientation="vertical" aria-label="{t("sidebar")}"></div>
  <div class="sl-main" id="main">
    <header class="sl-topbar"><button class="sl-iconbtn sl-iconbtn--ghost" id="sbt" data-sidebar-toggle title="{t("sidebar")} ([)" aria-label="{t("sidebar")}" aria-expanded="true">{_icon("panel")}</button>
      {_crumbs_html(crumbs)}<span class="sl-spacer"></span>{runs_widget_markup(store)}<span class="sl-tb-actions">{actions}</span></header>
    <section>{body}</section>
  </div>
</div>{drawer_markup(t("cmdk_close"), t("drawer_expand"))}{palette_markup()}{PALETTE_JS}{keymap_markup()}{KEYMAP_JS}{live_markup()}{LIVE_JS}{RUNS_WIDGET_JS}{SHELL_JS}{app_js}{SPA_JS}{DRAWER_JS}{render_slot("body_end", store)}</body></html>"""


# First component on the new builder (spec C3): markup via h() (auto-escaped), CSS co-located here.
_STUDY_LEAD_CSS = register_css(
    ".es{margin:24px 0 4px}"
    # ONE eyebrow voice app-wide (§11 T3, = the design-system .sl-eyebrow recipe): Sona Mono,
    # t-xs, weight 500, .14em caps tracking — colour stays contextual (accent where it labels
    # the page's answer/question, muted elsewhere).
    ".eyebrow{font-family:var(--mono);font-size:var(--t-xs);text-transform:uppercase;letter-spacing:.14em;color:var(--accent);font-weight:500;margin:0 0 12px}"
    ".qa-q{font-size:var(--t-lg);line-height:1.35;font-weight:600;color:var(--ink);margin:2px 0 16px;max-width:var(--measure-prose)}"
    ".qa-q::before{content:attr(data-label);display:block;font-family:var(--mono);font-size:var(--t-xs);font-weight:500;text-transform:uppercase;letter-spacing:.14em;color:var(--muted);margin-bottom:4px}")


# Long titles/subs (e.g. a council's full question-prompt) are clamped to a few lines + ellipsis — the
# header stays scannable (Linear-style) and the full text is available on hover (title=) and in the body.
# The hero uses the shared design-system .sl-page-header* (component chrome + spacing). Only the
# app-specific bits live here: the title's accent leading icon, and the 3-line clamp + click-to-expand
# affordance (set by initClamp() in SHELL_JS only when the text actually overflows).
_HERO_CSS = register_css(
    ".sl-page-header__title{font-size:var(--t-xl);font-weight:650;letter-spacing:-.02em;line-height:1.2;"
    "display:-webkit-box;-webkit-box-orient:vertical;-webkit-line-clamp:3;overflow:hidden}"
    ".sl-page-header__title svg{width:21px;height:21px;color:var(--accent);margin-right:8px;vertical-align:-2px}"
    ".sl-page-header__sub{max-width:74ch;"
    "display:-webkit-box;-webkit-box-orient:vertical;-webkit-line-clamp:3;overflow:hidden}"
    ".is-clamped{cursor:pointer}"                                  # only set by JS when actually truncated
    "h1.expanded,.sl-page-header__title.expanded,.sl-page-header__sub.expanded{"
    "-webkit-line-clamp:unset;display:block;overflow:visible}")


def _hero(title, *, sub=None, icon: str | None = None, hid: str | None = None, top=None) -> str:
    """The page hero used by every detail page — the shared .sl-page-header: optional `top` slot (a pill,
    trusted HTML), a title (text → escaped, or Safe HTML kept) with an optional leading `icon`, and an
    optional `sub` (text → escaped, or Safe HTML like a chip line). Title/sub are line-clamped (see
    _HERO_CSS); plain text gets a full-text title= tooltip."""
    h1_attrs = {"class_": "sl-page-header__title"}
    if type(title) is str:
        h1_attrs["title"] = title                                  # full text on hover (clamped display)
    sub_attrs = {"class_": "sl-page-header__sub"}
    if type(sub) is str:
        sub_attrs["title"] = sub
    return h("div", {"class_": "sl-page-header", "id": hid},
             h("div", {"class_": "sl-page-header__main"},
               h("div", {"class_": "sl-page-header__top"}, raw(top)) if top else None,
               h("h1", h1_attrs, raw(_icon(icon)) if icon else None, title),
               h("p", sub_attrs, sub) if sub else None))


def _study_lead(answer_html: str, answer_label: str, *, question: str = "",
                qlabel: str = "", qid: str = "exec") -> str:
    """Unified Question → Answer/Finding lead — the SAME typographic block on every study page
    (council 'finding', synthesis 'answer'). The qa-q question is shown only when given (synthesis,
    whose hero title is the thesis); council omits it because its hero title IS the question."""
    return h("div", {"class_": "es", "id": qid},
             h("p", {"class_": "qa-q", "data_label": qlabel}, question) if question else None,
             h("div", {"class_": "eyebrow"}, answer_label),
             h("div", {"class_": "sl-prose"}, raw(answer_html)))


def _framed_rows(rows: list) -> str:
    """Stack consecutive `.sl-entity` rows under ONE `.sl-entity-list` hairline frame (the
    design-system idiom for entity lists — flush rows are only legal INSIDE the frame, the
    spacing harness enforces it). Non-entity rows (`.group` headers, card rows like `.hyp`
    or `.sl-file--row`) break the frame and ride the `.rows` container's gap rhythm."""
    out: list[str] = []
    frame: list[str] = []
    def _flush() -> None:
        if frame:
            out.append(f'<div class="sl-entity-list">{"".join(frame)}</div>')
            frame.clear()
    for r in rows:
        html = str(r)
        if "sl-entity" in html[:120] and "sl-entity-list" not in html[:120]:
            frame.append(html)
        else:
            _flush()
            out.append(html)
    _flush()
    return "".join(out)


def _list_page(store: Store, *, title: str, lead: str, rows: list,
               empty_icon: str, empty_msg: str, active: str,
               pre: str = "", count: int | None = None,
               actions: str = "", empty_action: tuple | None = None,
               empty_teach: str = "", after: str = "") -> str:
    """One index-page shell — title + count + lead + rows (or an empty state). Every list page
    (projects, personas, councils, syntheses, prototypes, concepts) renders identically through this.
    `pre` is optional HTML between the lead and the rows (e.g. the hypotheses hit-rate strip);
    `count` overrides the h1 count when `rows` interleaves `.group` headers with the records
    (and when `rows` is one PAGE of a larger filtered set — pass the set's total).
    `actions` is topbar HTML (e.g. the New-project button); `empty_action` = (label, href, icon)
    adds the same CTA inside the empty state; `empty_teach` upgrades the empty card to the
    design-system FIRST-USE anatomy (audit F1 / C8 "teach"): the message becomes the title and
    the teach line — the next action that produces this kind — becomes the body; `after` is
    optional HTML below the rows (e.g. the pager controls)."""
    if rows:
        rows_html = raw(_framed_rows(rows))
    else:
        cta = (h("a", {"class_": "sl-btn", "href": empty_action[1]},
                 raw(_icon(empty_action[2])), " ", empty_action[0]) if empty_action else None)
        rows_html = h("div", {"class_": "sl-empty"},
                      h("div", {"class_": "sl-empty__icon"}, raw(_hifi(empty_icon, 44))),
                      h("h2", {"class_": "sl-empty__title"}, empty_msg) if empty_teach else None,
                      h("p", {"class_": "sl-empty__body"}, empty_teach or empty_msg),
                      h("div", {"class_": "sl-empty__actions"}, cta) if cta else None)
    cnt = h("span", {"class_": "h1cnt"}, str(count if count is not None else len(rows))) if rows else ""
    body = h("div", {"class_": "page"}, h("h1", {"class_": "h1"}, title, cnt),
             h("p", {"class_": "lead"}, lead), raw(pre) if pre else None,
             # data-keynav: the keymap's j/k row-focus hook (web/_keymap.py) targets this container
             h("div", {"class_": "rows", "data-keynav": True}, rows_html),
             raw(after) if after else None)
    return _layout(title, body, store, crumbs=[(title, None)], active=active, actions=actions)


def _empty_state(title: str, message: str, *, icon: str = "overview", action: tuple | None = None) -> str:
    """A calm, centered empty/not-found state (Linear-style): a hi-fi product glyph as the small
    'illustration', a title, one explanatory line, and a single CTA. `action` = (label, href, icon)."""
    label, href, ic = action or (t("projects"), "/jobs", "back")
    return h("div", {"class_": "page"}, h("div", {"class_": "sl-empty"},
             h("div", {"class_": "sl-empty__icon"}, raw(_hifi(icon, 44))),
             h("h2", {"class_": "sl-empty__title"}, title),
             h("p", {"class_": "sl-empty__body"}, message),
             h("a", {"class_": "sl-btn", "href": href}, raw(_icon(ic)), " ", label)))


# Edge-type → color is DATA (suggestions/edge_types.json via presentation.edge_colors); no edge color
# hardcoded here (Layer 2). The spine type (GAP-6) "informs" lives in that file like the rest.
_EDGE_COLORS = _pres.edge_colors()
_THEME_PALETTE = ["#6b7cff", "#34a853", "#f29900", "#a142f4", "#ea4335", "#00897b", "#5f6368", "#d81b60"]


def _theme_color(theme: str, vocab: list[str]) -> str:
    try:
        return _THEME_PALETTE[vocab.index(theme) % len(_THEME_PALETTE)]
    except ValueError:
        return "#9aa0a6"


def _proto_tags(pr: dict) -> set:
    """An artifact's open tags, mirroring methodology._artifact_tags (type tag + discriminators).
    Read from the record's data; no artifact value assumed."""
    tags = {pr.get("type") or _pres.DEFAULT_ARTIFACT_TYPE}
    if pr.get("fidelity"):
        tags.add(pr["fidelity"])
    for tg in (pr.get("tags") or []):
        tags.add(tg)
    return tags


def _artifact_present(pr: dict) -> dict:
    """Resolve an artifact's display fields purely from data: the type tag's presentation hint +
    the first discriminator tag's short label. Generic fallbacks when no hint exists."""
    type_tag = pr.get("type") or _pres.DEFAULT_ARTIFACT_TYPE
    tp = _pres.present(type_tag, pr.get("presentation"))
    disc = ""
    for tg in ([pr.get("fidelity")] + list(pr.get("tags") or [])):
        if tg:
            disc = _pres.present(tg)["short"]
            break
    return {"label": tp["label"], "color": tp["color"], "glyph": tp["glyph"], "icon": tp["icon"], "disc": disc}


def _pills(items: list[str]) -> str:
    return fragment(*(h("span", {"class_": "pill"}, item) for item in items))


def _md_inline(s: str) -> str:
    """Inline Markdown → HTML (auto-escaped): `code`, [text](/url), **bold**, ~~strike~~, _italic_,
    *italic*. Code spans and links are processed first and protected so their content isn't re-formatted."""
    s = _esc(s)
    holds: list[str] = []
    def _hold(html: str) -> str:
        holds.append(html); return f"\x00{len(holds) - 1}\x00"
    s = re.sub(r"`([^`]+)`", lambda m: _hold("<code>" + m.group(1) + "</code>"), s)
    s = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+|/[^)\s]*)\)",
               lambda m: _hold(f'<a href="{m.group(2)}">{m.group(1)}</a>'), s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"~~(.+?)~~", r"<del>\1</del>", s)
    s = re.sub(r"(?<![\w*])\*(?!\s)([^*]+?)(?<!\s)\*(?![\w*])", r"<em>\1</em>", s)      # *italic*
    s = re.sub(r"(?<![\w_])_(?!\s)([^_]+?)(?<!\s)_(?![\w_])", r"<em>\1</em>", s)        # _italic_ (not word-internal)
    for k, hh in enumerate(holds):
        s = s.replace(f"\x00{k}\x00", hh)
    return s


def _md(text: str) -> str:
    """Minimal-but-real GitHub-flavored Markdown → HTML (no deps). Covers the host-authored subset
    (spec/markdown-authoring-harness.md): #/##/### headings, **bold**/_italic_/`code`/[links]/~~del~~,
    `-`/`*` and `1.` lists, `>` blockquotes, `---` rules, ``` fenced code, pipe tables, paragraphs."""
    if not text:
        return ""

    def _cells(row: str) -> list[str]:
        return [c.strip() for c in row.strip().strip("|").split("|")]

    lines = text.split("\n")
    n = len(lines); out: list[str] = []; stack: list[str] = []; i = 0

    def _close():                                  # close any open list(s)
        while stack:
            out.append(f"</{stack.pop()}>")

    while i < n:
        line = lines[i].rstrip(); stripped = line.lstrip()
        if stripped.startswith("```"):             # fenced code block
            _close(); j = i + 1; buf = []
            while j < n and not lines[j].lstrip().startswith("```"):
                buf.append(_esc(lines[j])); j += 1
            out.append("<pre><code>" + "\n".join(buf) + "</code></pre>"); i = j + 1; continue
        if stripped.startswith("|") and i + 1 < n:  # pipe table (header + |---| separator)
            sep = lines[i + 1].strip()
            if sep.startswith("|") and "-" in sep and not set(sep) - set("|:- "):
                _close(); header = _cells(stripped); j = i + 2; rows = []
                while j < n and lines[j].strip().startswith("|"):
                    rows.append(_cells(lines[j])); j += 1
                th = "".join(f"<th>{_md_inline(c)}</th>" for c in header)
                trs = "".join("<tr>" + "".join(f"<td>{_md_inline(c)}</td>" for c in r) + "</tr>" for r in rows)
                out.append(f'<table class="sl-table sl-table--bordered sl-table--zebra"><thead><tr>{th}</tr></thead><tbody>{trs}</tbody></table>')
                i = j; continue
        if not stripped:
            _close(); i += 1; continue
        if re.fullmatch(r"(-{3,}|\*{3,}|_{3,})", stripped):     # horizontal rule
            _close(); out.append("<hr>"); i += 1; continue
        if stripped.startswith(">"):                 # blockquote (consume consecutive > lines)
            _close(); buf = []
            while i < n and lines[i].lstrip().startswith(">"):
                buf.append(lines[i].lstrip()[1:].lstrip()); i += 1
            out.append("<blockquote>" + _md_inline(" ".join(buf)) + "</blockquote>"); continue
        m = re.match(r"\d+\.\s+(.*)", stripped)      # ordered list
        if m:
            if not (stack and stack[-1] == "ol"):
                _close(); out.append("<ol>"); stack.append("ol")
            out.append(f"<li>{_md_inline(m.group(1))}</li>"); i += 1; continue
        if stripped[:2] in ("- ", "* ") or stripped.startswith("• "):   # unordered list
            if not (stack and stack[-1] == "ul"):
                _close(); out.append("<ul>"); stack.append("ul")
            out.append(f"<li>{_md_inline(stripped[2:].lstrip())}</li>"); i += 1; continue
        _close()
        if stripped.startswith("#### "): out.append(f"<h4>{_md_inline(stripped[5:])}</h4>")
        elif stripped.startswith("### "): out.append(f"<h4>{_md_inline(stripped[4:])}</h4>")
        elif stripped.startswith("## "): out.append(f"<h3>{_md_inline(stripped[3:])}</h3>")
        elif stripped.startswith("# "): out.append(f"<h3>{_md_inline(stripped[2:])}</h3>")
        else: out.append(f"<p>{_md_inline(line)}</p>")
        i += 1
    _close()
    return "\n".join(out)


def _srcchips(s: str) -> str:
    return re.sub(r"\[(C\d[^\]]*)\]", r'<span class="srcchip">\1</span>', s)


def _prose(s: object) -> str:
    """The ONE renderer for inline authored prose (list items, verdicts, arguments, recommendations):
    inline Markdown (**bold**/_italic_/`code`/links) PLUS [C#] citation chips. Use this everywhere a
    single line/paragraph of host-authored text is shown, so Markdown renders consistently and no
    surface shows literal `**`. Multi-paragraph blocks still use _md()."""
    return _srcchips(_md_inline(str(s)))


def _rec_row(text: str) -> str:
    m = re.match(r"\s*\[?PRIO\s*(\d+)\]?\s*[—:\-]\s*(.*)", text, re.S)
    if m:
        n = int(m.group(1)); body = m.group(2)
        badge = h("span", {"class_": f"prio prio-{min(n, 5)}"}, f"PRIO {n}")
    else:
        body = text; badge = h("span", {"class_": "prio prio-5"}, "•")
    return h("div", {"class_": "rec"}, badge, h("div", {}, raw(_srcchips(_esc(body)))))


def _rec_item(x) -> tuple:
    if isinstance(x, dict):
        return str(x.get("text", "")), x.get("aufwand"), x.get("nutzen")
    return str(x), None, None


def _rec_row_n(i: int, text: str, a, n) -> str:
    ax = h("span", {"class_": "axchip"}, t("effort_value", a=a, n=n)) if (a and n) else ""
    return h("div", {"class_": "rec", "id": f"rec-{i}"}, h("span", {"class_": "recnum"}, str(i)),
             h("div", {}, raw(_prose(text)), ax))


def _effort_impact(recs: list) -> str:
    """recs: [(text, effort, value)] (1-based order = the dot/legend number). Renders the design-system
    effort·impact chart (sonaloop._charts → .sl-quad/.sl-legend, vendored from sonaloop-design), with
    i18n axis + quadrant labels. Returns '' when nothing is scored."""
    from .._charts import effort_impact as _ds_effort_impact
    items = [{"label": txt, "x": a, "y": n} for (txt, a, n) in recs if a and n]
    return _ds_effort_impact(
        items, x_label=t("ei_effort_axis").replace("→", "").strip(),
        y_label=t("ei_value_axis").replace("→", "").strip(),
        quadrants=(t("ei_quick_wins"), t("ei_big_bets"), t("ei_fill_ins"), t("ei_time_sinks")))


def _doc(main: str, toc: str = "", rail: str = "") -> str:
    cls = "d3" if (toc and rail) else ("d2" if rail else "d1")
    toc_html = h("div", {"class_": "toc"}, raw(toc)) if toc else ""
    rail_html = h("aside", {"class_": "rail"}, raw(rail)) if rail else ""
    return h("div", {"class_": "page"}, h("div", {"class_": f"doc {cls}"}, toc_html,
             h("div", {"class_": "doc-main"}, raw(main)), rail_html))

# Co-located CSS (spec/roadmap.md R3): labels/avatars, stat strip, stars/favorites.
register_css(r"""
/* ---- labels / avatars (G5) ---- */
.lbl{display:inline-flex;align-items:center;gap:6px;font-size:var(--t-sm);border-radius:var(--radius-sm);padding:2px 8px;white-space:nowrap}
.lbl-soft{background:var(--panel-2);border:1px solid var(--line);color:var(--ink)}
.lbl-outline{border:1px solid var(--line);color:var(--muted)}
/* label dot (.sl-dot) and avatars (.sl-avatar) come from the shared COMPONENTS_CSS layer;
   _avatar() still sets per-instance size/colour inline. */
/* ---- stat strip + persona cards (G2) ---- */
.stats{display:flex;flex-wrap:wrap;gap:8px;margin:0 0 20px}
.stat{display:flex;align-items:baseline;gap:7px;border:1px solid var(--line);border-radius:var(--radius);background:var(--panel);padding:8px 12px}
.stat b{font-size:var(--t-lg);font-weight:700}.stat span{color:var(--muted);font-size:var(--t-sm)}
/* ---- stars / favorites ---- */
/* the box model comes from .sl-iconbtn--ghost (W3 one control vocabulary) — only the
   favourite colours live here */
.starbtn:hover{color:#e3a008}
.starbtn .star{fill:none}
.starbtn.on{color:#e3a008}.starbtn.on .star{fill:#e3a008;stroke:#e3a008}
#favs a{display:flex;align-items:center;gap:6px;flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.favrow{display:flex;align-items:center;gap:2px}
.favx{border:0;background:none;color:var(--muted);cursor:pointer;font-size:var(--t-prose);line-height:1;padding:1px 7px;border-radius:var(--radius-sm);opacity:0;transition:opacity 120ms}
.favrow:hover .favx{opacity:1}.favx:hover{color:#e3a008;background:var(--hover)}
""")

# Co-located CSS (spec/roadmap.md R3): turn cards / detail-page chrome.
register_css(r"""
/* ---- turn cards / detail ---- */
.turn{border:1px solid var(--line);border-radius:var(--radius);background:var(--panel);padding:12px}
/* speaker name = the row-title layer (600), never shouting over the turn text (§11 T4) */
.turn .hd{display:flex;align-items:center;gap:8px;margin:0 0 8px;flex-wrap:wrap}.turn .hd b{font-size:var(--t-body);font-weight:600}
.turn.mod{background:var(--panel-2)}
.turn-who{display:inline-flex;align-items:center;gap:7px;color:var(--ink);text-decoration:none}
.turn-who:hover b{color:var(--accent)}
.turn-ctx{flex-basis:100%;margin:2px 0 0;font-style:italic}
/* bare card (persona's own page): no avatar/name; lead with the council it was said in */
.turn-bare{padding:8px 12px}
.turn-src{display:inline-flex;align-items:center;gap:6px;color:var(--muted);text-decoration:none;font-size:var(--t-sm);max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.turn-src:hover{color:var(--accent)}.turn-src svg{width:13px;height:13px;flex:none;opacity:.8}
/* empty / not-found state — a calm centered card with a hi-fi product glyph (Linear-style) */
/* Empty / not-found state = the shared .sl-empty (+__icon/__title/__body) from COMPONENTS_CSS.
   Only the page-positioning (centre, push down from the top) is inspector-local. */
.sl-empty{margin:8vh auto 0}
.sl-empty .sl-btn{margin-top:8px}
/* a persona's multiple answers stack in one card, separated by a hairline */
.turn-ans+.turn-ans{margin-top:12px;padding-top:12px;border-top:1px solid var(--line-2)}
.turn-ans>p{margin:0}
/* moderated transcript: one round per moderator question (the question, then the answers) */
.qrounds{display:flex;flex-direction:column;gap:24px}
.qround{display:flex;flex-direction:column;gap:12px}
.qround-q{display:flex;align-items:flex-start;gap:12px;padding:12px 16px;background:var(--accent-weak);border:1px solid var(--line);border-radius:var(--radius)}
.qround-q>svg{color:var(--accent);flex-shrink:0;width:18px;height:18px;margin-top:1px}
.qround-q p{margin:2px 0 0;font-weight:600;font-size:var(--t-md);line-height:1.35;max-width:var(--measure-prose)}
/* the round kicker speaks the ONE eyebrow voice (§11 T3/T4) */
.qround-n{font-family:var(--mono);font-size:var(--t-xs);font-weight:500;letter-spacing:.14em;text-transform:uppercase;color:var(--accent)}
.qround-a{display:flex;flex-direction:column;gap:12px}
.turn-input{margin:2px 0 8px;border:1px dashed var(--line);border-radius:var(--radius);padding:8px 12px;background:var(--bg)}
.turn-input summary{cursor:pointer}
/* prototype-session fields, inside the shared .turn statement card — labelled like the sl-prose eyebrows */
.sfield{margin:12px 0 0}.sfield:first-child{margin-top:2px}.sfield .eyebrow{margin:0 0 3px}.sfield .sl-prose{margin:0}.sfield .sl-prose p{margin:0}
.detail{max-width:980px}.thought{font-size:var(--t-md);padding:8px 12px;background:var(--panel-2);border-radius:var(--radius)}
.quote{padding:8px 12px;background:var(--panel-2);margin:8px 0;border-radius:var(--radius)}
.identity{display:grid;grid-template-columns:160px 1fr;gap:20px;align-items:start}
.identity .avatar{width:160px;height:200px;object-fit:cover;border-radius:var(--radius);border:1px solid var(--line)}
""")
