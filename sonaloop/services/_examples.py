"""Loadable example projects (ticket loadable-example-projects): one-command demo data.

Shipped example projects live INSIDE the wheel as committed fixtures
(`sonaloop/examples/*.json`) — authored content, like docs. `load_example` replays a
fixture through the REAL record_* service layer (never the Store directly), so every
validation contract holds, every deterministic aggregation (price-ladder cliffs,
head-to-head tallies, red-team cases) is computed server-side, and every lifecycle
event fires — the Activity feed is populated like a real session's would be.

Idempotency: every entity loads under a stable, example-namespaced key
(`example:<slug>:<key>`), so the record layer's keyed upserts make a re-load an
update, never a duplicate. The only record paths without keyed upserts (idea notes,
plain notes, sections) are deduplicated here by their natural identity (text/title).

Removal: the fixture itself is the registry of what was loaded — every id is
re-derivable from the slug + keys, and personas additionally carry a
`provenance.example` stamp (mirroring sonaloop-data's `provenance.catalog`), so
`remove_example` deletes exactly the example's entities and nothing of the user's.

Host-authors-all-text contract: it applies to RUNTIME generation. The fixture prose
is committed, human-reviewed demo content — the same status as documentation.
"""
from __future__ import annotations

import json
from importlib import resources
from typing import Any

from ..config import utc_now_iso
from ..models import ResearchProject
from ..storage import Store

from ._common import *  # noqa: F401,F403  (stable_id, slugify, _require_research_project, …)

FIXTURE_SCHEMA = "sonaloop_example/1"


# ------------------------------------------------------------------- fixtures

def _fixture_dir():
    """The packaged fixture directory — resolved via importlib.resources so the
    examples work from a wheel install exactly like from a source checkout."""
    return resources.files("sonaloop").joinpath("examples")


def _fixtures() -> list[dict[str, Any]]:
    out = []
    for entry in sorted(_fixture_dir().iterdir(), key=lambda e: e.name):
        if entry.name.endswith(".json"):
            out.append(json.loads(entry.read_text(encoding="utf-8")))
    return out


def _fixture(slug: str) -> dict[str, Any]:
    for fx in _fixtures():
        if fx.get("slug") == slug:
            return fx
    known = [fx.get("slug") for fx in _fixtures()]
    raise KeyError(f"Unknown example: {slug!r} (available: {known})")


# ------------------------------------------------------------ deterministic ids

def _ns(slug: str, key: str) -> str:
    return f"example:{slug}:{key}"


def _example_project_id(slug: str) -> str:
    return stable_id("rproject", "example", slug)  # noqa: F821 (bound)


def _oq_id(project_id: str, question: str) -> str:
    # Mirrors record_open_questions' id derivation (stable per project + text).
    return stable_id("oq", project_id, question)  # noqa: F821 (bound)


# ------------------------------------------------------------------- resolvers

