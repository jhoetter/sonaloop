"""Usability-session pages: list (+ cross-session funnel) and the replay view — walk the dual
timeline of one recorded session (ticket session-replay-inspector). The session is the deliverable;
this is where you consume it: one row per step (screen panel ⇄ action/think-aloud), friction layered
via the data-driven scale colors, per-step verdicts, and a friction rail that jumps to `#step-N`.
Screenshots are served read-only from data/sessions/ via /sessions-files (traversal-safe)."""
from __future__ import annotations

from pathlib import Path

from fastapi.responses import FileResponse, Response

from ._ctx import *  # noqa: F401,F403  (shared render toolkit)
from .. import ui
from .._render import render_ref, render_statements
from .._synthesis import _stacked, _legend
from .._html import register_css
from ... import artifacts as _A
from ... import config as _config


# Co-located CSS: the dual-timeline replay (screen ⇄ action), friction rail, outcome banner, funnel.
# Friction accent rides on --sfc (set per step from friction_levels.json presentation.color); the
# targeted step highlights via pure CSS :target — no JS.
register_css(r"""
.sess-banner{display:flex;align-items:center;gap:10px;border:1px solid var(--line);border-left:3px solid var(--sbc,var(--line));border-radius:var(--radius);background:var(--panel);padding:10px 14px;margin:0 0 18px;font-size:var(--t-body)}
.sess-banner svg{width:16px;height:16px;flex:none;color:var(--sbc,var(--muted))}
.sess-rail{border:1px solid var(--line);border-radius:var(--radius);background:var(--panel);padding:12px 15px;margin:0 0 18px}
.sess-rail-h{font-size:var(--t-xs);text-transform:uppercase;letter-spacing:.05em;color:var(--muted);font-weight:600;margin:0 0 8px}
.sess-rail a{display:flex;align-items:center;gap:9px;padding:5px 0;color:var(--ink);text-decoration:none;font-size:var(--t-sm);border-bottom:1px solid var(--line-2)}
.sess-rail a:last-child{border-bottom:0}
.sess-rail a:hover .sess-rail-note{color:var(--accent)}
.sess-rail-note{color:var(--muted);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;min-width:0;flex:1}
.sess-steps{display:flex;flex-direction:column;gap:14px}
.sess-step{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);border:1px solid var(--line);border-left:3px solid var(--sfc,var(--line));border-radius:var(--radius);background:var(--panel);overflow:hidden;scroll-margin-top:72px}
.sess-step:target{border-color:var(--accent);box-shadow:0 0 0 3px var(--accent-weak)}
.sess-screen{background:var(--panel-2);border-right:1px solid var(--line);padding:13px 15px;display:flex;flex-direction:column;gap:8px;min-width:0}
.sess-shot{display:block;max-width:100%;border:1px solid var(--line);border-radius:var(--radius-sm)}
.sess-screen-txt{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:var(--t-sm);line-height:1.5;white-space:pre-wrap;border:1px dashed var(--line);border-radius:var(--radius-sm);background:var(--panel);padding:10px 12px;max-height:230px;overflow:auto}
.sess-cap{color:var(--muted);font-size:var(--t-xs);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.sess-act{padding:13px 15px;display:flex;flex-direction:column;gap:9px;min-width:0}
.sess-act-h{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.sess-n{flex:none;width:22px;height:22px;border-radius:50%;background:var(--accent-weak);color:var(--accent);font-size:var(--t-xs);font-weight:700;display:flex;align-items:center;justify-content:center}
.sess-target{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:var(--t-sm);color:var(--muted);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.sess-detail{color:var(--muted);font-size:var(--t-sm);margin:0}
.sess-mono{margin:0;border-left:3px solid var(--line-2);padding:2px 0 2px 12px;font-style:italic;font-size:var(--t-body);line-height:1.6;max-width:var(--measure-prose)}
.sess-foot{display:flex;align-items:center;gap:8px;flex-wrap:wrap;font-size:var(--t-sm);color:var(--muted);margin-top:auto}
.sess-funnel{border:1px solid var(--line);border-radius:var(--radius);background:var(--panel);padding:14px 16px;margin:0 0 18px}
.sess-funnel h2{margin:0 0 2px;font-size:var(--t-body)}
.sess-frow{display:grid;grid-template-columns:90px 1fr 140px;gap:12px;align-items:center;padding:6px 0;font-size:var(--t-sm)}
.sess-frow .sfl{color:var(--muted)}
.sess-frow .sfn{text-align:right;color:var(--muted);font-variant-numeric:tabular-nums}
.sess-freason{grid-column:2/-1;color:var(--muted);font-size:var(--t-xs);padding:0 0 4px}
@media(max-width:760px){.sess-step{grid-template-columns:1fr}.sess-screen{border-right:0;border-bottom:1px solid var(--line)}}
/* ---- step-shot lightbox + the first/last shot strip on session rows (ux-contract §9 V4) ---- */
.sl-shotlink{display:block;cursor:zoom-in}
.sl-shotlink:hover .sess-shot{border-color:var(--accent)}
.sl-shotstrip{display:flex;gap:7px;margin:4px 0 10px;flex-wrap:wrap}
.sl-shotstrip .sl-shotlink{cursor:zoom-in}
.sl-shotstrip img{display:block;height:54px;width:auto;max-width:120px;object-fit:cover;object-position:top;
  border:1px solid var(--line);border-radius:var(--radius-sm);background:var(--panel-2)}
.sl-shotstrip .sl-shotlink:hover img{border-color:var(--accent)}
/* W8 stacking/containment: the dialog is a CONTAINED panel (frame, padding, shadow) — a
   chrome-less 94vw screenshot OF the prototype was indistinguishable from the live iframe
   escaping over the dialog. position:fixed + z-index guard the paint order even on any
   non-top-layer path (showModal-less fallback); the body scroll-locks while open so the
   real iframe can't slide beneath the overlay. */
.sl-lightbox{position:fixed;inset:0;margin:auto;width:fit-content;height:fit-content;
  z-index:200;border:1px solid var(--line);border-radius:var(--radius-lg);background:var(--panel);
  padding:10px;box-shadow:0 24px 70px rgba(0,0,0,.5);max-width:92vw;max-height:92vh;overflow:visible}
.sl-lightbox::backdrop{background:rgba(0,0,0,.74)}
.sl-lightbox img{display:block;max-width:min(1100px,88vw);max-height:80vh;border:1px solid var(--line);
  border-radius:var(--radius-sm);background:var(--panel);cursor:zoom-out}
body:has(.sl-lightbox[open]){overflow:hidden}
/* visible close × + step caption (round-3 H6) — Esc / click-out unchanged */
.sl-lb-fig{margin:0;position:relative}
.sl-lb-close{position:absolute;top:-22px;right:-22px;width:30px;height:30px;border-radius:50%;
  border:1px solid var(--line);background:var(--panel);color:var(--ink);font-size:17px;line-height:1;
  cursor:pointer;display:flex;align-items:center;justify-content:center;padding:0;
  box-shadow:0 2px 8px rgba(0,0,0,.25)}
.sl-lb-close:hover{background:var(--panel-2)}
.sl-lb-cap{margin-top:8px;text-align:center;color:var(--muted);font-size:var(--t-sm)}
""")


