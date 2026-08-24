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

Back-compat: compatibility `phases` specs auto-translate to `steps`.
"""
from __future__ import annotations

import json
import re
import unicodedata
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


def _norm_work_item(raw: dict[str, Any]) -> dict[str, Any]:
    """One optional, data-authored Act todo seeded by a fan step."""
    return {
        "id": str(raw.get("id") or raw.get("key") or ""),
        "title": str(raw.get("title") or raw.get("name") or raw.get("id") or ""),
        "capability": str(raw.get("capability") or ""),
        "expected_output_kind": str(raw.get("expected_output_kind") or ""),
        "intent": str(raw.get("intent") or ""),
        "presentation": dict(raw.get("presentation") or {}),
    }


def _norm_routing(raw: dict[str, Any]) -> dict[str, Any]:
    """Canonical, data-authored front-door routing hints.

    These hints are advisory metadata for a server-owned selector.  They never
    affect plan execution and, importantly, keep methodology vocabulary in the
    registry instead of hardcoding it in a particular MCP host adapter.
    """
    signals = []
    for entry in raw.get("signals") or []:
        if isinstance(entry, str):
            phrase, weight = entry, 1
        elif isinstance(entry, dict):
            phrase, weight = entry.get("phrase"), entry.get("weight", 1)
        else:
            raise MethodologyError(
                "BAD_SPEC", "routing.signals entries must be strings or {phrase, weight}",
            )
        phrase = str(phrase or "").strip()
        try:
            weight = int(weight)
        except (TypeError, ValueError) as exc:
            raise MethodologyError("BAD_SPEC", "routing signal weight must be an integer") from exc
        if not phrase or weight < 1 or weight > 100:
            raise MethodologyError(
                "BAD_SPEC", "routing signals need a phrase and a weight between 1 and 100",
            )
        signals.append({"phrase": phrase, "weight": weight})
    try:
        threshold = int(raw.get("threshold", 5))
        ambiguity_margin = int(raw.get("ambiguity_margin", 2))
    except (TypeError, ValueError) as exc:
        raise MethodologyError(
            "BAD_SPEC", "routing threshold and ambiguity_margin must be integers",
        ) from exc
    if threshold < 1 or ambiguity_margin < 0:
        raise MethodologyError(
            "BAD_SPEC", "routing threshold must be positive and ambiguity_margin non-negative",
        )
    aliases = [str(value).strip() for value in raw.get("aliases") or [] if str(value).strip()]
    return {
        "schema": "methodology_routing.v1",
        "aliases": list(dict.fromkeys(aliases)),
        "signals": signals,
        "threshold": threshold,
        "ambiguity_margin": ambiguity_margin,
    }


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
        "work_items": [_norm_work_item(item) for item in (raw.get("work_items") or [])],
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
    """Translate a compatibility phase list (mode diverge/converge, alternating) to a step DAG.

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
    """Return a copy of the spec with a canonical `steps` list (translating compatibility `phases`)."""
    out = dict(spec)
    if out.get("steps"):
        out["steps"] = [_norm_step(s) for s in out["steps"]]
    elif out.get("phases"):
        out["steps"] = _phases_to_steps(out["phases"])
    else:
        out["steps"] = []
    if out.get("routing"):
        out["routing"] = _norm_routing(dict(out["routing"]))
    return out


def validate_methodology_spec(spec: dict[str, Any]) -> dict[str, Any]:
    """Validate a methodology spec (steps OR compatibility phases). Tag-agnostic: only graph mechanics
    and references are checked — never tag membership."""
    if not isinstance(spec, dict):
        raise MethodologyError("BAD_SPEC", "methodology spec must be an object")
    for k in ("key", "name", "description", "when_to_use"):
        if not spec.get(k):
            raise MethodologyError("BAD_SPEC", f"methodology spec missing '{k}'")
    if not (spec.get("steps") or spec.get("phases")):
        raise MethodologyError("BAD_SPEC", "methodology needs `steps` (or compatibility `phases`)")
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
        work_ids = [item["id"] for item in s.get("work_items") or []]
        if any(not item_id for item_id in work_ids) or len(work_ids) != len(set(work_ids)):
            raise MethodologyError("BAD_SPEC", f"step '{s['id']}' work_items need unique ids")
        for item in s.get("work_items") or []:
            if not item["title"] or not item["capability"] or not item["expected_output_kind"]:
                raise MethodologyError(
                    "BAD_SPEC",
                    f"step '{s['id']}' work item '{item['id']}' needs title, capability and expected_output_kind",
                )
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

