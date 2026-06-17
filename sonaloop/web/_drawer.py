"""SPA navigation + the Notion-style slide-over drawer (spec/ux-contract.md §8.1/§8.6, UX U6/U11).

The two client-side navigation layers, extracted from web/_components for the LOC bar and
because they form ONE history machine: the SPA router swaps #main for ordinary internal links,
the drawer opens data-drawer targets as a slide-over and pushes the CONTEXT URL — the background
page + `?d=<detail path>` (§8.6, Notion semantics v2) — and popstate is arbitrated between them
(the drawer consumes transitions into/out of its entries, window.__slBg tracks the page content
behind the overlay). _layout (web/_components) injects drawer_markup() + both scripts on every
page; a `?d=` context URL arrives SSR'd with the panel already open (web/_slide.ssr_drawer).
"""
from __future__ import annotations

import re as _re

from .._icons import icon as _icon
from ._html import h, raw, register_css
from ._slide import ssr_drawer


# SPA-style navigation (spec/design-system.md): the sidebar/topbar shell is rendered once; internal
# link clicks fetch the target and swap ONLY #main, so the sidebar (and its favorites) never re-render
# or flicker. Pure progressive enhancement — falls back to a full load on any error or non-HTML response.
# History interplay with the slide-over (§8.1/§8.6): popstate is ARBITRATED — the drawer (window.SLDrawer,
# DRAWER_JS below) consumes transitions into/out of its pushed ?d= context entries; only then does the
# SPA router re-fetch. window.__slBg tracks the URL of the page CONTENT currently in #main (always
# WITHOUT ?d= — the param is the overlay, not the page), so a re-entered drawer entry knows whether
# its background is still the page it was opened over.
SPA_JS = """
<script>
(function(){
  var main=document.getElementById('main');
  if(!main || !window.history || !window.history.pushState || !window.fetch) return;
  window.__slBg=(function(){ var p=new URLSearchParams(location.search); p.delete('d');
    var q=p.toString(); return location.pathname+(q?'?'+q:''); })();
  function runScripts(root){            // importNode'd <script>s don't execute — recreate them so they do
    root.querySelectorAll('script').forEach(function(old){
      var s=document.createElement('script');
      for(var i=0;i<old.attributes.length;i++){ s.setAttribute(old.attributes[i].name, old.attributes[i].value); }
      s.textContent=old.textContent; old.parentNode.replaceChild(s, old);
    });
  }
  function syncActive(doc){             // mirror the fetched page's sidebar active-state onto the live nav
    var on={}; doc.querySelectorAll('.sl-sidebar .sl-nav a.is-active').forEach(function(a){ on[a.getAttribute('href')]=1; });
    document.querySelectorAll('.sl-sidebar .sl-nav a').forEach(function(a){ a.classList.toggle('is-active', !!on[a.getAttribute('href')]); });
  }
  function swap(html, url, push){
    var doc=new DOMParser().parseFromString(html, 'text/html');
    var nm=doc.getElementById('main');
    if(!nm){ location.href=url; return; }                 // unexpected shape -> full load
    var imp=document.importNode(nm, true);
    main.replaceWith(imp); main=imp;
    if(doc.title) document.title=doc.title;
    syncActive(doc);
    runScripts(main);
    if(push) history.pushState({spa:1}, '', url);
    window.__slBg=url;                                     // the page now behind any overlay
    if(window.SLDrawer) window.SLDrawer.hide();            // navigating away closes the slide-over
    window.scrollTo(0,0);
    document.dispatchEvent(new CustomEvent('spa:load'));   // let app_js re-apply star states etc.
  }
  function navigate(url, push){
    document.body.classList.add('spa-loading');
    fetch(url, {headers:{'X-Requested-With':'spa'}, credentials:'same-origin'}).then(function(r){
      var ct=r.headers.get('content-type')||'';
      if(!r.ok || ct.indexOf('text/html')<0){ location.href=url; return; }
      return r.text().then(function(t){ swap(t, url, push); });
    }).catch(function(){ location.href=url; })
      .then(function(){ document.body.classList.remove('spa-loading'); });
  }
  document.addEventListener('click', function(e){
    if(e.defaultPrevented||e.button!==0||e.metaKey||e.ctrlKey||e.shiftKey||e.altKey) return;
    var a=e.target.closest && e.target.closest('a'); if(!a) return;
    if(a.hasAttribute('data-drawer')) return;                                // handled by the drawer
    var href=a.getAttribute('href');
    if(!href || href.charAt(0)!=='/' || href.indexOf('//')===0) return;     // internal absolute paths only
    if(a.target==='_blank' || a.hasAttribute('download') || a.getAttribute('rel')==='external') return;
    if(href.indexOf('/data/')===0 || href.indexOf('/proto-files/')===0) return;  // static assets -> real nav
    e.preventDefault();
    if(href===location.pathname+location.search){ return; }
    navigate(href, true);
  });
  window.addEventListener('popstate', function(e){
    if(window.SLDrawer && window.SLDrawer.onpop(e)) return;   // a drawer-entry transition — consumed
    navigate(location.pathname+location.search, false);
  });
})();
</script>
"""