# The minimal image lightbox (ux-contract §9 V4): every [data-lightbox] anchor opens its href
# (the full-resolution step shot) in a native <dialog> built lazily ON FIRST USE — Esc and any
# click close it, and a visible close × plus a small step/action caption make both discoverable
# (round-3 H6: data-caption on the anchor feeds the caption). Without JS the anchor simply opens
# the file. Idempotent (the window flag), so the script may ride along with every surface that
# renders shots (detail page, slide-over fragments re-execute their scripts, the prototype strip).
# W8 stacking contract: the dialog must be a DIRECT child of <body> when shown (re-appended if a
# fragment swap detached it) and opens through showModal() — the TOP LAYER, above the page, the
# slide-over and any iframe; where showModal is unavailable the [open] attribute + the fixed
# z-indexed .sl-lightbox CSS keep it above everything anyway.
LIGHTBOX_JS = """<script>(function(){
if(window.__slLightbox) return; window.__slLightbox=1;
document.addEventListener('click',function(e){
  var a=e.target.closest&&e.target.closest('[data-lightbox]'); if(!a) return;
  e.preventDefault();
  var dlg=document.getElementById('sl-lightbox');
  if(!dlg){
    dlg=document.createElement('dialog'); dlg.id='sl-lightbox'; dlg.className='sl-lightbox';
    var fig=document.createElement('figure'); fig.className='sl-lb-fig';
    fig.appendChild(document.createElement('img'));
    var x=document.createElement('button'); x.type='button'; x.className='sl-lb-close';
    x.setAttribute('aria-label','Close'); x.textContent='\\u00d7';
    fig.appendChild(x);
    var cap=document.createElement('figcaption'); cap.className='sl-lb-cap';
    fig.appendChild(cap);
    dlg.appendChild(fig);
    dlg.addEventListener('click',function(){ if(dlg.close) dlg.close(); else dlg.removeAttribute('open'); });
  }
  if(!dlg.isConnected||dlg.parentNode!==document.body) document.body.appendChild(dlg);
  var img=dlg.querySelector('img'), thumb=a.querySelector('img'), cap=dlg.querySelector('.sl-lb-cap');
  img.src=a.getAttribute('href'); img.alt=(thumb&&thumb.alt)||'';
  cap.textContent=a.getAttribute('data-caption')||(thumb&&thumb.alt)||'';
  cap.style.display=cap.textContent?'':'none';
  if(dlg.showModal){ if(!dlg.open) dlg.showModal(); }
  else dlg.setAttribute('open','');
});
})();</script>"""


# Action type → icon (the recorder's code enum; see services._usability_sessions._ACTION_TYPES).
# The chip label resolves through i18n (t("action_" + type)) only for known enum members — an
# off-enum compatibility token renders verbatim instead of painting a raw i18n key.
_ACTION_ICONS = {"look": "eye", "click": "target", "type": "pencil", "select": "check",
                 "scroll": "sort", "key": "command", "navigate": "compass", "back": "back",
                 "wait": "clock", "give_up": "flag"}
_FIDELITY_COLORS = {"artifact": "var(--muted)", "prototype": "var(--accent)", "live": "var(--green)"}


def _action_chip(action: dict) -> str:
    typ = action.get("type") or ""
    label = t("action_" + typ) if typ in _ACTION_ICONS else typ
    return h("span", {"class_": "lbl lbl-soft"},
             raw(_icon(_ACTION_ICONS.get(typ, "dot"))), " ", label)


