from __future__ import annotations

import json
from typing import Any


class PersonaLifecycleMixin:
    def upsert_persona_build(self, build: dict[str, Any]) -> None:
        self.conn.execute(
            "INSERT INTO persona_builds (build_id, persona_id, operation_id, status, data, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT(build_id) DO UPDATE SET "
            "status=excluded.status, data=excluded.data, updated_at=excluded.updated_at",
            (build["build_id"], build["persona_id"], build["operation_id"], build["status"],
             json.dumps(build, ensure_ascii=False), build["created_at"], build["updated_at"]),
        )
        self.conn.commit()

    def get_persona_build(self, build_id: str) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT data FROM persona_builds WHERE build_id=?", (build_id,)).fetchone()
        return json.loads(row["data"]) if row else None

    def get_persona_build_by_operation(self, persona_id: str, operation_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT data FROM persona_builds WHERE persona_id=? AND operation_id=?",
            (persona_id, operation_id)).fetchone()
        return json.loads(row["data"]) if row else None

    def list_persona_builds(self, persona_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT data FROM persona_builds WHERE persona_id=? ORDER BY updated_at DESC",
            (persona_id,)).fetchall()
        return [json.loads(row["data"]) for row in rows]

    def insert_persona_context_snapshot(self, snapshot: dict[str, Any]) -> None:
        self.conn.execute(
            "INSERT INTO persona_context_snapshots (id, persona_id, project_id, created_at, data) "
            "VALUES (?, ?, ?, ?, ?) ON CONFLICT(id) DO NOTHING",
            (snapshot["id"], snapshot["persona_id"], snapshot.get("project_id"),
             snapshot["created_at"], json.dumps(snapshot, ensure_ascii=False)),
        )
        self.conn.commit()

    def get_persona_context_snapshot(self, snapshot_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT data FROM persona_context_snapshots WHERE id=?", (snapshot_id,)).fetchone()
        return json.loads(row["data"]) if row else None

    def list_persona_context_snapshots(self, persona_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT data FROM persona_context_snapshots WHERE persona_id=? ORDER BY created_at DESC",
            (persona_id,)).fetchall()
        return [json.loads(row["data"]) for row in rows]

    def upsert_persona_memory_proposal(self, proposal: dict[str, Any]) -> None:
        self.conn.execute(
            "INSERT INTO persona_memory_proposals (id, persona_id, chat_id, status, created_at, updated_at, data) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET "
            "status=excluded.status, updated_at=excluded.updated_at, data=excluded.data",
            (proposal["id"], proposal["persona_id"], proposal.get("chat_id"), proposal["status"],
             proposal["created_at"], proposal["updated_at"], json.dumps(proposal, ensure_ascii=False)),
        )
        self.conn.commit()

    def get_persona_memory_proposal(self, proposal_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT data FROM persona_memory_proposals WHERE id=?", (proposal_id,)).fetchone()
        return json.loads(row["data"]) if row else None

    def list_persona_memory_proposals(self, persona_id: str, status: str | None = None) -> list[dict[str, Any]]:
        sql, params = "SELECT data FROM persona_memory_proposals WHERE persona_id=?", [persona_id]
        if status:
            sql += " AND status=?"
            params.append(status)
        sql += " ORDER BY updated_at DESC"
        return [json.loads(row["data"]) for row in self.conn.execute(sql, params).fetchall()]