_VIRTUAL_SPECS: dict[str, dict[str, Any]] = {
    "reaction_test": {
        "key": "reaction_test",
        "name": "Reaction Test",
        "description": "A lightweight reaction test for one fixed stimulus: collect audience reactions, then decide whether it clears a defined gate or needs revision.",
        "when_to_use": "Use when a concrete stimulus already exists and the decision is ship, revise, or review rather than broad discovery.",
        "routing": {
            "aliases": ["5-second test", "five second test", "content reaction"],
            "threshold": 5,
            "ambiguity_margin": 2,
            "signals": [
                {"phrase": "reaktionstest", "weight": 8},
                {"phrase": "reaction test", "weight": 8},
                {"phrase": "5 second test", "weight": 8},
                {"phrase": "five second test", "weight": 8},
                {"phrase": "ersteindruck", "weight": 6},
                {"phrase": "first impression", "weight": 6},
                {"phrase": "screenshot", "weight": 5},
                {"phrase": "website screen", "weight": 5},
                {"phrase": "landing page", "weight": 5},
                {"phrase": "headline", "weight": 5},
                {"phrase": "wording", "weight": 5},
                {"phrase": "verstandlichkeit", "weight": 4},
                {"phrase": "comprehension", "weight": 4}
            ]
        },
        # Methodology DATA declares the stricter research-integrity contract.  The
        # plan engine copies this block and derives a mandatory preflight task;
        # no MCP host has to remember the policy from prose.
        "integrity": {
            "product_understanding_required": True,
            "cohort_preflight_required": True,
            "stimulus_required": True,
            "claim_posture_required": True,
            "schema": "sonaloop.research_integrity.v1",
        },
        "presentation": {
            "icon": "sentiment",
            "image": "reaction-test.jpg",
            "complexity": "light",
            "summary": "Fast reaction scoring and a gate for one fixed stimulus.",
            "jobs": "Content, messaging, launch-copy and announcement checks.",
            "deck": {
                "purpose": "Enable a ship, revise or review decision for one fixed stimulus.",
                "target_core_slides": "6–8 slides for a 10-minute stakeholder readout; roughly one decision beat per 60–90 seconds.",
                "story_shape": "Orienting cover (tested artifact/journey + audience + test question) → decision dashboard → admitted stimulus → cohort lenses → reaction movement → editable proposed revision → release gate. Combine proof on the decision slide instead of spreading one finding over sparse slides.",
                "story_beats": [
                    {"role": "decision", "question": "What should happen next, how strong is the signal, and why?",
                     "preferred_visuals": ["decision_dashboard"]},
                    {"role": "stimulus", "question": "What exactly did the cohort see?",
                     "preferred_visuals": ["stimulus_comparison", "annotated_screen"]},
                    {"role": "cohort", "question": "Which perspectives shaped the result?",
                     "preferred_visuals": ["persona_grid"]},
                    {"role": "reaction", "question": "What landed, confused or changed?",
                     "preferred_visuals": ["preference_shift", "chart"]},
                    {"role": "revision", "question": "What concrete screen, copy or interaction should replace the current one?",
                     "preferred_visuals": ["revision_mockup", "annotated_screen"]},
                    {"role": "release_gate", "question": "What is kept, changed and validated next?",
                     "preferred_visuals": ["summary", "comparison"]},
                ],
                "required_visuals": ["real stimulus", "cohort overview",
                                     "scored reaction with denominator", "editable proposed revision",
                                     "release gate"],
                "appendix": ["response table by persona",
                             "optional persona details only when decision-relevant",
                             "method and limitations", "source index"],
                "speaker_notes": ["verbatim supporting voices", "source ids", "claim posture",
                                  "caveats", "what to say while the visual is on screen",
                                  "transition to the next decision beat"],
                "avoid": ["a cover that starts with unexplained A/B verdict language before naming what was tested",
                          "headlines longer than 12 words or 68 characters",
                          "describing an available stimulus only in prose",
                          "one sparse slide per finding",
                          "separate recommendation prose when a proposed revision can be shown",
                          "hiding denominators", "more than five appendix slides by default",
                          "calling synthetic reactions observed customer behavior"],
            },
        },
        "steps": [
            {
                "id": "react", "name": "React", "tags": ["explore", "reaction", "stimulus"],
                "intent": "Show the fixed stimulus to the selected cohort and collect scored reactions, comprehension issues and confusion points.",
                "strategy": "tension", "diverge_by": "persona_subset",
                "produces": {"role": "stimulus-reaction"},
                "work_items": [
                    {
                        "id": "comprehension",
                        "title": "Reaction · first impression and comprehension",
                        "capability": "reaction_council",
                        "expected_output_kind": "council",
                        "intent": "Run a segment-diverse council on first impression, information scent, comprehension and concrete confusion points. Cite only the admitted stimulus and persona memory.",
                    },
                    {
                        "id": "trust_action",
                        "title": "Reaction · trust, gaps and action readiness",
                        "capability": "reaction_council",
                        "expected_output_kind": "council",
                        "intent": "Run a distinct council angle on trust, missing information, comparison expectations and readiness to take the next action. Include skeptical and non-target voices.",
                    },
                ],
                "presentation": {
                    "forms": ["council/open_discussion", "council/objection_review"],
                    "formats": ["Council: Reaction", "Council: Objection review"],
                    "library": ["Councils", "Reports"],
                },
            },
            {
                "id": "gate", "name": "Gate", "tags": ["decide", "test", "gate"],
                "intent": "Synthesize the reaction score, confusion points and concrete revisions; decide whether the stimulus passes the threshold.",
                "strategy": "goal", "consumes": ["react"],
                "requires": {"min_inputs": 2, "gate_tag": "reaction_complete"},
                "produces": {"role": "decision-gate"},
                "presentation": {
                    "forms": ["council/open_discussion"],
                    "formats": ["Council: Gate review"],
                    "library": ["Reports", "Decisions"],
                },
            },
        ],
    },
}

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
    for key, spec in _VIRTUAL_SPECS.items():
        validate_methodology_spec(spec)
        specs[key] = _normalize_spec(spec)
    for spec in store.list_methodologies():
        specs[spec["key"]] = _normalize_spec(spec)
    return specs