def _fidelity_chip(fidelity: str) -> str:
    label = t("fidelity_" + fidelity) if fidelity in _FIDELITY_COLORS else fidelity
    return _label(label, _FIDELITY_COLORS.get(fidelity, "var(--muted)"))


def _friction_meta(level: str) -> dict | None:
    """The scale record ({term,value,label_key,color}) for a stored canonical friction level."""
    return next((r for r in _A.friction_terms() if r["term"] == level), None)


def _outcome_chip(sess: dict) -> str:
    out = sess.get("outcome") or {}
    if out.get("completed"):
        return _label(t("completed"), "var(--green)")
    return _label(t("outcome_dropped", n=out.get("dropoff_step", 0)), "var(--red)")


def _friction_count(sess: dict) -> int:
    return sum(1 for s in sess.get("steps") or []
               if ((_friction_meta((s.get("friction") or {}).get("level", "")) or {}).get("value", 0)) > 0)


def _verdict_chip(verdict: dict) -> str:
    cont = bool(verdict.get("would_continue"))
    chip = _label(t("verdict_continue") if cont else t("verdict_drop"),
                  "var(--green)" if cont else "var(--red)")
    reason = (verdict.get("reason") or "").strip()
    return fragment(raw(chip), h("span", {}, reason) if reason else None)


def _subject_link(store: Store, subject: dict):
    """The subject as a link: prototype/flow artifacts → the prototype page (when stored), a live
    URL → the external target; plain label otherwise."""
    label = subject.get("label") or subject.get("id") or subject.get("url") or "—"
    if subject.get("id"):
        proto = store.get_prototype(subject["id"])
        if proto:
            return h("a", {"href": f'/prototypes/{proto["slug"]}'}, label)
    if subject.get("url"):
        return h("a", {"href": subject["url"], "target": "_blank", "rel": "noopener"},
                 label, " ", raw(_icon("external")))
    return h("span", {}, label)


def _screenshot_url(sess_id: str, shot: str) -> str | None:
    """Resolve a stored screenshot reference to a servable URL.

    Shared row-tenancy deliberately exposes neither runtime-file route, so fail
    before probing the filesystem. Local/single-tenant mode keeps the historical
    resolution order and static URLs.
    """
    if _config.postgres_row_tenancy_enabled():
        return None
    sessions_root = _config.sessions_dir().resolve()
    data_root = _config.partition_dir().resolve()
    p = Path(shot)
    candidates = ([p] if p.is_absolute() else
                  [_config.sessions_dir() / sess_id / p, _config.sessions_dir() / p,
                   _config.partition_dir() / p])
    for c in candidates:
        try:
            r = c.resolve()
        except OSError:
            continue
        if not r.is_file():
            continue
        if r.is_relative_to(sessions_root):
            return "/sessions-files/" + r.relative_to(sessions_root).as_posix()
        if r.is_relative_to(data_root):
            return "/data/" + r.relative_to(data_root).as_posix()
    return None


def _persona_chip(store: Store, persona_id: str):
    # The session's subject in the detail header — the avatar rides the ONE avatar_group
    # anatomy (ux-contract §10 W11): a group of one, identical classes to every other kind.
    p = store.get_persona(persona_id)
    if p:
        return h("a", {"href": f'/personas/{p["id"]}', "class_": "turn-who"},
                 ui.avatar_group([p], size=22), h("b", {}, p["display_name"]))
    return h("span", {"class_": "turn-who"}, h("b", {}, persona_id or "—"))


# ---------------------------------------------------------------- prototype reaction sessions
# A protosession_* record (record_prototype_session) is the OTHER first-class session kind
# (ux-contract §8.2 — sessions are explicitly first-class): same step shape as a usability
# session (index/action/monologue/state/friction/verdict), but the steps live under
# reaction.steps and the walked subject is always its prototype. The vm maps it onto the ONE
# session row vocabulary (ui.primitive_row §3.2) so the Library tab, the prototype page and
# the slide-over render identical rows; the detail route below reuses the SAME step renderer.


def proto_session_vm(sess: dict, store: Store) -> dict:
    """A prototype session in the usability-session record shape the row vocabulary reads:
    subject = the prototype, steps = reaction.steps, fidelity = the prototype rung."""
    r = sess.get("reaction") if isinstance(sess.get("reaction"), dict) else {}
    proto = store.get_prototype(sess.get("prototype_id", "")) or {}
    return {"id": sess["id"], "persona_id": sess.get("persona_id", ""),
            "subject": {"kind": "prototype", "id": proto.get("id") or sess.get("prototype_id", ""),
                        "label": proto.get("name") or sess.get("prototype_id", "")},
            "fidelity": "prototype", "steps": r.get("steps") or _timeline_steps(r.get("timeline")),
            "grounded_verified": sess.get("grounded_verified"),
            "created_at": sess.get("created_at", ""), "date": sess.get("date", ""),
            "project_id": proto.get("project_id"), "outcome": {"summary": r.get("summary", "")}}


