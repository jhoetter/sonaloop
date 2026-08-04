"""Opt-in product tour: anchored spotlight steps over a real showcase project.

Self-contained (CSS + markup + JS, the _palette.py pattern) and injected on every page —
not by editing _layout but through the public "body_end" slot + register_css, so the
chrome module stays plug-in shaped. Dependency-free vanilla JS: a fixed spotlight ring
(box-shadow scrim) around the current target plus a positioned tooltip card with
title/body, progress dots and Back/Next/Skip; Esc ends the tour.

The steps are declared once in tour_steps() — project URL + selector + i18n'd title/body
(literal t() calls keep the i18n usage scan honest). When the showcase is not yet
loaded, a deliberate tour click POSTs the bundled onboarding example through the same
CSRF-protected route as the empty-home example cards, then resumes on the real project.
After the first navigation the tour stays on the project outline and opens real detail
drawers for each artifact, so Next/Back is local and fast instead of full-page routing.

Triggers — the tour NEVER auto-starts: any element with [data-tour-start] starts it.
The permanent quiet offer is the user-menu row; it replaced the one-time floating offer
toast. The empty-DB first-steps card also shows a prominent "Take the tour" link.
"""
from __future__ import annotations

import json

from .. import config, services
from .._icons import icon as _icon
from ..storage import Store
from ._i18n import t
from ._html import h, raw, register_css
from ._ext import register_slot

SHOWCASE_SLUG = "onboarding-showcase"


def _showcase() -> dict:
    pid = services.stable_id("rproject", "example", SHOWCASE_SLUG)
    return {"slug": SHOWCASE_SLUG, "project_id": pid, "url": f"/jobs/{pid}"}


def tour_steps() -> list[dict]:
    """The anchored showcase walkthrough, in order.

    Keep this as a same-page tour. Most steps spotlight real outline rows without
    opening drawers; only a few detail-heavy artifacts open a drawer. That keeps
    Next/Back responsive while still showing actual project data.
    """
    sc = _showcase()
    url = sc["url"]
    return [
        {"url": url, "sel": ".sl-scaffold__head,.h1", "title": t("tour_project_h"), "body": t("tour_project_d")},
        {"url": url, "sel": ".tour-plan-chip", "title": t("tour_plan_h"), "body": t("tour_plan_d")},
        {"url": url, "sel": ".outline", "title": t("tour_trace_h"), "body": t("tour_trace_d")},
        {"url": url, "sel": '.olrow[data-rkind="open_question"]', "title": t("tour_question_h"), "body": t("tour_question_d")},
        {"url": url, "sel": '.olrow[data-rkind="note"]', "title": t("tour_note_h"), "body": t("tour_note_d")},
        {"url": url, "sel": '.olrow[data-rkind="url_artifact"]', "title": t("tour_reference_h"), "body": t("tour_reference_d")},
        {"url": url, "sel": '.olrow[data-rkind="asset"],.sl-file', "title": t("tour_asset_h"), "body": t("tour_asset_d")},
        {"url": url, "sel": '.olrow[data-rkind="council"]', "open": True, "focus": "#stimmen", "title": t("tour_council_h"), "body": t("tour_council_d")},
        {"url": url, "sel": '.olrow[data-rkind="survey"]', "title": t("tour_survey_h"), "body": t("tour_survey_d")},
        {"url": url, "sel": '.olrow[data-rkind="hypothesis"]', "title": t("tour_hypothesis_h"), "body": t("tour_hypothesis_d")},
        {"url": url, "sel": '.olrow[data-rkind="prototype"]', "title": t("tour_prototype_h"), "body": t("tour_prototype_d")},
        {"url": url, "sel": '.olrow[data-rkind="session"]', "open": True, "focus": "#sec-replay,#sec-statements", "title": t("tour_session_h"), "body": t("tour_session_d")},
        {"url": url, "sel": '.olrow[data-rkind="synthesis"]', "open": True, "focus": "#exec,#verdict,.rp-cover,.syn-main", "title": t("tour_report_h"), "body": t("tour_report_d")},
        {"url": url, "sel": '.olrow[data-rkind="decision"]', "open": True, "focus": "#sec-decision", "title": t("tour_decision_h"), "body": t("tour_decision_d")},
        {"url": url, "sel": ".outline", "title": t("tour_library_h"), "body": t("tour_library_d")},
    ]


