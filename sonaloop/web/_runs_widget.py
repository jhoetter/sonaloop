"""Live "agents running" chrome widget (ticket agents-running-panel).

Self-contained (CSS + markup + JS, the _palette.py pattern), rendered by _layout into
the topbar of every page: a status dot + attention/active count, with a small flyout
listing affected jobs (project, last activity) and a link to the full /runs page.
Attention takes precedence over unrelated active runs — the silent failure mode must be loud.

Live updates ride the EXISTING SSE stream: _live.py re-dispatches every /api/events
frame as a `sl:live-event` DOM event; this widget debounces those into a refetch of
/api/runs and re-renders itself. Graceful static fallback: without EventSource the
server-rendered state simply stands (the SSR markup is always complete).

This module also owns collect_run_states() — the one read the /runs page, the widget
and /api/runs all share (deliberately NOT importing any page module, so _components
can import this without a cycle)."""
from __future__ import annotations

import contextvars
import copy
from typing import Any

from .._icons import icon as _picon     # direct import avoids a cycle (_components imports this module)
from ..run_activity import is_inactive_for
from ..storage import Store
from ._i18n import t
from ._html import h, raw, fragment

_RUN_STATES_CACHE: contextvars.ContextVar[dict[str, list[dict[str, Any]]] | None] = \
    contextvars.ContextVar("sonaloop_run_states_cache", default=None)
_PROJECT_HEALTH_CACHE: contextvars.ContextVar[
    dict[tuple[int, str, int], dict[str, Any]] | None
] = contextvars.ContextVar("sonaloop_project_health_cache", default=None)


def begin_run_states_cache() -> tuple[contextvars.Token, contextvars.Token]:
    """Open the request-local run and project-health read caches.

    Both caches deliberately live only for one web request.  A later request
    therefore always observes writes made since the preceding render.
    """
    return _RUN_STATES_CACHE.set(None), _PROJECT_HEALTH_CACHE.set({})


def end_run_states_cache(tokens: tuple[contextvars.Token, contextvars.Token]) -> None:
    run_states_token, project_health_token = tokens
    _PROJECT_HEALTH_CACHE.reset(project_health_token)
    _RUN_STATES_CACHE.reset(run_states_token)


def cached_project_health(project_id: str, store: Store | None = None,
                          stale_hours: int = 6) -> dict[str, Any]:
    """Read canonical project health once per project and web request.

    ``project_health`` is intentionally a deep integrity projection.  Several
    pieces of one project page need the same result, but recomputing it repeats
    all evidence/ref validation.  Copies keep presentation callers from
    mutating the value shared by the rest of the request.
    """
    from .. import services

    store = store or Store()
    cache = _PROJECT_HEALTH_CACHE.get()
    key = (id(store), str(project_id), int(stale_hours))
    if cache is not None and key in cache:
        return copy.deepcopy(cache[key])
    health = services.project_health(project_id, store=store, stale_hours=stale_hours)
    if cache is not None:
        cache[key] = health
    return copy.deepcopy(health)


