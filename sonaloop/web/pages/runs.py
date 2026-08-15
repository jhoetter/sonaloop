"""Runs page — every project's DRIVER status on one read-only surface (ticket
agents-running-panel). The stalled Codex project sat invisible for hours; this page
makes the silent failure mode loud: never-started, quiet-active and stopped jobs lead
(amber, with the canonical safe action behind diagnostics), active runs follow, and
finished plans collapse at the bottom. Every row links to its project page; the data
comes from services.project_health, read
through the shared collect_run_states() (web/_runs_widget.py).

Extension seam (mirrors the nav registry in web/_ext.py): downstream private packages
contribute extra sections to /runs WITHOUT the core importing them —

    from sonaloop.web import register_runs_section
    register_runs_section("assignments", render_assignments, order=50)

`provider(store) -> str` returns trusted HTML (extensions are trusted code, same rule
as layout slots); sections render below the core ones, ordered by `order`; idempotent
by section_id so a re-import or an override never duplicates. A broken provider is
skipped rather than taking down the page (the load_extensions fail-soft rule).
sonaloop-cloud will register its "assignments" section through this seam."""
from __future__ import annotations

from typing import Any, Callable

from ._ctx import *  # noqa: F401,F403  (shared render toolkit)
from .._html import register_css
from .._runs_widget import collect_run_states, run_attention_text, run_diagnostics_html

# ---------------------------------------------------------------- extension seam

_RUNS_SECTIONS: list[dict[str, Any]] = []


def register_runs_section(section_id: str, provider: Callable[[Any], str], order: int = 100) -> None:
    """Register (or replace) an extra /runs section. Idempotent by section_id."""
    for s in _RUNS_SECTIONS:
        if s["id"] == section_id:
            s.update(provider=provider, order=order)
            return
    _RUNS_SECTIONS.append({"id": section_id, "provider": provider, "order": order})


def _extension_sections(store) -> str:
    parts = []
    for s in sorted(_RUNS_SECTIONS, key=lambda s: s["order"]):
        try:
            parts.append(s["provider"](store))
        except Exception:  # noqa: BLE001 — never let one extension break the core page
            continue
    return "".join(parts)


# ---------------------------------------------------------------- core rendering

def _meta_line(r: dict) -> str:
    """Human-readable primary metadata; internal task keys live in diagnostics."""
    return h("div", {"class_": "run-meta"},
             h("span", {"class_": "muted small"},
               f'{t("run_last_activity")}: ', ui.local_ts(r["last_activity"])))


def _run_row(r: dict, *, stalled: bool = False, unverified: bool = False) -> str:
    waiting = r.get("state") == "waiting"
    expired = r.get("state") == "expired"
    state_label = (t("runs_expired_h") if expired else
                   t("runs_waiting_h") if waiting else
                   t("runs_unverified_h") if unverified else
                   (t("runs_not_started") if r.get("driver_state") == "not_started"
                    else t("runs_stopped") if r.get("driver_state") == "stopped"
                    else t("stalled")) if stalled else t("runs_active_h"))
    state_color = ("var(--red)" if unverified or expired
                   else "var(--amber)" if stalled or waiting else "var(--green)")
    attention = run_attention_text(r)
    return h("div", {"class_": "runrow" + (" runrow-waiting" if waiting else "")
                     + (" runrow-stalled" if stalled else "")
                     + (" runrow-expired" if expired else "")
                     + (" runrow-unverified" if unverified else ""),
                     "role": "status", "aria-label": state_label},
             h("div", {"class_": "runrow-head"},
               h("a", {"href": r["url"]}, raw(_icon("projects")), " ", h("b", {}, r["title"])),
               _label(state_label, state_color)),
             _meta_line(r),
             h("p", {"class_": "sl-run-attention"}, attention) if attention else None,
             raw(run_diagnostics_html(r)),
             # Explicitly announce that unverified is not engine-finished. The
             # text also keeps older screen-reader/search workflows truthful.
             h("span", {"class_": "sl-sr-only"}, t("run_engine_finished_no")) if unverified else None)


