from __future__ import annotations

import time
from typing import Any

from .. import services
from ._env import _env


def register_usability(mcp):
    # ================= Usability sessions — the durable, replayable trace =================
    # One schema serves rungs 1-3 (artifact flow → prototype → live browser); only the fidelity of
    # "state per step" changes. THE SESSION IS THE DELIVERABLE, not a summary of it. House triplet:
    # brief_usability_session (gather) → the host authors the dual timeline → record_usability_session
    # (validate + persist). Supersedes the reaction-only record_prototype_session for new recordings.
    @mcp.tool()
    def brief_usability_session(persona_id: str, subject: dict[str, Any], fidelity: str,
                                project_id: str | None = None) -> dict[str, Any]:
        """GATHER persona context (SOUL + state + task-keyed memory) + anti-steering framing + the
        friction vocabulary + the subject's context (prototype how-to-drive when
        subject.kind='prototype') before a usability session. `subject` =
        {kind: flow|prototype|live_url, id?, url?, label}; `fidelity` = artifact|prototype|live.
        Author the per-step dual timeline, then record_usability_session."""
        t = time.perf_counter()
        return _env("brief_usability_session",
                    services.brief_usability_session(persona_id, subject, fidelity, project_id), t)

    @mcp.tool()
    def record_usability_session(persona_id: str, subject: dict[str, Any], fidelity: str, date: str,
                                 steps: list[dict[str, Any]], outcome: dict[str, Any],
                                 statements: list[dict[str, Any]] | None = None,
                                 project_id: str | None = None, session_id: str | None = None,
                                 key: str | None = None,
                                 dispatch_token: str | None = None) -> dict[str, Any]:
        """Persist a host-authored usability session — the durable, REPLAYABLE trace (the session is
        the deliverable). `steps` is the ordered dual timeline: {index (contiguous from 0),
        action:{type: look|click|type|select|scroll|key|navigate|back|wait|give_up, target, detail},
        monologue, state:{url?, title?, screen, screenshot? (under data/sessions/<id>/)},
        friction:{level, note} (the closed vocabulary — see suggest_friction_levels),
        verdict:{would_continue, reason}}. `outcome` = {completed, dropoff_step (an existing step;
        required when completed=false), summary, predicted_behaviors}. `statements` are the unified
        primitives; session refs ({kind:'session', id?, anchor:'step:<index>'}) must point at
        existing steps. With fidelity prototype/live and a browser `session_id`, claimed states are
        verified against the harness session log. Pass a stable `key` for a deterministic id
        (idempotent upsert → resumable runs). In a governed run pass run_step's dispatch_token;
        the verified session is linked and the task is checkpointed automatically."""
        t = time.perf_counter()
        return _env("record_usability_session",
                    services.record_usability_session(persona_id, subject, fidelity, date, steps,
                                                      outcome, statements, project_id, session_id, key,
                                                      dispatch_token=dispatch_token), t)

    @mcp.tool()
    def get_usability_session(session_id: str) -> dict[str, Any]:
        """One recorded usability session by id — the full replayable trace (steps + outcome +
        statements)."""
        t = time.perf_counter()
        return _env("get_usability_session", services.get_usability_session(session_id), t)

    @mcp.tool()
    def list_usability_sessions(project_id: str | None = None, persona_id: str | None = None,
                                subject: dict[str, Any] | None = None) -> dict[str, Any]:
        """List recorded usability sessions, optionally filtered by project, persona and/or subject
        ({kind?, id?|url?})."""
        t = time.perf_counter()
        return _env("list_usability_sessions",
                    {"sessions": services.list_usability_sessions(project_id, persona_id, subject)}, t)

    @mcp.tool()
    def suggest_friction_levels() -> dict[str, Any]:
        """The CANONICAL per-step friction vocabulary for usability sessions — call this before
        authoring step friction. Each item is {term, value, label_key, aliases} in severity order
        (none → hesitation → confusion → blocked). Like the stance scale this set is CLOSED: a known
        alias resolves to its level, but an unknown level is REJECTED on record (never silently
        bucketed — a downgraded 'blocked' would corrupt the funnel). Derived live from
        suggestions/friction_levels.json."""
        t = time.perf_counter()
        return _env("suggest_friction_levels", services.suggest_friction_levels(), t)

    @mcp.tool()
    def get_session_funnel(subject_kind: str, subject_id_or_url: str) -> dict[str, Any]:
        """Aggregate ALL usability sessions of one subject into a step-indexed funnel: per step the
        entered/continued/dropped counts plus the drop reasons — the cross-session read the
        replayable traces exist for."""
        t = time.perf_counter()
        return _env("get_session_funnel",
                    services.get_session_funnel(subject_kind, subject_id_or_url), t)
