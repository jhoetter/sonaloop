"""Live "agents running" chrome widget (ticket agents-running-panel).

Self-contained (CSS + markup + JS, the _palette.py pattern), rendered by _layout into
the topbar of every page: a status dot + active-run count, with a small flyout listing
the active runs (project, last activity) and a link to the full /runs page. The dot
turns amber when any project is stalled — the silent failure mode must be loud.

Live updates ride the EXISTING SSE stream: _live.py re-dispatches every /api/events
frame as a `sl:live-event` DOM event; this widget debounces those into a refetch of
/api/runs and re-renders itself. Graceful static fallback: without EventSource the
server-rendered state simply stands (the SSR markup is always complete).

This module also owns collect_run_states() — the one read the /runs page, the widget
and /api/runs all share (deliberately NOT importing any page module, so _components
can import this without a cycle)."""
from __future__ import annotations

from typing import Any

from .._icons import icon as _picon     # direct import avoids a cycle (_components imports this module)
from ..storage import Store
from ._i18n import t
from ._html import h, raw, fragment
import contextvars

_RUN_STATES_CACHE: contextvars.ContextVar[dict[str, list[dict[str, Any]]] | None] = \
    contextvars.ContextVar("sonaloop_run_states_cache", default=None)


def begin_run_states_cache() -> contextvars.Token:
    return _RUN_STATES_CACHE.set(None)


def end_run_states_cache(token: contextvars.Token) -> None:
    _RUN_STATES_CACHE.reset(token)


def collect_run_states(store: Store | None = None) -> dict[str, list[dict[str, Any]]]:
    """Every project's run state (services.project_run_state), grouped by state.
    Projects without a plan (state None) are skipped — there is no driver to show.
    Cached per-request so multiple calls within one page render don't re-query."""
    cached = _RUN_STATES_CACHE.get()
    if cached is not None:
        return cached
    from .. import services
    store = store or Store()
    out: dict[str, list[dict[str, Any]]] = {"active": [], "stalled": [], "finished": []}
    for p in store.list_research_projects():
        try:
            rs = services.project_run_state(p["id"], store=store)
        except Exception:
            rs = None
        if not rs or rs.get("state") not in out:
            continue
        out[rs["state"]].append({
            "project_id": p["id"], "title": p["title"], "url": f'/jobs/{p["id"]}',
            "last_activity": rs.get("last_activity", ""),
            "next_ready": rs.get("next_ready") or [], "note": rs.get("note", "")})
    _RUN_STATES_CACHE.set(out)
    return out


def resume_html(note: str) -> str:
    """A stalled run's resume affordance: the run-state note verbatim, with its
    `start_run(...)` call rendered as a copyable snippet (one click → clipboard).
    Shared by the /runs journal rows and the project-header run-chip popover."""
    if "resume with " in note:
        prefix, snippet = note.rsplit("resume with ", 1)
        prefix += "resume with"
    else:
        prefix, snippet = note, ""
    return h("div", {"class_": "run-resume"},
             h("span", {"class_": "muted small"}, prefix),
             raw(str(h("code", {}, snippet))
                 + str(h("button", {"type": "button", "class_": "run-copy", "data-copy": snippet,
                                    "data-copied": t("copied")}, t("copy_btn"))))
             if snippet else None)


