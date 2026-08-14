"""Service layer (split out of the former monolithic sonaloop/services.py).

Behavior-preserving package split: every previously-public name on
`sonaloop.services` is still importable as `services.<name>` and via
`from sonaloop.services import <name>`. The original file's bare-name
cross-calls are preserved verbatim in the submodules; this __init__ binds the
needed cross-module names into each submodule's globals after all submodules are
imported, so those LOAD_GLOBAL lookups resolve exactly as before — without
introducing import cycles.

The host-authored simulation cluster (the simulate_day builder + record_day /
record_month_bundle) lives together in ._simulation; the day's text is authored
by the MCP host and passed in as day_plan/activities (no in-process generation).
"""

from __future__ import annotations

# --- Re-export the non-function module surface (constants, models, helpers that
#     the original services.py exposed as module attributes) -------------------
from ..config import (
    ROOT, utc_now_iso, content_language, ensure_content_language, language_instruction,
    critic_threshold, critic_sample_k,
)
from ..models import (
    CalendarEvent,
    CouncilSession,
    DailySummary,
    Evidence,
    ExperienceEvent,
    Hypothesis,
    OpenQuestion,
    PainPointObservation,
    Persona,
    PrototypeSession,
    Reflection,
    ResearchProject,
    SimulationResult,
    Survey,
    SurveyResponse,
    Synthesis,
)
from ..storage import Store
from ..taxonomy import GENERIC_TOOLS, normalized_tool_ids, normalized_tools
from .. import memory as memory_mod
from .. import evaluation as evaluation_mod
from ..llm_simulation import (
    build_cohort_critic_prompt,
    build_consolidation_prompt,
    build_synthesis_outline_prompt,
    build_synthesis_section_prompt,
    validate_synthesis_outline_payload,
    validate_synthesis_section_payload,
    build_digest_prompt,
    build_eval_critic_prompt,
    build_evidence_check_prompt,
    build_persona_revision_prompt,
    build_plan_prompt,
    build_profile_prompt,
    build_synthesis_prompt,
    validate_activity_payload,
    validate_cohort_critic_payload,
    validate_digest_payload,
    validate_eval_critic_payload,
    validate_evidence_check_payload,
    validate_memory_deltas_payload,
    validate_persona_revision_payload,
    validate_plan_payload,
    validate_profile_payload,
    validate_synthesis_payload,
)

# --- Submodules (order matters only for *binding*, not for import-time safety:
#     no submodule references another submodule at import time) ----------------
from . import _common
from . import _primitive_taxonomy
from . import _pagination
from . import _hooks
from . import _events
from . import _capabilities
from . import _personas
from . import _persona_readiness
from . import _persona_lifecycle
from . import _simulation
from . import _consolidation
from . import _memory
from . import _evaluation
from . import _snapshots
from . import _catalog
from . import _councils
from . import _artifacts_service
from . import _project_assets
from . import _remote_assets
from . import _flow_manifests
from . import _integrity
from . import _cohort_integrity
from . import _recovery
from . import _substrate
from . import _grounding
from . import _predictions
from . import _calibration
from . import _flows
from . import _head_to_head
from . import _pricing
from . import _ideation
from . import _red_team
from . import _coverage
from . import _synthesis
from . import _report_writes
from . import _synthesis_pptx
from . import _project_icons
from . import _result_schemas
from . import _research
from . import _research_graph
from . import _engines
from . import _surveys
from . import _hypotheses
from . import _decisions
from . import _usability_sessions
from . import _walkthrough
from . import _actuation
from . import _sections
from . import _examples
from . import _feedback
from . import _retrieval

_SUBMODULES = (
    _common, _primitive_taxonomy, _pagination, _hooks, _events, _capabilities, _personas, _persona_readiness, _persona_lifecycle, _simulation, _consolidation, _memory, _evaluation,
    _snapshots, _catalog, _councils, _artifacts_service, _project_assets, _remote_assets, _flow_manifests, _integrity, _cohort_integrity, _recovery, _substrate, _grounding, _predictions, _calibration, _flows, _head_to_head, _pricing, _ideation, _red_team, _coverage, _synthesis, _report_writes, _synthesis_pptx, _project_icons, _result_schemas, _research, _research_graph, _engines, _surveys, _hypotheses, _decisions, _usability_sessions, _walkthrough, _actuation, _sections, _examples, _feedback, _retrieval,
)