# The Notion-style slide-over (spec/ux-contract.md §8.1 + §8.6, UX U6/U11) — the shared
# design-system overlay (.sl-drawer*, --wide variant; styling lives in sonaloop-design
# styles/components.css, vendored via _components_css.py). Any element with
# data-drawer="<canonical detail URL>" opens that page's FULL content as a slide-over: the JS
# fetches the `?slide=1` fragment variant (same route, same renderer — web/_slide.py) while
# history.pushState's the CONTEXT URL — the background page + `?d=<urlencoded detail path>`
# (joined onto whatever params the background already carries: tabs, filters).
# Reload/share of that URL server-renders the SAME view (background + open panel, no fetch
# flash); the canonical detail URL stays the full-page address (the expand control navigates
# to it, and rows keep it as their href for middle-click / no-JS). Esc/scrim/back drops ?d=
# (history.back when we pushed the entry; replaceState when the panel arrived SSR-opened).
# Only the in-drawer .page reset is app-local; the panel/scrim/header chrome is the shared component.
DRAWER_CSS = register_css(".sl-drawer__body .page{padding:0;max-width:none}"
                          ".sl-drawer__body img{max-width:100%;height:auto}")


def drawer_markup(close_label: str, expand_label: str) -> str:
    """The drawer chrome _layout injects on every page — CLOSED by default (the client JS
    drives it), or SSR'd OPEN with the detail fragment already inside when the request is a
    `?d=` context URL (§8.6: reload reproduces the click view; no fetch flash). In SSR mode
    the scrim and the expand control are real links — scrim → the URL without `?d=`, expand →
    the canonical detail URL — so both work without JS; data-ssr lets DRAWER_JS adopt the
    open panel (title, history state) instead of re-fetching it."""
    ssr = ssr_drawer()
    expand_icon = raw(_icon("expand"))
    close_x = raw('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" '
                  'stroke-linecap="round"><path d="M6 6l12 12M18 6L6 18"/></svg>')
    if ssr is None:
        detail, body, title = None, None, ""
        scrim = h("div", {"class_": "sl-drawer__scrim", "data_drawer_close": True})
        expand = h("button", {"class_": "sl-iconbtn sl-iconbtn--ghost", "type": "button", "data_drawer_expand": True,
                              "aria_label": expand_label, "title": expand_label}, expand_icon)
    else:
        detail, body_html, close_href = ssr
        body = raw(body_html)
        # the server already knows the document title — no empty-header flash before JS runs
        m = _re.search(r"<h1[^>]*>(.*?)</h1>", body_html, _re.S)
        title = raw(_re.sub(r"<[^>]+>", "", m.group(1)).strip()) if m else ""  # already-escaped text
        scrim = h("a", {"class_": "sl-drawer__scrim", "data_drawer_close": True, "href": close_href,
                        "aria_label": close_label})
        expand = h("a", {"class_": "sl-iconbtn sl-iconbtn--ghost", "data_drawer_expand": True, "href": detail,
                         "aria_label": expand_label, "title": expand_label}, expand_icon)
    return str(h(
        "div", {"class_": "sl-drawer sl-drawer--wide" + (" is-open" if ssr else ""),
                "id": "drawer", "data_ssr": detail},
        scrim,
        h("aside", {"class_": "sl-drawer__panel", "role": "dialog", "aria_modal": "true",
                    "aria_labelledby": "drawer-title"},
          h("header", {"class_": "sl-drawer__head"},
            h("span", {"class_": "sl-drawer__title", "id": "drawer-title"}, title),
            expand,
            h("button", {"class_": "sl-iconbtn sl-iconbtn--ghost", "type": "button", "data_drawer_close": True,
                         "aria_label": close_label, "title": close_label}, close_x)),
          h("div", {"class_": "sl-drawer__body"}, body))))


