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

import base64
import json
import os
from importlib import resources
from typing import Any

from .. import config
from ..config import embeddings_enabled, utc_now_iso
from ..models import ResearchProject
from ..storage import Store
from .. import plan as _plan

from ._common import *  # noqa: F401,F403  (stable_id, slugify, _require_research_project, …)

FIXTURE_SCHEMA = "sonaloop_example/1"

# A fixture persona may declare `catalog_slug` instead of an inline profile: it then
# IS a real catalog persona (lived days, memory, the "From catalog" badge), so the
# showcase demonstrates the same personas a user would pull. The data comes from one
# of two places, in order: a live `catalog_pull` (fresh lived days + hi-res avatar,
# when the catalog is reachable), else the trimmed snapshot vendored beside the
# fixtures (offline/CI-safe, downscaled avatars). Set
# SONALOOP_EXAMPLES_REFRESH_FROM_CATALOG=0 to skip the live attempt entirely (the
# default the test suite uses — hermetic, no network).
_CATALOG_REFRESH_ENV = "SONALOOP_EXAMPLES_REFRESH_FROM_CATALOG"


def _vendored_catalog_dir():
    """The trimmed catalog snapshot shipped beside the fixtures (manifest + the
    selected personas/<slug>/ dirs) — the offline source of truth for example
    personas. None when it was not vendored (then only the live pull can supply them)."""
    d = _fixture_dir().joinpath("_catalog")
    return d if d.joinpath("manifest.json").is_file() else None


def _ensure_catalog_personas(slugs: list[str], store: Store) -> set[str]:
    """Make sure every catalog `slug` exists in the store with its lived days, the
    way a real `catalog_pull` leaves it (provenance.catalog → the "From catalog"
    badge). Tries a live pull first (fresh days + hi-res avatar) when refresh is on
    and the catalog is reachable, then fills any gap from the vendored snapshot.
    Returns the slugs that landed (so the caller can flag a hard miss)."""
    if not slugs:
        return set()
    embed = embeddings_enabled()
    landed: set[str] = set()
    if os.getenv(_CATALOG_REFRESH_ENV, "1").lower() not in {"0", "false", "no"}:
        try:
            out = catalog_pull(persona_slugs=slugs, embed=embed, store=store)  # noqa: F821 (bound)
            landed = {l["slug"] for l in out.get("landed", [])}
        except Exception:  # noqa: BLE001 — offline / unreachable catalog → vendored fallback
            landed = set()
    missing = [s for s in slugs if s not in landed]
    if missing and (vendor := _vendored_catalog_dir()) is not None:
        # import_snapshot globs personas/*/, so one call restores every vendored
        # persona (idempotent upserts); it stamps no provenance, so we add the
        # catalog stamp the badge keys off, exactly like a real pull would carry.
        try:
            import_snapshot(in_dir=str(vendor), store=store, embed=embed)  # noqa: F821 (bound)
        except ValueError:
            # import_snapshot computes a ROOT-relative summary AFTER every write; the
            # vendored snapshot lives in the package, not under ROOT, so that last step
            # trips. State is fully imported by then — same absorb as the catalog pull.
            store.commit()
        now = utc_now_iso()
        for slug in missing:
            per = store.get_persona(slug)
            if not per:
                continue
            if not (per.get("provenance") or {}).get("catalog"):
                per.setdefault("provenance", {})["catalog"] = {
                    "source": "sonaloop-data (vendored snapshot)", "slug": slug,
                    "repo": "jhoetter/sonaloop-data", "ref": "vendored", "pulled_at": now}
                store.upsert_persona(per, reason="example vendored catalog persona")
            landed.add(slug)
    return landed


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
        bucket = {"session": "usability_session", "url_artifact": "artifact",
                  "reference": "artifact"}.get(raw["kind"], raw["kind"])
        r["id"] = ctx[bucket][raw["key"]]
    return r