def project_run_chip(project_id: str, store: Store) -> str:
    """The project-header run chip (ux-contract §3.5 / decision §7.4): `▶ Run · state`
    in the state's color, opening a small popover with the state, the last activity,
    the next-ready steps or the copyable resume hint, and the /runs journal link.
    '' when the project has no plan — there is no driver to show."""
    from .. import services
    try:
        rs = services.project_run_state(project_id, store=store)
    except Exception:  # noqa: BLE001 — the chip is chrome; never break the page
        rs = None
    if not rs or rs.get("state") not in ("active", "stalled", "finished"):
        return ""
    state = rs["state"]
    label = {"active": t("runs_active_h"), "stalled": t("runs_stalled_h"),
             "finished": t("runs_finished_h")}[state]
    last = (rs.get("last_activity") or "")[:16].replace("T", " ")
    ready = rs.get("next_ready") or []
    btn = h("button", {"type": "button", "class_": f"sl-toolbtn runchip runchip--{state}",
                       "data-runchip-toggle": True, "aria-haspopup": "true",
                       "aria-expanded": "false"},
            raw(_picon("play")), f'{t("run_chip")} · {label}')
    fly = h("div", {"class_": "runchip-fly", "id": "runchip-fly", "hidden": True},
            h("div", {"class_": "runsw-h"}, f'{t("run_chip")} · {label}'),
            # the concept FIRST (§9 V8): one sentence saying what a run even is,
            # before this run's state details
            h("p", {"class_": "runchip-def"}, t("runs_lead")),
            h("div", {"class_": "run-meta"},
              h("span", {"class_": "muted small"},
                f'{t("run_last_activity")}: {last}') if last else None,
              fragment(h("span", {"class_": "muted small"}, f'{t("run_next_ready")}: '),
                       fragment(*(h("span", {"class_": "pill"}, step) for step in ready[:4])))
              if ready else None),
            raw(resume_html(rs["note"])) if state == "stalled" and rs.get("note") else None,
            h("a", {"class_": "runsw-all", "href": "/runs"},
              raw(_picon("arrowRight")), " ", t("runs_view_all")))
    return h("div", {"class_": "runchip-wrap", "id": "runchip"}, btn, fly)


RUNS_WIDGET_CSS = r"""
.runsw{position:relative;display:inline-flex}
.runsw[hidden]{display:none}
/* the topbar runs indicator is a STATUS CHIP ("1 run active" + pulse) — and at zero it is
   not rendered at all ("• 0" taught nothing; ux-contract §9 V7). Shape/hover come from the
   shared .sl-toolbtn contract (W3 one control vocabulary); only the state colours live here. */
.runsw-btn{gap:8px;font-weight:500}
.runsw-dot{flex:none;width:7px;height:7px;border-radius:50%;background:var(--faint)}
.runsw.has-active .runsw-dot{background:var(--green,#34a853);animation:livepulse 1.6s ease-out infinite}
.runsw.has-stalled .runsw-dot{background:var(--amber);animation:none}
.runsw.has-active .runsw-btn{color:var(--green,#34a853);border-color:color-mix(in srgb,var(--green,#34a853) 45%,var(--line))}
.runsw.has-stalled .runsw-btn{color:var(--amber);border-color:color-mix(in srgb,var(--amber) 45%,var(--line))}
.runsw-count{font-variant-numeric:tabular-nums}
.runsw-fly{position:absolute;right:0;top:calc(100% + 8px);width:min(320px,86vw);z-index:160;background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);box-shadow:0 14px 40px rgba(0,0,0,.3);padding:6px}
.runsw-fly[hidden]{display:none}
.runsw-h{font-size:var(--t-xs);color:var(--faint);font-weight:600;letter-spacing:.04em;padding:7px 8px 3px}
.runsw-row{display:flex;align-items:center;gap:9px;padding:7px 8px;border-radius:var(--radius-sm);text-decoration:none;color:var(--ink);font-size:var(--t-body)}
.runsw-row:hover{background:var(--hover)}
.runsw-row .runsw-t{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-weight:500}
.runsw-row .runsw-ts{flex:none;color:var(--muted);font-size:var(--t-sm)}
.runsw-empty{color:var(--muted);font-size:var(--t-sm);padding:10px 8px}
.runsw-all{display:block;text-align:center;font-size:var(--t-sm);color:var(--accent);text-decoration:none;border-top:1px solid var(--line-2);margin-top:4px;padding:7px 8px 4px}
/* ---- project-header run chip (+ popover): the .sl-toolbtn shape family (W3) ---- */
.runchip-wrap{position:relative;display:inline-flex}
.runchip{font-weight:500}
.runchip svg{width:12px;height:12px}
.runchip--active{color:var(--green,#34a853);border-color:color-mix(in srgb,var(--green,#34a853) 45%,var(--line))}
.runchip--stalled{color:var(--amber);border-color:color-mix(in srgb,var(--amber) 45%,var(--line))}
.runchip-fly{position:absolute;left:0;top:calc(100% + 8px);width:min(380px,86vw);z-index:160;background:var(--panel);
  border:1px solid var(--line);border-radius:var(--radius);box-shadow:0 14px 40px rgba(0,0,0,.3);padding:6px 8px 8px}
.sl-tb-actions .runchip-fly{left:auto;right:0}
.runchip-fly[hidden]{display:none}
.runchip-def{margin:2px 0 6px;padding:0 8px;color:var(--muted);font-size:var(--t-sm);line-height:1.5}
.runchip-fly .run-meta{padding:2px 8px}
.runchip-fly .run-resume{padding:4px 8px 2px}
.runchip-fly .run-resume code{font-size:var(--t-sm);background:var(--panel-2);border:1px solid var(--line);border-radius:var(--radius-sm);padding:2px 7px}
"""


