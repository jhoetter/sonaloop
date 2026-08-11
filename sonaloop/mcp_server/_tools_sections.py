from __future__ import annotations

import time
from typing import Any

from .. import services
from ._env import _env


def register_sections(mcp):
    # ----- Sections: methodology-INDEPENDENT overlay groupings of graph nodes -----
    # A section references nodes by id (explicit, overlap allowed); it is a VIEW, never a container.
    # Spec: spec/sections-and-composable-graph.md.
    @mcp.tool()
    def create_section(project_id: str, title: str, kind: str = "theme",
                       member_ids: list[str] | None = None, parent_id: str | None = None,
                       order: int | None = None, presentation: dict[str, Any] | None = None,
                       note: str = "") -> dict[str, Any]:
        """Create a labeled overlay grouping of graph nodes (e.g. 'Initial user research',
        'Problem exploration'). `member_ids` must reference real nodes (council:<id>/synthesis:<id>/
        prototype ids). `kind` is a FREE tag (theme|phase|invented) rendered from data. A section is
        a view over shared nodes — it never owns/moves/deletes them."""
        t = time.perf_counter()
        return _env("create_section", services.create_section(
            project_id, title, kind, member_ids, parent_id, order, presentation, note), t)

    @mcp.tool()
    def update_section(section_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        """Update a section (title/kind/parent_id/order/presentation/note/member_ids)."""
        t = time.perf_counter()
        return _env("update_section", services.update_section(section_id, patch), t)

    @mcp.tool()
    def add_to_section(section_id: str, node_ids: list[str]) -> dict[str, Any]:
        """Add node ids to a section's membership (validated against the project graph)."""
        t = time.perf_counter()
        return _env("add_to_section", services.add_to_section(section_id, node_ids), t)

    @mcp.tool()
    def remove_from_section(section_id: str, node_ids: list[str]) -> dict[str, Any]:
        """Remove node ids from a section's membership (nodes themselves are untouched)."""
        t = time.perf_counter()
        return _env("remove_from_section", services.remove_from_section(section_id, node_ids), t)

    @mcp.tool()
    def set_section_members(section_id: str, node_ids: list[str]) -> dict[str, Any]:
        """Bulk-set a section's membership — the 'promote this cluster into a named section' move."""
        t = time.perf_counter()
        return _env("set_section_members", services.set_section_members(section_id, node_ids), t)

    @mcp.tool()
    def reorder_sections(project_id: str, ordered_ids: list[str]) -> dict[str, Any]:
        """Set the display/outline order of a project's sections."""
        t = time.perf_counter()
        return _env("reorder_sections", services.reorder_sections(project_id, ordered_ids), t)

    @mcp.tool()
    def list_sections(project_id: str) -> dict[str, Any]:
        """List a project's sections (ordered)."""
        t = time.perf_counter()
        return _env("list_sections", services.list_sections(project_id), t)

    @mcp.tool()
    def get_section(section_id: str) -> dict[str, Any]:
        """Get one section by id."""
        t = time.perf_counter()
        return _env("get_section", services.get_section(section_id), t)

    @mcp.tool()
    def delete_section(section_id: str) -> dict[str, Any]:
        """Delete a section. Member nodes are kept (reference, not containment)."""
        t = time.perf_counter()
        return _env("delete_section", services.delete_section(section_id), t)

    @mcp.tool()
    def suggest_section_kinds() -> dict[str, Any]:
        """Suggested section kinds + presentation (data-driven; adopt/tweak/invent)."""
        t = time.perf_counter()
        return _env("suggest_section_kinds", services.suggest_section_kinds(), t)

    @mcp.tool()
    def get_section_members(section_id: str) -> dict[str, Any]:
        """Resolve a section's members into {kind,title,summary,href} records (section-scoped view)."""
        t = time.perf_counter()
        return _env("get_section_members", services.section_members(section_id), t)

    @mcp.tool()
    def export_section(section_id: str, format: str = "md") -> dict[str, Any]:
        """Self-contained export of a section (md|json): its members' summaries, for a downstream agent."""
        t = time.perf_counter()
        return _env("export_section", services.export_section(section_id, format), t)

    # ----- Note nodes: lightweight first-class observation primitive (no methodology required) -----
    @mcp.tool()
    def create_note(project_id: str, text: str, title: str = "", kind: str = "note",
                    data: dict[str, Any] | None = None) -> dict[str, Any]:
        """Create a lightweight NOTE node — the ONE note entity (from a raw observation to a worked-out
        solution idea; there is no separate 'concept'). For a solution idea, pass structured `data`
        {lens, artifact_kind, prototype_id|null} so the completeness critic can track the solution space
        and the graph pairs it with its prototype once built (set prototype_id via set_note_data). `kind`
        is accepted for back-compat but normalized to 'note'."""
        t = time.perf_counter()
        return _env("create_note", services.create_note(project_id, text, title, kind, data), t)

    @mcp.tool()
    def set_note_data(note_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        """Merge keys into a note's `data` — e.g. set a concept note's `prototype_id` once you build it,
        so the completeness critic stops flagging it as un-prototyped."""
        t = time.perf_counter()
        return _env("set_note_data", services.set_note_data(note_id, patch), t)

    @mcp.tool()
    def list_notes(project_id: str, limit: int = 25, cursor: str | None = None) -> dict[str, Any]:
        """List a project's note nodes in creation order. Paginated per the shared
        convention (docs/pagination.md): `limit` (default 25) + opaque `cursor`; answers
        {items, total, has_more, next_cursor}. No params → the first page (backward
        compatible)."""
        t = time.perf_counter()
        def key(n: dict[str, Any]) -> str:
            return f'{n.get("created_at") or ""}\x1f{n.get("id") or ""}'
        rows = sorted(services.list_notes(project_id), key=key)
        page = services.paginate(rows, key, limit=limit, cursor=cursor,
                                 filters={"project_id": project_id})
        return _env("list_notes", page, t)

    @mcp.tool()
    def delete_note(project_id: str, note_id: str) -> dict[str, Any]:
        """Delete a note node from the project."""
        t = time.perf_counter()
        return _env("delete_note", services.delete_note(project_id, note_id), t)

    # ----- ESV1: auto-organization (a finished run is organized + handed-off BY CONSTRUCTION) -----
    @mcp.tool()
    def derive_sections(project_id: str) -> dict[str, Any]:
        """Auto-organize: derive persisted SECTION overlays from the plan — one per methodology phase
        (fan + its converging waist; label from the step name), a Prototype-ladder, a Deliver/Conclusion,
        and a Run-Journal section. Idempotent by title. Flips assess_project.finish.organized true."""
        t = time.perf_counter()
        return _env("derive_sections", services.derive_sections(project_id), t)

    @mcp.tool()
    def scaffold_synthesis(project_id: str, operation_id: str | None = None,
                           dispatch_token: str | None = None) -> dict[str, Any]:
        """Seed a project REPORT outline from the project's phases so the conclusion hand-off is one author
        step (brief_synthesis_section → record_synthesis_section). This creates resumable progress,
        not a completed hand-off. During a governed run pass the hand-off dispatch_token; the final
        authored section checkpoints that dispatch. Reuse operation_id on transport retries."""
        t = time.perf_counter()
        return _env("scaffold_synthesis", services.scaffold_synthesis(
            project_id, operation_id=operation_id, dispatch_token=dispatch_token), t)