def proto_session_rows(store: Store, project_id: str | None = None,
                       prototype_id: str | None = None) -> list[dict]:
    """The prototype sessions as session vms (newest first), optionally narrowed to one project
    (via the owning prototype) or one prototype — the Library Sessions tab merges these with the
    usability sessions so EVERY recorded session is one reachable row."""
    vms = [proto_session_vm(s, store)
           for s in store.list_prototype_sessions(prototype_id=prototype_id)]
    if project_id:
        vms = [v for v in vms if v.get("project_id") == project_id]
    return vms


# reaction.timeline is the OTHER authored walk shape (record_prototype_session accepts the
# reaction free-form, and agents author these keys in either language): per entry the narration
# lives under monologue|monolog, the observed screen under observed|beobachtung|screen.
_TL_MONOLOGUE_KEYS = ("monologue", "monolog")
_TL_OBSERVED_KEYS = ("observed", "beobachtung", "screen")


def _timeline_steps(timeline) -> list[dict]:
    """Adapt a free-form `reaction.timeline` onto the steps contract the replay renderer reads
    (§9 V4 root cause: half the showcase's prototype reactions recorded their walk HERE, not
    under reaction.steps — the replay rendered nothing and every retained step-<n>.png stayed
    invisible). Index comes from the authored `step` number (falling back to the position), the
    action stays free text (no typed chip), narration/observed-state map onto monologue/screen."""
    if not isinstance(timeline, list):
        return []
    steps = []
    for pos, entry in enumerate(e for e in timeline if isinstance(e, dict)):
        try:
            idx = int(str(entry.get("step", pos)).strip())
        except (TypeError, ValueError):
            idx = pos
        monologue = next((entry[k] for k in _TL_MONOLOGUE_KEYS if entry.get(k)), "")
        observed = next((entry[k] for k in _TL_OBSERVED_KEYS if entry.get(k)), "")
        steps.append({"index": idx, "action": {"detail": str(entry.get("action") or "")},
                      "monologue": str(monologue), "state": {"screen": str(observed)}})
    return steps


def _proto_step_shim(sess: dict) -> dict:
    """The {id, steps} shim _step_html/_friction_rail read: reaction.steps, else the adapted
    reaction.timeline (_timeline_steps), enriched with the harness's on-disk screenshot
    convention (data/sessions/<browser session_id>/step-<n>.png) — the id is the BROWSER
    session dir, so _screenshot_url resolves the file when it exists and the step falls back
    to its recorded screen text when it doesn't. The enrichment also repairs an explicitly
    stored empty screenshot (key present but None/'' — setdefault missed those)."""
    r = sess.get("reaction") if isinstance(sess.get("reaction"), dict) else {}
    steps = []
    for st in r.get("steps") or _timeline_steps(r.get("timeline")):
        st = dict(st)
        state = dict(st.get("state") or {})
        if not state.get("screenshot"):
            state["screenshot"] = f'step-{st.get("index", 0)}.png'
        st["state"] = state
        steps.append(st)
    return {"id": sess.get("session_id") or sess["id"], "steps": steps}


def session_shot_strip(sess: dict) -> str:
    """The small first/last step-shot strip a session row carries on the prototype page
    (ux-contract §9 V4): up to two resolvable screenshots as thumbnails, each opening the
    lightbox (no-JS: the file itself). Handles BOTH session kinds — a prototype reaction
    resolves through the shim (browser-session dir convention), a usability walk through its
    own stored step screenshots. '' when no step file resolves."""
    if isinstance(sess.get("reaction"), dict):
        shim = _proto_step_shim(sess)
    else:
        shim = {"id": sess["id"], "steps": sess.get("steps") or []}
    shots = []
    for st in shim["steps"]:
        state = st.get("state") or {}
        if not state.get("screenshot"):
            continue
        url = _screenshot_url(shim["id"], state["screenshot"])
        if url:
            shots.append((st.get("index", 0), url, state.get("title") or ""))
    if not shots:
        return ""
    picks = shots[:1] if len(shots) == 1 else [shots[0], shots[-1]]
    thumbs = [h("a", {"class_": "sl-shotlink", "href": url, "data-lightbox": True,
                      "data-caption": t("step_n", n=i), "title": t("step_n", n=i)},
               h("img", {"src": url, "alt": title or t("step_n", n=i), "loading": "lazy"}))
              for i, url, title in picks]
    return h("div", {"class_": "sl-shotstrip"}, fragment(*thumbs))


def _predicted_behaviors_html(behaviors: list, store: Store) -> str:
    """The session's falsifiable output (predicted_behaviors): one row per prediction —
    the labeled likelihood (% + mini-bar via the vendored `.sl-likelihood` contract, V3:
    never a bare "0.6" chip) · the expected action · its trigger · evidence refs. '' when
    none."""
    if not behaviors:
        return ""
    rows = []
    for b in behaviors:
        refs = fragment(*(raw(render_ref(r, store)) for r in (b.get("refs") or [])))
        rows.append(h("div", {"class_": "hyp"},
                      h("div", {}, ui.likelihood(b.get("likelihood")), " ",
                        h("b", {}, b.get("action", ""))),
                      (h("p", {"class_": "muted small"}, b["trigger"]) if b.get("trigger") else None),
                      (h("p", {"class_": "muted small turn-refs"}, refs) if b.get("refs") else None)))
    return h("div", {"class_": "sec", "id": "sec-predicted"},
             h("h2", {}, t("predicted_behaviors_h"), h("span", {"class_": "h1cnt"}, str(len(behaviors)))),
             fragment(*rows))


