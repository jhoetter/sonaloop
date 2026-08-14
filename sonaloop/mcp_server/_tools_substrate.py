from __future__ import annotations

import time
from typing import Any

from .. import services
from ._env import _env


def register_substrate(mcp):
    # ====== The queryable substrate (docs/substrate.md): versioned programmatic reads ======
    @mcp.tool()
    def substrate_schema() -> dict[str, Any]:
        """The versioned substrate contract (envelope, row schemas, filters, the chat flow,
        the access-guard seam) — what an external automation pins to before querying."""
        t = time.perf_counter()
        return _env("substrate_schema", services.substrate_schema(), t)

    @mcp.tool()
    def query_personas(q: str | None = None, limit: int = 50, offset: int = 0) -> dict[str, Any]:
        """Paginated lean persona rows, filterable by free text. Stable ordering + next_offset."""
        t = time.perf_counter()
        return _env("query_personas", services.query_personas(q, limit, offset), t)

    @mcp.tool()
    def query_projects(status: str | None = None, q: str | None = None, since: str | None = None,
                       limit: int = 50, offset: int = 0) -> dict[str, Any]:
        """Paginated lean research-project rows; filter by status, free text, and `since`
        (ISO lower bound on updated_at). Newest first."""
        t = time.perf_counter()
        return _env("query_projects", services.query_projects(status, q, since, limit, offset), t)

    @mcp.tool()
    def query_councils(project_id: str | None = None, persona_id: str | None = None,
                       q: str | None = None, since: str | None = None,
                       limit: int = 50, offset: int = 0) -> dict[str, Any]:
        """Paginated lean council rows; filter by project, participant, free text, `since`."""
        t = time.perf_counter()
        return _env("query_councils",
                    services.query_councils(project_id, persona_id, q, since, limit, offset), t)

    @mcp.tool()
    def query_syntheses(status: str | None = None, q: str | None = None, since: str | None = None,
                        limit: int = 50, offset: int = 0) -> dict[str, Any]:
        """Paginated lean synthesis rows (the answer/report nodes); filter by status, text, `since`."""
        t = time.perf_counter()
        return _env("query_syntheses", services.query_syntheses(status, q, since, limit, offset), t)

    @mcp.tool()
    def get_study_result(project_id: str) -> dict[str, Any]:
        """ONE structured study result: lean project row + run state + council rows + the FULL
        syntheses in the project's graph + open questions. The shape recurring automations poll."""
        t = time.perf_counter()
        return _env("get_study_result", services.get_study_result(project_id), t)

    # ====== Durable persona chat (gather → author → write-back, with history) ======
    @mcp.tool()
    def chat_with_persona(persona_id: str, message: str, chat_id: str | None = None) -> dict[str, Any]:
        """Chat with ONE persona, durably. Returns the loaded agent context + prior turns;
        YOU author the in-character reply, then persist it with record_chat_turn. Omit
        chat_id to open a new conversation; pass it back to continue with full history."""
        t = time.perf_counter()
        return _env("chat_with_persona", services.chat_with_persona(persona_id, message, chat_id), t)

    @mcp.tool()
    def record_chat_turn(persona_id: str, chat_id: str, user_message: str, persona_reply: str,
                         refs: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        """Persist one authored chat exchange (the durable, queryable artifact). Emits
        the `chat.recorded` lifecycle event."""
        t = time.perf_counter()
        return _env("record_chat_turn",
                    services.record_chat_turn(persona_id, chat_id, user_message, persona_reply, refs), t)

    @mcp.tool()
    def brief_memory_from_chat(persona_id: str, chat_id: str,
                               turn_indexes: list[int] | None = None) -> dict[str, Any]:
        """Gather exact chat turns for a proposed continuity note. Chat output is
        synthetic conversation, never independent evidence or lived memory."""
        t = time.perf_counter()
        return _env("brief_memory_from_chat", services.brief_memory_from_chat(
            persona_id, chat_id, turn_indexes), t)

    @mcp.tool()
    def record_memory_proposal(persona_id: str, chat_id: str, turn_indexes: list[int],
                               proposal: dict[str, Any]) -> dict[str, Any]:
        """Persist a pending chat-continuity proposal. It affects no persona context
        until explicitly approved with review_memory_proposal."""
        t = time.perf_counter()
        return _env("record_memory_proposal", services.record_memory_proposal(
            persona_id, chat_id, turn_indexes, proposal), t)

    @mcp.tool()
    def review_memory_proposal(proposal_id: str, decision: str,
                               reason: str) -> dict[str, Any]:
        """Approve or reject a pending continuity note with an auditable reason.
        Approval only changes future chat continuity, never facts or identity."""
        t = time.perf_counter()
        return _env("review_memory_proposal", services.review_memory_proposal(
            proposal_id, decision, reason), t)

    @mcp.tool()
    def get_memory_proposal(proposal_id: str) -> dict[str, Any]:
        """Read one chat-continuity proposal and its review status."""
        t = time.perf_counter()
        return _env("get_memory_proposal", services.get_memory_proposal(proposal_id), t)

    @mcp.tool()
    def list_memory_proposals(persona_id: str,
                              status: str | None = None) -> dict[str, Any]:
        """List continuity proposals for one persona, optionally by review status."""
        t = time.perf_counter()
        return _env("list_memory_proposals", services.list_memory_proposals(
            persona_id, status), t)

    @mcp.tool()
    def get_chat(chat_id: str) -> dict[str, Any]:
        """One chat with its full turn history."""
        t = time.perf_counter()
        return _env("get_chat", services.get_chat(chat_id), t)

    @mcp.tool()
    def list_chats(persona_id: str | None = None, limit: int = 50, offset: int = 0) -> dict[str, Any]:
        """Paginated lean chat rows (newest first), optionally scoped to one persona."""
        t = time.perf_counter()
        return _env("list_chats", services.list_chats(persona_id, limit, offset), t)
