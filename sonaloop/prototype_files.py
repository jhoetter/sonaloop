"""Containment-safe static prototype file resolution."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .storage import Store


def resolve_prototype_file(prototype_id: str, asset_path: str = "", *,
                           refresh_entry: bool = False,
                           store: Store | None = None) -> tuple[dict[str, Any], Path]:
    """Resolve one static prototype file inside the active workspace partition."""
    from . import prototypes as registry

    store = store or Store()
    prototype = registry.get_prototype(prototype_id, store=store)
    if prototype.get("run") != "static" or str(prototype.get("run_cmd") or "").strip():
        raise registry.PrototypeError("UNSAFE_RUNNER", "only static prototypes can be served")
    app_dir = registry._prototype_app_dir(prototype)
    requested = str(asset_path or prototype.get("entry") or "index.html")
    target = (app_dir / requested).resolve()
    try:
        target.relative_to(app_dir)
    except ValueError:
        raise registry.PrototypeError(
            "BAD_PATH", "prototype file escapes its app directory") from None
    if target.is_dir():
        target = (target / "index.html").resolve()
        try:
            target.relative_to(app_dir)
        except ValueError:
            raise registry.PrototypeError(
                "BAD_PATH", "prototype file escapes its app directory") from None
    if refresh_entry and requested == str(prototype.get("entry") or "index.html"):
        registry.refresh_prototype_design_system(prototype["id"], store=store)
    if not target.exists() or not target.is_file():
        raise registry.PrototypeError(
            "MISSING_FILES", f"prototype file not found: {requested}")
    return prototype, target


def prototype_entry_available(prototype_id: str, store: Store | None = None) -> bool:
    """Whether the registered static entry exists without mutating or serving it."""
    from .prototypes import PrototypeError

    store = store or Store()
    try:
        prototype = store.get_prototype(prototype_id) or {}
        if prototype.get("run") == "remote":
            return bool(prototype.get("url"))
    except (KeyError, OSError, ValueError):
        return False

    try:
        resolve_prototype_file(prototype_id, store=store)
    except (PrototypeError, KeyError, OSError, ValueError):
        return False
    return True


__all__ = ["prototype_entry_available", "resolve_prototype_file"]