def _proto_session_detail(store: Store, sess: dict) -> str:
    """The prototype session's full detail page — the SAME anatomy and step renderer as the
    usability replay (one session concept, two recorders): persona + prototype header with the
    verified badge, verdict lead, liked/friction reads, the per-step timeline (monologue +
    screenshots from the retained browser-session dir), predicted behaviors."""
    r = sess.get("reaction") if isinstance(sess.get("reaction"), dict) else {}
    proto = store.get_prototype(sess.get("prototype_id", "")) or {}
    proj = (store.get_research_project(proto["project_id"]) if proto.get("project_id") else None)
    title = proto.get("name") or sess.get("prototype_id", sess["id"])
    grounded = sess.get("grounded_verified")
    proto_link = (h("a", {"href": f'/prototypes/{proto["slug"]}'}, title) if proto.get("slug")
                  else h("span", {}, title))
    # meta line (V5: plain text, no pill-soup): persona · session kind · date — "Janine Wolf ·
    # Prototyp-Session · 12 Jun". The fidelity pill was redundant with the eyebrow/properties,
    # and the date is meta text, not a status.
    session_day = (ui.fmt_day(sess.get("date") or "") if sess.get("date")
                   else ui.local_day(sess.get("created_at", "")))
    sub = h("span", {"class_": "syn-meta"},
            _persona_chip(store, sess.get("persona_id", "")),
            h("span", {"class_": "muted"},
              f' · {t("session_kind_prototype")} · ', session_day))
    shim = _proto_step_shim(sess)
    steps = shim["steps"]
    verdict_html = (raw(_study_lead(ui.clamp(raw(_md(r["verdict"])), threshold=ui.SECTION_CLAMP),
                                    t("verdict_h"), qid="sec-verdict"))
                    if (r.get("verdict") or "").strip() else "")
    def _read_list(sid: str, heading: str, items: list) -> str:
        if not items:
            return ""
        return h("div", {"class_": "sec", "id": sid},
                 h("h2", {}, heading, h("span", {"class_": "h1cnt"}, str(len(items)))),
                 fragment(*(h("p", {"class_": "small"}, x) for x in items)))
    liked_html = _read_list("sec-liked", t("proto_liked_h"), r.get("liked") or [])
    friction_html = _read_list("sec-friction", t("friction_rail_h"), r.get("friction") or [])
    timeline = ""
    if steps:
        timeline = h("div", {"class_": "sec", "id": "sec-replay"},
                     h("h2", {}, t("replay_h"), h("span", {"class_": "h1cnt"}, str(len(steps)))),
                     h("div", {"class_": "sess-steps"},
                       fragment(*(_step_html(shim, s) for s in steps))))
    predicted_html = _predicted_behaviors_html(r.get("predicted_behaviors") or [], store)
    body = fragment(verdict_html, liked_html, friction_html, timeline, raw(predicted_html),
                    raw(LIGHTBOX_JS) if timeline else None)
    # Project-rooted crumb (§8.2 — the council pattern); the kind root stays only for
    # orphan records that have no project to live under.
    crumbs = ([(t("projects"), "/jobs"), (proj["title"], f'/jobs/{proj["id"]}')]
              if proj else [(t("sessions"), "/sessions")])
    crumbs.append((_display_title(title), None))
    # Rail order is the §8.2 anatomy: project → kind-specifics → dates; the prototype row
    # is ONE prototype (singular label).
    prop_rows = [
        ("projects", t("project"),
         h("a", {"href": f'/jobs/{proj["id"]}'}, proj["title"]) if proj else ""),
        *detail_form_rows("session", proto_session_vm(sess, store)),
        ("square", t("fidelity"), raw(_fidelity_chip("prototype"))),
        ("prototype", t("prototype_kind"), proto_link),
        ("plan", t("steps_h"), str(len(steps)) if steps else ""),
        ("check", t("grounding_h"),
         raw(_label(t("grounded_yes") if grounded else t("grounded_no"),
                    "var(--green)" if grounded else "var(--muted)")) if grounded is not None else ""),
        ("dot", t("created"), ui.local_date(sess.get("created_at") or "")),
    ]
    rail_sections = ([("sec-verdict", t("verdict_h"))] if verdict_html else []) \
        + ([("sec-liked", t("proto_liked_h"))] if liked_html else []) \
        + ([("sec-friction", t("friction_rail_h"))] if friction_html else []) \
        + ([("sec-replay", t("replay_h"))] if timeline else []) \
        + ([("sec-predicted", t("predicted_behaviors_h"))] if predicted_html else [])
    pills = [_label(t("grounded_yes"), "var(--green)")] if grounded else []
    return detail_page(
        store, title=_display_title(title), crumbs=crumbs,
        # G5: the sidebar follows the crumb root — Projects when project-rooted, Library for orphans
        active="projects" if proj else "library",
        hero=_hero(title, icon="activity", sub=sub, hid="sec-head",
                   top=detail_eyebrow(t("session_kind_prototype"), pills)),
        body=body, prop_rows=prop_rows,
        rel_study_id=f"session:{sess['id']}", rel_proj_id=proto.get("project_id") or None,
        rail_sections=rail_sections,
        star=("session", sess["id"], str(title)[:60], f'/sessions/{sess["id"]}'))


