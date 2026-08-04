"""Cmd+K command palette v2 (ux-contract §9 V6): Recent · Navigate · entity results.

Self-contained (CSS deltas + markup + JS), injected once by _layout so it works on every
page — built on the vendored design-system `.sl-cmdk-*` contract (sonaloop-design ships
the classes; this module ships the inspector's markup over them).

Anatomy (Linear-grade, quiet groups):
  - EMPTY: **Recent** (the last 6 visited entities — tracked client-side in localStorage
    from server-stamped `visit_marker` beacons on detail/slide-over renders) · **Navigate**
    (the 4 workspace items + Settings/Documentation/Keyboard, icons everywhere; the Library
    kind lists are ONE expandable "Library" entry — → expands, ← collapses — never 13 flat
    links, C10) · **Actions** (theme toggle, tour, feedback — riding the existing
    data-tour-start / data-fb-open affordances).
  - TYPING: entity results from /api/search (web/_palette_registry.search_rows — ranked
    title-prefix > word-prefix > substring, diacritic-insensitive, 6 per kind) grouped by
    kind: icon · title · owning project · date. Navigation rows + actions stay matchable.
    Zero hits → honest empty state + the registry's closest matches (the DS-site idea).

WHAT the palette can reach is not declared here: the coverage registry
(web/_palette_registry.py) enumerates the searchable entity types and the structured
Navigate model; the canary test (tests/test_palette_coverage.py) fails when the app grows
a surface the registry doesn't reach."""
from __future__ import annotations

import json

from .. import config
from .._icons import icon as _picon       # direct import avoids a cycle (_components imports _palette)
from ._i18n import t
from ._html import h, raw
from ._palette_registry import SEARCH_SOURCES, nav_commands, palette_nav, search_rows  # noqa: F401 (search_rows re-exported for the API)


# App-side deltas over the vendored .sl-cmdk contract: the entity-row desc/meta columns
# (owning project · right-aligned date), the indented Library sub-rows + expand caret,
# and the teach line under the honest empty state. Type dot colors come FROM the registry.
PALETTE_CSS = r"""
.sl-cmdk-panel{max-height:78vh}
.sl-cmdk-input:focus,.sl-cmdk-input:focus-visible{outline:none;box-shadow:none}
.sl-cmdk-item{padding-top:.48em;padding-bottom:.48em}
.sl-cmdk-title{flex:0 1 auto}
.sl-cmdk-title:has(+ .sl-cmdk-desc){max-width:62%}
.sl-cmdk-desc{flex:1;min-width:0;color:var(--muted);font-size:var(--t-sm);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.sl-cmdk-meta{flex:none;margin-left:auto;color:var(--faint);font-size:var(--t-xs);font-variant-numeric:tabular-nums}
.sl-cmdk-item--sub{padding-left:2.5em}
.sl-cmdk-x{flex:none;margin-left:auto;display:inline-flex;color:var(--faint)}
.sl-cmdk-x svg{width:14px;height:14px;transition:transform .12s}
.sl-cmdk-item.is-open .sl-cmdk-x svg{transform:rotate(90deg)}
.sl-cmdk-empty small{display:block;margin-top:6px;color:var(--faint);font-size:var(--t-sm)}
""" + "".join(f".sl-cmdk-ico[data-t={tp}]{{color:{src.color}}}"   # per-type dot colors FROM the registry
              for tp, src in SEARCH_SOURCES.items())


def visit_marker(title: str, project: str = "") -> str:
    """The recents beacon (V6): every detail renderer stamps WHO is being viewed as an
    inert JSON `<script data-cmdk-visit>`; the palette JS picks it up (initial load, SPA
    swaps AND slide-over fetches — a MutationObserver watches for new beacons) and records
    {type, title, project, url} into localStorage ('sl-recent', last 6, deduped by url) —
    the palette's Recent group. Emits NOTHING unless the current request path is a
    searchable detail URL (/{prefix}/{id} with a SEARCH_SOURCES prefix), so list pages,
    sub-pages (/jobs/{id}/plan) and excused routes never pollute the recents."""
    from ._slide import request_path
    path = (request_path() or "").partition("?")[0]
    seg = [s for s in path.split("/") if s]
    if len(seg) != 2 or not title:
        return ""
    typ = next((tp for tp, src in SEARCH_SOURCES.items() if src.url_prefix == "/" + seg[0]), None)
    if not typ:
        return ""
    payload = json.dumps({"type": typ, "title": str(title), "project": str(project or ""),
                          "url": path}).replace("<", "\\u003c")
    return h("script", {"type": "application/json", "data-cmdk-visit": True}, raw(payload))


