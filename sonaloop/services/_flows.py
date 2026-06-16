"""Screenshot flows: a persona walks an ordered flow of REAL screens and shows
exactly where it drops off (ticket prototype-walkthrough-dropoff — the killer
use-case, artifact-first by design).

~80% of walkthrough value is more reliable via reaction-to-artifacts than via
live app control, so this path needs NO browser: a flow is an ordered sequence
of screens drawn from the project's evidence assets (uploaded screenshots,
captured prototype shots), each step citable by asset id. The walkthrough
brief hands the persona context + the ordered screens; the HOST looks at each
screen (`view_asset` returns real pixels) and authors the dual timeline through
the existing usability-session recorder — friction per step, the drop-off point
with its reason, predicted behaviors with likelihoods. `flow_funnel` is the
segment view: where personas abandon and why, aggregated across the cohort.

Live actuation stays out of scope here (see the walkthrough/live modules);
this is its reliable counterpart."""

from __future__ import annotations

from typing import Any

from ..config import utc_now_iso
from ..storage import Store

from ._common import *  # noqa: F401,F403  (stable_id, _require_research_project, …)


def _project_flows(project: dict[str, Any]) -> list[dict[str, Any]]:
    return project.setdefault("flows", [])


def define_flow(project_id: str, title: str, steps: list[dict[str, Any]],
                key: str | None = None, store: Store | None = None) -> dict[str, Any]:
    """Define an ordered flow from the project's evidence assets. Each step is
    {asset_id, caption?} — the asset must exist on the project (attach screenshots
    first via attach_asset / attach_prototype_shot). Stored on the project like
    artifacts/assets; a stable `key` makes re-definition an idempotent upsert."""
    store = store or Store()
    project = _require_research_project(store, project_id)  # noqa: F821 (bound)
    if not (title or "").strip():
        raise ValueError("flow title is required")
    if not steps:
        raise ValueError("steps is required: the ORDERED screens [{asset_id, caption?}] — "
                         "an empty flow walks nowhere")
    valid_assets = {a["id"]: a for a in project.get("assets") or []}
    out_steps = []
    for i, raw in enumerate(steps):
        aid = (raw or {}).get("asset_id")
        if aid not in valid_assets:
            raise KeyError(f"steps[{i}].asset_id {aid!r} is not an asset on this project — "
                           "attach the screenshot first (attach_asset)")
        asset = valid_assets[aid]
        if asset.get("kind") not in ("image", "screenshot"):
            raise ValueError(f"steps[{i}] asset {aid} is {asset.get('kind')!r} — flow steps must "
                             "be image/screenshot assets (the persona reacts to pixels)")
        out_steps.append({"index": i, "asset_id": aid,
                          "caption": str((raw or {}).get("caption") or asset.get("title") or ""),
                          "url": asset.get("url", "")})
    fid = stable_id("flow", key) if key else stable_id("flow", project["id"], title, utc_now_iso())  # noqa: F821 (bound)
    flows = _project_flows(project)
    existing = next((f for f in flows if f["id"] == fid), None)
    record = {"id": fid, "title": title.strip(), "steps": out_steps,
              "created_at": (existing or {}).get("created_at") or utc_now_iso(),
              "updated_at": utc_now_iso()}
    if existing:
        flows[flows.index(existing)] = record
    else:
        flows.append(record)
    project["updated_at"] = utc_now_iso()
    store.upsert_research_project(project)
    return record


def list_flows(project_id: str, store: Store | None = None) -> list[dict[str, Any]]:
    store = store or Store()
    project = _require_research_project(store, project_id)  # noqa: F821 (bound)
    return [{"id": f["id"], "title": f["title"], "steps": len(f["steps"]),
             "updated_at": f.get("updated_at", "")} for f in _project_flows(project)]


