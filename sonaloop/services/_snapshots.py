"""Portable snapshot export/import of generated state.

Split out of the original sonaloop/services.py (behavior-preserving).
Cross-module function references are bound at import time by services/__init__.py."""

from __future__ import annotations

import csv
import hashlib
import json
import random
import re
import uuid
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any

from .. import config
from ..config import (
    utc_now_iso, content_language, ensure_content_language, language_instruction,
    critic_threshold, critic_sample_k,
)
from ..models import (
    CalendarEvent,
    CouncilSession,
    DailySummary,
    Evidence,
    ExperienceEvent,
    OpenQuestion,
    PainPointObservation,
    Persona,
    PrototypeSession,
    Reflection,
    ResearchProject,
    SimulationResult,
    Synthesis,
)
from ..storage import Store
from ..taxonomy import GENERIC_TOOLS, normalized_tool_ids, normalized_tools
from .. import memory as memory_mod
from .. import evaluation as evaluation_mod
from ..llm_simulation import (
    build_cohort_critic_prompt,
    build_consolidation_prompt,
    build_synthesis_outline_prompt,
    build_synthesis_section_prompt,
    validate_synthesis_outline_payload,
    validate_synthesis_section_payload,
    build_digest_prompt,
    build_eval_critic_prompt,
    build_evidence_check_prompt,
    build_persona_revision_prompt,
    build_plan_prompt,
    build_profile_prompt,
    build_synthesis_prompt,
    validate_activity_payload,
    validate_cohort_critic_payload,
    validate_digest_payload,
    validate_eval_critic_payload,
    validate_evidence_check_payload,
    validate_memory_deltas_payload,
    validate_persona_revision_payload,
    validate_plan_payload,
    validate_profile_payload,
    validate_synthesis_payload,
)


from ._common import *  # noqa: F401,F403  (shared helpers + constants)


def _avatar_disk_path(stored_path: str) -> Path:
    """Resolve a persona's stored avatar path ("data/avatars/<slug>.png") to its on-disk
    location under the writable runtime — DATA_DIR, exactly as avatar.py writes it and
    web/_avatar.py serves it. NOT config.ROOT: in an installed deployment (cloud/prod) ROOT is
    site-packages and must never be written to/read from, so a ROOT-based avatar lands where
    nothing serves it (the imported-persona "no portrait" bug). In a source checkout DATA_DIR ==
    ROOT/data, so this is byte-for-byte the old path."""
    rel = stored_path[len("data/"):] if stored_path.startswith("data/") else stored_path
    return config.DATA_DIR / rel


