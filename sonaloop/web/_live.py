"""Live event stream client: the inspector updates beside the recording agent.

Self-contained (CSS + markup + JS, the _palette.py pattern), injected once by
_layout so every page is live. An EventSource on /api/events (the SSE tail of the
cross-process bus, services._events) drives two behaviours:

  1. a subtle activity toast bottom-right ("Council recorded · <prompt> · open")
     linking to the entity, on every event;
  2. a full reload (it's SSR — cheap and always consistent) when the event concerns
     what's on screen: the event's URL, entity id or project id appears in the path.

EventSource reconnects automatically and re-sends Last-Event-ID, so a laptop nap or
server restart replays the missed rows from the capped table. Vanilla JS only."""
from __future__ import annotations

import json

from ._i18n import t
from ._html import h, raw


def event_labels() -> dict[str, str]:
    """Localised short labels for every catalogued lifecycle event — shared by the
    toast (seeded as JSON per request) and the /activity feed. Literal t() calls so
    the i18n parity scan sees every key."""
    return {
        "persona.created": t("evt_persona_created"),
        "persona.updated": t("evt_persona_updated"),
        "evidence.attached": t("evt_evidence_attached"),
        "persona.grounded": t("evt_persona_grounded"),
        "chat.recorded": t("evt_chat_recorded"),
        "day.recorded": t("evt_day_recorded"),
        "prediction.scored": t("evt_prediction_scored"),
        "calibration.round_recorded": t("evt_calibration_round_recorded"),
        "asset.attached": t("evt_asset_attached"),
        "council.recorded": t("evt_council_recorded"),
        "synthesis.recorded": t("evt_synthesis_recorded"),
        "project.created": t("evt_project_created"),
        "project.updated": t("evt_project_updated"),
        "run.finished": t("evt_run_finished"),
    }


LIVE_CSS = r"""
.live-toast{position:fixed;right:18px;bottom:18px;z-index:190;display:flex;align-items:center;gap:10px;max-width:min(440px,calc(100vw - 36px));background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);box-shadow:0 12px 36px rgba(0,0,0,.3);padding:10px 14px;font-size:var(--t-body);color:var(--ink);opacity:0;transform:translateY(6px);transition:opacity .18s,transform .18s;pointer-events:none}
.live-toast.show{opacity:1;transform:none;pointer-events:auto}
.live-dot{flex:none;width:7px;height:7px;border-radius:50%;background:var(--green,#34a853);animation:livepulse 1.6s ease-out infinite}
@keyframes livepulse{0%{box-shadow:0 0 0 0 rgba(52,168,83,.4)}70%{box-shadow:0 0 0 7px rgba(52,168,83,0)}100%{box-shadow:0 0 0 0 rgba(52,168,83,0)}}
.live-msg{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.live-msg .muted{color:var(--muted)}
.live-toast a{flex:none;color:var(--accent);text-decoration:none;font-weight:600}
"""


def live_markup() -> str:
    """Per-request toast markup (hidden until an event arrives) + the localised
    event-label table as JSON config — same seeding pattern as the palette."""
    cfg = json.dumps({"labels": event_labels()})
    toast = h("div", {"class_": "live-toast", "id": "live-toast", "role": "status", "aria-live": "polite"},
              h("span", {"class_": "live-dot"}),
              h("span", {"class_": "live-msg", "id": "live-msg"}),
              h("a", {"id": "live-link", "href": "/activity"}, t("open")))
    return toast + h("script", {"id": "live-cfg", "type": "application/json"}, raw(cfg))


LIVE_JS = r"""<script>(function(){
if(!window.EventSource) return;
var toast=document.getElementById('live-toast'); if(!toast) return;
var msg=document.getElementById('live-msg'), link=document.getElementById('live-link');
var CFG={labels:{}}; try{ CFG=JSON.parse(document.getElementById('live-cfg').textContent)||CFG; }catch(e){}
var hideT=null, reloadT=null;
function show(text,sub,url){
  msg.textContent=''; msg.appendChild(document.createTextNode(text));
  if(sub){ var s=document.createElement('span'); s.className='muted'; s.textContent=' · '+sub; msg.appendChild(s); }
  link.href=url||'/activity';
  toast.classList.add('show');
  clearTimeout(hideT); hideT=setTimeout(function(){ toast.classList.remove('show'); },6000);
}
// Does the event concern what's on screen? The SSR path carries the ids: the event's
// own URL, its entity id, or its project id appearing in the path means stale content.
function concerns(d){
  var p=location.pathname;
  if(p==='/activity') return true;
  if(d.url && d.url!=='/jobs' && (p===d.url||p.indexOf(d.url+'/')===0)) return true;
  if(d.entity_id && p.indexOf(d.entity_id)>=0) return true;
  if(d.project_id && p.indexOf(d.project_id)>=0) return true;
  return false;
}
var es=new EventSource('/api/events');   // auto-reconnects; replays via Last-Event-ID
es.onmessage=function(ev){
  var d; try{ d=JSON.parse(ev.data); }catch(e){ return; }
  // Re-dispatch as a DOM event so OTHER chrome modules (e.g. the runs widget) ride
  // this one EventSource instead of opening their own connection.
  try{ document.dispatchEvent(new CustomEvent('sl:live-event',{detail:d})); }catch(e){}
  // A generated deliverable is the result of the user's export action, not new incoming
  // evidence that needs inspection. The browser download is already the feedback; showing
  // an "Asset attached · Open" toast sends customers to the internal provenance surface.
  if(d.event==='asset.attached' && d.direction==='out') return;
  show(CFG.labels[d.event]||d.event, d.label||'', d.url);
  if(concerns(d)){ clearTimeout(reloadT); reloadT=setTimeout(function(){ location.reload(); },900); }
};
})();</script>"""
