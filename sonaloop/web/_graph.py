from __future__ import annotations

from .. import presentation as _pres
from ._i18n import t
from ._components import _icon
from ._graph_outline import _outline_html  # noqa: F401  (split out; import surface preserved)
from ._html import h, raw, fragment
from ._plan_fw import _framework_strip


def _plan_html(plan: dict, store) -> str:
    tasks = plan.get("tasks", [])
    done = sum(1 for tk in tasks if tk["status"] == "done")
    complete = bool(tasks) and done == len(tasks)
    by_title = {tk["id"]: tk.get("title", tk["id"]) for tk in tasks}
    # Status marks are sonaloop-design (single source of truth); colour drives currentColor.
    STATUS = {"done": ("check", "var(--green)"), "active": ("half", "var(--accent)"),
              "todo": ("circle", "var(--muted)"), "blocked": ("alert", "var(--red)")}
    # Resolve evidence links by IDENTITY (which collection the ref lives in), not by a kind
    # literal — the kind LABEL comes from data via present(); storage membership is legitimate.
    _syn_ids = {s["id"] for s in store.list_syntheses()}
    _protos = {p["id"]: p for p in store.list_prototypes(plan["project_id"])}

    def ev_chip(r: dict, n: int = 0) -> str:
        rid, kind = r.get("id", ""), r.get("kind", "")
        label = _pres.present(kind)["short"] if kind else rid
        if kind == "session" and n:                            # distinguish the otherwise-identical "session" chips
            label = f"{label} {n}"
        href = None
        if rid in _protos:
            p = _protos[rid]
            href, label = f"/prototypes/{p['slug']}", f"{label} · {p.get('name', p['slug'])}"
        elif rid in _syn_ids:
            href = f"/syntheses/{rid}"
        elif store.get_council_session(rid):
            href = f"/councils/{rid}"
        if href:
            return h("a", {"class_": "ev", "href": href}, label, " ↗")
        return h("span", {"class_": "ev"}, label)

    def row(tk: dict, last: bool) -> str:
        st = tk["status"]
        mark, clr = STATUS.get(st, ("circle", "var(--faint)"))
        cons = " · ".join(by_title.get(c, c) for c in tk.get("consumes", []))
        req = tk.get("requires", {}) or {}
        gates = []
        if req.get("min_inputs") is not None:
            gates.append(f"min. {req['min_inputs']} Inputs")
        if req.get("gate_tag"):
            gates.append(_pres.present(req["gate_tag"])["short"])
        for tg in (req.get("session_of_tags") or []):
            gates.append(f"Session: {_pres.present(tg)['short']}")
        for tg in (req.get("artifact_tags") or []):
            gates.append(f"Artefakt: {_pres.present(tg)['short']}")
        # one quiet sub-line: what it builds on (↳) + the gates it must clear, dot-separated
        sub_bits = ([f"↳ {cons}"] if cons else []) + gates
        sub_html = h("div", {"class_": "pt-sub"}, " · ".join(sub_bits)) if sub_bits else ""
        cap = tk.get("capability", "")
        cap_html = h("span", {"class_": "pt-cap"}, cap) if cap else ""
        # skip the frame self-reference; link the rest, numbering same-kind sessions (Session 1…5)
        evs, _sn = [], 0
        for r in tk.get("produces", []):
            if r.get("id") == tk["id"]:
                continue
            if r.get("kind") == "session":
                _sn += 1
                evs.append(ev_chip(r, _sn))
            else:
                evs.append(ev_chip(r))
        ev_html = h("div", {"class_": "pt-evs"}, fragment(*evs)) if evs else ""
        cls = "ptask" + (" is-done" if st == "done" else "") + (" is-last" if last else "")
        return h("div", {"class_": cls},
                 h("div", {"class_": "pt-mark", "style": f"color:{clr}"}, raw(_icon(mark))),
                 h("div", {"class_": "pt-body"},
                   h("div", {"class_": "pt-row1"}, h("span", {"class_": "pt-title"}, tk.get("title", tk["id"])), cap_html),
                   sub_html, ev_html))

    secs = []
    for b, label in [("analyze", t("plan_bucket_analyze")), ("act", t("plan_bucket_act")),
                     ("verify", t("plan_bucket_verify"))]:
        bt = [tk for tk in tasks if tk["bucket"] == b]
        if not bt:
            continue
        bdone = sum(1 for tk in bt if tk["status"] == "done")
        rrows = [row(tk, i == len(bt) - 1) for i, tk in enumerate(bt)]
        secs.append(h("div", {"class_": "psec"},
                      h("div", {"class_": "psec-h"}, h("span", {}, label),
                        h("span", {"class_": "psec-n"}, f"{bdone}/{len(bt)}")),
                      h("div", {"class_": "psec-list"}, fragment(*rrows))))

    pct = round(100 * done / len(tasks)) if tasks else 0
    status_txt = (t("plan_complete") if complete else t("plan_progress", done=done, n=len(tasks)))
    fw_strip = _framework_strip(plan, tasks)
    head = h("div", {"class_": "plan-hd"},
             h("div", {"class_": "plan-goal"}, plan.get("goal", "")),
             fw_strip,
             h("div", {"class_": "plan-prog-row"},
               h("div", {"class_": "plan-prog" + (" full" if complete else "")},
                 h("i", {"style": f"width:{pct}%"})),
               h("span", {"class_": "plan-prog-txt"}, status_txt)),
             h("div", {"class_": "plan-sub"}, h("span", {"class_": "pt-cap"}, plan.get("methodology") or t("plan_freeform")),
               h("span", {}, t("n_tasks", n=len(tasks)))))
    # styles live in web_assets.py (.plan-*/.psec*/.ptask/.pt-*) — applied in the layout + the drawer
    return h("div", {"class_": "page"}, head, fragment(*secs))
