"""The queryable substrate: programmatic read paths + durable persona chat
(ticket queryable-substrate; the contract docs/substrate.md documents).

Today's value is locked inside interactive runs. This module exposes it as
infrastructure: lean, paginated, filterable queries over personas / projects /
councils / syntheses, one structured `get_study_result` per project (the shape
recurring jobs poll), and a durable multi-turn persona chat built on the same
host-authored contract as brief_ask (the server never generates text).

Three contract guarantees every consumer can rely on:
- VERSIONED: every envelope carries `substrate_version`; shape changes bump it.
- STABLE: ids are the durable handles; ordering is deterministic
  (newest-first, id tie-break) so pagination never shuffles.
- GUARDED: every read/write passes the access-guard seam — a no-op locally,
  the multi-tenant enforcement point for sonaloop-cloud (register_access_guard).
"""

from __future__ import annotations

import json
from typing import Any, Callable

from ..config import ensure_content_language, language_instruction, utc_now_iso
from ..storage import Store

from ._common import *  # noqa: F401,F403  (stable_id, _require_research_project, …)
from ._authoring import PERSONA_VOICE_CONTRACT


SUBSTRATE_VERSION = 1
_MAX_LIMIT = 200

# --- The auth/permission seam (cloud overrides; local default = allow all) -----
# A guard is fn(operation: str, resource: dict) -> None, raising PermissionError to
# deny. sonaloop-cloud registers one at startup to scope queries to a workspace;
# locally the list stays empty and every call passes.
_ACCESS_GUARDS: list[Callable[[str, dict[str, Any]], None]] = []


def register_access_guard(guard: Callable[[str, dict[str, Any]], None]) -> None:
    """Register a substrate access guard (the multi-tenant seam). Guards run on
    EVERY substrate operation, in registration order; raise PermissionError to deny."""
    _ACCESS_GUARDS.append(guard)


def clear_access_guards() -> None:
    _ACCESS_GUARDS.clear()


def _guard(operation: str, resource: dict[str, Any]) -> None:
    for g in list(_ACCESS_GUARDS):
        g(operation, resource)


def check_access(operation: str, resource: dict[str, Any] | None = None) -> None:
    """Run the registered access guards over a NON-substrate operation — the same
    seam register_access_guard feeds. The web inspector's write routes call this
    with `web.<action>` operations so sonaloop-cloud's tenancy guard can hold its
    editor+ write rule in multi-user installs; locally it is a no-op. Raises
    PermissionError to deny, like every guard call."""
    _guard(operation, resource or {})


# --- Envelope / paging helpers --------------------------------------------------

def _clamp(limit: int, offset: int) -> tuple[int, int]:
    return max(1, min(_MAX_LIMIT, int(limit))), max(0, int(offset))


def _page(items: list[dict[str, Any]], limit: int, offset: int) -> dict[str, Any]:
    limit, offset = _clamp(limit, offset)
    window = items[offset:offset + limit]
    nxt = offset + limit if offset + limit < len(items) else None
    return {"substrate_version": SUBSTRATE_VERSION, "total": len(items),
            "limit": limit, "offset": offset, "next_offset": nxt, "items": window}


def _hit(q: str | None, row: dict[str, Any]) -> bool:
    return not q or q.lower() in json.dumps(row, ensure_ascii=False).lower()


def _since_ok(since: str | None, row: dict[str, Any]) -> bool:
    if not since:
        return True
    ts = row.get("updated_at") or row.get("created_at") or ""
    return ts >= since


