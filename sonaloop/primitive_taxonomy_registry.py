"""Machine-readable primitive/form taxonomy registry.

This is the contract layer for the Library and research graph taxonomy. It is
not wired into rendering yet; current UI helpers continue to live in
`sonaloop.web._primitive_taxonomy`. The registry gives upcoming migrations a
validated data source so new primitives/forms cannot appear from arbitrary text.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from typing import Any

from .config import PACKAGE_DIR

REGISTRY_SCHEMA = "sonaloop.primitive_taxonomy.registry"
_ID = re.compile(r"^[a-z][a-z0-9_]*$")


def registry_path():
    return PACKAGE_DIR / "primitive_taxonomy.json"


@lru_cache(maxsize=1)
def load_registry() -> dict[str, Any]:
    return json.loads(registry_path().read_text(encoding="utf-8"))


def _ids(rows: list[dict[str, Any]], label: str, errors: list[str]) -> set[str]:
    seen: set[str] = set()
    for row in rows:
        rid = str(row.get("id") or "")
        if not _ID.match(rid):
            errors.append(f"{label} {rid!r}: id must be lower_snake_case")
            continue
        if rid in seen:
            errors.append(f"{label} {rid!r}: duplicate id")
        seen.add(rid)
    return seen


def registry_errors(registry: dict[str, Any] | None = None) -> list[str]:
    reg = registry or load_registry()
    errors: list[str] = []
    if reg.get("schema") != REGISTRY_SCHEMA:
        errors.append(f"schema must be {REGISTRY_SCHEMA!r}")
    if not isinstance(reg.get("version"), int) or reg.get("version", 0) < 1:
        errors.append("version must be an integer >= 1")

    families = reg.get("families") or []
    primitives = reg.get("primitives") or []
    forms = reg.get("forms") or []
    attrs = reg.get("orthogonal_attributes") or []
    relationships = reg.get("relationship_types") or []

    family_ids = _ids(families, "family", errors)
    primitive_ids = _ids(primitives, "primitive", errors)
    attr_ids = _ids(attrs, "attribute", errors)
    relationship_ids = _ids(relationships, "relationship", errors)

    for family in families:
        for field in ("label", "description", "icon"):
            if not str(family.get(field) or "").strip():
                errors.append(f"family {family.get('id')!r}: missing {field}")

    for primitive in primitives:
        pid = primitive.get("id")
        if primitive.get("family") not in family_ids:
            errors.append(f"primitive {pid!r}: unknown family {primitive.get('family')!r}")
        for field in ("label", "description", "icon", "color"):
            if not str(primitive.get(field) or "").strip():
                errors.append(f"primitive {pid!r}: missing {field}")

    seen_forms: set[tuple[str, str]] = set()
    aliases_by_primitive: dict[str, set[str]] = {}
    forms_by_family: dict[str, int] = {fid: 0 for fid in family_ids}
    for form in forms:
        fid = str(form.get("id") or "")
        primitive = str(form.get("primitive") or "")
        where = f"form {primitive}/{fid}"
        if not _ID.match(fid):
            errors.append(f"{where}: id must be lower_snake_case")
        if primitive not in primitive_ids:
            errors.append(f"{where}: unknown primitive")
        key = (primitive, fid)
        if key in seen_forms:
            errors.append(f"{where}: duplicate form id for primitive")
        seen_forms.add(key)
        aliases = aliases_by_primitive.setdefault(primitive, set())
        if fid in aliases:
            errors.append(f"{where}: form id collides with an alias")
        aliases.add(fid)
        for alias in form.get("aliases") or []:
            alias = str(alias)
            if not _ID.match(alias):
                errors.append(f"{where}: alias {alias!r} must be lower_snake_case")
            if alias in aliases:
                errors.append(f"{where}: duplicate alias {alias!r} for primitive {primitive!r}")
            aliases.add(alias)
        for field in ("label", "description", "schema", "renderer", "protocol"):
            if not form.get(field):
                errors.append(f"{where}: missing {field}")
        renderer = form.get("renderer") or {}
        if not renderer.get("library") or not renderer.get("detail"):
            errors.append(f"{where}: renderer needs library and detail")
        if primitive == "council":
            classifier = form.get("classifier") or {}
            if not classifier.get("mode_alias"):
                errors.append(f"{where}: council forms need classifier.mode_alias")
            if not renderer.get("requires"):
                errors.append(f"{where}: council forms need renderer.requires")
        if primitive == "session":
            classifier = form.get("classifier") or {}
            if not classifier.get("mode_alias"):
                errors.append(f"{where}: session forms need classifier.mode_alias")
            if not (classifier.get("subject_kind") or classifier.get("compat_fields")):
                errors.append(f"{where}: session forms need classifier subject_kind or compat_fields")
            if not renderer.get("requires"):
                errors.append(f"{where}: session forms need renderer.requires")
        schema = form.get("schema") or {}
        if schema.get("type") != "object":
            errors.append(f"{where}: schema.type must be 'object'")
        if not isinstance(schema.get("fields"), dict) or not schema.get("fields"):
            errors.append(f"{where}: schema.fields must be a non-empty object")
        for parameter in form.get("parameters") or []:
            if parameter.get("attribute") not in attr_ids:
                errors.append(f"{where}: unknown parameter attribute {parameter.get('attribute')!r}")
        if primitive in primitive_ids:
            family = next((p["family"] for p in primitives if p.get("id") == primitive), None)
            if family in forms_by_family:
                forms_by_family[family] += 1

    for family, count in forms_by_family.items():
        if count == 0:
            errors.append(f"family {family!r}: no registered forms")

    policy = reg.get("custom_form_policy") or {}
    if policy.get("default") != "reject_unknown":
        errors.append("custom_form_policy.default must stay 'reject_unknown'")

    for edge_form in (f for f in forms if f.get("primitive") == "edge"):
        if edge_form.get("id") not in relationship_ids:
            errors.append(f"edge form {edge_form.get('id')!r}: no matching relationship_type")

    return errors


def assert_valid_registry(registry: dict[str, Any] | None = None) -> dict[str, Any]:
    reg = registry or load_registry()
    errors = registry_errors(reg)
    if errors:
        raise ValueError("Invalid primitive taxonomy registry:\n- " + "\n- ".join(errors))
    return reg


def forms_for_primitive(primitive_id: str) -> list[dict[str, Any]]:
    reg = load_registry()
    return [form for form in reg.get("forms", []) if form.get("primitive") == primitive_id]


def list_primitives() -> list[dict[str, Any]]:
    """Read-only primitive catalogue with family, presentation and purpose."""
    return [dict(p) for p in load_registry().get("primitives") or []]


def list_forms(primitive: str | None = None) -> list[dict[str, Any]]:
    """Read-only form catalogue, optionally filtered by primitive id."""
    forms = [dict(f) for f in load_registry().get("forms") or []]
    if primitive:
        forms = [f for f in forms if f.get("primitive") == primitive]
    return forms


def get_form(primitive: str, form_id: str) -> dict[str, Any]:
    form = resolve_form(primitive, form_id)
    if form is None:
        raise KeyError(f"No registered form {primitive}/{form_id}")
    return dict(form)


def suggest_forms(primitive: str) -> dict[str, Any]:
    """Agent-facing read path for choosing a form and inspecting payload shape."""
    primitive_doc = next((p for p in list_primitives() if p.get("id") == primitive), None)
    if primitive_doc is None:
        raise KeyError(f"No registered primitive {primitive}")
    return {
        "primitive": primitive_doc,
        "forms": list_forms(primitive),
        "custom_form_policy": dict(load_registry().get("custom_form_policy") or {}),
    }


def resolve_form(primitive_id: str, value: str) -> dict[str, Any] | None:
    """Resolve a canonical form id or compatibility alias for one primitive."""
    needle = str(value or "")
    for form in forms_for_primitive(primitive_id):
        if form.get("id") == needle or needle in (form.get("aliases") or []):
            return form
    return None


def primitive_ids() -> set[str]:
    return {str(p.get("id")) for p in load_registry().get("primitives", [])}


def form_ids(primitive_id: str | None = None) -> set[str]:
    forms = load_registry().get("forms", [])
    if primitive_id:
        forms = [f for f in forms if f.get("primitive") == primitive_id]
    return {str(f.get("id")) for f in forms}