def _session_row(s: dict, store: Store) -> str:
    """One list row: persona avatar chip · subject label · outcome · friction count · date
    (progressive disclosure — the replay itself lives on the detail page; V2 capped the row
    at ≤2 chips, so the fidelity tag lives in the detail properties)."""
    p = store.get_persona(s.get("persona_id", ""))
    av = _avatar(p or {"display_name": s.get("persona_id", "?"), "id": s.get("persona_id", "x")}, 22)
    n_fr = _friction_count(s)
    right = fragment(
        raw(_outcome_chip(s)),
        raw(_label(t("friction_n", n=n_fr), "var(--amber)")) if n_fr else None,
        h("span", {}, (ui.fmt_day(s.get("date") or "") if s.get("date")
                        else ui.local_day(s.get("created_at", "")))),
        raw(_star("session", s["id"], (s.get("subject") or {}).get("label", "")[:60], f'/sessions/{s["id"]}')))
    sub = (p or {}).get("display_name") or s.get("persona_id", "")
    return h("a", {"class_": "row", "href": f'/sessions/{s["id"]}'}, av,
             h("span", {"class_": "title"}, (s.get("subject") or {}).get("label", "—"),
               h("span", {"class_": "muted small"}, f" · {sub}") if sub else None),
             h("span", {"class_": "right"}, right))


def _funnel_html(funnel: dict) -> str:
    """The cross-session funnel for ONE subject (services.get_session_funnel): per step a
    continued/dropped bar against the entered count, with the drop reasons under the row."""
    rows = []
    mx = max((r["entered"] for r in funnel["rows"]), default=0) or 1
    for r in funnel["rows"]:
        parts = [(r["continued"], "var(--green)", t("funnel_continued")),
                 (r["dropped"], "var(--red)", t("funnel_dropped"))]
        bar = h("div", {"style": f'max-width:{r["entered"] / mx * 100:.1f}%'}, _stacked(parts, thin=True))
        rows.append(h("div", {"class_": "sess-frow"},
                      h("span", {"class_": "sfl"}, t("step_n", n=r["step"])), bar,
                      h("span", {"class_": "sfn"},
                        f'{r["entered"]} {t("funnel_entered")} · {r["dropped"]} {t("funnel_dropped")}')))
        for reason in r.get("drop_reasons", []):
            rows.append(h("div", {"class_": "sess-frow"}, h("span", {}),
                          h("span", {"class_": "sess-freason"}, raw(_icon("warning")), " ", reason)))
    legend = _legend([(funnel["completed"], "var(--green)", t("funnel_continued")),
                      (funnel["sessions"] - funnel["completed"], "var(--red)", t("funnel_dropped"))])
    return h("div", {"class_": "sess-funnel", "id": "funnel"},
             h("h2", {}, t("funnel_h"), " · ", (funnel.get("subject") or {}).get("key", "")),
             h("p", {"class_": "ihint"}, t("funnel_hint", n=funnel["sessions"])),
             fragment(*rows), legend)


def _sessions_section(store: Store, sessions: list[dict], sid: str = "sec-sessions",
                      *, shots: bool = False, heading: str = "") -> str:
    """The cross-link block other detail pages embed (persona / project / prototype): each of their
    sessions as one compact row — date · subject · fidelity · outcome. '' when there are none.
    `shots=True` (the prototype page, §9 V4) appends each row's first/last step-shot strip;
    `heading` overrides the section name (G1: the prototype page calls its replayable walks
    "Replays" to read distinct from the reaction sessions below)."""
    if not sessions:
        return ""
    rows = []
    for s in sessions:
        rows.append(_session_row(s, store))
        if shots:
            rows.append(raw(session_shot_strip(s)))
    return h("div", {"class_": "sec", "id": sid},
             h("h2", {}, f'{heading or t("sessions")} ({len(sessions)})'),
             h("div", {"class_": "rows"}, raw("".join(str(r) for r in rows))))


def _step_html(sess: dict, step: dict) -> str:
    """One timeline row (`id="step-N"`): the SCREEN panel (screenshot when the file exists, else the
    recorded screen text as a framed excerpt + url/title caption) beside the ACTION side (typed
    action chip + target/detail, the think-aloud monologue, friction + per-step verdict)."""
    i = step.get("index", 0)
    state = step.get("state") or {}
    fr = step.get("friction") or {}
    meta = _friction_meta(fr.get("level", ""))
    has_friction = bool(meta and meta["value"] > 0)
    shot_url = _screenshot_url(sess["id"], state["screenshot"]) if state.get("screenshot") else None
    action = step.get("action") or {}
    # the lightbox caption: step number + action (round-3 H6) — the typed chip label when one exists
    typ = action.get("type") or ""
    act_label = (t("action_" + typ) if typ in _ACTION_ICONS else typ)
    lb_caption = " · ".join(x for x in (t("step_n", n=i), act_label) if x)
    # the shot opens the full-resolution file in the lightbox (no-JS: the file itself, V4)
    screen = (h("a", {"class_": "sl-shotlink", "href": shot_url, "data-lightbox": True,
                      "data-caption": lb_caption},
                h("img", {"class_": "sess-shot", "src": shot_url,
                          "alt": state.get("title") or t("step_n", n=i), "loading": "lazy"}))
              if shot_url
              else h("div", {"class_": "sess-screen-txt"}, state.get("screen", "")))
    caption = " · ".join(x for x in (state.get("url"), state.get("title")) if x)
    target = (action.get("target") or "").strip()
    detail = (action.get("detail") or "").strip()
    monologue = (step.get("monologue") or "").strip()
    foot = h("div", {"class_": "sess-foot"},
             raw(_label(t(meta["label_key"]), meta["color"], title=fr.get("note") or None)) if has_friction else None,
             (h("span", {}, fr["note"]) if has_friction and fr.get("note") else None),
             _verdict_chip(step.get("verdict") or {}))
    style = f'--sfc:{meta["color"]}' if has_friction else None
    return h("div", {"class_": "sess-step", "id": f"step-{i}", "style": style},
             h("div", {"class_": "sess-screen"}, screen,
               h("div", {"class_": "sess-cap", "title": caption}, caption) if caption else None),
             h("div", {"class_": "sess-act"},
               h("div", {"class_": "sess-act-h"},
                 h("span", {"class_": "sess-n"}, str(i)),
                 # a timeline-shaped step has free-text action only — no typed chip to paint
                 raw(_action_chip(action)) if action.get("type") else None,
                 h("span", {"class_": "sess-target"}, target) if target else None),
               h("p", {"class_": "sess-detail"}, detail) if detail else None,
               h("blockquote", {"class_": "sess-mono"}, monologue) if monologue else None,
               foot))