def _fly_rows(active: list[dict]) -> str:
    rows = [h("a", {"class_": "runsw-row", "href": r["url"]},
              h("span", {"class_": "runsw-t"}, r["title"]),
              h("span", {"class_": "runsw-ts"}, r["last_activity"][:16].replace("T", " ")))
            for r in active]
    if not rows:
        return h("div", {"class_": "runsw-empty"}, t("runs_none_active"))
    return "".join(rows)


def chip_label(n_active: int, n_stalled: int) -> str:
    """The status-chip text (§9 V7): "1 run active" / "{n} runs active", or the stalled
    read when nothing is active but something hangs. '' at full zero (the chip hides)."""
    if n_active:
        return t("run_active_n", n=n_active)
    if n_stalled:
        return t("run_stalled_n", n=n_stalled)
    return ""


def runs_widget_markup(store: Store) -> str:
    """Per-request widget markup (localised, server-rendered with the current counts —
    the static fallback IS the initial state). JS only mutates it on live events.
    At zero the whole chip is hidden (§9 V7) — the markup still ships so a live event
    can unhide it without a reload."""
    states = collect_run_states(store)
    n_active, n_stalled = len(states["active"]), len(states["stalled"])
    cls = "runsw" + (" has-active" if n_active else "") + (" has-stalled" if n_stalled else "")
    btn = h("button", {"type": "button", "class_": "sl-toolbtn runsw-btn", "data-runsw-toggle": True,
                       "aria-haspopup": "true", "aria-expanded": "false",
                       "title": t("active_runs"), "aria-label": t("active_runs")},
            h("span", {"class_": "runsw-dot"}),
            h("span", {"class_": "runsw-count", "id": "runsw-count"},
              chip_label(n_active, n_stalled)))
    fly = h("div", {"class_": "runsw-fly", "id": "runsw-fly", "hidden": True,
                    "data-empty": t("runs_none_active")},
            h("div", {"class_": "runsw-h"}, t("active_runs")),
            h("div", {"id": "runsw-list"}, raw(_fly_rows(states["active"]))),
            h("a", {"class_": "runsw-all", "href": "/runs"},
              raw(_picon("arrowRight")), " ", t("runs_view_all")))
    return h("div", {"class_": cls, "id": "runsw", "hidden": not (n_active or n_stalled),
                     # the JS re-render composes the localized chip text from these templates
                     "data-l-active-one": t("run_active_n", n=1),
                     "data-l-active-n": t("run_active_n", n="{n}"),
                     "data-l-stalled-one": t("run_stalled_n", n=1),
                     "data-l-stalled-n": t("run_stalled_n", n="{n}")}, btn, fly)


