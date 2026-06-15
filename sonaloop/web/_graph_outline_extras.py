"""Outline absorption of the remaining primitives (spec/ux-contract.md §3.4, UX P2).

Decisions, surveys, hypotheses, open questions and assets become outline ROWS in their phase
context — the appendix sections retired. Placement (with honest fallbacks):

  - decision  → the phase of the verify task that PRODUCED it (plan `produces` carries a
                decision ref) or whose gate judgment CITES it (`judgments[].evidence_refs`);
                fallback: the phase active at created_at.
  - survey    → the phase of the act task that produced it (mapped onto the frame it consumes,
                exactly like services._evidence_node); fallback like decisions.
  - hypothesis / open question → the phase active at created_at (the latest plan-bound node at
                or before the timestamp; the project's first phase before anything exists).
  - asset     → deliverables (direction out) join the final phase group (the Deliver group,
                §7.2) sorted last; evidence assets land in an *Evidence* sub-group inside the
                phase active at created_at (cheap v1 — node-adjacent placement upgrades once
                plan_graph carries grounding edges).

Pure item-building (the unified outline-item shape _graph_outline renders); the page route
fetches the record lists (it holds the Store) and passes them in. Rounds are chronological, so
every extra row borrows the round of its nearest preceding plan node.
"""
from __future__ import annotations

from ._i18n import t

# Row kinds that open as a slide-over (spec §8.1: click = the kind's FULL detail page sliding
# over the outline; the drawer URL IS the row's canonical href). Universally true for every kind
# that HAS a detail page — assets included since UX U8 (/assets/{id}; the row's download chip
# keeps the file itself one click away); references, flows and open questions have their own
# detail pages since the artifact-inventory audit closed the Library gap.
# (A tuple head keeps the kind-vocabulary grep gates clean — no kind-literal set heads in web/.)
DRAWER_KINDS = frozenset(("council", "synthesis", "report", "note", "prototype", "session",
                          "decision", "survey", "hypothesis", "asset", "url_artifact",
                          "flow", "open_question"))


def drawer_url(rkind: str, href: str) -> str | None:
    """The slide-over URL for an outline row: its OWN canonical detail href (§8.1 — pushState
    makes it the address, so it must be a real internal page), or None for kinds without one."""
    if rkind not in DRAWER_KINDS or not href or not href.startswith("/"):
        return None
    return href


# ------------------------------------------------------------------ phase placement helpers

def _task_step(task: dict) -> str:
    """A task's layout column (the same binding services._evidence_node uses): a verify task IS
    its step (the converge waist); an act task fans from the frame it consumes."""
    if task.get("bucket") == "verify":
        return task.get("id", "")
    cons = task.get("consumes") or []
    return cons[0] if cons else task.get("id", "")


def producing_step(plan: dict | None, eid: str, kinds: tuple[str, ...]) -> str | None:
    """The step of the task whose `produces` carries a {kind, id} ref to this record."""
    for task in (plan or {}).get("tasks", []):
        for r in task.get("produces", []):
            if r.get("kind") in kinds and r.get("id") == eid:
                return _task_step(task)
    return None


def _judging_step(plan: dict | None, eid: str) -> str | None:
    """The step of the task whose gate judgment cites this record (evidence_refs carry bare ids)."""
    tasks = {task["id"]: task for task in (plan or {}).get("tasks", [])}
    for j in (plan or {}).get("judgments", []):
        if eid in (j.get("evidence_refs") or []) and j.get("task_id") in tasks:
            return _task_step(tasks[j["task_id"]])
    return None


def _phase_round_at(ts: str, plan_nodes: list[dict], node_round: dict[str, int],
                    default_phase: str) -> tuple[str, int]:
    """(phase, round) active at a timestamp: the latest plan-bound node at/before `ts` carries
    both; before anything exists the project's first phase, round 0."""
    best = None
    for n in plan_nodes:                       # chronological (sorted by the caller)
        if (n.get("created_at") or "") <= (ts or ""):
            best = n
        else:
            break
    if best is not None:
        return best.get("phase", ""), node_round.get(best["study_id"], 0)
    return default_phase, 0


# ------------------------------------------------------------------------- the item builders