def tour_link(extra_class: str = "") -> str:
    """A 'Take the tour' trigger link (home page; prominent variant on the empty DB)."""
    if not config.product_tour_enabled():
        return ""
    return h("a", {"class_": ("tour-take " + extra_class).strip(), "href": "#tour",
                   "data-tour-start": True}, t("tour_take"))


def tour_footer_entry() -> str:
    """Compatibility footer entry helper. The core shell now renders the tour from the user menu."""
    if not config.product_tour_enabled():
        return ""
    return h("button", {"type": "button", "class_": "pi-hover", "data-tour-start": True},
             raw(_icon("compass", animate=True)), h("span", {}, t("tour_take")))


def tour_markup(store: Store | None = None) -> str:
    """Per-request overlay skeleton (hidden) and the localized step/label config as
    JSON — the same seeding pattern as the palette."""
    if not config.product_tour_enabled():
        return ""
    store = store or Store()
    sc = _showcase()
    loaded = store.get_research_project(sc["project_id"]) is not None
    cfg = json.dumps({
        "steps": tour_steps(),
        "sample": {"slug": sc["slug"], "url": sc["url"], "load_url": f"/examples/{sc['slug']}/load",
                   "loaded": loaded},
        "labels": {"next": t("tour_next"), "back": t("tour_back"), "skip": t("tour_skip"),
                   "done": t("tour_done"), "loading": t("tour_loading_sample")},
    })
    overlay = h("div", {"class_": "tourov", "id": "tourov", "hidden": True},
                h("div", {"class_": "tour-ring", "id": "tour-ring"}),
                h("div", {"class_": "tour-card", "id": "tour-card", "role": "dialog",
                          "aria-modal": "false", "aria-label": t("tour_take")}))
    from ._forms import csrf_field
    return (overlay + h("div", {"id": "tour-csrf", "hidden": True}, raw(csrf_field()))
            + h("script", {"id": "tour-cfg", "type": "application/json"}, raw(cfg)))


register_css(r"""
/* ---- product tour (web/_tour.py) ---- */
.tourov[hidden]{display:none}
.tour-ring{position:fixed;z-index:230;border:2px solid var(--accent);border-radius:10px;
  box-shadow:0 0 0 9999px rgba(0,0,0,.5);pointer-events:none;transition:all .22s ease}
.tour-card{position:fixed;z-index:231;width:min(440px,calc(100vw - 24px));background:var(--panel);
  border:1px solid var(--line);border-radius:var(--radius);box-shadow:0 18px 50px rgba(0,0,0,.4);
  padding:14px 16px}
.tour-card h3{margin:0 0 6px;font-size:var(--t-md)}
.tour-card p{margin:0 0 12px;color:var(--muted);font-size:var(--t-body);line-height:1.5}
.tour-foot{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.tour-dots{display:inline-flex;gap:5px;flex:1 0 100%;min-width:0}
.tour-dot{width:7px;height:7px;border-radius:50%;background:var(--line);transition:background .15s}
.tour-dot.on{background:var(--accent)}
.tour-foot .sl-btn{flex:0 0 auto}
.tour-skip{border:0;background:none;color:var(--muted);cursor:pointer;font-size:var(--t-sm);padding:4px 6px;margin-left:auto;white-space:nowrap}
.tour-skip:hover{color:var(--ink)}
.tour-take{font-size:var(--t-sm)}
a.tour-take{color:var(--accent);text-decoration:none}
""")