def palette_markup() -> str:
    """Per-request overlay markup (localised). The structured Navigate model (with the
    Library children), the actions, group labels, per-type icons and the grouping order
    are all seeded as JSON FROM the coverage registry — nothing is hand-copied here."""
    actions = [
        {"title": t("cmdk_theme"), "url": "#", "act": "theme", "ico": _picon("moon")},
    ]
    if config.product_tour_enabled():
        actions.append(
            {"title": t("tour_take"), "url": "#", "act": "tour", "ico": _picon("compass")}
        )
    actions.append(
        {"title": t("feedback_h"), "url": "#", "act": "feedback", "ico": _picon("chat")}
    )
    cfg = json.dumps({
        "nav": [{**it, "ico": _picon(it["icon"])} if "children" not in it
                else {**it, "ico": _picon(it["icon"]),
                      "children": [{**c, "ico": _picon(c["icon"])} for c in it["children"]]}
                for it in palette_nav()],
        "actions": actions,
        "labels": {"recent": t("cmdk_recent"), "go": t("cmdk_navigate"), "actions": t("cmdk_actions"),
                   "closest": t("cmdk_closest"), "empty": t("cmdk_empty"), "teach": t("cmdk_teach"),
                   **{tp: src.label() for tp, src in SEARCH_SOURCES.items()}},
        "icons": {"go": _picon("arrowRight"), **{tp: _picon(src.icon) for tp, src in SEARCH_SOURCES.items()}},
        "caret": _picon("caretRight"),
        "order": list(SEARCH_SOURCES),
    }).replace("<", "\\u003c")
    foot = h("div", {"class_": "sl-cmdk-foot"},
             h("span", {}, h("kbd", {"class_": "sl-kbd"}, "↑↓"), t("cmdk_nav")),
             h("span", {}, h("kbd", {"class_": "sl-kbd"}, "↵"), t("cmdk_open")),
             h("span", {}, h("kbd", {"class_": "sl-kbd"}, "esc"), t("cmdk_close")))
    overlay = h("div", {"class_": "sl-cmdk", "id": "cmdk", "hidden": True},
                h("div", {"class_": "sl-cmdk-backdrop", "data-cmdk-close": True}),
                h("div", {"class_": "sl-cmdk-panel", "role": "dialog", "aria-modal": "true"},
                  h("div", {"class_": "sl-cmdk-head"},
                    raw(_picon("search", cls="sl-cmdk-head-ico")),
                    h("input", {"id": "cmdk-in", "class_": "sl-cmdk-input", "type": "text",
                                "autocomplete": "off", "spellcheck": "false",
                                "placeholder": t("cmdk_placeholder")})),
                  h("div", {"class_": "sl-cmdk-list", "id": "cmdk-list"}),
                  foot))
    return overlay + h("script", {"id": "cmdk-cfg", "type": "application/json"}, raw(cfg))


