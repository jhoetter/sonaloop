from __future__ import annotations

import json
from typing import Any


def _load_healed(data: str, *text_fields: str) -> dict[str, Any]:
    """json.loads + the artifacts.heal_text read-layer healing on the record's TITLE-bearing
    text fields (council `prompt`, synthesis `title`): literal \\uXXXX escapes authored by a
    remote host on a sibling store decode to real characters at READ time — the same seam as
    the dict-repr prompt healing (artifacts._prompt_text), one layer lower so the page hero /
    list rows heal too, not only the prompt accessors. Stored bytes stay untouched."""
    from ..artifacts import heal_text

    rec = json.loads(data)
    for f in text_fields:
        if isinstance(rec.get(f), str) and "\\u" in rec[f]:
            rec[f] = heal_text(rec[f])
    return rec


class CouncilsMixin:
    def insert_council_session(self, session: dict[str, Any]) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO council_sessions (id, created_at, data) VALUES (?, ?, ?)",
            (session["id"], session["created_at"], json.dumps(session, ensure_ascii=False)),
        )
        self.conn.commit()

    def insert_evidence(self, evidence: dict[str, Any]) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO evidence (id, persona_id, source_type, data) VALUES (?, ?, ?, ?)",
            (evidence["id"], evidence["persona_id"], evidence["source_type"], json.dumps(evidence, ensure_ascii=False)),
        )
        self.audit("evidence", evidence["id"], "attach", evidence.get("notes"), evidence)
        self.conn.commit()

    def get_evidence(self, evidence_id: str) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT data FROM evidence WHERE id=?", (evidence_id,)).fetchone()
        return json.loads(row["data"]) if row else None

    def list_evidence(self, persona_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT data FROM evidence WHERE persona_id=? ORDER BY id", (persona_id,)
        ).fetchall()
        return [json.loads(r["data"]) for r in rows]

    def list_council_sessions(self, project_id: str | None = None) -> list[dict[str, Any]]:
        if project_id:
            rows = self.conn.execute(
                "SELECT data FROM council_sessions WHERE json_extract(data, '$.project_id')=? "
                "ORDER BY created_at DESC", (project_id,)
            ).fetchall()
        else:
            rows = self.conn.execute("SELECT data FROM council_sessions ORDER BY created_at DESC").fetchall()
        return [_load_healed(r["data"], "prompt", "proposal") for r in rows]

    def get_council_session(self, session_id: str) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT data FROM council_sessions WHERE id=?", (session_id,)).fetchone()
        return _load_healed(row["data"], "prompt", "proposal") if row else None

    def upsert_synthesis(self, synthesis: dict[str, Any]) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO syntheses (id, title, data, created_at) VALUES (?, ?, ?, ?)",
            (synthesis["id"], synthesis["title"], json.dumps(synthesis, ensure_ascii=False), synthesis["created_at"]),
        )
        self.conn.commit()

    def get_synthesis(self, synthesis_id: str) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT data FROM syntheses WHERE id=?", (synthesis_id,)).fetchone()
        return _load_healed(row["data"], "title") if row else None

    def list_syntheses(self, project_id: str | None = None) -> list[dict[str, Any]]:
        if project_id:
            rows = self.conn.execute(
                "SELECT data FROM syntheses WHERE json_extract(data, '$.project_id')=? "
                "ORDER BY created_at DESC", (project_id,)
            ).fetchall()
        else:
            rows = self.conn.execute("SELECT data FROM syntheses ORDER BY created_at DESC").fetchall()
        return [_load_healed(r["data"], "title") for r in rows]

    def delete_synthesis(self, synthesis_id: str) -> int:
        cur = self.conn.execute("DELETE FROM syntheses WHERE id=?", (synthesis_id,))
        self.conn.commit()
        return cur.rowcount

    def delete_council_session(self, session_id: str) -> int:
        cur = self.conn.execute("DELETE FROM council_sessions WHERE id=?", (session_id,))
        self.conn.commit()
        return cur.rowcount