TOUR_JS = r"""<script>(function(){
var ov=document.getElementById('tourov'); if(!ov) return;
var ring=document.getElementById('tour-ring'), card=document.getElementById('tour-card');
var CFG={steps:[],labels:{}}; try{ CFG=JSON.parse(document.getElementById('tour-cfg').textContent)||CFG; }catch(e){}
var steps=[], i=0, on=false;
var KEY='sl-tour-resume';
var openHref='';
function q(sel){ try{ return document.querySelector(sel); }catch(e){ return null; } }
function esc(s){ return String(s==null?'':s).replace(/[&<>"]/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c];}); }
function cleanUrl(u){ var x; try{x=new URL(u||location.href, location.origin);}catch(e){return String(u||'').split('#')[0];}
  x.hash=''; x.searchParams.delete('d'); return x.pathname+(x.searchParams.toString()?'?'+x.searchParams.toString():''); }
function here(){ return cleanUrl(location.href); }
function same(a,b){ return cleanUrl(a)===cleanUrl(b); }
function go(n){ sessionStorage.setItem(KEY,String(n)); location.href=steps[n].url; }
function resume(){
  var raw=sessionStorage.getItem(KEY); if(raw==null) return;
  var n=parseInt(raw,10); if(isNaN(n)) { sessionStorage.removeItem(KEY); return; }
  steps=CFG.steps||[]; i=Math.max(0,Math.min(n,steps.length-1)); on=true; ov.hidden=false;
  if(steps[i]&&steps[i].url&&!same(here(),steps[i].url)){ go(i); return; }
  sessionStorage.removeItem(KEY); setTimeout(place,80);
}
function loadSampleThenStart(){
  var sample=CFG.sample||{};
  var tokenEl=document.querySelector('#tour-csrf input[name="csrf_token"]');
  var token=tokenEl?tokenEl.value:'';
  card.innerHTML='<h3>'+esc(CFG.labels.loading||'Loading sample project')+'</h3>';
  ov.hidden=false;
  var form=document.createElement('form');
  form.method='post'; form.action=sample.load_url||'/examples/onboarding-showcase/load';
  var input=document.createElement('input'); input.type='hidden'; input.name='csrf_token'; input.value=token;
  form.appendChild(input); document.body.appendChild(form);
  sessionStorage.setItem(KEY,'0'); form.submit();
}
function drawer(){ return document.getElementById('drawer'); }
function closeDrawer(){
  var d=drawer(); if(!d||!d.classList.contains('is-open')) return;
  var b=d.querySelector('[data-drawer-close]'); if(b) b.click();
  openHref='';
}
function targetFor(st, el){
  var d=drawer();
  if(st.open && d && d.classList.contains('is-open')){
    return d.querySelector('.sl-drawer__panel') || d;
  }
  return el;
}
function focusInDrawer(st){
  var d=drawer(); if(!st.open || !st.focus || !d || !d.classList.contains('is-open')) return;
  var f=null; try{ f=d.querySelector(st.focus); }catch(e){}
  if(f && f.scrollIntoView) f.scrollIntoView({block:'center', inline:'nearest'});
}
function visibleRect(el, fullHeight){
  var r=el.getBoundingClientRect(), pad=5;
  var left=Math.max(10, r.left-pad), right=Math.min(window.innerWidth-10, r.right+pad);
  var top=Math.max(10, r.top-pad), bottom=Math.min(window.innerHeight-10, r.bottom+pad);
  var maxH=fullHeight ? (window.innerHeight-20) : Math.min(430, window.innerHeight-40);
  if((bottom-top)>maxH){
    var mid=Math.max(top+maxH/2, Math.min(window.innerHeight/2, bottom-maxH/2));
    top=Math.max(10, mid-maxH/2); bottom=Math.min(window.innerHeight-10, top+maxH);
  }
  return {left:left, top:top, width:Math.max(40,right-left), height:Math.max(40,bottom-top)};
}
function ensureDetail(st, el, tries){
  if(!st.open){ closeDrawer(); return false; }
  var d=drawer(), href=el && el.getAttribute && el.getAttribute('data-drawer');
  if(!href) return false;
  if(d && d.classList.contains('is-open') && openHref===href){
    var ready=targetFor(st, el);
    var rr=ready && ready.getBoundingClientRect ? ready.getBoundingClientRect() : null;
    if(rr && rr.width>0 && rr.height>0) return false;
    if((tries||0)<12){ setTimeout(function(){ ensureDetail(st, el, (tries||0)+1); place(); }, 50); return true; }
    return false;
  }
  if(st._opening===href) return true;
  if(!st._opened || openHref!==href){
    st._opened=true;
    st._opening=href;
    el.click();
    openHref=href;
    setTimeout(function(){ st._opening=''; place(); }, 320);
    return true;
  }
  if((!d || !d.classList.contains('is-open')) && (tries||0)<12){
    setTimeout(function(){ ensureDetail(st, el, (tries||0)+1); place(); }, 50);
    return true;
  }
  return false;
}
function place(){
  var st=steps[i], el=q(st.sel);
  if(!el){ next(1); return; }                            // target vanished mid-tour: auto-skip
  if(ensureDetail(st, el, 0)) return;
  focusInDrawer(st);
  var tgt=targetFor(st, el);
  if(!st.open) tgt.scrollIntoView({block:'center', inline:'nearest'});
  var r=visibleRect(tgt, !!st.open);
  ring.style.left=r.left+'px'; ring.style.top=r.top+'px';
  ring.style.width=r.width+'px'; ring.style.height=r.height+'px';
  var dots=''; for(var d=0;d<steps.length;d++){ dots+='<span class="tour-dot'+(d===i?' on':'')+'"></span>'; }
  var L=CFG.labels;
  card.innerHTML='<h3>'+esc(st.title)+'</h3><p>'+esc(st.body)+'</p>'
    +'<div class="tour-foot"><span class="tour-dots">'+dots+'</span>'
    +(i>0?'<button type="button" class="sl-btn" data-tour-back>'+esc(L.back)+'</button>':'')
    +'<button type="button" class="sl-btn sl-btn--primary" data-tour-next>'
    +esc(i===steps.length-1?L.done:L.next)+'</button>'
    +'<button type="button" class="tour-skip" data-tour-end>'+esc(L.skip)+'</button></div>';
  // card beside the target (right) when it fits, else below — clamped to the viewport
  var cw=Math.min(440, window.innerWidth-24);
  var x=(r.left+r.width+14+cw<=window.innerWidth-10)?(r.left+r.width+14):Math.max(10,Math.min(r.left, window.innerWidth-cw-10));
  var y=(r.left+r.width+14+cw<=window.innerWidth-10)?r.top:(r.top+r.height+12);
  card.style.left=x+'px';
  card.style.top=Math.max(10,Math.min(y, window.innerHeight-(card.offsetHeight||180)-10))+'px';
  var btn=card.querySelector('[data-tour-next]'); if(btn) btn.focus();
}
function next(d){
  var ni=i+d;
  if(ni>=0 && ni<steps.length && steps[ni].url && !same(here(),steps[ni].url)){ go(ni); return; }
  i=ni;
  while(i>=0 && i<steps.length && !q(steps[i].sel)) i+=d;  // tolerate missing targets
  if(i<0) i=0;
  if(i>=steps.length){ end(); return; }
  place();
}
function start(){
  if(CFG.sample && !CFG.sample.loaded){ loadSampleThenStart(); return; }
  steps=CFG.steps||[];
  if(!steps.length) return;
  var pop=document.querySelector('.sl-um-pop'); if(pop) pop.hidden=true;  // leave the settings popover
  i=0; on=true; ov.hidden=false;
  if(steps[0].url && !same(here(),steps[0].url)){ go(0); return; }
  place();
}
function end(){ on=false; ov.hidden=true; sessionStorage.removeItem(KEY); }
document.addEventListener('click',function(e){
  if(e.target.closest&&e.target.closest('[data-tour-start]')){ e.preventDefault(); start(); return; }
  if(!on) return;
  if(e.target.closest&&e.target.closest('[data-tour-next]')){ e.preventDefault(); next(1); return; }
  if(e.target.closest&&e.target.closest('[data-tour-back]')){ e.preventDefault(); next(-1); return; }
  if(e.target.closest&&e.target.closest('[data-tour-end]')){ e.preventDefault(); end(); }
});
window.addEventListener('keydown',function(e){ if(on&&e.key==='Escape'){ e.preventDefault(); end(); } });
window.addEventListener('resize',function(){ if(on) place(); });
document.addEventListener('spa:load',function(){ if(on) place(); });
resume();
})();</script>"""


def _tour_chrome(store: Store | None = None) -> str:
    """Return the complete tour payload, or nothing when the feature is disabled."""
    if not config.product_tour_enabled():
        return ""
    return tour_markup(store) + TOUR_JS


# Injected on every page through the public body_end slot (no _layout edit needed).
register_slot("body_end", _tour_chrome)
