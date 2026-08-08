from __future__ import annotations

import json
from typing import Any

from ..config import utc_now_iso


class ResearchMixin:
    # ---- Research graph: projects / edges / open questions / reports ----
    def insert_research_project_if_absent(self, project: dict[str, Any]) -> bool:
        """Atomically claim a deterministic project id without overwriting its owner.

        Used by retry-safe ``start_project(operation_id=...)``. The explicit conflict target is
        tenant-expanded by the Postgres backend, while SQLite uses the same statement verbatim.
        """
        cur = self.conn.execute(
            "INSERT INTO research_projects (id, slug, title, data, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(id) DO NOTHING",
            (project["id"], project["slug"], project["title"],
             json.dumps(project, ensure_ascii=False), project["created_at"],
             project.get("updated_at", project["created_at"])),
        )
        self.conn.commit()
        return cur.rowcount == 1

    def upsert_research_project(self, project: dict[str, Any]) -> None:
        self.conn.execute(
            "INSERT INTO research_projects (id, slug, title, data, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET slug=excluded.slug, title=excluded.title, data=excluded.data, updated_at=excluded.updated_at",
            (project["id"], project["slug"], project["title"], json.dumps(project, ensure_ascii=False),
             project["created_at"], project.get("updated_at", project["created_at"])),
        )
        self.conn.commit()

    def compare_and_swap_research_project(
        self, expected: dict[str, Any], project: dict[str, Any]
    ) -> bool:
        """Replace one project only when its persisted JSON has not changed."""
        cur = self.conn.execute(
            "UPDATE research_projects SET slug=?, title=?, data=?, updated_at=? "
            "WHERE id=? AND data=?",
            (
                project["slug"], project["title"], json.dumps(project, ensure_ascii=False),
                project.get("updated_at", project["created_at"]), project["id"],
                json.dumps(expected, ensure_ascii=False),
            ),
        )
        self.conn.commit()
        return cur.rowcount == 1

    def get_research_project(self, project_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT data FROM research_projects WHERE id=? OR slug=?", (project_id, project_id)).fetchone()
        return json.loads(row["data"]) if row else None

    def list_research_projects(self) -> list[dict[str, Any]]:
        rows = self.conn.execute("SELECT data FROM research_projects ORDER BY created_at DESC").fetchall()
        return [json.loads(r["data"]) for r in rows]

    # study_edge storage RETIRED (constellation graph; the plan engine is the graph now).

    def upsert_open_question(self, oq: dict[str, Any]) -> None:
        self.conn.execute(
            "INSERT INTO research_open_questions (id, project_id, study_id, status, data, created_at) VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET status=excluded.status, study_id=excluded.study_id, data=excluded.data",
            (oq["id"], oq["project_id"], oq.get("study_id"), oq["status"],
             json.dumps(oq, ensure_ascii=False), oq["created_at"]))
        self.conn.commit()

    def list_open_questions(self, project_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT data FROM research_open_questions WHERE project_id=? ORDER BY created_at", (project_id,)).fetchall()
        return [json.loads(r["data"]) for r in rows]

    # A report IS a project-scope SYNTHESIS (scope="project") — one concept. These are thin views
    # over the syntheses store, queried by scope.
    def get_report(self, report_id: str) -> dict[str, Any] | None:
        syn = self.get_synthesis(report_id)
        return syn if syn and syn.get("scope") == "project" else None

    def list_reports(self, project_id: str) -> list[dict[str, Any]]:
        rep = [s for s in self.list_syntheses() if s.get("scope") == "project" and s.get("project_id") == project_id]
        return sorted(rep, key=lambda s: s.get("created_at", ""), reverse=True)

    # ---- ESV: the resumable run object ----
    def insert_run_if_absent(self, run: dict[str, Any]) -> bool:
        """Atomically claim a caller-addressable run id without overwriting it."""
        cur = self.conn.execute(
            "INSERT INTO runs (run_id, project_id, status, cursor, data, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT(run_id) DO NOTHING",
            (
                run["run_id"], run["project_id"], run.get("status", "active"),
                int(run.get("cursor", 0)), json.dumps(run, ensure_ascii=False),
                run["created_at"], run.get("updated_at", run["created_at"]),
            ),
        )
        self.conn.commit()
        return cur.rowcount == 1

    def upsert_run(self, run: dict[str, Any]) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO runs (run_id, project_id, status, cursor, data, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (run["run_id"], run["project_id"], run.get("status", "active"), int(run.get("cursor", 0)),
             json.dumps(run, ensure_ascii=False), run["created_at"], run.get("updated_at", run["created_at"])))
        self.conn.commit()

    def compare_and_swap_run(self, expected: dict[str, Any], run: dict[str, Any]) -> bool:
        """Replace one run only when its complete persisted JSON is unchanged.

        Runs currently store their journal as one JSON document.  This CAS gives
        checkpoint/critic writers an atomic retry primitive on both SQLite and the
        tenant-expanded Postgres backend, preventing concurrent read-modify-write
        calls from silently dropping one another.
        """
        previous_data = json.dumps(expected, ensure_ascii=False)
        next_data = json.dumps(run, ensure_ascii=False)
        cur = self.conn.execute(
            "UPDATE runs SET project_id=?, status=?, cursor=?, data=?, updated_at=? "
            "WHERE run_id=? AND data=?",
            (
                run["project_id"], run.get("status", "active"), int(run.get("cursor", 0)),
                next_data, run.get("updated_at", run["created_at"]), run["run_id"], previous_data,
            ),
        )
        self.conn.commit()
        return cur.rowcount == 1

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT data FROM runs WHERE run_id=?", (run_id,)).fetchone()
        return json.loads(row["data"]) if row else None

    def list_runs(self, project_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT data FROM runs WHERE project_id=? ORDER BY created_at DESC", (project_id,)).fetchall()
        return [json.loads(r["data"]) for r in rows]

    # ---- Methodology engine: user-defined specs + per-phase judgments ----
    def upsert_methodology(self, spec: dict[str, Any]) -> None:
        self.conn.execute(
            "INSERT INTO methodologies (key, name, data, created_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET name=excluded.name, data=excluded.data",
            (spec["key"], spec["name"], json.dumps(spec, ensure_ascii=False),
             spec.get("created_at", utc_now_iso())))
        self.conn.commit()

    def get_methodology(self, key: str) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT data FROM methodologies WHERE key=?", (key,)).fetchone()
        return json.loads(row["data"]) if row else None

    def list_methodologies(self) -> list[dict[str, Any]]:
        rows = self.conn.execute("SELECT data FROM methodologies ORDER BY key").fetchall()
        return [json.loads(r["data"]) for r in rows]

    def insert_methodology_judgment(self, j: dict[str, Any]) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO methodology_judgments (id, project_id, phase_key, kind, decided, data, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (j["id"], j["project_id"], j["phase_key"], j["kind"], 1 if j.get("decided") else 0,
             json.dumps(j, ensure_ascii=False), j["created_at"]))
        self.conn.commit()

    def list_methodology_judgments(self, project_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT data FROM methodology_judgments WHERE project_id=? ORDER BY created_at", (project_id,)).fetchall()
        return [json.loads(r["data"]) for r in rows]

    # ---- Research plan (one per project) ----
    def upsert_research_plan(self, plan: dict[str, Any]) -> None:
        self.conn.execute(
            "INSERT INTO research_plans (project_id, data, created_at, updated_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(project_id) DO UPDATE SET data=excluded.data, updated_at=excluded.updated_at",
            (plan["project_id"], json.dumps(plan, ensure_ascii=False),
             plan.get("created_at", ""), plan.get("updated_at", "")))
        self.conn.commit()

    def get_research_plan(self, project_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT data FROM research_plans WHERE project_id=?", (project_id,)).fetchone()
        return json.loads(row["data"]) if row else None

    # ---- Granular deletes (D in CRUD; all via MCP/CLI, never the read-only UI) ----
    def delete_research_project(self, project_id: str) -> dict[str, int]:
        """Delete a project container and every project-scoped artifact row.

        Personas and persona memory are global and remain. Research outputs with this
        project_id do not: leaving them behind makes Library/global views point at a
        missing project and breaks trace annotation.
        """
        p = self.get_research_project(project_id)
        if not p:
            return {}
        pid = p["id"]
        deleted: dict[str, int] = {}
        # Capture exact child ids before deleting their rows. Current lifecycle events carry
        # project_id, but older synthesis events did not; entity ids let the cascade remove
        # those legacy Activity links without broad label/URL matching.
        event_entities: dict[str, list[str]] = {
            "project": [pid],
            "asset": [str(a["id"]) for a in p.get("assets", []) if a.get("id")],
        }
        for table, entity_type in (("council_sessions", "council"),
                                   ("syntheses", "synthesis")):
            rows = self.conn.execute(
                f"SELECT id FROM {table} WHERE json_extract(data, '$.project_id')=?", (pid,)).fetchall()
            event_entities[entity_type] = [str(r["id"]) for r in rows]
        run_rows = self.conn.execute("SELECT run_id FROM runs WHERE project_id=?", (pid,)).fetchall()
        event_entities["run"] = [str(r["run_id"]) for r in run_rows]
        # Delete prototype sessions before prototypes; prototype_sessions has no project_id.
        proto_rows = self.conn.execute("SELECT id FROM prototypes WHERE project_id=?", (pid,)).fetchall()
        proto_ids = [r["id"] for r in proto_rows]
        if proto_ids:
            qmarks = ",".join("?" for _ in proto_ids)
            cur = self.conn.execute(f"DELETE FROM prototype_sessions WHERE prototype_id IN ({qmarks})", proto_ids)
            deleted["prototype_sessions"] = cur.rowcount

        # Survey responses hang off surveys, not project_id.
        survey_rows = self.conn.execute("SELECT id FROM surveys WHERE project_id=?", (pid,)).fetchall()
        survey_ids = [r["id"] for r in survey_rows]
        if survey_ids:
            qmarks = ",".join("?" for _ in survey_ids)
            cur = self.conn.execute(f"DELETE FROM survey_responses WHERE survey_id IN ({qmarks})", survey_ids)
            deleted["survey_responses"] = cur.rowcount

        for table in (
            "research_open_questions",
            "methodology_judgments",
            "research_plans",
            "runs",
            "prediction_outcomes",
            "prototypes",
            "surveys",
            "hypotheses",
            "decision_records",
            "usability_sessions",
        ):
            cur = self.conn.execute(f"DELETE FROM {table} WHERE project_id=?", (pid,))
            deleted[table] = cur.rowcount
        for table in ("council_sessions", "syntheses"):
            cur = self.conn.execute(
                f"DELETE FROM {table} WHERE json_extract(data, '$.project_id')=?", (pid,))
            deleted[table] = cur.rowcount
        # The lifecycle bus is a bounded live-view cache, not durable audit history.
        # Exact project_id is the normal path; exact typed entity ids cover legacy rows
        # that predate project_id propagation (notably synthesis.recorded).
        cur = self.conn.execute("DELETE FROM events WHERE project_id=?", (pid,))
        deleted["events"] = cur.rowcount
        for entity_type, entity_ids in event_entities.items():
            if not entity_ids:
                continue
            qmarks = ",".join("?" for _ in entity_ids)
            cur = self.conn.execute(
                f"DELETE FROM events WHERE entity_type=? AND entity_id IN ({qmarks})",
                (entity_type, *entity_ids))
            deleted["events"] += cur.rowcount
        cur = self.conn.execute("DELETE FROM research_projects WHERE id=?", (pid,))
        deleted["research_projects"] = cur.rowcount
        self.conn.commit()
        return deleted

    def delete_open_question(self, question_id: str) -> int:
        cur = self.conn.execute("DELETE FROM research_open_questions WHERE id=?", (question_id,))
        self.conn.commit()
        return cur.rowcount