def extra_outline_items(graph: dict, *, decisions: list, hypotheses: list, surveys: list,
                        pmeta: dict, node_round: dict[str, int], default_phase: str) -> list[dict]:
    """The absorbed kinds as outline items (decisions/hypotheses/surveys from the page route;
    open questions + assets ride the graph). `pmeta` maps step key -> (order, label)."""
    plan = graph.get("plan")
    nodes = sorted((n for n in graph.get("nodes", []) if n.get("phase", "") in pmeta),
                   key=lambda n: n.get("created_at", ""))
    last_key = max(pmeta, key=lambda k: pmeta[k][0]) if pmeta else ""

    def item(oid, *, color, title, kind, href, pk, ts, rkind, node, order=None, anchor=None,
             lead=None, external=False, evidence=False, deliverable=False, rnd=None):
        po, pl = pmeta.get(pk, (99, ""))
        if rnd is None:
            rnd = _phase_round_at(ts, nodes, node_round, default_phase)[1]
        it = {"oid": oid, "color": color, "title": title, "kind": kind, "href": href,
              "plabel": pl or kind, "po": po, "round": rnd, "order": order or ts, "ts": ts,
              "indent": 0, "last_child": False, "rkind": rkind, "node": node,
              "evidence": evidence, "deliverable": deliverable, "pk": pk or ""}
        if anchor:
            it["anchor"] = anchor
        if lead:
            it["lead"] = str(lead)
        if external:
            it["external"] = True
        return it

    out: list[dict] = []
    for d in decisions:
        ts = d.get("created_at", "")
        pk = (producing_step(plan, d["id"], ("decision",)) or _judging_step(plan, d["id"])
              or _phase_round_at(ts, nodes, node_round, default_phase)[0])
        out.append(item(d["id"], color="#c0476b", title=d.get("title", ""),
                        kind=t("decision_kind"), href=f'/decisions/{d["id"]}', pk=pk, ts=ts,
                        rkind="decision", node=d, anchor=f'dec-{d["id"]}'))
    for s in surveys:
        ts = s.get("created_at", "")
        pk = (producing_step(plan, s["id"], ("survey",))
              or _phase_round_at(ts, nodes, node_round, default_phase)[0])
        out.append(item(s["id"], color="#6b7cff", title=s.get("title", ""),
                        kind=t("survey_kind"), href=f'/surveys/{s["id"]}', pk=pk, ts=ts,
                        rkind="survey", node=s))
    for x in hypotheses:
        ts = x.get("created_at", "")
        pk = _phase_round_at(ts, nodes, node_round, default_phase)[0]
        out.append(item(x["id"], color="#e0820a", title=x.get("text", ""),
                        kind=t("hypothesis_kind"), href=f'/hypotheses/{x["id"]}', pk=pk, ts=ts,
                        rkind="hypothesis", node=x, anchor=f'hyp-{x["id"]}'))
    for o in graph.get("open_questions") or []:
        ts = o.get("created_at", "")
        pk = _phase_round_at(ts, nodes, node_round, default_phase)[0]
        out.append(item(o["id"], color="#9aa0a6", title=o.get("text", ""),
                        kind=t("open_question_kind"), href=f'/open-questions/{o["id"]}', pk=pk, ts=ts,
                        rkind="open_question", node=o))
    for a in graph.get("assets") or []:
        ts = a.get("created_at", "")
        deliverable = a.get("direction") == "out"
        if deliverable:                       # the final Deliver group, after the reports (§7.2)
            pk, order, rnd = last_key, f"~~{ts}", max(node_round.values(), default=0)
        else:                                 # the phase's Evidence sub-group, after its rows
            pk, order, rnd = _phase_round_at(ts, nodes, node_round, default_phase)[0], f"~{ts}", None
        # V9: the renderer presents asset items as `.sl-file--row` FILE rows (_graph_outline.row)
        # — identity badge, one download/open affordance, body = the /assets/{id} slide-over.
        out.append(item(a["id"], color="#0f9d8f" if deliverable else "#8a6d3b",
                        title=a.get("title") or a.get("filename", ""),
                        kind=t("asset_kind_" + (a.get("kind") or "file")), href=f'/assets/{a["id"]}',
                        pk=pk, ts=ts, rkind="asset", node=a, order=order, rnd=rnd,
                        evidence=not deliverable, deliverable=deliverable))
    return out
