"""Activity feed: the recent cross-process lifecycle events (ticket live-event-stream).

Renders the same capped `events` table the SSE endpoint streams — one row per event
(time, localised event type, short label) linking to the entity it concerns. The
page itself is live: the chrome's EventSource module reloads it on every new event.
Read-only like every inspector page.

Per-run grouping (ux-contract §9 V8/G3): events that happened inside one run — same
project, timestamped between the run's start and finish (the bus rows are lean and carry
no run id, so the run CONTEXT is derived from the runs journal) — fold under one
collapsible run header row (the outline's details/summary idiom); everything recorded
outside a run stays a flat row. Identical-neighbor coalescing (×n, audit F4) keeps
working inside and outside the groups; INSIDE a run, same-key events also coalesce
across interleaved rows, and a repeated asset attach reads as ONE quiet "re-exported"
row (round-4 J3 — the re-export triplet).
"""
from __future__ import annotations

from ._ctx import *  # noqa: F401,F403  (shared render toolkit)
from .._html import register_css
from .._live import event_labels

register_css(r"""
/* ---- Activity: the per-run group (§9 V8/G3 — the outline's details/summary idiom) ---- */
details.sl-rungroup{border:1px solid var(--line);border-radius:var(--radius);background:var(--panel);margin:3px 0}
details.sl-rungroup>summary{list-style:none;cursor:pointer;display:flex;align-items:center;gap:9px;
  padding:8px 11px;font-size:var(--t-body);border-radius:var(--radius)}
details.sl-rungroup>summary::-webkit-details-marker{display:none}
details.sl-rungroup>summary:hover{background:var(--hover)}
details.sl-rungroup>summary svg{width:14px;height:14px;color:var(--accent);flex:none}
details.sl-rungroup>summary b{font-weight:600}
details.sl-rungroup>summary .cnt{color:var(--muted)}
details.sl-rungroup .row{border-top:1px solid var(--line-2);border-radius:0}
""")


def _run_intervals(store) -> list[dict]:
    """Every recorded run as a time interval: project, title, status, [start, end] —
    end stays open while the run is not finished. The read the grouping joins events
    against (the bus rows themselves are lean and carry no run id)."""
    out = []
    for p in store.list_research_projects():
        for r in store.list_runs(p["id"]):
            out.append({"run_id": r.get("run_id") or "", "project_id": p["id"],
                        "title": p["title"], "status": r.get("status", "active"),
                        "start": r.get("created_at") or "",
                        "end": (r.get("updated_at") or "") if r.get("status") == "finished" else ""})
    return out


def _run_of(ev: dict, intervals: list[dict]) -> dict | None:
    """The run an event belongs to: a run-entity event matches its run by id (the terminal
    `run.finished` row may stamp microseconds after the journal's updated_at); any other
    event joins the latest-starting run of its project whose interval contains its ts."""
    if ev.get("entity_type") == "run":
        return next((iv for iv in intervals if iv["run_id"] == ev.get("entity_id")), None)
    best = None
    for iv in intervals:
        if ev.get("project_id") != iv["project_id"] or not iv["start"]:
            continue
        if ev["ts"] < iv["start"] or (iv["end"] and ev["ts"] > iv["end"]):
            continue
        if best is None or iv["start"] > best["start"]:
            best = iv
    return best


