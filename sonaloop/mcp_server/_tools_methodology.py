from __future__ import annotations

import time
from typing import Any

from .. import services
from ._env import _env


def register_methodologies(mcp):
    # ============ Methodologies: tag-driven constellation SEEDS for the plan engine ============
    # A methodology = a DAG of steps carrying OPEN TAGS. It is purely data: starting one SEEDS the
    # research plan (analyze/act/verify) — the single runtime engine is the plan (see _tools_plan +
    # spec/hx3-engine-collapse.md). Common building blocks are SUGGESTED as data (suggest_*), never
    # enforced. See spec/methodology-constellations.md.
    @mcp.tool()
    def suggest_capabilities() -> dict[str, Any]:
        """SUGGESTED capability tags (explore/cluster/decide/build/test/synthesize, …) for a step's
        `tags`. Recommendations only — adopt, tweak, or invent your own; the engine never enforces."""
        t = time.perf_counter()
        return _env("suggest_capabilities", services.suggest_capabilities(), t)

    @mcp.tool()
    def suggest_roles() -> dict[str, Any]:
        """SUGGESTED role tags for a step's produces.role. Recommendations only."""
        t = time.perf_counter()
        return _env("suggest_roles", services.suggest_roles(), t)

    @mcp.tool()
    def suggest_artifact_types() -> dict[str, Any]:
        """SUGGESTED artifact-type tags for produces.artifact_type / requires.*_tags (matched by
        tag-equality, no string is special-cased). Recommendations only."""
        t = time.perf_counter()
        return _env("suggest_artifact_types", services.suggest_artifact_types(), t)

    @mcp.tool()
    def suggest_methodologies() -> dict[str, Any]:
        """SUGGESTED whole-constellation templates to copy and adapt (the registered methodologies
        + any extra templates). Tags are free; nothing here constrains what you may author."""
        t = time.perf_counter()
        return _env("suggest_methodologies", services.suggest_methodologies(), t)

    @mcp.tool()
    def list_methodologies() -> dict[str, Any]:
        """List available methodologies (built-in + user-defined) and their step keys."""
        t = time.perf_counter()
        return _env("list_methodologies", services.list_methodologies(), t)

    @mcp.tool()
    def get_methodology(key: str) -> dict[str, Any]:
        """The full constellation spec for one methodology (steps, tags, consumes, produces, requires)."""
        t = time.perf_counter()
        return _env("get_methodology", services.get_methodology(key), t)

    @mcp.tool()
    def register_methodology(spec: dict[str, Any]) -> dict[str, Any]:
        """Register a USER-DEFINED methodology — author your own constellation and it becomes a
        Framework any study can run through (start_project(methodology=<key>) seeds the plan).
        Spec shape: {key, name, description, when_to_use, steps:[{id, name, tags, intent, consumes,
        strategy, diverge_by, produces:{role, artifact_type, more_tags}, requires:{min_inputs,
        gate_tag, artifact_tags, session_of_tags}, loop_back}]} — copy a template from
        suggest_methodologies / get_methodology and pull tag vocabulary from suggest_capabilities /
        suggest_roles / suggest_artifact_types (all SUGGESTED; tags are free). Compatibility `phases`
        specs auto-translate to `steps`. User specs overlay built-ins by `key`, so re-registering
        your key updates it — but built-in keys are RESERVED (rejected with code RESERVED_KEY).
        Invalid specs fail with a stable MethodologyError code (e.g. BAD_SPEC) + message: fix and retry."""
        t = time.perf_counter()
        return _env("register_methodology", services.register_methodology(spec), t)

    @mcp.tool()
    def list_frameworks() -> dict[str, Any]:
        """The Frameworks (the methodologies that seed a study's plan) in PLAIN LANGUAGE, as one clean
        list the user — and the website / job presets — can read: each {id, name, what (the shape it
        is), when (when to use it), stages:[{id, name, what}] (the ordered diverge->converge stages)}.
        Use this to help the user knowingly pick which Framework a study runs through, then bind it with
        start_project(methodology=<id>) or set_project_methodology. Joined from the canonical taxonomy +
        the live methodology specs."""
        t = time.perf_counter()
        return _env("list_frameworks", services.list_frameworks(), t)

    @mcp.tool()
    def describe_framework(framework_id: str) -> dict[str, Any]:
        """One Framework's plain-language description by stable id (e.g. 'double_diamond'):
        {id, name, what, when, stages:[{id, name, what}]}. The structured companion to get_methodology
        (which returns the raw constellation graph) for showing/choosing a study's Framework."""
        t = time.perf_counter()
        return _env("describe_framework", services.describe_framework(framework_id), t)

    # start_methodology_project — RETIRED (a back-compat alias for start_project(methodology=...); M1).
    # Use start_project with methodology=<key>. The service fn remains for back-compat callers.

    @mcp.tool()
    def set_project_methodology(project_id: str, methodology_key: str) -> dict[str, Any]:
        """Bind an existing research project to a methodology by (re)seeding its plan from the
        constellation. The plan is the single engine; drive it via the plan tools."""
        t = time.perf_counter()
        return _env("set_project_methodology", services.set_project_methodology(project_id, methodology_key), t)

    @mcp.tool()
    def brief_next(project_id: str) -> dict[str, Any]:
        """GATHER what the plan's ready frontier needs now: the primary ready task (+ the full ready
        set), its bucket/capability, consumed frames, and unmet gates. The plan router — for richer
        per-iteration grounding use next_action."""
        t = time.perf_counter()
        return _env("brief_next", services.brief_next(project_id), t)

    @mcp.tool()
    def record_judgment(project_id: str, task_id: str, gate_tag: str, decided: bool, rationale: str,
                        evidence_refs: list[str] | None = None) -> dict[str, Any]:
        """Record an evidence-backed LLM gate judgment on a plan TASK (usually a verify task). `gate_tag`
        is a FREE tag (e.g. divergence_complete, or whatever the verify task requires). The engine
        requires its presence to complete the verify but never dictates its content or a number."""
        t = time.perf_counter()
        return _env("record_judgment",
                    services.record_judgment(project_id, task_id, gate_tag, decided, rationale, evidence_refs), t)

    @mcp.tool()
    def park_evidence(project_id: str, refs: list[Any], reason: str,
                      task_id: str = "") -> dict[str, Any]:
        """Explicitly park evidence that should remain visible but should NOT flow into a downstream
        gate/decision. Use this instead of leaving produced evidence orphaned."""
        t = time.perf_counter()
        return _env("park_evidence", services.park_evidence(project_id, refs, reason, task_id), t)