def list_methodologies(store: Store | None = None) -> list[dict[str, Any]]:
    store = store or Store()
    out = []
    for s in registry(store).values():
        keys = [st["id"] for st in s["steps"]]
        out.append({"key": s["key"], "name": s["name"], "description": s["description"],
                    "when_to_use": s["when_to_use"], "step_keys": keys, "phase_keys": keys,
                    **({"integrity": dict(s["integrity"])} if s.get("integrity") else {}),
                    **({"routing": dict(s["routing"])} if s.get("routing") else {})})
    return out


def _methodology_alias(value: str) -> str:
    """Canonical comparison form for human-facing methodology names.

    Methodology keys remain the durable identifiers stored on projects.  This comparison
    form exists only at the input boundary so an MCP host does not have to guess that the
    display name ``Reaction Test`` is persisted as ``reaction_test``.
    """
    folded = unicodedata.normalize("NFKD", str(value)).casefold()
    folded = "".join(ch for ch in folded if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", "_", folded).strip("_")


def resolve_methodology_key(value: str, store: Store | None = None) -> str:
    """Resolve a stable key from a key, display name, or harmless spelling variant.

    Exact keys win.  Otherwise matching is case-insensitive and treats whitespace,
    punctuation, hyphens and underscores alike.  Ambiguous display names fail closed
    instead of choosing whichever registry row happened to be iterated first.
    """
    store = store or Store()
    raw = str(value or "").strip()
    specs = registry(store)
    if raw in specs:
        return raw
    alias = _methodology_alias(raw)
    matches = sorted({
        key
        for key, spec in specs.items()
        if alias and alias in {_methodology_alias(key), _methodology_alias(spec.get("name", ""))}
    })
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise MethodologyError(
            "AMBIGUOUS_METHODOLOGY",
            f"Methodology {value!r} matches multiple keys: {', '.join(matches)}",
        )
    available = ", ".join(f"{key} ({spec.get('name', key)})" for key, spec in sorted(specs.items()))
    raise MethodologyError(
        "UNKNOWN_METHODOLOGY",
        f"No methodology {value!r}. Use a key or display name from: {available}",
    )


def get_methodology(key: str, store: Store | None = None) -> dict[str, Any]:
    store = store or Store()
    canonical = resolve_methodology_key(key, store=store)
    return registry(store)[canonical]


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
    seen = {s.get("id") for s in out}
    for s in store.list_usability_sessions(project_id=project_id):
        subject = s.get("subject") or {}
        if subject.get("kind") != "prototype":
            continue
        proto = store.get_prototype(subject.get("id", "")) or {}
        if proto.get("project_id") != project_id or tag not in _artifact_tags(proto):
            continue
        if s.get("id") not in seen:
            out.append(s)
    return out