def export_snapshot(out_dir: str | None = None, store: Store | None = None) -> dict[str, Any]:
    import shutil

    store = store or Store()
    base = Path(out_dir) if out_dir else (config.ROOT / "data" / "export")
    if not base.is_absolute():
        base = config.ROOT / base
    personas = store.list_personas()

    def _w(path: Path, obj: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")

    counts = {"personas": 0, "experience_events": 0, "entities": 0, "facts": 0, "avatars": 0}
    index = []
    for p in personas:
        pid = p["id"]
        pdir = base / "personas" / p["slug"]
        pdir.mkdir(parents=True, exist_ok=True)
        _w(pdir / "profile.json", p)
        (pdir / "SOUL.md").write_text(get_persona_soul(pid, store)["content"], encoding="utf-8")
        (pdir / "MEMORY.md").write_text(memory_mod.render_memory_md(store, p), encoding="utf-8")
        events = store.list_experience_events(pid)
        _w(pdir / "calendar.json", store.list_calendar_events(pid))
        _w(pdir / "experiences.json", events)
        _w(pdir / "daily_summaries.json", store.list_daily_summaries(pid))
        _w(pdir / "memory.json", {
            "entities": store.list_entities(pid),
            "entity_facts": store.list_persona_facts(pid),
            "event_links": store.list_event_entities(pid),
            "threads": store.list_threads(pid),
            "plans": store.list_plans(pid),
            "digests": store.list_digests(pid),
        })
        _w(pdir / "eval.json", {"reports": store.list_eval_reports(pid), "anomalies": store.list_anomalies(pid)})
        avatar = p.get("avatar")
        if avatar and avatar.get("path"):
            src = _avatar_disk_path(avatar["path"])
            if src.exists():
                shutil.copyfile(src, pdir / "avatar.png")
                counts["avatars"] += 1
        counts["personas"] += 1
        counts["experience_events"] += len(events)
        counts["entities"] += len(store.list_entities(pid))
        counts["facts"] += len(store.list_persona_facts(pid))
        # updated_at rides the index so catalog consumers (catalog_status) get exact
        # per-persona staleness from the manifest alone, without fetching every profile.
        index.append({"slug": p["slug"], "display_name": p["display_name"],
                      "role": p.get("role", {}).get("title"), "has_avatar": bool(avatar),
                      "updated_at": p.get("updated_at")})

    _w(base / "world_context.json", store.list_world_context())
    sessions = store.list_council_sessions()
    for sess in sessions:
        _w(base / "councils" / f"{sess['id']}.json", sess)
    counts["councils"] = len(sessions)
    syns = store.list_syntheses()
    for syn in syns:
        _w(base / "syntheses" / f"{syn['id']}.json", syn)
    counts["syntheses"] = len(syns)
    # Research projects ride the snapshot too — they own the artifacts + the evidence
    # assets (ticket attach-evidence-files-mcp: "assets persist in the snapshot").
    # Asset binaries are copied alongside so the round-trip restores citable evidence.
    projects = store.list_research_projects()
    counts["projects"] = len(projects)
    counts["assets"] = 0
    for pr in projects:
        _w(base / "projects" / f"{pr['id']}.json", pr)
        for a in pr.get("assets", []):
            from ._project_assets import _assets_dir
            src = _assets_dir() / Path(a["asset_path"]).name
            if src.exists():
                (base / "assets").mkdir(parents=True, exist_ok=True)
                shutil.copyfile(src, base / "assets" / src.name)
                counts["assets"] += 1
    _w(base / "manifest.json", {
        "generated_at": utc_now_iso(), "schema_version": store.schema_version(),
        "embedding_models": store.embedding_models(),   # which spaces produced the (re-derivable) vectors
        "counts": counts, "personas": index,
        "note": "Reproducible snapshot of generated state. Rebuild the DB by re-running the simulation loop; this is the portable, local-only artifact (the SQLite DB stays gitignored).",
    })
    store.commit()
    return {"out_dir": str(base.relative_to(config.ROOT)), "counts": counts}



def import_snapshot(in_dir: str | None = None, store: Store | None = None, embed: bool = True) -> dict[str, Any]:
    """Rebuild the runtime DB (+ avatars, SOUL/MEMORY) from a portable snapshot.

    The portable round-trip: on another machine, copy data/export/ across (it is
    local-only, not in git), then `sonaloop import-snapshot` reproduces
    this exact state — no re-generation. Embeddings are re-derived (not stored,
    to keep snapshots lean); pass embed=False to skip (recall stays keyword-only
    until backfilled).
    """
    import shutil

    store = store or Store()
    base = Path(in_dir) if in_dir else (config.ROOT / "data" / "export")
    if not base.is_absolute():
        base = config.ROOT / base
    if not (base / "manifest.json").exists():
        raise FileNotFoundError(f"No snapshot manifest at {base}")
    pdirs = sorted((base / "personas").glob("*/")) if (base / "personas").exists() else []
    counts = {"personas": 0, "experience_events": 0, "calendar_events": 0, "entities": 0,
              "facts": 0, "threads": 0, "plans": 0, "digests": 0, "avatars": 0}

    def _load(path: Path, default):
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default

    for pdir in pdirs:
        persona = _load(pdir / "profile.json", None)
        if not persona:
            continue
        # avatar: copy the snapshot png back into a web-served runtime path.
        # Catalog snapshots commonly store profile.avatar.path as the snapshot-local
        # "avatar.png"; normalize that to data/avatars/<slug>.png so imported
        # catalog personas render a portrait instead of creating ./avatar.png.
        avatar = persona.get("avatar")
        avatar_file = pdir / "avatar.png"
        if avatar and avatar_file.exists():
            avatar = dict(avatar)
            raw_path = str(avatar.get("path") or "").strip()
            if raw_path.startswith("data/"):
                rel_path = raw_path
            else:
                slug = persona.get("slug") or pdir.name
                rel_path = f"data/avatars/{slug}.png"
                avatar["path"] = rel_path
                persona["avatar"] = avatar
            dest = _avatar_disk_path(rel_path)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(avatar_file, dest)
            counts["avatars"] += 1
        store.upsert_persona(persona, reason="import_snapshot")
        pid = persona["id"]
        for ev in _load(pdir / "calendar.json", []):
            store.insert_calendar_event(ev); counts["calendar_events"] += 1
        for ev in _load(pdir / "experiences.json", []):
            store.insert_experience_event(ev); counts["experience_events"] += 1
        for s in _load(pdir / "daily_summaries.json", []):
            store.upsert_daily_summary(s)
        mem = _load(pdir / "memory.json", {})
        for ent in mem.get("entities", []):
            store.upsert_entity(ent); counts["entities"] += 1
        for f in mem.get("entity_facts", []):
            store.insert_entity_fact(f); counts["facts"] += 1
        for link in mem.get("event_links", []):
            store.link_event_entity(link["event_id"], link["entity_id"], link.get("persona_id", pid), link.get("role"))
        for th in mem.get("threads", []):
            store.upsert_thread(th); counts["threads"] += 1
        for pl in mem.get("plans", []):
            store.upsert_plan(pl); counts["plans"] += 1
        for dg in mem.get("digests", []):
            store.upsert_digest(dg); counts["digests"] += 1
        ev_data = _load(pdir / "eval.json", {})
        for rep in ev_data.get("reports", []):
            store.insert_eval_report(rep)
        for an in ev_data.get("anomalies", []):
            store.insert_anomaly(an)
        # re-render SOUL/MEMORY from the restored persona
        persona["soul"] = write_soul(persona, store)
        store.upsert_persona(persona, reason="import_snapshot soul")
        counts["personas"] += 1

    for w in _load(base / "world_context.json", []):
        store.insert_world_context(w)
    cdir = base / "councils"
    if cdir.exists():
        for cf in sorted(cdir.glob("*.json")):
            store.insert_council_session(_load(cf, None))
            counts["councils"] = counts.get("councils", 0) + 1
    sdir = base / "syntheses"
    if sdir.exists():
        for sf in sorted(sdir.glob("*.json")):
            store.upsert_synthesis(_load(sf, None))
            counts["syntheses"] = counts.get("syntheses", 0) + 1
    prdir = base / "projects"
    if prdir.exists():
        for pf in sorted(prdir.glob("*.json")):
            store.upsert_research_project(_load(pf, None))
            counts["projects"] = counts.get("projects", 0) + 1
    adir = base / "assets"
    if adir.exists():
        from ._project_assets import _assets_dir
        dest_dir = _assets_dir()
        dest_dir.mkdir(parents=True, exist_ok=True)
        for af in sorted(adir.glob("*")):
            shutil.copyfile(af, dest_dir / af.name)
            counts["assets"] = counts.get("assets", 0) + 1
    store.commit()

    embedded = {}
    if embed:
        for pdir in pdirs:
            persona = _load(pdir / "profile.json", None)
            if persona:
                embedded[persona["slug"]] = memory_mod.backfill_persona_embeddings(store, persona["id"])
    return {"in_dir": str(base.relative_to(config.ROOT)), "counts": counts,
            "embeddings": "skipped" if not embed else "re-derived"}


# ===================================================================== #
# Synthesis — a study arc: chain of councils -> cross-council learnings. #
# ===================================================================== #