DRAWER_JS = """
<script>
(function(){
  var wrap=document.getElementById('drawer'); if(!wrap || !window.fetch) return;
  var body=wrap.querySelector('.sl-drawer__body'), titleEl=wrap.querySelector('.sl-drawer__title'), lastFocus=null;
  var pushed=false, curUrl='';                 // pushed: we own ONE history entry (the ?d= context URL)
  function bgUrl(){ var p=new URLSearchParams(location.search); p.delete('d');
    var q=p.toString(); return location.pathname+(q?'?'+q:''); }
  function ctxUrl(detail){ var p=new URLSearchParams(location.search); p.set('d', detail);
    return location.pathname+'?'+p.toString(); }
  if(!window.__slBg) window.__slBg=bgUrl();
  function runScripts(root){
    root.querySelectorAll('script').forEach(function(old){ var s=document.createElement('script');
      for(var i=0;i<old.attributes.length;i++){ s.setAttribute(old.attributes[i].name, old.attributes[i].value); }
      s.textContent=old.textContent; old.parentNode.replaceChild(s, old); });
  }
  // V10: the fragment carries the page's header actions (the "…" overflow + its edit/delete
  // dialogs, the star) hidden as [data-slide-actions] — hoist them into the panel header next
  // to expand/close, so the actions are reachable from the peek too.
  function hoistActions(){
    var head=wrap.querySelector('.sl-drawer__head'); if(!head) return;
    head.querySelectorAll('[data-slide-actions]').forEach(function(n){ n.remove(); });
    var a=body.querySelector('[data-slide-actions]');
    if(a){ a.removeAttribute('hidden'); head.insertBefore(a, head.querySelector('[data-drawer-expand]')); }
  }
  function hide(){ wrap.classList.remove('is-open'); pushed=false; curUrl='';
    if(lastFocus&&lastFocus.focus) lastFocus.focus(); lastFocus=null; }
  function close(){                            // drop ?d=: pop our entry when we pushed one,
    if(pushed && history.state && history.state.slDrawer) history.back();   // -> onpop -> hide()
    else{                                      // SSR-opened (no entry of ours) -> rewrite in place
      if(history.replaceState && new URLSearchParams(location.search).has('d'))
        history.replaceState({spa:1}, '', bgUrl());
      hide(); }
  }
  function load(url, title){
    curUrl=url; titleEl.textContent=title||'';
    body.innerHTML='<p class="muted small">\\u2026</p>';
    wrap.classList.add('is-open');
    var fu=url+(url.indexOf('?')<0?'?':'&')+'slide=1';     // the fragment variant of the SAME route
    fetch(fu, {headers:{'X-Requested-With':'drawer'}, credentials:'same-origin'}).then(function(r){
      if(!r.ok) throw 0; return r.text();
    }).then(function(html){
      var doc=new DOMParser().parseFromString(html, 'text/html');
      // ?slide=1 answers a bare .sl-slide fragment; a page without the variant peeks its #main section
      var frag=doc.querySelector('.sl-slide') || doc.querySelector('#main section')
               || doc.getElementById('main') || doc.body.firstElementChild;
      body.innerHTML='';
      if(frag){ body.appendChild(document.importNode(frag, true)); runScripts(body); }
      hoistActions();
      if(!titleEl.textContent){ var h1=body.querySelector('h1');
        if(h1) titleEl.textContent=(h1.textContent||'').trim(); }
      body.scrollTop=0;
      document.dispatchEvent(new CustomEvent('spa:load'));   // re-apply star states inside the drawer
    }).catch(function(){ location.href=url; });               // any failure -> just open the real page
  }
  function open(url, title, trigger){
    lastFocus=trigger||document.activeElement;
    // Notion semantics v2 (§8.6): the address stays the BACKGROUND URL and gains ?d=<detail>
    // (composed with the background's own params — tabs, filters, views); reload/share of that
    // URL SSRs the same context view. Back/Esc/scrim pops our entry and restores the list URL.
    if(window.history && history.pushState){
      var cu=ctxUrl(url);
      if(cu!==location.pathname+location.search){
        // pushed:1 rides the STATE so a reload of this entry still knows close = history.back()
        history.pushState({slDrawer:url, under:window.__slBg||bgUrl(), pushed:1}, '', cu); pushed=true; }
    }
    load(url, title);
  }
  // popstate arbitration (SPA_JS defers here first): consume transitions into/out of drawer entries.
  window.SLDrawer={
    hide: hide,
    onpop: function(e){
      var st=e.state||{};
      if(st.slDrawer){                          // forward/back INTO a drawer entry
        if((st.under||'')===(window.__slBg||'')){ pushed=!!st.pushed; load(st.slDrawer, ''); }
        else location.reload();                 // background changed since -> honest full render
        return true; }
      if(/[?&]d=/.test(location.search)){       // a ?d= entry we never stamped -> honest SSR render
        location.reload(); return true; }
      if(wrap.classList.contains('is-open')){ hide(); return true; }   // back OUT of the drawer
      return false; }};
  document.addEventListener('click', function(e){
    if(e.defaultPrevented||e.button!==0||e.metaKey||e.ctrlKey||e.shiftKey||e.altKey) return;  // modified click -> href
    var x=e.target.closest && e.target.closest('[data-drawer-expand]');
    if(x){ e.preventDefault();
      // expand = a REAL navigation to the canonical detail URL (full page; back returns here)
      if(curUrl && curUrl!==location.pathname+location.search) location.href=curUrl;
      else location.reload();
      return; }
    if(e.target.closest && e.target.closest('[data-drawer-close]')){ e.preventDefault(); close(); return; }
    var t=e.target.closest && e.target.closest('[data-drawer]');
    if(t){ e.preventDefault(); e.stopPropagation();
      // Title fallback prefers the row's title slot — full textContent would concatenate
      // title+desc+badges into one run-on header (ux-audit P5 finding).
      var tt=t.querySelector && t.querySelector('.sl-entity__title,.ol-title');
      open(t.getAttribute('data-drawer'), t.getAttribute('data-drawer-title')||((tt||t).textContent||'').trim(), t); return; }
  });
  document.addEventListener('keydown', function(e){
    // a modal <dialog> (V10 edit / confirm) owns Esc while open — don't also drop the panel
    if(e.key==='Escape' && wrap.classList.contains('is-open') && !document.querySelector('dialog[open]')) close(); });
  // SSR-opened context URL (§8.6): adopt the server-rendered panel — no entry of ours exists
  // (close rewrites the URL in place), but the CURRENT entry must self-describe so leaving and
  // re-entering it via back/forward re-opens the panel instead of stranding a ?d= URL closed.
  var ssr=wrap.getAttribute('data-ssr');
  if(ssr){
    curUrl=ssr; window.__slBg=bgUrl();
    hoistActions();
    // reload of a CLICK-pushed entry keeps state.pushed -> close stays history.back();
    // a direct load has no state -> close rewrites the URL in place (nowhere of ours to go back to)
    pushed=!!(history.state && history.state.slDrawer && history.state.pushed);
    if(!titleEl.textContent){ var sh=body.querySelector('h1');
      if(sh) titleEl.textContent=(sh.textContent||'').trim(); }
    if(history.replaceState && !(history.state && history.state.slDrawer))
      history.replaceState({slDrawer:ssr, under:window.__slBg}, '', location.pathname+location.search);
  }
})();
</script>
"""