def _collect_public_symbols() -> dict[str, object]:
    """Build the registry of every symbol defined in a submodule.

    A name is owned by the submodule that *defines* it (its __module__ ends with
    that submodule). For plain constants (no __module__) the first submodule that
    declares it wins; engines' redefined brief_next/record_judgment win because we
    take the value as bound on the submodule that lists it in its own __all__-like
    body — handled by preferring the engines copy explicitly below.
    """
    registry: dict[str, object] = {}
    for mod in _SUBMODULES:
        mod_name = mod.__name__.rsplit(".", 1)[-1]
        for name, value in vars(mod).items():
            if name.startswith("__"):
                continue
            owner = getattr(value, "__module__", None)
            if owner is not None:
                # Only register functions/classes physically defined in THIS submodule.
                if owner.endswith("." + mod_name):
                    registry[name] = value
            else:
                # constants / non-introspectable: register once (first definer)
                registry.setdefault(name, value)
    return registry


_REGISTRY = _collect_public_symbols()

# brief_next / record_judgment: the dispatching versions defined in _engines are
# the public ones (they shadow the methodology-engine imports). Ensure those win.
_REGISTRY["brief_next"] = _engines.brief_next
_REGISTRY["record_judgment"] = _engines.record_judgment

# The methodology-registry / suggestions / plan-engine / prototype seam names were module
# globals of the original services.py. Submodules reference some of them by bare name, so they
# must be part of the bound registry too. The constellation runtime was retired (HX3): a
# methodology only SEEDS the plan (set_project_methodology re-seeds an existing project; HX3).
for _eng_name in (
    "MethodologyError", "list_methodologies", "get_methodology", "register_methodology",
    "set_project_methodology",
    "suggest_capabilities", "suggest_roles", "suggest_artifact_types", "suggest_section_kinds", "suggest_chart_kinds", "suggest_methodologies", "suggest_stances", "suggest_finding_kinds", "suggest_friction_levels", "suggest_tech_comfort", "suggest_likelihood_levels",
    "PlanError", "new_plan", "validate_plan", "seed_plan_from_methodology", "ready_tasks",
    "is_complete", "render_plan_md",
    "_plan", "_proto", "_browser",
):
    _REGISTRY[_eng_name] = getattr(_engines, _eng_name)
del _eng_name

# --- Bind cross-module references into each submodule's globals so the verbatim
#     bare-name calls resolve exactly like the original single-module file. We do
#     NOT overwrite a name a submodule already defines locally (protects the
#     engines dispatch redefinitions and any local shadowing). ------------------
for _mod in _SUBMODULES:
    _mdict = vars(_mod)
    for _name, _value in _REGISTRY.items():
        if _name not in _mdict:
            _mdict[_name] = _value

# --- Promote everything to the package namespace (services.<name>) -------------
for _name, _value in _REGISTRY.items():
    globals()[_name] = _value

# Re-export the methodology-registry / suggestions / plan-engine / prototype seam names
# that the original services.py exposed (they live on _engines after its imports).
for _name in (
    "MethodologyError", "list_methodologies", "get_methodology", "register_methodology",
    "set_project_methodology",
    "suggest_capabilities", "suggest_roles", "suggest_artifact_types", "suggest_section_kinds", "suggest_chart_kinds", "suggest_methodologies", "suggest_stances", "suggest_finding_kinds", "suggest_friction_levels", "suggest_tech_comfort", "suggest_likelihood_levels",
    "PlanError", "new_plan", "validate_plan", "seed_plan_from_methodology", "ready_tasks",
    "is_complete", "render_plan_md",
    "_plan", "_proto", "_browser",
):
    globals()[_name] = getattr(_engines, _name)

# Stdlib / typing names the original module exposed as attributes (some callers do
# services.Path / services.datetime etc.). Re-export to preserve the surface.
from typing import Any  # noqa: E402,F401
from pathlib import Path  # noqa: E402,F401
from datetime import date, datetime, time, timedelta  # noqa: E402,F401

del _name, _value, _mod, _mdict
del _REGISTRY, _collect_public_symbols

# --- Patch semantics after the split ------------------------------------------
# Cross-module function references are bound ONCE at import time by the _REGISTRY
# loop above, exactly as the original single-module file resolved them. Two kinds
# of runtime overrides used to rely on a package-level setattr fan-out; both are
# now decoupled at the source, so no fan-out (and no custom module __setattr__) is
# needed:
#   * ROOT — the repo root. Submodules read it dynamically as `config.ROOT`
#     (single source in sonaloop/config.py), so a test that does
#     `monkeypatch.setattr(config, "ROOT", tmp)` redirects every service at once.
#   * function overrides (e.g. export_synthesis_pptx / export_synthesis_pdf) —
#     patch the submodule that CALLS the bare name
#     (`sonaloop.services._synthesis_pptx.<fn>`), the same namespace the call
#     resolves its globals from.
# _SUBMODULES stays as a module attribute for the presence gate and other callers.