def register_activity(app) -> None:
    @app.get("/activity", response_class=HTMLResponse)
    def activity() -> str:
        store = Store()
        labels = event_labels()
        intervals = _run_intervals(store)
        # Coalesce identical NEIGHBORS into one row with a ×n badge (audit F4): a re-export
        # that supersedes an asset emits the same event/label/url back-to-back — honest data,
        # but two visually identical lines teach nothing the badge doesn't.
        groups: list[dict] = []
        for ev in store.list_recent_events(limit=200):
            run = _run_of(ev, intervals)
            key = (ev["event"], ev["data"].get("label") or "", ev["data"].get("url") or "",
                   (run or {}).get("run_id"))
            if groups and groups[-1]["key"] == key:
                groups[-1]["n"] += 1
            else:
                groups.append({"key": key, "ev": ev, "n": 1, "run": run})
        total = sum(g["n"] for g in groups)   # raw event count, BEFORE the J3 folding below

        def _row(g: dict) -> str:
            ev = g["ev"]
            title = labels.get(ev["event"], ev["event"])
            # A coalesced re-export (round-4 J3): the same asset attached n× — superseded and
            # re-attached by a re-export — reads as ONE quiet verb, not n identical "attached"
            # rows; the ×n badge keeps the honest count.
            if ev["event"] in ("asset.attached",) and g["n"] > 1:
                title = t("evt_asset_reexported")
            label = ev["data"].get("label") or ""
            # Drop a detail label the event title already states ("Run finished · finished") —
            # text discipline, ux-contract C6 (ux-audit P5 finding).
            if label and label.casefold() in title.casefold():
                label = ""
            return h("a", {"class_": "row", "href": ev["data"].get("url") or "/jobs"},
                     h("span", {"class_": "rico", "style": "color:var(--accent)"},
                       raw(_icon("activity"))),
                     h("span", {"class_": "title"}, title,
                       h("span", {"class_": "muted small"}, f" · {label}") if label else None,
                       (h("span", {"class_": "pill"}, f'×{g["n"]}') if g["n"] > 1 else None)),
                     h("span", {"class_": "right"},
                       h("span", {}, ui.local_ts(ev["ts"]))))

        # ONE header per run: all of a run's events fold under a single group, anchored at
        # the run's newest event (an unattributable event — e.g. a bus row without a
        # project id — interleaving the stretch must not split the run into fragments).
        # Within a run the coalescing goes BEYOND adjacent-identical (round-4 J3): a re-export
        # emits the same asset/synthesis event minutes apart with other rows interleaved —
        # same-key groups fold into their newest occurrence (×n), so one action reads as one row.
        by_run: dict[str, list[dict]] = {}
        for g in groups:
            rid = (g["run"] or {}).get("run_id")
            if rid:
                bucket = by_run.setdefault(rid, [])
                same = next((x for x in bucket if x["key"] == g["key"]), None)
                if same is not None:
                    same["n"] += g["n"]            # the newest occurrence carries the row
                else:
                    bucket.append(g)
        # The render sequence: each run appears ONCE (anchored at its newest event). Flat rows
        # that become neighbors once a run's rows fold out of the stream coalesce too (J3 —
        # the re-recorded synthesis of a re-export loop straddles the run's asset events in
        # the raw stream, so plain neighbor-coalescing never saw the rows side by side).
        seq: list[tuple[dict | None, dict]] = []
        rendered: set[str] = set()
        for g in groups:
            run = g["run"]
            if run:
                if run["run_id"] not in rendered:
                    rendered.add(run["run_id"])
                    seq.append((run, g))
                continue
            if seq and seq[-1][0] is None and seq[-1][1]["key"] == g["key"]:
                seq[-1][1]["n"] += g["n"]
                continue
            seq.append((None, g))
        rows = []
        for run, g in seq:
            if run is None:
                rows.append(_row(g))
                continue
            bucket = by_run[run["run_id"]]
            n_ev = sum(x["n"] for x in bucket)
            state = (t("runs_finished_h") if run["status"] == "finished" else
                     t("runs_stalled_h") if run["status"] == "stalled" else t("runs_active_h"))
            rows.append(h("details", {"class_": "sl-rungroup", "open": True},
                          h("summary", {},
                            raw(_icon("play")),
                            h("span", {"class_": "title"},
                              h("b", {}, f'{t("run_chip")} · {run["title"]}'),
                              h("span", {"class_": "cnt"}, f' · {t("run_events_n", n=n_ev)}')),
                            h("span", {"class_": "right"},
                              raw(_label(state, "var(--muted)" if run["status"] == "finished"
                                         else "var(--green)")))),
                          fragment(*(_row(x) for x in bucket))))
        return _list_page(store, title=t("activity_h"), lead=t("activity_lead"), rows=rows,
                          count=total,
                          empty_icon="activity", empty_msg=t("no_activity"), active="activity")