def _friction_rail(sess: dict) -> str:
    """The jump nav over the session's friction: every step with friction > none, its level chip and
    note, linking to the step's `#step-N` anchor. '' for a friction-free run."""
    items = []
    for step in sess.get("steps") or []:
        meta = _friction_meta((step.get("friction") or {}).get("level", ""))
        if not meta or meta["value"] <= 0:
            continue
        note = (step.get("friction") or {}).get("note") or (step.get("monologue") or "")
        items.append(h("a", {"href": f'#step-{step["index"]}'},
                       h("span", {"class_": "sess-n"}, str(step["index"])),
                       raw(_label(t(meta["label_key"]), meta["color"])),
                       h("span", {"class_": "sess-rail-note"}, note)))
    if not items:
        return ""
    return h("div", {"class_": "sess-rail", "id": "sec-friction"},
             h("div", {"class_": "sess-rail-h"}, t("friction_rail_h"), f" ({len(items)})"),
             fragment(*items))


def _outcome_banner(sess: dict) -> str:
    out = sess.get("outcome") or {}
    summary = (out.get("summary") or "").strip()
    if out.get("completed"):
        return h("div", {"class_": "sess-banner", "style": "--sbc:var(--green)"}, raw(_icon("check")),
                 h("strong", {}, t("completed")), h("span", {"class_": "muted"}, summary) if summary else None)
    drop = out.get("dropoff_step", 0)
    step = next((s for s in sess.get("steps") or [] if s.get("index") == drop), {})
    reason = ((step.get("verdict") or {}).get("reason") or summary or "").strip()
    return h("div", {"class_": "sess-banner", "style": "--sbc:var(--red)"}, raw(_icon("warning")),
             h("strong", {}, h("a", {"href": f"#step-{drop}"}, t("outcome_dropped", n=drop))),
             h("span", {"class_": "muted"}, reason) if reason else None)