def _latest(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    return max(rows, key=lambda row: (
        str(row.get("updated_at") or ""),
        str(row.get("created_at") or ""),
        int(row.get("idx") or 0),
    ), default=None)


def collect_run_attention_states(store: Store | None = None,
                                 stale_hours: int = 6,
                                 expire_hours: int = 24) -> dict[str, list[dict[str, Any]]]:
    """Cheap, truthful SSR projection for the visible topbar attention lanes.

    The widget needs only active, setup-waiting, stalled and expired jobs.  It must not
    perform the claim/ref/report verification required by the full run journal
    merely to decide whether to render a status chip.  Active Reaction Test
    preflights remain canonical: an open run blocked on setup is ``waiting``,
    never a reassuring green ``active``.

    ``/runs`` and ``/api/runs`` continue to use :func:`collect_run_states`, so
    finished and unverified output still receive the full integrity projection
    whenever those detailed surfaces are requested.
    """
    from .. import plan as plan_mod
    from ..research_integrity import is_reaction_project, project_policy
    from ..services._recovery import _preflight_health

    store = store or Store()
    out: dict[str, list[dict[str, Any]]] = {
        "active": [], "waiting": [], "stalled": [], "expired": [],
        "finished": [], "unverified": [],
    }
    for project in store.list_research_projects():
        lifecycle = str(project.get("status") or "active").strip().casefold()
        if lifecycle in {"archived", "superseded"}:
            continue
        try:
            plan = plan_mod.get_plan(project["id"], store=store)
            if not plan:
                continue
            runs = store.list_runs(project["id"])
            active_runs = [row for row in runs if row.get("status") == "active"]
            run = _latest(active_runs) or _latest(runs)

            # Finished/unverified jobs have no visible topbar lane.  Omit them
            # before any deep artifact verification.  An active run remains
            # authoritative even if an older run already finished.
            if not active_runs and (run and run.get("status") == "finished"
                                    or plan_mod.is_complete(plan)):
                continue

            preflight: dict[str, Any] = {}
            if active_runs:
                policy = project_policy(project, plan)
                preflight = (
                    _preflight_health(project, plan, store)
                    if (is_reaction_project(project, plan)
                        or policy.get("cohort_preflight_required"))
                    else {"state": "ready"}
                )
                if is_inactive_for(str((run or {}).get("updated_at") or ""), expire_hours):
                    state = driver_state = "expired"
                elif preflight.get("state") == "waiting":
                    state = "waiting"
                    driver_state = "waiting_on_preflight"
                elif is_inactive_for(str((run or {}).get("updated_at") or ""), stale_hours):
                    state = driver_state = "stalled"
                else:
                    state = "running"
                    driver_state = "running"
            else:
                state = "stalled"
                driver_state = "not_started" if not runs else "stopped"

            bucket = "active" if state == "running" else state
            out[bucket].append({
                "project_id": project["id"],
                "title": project["title"],
                "url": f'/jobs/{project["id"]}',
                "state": state,
                "last_activity": max(
                    [str(project.get("updated_at") or "")]
                    + [str(row.get("updated_at") or "") for row in runs]
                ),
                "driver_state": driver_state,
                "preflight": preflight,
            })
        except Exception:
            # Chrome must never prevent the requested page from rendering.
            # Detailed surfaces still expose projection failures explicitly.
            continue
    return out


def _action_call(action: dict[str, Any]) -> str:
    args = ", ".join(f"{key}={value!r}" for key, value in (action.get("arguments") or {}).items()
                     if value != "")
    return f"{action.get('tool')}({args})" if action.get("tool") else ""


def collect_run_states(store: Store | None = None) -> dict[str, list[dict[str, Any]]]:
    """Every project's run state (services.project_run_state), grouped by state.
    Projects without a plan (state None) are skipped — there is no driver to show.
    Cached per-request so multiple calls within one page render don't re-query."""
    cached = _RUN_STATES_CACHE.get()
    if cached is not None:
        return cached
    store = store or Store()
    out: dict[str, list[dict[str, Any]]] = {
        "active": [], "waiting": [], "stalled": [], "expired": [],
        "finished": [], "unverified": [],
    }
    for p in store.list_research_projects():
        # Archive is an evidence-preserving lifecycle state, not an active-work
        # lane.  Keep archived records reachable by their exact detail URL, but
        # never let their historical plan/run health reappear in the journal,
        # global attention widget or shared /api/runs projection.
        if str(p.get("status") or "active").strip().casefold() == "archived":
            continue
        try:
            health = cached_project_health(p["id"], store=store)
        except Exception:
            health = None
        if not health:
            continue
        bucket = {"running": "active", "waiting": "waiting", "stalled": "stalled",
                  "expired": "expired", "finished": "finished",
                  "unverified": "unverified"}.get(str(health.get("state") or ""))
        if not bucket:
            continue
        action = health.get("safe_next_action") or {}
        out[bucket].append({
            "project_id": p["id"], "title": p["title"], "url": f'/jobs/{p["id"]}',
            "state": health.get("state", ""),
            "last_activity": health.get("last_activity", ""),
            "driver_state": health.get("driver_state", ""),
            "preflight": health.get("preflight") or {},
            "run_inventory": health.get("run_inventory") or {},
            "next_ready": (health.get("tasks") or {}).get("next_ready") or [],
            "unmet_invariant": health.get("unmet_invariant"),
            "last_successful_operation": health.get("last_successful_operation"),
            "safe_next_action": action, "trace": health.get("trace"),
            "integrity_findings": health.get("integrity_findings") or [],
            "engine_finished": health.get("engine_finished", False),
            "activity_lifecycle": health.get("activity_lifecycle") or {},
            "unverified_output": health.get("unverified_output", False)})
    _RUN_STATES_CACHE.set(out)
    return out


def run_diagnostics_html(run_state: dict[str, Any]) -> str:
    """Progressive disclosure for support-grade run details.

    The project canvas and normal run summary deliberately contain no invariant
    prose, tool calls or trace identifiers. Those exact values remain available
    here for operators and support after the reader opens the disclosure.
    """
    unmet = run_state.get("unmet_invariant") or {}
    last = run_state.get("last_successful_operation") or {}
    action = run_state.get("safe_next_action") or {}
    call = _action_call(action)
    trace = run_state.get("trace") or {}
    support_ref = str(trace.get("support_ref") or "")
    limitation = str(trace.get("limitation") or "")
    ready_source = run_state.get("next_ready")
    if ready_source is None:
        ready_source = (run_state.get("tasks") or {}).get("next_ready")
    next_ready = [str(step) for step in (ready_source or []) if str(step)]
    project_title = str(run_state.get("title") or "").strip()
    issues = []
    for row in run_state.get("integrity_findings") or []:
        content = (
            h("a", {"href": row["target"]}, row.get("message") or row.get("code") or "—")
            if row.get("target") else row.get("message") or row.get("code") or "—"
        )
        issues.append(h("li", {"data-integrity-code": row.get("code", "")}, content))
    if not any((unmet, last, action, support_ref, limitation, next_ready, issues)):
        return ""
    action_value = (
        fragment(
            h("code", {}, call), " ",
            h("button", {"type": "button", "class_": "run-copy", "data-copy": call,
                         "data-copied": t("copied"), "aria-label": t("copy_btn")},
              t("copy_btn")),
        )
        if call else action.get("reason") or "—"
    )
    trace_value = fragment(
        h("code", {}, support_ref) if support_ref else None,
        h("span", {"class_": "muted small"},
          (" · " if support_ref and limitation else ""), t("health_external_limit"), ": ",
          limitation) if limitation else None,
    )
    summary_attrs = ({"aria_label": t("health_diagnostics_for", title=project_title)}
                     if project_title else {})
    return h(
        "details", {"class_": "sl-run-diagnostics", "data-run-diagnostics": True},
        h("summary", summary_attrs, t("health_diagnostics")),
        h("p", {"class_": "muted small sl-run-diagnostics-help"}, t("health_diagnostics_help")),
        h("dl", {"class_": "sl-run-diagnostics-grid"},
          h("dt", {}, t("health_unmet")),
          h("dd", {}, unmet.get("message") or t("health_no_issues")),
          h("dt", {}, t("health_last_success")),
          h("dd", {}, h("code", {}, last.get("key") or last.get("kind") or "—"),
            (f' · {last.get("summary")}' if last.get("summary") else "")),
          h("dt", {}, t("health_safe_next")),
          h("dd", {}, action_value),
          h("dt", {}, t("health_trace")),
          h("dd", {}, trace_value or "—"),
          (fragment(
            h("dt", {}, t("health_next_ready")),
            h("dd", {}, h("ul", {"class_": "sl-run-diagnostics-tasks"},
              fragment(*(h("li", {}, h("code", {}, step)) for step in next_ready)))))
           if next_ready else None),
          (fragment(
            h("dt", {"class_": "sl-run-diagnostics-issues"}, t("health_findings")),
            h("dd", {"class_": "sl-run-diagnostics-issues"},
              h("ul", {}, fragment(*issues)))) if issues else None)))


def run_attention_text(run_state: dict[str, Any]) -> str:
    """One human recovery sentence for the visible run state."""
    if run_state.get("state") == "waiting" \
            or run_state.get("driver_state") == "waiting_on_preflight":
        gate = str((run_state.get("preflight") or {}).get("gate") or "")
        return (t("health_attention_preflight_product")
                if gate == "product_understanding"
                else t("health_attention_preflight_selection")
                if gate == "cohort_selection"
                else t("health_attention_preflight_cohort"))
    if run_state.get("state") == "unverified":
        return t("health_attention_unverified")
    if run_state.get("state") == "expired":
        return t("health_attention_expired")
    if run_state.get("state") == "stalled":
        if run_state.get("driver_state") == "not_started":
            return t("health_attention_not_started")
        if run_state.get("driver_state") == "stopped":
            return t("health_attention_stopped")
        return t("health_attention_stalled")
    return ""


def project_run_chip(project_id: str, store: Store,
                     run_state: dict[str, Any] | None = None) -> str:
    """The project-header run chip (ux-contract §3.5 / decision §7.4): `▶ Run · state`
    in the state's color, opening a small popover with the state, the last activity,
    a human-readable recovery hint, closed support diagnostics, and the /runs journal link.
    '' when the project has no plan — there is no driver to show."""
    rs = run_state
    if rs is None:
        try:
            rs = cached_project_health(project_id, store=store)
        except Exception:  # noqa: BLE001 — the chip is chrome; never break the page
            rs = None
    if not rs or rs.get("state") not in (
            "running", "waiting", "stalled", "expired", "finished", "unverified"):
        return ""
    state = rs["state"]
    css_state = "active" if state == "running" else state
    label = {"running": t("runs_active_h"), "waiting": t("runs_waiting_h"),
             "stalled": t("runs_stalled_h"),
             "expired": t("runs_expired_h"),
             "finished": t("runs_finished_h"), "unverified": t("runs_unverified_h")}[state]
    last = (rs.get("last_activity") or "")[:16].replace("T", " ")
    btn = h("button", {"type": "button", "class_": f"sl-toolbtn runchip runchip--{css_state}",
                       "data-runchip-toggle": True, "aria-haspopup": "dialog",
                       "aria-controls": "runchip-fly", "aria-expanded": "false"},
            raw(_picon("play")), f'{t("run_chip")} · {label}')
    fly = h("div", {"class_": "runchip-fly", "id": "runchip-fly", "hidden": True,
                    "role": "dialog", "aria-labelledby": "runchip-fly-title", "tabindex": "-1"},
            h("div", {"class_": "runsw-h", "id": "runchip-fly-title"},
              f'{t("run_chip")} · {label}'),
            # the concept FIRST (§9 V8): one sentence saying what a run even is,
            # before this run's state details
            h("p", {"class_": "runchip-def"}, t("runs_lead")),
            h("div", {"class_": "run-meta"},
              h("span", {"class_": "muted small"},
                f'{t("run_last_activity")}: {last}') if last else None),
            h("p", {"class_": "sl-run-attention"}, run_attention_text(rs))
            if state in {"waiting", "stalled", "expired", "unverified"} else None,
            raw(run_diagnostics_html(rs)),
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
.runsw.has-waiting .runsw-dot,.runsw.has-stalled .runsw-dot{background:var(--amber);animation:none}
.runsw.has-expired .runsw-dot{background:var(--red);animation:none}
.runsw.has-active .runsw-btn{color:var(--green,#34a853);border-color:color-mix(in srgb,var(--green,#34a853) 45%,var(--line))}
.runsw.has-waiting .runsw-btn,.runsw.has-stalled .runsw-btn{color:var(--amber);border-color:color-mix(in srgb,var(--amber) 45%,var(--line))}
.runsw.has-expired .runsw-btn{color:var(--red);border-color:color-mix(in srgb,var(--red) 45%,var(--line))}
.runsw-count{font-variant-numeric:tabular-nums}
.runsw-fly{position:absolute;right:0;top:calc(100% + 8px);width:min(320px,86vw);z-index:160;background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);box-shadow:0 14px 40px rgba(0,0,0,.3);padding:6px}
.runsw-fly[hidden]{display:none}
.runsw-h{font-size:var(--t-xs);color:var(--faint);font-weight:600;letter-spacing:.04em;padding:7px 8px 3px}
.runsw-lane+.runsw-lane{border-top:1px solid var(--line-2);margin-top:3px;padding-top:3px}.runsw-lane-h{padding:5px 8px 2px;color:var(--muted);font-size:var(--t-xs);font-weight:600}
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
.runchip--expired{color:var(--red);border-color:color-mix(in srgb,var(--red) 45%,var(--line))}
.runchip--waiting{color:var(--amber);border-color:color-mix(in srgb,var(--amber) 45%,var(--line))}
.runchip--unverified{color:var(--red);border-color:color-mix(in srgb,var(--red) 45%,var(--line))}
.runchip-fly{position:absolute;left:0;top:calc(100% + 8px);width:min(380px,86vw);z-index:160;background:var(--panel);
  border:1px solid var(--line);border-radius:var(--radius);box-shadow:0 14px 40px rgba(0,0,0,.3);padding:6px 8px 8px}
.sl-tb-actions .runchip-fly{left:auto;right:0}
.runchip-fly[hidden]{display:none}
.runchip-def{margin:2px 0 6px;padding:0 8px;color:var(--muted);font-size:var(--t-sm);line-height:1.5}
.runchip-fly .run-meta{padding:2px 8px}
.sl-run-attention{margin:6px 8px;color:var(--ink);font-size:var(--t-sm);line-height:1.45}
.sl-run-diagnostics{margin:6px 8px;border-top:1px solid var(--line-2);padding-top:6px;font-size:var(--t-sm)}
.sl-run-diagnostics summary{cursor:pointer;color:var(--muted);font-weight:500;list-style-position:inside}
.sl-run-diagnostics[open] summary{color:var(--ink)}
.sl-run-diagnostics-help{margin:6px 0}
.sl-run-diagnostics-grid{display:grid;grid-template-columns:minmax(112px,.34fr) 1fr;gap:6px 10px;margin:8px 0 2px}
.sl-run-diagnostics-grid dt{color:var(--muted)}.sl-run-diagnostics-grid dd{margin:0;min-width:0;overflow-wrap:anywhere}
.sl-run-diagnostics-grid code{font-size:var(--t-xs)}.sl-run-diagnostics-issues{grid-column:1/-1}
.sl-run-diagnostics-tasks{margin:0;padding-left:18px}
.sl-run-diagnostics-issues ul{margin:2px 0;padding-left:18px}.sl-run-diagnostics-issues a{color:var(--accent)}
.sl-run-diagnostics .run-copy{margin-left:4px}
@media(max-width:640px){.sl-run-diagnostics-grid{grid-template-columns:1fr}.sl-run-diagnostics-grid dd{margin-bottom:4px}}
"""


def _fly_rows(rows: list[dict]) -> str:
    items = [h("a", {"class_": "runsw-row", "href": r["url"]},
              h("span", {"class_": "runsw-t"}, r["title"]),
              h("span", {"class_": "runsw-ts"}, r["last_activity"][:16].replace("T", " ")))
             for r in rows]
    return "".join(items)


def _fly_sections(states: dict[str, list[dict]]) -> str:
    sections = []
    for key, label in (("expired", t("runs_expired_h")),
                       ("waiting", t("runs_setup_h")),
                       ("stalled", t("runs_stalled_h")),
                       ("active", t("runs_active_h"))):
        rows = states[key]
        if rows:
            sections.append(h("div", {"class_": "runsw-lane", "data-run-lane": key},
                              h("div", {"class_": "runsw-lane-h"}, label),
                              raw(_fly_rows(rows))))
    return "".join(sections) or h("div", {"class_": "runsw-empty"}, t("runs_none_active"))


def chip_label(n_active: int, n_stalled: int, n_waiting: int = 0,
               n_expired: int = 0) -> str:
    """Status-chip text: attention wins, otherwise show active governed runs.

    Silent failures must remain loud even while another project is progressing. The
    attention count includes both interrupted runs and jobs whose governed run never
    started, so it must not claim that every counted item is a stalled run.
    """
    if n_expired and (n_waiting or n_stalled):
        return t("run_stalled_n", n=n_expired + n_waiting + n_stalled)
    if n_expired:
        return t("run_expired_n", n=n_expired)
    if n_waiting and n_stalled:
        return t("run_stalled_n", n=n_waiting + n_stalled)
    if n_waiting:
        return t("run_setup_n", n=n_waiting)
    if n_stalled:
        return t("run_stalled_n", n=n_stalled)
    if n_active:
        return t("run_active_n", n=n_active)
    return ""


def runs_widget_markup(store: Store) -> str:
    """Per-request widget markup (localised, server-rendered with the current counts —
    the static fallback IS the initial state). JS only mutates it on live events.
    At zero the whole chip is hidden (§9 V7) — the markup still ships so a live event
    can unhide it without a reload."""
    from ._ext import is_customer_surface
    if is_customer_surface():
        return ""
    # The /runs page has already paid for the canonical full projection in this
    # same request; reuse it there.  Ordinary pages never trigger that work just
    # for chrome and take the lightweight path.
    states = _RUN_STATES_CACHE.get()
    if states is None:
        states = collect_run_attention_states(store)
    n_active, n_waiting, n_stalled, n_expired = (
        len(states["active"]), len(states["waiting"]), len(states["stalled"]),
        len(states["expired"]),
    )
    cls = ("runsw" + (" has-active" if n_active else "")
           + (" has-waiting" if n_waiting else "")
           + (" has-stalled" if n_stalled else "")
           + (" has-expired" if n_expired else ""))
    btn = h("button", {"type": "button", "class_": "sl-toolbtn runsw-btn", "data-runsw-toggle": True,
                       "aria-haspopup": "dialog", "aria-controls": "runsw-fly",
                       "aria-expanded": "false",
                       "title": t("active_runs"), "aria-label": t("active_runs")},
            h("span", {"class_": "runsw-dot"}),
            h("span", {"class_": "runsw-count", "id": "runsw-count"},
              chip_label(n_active, n_stalled, n_waiting, n_expired)))
    fly = h("div", {"class_": "runsw-fly", "id": "runsw-fly", "hidden": True,
                    "data-empty": t("runs_none_active"), "role": "dialog",
                    "aria-labelledby": "runsw-fly-title", "tabindex": "-1"},
            h("div", {"class_": "runsw-h", "id": "runsw-fly-title"}, t("active_runs")),
            h("div", {"id": "runsw-list"}, raw(_fly_sections(states))),
            h("a", {"class_": "runsw-all", "href": "/runs"},
              raw(_picon("arrowRight")), " ", t("runs_view_all")))
    return h("div", {"class_": cls, "id": "runsw",
                     "hidden": not (n_active or n_waiting or n_stalled or n_expired),
                     # the JS re-render composes the localized chip text from these templates
                     "data-l-active-one": t("run_active_n", n=1),
                     "data-l-active-n": t("run_active_n", n="{n}"),
                     "data-l-setup-one": t("run_setup_n", n=1),
                     "data-l-setup-n": t("run_setup_n", n="{n}"),
                     "data-l-stalled-one": t("run_stalled_n", n=1),
                     "data-l-stalled-n": t("run_stalled_n", n="{n}"),
                     "data-l-expired-one": t("run_expired_n", n=1),
                     "data-l-expired-n": t("run_expired_n", n="{n}"),
                     "data-l-expired-h": t("runs_expired_h"),
                     "data-l-setup-h": t("runs_setup_h"),
                     "data-l-stalled-h": t("runs_stalled_h"),
                     "data-l-active-h": t("runs_active_h")}, btn, fly)


RUNS_WIDGET_JS = r"""<script>(function(){
if(window.__slRunsWidget) return; window.__slRunsWidget=1;
function el(id){ return document.getElementById(id); }
function esc(s){ return String(s==null?'':s).replace(/[&<>"]/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c];}); }
function closePopover(btn,fly,restore){
  if(!fly) return; var ownedFocus=fly.contains(document.activeElement); fly.hidden=true;
  if(btn) btn.setAttribute('aria-expanded','false');
  if((restore||ownedFocus)&&btn) btn.focus();
}
function openPopover(btn,fly){
  if(!btn||!fly) return; fly.hidden=false; btn.setAttribute('aria-expanded','true');
  var first=fly.querySelector('summary,a[href],button:not([disabled]),[tabindex]:not([tabindex="-1"])');
  (first||fly).focus();
}
// Delegated toggles: the widgets live inside #main, which SPA navigation replaces.
// Same pattern for the topbar flyout and the project-header run-chip popover.
document.addEventListener('click',function(e){
  var b=e.target.closest&&e.target.closest('[data-runsw-toggle]');
  var fly=el('runsw-fly');
  var c=e.target.closest&&e.target.closest('[data-runchip-toggle]');
  var cfly=el('runchip-fly');
  if(b&&fly){ e.preventDefault();
    closePopover(document.querySelector('[data-runchip-toggle]'),cfly,false);
    if(fly.hidden) openPopover(b,fly); else closePopover(b,fly,false); return; }
  if(c&&cfly){ e.preventDefault();
    closePopover(document.querySelector('[data-runsw-toggle]'),fly,false);
    if(cfly.hidden) openPopover(c,cfly); else closePopover(c,cfly,false); return; }
  if(fly&&!fly.hidden&&!(e.target.closest&&e.target.closest('#runsw')))
    closePopover(document.querySelector('[data-runsw-toggle]'),fly,false);
  if(cfly&&!cfly.hidden&&!(e.target.closest&&e.target.closest('#runchip')))
    closePopover(document.querySelector('[data-runchip-toggle]'),cfly,false);
});
document.addEventListener('keydown',function(e){ if(e.key!=='Escape') return;
  var fly=el('runsw-fly'), cfly=el('runchip-fly');
  if(cfly&&!cfly.hidden){ e.preventDefault();
    closePopover(document.querySelector('[data-runchip-toggle]'),cfly,true); return; }
  if(fly&&!fly.hidden){ e.preventDefault();
    closePopover(document.querySelector('[data-runsw-toggle]'),fly,true); }
});
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
  var act=d.active||[], wait=d.waiting||[], st=d.stalled||[], exp=d.expired||[];
  // Attention remains loud even when another run is active; full zero stays hidden.
  var n=act.length, q=wait.length, s=st.length, x=exp.length, lbl='';
  if(x&&(q||s)){ var attention=x+q+s; lbl=(attention===1)?w.getAttribute('data-l-stalled-one'):w.getAttribute('data-l-stalled-n').replace('{n}',attention); }
  else if(x) lbl=(x===1)?w.getAttribute('data-l-expired-one'):w.getAttribute('data-l-expired-n').replace('{n}',x);
  else if(q&&s){ var total=q+s; lbl=(total===1)?w.getAttribute('data-l-stalled-one'):w.getAttribute('data-l-stalled-n').replace('{n}',total); }
  else if(q) lbl=(q===1)?w.getAttribute('data-l-setup-one'):w.getAttribute('data-l-setup-n').replace('{n}',q);
  else if(s) lbl=(s===1)?w.getAttribute('data-l-stalled-one'):w.getAttribute('data-l-stalled-n').replace('{n}',s);
  else if(n) lbl=(n===1)?w.getAttribute('data-l-active-one'):w.getAttribute('data-l-active-n').replace('{n}',n);
  cnt.textContent=lbl||'';
  w.hidden=!(n||q||s||x);
  w.classList.toggle('has-active',n>0);
  w.classList.toggle('has-waiting',q>0);
  w.classList.toggle('has-stalled',s>0);
  w.classList.toggle('has-expired',x>0);
  function rows(items){ var out=''; items.forEach(function(r){ out+='<a class="runsw-row" href="'+esc(r.url)+'">'
    +'<span class="runsw-t">'+esc(r.title)+'</span>'
    +'<span class="runsw-ts">'+esc((r.last_activity||'').slice(0,16).replace('T',' '))+'</span></a>'; }); return out; }
  function lane(key,label,items){ return items.length?'<div class="runsw-lane" data-run-lane="'+key+'">'
    +'<div class="runsw-lane-h">'+esc(label)+'</div>'+rows(items)+'</div>':''; }
  var html=lane('expired',w.getAttribute('data-l-expired-h'),exp)
    +lane('waiting',w.getAttribute('data-l-setup-h'),wait)
    +lane('stalled',w.getAttribute('data-l-stalled-h'),st)
    +lane('active',w.getAttribute('data-l-active-h'),act);
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
