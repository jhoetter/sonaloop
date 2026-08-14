from __future__ import annotations

import json
from typing import Any


class SimulationMixin:
    def insert_calendar_event(self, event: dict[str, Any]) -> None:
        self.conn.execute(
            'INSERT OR REPLACE INTO calendar_events (id, persona_id, start, "end", data) VALUES (?, ?, ?, ?, ?)',
            (event["id"], event["persona_id"], event["start"], event["end"], json.dumps(event, ensure_ascii=False)),
        )

    def insert_experience_event(self, event: dict[str, Any]) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO experience_events (id, persona_id, timestamp, event_type, data) VALUES (?, ?, ?, ?, ?)",
            (event["id"], event["persona_id"], event["timestamp"], event["event_type"], json.dumps(event, ensure_ascii=False)),
        )

    def upsert_daily_summary(self, summary: dict[str, Any]) -> None:
        self.conn.execute(
            """
            INSERT INTO daily_summaries (id, persona_id, date, data)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(persona_id, date) DO UPDATE SET data=excluded.data
            """,
            (summary["id"], summary["persona_id"], summary["date"], json.dumps(summary, ensure_ascii=False)),
        )

    def insert_reflection(self, reflection: dict[str, Any]) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO reflections (id, persona_id, period_start, period_end, data) VALUES (?, ?, ?, ?, ?)",
            (
                reflection["id"],
                reflection["persona_id"],
                reflection["period_start"],
                reflection["period_end"],
                json.dumps(reflection, ensure_ascii=False),
            ),
        )

    def upsert_pain_point(self, pain: dict[str, Any]) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO pain_points (id, persona_id, issue, data) VALUES (?, ?, ?, ?)",
            (pain["id"], pain["persona_id"], pain["issue"], json.dumps(pain, ensure_ascii=False)),
        )

    def list_calendar_events(self, persona_id: str, start: str | None = None, end: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT data FROM calendar_events WHERE persona_id=?"
        params: list[Any] = [persona_id]
        if start:
            query += " AND start>=?"
            params.append(start)
        if end:
            query += " AND start<=?"
            params.append(end)
        query += " ORDER BY start"
        return [json.loads(r["data"]) for r in self.conn.execute(query, params).fetchall()]

    def list_experience_events(self, persona_id: str, start: str | None = None, end: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT data FROM experience_events WHERE persona_id=?"
        params: list[Any] = [persona_id]
        if start:
            query += " AND timestamp>=?"
            params.append(start)
        if end:
            query += " AND timestamp<=?"
            params.append(end)
        query += " ORDER BY timestamp"
        return [json.loads(r["data"]) for r in self.conn.execute(query, params).fetchall()]

    def get_experience_event(self, event_id: str) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT data FROM experience_events WHERE id=?", (event_id,)).fetchone()
        return json.loads(row["data"]) if row else None

    def set_experience_event_memory_state(self, event_id: str, state: str,
                                          archived_at: str | None = None) -> bool:
        """Move an episode between active recall and the retained archive.

        The raw episode remains available to timelines/audits; recall deliberately
        excludes archived rows.  This is reversible and therefore safer than deleting
        lived history merely to model forgetting.
        """
        if state not in {"active", "archived"}:
            raise ValueError("memory state must be active|archived")
        event = self.get_experience_event(event_id)
        if not event:
            return False
        event["memory_state"] = state
        event["archived_at"] = archived_at if state == "archived" else None
        self.insert_experience_event(event)
        return True

    def list_daily_summaries(self, persona_id: str, start: str | None = None, end: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT data FROM daily_summaries WHERE persona_id=?"
        params: list[Any] = [persona_id]
        if start:
            query += " AND date>=?"
            params.append(start)
        if end:
            query += " AND date<=?"
            params.append(end)
        query += " ORDER BY date"
        return [json.loads(r["data"]) for r in self.conn.execute(query, params).fetchall()]

    def list_reflections(self, persona_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT data FROM reflections WHERE persona_id=? ORDER BY period_end",
            (persona_id,),
        ).fetchall()
        return [json.loads(r["data"]) for r in rows]

    def list_pain_points(self, persona_id: str | None = None) -> list[dict[str, Any]]:
        if persona_id:
            rows = self.conn.execute(
                "SELECT data FROM pain_points WHERE persona_id=? ORDER BY issue",
                (persona_id,),
            ).fetchall()
        else:
            rows = self.conn.execute("SELECT data FROM pain_points ORDER BY issue").fetchall()
        return [json.loads(r["data"]) for r in rows]