_RUNS_CSS = register_css(r"""
/* ---- /runs page (ticket agents-running-panel) ---- */
.runrow{border:1px solid var(--line);border-radius:var(--radius);background:var(--panel);padding:11px 13px;margin:0 0 8px}
.runrow-stalled{border-color:var(--amber)}
.runrow-waiting{border-color:var(--amber)}
.runrow-expired{border-color:var(--red)}
.runrow-unverified{border-color:var(--red)}
.runrow-head{display:flex;align-items:center;gap:10px;justify-content:space-between}
.runrow-head a{display:inline-flex;align-items:center;gap:8px;color:var(--ink);text-decoration:none;min-width:0}
.runrow-head a:hover b{color:var(--accent)}
.runrow-head svg{width:15px;height:15px;color:var(--accent);flex:none}
.run-meta{margin-top:5px;display:flex;align-items:center;gap:6px;flex-wrap:wrap}
.run-resume{margin-top:7px;display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.run-resume code{font-size:var(--t-sm);background:var(--panel-2);border:1px solid var(--line);border-radius:var(--radius-sm);padding:2px 7px}
.run-copy{border:1px solid var(--line);background:var(--panel-2);color:var(--muted);border-radius:var(--radius-sm);font-size:var(--t-xs);padding:2px 8px;cursor:pointer}
.run-copy:hover{color:var(--ink);background:var(--hover)}
.sl-sr-only{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}
.runs-sec{margin:18px 0 6px;font-size:var(--t-md);font-weight:600;display:flex;align-items:center;gap:8px}
.runs-sec .cnt{color:var(--muted);font-weight:500}
details.runs-fin summary{cursor:pointer;margin:18px 0 6px;font-size:var(--t-md);font-weight:600;color:var(--muted)}
""")

def _section(label: str, rows: list) -> str:
    if not rows:
        return ""
    return fragment(h("div", {"class_": "runs-sec"}, label, h("span", {"class_": "cnt"}, str(len(rows)))),
                    fragment(*rows))


def register_runs(app) -> None:
    @app.get("/runs", response_class=HTMLResponse)
    def runs_page() -> str:
        store = Store()
        states = collect_run_states(store)
        waiting = [_run_row(r) for r in states["waiting"]]
        stalled = [_run_row(r, stalled=True) for r in states["stalled"]]
        expired = [_run_row(r) for r in states["expired"]]
        active = [_run_row(r) for r in states["active"]]
        unverified = [_run_row(r, unverified=True) for r in states["unverified"]]
        finished = [h("div", {"class_": "runrow"},
                      h("div", {"class_": "runrow-head"},
                        h("a", {"href": r["url"]}, raw(_icon("projects")), " ", h("b", {}, r["title"])),
                        h("span", {"class_": "muted small"}, ui.local_ts(r["last_activity"]))),
                      raw(run_diagnostics_html(r)))
                    for r in states["finished"]]
        if not (waiting or stalled or expired or active or unverified or finished):
            core = h("div", {"class_": "sl-empty"},
                     h("div", {"class_": "sl-empty__icon"}, raw(_icon("play"))),
                     h("p", {"class_": "sl-empty__body"}, t("no_runs")))
        else:
            core = fragment(
                raw(_section(t("runs_expired_h"), expired)),
                raw(_section(t("runs_setup_h"), waiting)),
                raw(_section(t("runs_stalled_h"), stalled)),
                h("details", {"class_": "runs-fin sl-runs-unverified", "open": True},
                  h("summary", {}, f'{t("runs_unverified_h")} ({len(unverified)})'),
                  fragment(*unverified)) if unverified else None,
                raw(_section(t("runs_active_h"), active)),
                # When nothing is stalled or active, the finished journal IS the page — render
                # it open instead of greeting the reader with one collapsed chevron (ux-audit P5).
                h("details", {"class_": "runs-fin", "open": True if not (waiting or stalled or expired or active or unverified) else None},
                  h("summary", {}, f'{t("runs_finished_h")} ({len(finished)})'),
                  fragment(*finished)) if finished else None)
        # (the data-copy clipboard handler ships with the chrome — RUNS_WIDGET_JS)
        body = h("div", {"class_": "page"},
                 h("h1", {"class_": "h1"}, t("runs_h")),
                 h("p", {"class_": "lead"}, t("runs_lead")),
                 core, raw(_extension_sections(store)))
        return _layout(t("runs_h"), body, store, crumbs=[(t("runs_h"), None)], active="runs")