def get_flow(project_id: str, flow_id: str, store: Store | None = None) -> dict[str, Any]:
    store = store or Store()
    project = _require_research_project(store, project_id)  # noqa: F821 (bound)
    for f in _project_flows(project):
        if f["id"] == flow_id or f.get("title") == flow_id:
            return f
    raise KeyError(f"Unknown flow '{flow_id}' in project {project_id}")


def flow_screens_brief(project_id: str, flow_id: str,
                       store: Store | None = None) -> list[dict[str, Any]]:
    """The ordered screens a walkthrough brief carries: per step the caption + the
    view_asset call that returns the REAL pixels — no live browser anywhere."""
    flow = get_flow(project_id, flow_id, store=store)
    return [{"index": s["index"], "caption": s["caption"], "asset_id": s["asset_id"],
             "view": f"view_asset('{project_id}', '{s['asset_id']}')"}
            for s in flow["steps"]]


def brief_flow_walkthrough(persona_id: str, project_id: str, flow_id: str,
                           store: Store | None = None) -> dict[str, Any]:
    """GATHER one persona's screen-sequence session for a defined flow: the loaded persona
    context (via the usability-session brief) + the ordered screens. The host LOOKS at
    every screen (view_asset) and authors one timeline step per screen — honest friction,
    would_continue, the drop-off where THIS persona would actually bail — then persists
    with record_usability_session(subject={kind:'flow', id:<flow id>}, fidelity='artifact')
    so flow_funnel aggregates the cohort."""
    store = store or Store()
    flow = get_flow(project_id, flow_id, store=store)
    subject = {"kind": "flow", "id": flow["id"], "label": flow["title"]}
    brief = brief_usability_session(persona_id, subject, "artifact",  # noqa: F821 (bound)
                                    project_id=project_id, store=store)
    screens = flow_screens_brief(project_id, flow["id"], store=store)
    brief["flow"] = {"id": flow["id"], "title": flow["title"], "steps": screens}
    brief["how_to_drive"] = (
        "SCREEN-SEQUENCE SESSION — no live browser. Walk the screens IN ORDER: for each step call "
        "the listed view_asset(...) and LOOK at the real screen before reacting; author one "
        "timeline step per screen (state.screen = the asset id + what is actually visible). "
        "React as THIS persona: friction on the canonical scale, would_continue honestly — set "
        "outcome.dropoff_step at the screen where the persona would genuinely bail, with the "
        "reason in that step's verdict. Author outcome.predicted_behaviors with canonical "
        "likelihoods + evidence refs. Record with the SAME subject so the funnel aggregates.")
    return brief


def flow_funnel(project_id: str, flow_id: str, store: Store | None = None) -> dict[str, Any]:
    """The segment view of one flow: the step-indexed funnel (entered / continued /
    dropped, with reasons and the dropping personas) joined with the flow's captions —
    'where personas abandon and why', aggregated across the cohort."""
    store = store or Store()
    flow = get_flow(project_id, flow_id, store=store)
    funnel = get_session_funnel("flow", flow["id"], store=store)  # noqa: F821 (bound)
    sessions = store.list_usability_sessions(subject_kind="flow", subject_key=flow["id"])
    captions = {s["index"]: s["caption"] for s in flow["steps"]}
    for row in funnel["rows"]:
        row["caption"] = captions.get(row["step"], "")
        row["personas"] = sorted({s.get("persona_id", "") for s in sessions
                                  if (s.get("outcome") or {}).get("dropoff_step") == row["step"]
                                  and not (s.get("outcome") or {}).get("completed")} - {""})
    biggest = max((r for r in funnel["rows"] if r["dropped"]),
                  key=lambda r: r["dropped"], default=None)
    return {**funnel, "flow": {"id": flow["id"], "title": flow["title"], "steps": len(flow["steps"])},
            "biggest_dropoff": ({"step": biggest["step"], "caption": biggest["caption"],
                                 "dropped": biggest["dropped"], "reasons": biggest["drop_reasons"]}
                                if biggest else None)}
