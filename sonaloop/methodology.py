"""Methodology specs — tag-driven constellations (spec/methodology-constellations.md).

A methodology is a CONSTELLATION: a DAG of steps, each carrying OPEN TAGS. There are NO
hardcoded vocabularies — capability ("explore"/"cluster"/"decide"/…), role, artifact_type,
gate and strategy are all free strings the spec declares. The only fixed concepts are the DAG
(`consumes`), an integer `min_inputs`, tag-equality, and the PRESENCE of an evidence-backed
judgment; a tag is never compared to a closed set.

Since HX3 (spec/hx3-engine-collapse.md) this module is a SPEC + REGISTRY + structural-helper
module only: methodologies are **plan seeds** (`plan.seed_plan_from_methodology`) and the single
runtime engine is `plan.py` (analyze→act→verify). The phase_log lifecycle engine that used to live
here was retired; the helpers the plan engine reuses (`_is_decide`, `_artifact_tags`,
`_project_artifacts_with`, `_sessions_of`) stay.

Back-compat: legacy `phases` specs auto-translate to `steps`.
"""
from __future__ import annotations

import json
from typing import Any

from .config import methodologies_dir, utc_now_iso
from . import primitive_taxonomy_registry as _taxonomy
from .storage import Store

# The structural breadth invariant: a waist consuming a fan needs at least this many upstream
# nodes. Used only as the default when a step does not declare its own `requires.min_inputs`; it is
# NOT a dynamics threshold.
_DEFAULT_FAN_MIN = 2


class MethodologyError(Exception):
    """Carries a stable code (§8.4) so callers/tests can assert the exact violation."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message

    def __str__(self) -> str:
        # The stable code rides str(exc) so it survives any boundary that stringifies the
        # exception (FastMCP's ToolError does) — an agent can match the code and fix the spec.
        return f"{self.code}: {self.message}"


# ----------------------------------------------------------------- spec normalization

def _as_list(v: Any) -> list:
    if v is None:
        return []
    return list(v) if isinstance(v, (list, tuple)) else [v]


def _norm_step(raw: dict[str, Any]) -> dict[str, Any]:
    """Canonical step dict. All domain words are open tags; nothing checked against a set."""
    produces = dict(raw.get("produces") or {})
    requires = dict(raw.get("requires") or {})
    presentation = dict(raw.get("presentation") or {})
    registered_forms = _registered_forms_for_presentation(presentation)
    if registered_forms:
        presentation["registered_forms"] = registered_forms
    return {
        "id": raw.get("id") or raw.get("key"),
        "name": raw.get("name", raw.get("id") or raw.get("key") or ""),
        "tags": list(raw.get("tags") or []),
        "intent": raw.get("intent", ""),
        "consumes": [str(c) for c in _as_list(raw.get("consumes"))],
        "strategy": raw.get("strategy") or raw.get("council_strategy") or "",
        "diverge_by": raw.get("diverge_by", ""),
        "produces": {
            "role": produces.get("role", ""),
            "artifact_type": produces.get("artifact_type", ""),
            "more_tags": list(produces.get("more_tags") or []),
        },
        "requires": {
            "min_inputs": int(requires["min_inputs"]) if requires.get("min_inputs") is not None else None,
            "gate_tag": requires.get("gate_tag", ""),
            "artifact_tags": list(requires.get("artifact_tags") or []),
            "session_of_tags": list(requires.get("session_of_tags") or []),
        },
        "loop_back": raw.get("loop_back", ""),
        "presentation": presentation,
    }


def _registered_forms_for_presentation(presentation: dict[str, Any]) -> list[dict[str, Any]]:
    """Resolve optional user-facing stage form hints against the primitive registry.

    Methodology tags stay open. Only explicit `presentation.forms` declarations are checked,
    then exposed as `registered_forms` for UI/MCP consumers.
    """
    declared = presentation.get("forms") or presentation.get("registered_forms") or []
    if not declared:
        return []
    primitives = {p["id"]: p for p in _taxonomy.list_primitives()}
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for raw in declared:
        if isinstance(raw, str) and "/" in raw:
            primitive, form_id = raw.split("/", 1)
        elif isinstance(raw, dict):
            primitive = str(raw.get("primitive") or "")
            form_id = str(raw.get("form") or raw.get("id") or "")
        else:
            raise MethodologyError("BAD_SPEC", "presentation.forms entries must be {primitive, form} or 'primitive/form'")
        primitive_doc = primitives.get(primitive)
        form = _taxonomy.resolve_form(primitive, form_id)
        if primitive_doc is None or form is None:
            raise MethodologyError("BAD_SPEC", f"unknown registered form '{primitive}/{form_id}'")
        key = (primitive, str(form["id"]))
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "primitive": primitive,
            "form": str(form["id"]),
            "primitive_label": primitive_doc.get("label", primitive),
            "form_label": form.get("label", form["id"]),
            "label": f"{primitive_doc.get('label', primitive)} / {form.get('label', form['id'])}",
            "description": form.get("description", ""),
        })
    return out


def _phases_to_steps(phases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Translate a legacy phase list (mode diverge/converge, alternating) to a step DAG.

    A linear chain: each step consumes the previous one. Converge phases gain the structural
    breadth + gate requirement; prototype/prototype_session requirements become tag references
    (matched by tag-equality, no literal artifact string survives)."""
    steps: list[dict[str, Any]] = []
    for i, p in enumerate(phases):
        key = p.get("key")
        mode = p.get("mode")
        prev = phases[i - 1] if i > 0 else None
        consumes = [prev["key"]] if prev else []
        req_arts = list(p.get("requires_artifacts") or [])
        raw: dict[str, Any] = {
            "id": key, "name": p.get("name", key), "intent": p.get("intent", ""),
            "consumes": consumes, "strategy": p.get("council_strategy", ""),
            "diverge_by": p.get("diverge_by", ""),
            "produces": {"role": p.get("produces_role", ""), "more_tags": []},
            "requires": {}, "loop_back": p.get("loop_back", ""),
        }
        if mode == "diverge":
            raw["tags"] = ["explore"] + ([p["produces_role"]] if p.get("produces_role") else [])
            if "prototype" in req_arts:
                raw["tags"].append("build")
                raw["produces"]["artifact_type"] = "prototype"
                if p.get("fidelity"):
                    raw["produces"]["more_tags"] = [p["fidelity"]]
        else:  # converge — a waist: needs breadth + a divergence gate
            raw["tags"] = ["decide"] + ([p["produces_role"]] if p.get("produces_role") else [])
            raw["requires"] = {"min_inputs": _DEFAULT_FAN_MIN, "gate_tag": "divergence_complete"}
            if "prototype_session" in req_arts:
                # require a recorded session of the prototype the consumed step built, keyed by
                # the most specific tag available (fidelity if set, else "prototype").
                disc = (prev or {}).get("fidelity") or "prototype"
                raw["requires"]["session_of_tags"] = [disc]
        steps.append(_norm_step(raw))
    return steps