def _newest_first(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(rows, key=lambda r: (r.get("updated_at") or r.get("created_at") or "", r["id"]),
                  reverse=True)


# --- Queries: lean, filterable, paginated ---------------------------------------

def query_personas(q: str | None = None, limit: int = 50, offset: int = 0,
                   store: Store | None = None) -> dict[str, Any]:
    """Lean persona rows (the compact summary shape), filterable by free text."""
    store = store or Store()
    _guard("query_personas", {"q": q})
    rows = list_personas(store=store, compact=True)  # noqa: F821 (bound)
    rows = [r for r in rows if _hit(q, r)]
    rows.sort(key=lambda r: r["id"])  # compact rows carry no timestamps; id order is stable
    return _page(rows, limit, offset)


def _project_row(p: dict[str, Any]) -> dict[str, Any]:
    return {"id": p["id"], "slug": p.get("slug", ""), "title": p.get("title", ""),
            "goal": p.get("goal", ""), "status": p.get("status", "active"),
            "methodology": p.get("methodology", ""),
            "councils": len(p.get("council_ids") or []),
            "artifacts": len(p.get("artifacts") or []), "assets": len(p.get("assets") or []),
            "persona_ids": p.get("persona_ids") or [],
            "created_at": p.get("created_at", ""), "updated_at": p.get("updated_at", "")}


def query_projects(status: str | None = None, q: str | None = None, since: str | None = None,
                   limit: int = 50, offset: int = 0, store: Store | None = None) -> dict[str, Any]:
    """Lean research-project rows; filter by status, free text, and `since`
    (ISO timestamp lower bound on updated_at). Newest first, id tie-break."""
    store = store or Store()
    _guard("query_projects", {"status": status, "q": q})
    rows = [_project_row(p) for p in store.list_research_projects()]
    rows = [r for r in rows
            if (not status or r["status"] == status) and _hit(q, r) and _since_ok(since, r)]
    return _page(_newest_first(rows), limit, offset)


def _council_row(c: dict[str, Any]) -> dict[str, Any]:
    return {"id": c["id"], "project_id": c.get("project_id", ""), "prompt": c.get("prompt", ""),
            "persona_ids": c.get("persona_ids") or [],
            "statements": len(c.get("statements") or []), "votes": len(c.get("votes") or []),
            "questions": len(c.get("questions") or []), "created_at": c.get("created_at", "")}


def query_councils(project_id: str | None = None, persona_id: str | None = None,
                   q: str | None = None, since: str | None = None,
                   limit: int = 50, offset: int = 0, store: Store | None = None) -> dict[str, Any]:
    """Lean council rows; filter by project, participant, free text, `since`."""
    store = store or Store()
    _guard("query_councils", {"project_id": project_id, "persona_id": persona_id, "q": q})
    rows = [_council_row(c) for c in store.list_council_sessions()]
    rows = [r for r in rows
            if (not project_id or r["project_id"] == project_id)
            and (not persona_id or persona_id in r["persona_ids"])
            and _hit(q, r) and _since_ok(since, r)]
    return _page(_newest_first(rows), limit, offset)


def _synthesis_row(s: dict[str, Any]) -> dict[str, Any]:
    return {"id": s["id"], "title": s.get("title", ""), "status": s.get("status", ""),
            "goal": s.get("goal", ""), "council_ids": s.get("council_ids") or [],
            "findings": len(s.get("findings") or []), "statements": len(s.get("statements") or []),
            "created_at": s.get("created_at", ""), "updated_at": s.get("updated_at", "")}


def query_syntheses(status: str | None = None, q: str | None = None, since: str | None = None,
                    limit: int = 50, offset: int = 0, store: Store | None = None) -> dict[str, Any]:
    """Lean synthesis (answer/report node) rows; filter by status, free text, `since`."""
    store = store or Store()
    _guard("query_syntheses", {"status": status, "q": q})
    rows = [_synthesis_row(s) for s in store.list_syntheses()]
    rows = [r for r in rows
            if (not status or r["status"] == status) and _hit(q, r) and _since_ok(since, r)]
    return _page(_newest_first(rows), limit, offset)


def get_study_result(project_id: str, store: Store | None = None) -> dict[str, Any]:
    """ONE structured result per project — the shape automations poll: the lean
    project row, the live run state, council rows, and the FULL syntheses that
    belong to the project's graph (the answer nodes). Versioned like every
    substrate envelope; built on the plan-evidence graph (the source of truth)."""
    store = store or Store()
    project = _require_research_project(store, project_id)  # noqa: F821 (bound)
    _guard("get_study_result", {"project_id": project["id"]})
    graph = get_project_graph(project["id"], store=store)  # noqa: F821 (bound)
    syn_ids = [str(n["study_id"]).split(":", 1)[1] for n in graph["nodes"]
               if str(n["study_id"]).startswith("synthesis:")]
    syntheses = [s for s in (store.get_synthesis(sid) for sid in dict.fromkeys(syn_ids)) if s]
    councils = [_council_row(store.get_council_session(cid) or {"id": cid})
                for cid in project.get("council_ids") or []]
    try:
        run_state = project_run_state(project["id"], store=store)  # noqa: F821 (bound)
    except Exception:
        run_state = None
    try:
        health = project_health(project["id"], store=store)  # noqa: F821 (bound)
    except Exception:
        health = None
    try:
        predictions = aggregate_predictions(project["id"], store=store)  # noqa: F821 (bound)
    except Exception:
        predictions = None
    return {"substrate_version": SUBSTRATE_VERSION,
            "project": _project_row(project),
            "run_state": run_state,
            "project_health": health,
            "councils": councils,
            "syntheses": syntheses,
            "predictions": predictions,
            "open_questions": graph.get("open_questions") or [],
            "counts": graph.get("counts") or {}}


# --- Durable persona chat (host-authored, like everything else) -----------------

def chat_with_persona(persona_id: str, message: str, chat_id: str | None = None,
                      store: Store | None = None) -> dict[str, Any]:
    """Open (or continue) a durable chat with ONE persona. Returns the persona's
    loaded agent context + the prior turns; the HOST authors the in-character
    reply and persists the exchange with record_chat_turn (same gather → author →
    write-back contract as brief_ask, plus durable history)."""
    store = store or Store()
    persona = store.get_persona(persona_id)
    if not persona:
        raise KeyError(f"Unknown persona: {persona_id}")
    _guard("chat_with_persona", {"persona_id": persona["id"], "chat_id": chat_id})
    if chat_id:
        chat = store.get_persona_chat(chat_id)
        if not chat:
            raise KeyError(f"Unknown chat: {chat_id}")
        if chat["persona_id"] != persona["id"]:
            raise ValueError(f"Chat {chat_id} belongs to persona {chat['persona_id']}, not {persona['id']}")
    else:
        chat = {"id": stable_id("chat", persona["id"], utc_now_iso()),  # noqa: F821 (bound)
                "persona_id": persona["id"], "turns": [],
                "created_at": utc_now_iso(), "updated_at": utc_now_iso()}
        store.upsert_persona_chat(chat)
    history = "\n".join(f"[{t['role']}] {t['text']}" for turn in chat["turns"]
                        for t in ({"role": "user", "text": turn["user_message"]},
                                  {"role": persona["display_name"], "text": turn["persona_reply"]}))
    language = ensure_content_language(message)
    ctx = prepare_persona_agent_context(persona["id"], message, store=store)  # noqa: F821 (bound)
    approved = store.list_persona_memory_proposals(persona["id"], "approved")[:8]
    continuity_notes = [str(note)[:500] for item in approved
                        for note in ((item.get("proposal") or {}).get("continuity_notes") or [])][:24]
    continuity = "\n".join(f"- {note}" for note in continuity_notes)[:6_000]
    agent_context = ctx["agent_context"]
    if continuity:
        agent_context += (
            "\n\n## Approved Conversation Continuity\n"
            "These notes came from prior synthetic chats. They preserve conversational "
            "continuity only; they are not evidence or lived experience.\n" + continuity)
    return {
        "schema": "persona_chat", "substrate_version": SUBSTRATE_VERSION,
        "chat_id": chat["id"], "persona_id": persona["id"],
        "display_name": persona["display_name"], "message": message,
        "turns": len(chat["turns"]), "history": history,
        "soul_path": ctx["soul_path"], "agent_context": agent_context,
        "instructions": (
            "Answer AS this persona, grounded in agent_context AND consistent with the prior "
            "turns in `history` — do not force support; say what is uncertain if the record is "
            "thin. Then persist the exchange: record_chat_turn(persona_id, chat_id, "
            "user_message=<the message>, persona_reply=<your authored answer>). "
            + language_instruction(language) + PERSONA_VOICE_CONTRACT
        ),
    }


def record_chat_turn(persona_id: str, chat_id: str, user_message: str, persona_reply: str,
                     refs: list[dict[str, Any]] | None = None,
                     store: Store | None = None) -> dict[str, Any]:
    """Persist one authored chat exchange. The chat is the durable, queryable
    artifact; emits `chat.recorded` so automations can react."""
    store = store or Store()
    chat = store.get_persona_chat(chat_id)
    if not chat:
        raise KeyError(f"Unknown chat: {chat_id}")
    if chat["persona_id"] != persona_id:
        raise ValueError(f"Chat {chat_id} belongs to persona {chat['persona_id']}, not {persona_id}")
    if not (user_message or "").strip() or not (persona_reply or "").strip():
        raise ValueError("Both user_message and persona_reply are required.")
    _guard("record_chat_turn", {"persona_id": persona_id, "chat_id": chat_id})
    chat["turns"].append({"idx": len(chat["turns"]), "user_message": user_message,
                          "persona_reply": persona_reply, "refs": refs or [],
                          "created_at": utc_now_iso()})
    chat["updated_at"] = utc_now_iso()
    store.upsert_persona_chat(chat)
    emit_lifecycle_event("chat.recorded", {"chat_id": chat_id, "persona_id": persona_id,  # noqa: F821 (bound)
                                           "turns": len(chat["turns"])}, store)
    return {"chat_id": chat_id, "persona_id": persona_id, "turns": len(chat["turns"]),
            "updated_at": chat["updated_at"]}


def get_chat(chat_id: str, store: Store | None = None) -> dict[str, Any]:
    """One chat with its full turn history."""
    store = store or Store()
    chat = store.get_persona_chat(chat_id)
    if not chat:
        raise KeyError(f"Unknown chat: {chat_id}")
    _guard("get_chat", {"chat_id": chat_id, "persona_id": chat["persona_id"]})
    return chat


def list_chats(persona_id: str | None = None, limit: int = 50, offset: int = 0,
               store: Store | None = None) -> dict[str, Any]:
    """Lean chat rows (newest first), optionally scoped to one persona."""
    store = store or Store()
    _guard("list_chats", {"persona_id": persona_id})
    rows = [{"id": c["id"], "persona_id": c["persona_id"], "turns": len(c.get("turns") or []),
             "last_message": (c.get("turns") or [{}])[-1].get("user_message", ""),
             "created_at": c.get("created_at", ""), "updated_at": c.get("updated_at", "")}
            for c in store.list_persona_chats(persona_id)]
    return _page(rows, limit, offset)


# --- The documented contract -----------------------------------------------------

def substrate_schema() -> dict[str, Any]:
    """The versioned substrate contract: envelope shape, row schemas, filters,
    the chat flow, and the access-guard seam. THIS is what automations pin to."""
    return {
        "substrate_version": SUBSTRATE_VERSION,
        "envelope": {"substrate_version": "int — bumped on shape changes",
                     "total": "int", "limit": "int (≤200)", "offset": "int",
                     "next_offset": "int|null — pass back to continue", "items": "[row]"},
        "ordering": "newest first (updated_at|created_at desc), id tie-break — stable for pagination",
        "rows": {
            "persona": {"id": "…", "slug": "…", "display_name": "…", "age_range": "…",
                        "role": "…", "segment": "…"},
            "project": {"id": "…", "slug": "…", "title": "…", "goal": "…", "status": "…",
                        "methodology": "…", "councils": "int", "artifacts": "int", "assets": "int",
                        "persona_ids": "[id]", "created_at": "iso", "updated_at": "iso"},
            "council": {"id": "…", "project_id": "…", "prompt": "…", "persona_ids": "[id]",
                        "statements": "int", "votes": "int", "questions": "int", "created_at": "iso"},
            "synthesis": {"id": "…", "title": "…", "status": "…", "goal": "…",
                          "council_ids": "[id]", "findings": "int", "statements": "int",
                          "created_at": "iso", "updated_at": "iso"},
            "chat": {"id": "…", "persona_id": "…", "turns": "int", "last_message": "…",
                     "created_at": "iso", "updated_at": "iso"},
        },
        "filters": {"q": "free text over the row", "since": "ISO lower bound on updated_at|created_at",
                    "status": "projects/syntheses", "project_id/persona_id": "councils"},
        "study_result": "get_study_result(project_id) → {project row, run_state, council rows, "
                        "FULL syntheses (the answer nodes), open_questions, counts}",
        "chat_flow": "chat_with_persona(persona_id, message[, chat_id]) → host authors the reply "
                     "from agent_context+history → record_chat_turn(...) persists it (emits "
                     "chat.recorded); get_chat / list_chats read back",
        "auth_seam": "register_access_guard(fn(operation, resource)) — raise PermissionError to "
                     "deny; every substrate operation passes the guards (no-op locally, the "
                     "multi-tenant enforcement point for cloud)",
        "events": "substrate writes emit lifecycle events (chat.recorded); see docs/lifecycle-hooks.md",
    }