def _resolve_report_sections(raw_sections: list[dict[str, Any]], ctx: dict[str, Any]) -> list[dict[str, Any]]:
    sections: list[dict[str, Any]] = []
    for i, raw in enumerate(raw_sections or [], 1):
        sec = {k: v for k, v in raw.items()
               if k not in ("source_refs", "citations", "figures")}
        sec["id"] = sec.get("id") or f"sec{i}"
        sec["source_study_ids"] = list(sec.get("source_study_ids") or [])
        sec["source_study_ids"].extend(
            _resolve_ref(ref, ctx)["id"] for ref in raw.get("source_refs") or [])

        citations = []
        for c in raw.get("citations") or []:
            row = {k: v for k, v in c.items()
                   if k not in ("study_ref", "council_ref", "study", "council")}
            if c.get("study_ref"):
                row["study_id"] = _resolve_ref(c["study_ref"], ctx)["id"]
            elif c.get("study"):
                row["study_id"] = ctx["synthesis"][c["study"]]
            if c.get("council_ref"):
                row["council_id"] = _resolve_ref(c["council_ref"], ctx)["id"]
            elif c.get("council"):
                row["council_id"] = ctx["council"][c["council"]]
            if row.get("council_id") and not row.get("study_id"):
                row["study_id"] = row["council_id"]
            citations.append(row)
        sec["citations"] = citations

        figures = []
        for f in raw.get("figures") or []:
            fig = dict(f)
            if fig.get("key") and fig.get("kind") in ctx:
                fig["id"] = ctx[fig["kind"]][fig.pop("key")]
            figures.append(fig)
        sec["figures"] = figures
        sections.append(sec)
    return sections


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


def _question_text(raw: Any) -> str:
    return str(raw.get("text") if isinstance(raw, dict) else raw).strip()


def _fixture_created(raw: Any, fallback: str = "") -> str:
    if not isinstance(raw, dict):
        return fallback
    return str(raw.get("created_at") or fallback)


def _plan_ref(raw: dict[str, Any], ctx: dict[str, Any]) -> dict[str, str]:
    kind = str(raw.get("kind") or "")
    key = raw.get("key")
    if raw.get("id"):
        return {"kind": kind, "id": str(raw["id"])}
    bucket = {"url_artifact": "artifact", "reference": "artifact", "report": "synthesis",
              "session": "usability_session"}.get(kind, kind)
    if key is None or bucket not in ctx:
        return {"kind": kind, "id": str(key or "")}
    return {"kind": kind, "id": str(ctx[bucket][key])}


def _plan_ref_text(raw: dict[str, Any], ctx: dict[str, Any]) -> str:
    ref = _plan_ref(raw, ctx)
    return f"{ref['kind']}:{ref['id']}" if ref["kind"] and ref["id"] else ref["id"]


def _load_fixture_plan(fx: dict[str, Any], ctx: dict[str, Any], store: Store) -> None:
    raw = fx.get("plan")
    if not raw:
        root = {"id": "frame__root", "title": "Example frame", "bucket": "analyze",
                "capability": "frame", "status": "done", "consumes": [],
                "produces": [{"kind": "frame", "id": "frame__root"}],
                "frame": {"questions": [fx["project"].get("goal", "Example project")],
                          "hypotheses": [], "memory_refs": [f"example:{fx['slug']}"]}}
        plan = _plan.new_plan(ctx["project_id"], fx["project"].get("goal", ""), "", [root])
        _plan.save_plan(plan, store=store)
        return
    tasks = []
    for t in raw.get("tasks") or []:
        task = dict(t)
        task["produces"] = [_plan_ref(r, ctx) for r in t.get("produces") or []]
        tasks.append(task)
    plan = _plan.new_plan(ctx["project_id"], fx["project"].get("goal", ""),
                          raw.get("methodology", ""), tasks)
    plan["judgments"] = [
        {**{k: v for k, v in j.items() if k != "evidence_refs"},
         "evidence_refs": [_plan_ref_text(r, ctx) for r in j.get("evidence_refs") or []],
         "created_at": j.get("created_at") or utc_now_iso()}
        for j in raw.get("judgments") or []
    ]
    plan["parked_refs"] = [
        {**{k: v for k, v in p.items() if k != "refs"},
         "refs": [_plan_ref_text(r, ctx) for r in p.get("refs") or []],
         "created_at": p.get("created_at") or utc_now_iso()}
        for p in raw.get("parked_refs") or []
    ]
    _plan.save_plan(plan, store=store)