def register_sessions(app) -> None:
    @app.get("/sessions", response_class=HTMLResponse)
    def sessions_list(project: str | None = Query(default=None),
                      subject_kind: str | None = Query(default=None),
                      subject: str | None = Query(default=None),
                      status: str = Query(default=""),
                      subtype: str = Query(default=""), trace: str = Query(default=""),
                      q: str = Query(default="")) -> str:
        """The Library's Sessions tab under the canonical URL (ux-contract §3.5) — the
        honest subject query filters stay, and a subject filter with ≥2 recorded
        walks keeps earning its cross-session funnel above the rows. BOTH session kinds
        list here (§8.2 — sessions are first-class): usability walks and prototype
        reactions, newest first, one row vocabulary. ?project= and ?status= ride the
        shared FilterBar grammar (U10) — same param, now with chips + counts."""
        from urllib.parse import quote
        from .library import library_filters, library_page
        store = Store()
        subj = ({"kind": subject_kind, "id": subject} if (subject_kind and subject)
                else subject or None)
        sessions = services.list_usability_sessions(subject=subj, store=store)
        funnel_html = ""
        if subject_kind and subject and len(sessions) >= 2:
            funnel_html = _funnel_html(services.get_session_funnel(subject_kind, subject, store=store))
        protos = proto_session_rows(store)
        if subject:                                   # subject filter: the walked prototype
            key = subject if isinstance(subject, str) else ""
            protos = [v for v in protos if key and v["subject"].get("id") == key]
        merged = sorted(sessions + protos, key=lambda s: s.get("created_at", ""), reverse=True)
        base = "/sessions" + (f'?subject_kind={quote(subject_kind)}&subject={quote(subject)}'
                              if subject_kind and subject else "")
        return library_page("sessions", store, sessions=merged, pre_extra=funnel_html,
                            flt=library_filters(project or "", status, subtype=subtype, trace=trace),
                            base=base, q=q)

    @app.get("/sessions/{session_id}", response_class=HTMLResponse)
    def session_detail(session_id: str) -> str:
        """ONE detail route for both session kinds: a usability walk renders the dual-timeline
        replay; a protosession_* id dispatches to the prototype-session detail (same scaffold,
        same step renderer — the record decides, not the URL shape)."""
        store = Store()
        sess = store.get_usability_session(session_id)
        if not sess:
            psess = store.get_prototype_session(session_id)
            if psess:
                return _proto_session_detail(store, psess)
            return _layout(t("not_found"),
                           _empty_state(t("session_not_found"), t("runtime_maybe_cleared"), icon="activity"),
                           store, active="library")
        subject = sess.get("subject") or {}
        title = subject.get("label") or session_id
        fid = sess.get("fidelity", "")
        kind_label = (t("session_kind_live") if fid == "live" else
                      t("session_kind_artifact") if fid == "artifact" else
                      t("session_kind_prototype"))
        # meta line (V5: plain text, no pill-soup): persona · session kind · date. The
        # fidelity pill repeated the eyebrow, the date is meta text, and the tech-comfort
        # capability moved into the Properties rail where the other facts live.
        session_day = (ui.fmt_day(sess.get("date") or "") if sess.get("date")
                       else ui.local_day(sess.get("created_at", "")))
        sub = h("span", {"class_": "syn-meta"},
                _persona_chip(store, sess.get("persona_id", "")),
                h("span", {"class_": "muted"},
                  f' · {kind_label} · ', session_day))
        steps = sess.get("steps") or []
        timeline = h("div", {"class_": "sec", "id": "sec-replay"},
                     h("h2", {}, t("replay_h"), h("span", {"class_": "h1cnt"}, str(len(steps)))),
                     h("div", {"class_": "sess-steps"}, fragment(*(_step_html(sess, s) for s in steps))))
        statements_html = ""
        if sess.get("statements"):
            statements_html = h("div", {"class_": "sec", "id": "sec-statements"},
                                h("h2", {}, t("voices")),
                                raw(render_statements(sess["statements"], store)))
        rail = _friction_rail(sess)
        body = fragment(raw(_outcome_banner(sess)), raw(rail), timeline, raw(statements_html),
                        raw(LIGHTBOX_JS))
        proj = store.get_research_project(sess["project_id"]) if sess.get("project_id") else None
        # Project-rooted crumb (§8.2 — the council pattern); kind root only for orphans.
        crumbs = ([(t("projects"), "/jobs"), (proj["title"], f'/jobs/{proj["id"]}')]
                  if proj else [(t("sessions"), "/sessions")])
        crumbs.append((_display_title(title), None))
        grounded = sess.get("grounded_verified")
        caps = sess.get("capabilities_snapshot") or {}
        caps_prop = ""
        if caps.get("tech_comfort") is not None:
            cm = _A.tech_comfort_meta(caps["tech_comfort"])
            caps_prop = raw(_label(t(cm["label_key"]), cm["color"], title=cm["hint"]))
        # Rail order is the §8.2 anatomy: project → kind-specifics → dates.
        prop_rows = [
            ("projects", t("project"), h("a", {"href": f'/jobs/{proj["id"]}'}, proj["title"]) if proj else ""),
            *detail_form_rows("session", sess),
            ("square", t("fidelity"), raw(_fidelity_chip(sess.get("fidelity", "")))),
            ("compass", t("subject_h"), _subject_link(store, subject)),
            ("personas", t("cap_tech_comfort"), caps_prop),
            ("plan", t("steps_h"), str(len(steps))),
            # static "Grounding" label — the old code repeated the value as its own label
            # ("grounded → grounded", ux-audit P5 finding).
            ("check", t("grounding_h"),
             raw(_label(t("grounded_yes") if grounded else t("grounded_no"),
                        "var(--green)" if grounded else "var(--muted)")) if grounded is not None else ""),
            ("dot", t("created"), ui.local_date(sess.get("created_at") or "")),
        ]
        rail_sections = (([("sec-friction", t("friction_rail_h"))] if rail else [])
                         + [("sec-replay", t("replay_h"))]
                         + ([("sec-statements", t("voices"))] if statements_html else []))
        pills = ([_label(t("grounded_yes"), "var(--green)")] if grounded else []) \
            + [_outcome_chip(sess)]
        return detail_page(
            store, title=_display_title(title), crumbs=crumbs,
            # G5: sidebar active follows the crumb root (project-rooted → Projects)
            active="projects" if proj else "library",
            hero=_hero(title, icon="activity", sub=sub, hid="sec-head",
                       top=detail_eyebrow(kind_label, pills)),
            body=body,
            prop_rows=prop_rows,
            rel_study_id=f"session:{session_id}", rel_proj_id=sess.get("project_id") or None,
            rail_sections=rail_sections,
            star=("session", session_id, title[:60], f"/sessions/{session_id}"))

    if not _config.postgres_row_tenancy_enabled():
        @app.get("/sessions-files/{path:path}")
        def session_file(path: str):
            """Read-only screenshots from data/sessions/ (the avatar pattern, but with an
            explicit resolve + containment check: a traversal that escapes the sessions dir is
            a 404, never a file read). Shared row-tenancy deliberately registers no such route
            until workspace-aware filesystem/object-storage authorization replaces it."""
            base = _config.sessions_dir().resolve()
            try:
                target = (base / path).resolve()
            except OSError:
                return Response(status_code=404)
            if not (target.is_relative_to(base) and target.is_file()):
                return Response(status_code=404)
            return FileResponse(target)
