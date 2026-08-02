"""Low-level shared helpers, IDs, date math, requires, module constants.

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



def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:60] or f"persona-{uuid.uuid4().hex[:8]}"



def stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"



def persona_dir(persona: dict[str, Any]) -> Path:
    # Runtime working dir for rendered SOUL.md/MEMORY.md. Lives under data/ (all
    # generated state is under data/; gitignored). The portable, local-only copy
    # is data/export/ (see export_snapshot/import_snapshot).
    slug = str(persona.get("slug") or "")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", slug):
        raise ValueError(f"unsafe persona slug for runtime directory: {slug!r}")
    return config.partition_dir() / "personas" / slug


def runtime_path_ref(path: Path) -> str:
    """Stable persisted/display path for a runtime file.

    Source checkouts keep the historical ``data/...`` value.  Installed builds
    whose writable data root lives outside the package store an absolute path;
    ``Path(ROOT) / absolute`` remains compatible with older readers.
    """
    try:
        return str(path.relative_to(config.ROOT))
    except ValueError:
        return str(path)



def soul_path(persona: dict[str, Any]) -> Path:
    return persona_dir(persona) / "SOUL.md"



def _parse_date(value: str | None) -> date:
    if value:
        return date.fromisoformat(value)
    return date.today()



def _event_time(day: date, hour: int, minute: int = 0) -> datetime:
    return datetime.combine(day, time(hour, minute))



def _make_rng(seed: str | None, *parts: str) -> random.Random:
    base = seed or "|".join(parts)
    return random.Random(int(hashlib.sha256(base.encode()).hexdigest(), 16))



def _period_bounds(anchor: date, view: str) -> tuple[date, date]:
    if view == "week":
        start = anchor - timedelta(days=anchor.weekday())
        return start, start + timedelta(days=6)
    if view == "month":
        start = anchor.replace(day=1)
        next_month = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
        return start, next_month - timedelta(days=1)
    if view == "year":
        return anchor.replace(month=1, day=1), anchor.replace(month=12, day=31)
    return anchor, anchor



def write_export(content: str, path: str | Path) -> str:
    out = Path(path)
    if config.postgres_row_tenancy_enabled():
        part = config.partition_dir()
        if not out.is_absolute():
            out = part / "exports" / out
        if not out.resolve().is_relative_to(part.resolve()):
            raise ValueError(f"export path escapes the active workspace partition: {path!r}")
    elif not out.is_absolute():
        out = config.ROOT / out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(content, encoding="utf-8")
    return str(out)


def web_url(path: str) -> str:
    """Absolute inspector URL for `path` — hosted deployments set
    SONALOOP_PUBLIC_BASE_URL (e.g. https://app.sonaloop.com) so tool results can
    say WHERE to look at what was just created; locally the default inspector."""
    import os
    base = os.getenv("SONALOOP_PUBLIC_BASE_URL") or "http://127.0.0.1:8787"
    return base.rstrip("/") + path


def write_export_bytes(data: bytes, path: str | Path) -> str:
    """Write a binary export (pdf/pptx). Relative paths resolve under the active
    data partition's exports/ (== DATA_DIR/exports/ outside multi-tenant requests)."""
    from ..config import partition_dir
    out = Path(path)
    if not out.is_absolute():
        out = partition_dir() / "exports" / out
    if config.postgres_row_tenancy_enabled() and not out.resolve().is_relative_to(
            partition_dir().resolve()):
        raise ValueError(f"export path escapes the active workspace partition: {path!r}")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(data)
    return str(out)


def export_download_url(path: str | Path) -> str:
    """The absolute, auth-gated download URL for an export file — the web app serves
    DATA_DIR at /data, so anything written below it (exports/, the share bundles) is
    one click away. '' for paths outside the served tree (an absolute out_path the
    caller chose) — a server filesystem path is NOT a hand-off to a remote user."""
    from .. import config
    try:
        resolved = Path(path).resolve()
        if config.postgres_row_tenancy_enabled() and not resolved.is_relative_to(
                config.partition_dir().resolve()):
            return ""
        rel = resolved.relative_to(Path(config.DATA_DIR).resolve())
    except ValueError:
        return ""
    return web_url("/data/" + rel.as_posix())


# ===================================================================== #
# Memory & multi-resolution orchestration                               #
# spec/memory-and-simulation-architecture.md §3, §4, §4A, §12.          #
# Pattern: brief_* gathers context + builds the host prompt; the host   #
# LLM authors JSON; record_*/put_* validate and persist. No server text.#
# ===================================================================== #



_ANTI_STEERING = (
    "Do not steer toward BIM, AI, automation, or any product direction unless the "
    "persona's source/evidence supports it. Prefer ordinary work, skepticism, and stalls."
)



def memory_path(persona: dict[str, Any]) -> Path:
    return persona_dir(persona) / "MEMORY.md"



def _scope_bounds(anchor: date, scope: str) -> tuple[date, date]:
    if scope == "week":
        start = anchor - timedelta(days=anchor.weekday())
        return start, start + timedelta(days=6)
    if scope == "month":
        start = anchor.replace(day=1)
        nxt = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
        return start, nxt - timedelta(days=1)
    if scope == "quarter":
        q = (anchor.month - 1) // 3
        start = date(anchor.year, q * 3 + 1, 1)
        end_month_first = (date(anchor.year, q * 3 + 3, 28) + timedelta(days=4)).replace(day=1)
        return start, end_month_first - timedelta(days=1)
    if scope == "year":
        return anchor.replace(month=1, day=1), anchor.replace(month=12, day=31)
    return anchor, anchor



def _require_persona(store: Store, persona_id: str) -> dict[str, Any]:
    persona = store.get_persona(persona_id)
    if not persona:
        raise KeyError(f"Unknown persona: {persona_id}")
    return persona


# ---- Consolidation (Phase C) ---------------------------------------------



CRITIC_THRESHOLD = 4  # each dimension must reach this for semantic "top" (see config.critic_threshold)



EDGE_TYPES = {"spawned_from", "refines", "contrasts", "depends_on", "duplicates", "answers"}



OQ_STATUSES = {"open", "being_studied", "answered", "dropped"}



def _require_research_project(store: Store, project_id: str) -> dict[str, Any]:
    p = store.get_research_project(project_id)
    if not p:
        raise KeyError(f"Unknown research project: {project_id}")
    return p


__all__ = [
    "slugify", "stable_id", "persona_dir", "runtime_path_ref", "soul_path", "_parse_date", "_event_time",
    "_make_rng", "_period_bounds", "write_export", "_ANTI_STEERING", "memory_path",
    "_scope_bounds", "_require_persona", "CRITIC_THRESHOLD", "EDGE_TYPES", "OQ_STATUSES",
    "_require_research_project",
]