PALETTE_JS = r"""<script>(function(){
var ov=document.getElementById('cmdk'); if(!ov) return;
var inp=document.getElementById('cmdk-in'), list=document.getElementById('cmdk-list');
var CFG={nav:[],actions:[],labels:{},icons:{},order:[]};
try{ CFG=JSON.parse(document.getElementById('cmdk-cfg').textContent)||CFG; }catch(e){}
var ORDER=CFG.order||[], L=CFG.labels||{}, sel=0, timer=null, libOpen=false;
function esc(s){ return String(s==null?'':s).replace(/[&<>"]/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c];}); }
function fold(s){ s=String(s==null?'':s); try{ s=s.normalize('NFKD').replace(/[\u0300-\u036f]/g,''); }catch(e){} return s.toLowerCase(); }
// ---- Recent: server-stamped [data-cmdk-visit] beacons -> localStorage (last 6, deduped).
var RK='sl-recent';
function recents(){ try{ var l=JSON.parse(localStorage.getItem(RK)||'[]'); return Array.isArray(l)?l.slice(0,6):[]; }catch(e){ return []; } }
function record(v){ if(!v||!v.url||!v.title||!CFG.icons[v.type]) return;
  var l=recents().filter(function(r){ return r.url!==v.url; });
  l.unshift({type:v.type,title:v.title,subtitle:v.project||'',url:v.url});
  try{ localStorage.setItem(RK,JSON.stringify(l.slice(0,6))); }catch(e){} }
function scan(){ var ms=document.querySelectorAll('script[data-cmdk-visit]:not([data-cv])');
  for(var i=0;i<ms.length;i++){ ms[i].setAttribute('data-cv','1');
    try{ record(JSON.parse(ms[i].textContent)); }catch(e){} } }
scan();
if(window.MutationObserver){ var mt=0, mo=new MutationObserver(function(){
  if(mt) return; mt=setTimeout(function(){ mt=0; scan(); },80); });
  mo.observe(document.body,{childList:true,subtree:true}); }
// ---- rendering: one sl-entity-grade row (icon - title - desc - meta), muted group headers.
function row(r,i,o){ o=o||{};
  var cls='sl-cmdk-item'+(i===sel?' is-active':'')+(o.sub?' sl-cmdk-item--sub':'')+(o.open?' is-open':'');
  var p='<a class="'+cls+'" data-i="'+i+'" href="'+esc(r.url||'#')+'"';
  if(r.act) p+=' data-act="'+esc(r.act)+'"';
  if(r.act==='tour') p+=' data-tour-start';
  if(r.act==='feedback') p+=' data-fb-open';
  if(o.lib) p+=' data-lib';
  p+='><span class="sl-cmdk-ico" data-t="'+esc(r.type||'go')+'">'+(r.ico||CFG.icons[r.type]||CFG.icons.go||'')+'</span>';
  p+='<span class="sl-cmdk-title">'+esc(r.title)+'</span>';
  if(r.subtitle) p+='<span class="sl-cmdk-desc">'+esc(r.subtitle)+'</span>';
  if(r.date) p+='<span class="sl-cmdk-meta">'+esc(r.date)+'</span>';
  if(o.lib) p+='<span class="sl-cmdk-x">'+(CFG.caret||'')+'</span>';
  return p+'</a>';
}
function sec(label){ return '<div class="sl-cmdk-sec">'+esc(label)+'</div>'; }
function paint(html,n){ if(sel>=n) sel=n?n-1:0; list.scrollTop=0; list.innerHTML=html; }
// ---- the empty state: Recent - Navigate (Library expandable) - Actions.
function home(){
  var html='', i=0, rec=recents();
  if(rec.length){ html+=sec(L.recent); rec.forEach(function(r){ html+=row(r,i++); }); }
  html+=sec(L.go);
  (CFG.nav||[]).forEach(function(n){
    if(n.quiet) return;
    var lib=!!n.children;
    html+=row(n,i++,{lib:lib,open:lib&&libOpen});
    if(lib&&libOpen) n.children.forEach(function(c){ html+=row(c,i++,{sub:true}); });
  });
  if((CFG.actions||[]).length){ html+=sec(L.actions); CFG.actions.forEach(function(a){ html+=row(a,i++); }); }
  paint(html,i);
}
// ---- typing: rank statics title-prefix > word-prefix > substring (diacritic-folded).
function rank(qf,title){ var tf=fold(title); var at=tf.indexOf(qf); if(at<0) return -1;
  if(at===0) return 0;
  var ws=tf.split(/\s+/); for(var k=0;k<ws.length;k++){ if(ws[k].lastIndexOf(qf,0)===0) return 1; }
  return 2; }
function statics(qf){
  var nav=[], act=[];
  (CFG.nav||[]).forEach(function(n){
    var r0=rank(qf,n.title); if(r0>=0) nav.push([r0,n]);
    (n.children||[]).forEach(function(c){
      var rc=rank(qf,c.title); if(rc>=0) nav.push([rc,{title:c.title,url:c.url,ico:c.ico,subtitle:n.title}]); });
  });
  (CFG.actions||[]).forEach(function(a){ var ra=rank(qf,a.title); if(ra>=0) act.push([ra,a]); });
  function srt(x){ x.sort(function(p,q2){ return p[0]-q2[0]; }); return x.map(function(p){ return p[1]; }); }
  return {nav:srt(nav),act:srt(act)};
}
function results(q,data){
  var st=statics(fold(q)), rows=(data&&data.rows)||[], close=(data&&data.closest)||[];
  if(!data&&!st.nav.length&&!st.act.length) return;   // keep the old list until the fetch lands
  var html='', i=0;
  if(st.nav.length){ html+=sec(L.go); st.nav.forEach(function(n){ html+=row(n,i++); }); }
  if(st.act.length){ html+=sec(L.actions); st.act.forEach(function(a){ html+=row(a,i++); }); }
  var groups={}; rows.forEach(function(r){ (groups[r.type]=groups[r.type]||[]).push(r); });
  ORDER.forEach(function(tp){ var g=groups[tp]; if(!g) return;
    html+=sec(L[tp]||tp); g.forEach(function(r){ html+=row(r,i++); }); });
  if(!i&&data){ html+='<div class="sl-cmdk-empty">'+esc(L.empty)+'<small>'+esc(L.teach)+'</small></div>';
    if(close.length){ html+=sec(L.closest); close.forEach(function(r){ html+=row(r,i++); }); } }
  paint(html,i);
}
function search(q){ q=(q||'').trim();
  if(!q){ sel=0; home(); return; }
  sel=0; results(q,null);
  fetch('/api/search?q='+encodeURIComponent(q)).then(function(r){return r.json();}).then(function(d){
    if(ov.hidden||inp.value.trim()!==q) return; results(q,d); }).catch(function(){});
}
function open(){ ov.hidden=false; inp.value=''; sel=0; libOpen=false; home(); inp.focus(); }
function close(){ ov.hidden=true; }
function move(d){ var els=list.querySelectorAll('.sl-cmdk-item'); if(!els.length) return;
  if(els[sel]) els[sel].classList.remove('is-active'); sel=(sel+d+els.length)%els.length;
  els[sel].classList.add('is-active'); els[sel].scrollIntoView({block:'nearest'}); }
function setLib(openIt){ var a=list.querySelector('.sl-cmdk-item[data-i="'+sel+'"]');
  if(!a||!a.hasAttribute('data-lib')||libOpen===openIt) return false;
  libOpen=openIt; home(); return true; }
function toggleTheme(){
  var cur=document.documentElement.dataset.theme||
    (window.matchMedia&&matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light');
  var nxt=cur==='dark'?'light':'dark';
  var b=document.querySelector('[data-theme-set="'+nxt+'"]');
  if(b){ b.click(); }
  else{ document.documentElement.dataset.theme=nxt; try{localStorage.setItem('theme',nxt);}catch(e){} }
}
inp.addEventListener('input',function(){ clearTimeout(timer); var q=inp.value; timer=setTimeout(function(){ search(q); },120); });
inp.addEventListener('keydown',function(e){
  if(e.key==='ArrowDown'){ e.preventDefault(); move(1); }
  else if(e.key==='ArrowUp'){ e.preventDefault(); move(-1); }
  else if(e.key==='ArrowRight'&&!inp.value){ if(setLib(true)) e.preventDefault(); }
  else if(e.key==='ArrowLeft'&&!inp.value){ if(setLib(false)) e.preventDefault(); }
  else if(e.key==='Enter'){ e.preventDefault(); var a=list.querySelector('.sl-cmdk-item[data-i="'+sel+'"]'); if(a) a.click(); }
  else if(e.key==='Escape'){ e.preventDefault(); close(); } });
list.addEventListener('click',function(e){
  var a=e.target.closest&&e.target.closest('.sl-cmdk-item'); if(!a) return;
  if(a.hasAttribute('data-lib')&&e.target.closest&&e.target.closest('.sl-cmdk-x')){
    e.preventDefault(); e.stopPropagation(); libOpen=!libOpen; sel=+a.getAttribute('data-i')||0; home(); return; }
  var act=a.getAttribute('data-act');
  if(act){ e.preventDefault(); if(act==='theme') toggleTheme(); }   // tour/feedback ride their delegated [data-*] handlers
  close();
});
list.addEventListener('mousemove',function(e){ var a=e.target.closest&&e.target.closest('.sl-cmdk-item'); if(!a) return;
  var i=+a.getAttribute('data-i'); if(i!==sel){ var els=list.querySelectorAll('.sl-cmdk-item'); if(els[sel]) els[sel].classList.remove('is-active'); sel=i; a.classList.add('is-active'); } });
ov.addEventListener('click',function(e){ if(e.target.hasAttribute('data-cmdk-close')) close(); });
// the sidebar search trigger (under the logo) opens the palette; delegated so it survives SPA swaps
document.addEventListener('click',function(e){ if(e.target.closest&&e.target.closest('[data-cmdk-open]')){ e.preventDefault(); open(); } });
// the '#settings' jump command opens the sidebar's settings popover (no /settings route)
document.addEventListener('click',function(e){
  var a=e.target.closest&&e.target.closest('a[href="#settings"]'); if(!a) return;
  e.preventDefault(); var tg=document.querySelector('.sl-um-trigger'); if(tg) tg.click(); });
window.addEventListener('keydown',function(e){
  if((e.metaKey||e.ctrlKey)&&(e.key==='k'||e.key==='K')){ e.preventDefault(); if(ov.hidden) open(); else close(); }
  else if(e.key==='Escape'&&!ov.hidden){ close(); } });
})();</script>"""