RUNS_WIDGET_JS = r"""<script>(function(){
if(window.__slRunsWidget) return; window.__slRunsWidget=1;
function el(id){ return document.getElementById(id); }
function esc(s){ return String(s==null?'':s).replace(/[&<>"]/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c];}); }
// Delegated toggles: the widgets live inside #main, which SPA navigation replaces.
// Same pattern for the topbar flyout and the project-header run-chip popover.
document.addEventListener('click',function(e){
  var b=e.target.closest&&e.target.closest('[data-runsw-toggle]');
  var fly=el('runsw-fly');
  if(b&&fly){ e.preventDefault(); fly.hidden=!fly.hidden; b.setAttribute('aria-expanded',fly.hidden?'false':'true'); return; }
  if(fly&&!fly.hidden&&!(e.target.closest&&e.target.closest('#runsw'))) fly.hidden=true;
  var c=e.target.closest&&e.target.closest('[data-runchip-toggle]');
  var cfly=el('runchip-fly');
  if(c&&cfly){ e.preventDefault(); cfly.hidden=!cfly.hidden; c.setAttribute('aria-expanded',cfly.hidden?'false':'true'); return; }
  if(cfly&&!cfly.hidden&&!(e.target.closest&&e.target.closest('#runchip'))) cfly.hidden=true;
});
document.addEventListener('keydown',function(e){ if(e.key!=='Escape') return;
  var fly=el('runsw-fly'); if(fly&&!fly.hidden) fly.hidden=true;
  var cfly=el('runchip-fly'); if(cfly&&!cfly.hidden) cfly.hidden=true; });
// Copy-to-clipboard for resume snippets (journal rows + the run-chip popover).
document.addEventListener('click',function(e){
  var b=e.target.closest&&e.target.closest('[data-copy]'); if(!b) return;
  var txt=b.getAttribute('data-copy'), done=b.getAttribute('data-copied')||'';
  function ok(){ var old=b.textContent; b.textContent=done; setTimeout(function(){ b.textContent=old; },1400); }
  if(navigator.clipboard&&navigator.clipboard.writeText){ navigator.clipboard.writeText(txt).then(ok); }
  else{ var ta=document.createElement('textarea'); ta.value=txt; document.body.appendChild(ta);
        ta.select(); try{ document.execCommand('copy'); ok(); }catch(_){ } document.body.removeChild(ta); }
});
if(!window.EventSource) return;   // static fallback: the server-rendered state stands
function render(d){
  var w=el('runsw'), list=el('runsw-list'), cnt=el('runsw-count'); if(!w||!list||!cnt) return;
  var act=d.active||[], st=d.stalled||[];
  // status-chip semantics (V7): hidden at full zero, "N run(s) active" (else stalled) otherwise
  var n=act.length, s=st.length, lbl='';
  if(n) lbl=(n===1)?w.getAttribute('data-l-active-one'):w.getAttribute('data-l-active-n').replace('{n}',n);
  else if(s) lbl=(s===1)?w.getAttribute('data-l-stalled-one'):w.getAttribute('data-l-stalled-n').replace('{n}',s);
  cnt.textContent=lbl||'';
  w.hidden=!(n||s);
  w.classList.toggle('has-active',n>0);
  w.classList.toggle('has-stalled',s>0);
  var html='';
  act.forEach(function(r){ html+='<a class="runsw-row" href="'+esc(r.url)+'">'
    +'<span class="runsw-t">'+esc(r.title)+'</span>'
    +'<span class="runsw-ts">'+esc((r.last_activity||'').slice(0,16).replace('T',' '))+'</span></a>'; });
  if(!html){ var fly=el('runsw-fly'); html='<div class="runsw-empty">'+esc(fly?fly.getAttribute('data-empty'):'')+'</div>'; }
  list.innerHTML=html;
}
var t=null;
document.addEventListener('sl:live-event',function(){
  clearTimeout(t); t=setTimeout(function(){
    fetch('/api/runs').then(function(r){return r.json();}).then(render).catch(function(){});
  },400);
});
})();</script>"""