def _normalize_spec(spec: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of the spec with a canonical `steps` list (translating legacy `phases`)."""
    out = dict(spec)
    if out.get("steps"):
        out["steps"] = [_norm_step(s) for s in out["steps"]]
    elif out.get("phases"):
        out["steps"] = _phases_to_steps(out["phases"])
    else:
        out["steps"] = []
    return out


def validate_methodology_spec(spec: dict[str, Any]) -> dict[str, Any]:
    """Validate a methodology spec (steps OR legacy phases). Tag-agnostic: only graph mechanics
    and references are checked — never tag membership."""
    if not isinstance(spec, dict):
        raise MethodologyError("BAD_SPEC", "methodology spec must be an object")
    for k in ("key", "name", "description", "when_to_use"):
        if not spec.get(k):
            raise MethodologyError("BAD_SPEC", f"methodology spec missing '{k}'")
    if not (spec.get("steps") or spec.get("phases")):
        raise MethodologyError("BAD_SPEC", "methodology needs `steps` (or legacy `phases`)")
    steps = _normalize_spec(spec)["steps"]
    if len(steps) < 2:
        raise MethodologyError("BAD_SPEC", "methodology needs >= 2 steps")
    ids = [s["id"] for s in steps]
    if not all(ids) or len(set(ids)) != len(ids):
        raise MethodologyError("BAD_SPEC", "step ids must be present and unique")
    idset = set(ids)
    roots = 0
    for s in steps:
        if not s["name"]:
            raise MethodologyError("BAD_SPEC", f"step '{s['id']}' needs a name")
        for c in s["consumes"]:
            if c not in idset:
                raise MethodologyError("BAD_SPEC", f"step '{s['id']}' consumes unknown step '{c}'")
            if c == s["id"]:
                raise MethodologyError("BAD_SPEC", f"step '{s['id']}' cannot consume itself")
        if not s["consumes"]:
            roots += 1
        mi = s["requires"]["min_inputs"]
        if mi is not None and (not isinstance(mi, int) or mi < 0):
            raise MethodologyError("BAD_SPEC", f"step '{s['id']}' requires.min_inputs must be a non-negative int")
        if s["loop_back"] and s["loop_back"] not in idset:
            raise MethodologyError("BAD_SPEC", f"step '{s['id']}' loop_back target '{s['loop_back']}' is not a step")
    if roots < 1:
        raise MethodologyError("BAD_SPEC", "methodology needs >= 1 root step (consumes [])")
    # INV-DAG: the `consumes` graph must be acyclic (loop_back is a separate, logged back-edge).
    _assert_acyclic(steps)
    return spec


def _assert_acyclic(steps: list[dict[str, Any]]) -> None:
    by_id = {s["id"]: s for s in steps}
    state: dict[str, int] = {}  # 0=visiting, 1=done

    def visit(sid: str) -> None:
        if state.get(sid) == 1:
            return
        if state.get(sid) == 0:
            raise MethodologyError("BAD_SPEC", f"`consumes` graph has a cycle at '{sid}'")
        state[sid] = 0
        for c in by_id[sid]["consumes"]:
            visit(c)
        state[sid] = 1

    for s in steps:
        visit(s["id"])


# --------------------------------------------------------------------------- registry

def _load_builtin_specs() -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    d = methodologies_dir()
    if not d.exists():
        return out
    for path in sorted(d.glob("*.json")):
        spec = json.loads(path.read_text(encoding="utf-8"))
        validate_methodology_spec(spec)
        out[spec["key"]] = _normalize_spec(spec)
    return out


def registry(store: Store | None = None) -> dict[str, dict[str, Any]]:
    """Built-in specs (package files) overlaid with user-defined ones (DB), all normalized."""
    store = store or Store()
    specs = _load_builtin_specs()
    for spec in store.list_methodologies():
        specs[spec["key"]] = _normalize_spec(spec)
    return specs


def list_methodologies(store: Store | None = None) -> list[dict[str, Any]]:
    store = store or Store()
    out = []
    for s in registry(store).values():
        keys = [st["id"] for st in s["steps"]]
        out.append({"key": s["key"], "name": s["name"], "description": s["description"],
                    "when_to_use": s["when_to_use"], "step_keys": keys, "phase_keys": keys})
    return out


def get_methodology(key: str, store: Store | None = None) -> dict[str, Any]:
    store = store or Store()
    spec = registry(store).get(key)
    if not spec:
        raise MethodologyError("UNKNOWN_METHODOLOGY", f"No methodology '{key}'")
    return spec


def register_methodology(spec: dict[str, Any], store: Store | None = None) -> dict[str, Any]:
    store = store or Store()
    validate_methodology_spec(spec)
    # Built-in keys are RESERVED: user specs overlay built-ins by key, so accepting one here
    # would silently shadow the packaged spec. Reject with a stable code instead.
    if spec["key"] in _load_builtin_specs():
        raise MethodologyError(
            "RESERVED_KEY", f"'{spec['key']}' is a built-in methodology; register under a new key")
    spec = dict(spec)
    spec.setdefault("created_at", utc_now_iso())
    store.upsert_methodology(spec)
    return spec


# --------------------------------------------------------------- structural helpers
# Reused by the plan engine (plan.py) when it seeds from / gates against a constellation.

def _is_decide(step: dict[str, Any]) -> bool:
    """A 'waist' step: it consolidates inputs behind a gate. Derived from structure, not a tag."""
    r = step["requires"]
    return bool(r["min_inputs"] is not None or r["gate_tag"] or r["session_of_tags"] or r["artifact_tags"])


def _artifact_tags(proto: dict[str, Any]) -> set[str]:
    """An artifact's open tags — its type tag plus any discriminators (e.g. a fidelity tag).
    All read from the record's data; no artifact value is assumed."""
    tags = {proto.get("type") or "prototype"}
    if proto.get("fidelity"):
        tags.add(proto["fidelity"])
    for tg in (proto.get("tags") or []):
        tags.add(tg)
    return tags


def _project_artifacts_with(store: Store, project_id: str, tag: str) -> list[dict[str, Any]]:
    return [p for p in store.list_prototypes(project_id) if tag in _artifact_tags(p)]


def _sessions_of(store: Store, project_id: str, tag: str) -> list[dict[str, Any]]:
    out = []
    for s in store.list_prototype_sessions():
        proto = store.get_prototype(s.get("prototype_id", "")) or {}
        if proto.get("project_id") == project_id and tag in _artifact_tags(proto):
            out.append(s)
    return out
