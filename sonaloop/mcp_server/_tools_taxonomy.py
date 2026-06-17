from __future__ import annotations

import time
from typing import Any

from .. import services
from ._env import _env


def register_taxonomy(mcp):
    @mcp.tool()
    def list_primitives() -> dict[str, Any]:
        """List registered Library primitives with family, icon, color and purpose metadata."""
        t = time.perf_counter()
        return _env("list_primitives", services.list_primitives(), t)

    @mcp.tool()
    def list_forms(primitive: str | None = None) -> dict[str, Any]:
        """List registered primitive forms, optionally filtered by primitive id."""
        t = time.perf_counter()
        return _env("list_forms", services.list_forms(primitive), t)

    @mcp.tool()
    def get_form(primitive: str, form_id: str) -> dict[str, Any]:
        """Inspect one registered primitive form by canonical id or compatibility alias."""
        t = time.perf_counter()
        return _env("get_form", services.get_form(primitive, form_id), t)

    @mcp.tool()
    def suggest_forms(primitive: str) -> dict[str, Any]:
        """Show the registered forms, schemas, renderers, aggregators and alias policy for one primitive."""
        t = time.perf_counter()
        return _env("suggest_forms", services.suggest_forms(primitive), t)
