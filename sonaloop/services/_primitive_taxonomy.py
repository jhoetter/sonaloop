"""Read-only primitive/form taxonomy service surface."""

from __future__ import annotations

from typing import Any

from .. import primitive_taxonomy_registry as _registry


def list_primitives() -> list[dict[str, Any]]:
    return _registry.list_primitives()


def list_forms(primitive: str | None = None) -> list[dict[str, Any]]:
    return _registry.list_forms(primitive)


def get_form(primitive: str, form_id: str) -> dict[str, Any]:
    return _registry.get_form(primitive, form_id)


def suggest_forms(primitive: str) -> dict[str, Any]:
    return _registry.suggest_forms(primitive)


def register_custom_form(form: dict[str, Any]) -> dict[str, Any]:
    return _registry.register_custom_form(form)


def export_custom_forms() -> dict[str, Any]:
    return _registry.export_custom_forms()


def import_custom_forms(forms: list[dict[str, Any]]) -> dict[str, Any]:
    return _registry.import_custom_forms(forms)