def _stamp_project_list_item(store: Store, project_id: str, field: str, item_id: str,
                             created_at: str = "") -> None:
    """Fixture-only timestamp repair for project-embedded collections.

    Several public record APIs intentionally stamp runtime creation time and do not expose
    `created_at`. Examples, however, are authored demo histories. When a fixture supplies a
    timestamp, replay it after validation so project views do not look chronologically incoherent.
    """
    if not created_at:
        return
    project = store.get_research_project(project_id) or {}
    items = list(project.get(field) or [])
    changed = False
    for it in items:
        if it.get("id") == item_id:
            it["created_at"] = created_at
            it.setdefault("updated_at", created_at)
            changed = True
            break
    if changed:
        project[field] = items
        project["updated_at"] = utc_now_iso()
        store.upsert_research_project(project)


def _stamp_entity_created(store: Store, kind: str, entity_id: str, created_at: str = "") -> None:
    if not created_at:
        return
    getters = {
        "council": store.get_council_session,
        "synthesis": store.get_synthesis,
        "hypothesis": store.get_hypothesis,
        "survey": store.get_survey,
        "decision": store.get_decision,
        "prototype": store.get_prototype,
        "session": store.get_usability_session,
    }
    updaters = {
        "council": store.insert_council_session,
        "synthesis": store.upsert_synthesis,
        "hypothesis": store.upsert_hypothesis,
        "survey": store.upsert_survey,
        "decision": store.upsert_decision,
        "prototype": store.upsert_prototype,
        "session": store.insert_usability_session,
    }
    rec = getters[kind](entity_id)
    if not rec:
        return
    rec["created_at"] = created_at
    rec.setdefault("updated_at", created_at)
    updaters[kind](rec)