def _resolve_ref(raw: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
    """Fixture Ref -> real Ref: `key` resolves through the per-kind id maps built
    during the load; `question` resolves to the project's open-question id."""
    r = {k: v for k, v in raw.items() if k not in ("key", "question")}
    if raw.get("question"):
        r["id"] = _oq_id(ctx["project_id"], raw["question"])
    elif raw.get("key") is not None:
        r["id"] = ctx[raw["kind"]][raw["key"]]
    return r


def _resolve_subject(raw: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
    """Fixture session subject -> real subject. Flow/prototype ids are produced while
    replaying the fixture; URL subjects pass through unchanged."""
    out = {k: v for k, v in raw.items() if k not in ("key",)}
    if raw.get("key") is not None:
        out["id"] = ctx[raw["kind"]][raw["key"]]
    return out


def _resolve_statements(raw: Any, pids: dict[str, str]) -> list[dict[str, Any]]:
    """Fixture statements -> artifact statements: `persona` keys become ids, a bare
    `about` string becomes a prompt ref (q0 / opt:A / price:€19 / red_team)."""
    out = []
    for s in raw or []:
        s = dict(s)
        s["persona_id"] = pids[s.pop("persona")]
        if isinstance(s.get("about"), str):
            s["about"] = {"kind": "prompt", "id": s["about"]}
        out.append(s)
    return out


def _with_persona_ids(rows: Any, pids: dict[str, str]) -> list[dict[str, Any]]:
    out = []
    for r in rows or []:
        r = dict(r)
        r["persona_id"] = pids[r.pop("persona")]
        out.append(r)
    return out


def _hypothesis_phase(h: dict[str, Any]) -> str:
    """Hypotheses that only cite open questions are stamped BEFORE the councils run
    (the bet precedes exposure); ones citing councils/syntheses load after."""
    kinds = {r.get("kind") for r in h.get("derived_from") or []}
    return "pre" if kinds <= {"open_question"} else "post"


# ------------------------------------------------------------------ public API

def list_examples(store: Store | None = None) -> list[dict[str, Any]]:
    """The shipped example projects: slug, title, tagline, and whether each is
    currently loaded into this database."""
    store = store or Store()
    out = []
    for fx in _fixtures():
        pid = _example_project_id(fx["slug"])
        out.append({
            "slug": fx["slug"],
            "title": fx["project"]["title"],
            "tagline": fx.get("tagline", ""),
            "loaded": store.get_research_project(pid) is not None,
            "project_id": pid,
            "url": f"/projects/{pid}",
        })
    return out


def load_example(slug: str, store: Store | None = None) -> dict[str, Any]:  # noqa: C901 (one linear replay)
    """Load one shipped example project end-to-end through the record_* layer.
    Idempotent: re-loading updates the same stable ids — no duplicates."""
    store = store or Store()
    fx = _fixture(slug)
    pid = _example_project_id(slug)
    now = utc_now_iso()

    # -- project container (fixed id/slug so a re-load updates in place) --------
    project = store.get_research_project(pid)
    created = project is None
    if created:
        project = ResearchProject(
            id=pid, slug=f"example-{slug}"[:60], title=fx["project"]["title"],
            goal=fx["project"].get("goal", ""), description=fx["project"].get("description", ""),
            persona_ids=[], study_ids=[], study_tags={}, themes=[],
            status="active", created_at=now, updated_at=now, council_ids=[],
        ).to_dict()
    else:
        project.update({k: fx["project"].get(k, project.get(k, ""))
                        for k in ("title", "goal", "description")})
        project["updated_at"] = now
    project["example"] = slug                      # provenance: which fixture owns this container
    store.upsert_research_project(project)
    if created:
        emit_lifecycle_event("project.created", {"project_id": pid,  # noqa: F821 (bound)
                                                 "title": project["title"]}, store)

    # -- personas (record_persona derives a stable id from description+hint) ----
    pids: dict[str, str] = {}
    for p in fx.get("personas", []):
        rec = record_persona(p["description"], p["profile"],  # noqa: F821 (bound)
                             segment_hint=_ns(slug, p["key"]), store=store)
        if rec.get("provenance", {}).get("example") != slug:
            # The removal stamp — mirrors sonaloop-data's provenance.catalog.
            rec.setdefault("provenance", {})["example"] = slug
            store.upsert_persona(rec, reason="example fixture provenance")
        pids[p["key"]] = rec["id"]
    project = store.get_research_project(pid)
    missing = [i for i in pids.values() if i not in (project.get("persona_ids") or [])]
    if missing:
        project["persona_ids"] = list(project.get("persona_ids") or []) + missing
        project["updated_at"] = utc_now_iso()
        store.upsert_research_project(project)

    ctx: dict[str, Any] = {
        "project_id": pid, "asset": {}, "flow": {}, "artifact": {}, "prototype": {}, "survey": {},
        "usability_session": {}, "council": {}, "synthesis": {}, "hypothesis": {},
    }

    # -- open questions + the HMW reframe (stable per-text ids -> idempotent) ---
    if fx.get("open_questions"):
        record_open_questions(pid, fx["open_questions"], store=store)  # noqa: F821 (bound)
    hmw = fx.get("hmw")
    if hmw:
        record_hmw_reframe(pid, hmw["problem"], hmw["questions"], store=store)  # noqa: F821 (bound)

    # -- idea notes (diverge) — deduped by text, create_note has no keyed upsert -
    if fx.get("ideas"):
        existing_texts = {n["text"] for n in list_ideas(pid, store=store)}  # noqa: F821 (bound)
        for idea in fx["ideas"]:
            if idea["text"].strip() in existing_texts:
                continue
            record_ideas(pid, [{  # noqa: F821 (bound)
                "text": idea["text"], "persona_id": pids[idea["persona"]],
                "hmw_ref": _oq_id(pid, hmw["questions"][idea["hmw"]]),
                "cluster": idea.get("cluster"),
            }], store=store)

    # -- project assets + screenshot flows (artifact-first walkthroughs) --------
    for a in fx.get("assets", []):
        rec = attach_asset(  # noqa: F821 (bound)
            pid, content_base64=a["content_base64"], filename=a["filename"],
            kind=a.get("kind"), title=a.get("title", ""), notes=a.get("notes", ""),
            source=a.get("source", ""), direction=a.get("direction"), store=store)
        ctx["asset"][a["key"]] = rec["id"]
    for f in fx.get("flows", []):
        rec = define_flow(  # noqa: F821 (bound)
            pid, f["title"],
            [{"asset_id": ctx["asset"][s["asset"]], "caption": s.get("caption", "")}
             for s in f.get("steps") or []],
            key=_ns(slug, f["key"]), store=store)
        ctx["flow"][f["key"]] = rec["id"]
    for a in fx.get("artifacts", []):
        rec = add_artifact(  # noqa: F821 (bound)
            pid, a["url"], kind=a.get("kind", "url"), title=a.get("title", ""),
            label=a.get("label"), capture=bool(a.get("capture", True)),
            key=_ns(slug, a["key"]), store=store)
        ctx["artifact"][a["key"]] = rec["id"]

    # -- hypotheses, phase 1: the bets stamped BEFORE exposure -------------------
    def _record_hypothesis(h: dict[str, Any]) -> None:
        hid = stable_id("hyp", pid, _ns(slug, h["key"]))  # noqa: F821 (bound)
        ctx["hypothesis"][h["key"]] = hid
        existing = store.get_hypothesis(hid)
        if existing and existing.get("status") != "open":
            return                                  # resolved on a prior load — the audit trail stays
        record_hypothesis(pid, h["text"], h["prediction"],  # noqa: F821 (bound)
                          derived_from=[_resolve_ref(r, ctx) for r in h.get("derived_from") or []],
                          key=_ns(slug, h["key"]), store=store)

    hypotheses = fx.get("hypotheses", [])
    for h in hypotheses:
        if _hypothesis_phase(h) == "pre":
            _record_hypothesis(h)

    # -- councils (every format rides record_*'s keyed idempotent upsert) --------
    for c in fx.get("councils", []):
        key = _ns(slug, c["key"])
        fmt = c.get("format", "council")
        stmts = _resolve_statements(c.get("statements"), pids)
        common = dict(summary=c.get("summary", ""), exec_summary=c.get("exec_summary", ""),
                      selection_reason=c.get("selection_reason", ""), key=key,
                      created_at=c.get("created_at"), store=store)
        if fmt == "price_ladder":
            sess = record_price_ladder(pid, c["prompt"], c["price_points"],  # noqa: F821 (bound)
                                       responses=_with_persona_ids(c.get("responses"), pids),
                                       statements=stmts, **common)
        elif fmt == "head_to_head":
            vm = dict(c.get("variant_meta") or {})
            if vm.get("order_shown"):
                vm["order_shown"] = {pids[k]: v for k, v in vm["order_shown"].items()}
            if vm.get("hypothesis"):
                vm["hypothesis_id"] = ctx["hypothesis"][vm.pop("hypothesis")]
            sess = record_head_to_head(pid, c["prompt"], c["options"],  # noqa: F821 (bound)
                                       preferences=_with_persona_ids(c.get("preferences"), pids),
                                       statements=stmts, variant_meta=vm or None, **common)
        elif fmt == "red_team":
            sess = record_red_team(pid, c["prompt"],  # noqa: F821 (bound)
                                   objections=_with_persona_ids(c.get("objections"), pids),
                                   endorsements=_with_persona_ids(c.get("endorsements"), pids),
                                   stance=c.get("stance", "against"), statements=stmts, **common)
        elif fmt == "ideation":
            by_text = {n["text"]: n["id"] for n in list_ideas(pid, store=store)}  # noqa: F821 (bound)
            shortlist = [{"idea_id": by_text[p["idea"]], "rationale": p["rationale"]}
                         for p in c.get("shortlist") or []]
            sess = record_ideation_summary(pid, c["problem"], shortlist,  # noqa: F821 (bound)
                                           statements=stmts, **common)
        else:
            sess = record_council(pid, c["prompt"], [pids[k] for k in c.get("personas", [])],  # noqa: F821 (bound)
                                  statements=stmts, votes=c.get("votes"),
                                  proposal=c.get("proposal", ""),
                                  questions=c.get("questions"), **common)
        ctx["council"][c["key"]] = sess["id"]

    # -- hypotheses, phase 2 (derived from councils) + results -------------------
    for h in hypotheses:
        if _hypothesis_phase(h) == "post":
            _record_hypothesis(h)
    for r in fx.get("hypothesis_results", []):
        hid = ctx["hypothesis"][r["hypothesis"]]
        if (store.get_hypothesis(hid) or {}).get("status") == "open":
            record_hypothesis_result(hid, r["observed_value"], _resolve_ref(r["source"], ctx),  # noqa: F821 (bound)
                                     note=r.get("note", ""), store=store)

    # -- syntheses (keyed upsert) + register them on the project graph -----------
    for s in fx.get("syntheses", []):
        payload = dict(s.get("payload") or {})
        payload["references"] = [{"council_id": ctx["council"][r["council"]],
                                  "role": r.get("role", "")} for r in payload.get("references") or []]
        payload["citations"] = [{"kind": "council", "ref": ctx["council"][c["council"]],
                                 "quote": c.get("quote", "")} for c in payload.get("citations") or []]
        for f in payload.get("findings") or []:
            f["refs"] = [_resolve_ref(r, ctx) for r in f.get("refs") or []]
        payload["statements"] = _resolve_statements(payload.get("statements"), pids)
        rec = record_synthesis(s["title"], s.get("start_input", ""),  # noqa: F821 (bound)
                               council_ids=[ctx["council"][k] for k in s.get("councils") or []],
                               payload=payload, goal=s.get("goal", ""),
                               key=_ns(slug, s["key"]), created_at=s.get("created_at"), store=store)
        ctx["synthesis"][s["key"]] = rec["id"]
    project = store.get_research_project(pid)
    new_studies = [sid for sid in ctx["synthesis"].values()
                   if sid not in (project.get("study_ids") or [])]
    if new_studies:
        project["study_ids"] = list(project.get("study_ids") or []) + new_studies
        project["updated_at"] = utc_now_iso()
        store.upsert_research_project(project)

    # -- surveys + imported responses -----------------------------------------
    for s in fx.get("surveys", []):
        rec = record_survey(  # noqa: F821 (bound)
            pid, s["title"], s["questions"], intro=s.get("intro", ""),
            derived_from=[_resolve_ref(r, ctx) for r in s.get("derived_from") or []],
            status=s.get("status", "draft"), slug=s.get("slug"), key=_ns(slug, s["key"]),
            store=store)["survey"]
        ctx["survey"][s["key"]] = rec["id"]
        if s.get("responses"):
            import_survey_responses(rec["id"], responses=s["responses"],  # noqa: F821 (bound)
                                    source=s.get("response_source", "example"), store=store)

    # -- prototypes + usability sessions --------------------------------------
    for p in fx.get("prototypes", []):
        rec = scaffold_prototype(  # noqa: F821 (bound)
            p["slug"], p["name"], p["concept"], template=p.get("template"),
            project_id=pid, fidelity=p.get("fidelity"), store=store)
        ctx["prototype"][p["key"]] = rec["id"]
    for s in fx.get("usability_sessions", []):
        rec = record_usability_session(  # noqa: F821 (bound)
            pids[s["persona"]], _resolve_subject(s["subject"], ctx), s["fidelity"],
            s["date"], s["steps"], s["outcome"], statements=_resolve_statements(s.get("statements"), pids),
            project_id=pid, session_id=s.get("session_id"), key=_ns(slug, s["key"]), store=store)
        ctx["usability_session"][s["key"]] = rec["usability_session"]["id"]

    # -- decision records (keyed upsert; refs must resolve by contract) ----------
    for d in fx.get("decisions", []):
        record_decision(pid, d["title"], d["decision"],  # noqa: F821 (bound)
                        based_on=[_resolve_ref(r, ctx) for r in d.get("based_on") or []],
                        rejected=[_resolve_ref(r, ctx) for r in d.get("rejected") or []],
                        status=d.get("status", "proposed"), key=_ns(slug, d["key"]), store=store)

    # -- plain notes + sections (deduped: no keyed upsert on these paths) --------
    note_ids: dict[str, str] = {}
    existing_notes = {n["id"] for n in list_notes(pid, store=store)}  # noqa: F821 (bound)
    for n in fx.get("notes", []):
        nid = stable_id("note", pid, n["text"], n["created_at"])  # noqa: F821 (bound)
        note_ids[n["key"]] = nid
        if nid not in existing_notes:
            create_note(pid, n["text"], title=n.get("title", ""),  # noqa: F821 (bound)
                        created_at=n["created_at"], store=store)
    existing_sections = {s["title"] for s in list_sections(pid, store=store)}  # noqa: F821 (bound)
    for sec in fx.get("sections", []):
        if sec["title"] in existing_sections:
            continue
        members = []
        for m in sec.get("members") or []:
            if m["kind"] == "synthesis":
                members.append(ctx["synthesis"][m["key"]])
            elif m["kind"] == "note":
                members.append(f"note:{note_ids[m['key']]}")
        create_section(pid, sec["title"], kind=sec.get("kind", "theme"),  # noqa: F821 (bound)
                       member_ids=members, note=sec.get("note", ""), store=store)

    emit_lifecycle_event("example.loaded", {"project_id": pid, "slug": slug,  # noqa: F821 (bound)
                                            "title": fx["project"]["title"]}, store)
    return {
        "slug": slug, "project_id": pid, "url": f"/projects/{pid}",
        "title": fx["project"]["title"],
        "counts": {
            "personas": len(pids),
            "councils": len(ctx["council"]),
            "syntheses": len(ctx["synthesis"]),
            "surveys": len(ctx["survey"]),
            "assets": len(fx.get("assets", [])),
            "references": len(ctx["artifact"]),
            "flows": len(ctx["flow"]),
            "prototypes": len(ctx["prototype"]),
            "sessions": len(ctx["usability_session"]),
            "hypotheses": len(hypotheses),
            "decisions": len(fx.get("decisions", [])),
            "open_questions": len(store.list_open_questions(pid)),
            "ideas": len(list_ideas(pid, store=store)),  # noqa: F821 (bound)
            "notes": len(list_notes(pid, store=store)),  # noqa: F821 (bound)
            "sections": len(list_sections(pid, store=store)),  # noqa: F821 (bound)
        },
    }


def remove_example(slug: str, store: Store | None = None) -> dict[str, Any]:
    """Remove ONE example's entities — and nothing else. Every id is re-derived from
    the fixture (slug + keys); personas are matched by their `provenance.example`
    stamp. User-created data is never touched."""
    store = store or Store()
    fx = _fixture(slug)
    pid = _example_project_id(slug)
    deleted = {"project": 0, "personas": 0, "councils": 0, "syntheses": 0,
               "hypotheses": 0, "decisions": 0, "surveys": 0, "prototypes": 0,
               "sessions": 0}
    for s in fx.get("usability_sessions", []):
        deleted["sessions"] += store.delete_usability_session(
            stable_id("usession", _ns(slug, s["key"])))  # noqa: F821 (bound)
    for p in fx.get("prototypes", []):
        deleted["prototypes"] += store.delete_prototype(p["slug"])
    for s in fx.get("surveys", []):
        deleted["surveys"] += store.delete_survey(
            stable_id("survey", _ns(slug, s["key"])))  # noqa: F821 (bound)
    for c in fx.get("councils", []):
        deleted["councils"] += store.delete_council_session(
            stable_id("council", _ns(slug, c["key"])))  # noqa: F821 (bound)
    for s in fx.get("syntheses", []):
        deleted["syntheses"] += store.delete_synthesis(
            stable_id("synthesis", _ns(slug, s["key"])))  # noqa: F821 (bound)
    for h in fx.get("hypotheses", []):
        deleted["hypotheses"] += store.delete_hypothesis(
            stable_id("hyp", pid, _ns(slug, h["key"])))  # noqa: F821 (bound)
    for d in fx.get("decisions", []):
        deleted["decisions"] += store.delete_decision(
            stable_id("dec", pid, _ns(slug, d["key"])))  # noqa: F821 (bound)
    if store.get_research_project(pid) is not None:
        # Cascades the project's open questions; notes/sections ride the record.
        delete_research_project(pid, store=store)  # noqa: F821 (bound)
        deleted["project"] = 1
    for p in store.list_personas():
        if (p.get("provenance") or {}).get("example") == slug:
            delete_persona(p["id"], store=store)  # noqa: F821 (bound)
            deleted["personas"] += 1
    return {"slug": slug, "deleted": deleted}
