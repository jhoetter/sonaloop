from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..config import DATA_DIR, utc_now_iso
from ._backend import StorageBackend, make_backend


class StoreBase:
    def __init__(self, path: Path | None = None, backend: StorageBackend | None = None) -> None:
        # The backend owns the dialect (SQLite today; Postgres + row tenancy next — see the
        # cloud-data-model page). Mixins keep using `self.conn` with `?` placeholders; a
        # backend is free to translate those, so this class stays dialect-agnostic.
        self._closed = True                    # set FIRST: a Store whose __init__ raises before
                                               # connect() must be a safe no-op in __del__/close()
        self.backend = backend or make_backend(path)
        self.path = self.backend.path          # the SQLite file path (None for server backends)
        # parents=True: a cold uvx/pipx install starts with NO per-user data dir (and possibly
        # no ~/.local/share at all) — first touch must create the whole chain, not error.
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = self.backend.connect()
        self._closed = False                   # past connect(): there is a connection to release
        self.backend.apply_schema(self.conn)
        self._stamp_schema_version()

    def _stamp_schema_version(self) -> None:
        from ..config import MEMORY_SCHEMA_VERSION

        self.conn.execute(
            "INSERT INTO meta (key, value) VALUES ('schema_version', ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (str(MEMORY_SCHEMA_VERSION),),
        )
        self.conn.commit()

    def schema_version(self) -> int:
        row = self.conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
        return int(row["value"]) if row else 0

    def close(self) -> None:
        # Idempotent: an explicit close(), __exit__, and the __del__ backstop may all fire for
        # the same Store. Guard so the underlying connection is released exactly once.
        if getattr(self, "_closed", True):
            return
        self._closed = True
        self.conn.close()

    def __enter__(self) -> "StoreBase":
        return self

    def __exit__(self, *exc: object) -> bool:
        self.close()
        return False

    def __del__(self) -> None:
        # Backstop for the many call sites — especially cloud's SHARED core web routes running
        # on Postgres — that build a Store and never close it. CPython refcounting collects a
        # function-local Store at function return, so __del__ then releases its connection
        # deterministically instead of leaving it idle-in-transaction (holding locks) until the
        # next cyclic GC. Under SQLite this only makes the existing GC-close prompt; behaviour is
        # unchanged. Never raise from __del__: interpreter shutdown may have torn down globals.
        try:
            self.close()
        except Exception:
            pass

    def delete_persona_cascade(self, persona_id: str) -> dict[str, int]:
        """Delete a persona and all of its persona-scoped rows (memory, simulation,
        evidence, eval). Council/synthesis rows reference personas only inside JSON and
        are left intact."""
        deleted: dict[str, int] = {}
        scoped = ["calendar_events", "experience_events", "daily_summaries", "reflections",
                  "pain_points", "entities", "entity_facts", "event_entities", "threads",
                  "plans", "memory_digests", "embeddings", "persona_revisions", "evidence",
                  "eval_reports", "memory_anomalies"]
        for table in scoped:
            cur = self.conn.execute(f"DELETE FROM {table} WHERE persona_id=?", (persona_id,))
            deleted[table] = cur.rowcount
        cur = self.conn.execute("DELETE FROM personas WHERE id=?", (persona_id,))
        deleted["personas"] = cur.rowcount
        self.conn.commit()
        return deleted

    def clear_simulation_state(self) -> dict[str, int]:
        tables = [
            "calendar_events",
            "experience_events",
            "daily_summaries",
            "reflections",
            "pain_points",
            "council_sessions",
            "syntheses",
            "entities",
            "entity_facts",
            "event_entities",
            "threads",
            "plans",
            "memory_digests",
            "embeddings",
            "persona_revisions",
            "memory_anomalies",
            "eval_reports",
            "research_projects",
            "research_plans",
            "research_open_questions",
        ]
        deleted: dict[str, int] = {}
        for table in tables:
            count = self.conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"]
            self.conn.execute(f"DELETE FROM {table}")
            deleted[table] = int(count)
        self.audit("simulation_state", "all", "clear", "cleared generated simulation state", deleted)
        self.conn.commit()
        return deleted

    def purge_runtime_state(self) -> dict[str, int]:
        tables = [
            "events",
            "calendar_events",
            "experience_events",
            "daily_summaries",
            "reflections",
            "pain_points",
            "survey_responses",
            "prototype_sessions",
            "usability_sessions",
            "surveys",
            "hypotheses",
            "decision_records",
            "prototypes",
            "council_sessions",
            "syntheses",
            "evidence",
            "prediction_outcomes",
            "corpus_chunks",
            "corpora",
            "persona_chats",
            "entities",
            "entity_facts",
            "event_entities",
            "threads",
            "plans",
            "memory_digests",
            "embeddings",
            "persona_revisions",
            "world_context",
            "memory_anomalies",
            "eval_reports",
            "research_projects",
            "research_plans",
            "research_open_questions",
            "methodology_judgments",
            "runs",
            "personas",
            "audit_log",
        ]
        deleted: dict[str, int] = {}
        for table in tables:
            count = self.conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"]
            self.conn.execute(f"DELETE FROM {table}")
            deleted[table] = int(count)
        self.conn.commit()
        return deleted

    def audit(self, entity_type: str, entity_id: str, action: str, reason: str | None, data: dict[str, Any] | None = None) -> None:
        self.conn.execute(
            "INSERT INTO audit_log (entity_type, entity_id, action, reason, created_at, data) VALUES (?, ?, ?, ?, ?, ?)",
            (entity_type, entity_id, action, reason, utc_now_iso(), json.dumps(data or {}, ensure_ascii=False)),
        )

    def commit(self) -> None:
        self.conn.commit()