def _attach_fixture_avatar(persona: dict[str, Any], raw: dict[str, Any], store: Store) -> dict[str, Any]:
    data = raw.get("avatar_base64")
    if not data:
        return persona
    rel = f"data/avatars/{persona['slug']}.png"
    dest = config.ROOT / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(base64.b64decode(data))
    avatar = {
        "path": rel,
        "source": "example_fixture",
        "catalog_slug": raw.get("avatar_catalog_slug"),
    }
    persona["avatar"] = {k: v for k, v in avatar.items() if v}
    persona["updated_at"] = utc_now_iso()
    store.upsert_persona(persona, reason="example fixture avatar")
    return persona


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

    # -- personas: either inline-authored profiles, or real catalog personas -----
    #    (a `catalog_slug` entry pulls the lived persona — days + memory + badge).
    catalog_slugs = [p["catalog_slug"] for p in fx.get("personas", []) if p.get("catalog_slug")]
    _ensure_catalog_personas(catalog_slugs, store)
    pids: dict[str, str] = {}
    for p in fx.get("personas", []):
        if p.get("catalog_slug"):
            rec = store.get_persona(p["catalog_slug"])
            if rec is None:
                raise RuntimeError(
                    f"example {slug!r}: catalog persona {p['catalog_slug']!r} could not be "
                    "loaded (no live catalog and no vendored snapshot)")
        else:
            rec = record_persona(p["description"], p["profile"],  # noqa: F821 (bound)
                                 segment_hint=_ns(slug, p["key"]), store=store)
            rec = _attach_fixture_avatar(rec, p, store)
        if rec.get("provenance", {}).get("example") != slug:
            # The removal stamp — mirrors sonaloop-data's provenance.catalog. Catalog
            # personas keep BOTH stamps: .catalog (badge) + .example (clean removal).
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
        "decision": {}, "note": {},
    }

    # -- open questions + the HMW reframe (stable per-text ids -> idempotent) ---
    if fx.get("open_questions"):
        oq_inputs = fx["open_questions"]
        oq_records = record_open_questions(pid, [_question_text(q) for q in oq_inputs], store=store)  # noqa: F821 (bound)
        created_by_text = {_question_text(q): _fixture_created(q, fx.get("open_questions_created_at", ""))
                           for q in oq_inputs}
        for oq in oq_records:
            if ts := created_by_text.get(oq.get("text", "")):
                oq["created_at"] = ts
                store.upsert_open_question(oq)
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

    # -- project assets + screenshot walkthrough scripts -----------------------
    # Example assets are content-addressed in the same project container. If a
    # fixture fixes the bytes for a stable filename (for example replacing a bad
    # screenshot seed with a valid PNG), prune the old fixture-owned records first
    # so re-loading the example repairs existing local databases instead of
    # leaving stale same-name assets beside the new ones.
    fixture_asset_names = {a.get("filename") for a in fx.get("assets", []) if a.get("filename")}
    if fixture_asset_names:
        project = store.get_research_project(pid) or {}
        before = list(project.get("assets") or [])
        after = [a for a in before if a.get("filename") not in fixture_asset_names]
        if len(after) != len(before):
            project["assets"] = after
            project["updated_at"] = utc_now_iso()
            store.upsert_research_project(project)
    for a in fx.get("assets", []):
        rec = attach_asset(  # noqa: F821 (bound)
            pid, content_base64=a["content_base64"], filename=a["filename"],
            kind=a.get("kind"), title=a.get("title", ""), notes=a.get("notes", ""),
            source=a.get("source", ""), direction=a.get("direction"), store=store)
        _stamp_project_list_item(store, pid, "assets", rec["id"], a.get("created_at", ""))
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
        _stamp_project_list_item(store, pid, "artifacts", rec["id"], a.get("created_at", ""))
        ctx["artifact"][a["key"]] = rec["id"]

    # -- hypotheses, phase 1: the bets stamped BEFORE exposure -------------------
    def _record_hypothesis(h: dict[str, Any]) -> None:
        hid = stable_id("hyp", pid, _ns(slug, h["key"]))  # noqa: F821 (bound)
        ctx["hypothesis"][h["key"]] = hid
        existing = store.get_hypothesis(hid)
        if existing and existing.get("status") != "open":
            _stamp_entity_created(store, "hypothesis", hid, h.get("created_at", ""))
            return                                  # resolved on a prior load — the audit trail stays
        record_hypothesis(pid, h["text"], h["prediction"],  # noqa: F821 (bound)
                          derived_from=[_resolve_ref(r, ctx) for r in h.get("derived_from") or []],
                          key=_ns(slug, h["key"]), store=store)
        _stamp_entity_created(store, "hypothesis", hid, h.get("created_at", ""))

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
        _stamp_entity_created(store, "council", sess["id"], c.get("created_at", ""))
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

    # -- surveys + imported responses -----------------------------------------
    for s in fx.get("surveys", []):
        rec = record_survey(  # noqa: F821 (bound)
            pid, s["title"], s["questions"], intro=s.get("intro", ""),
            derived_from=[_resolve_ref(r, ctx) for r in s.get("derived_from") or []],
            status=s.get("status", "draft"), slug=s.get("slug"), key=_ns(slug, s["key"]),
            store=store)["survey"]
        _stamp_entity_created(store, "survey", rec["id"], s.get("created_at", ""))
        ctx["survey"][s["key"]] = rec["id"]
        if s.get("responses"):
            import_survey_responses(rec["id"], responses=s["responses"],  # noqa: F821 (bound)
                                    source=s.get("response_source", "example"), store=store)

    # -- prototypes + usability sessions --------------------------------------
    for p in fx.get("prototypes", []):
        rec = scaffold_prototype(  # noqa: F821 (bound)
            p["slug"], p["name"], p["concept"], template=p.get("template"),
            project_id=pid, fidelity=p.get("fidelity"), store=store)
        _stamp_entity_created(store, "prototype", rec["id"], p.get("created_at", ""))
        ctx["prototype"][p["key"]] = rec["id"]
    for s in fx.get("usability_sessions", []):
        rec = record_usability_session(  # noqa: F821 (bound)
            pids[s["persona"]], _resolve_subject(s["subject"], ctx), s["fidelity"],
            s["date"], s["steps"], s["outcome"], statements=_resolve_statements(s.get("statements"), pids),
            project_id=pid, session_id=s.get("session_id"), key=_ns(slug, s["key"]), store=store)
        _stamp_entity_created(store, "session", rec["usability_session"]["id"], s.get("created_at", ""))
        ctx["usability_session"][s["key"]] = rec["usability_session"]["id"]

    # -- syntheses (keyed upsert) + register them on the project graph -----------
    # Loaded after sessions so fixture reports can cite session evidence directly.
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
        if s.get("scope") or s.get("lead") or s.get("sections"):
            rec = dict(rec)
            rec["scope"] = s.get("scope", rec.get("scope", "convergence"))
            rec["project_id"] = pid if rec["scope"] == "project" else rec.get("project_id", pid)
            rec["lead"] = s.get("lead", rec.get("lead", ""))
            rec["sections"] = _resolve_report_sections(s.get("sections") or [], ctx)
            store.upsert_synthesis(rec)
        _stamp_entity_created(store, "synthesis", rec["id"], s.get("created_at", ""))
        ctx["synthesis"][s["key"]] = rec["id"]
    project = store.get_research_project(pid)
    new_studies = [sid for sid in ctx["synthesis"].values()
                   if sid not in (project.get("study_ids") or [])]
    if new_studies:
        project["study_ids"] = list(project.get("study_ids") or []) + new_studies
        project["updated_at"] = utc_now_iso()
        store.upsert_research_project(project)

    # -- decision records (keyed upsert; refs must resolve by contract) ----------
    for d in fx.get("decisions", []):
        dec = record_decision(pid, d["title"], d["decision"],  # noqa: F821 (bound)
                              based_on=[_resolve_ref(r, ctx) for r in d.get("based_on") or []],
                              rejected=[_resolve_ref(r, ctx) for r in d.get("rejected") or []],
                              status=d.get("status", "proposed"), key=_ns(slug, d["key"]), store=store)
        _stamp_entity_created(store, "decision", dec["decision"]["id"], d.get("created_at", ""))
        ctx["decision"][d["key"]] = dec["decision"]["id"]

    # -- plain notes + sections (deduped: no keyed upsert on these paths) --------
    note_ids: dict[str, str] = {}
    existing_notes = {n["id"] for n in list_notes(pid, store=store)}  # noqa: F821 (bound)
    for n in fx.get("notes", []):
        nid = stable_id("note", pid, n["text"], n["created_at"])  # noqa: F821 (bound)
        note_ids[n["key"]] = nid
        if nid not in existing_notes:
            create_note(pid, n["text"], title=n.get("title", ""),  # noqa: F821 (bound)
                        created_at=n["created_at"], store=store)
    ctx["note"] = note_ids
    _load_fixture_plan(fx, ctx, store)
    existing_sections = {s["title"] for s in list_sections(pid, store=store)}  # noqa: F821 (bound)
    for sec in fx.get("sections", []):
        if sec["title"] in existing_sections:
            continue
        members = []
        for m in sec.get("members") or []:
            if m["kind"] == "synthesis":
                members.append(f"synthesis:{ctx['synthesis'][m['key']]}")
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
