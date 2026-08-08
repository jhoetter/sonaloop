"""Deterministic cohort-depth and hypothesis-leakage contract.

The gate intentionally contains no product/category vocabulary and does not call
an LLM.  It compares the current, evidence-backed product stimulus with persona
profile claims using versioned lexical features.  Hosts may additionally supply
one provider-neutral semantic similarity feature, but the same server-owned
threshold applies to every provider and the lexical path is always present.

Persona events/evidence created before the research project form independent
target context.  The Product Understanding and project goal form product
stimulus.  Keeping those lanes separate makes a freshly authored, product-shaped
persona visible instead of allowing its seeded pain points to masquerade as
discovery.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any

from .research_integrity import IntegrityError, current_product_understanding
from .storage import Store


COHORT_PREFLIGHT_SCHEMA = "sonaloop.cohort_integrity.v1"
COHORT_FEATURE_SCHEMA = "sonaloop.cohort_integrity.features.v1"
SEMANTIC_OVERLAP_SCHEMA = "sonaloop.semantic_overlap.v1"
COHORT_POLICY_VERSION = "2026-08-08.2"
COHORT_GATE_STATUSES = frozenset({
    "pass", "needs_deepening", "needs_reselection", "overridden",
})
REPRESENTATION_POSTURES = frozenset({
    "target", "skeptical", "indifferent", "non_target",
})

# Data, not provider-specific tuning.  Every value is persisted in each result.
DEFAULT_THRESHOLDS: dict[str, Any] = {
    "min_personas": 2,
    "min_independent_events_per_persona": 3,
    "min_independent_evidence_per_persona_alternative": 2,
    "min_independent_context_items_per_persona": 6,
    "max_thin_fraction": 0.34,
    "fresh_persona_hours": 24,
    "lexical_overlap_reselection": 0.50,
    "semantic_overlap_reselection": 0.82,
    "min_countervoices": 1,
}

# Function words only.  There are deliberately no product, industry, benefit,
# pain, technology or sentiment terms in this list.
_FUNCTION_WORDS = frozenset({
    "and", "are", "but", "das", "dass", "dem", "den", "der", "die", "ein",
    "eine", "einer", "eines", "for", "from", "haben", "hat", "how", "ist",
    "mit", "oder", "sich", "the", "their", "this", "und", "von", "was",
    "werden", "wie", "with", "would", "zum", "zur",
})
_TOKEN_RE = re.compile(r"[^\W_]+", re.UNICODE)


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), default=str)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def cohort_ids_digest(persona_ids: list[str]) -> str:
    return digest(sorted(dict.fromkeys(str(x) for x in persona_ids if str(x))))


def framed_research_inputs(project_id: str, store: Store) -> dict[str, Any]:
    """Return only the root frame(s) that the final cohort gate directly consumes."""
    from . import plan as research_plan

    plan = research_plan.get_plan(project_id, store=store) or {}
    cohort_task = next((row for row in plan.get("tasks") or []
                        if row.get("id") == "preflight__cohort_integrity"), None)
    source_ids = set((cohort_task or {}).get("consumes") or [])
    frames = [row for row in plan.get("tasks") or []
              if row.get("id") in source_ids and row.get("frame")]
    questions = list(dict.fromkeys(
        str(value).strip() for row in frames
        for value in (row.get("frame") or {}).get("questions") or []
        if str(value).strip()
    ))
    hypotheses = list(dict.fromkeys(
        str(value).strip() for row in frames
        for value in (row.get("frame") or {}).get("hypotheses") or []
        if str(value).strip()
    ))
    return {
        "frame_ids": [str(row.get("id") or "") for row in frames],
        "questions": questions,
        "hypotheses": hypotheses,
        "questions_digest": digest(questions),
        "hypotheses_digest": digest(hypotheses),
    }


def project_brief_digest(project: dict[str, Any]) -> str:
    """Mutable project-authored stimulus that must invalidate an earlier gate pass."""
    return digest({
        "goal": str(project.get("goal") or ""),
        "description": str(project.get("description") or ""),
    })


def _parse_ts(value: Any) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _age_hours(older: Any, newer: Any) -> float | None:
    before, after = _parse_ts(older), _parse_ts(newer)
    if not before or not after:
        return None
    return round(max(0.0, (after - before).total_seconds() / 3600), 2)


def _before_or_equal(value: Any, cutoff: Any) -> bool:
    item, boundary = _parse_ts(value), _parse_ts(cutoff)
    return bool(item and boundary and item <= boundary)


def tokens(text: str) -> list[str]:
    return [token for token in _TOKEN_RE.findall(str(text or "").casefold())
            if len(token) >= 3 and token not in _FUNCTION_WORDS]


def _selected_text(persona: dict[str, Any]) -> str:
    """Profile claims that can circularly repeat a product-shaped authoring prompt."""
    role = persona.get("role") or {}
    values: list[Any] = [
        persona.get("source_description"), role.get("title"), role.get("responsibilities"),
        *(persona.get("goals") or []), *(persona.get("constraints") or []),
        *(persona.get("pain_points") or []), *(persona.get("success_criteria") or []),
    ]
    return "\n".join(str(value) for value in values if str(value or "").strip())


def stimulus_text(project: dict[str, Any], hypotheses: list[str] | None = None) -> str:
    """External product stimulus; never persona memory."""
    values: list[Any] = [project.get("goal"), project.get("description"), *(hypotheses or [])]
    understanding = current_product_understanding(project) or {}
    target = understanding.get("target") or {}
    values.extend(target.get(key) for key in ("name", "identity", "url"))
    for key in ("routes", "flows", "states"):
        for row in understanding.get(key) or []:
            values.extend(row.get(field) for field in ("path", "name", "label", "state"))
    values.extend(row.get("claim") for row in understanding.get("capabilities") or [])
    return "\n".join(str(value) for value in values if str(value or "").strip())


def stimulus_segments(project: dict[str, Any], hypotheses: list[str] | None = None) -> list[str]:
    """Independent authored claims, so a long inventory cannot dilute one copied hypothesis."""
    understanding = current_product_understanding(project) or {}
    target = understanding.get("target") or {}
    rows: list[Any] = [project.get("goal"), project.get("description"), *(hypotheses or []),
                       *(row.get("claim") for row in understanding.get("capabilities") or []),
                       *(target.get(key) for key in ("name", "identity", "url"))]
    clean = [str(row).strip() for row in rows if str(row or "").strip()]
    full = stimulus_text(project, hypotheses)
    return list(dict.fromkeys([*clean, full]))


def lexical_overlap(left: str, right: str) -> dict[str, Any]:
    """Versioned, explainable overlap: token coverage + Jaccard + shared bigrams."""
    lt, rt = tokens(left), tokens(right)
    ls, rs = set(lt), set(rt)
    shared = ls & rs
    coverage = len(shared) / max(1, len(ls))
    jaccard = len(shared) / max(1, len(ls | rs))
    lb = set(zip(lt, lt[1:]))
    rb = set(zip(rt, rt[1:]))
    bigram_coverage = len(lb & rb) / max(1, len(lb))
    score = min(1.0, 0.55 * coverage + 0.20 * jaccard + 0.25 * bigram_coverage)
    return {
        "feature_schema": COHORT_FEATURE_SCHEMA,
        "algorithm": "token_coverage_0.55+jaccard_0.20+bigram_coverage_0.25",
        "score": round(score, 4),
        "hypothesis_token_count": len(ls),
        "profile_token_count": len(rs),
        "shared_token_count": len(shared),
        "shared_tokens": sorted(shared)[:12],
        "shared_bigram_count": len(lb & rb),
    }


def _origin(persona: dict[str, Any]) -> str:
    provenance = persona.get("provenance") or {}
    if provenance.get("catalog") or provenance.get("catalog_slug"):
        return "catalog"
    if provenance.get("grounding") or provenance.get("grounded_claims"):
        return "grounded"
    if provenance.get("source_description"):
        return "authored"
    return "unknown"


def persona_depth(persona_id: str, project: dict[str, Any], store: Store,
                  *, evaluated_at: str) -> dict[str, Any]:
    persona = store.get_persona(persona_id)
    if not persona:
        return {"persona_id": persona_id, "exists": False, "thin": True,
                "source_provenance": {"origin": "missing"}}
    cutoff = str(project.get("created_at") or evaluated_at)
    facts = store.list_persona_facts(persona_id)
    events = store.list_experience_events(persona_id)
    evidence = store.list_evidence(persona_id)
    independent_facts = [row for row in facts if _before_or_equal(row.get("t_valid"), cutoff)]
    independent_events = [row for row in events if _before_or_equal(row.get("timestamp"), cutoff)]
    independent_evidence = [row for row in evidence
                            if _before_or_equal(row.get("created_at"), cutoff)]
    post_project = {
        "facts": len(facts) - len(independent_facts),
        "events": len(events) - len(independent_events),
        "evidence": len(evidence) - len(independent_evidence),
    }
    independent_total = len(independent_facts) + len(independent_events) + len(independent_evidence)
    event_or_evidence = (
        len(independent_events) >= DEFAULT_THRESHOLDS["min_independent_events_per_persona"]
        or len(independent_evidence) >=
        DEFAULT_THRESHOLDS["min_independent_evidence_per_persona_alternative"]
    )
    thin = not (independent_total >=
                DEFAULT_THRESHOLDS["min_independent_context_items_per_persona"]
                and event_or_evidence)
    created_at = str(persona.get("created_at") or "")
    profile_age = _age_hours(created_at, cutoff)
    source_rows = [{"id": row.get("id"), "source_type": row.get("source_type"),
                    "created_at": row.get("created_at"),
                    "age_hours_at_project_start": _age_hours(row.get("created_at"), cutoff)}
                   for row in independent_evidence]
    return {
        "persona_id": persona_id,
        "display_name": persona.get("display_name") or persona.get("slug") or persona_id,
        "exists": True,
        "thin": thin,
        "profile_claim_digest": digest(_selected_text(persona)),
        "profile_created_at": created_at,
        "profile_age_hours_at_project_start": profile_age,
        "fresh_profile_at_project_start": (
            profile_age is not None
            and profile_age <= DEFAULT_THRESHOLDS["fresh_persona_hours"]
        ),
        "depth": {
            "facts": len(facts), "events": len(events), "evidence": len(evidence),
            "independent_facts": len(independent_facts),
            "independent_events": len(independent_events),
            "independent_evidence": len(independent_evidence),
            "independent_context_items": independent_total,
            "post_project_or_stimulus_bound": post_project,
        },
        "source_provenance": {
            "origin": _origin(persona),
            "profile": persona.get("provenance") or {},
            "independent_evidence_sources": source_rows,
            "event_range": {
                "oldest": min((str(x.get("timestamp") or "") for x in independent_events),
                              default=""),
                "newest": max((str(x.get("timestamp") or "") for x in independent_events),
                              default=""),
            },
        },
    }


def _context_index(persona_id: str, project: dict[str, Any], store: Store) -> dict[tuple[str, str], str]:
    cutoff = str(project.get("created_at") or "")
    index: dict[tuple[str, str], str] = {}
    for row in store.list_persona_facts(persona_id):
        if _before_or_equal(row.get("t_valid"), cutoff):
            index[("fact", str(row.get("id") or ""))] = str(row.get("fact") or "")
    for row in store.list_experience_events(persona_id):
        if _before_or_equal(row.get("timestamp"), cutoff):
            # ExperienceEvent exposes both authored/simulated quotes and the persona's
            # internal perspective.  Keep the legacy ``internal_thought`` field readable,
            # but index the canonical model fields returned by get_persona as well.
            # Deliberately do not index the whole event object: metadata and another
            # participant's conversation must not accidentally ground a countervoice.
            values = [
                row.get(key)
                for key in ("summary", "what_happened", "internal_thought", "persona_thought")
            ]
            key_quotes = row.get("key_quotes")
            values.extend(key_quotes if isinstance(key_quotes, list) else [key_quotes])
            index[("event", str(row.get("id") or ""))] = " ".join(
                str(value) for value in values if str(value or "").strip()
            )
    for row in store.list_evidence(persona_id):
        if _before_or_equal(row.get("created_at"), cutoff):
            index[("evidence", str(row.get("id") or ""))] = " ".join(str(row.get(key) or "")
                for key in ("content_or_path", "notes"))
    return index


def _normalized_quote(value: Any) -> str:
    return " ".join(str(value or "").casefold().split())


def _representation(rows: list[dict[str, Any]] | None, persona_ids: list[str],
                    project: dict[str, Any], store: Store) -> dict[str, Any]:
    clean, seen = [], set()
    for index, raw in enumerate(rows or []):
        if not isinstance(raw, dict):
            raise IntegrityError("BAD_COHORT_REPRESENTATION",
                                 f"representation[{index}] must be an object")
        pid = str(raw.get("persona_id") or "").strip()
        posture = str(raw.get("posture") or "").strip().lower()
        rationale = str(raw.get("rationale") or "").strip()
        if pid not in persona_ids:
            raise IntegrityError("BAD_COHORT_REPRESENTATION",
                                 f"representation persona {pid!r} is not in the cohort")
        if posture not in REPRESENTATION_POSTURES:
            raise IntegrityError("BAD_COHORT_REPRESENTATION",
                                 f"posture must be one of {', '.join(sorted(REPRESENTATION_POSTURES))}")
        if len(rationale) < 8:
            raise IntegrityError("BAD_COHORT_REPRESENTATION",
                                 "each representation posture needs a concrete rationale")
        if pid in seen:
            raise IntegrityError("BAD_COHORT_REPRESENTATION",
                                 f"persona {pid!r} is declared more than once")
        seen.add(pid)
        context = _context_index(pid, project, store)
        evidence_refs, rejected_refs = [], []
        for ref_index, ref in enumerate(raw.get("evidence_refs") or []):
            if not isinstance(ref, dict):
                raise IntegrityError("BAD_COHORT_REPRESENTATION",
                                     f"representation[{index}].evidence_refs[{ref_index}] must be an object")
            normalized = {"kind": str(ref.get("kind") or "").strip().lower(),
                          "id": str(ref.get("id") or "").strip()}
            if (normalized["kind"], normalized["id"]) in context:
                evidence_refs.append(normalized)
            else:
                rejected_refs.append(normalized)
        quote = str(raw.get("basis_quote") or "").strip()
        quote_key = _normalized_quote(quote)
        quote_matches = [ref for ref in evidence_refs
                         if len(quote_key) >= 8 and quote_key in _normalized_quote(
                             context[(ref["kind"], ref["id"])])]
        countervoice = posture != "target"
        grounding_status = (
            "grounded_context" if countervoice and quote_matches else
            "unverified" if countervoice else "not_required"
        )
        clean.append({
            "persona_id": pid, "posture": posture, "rationale": rationale,
            "evidence_refs": evidence_refs, "basis_quote": quote,
            "grounding_status": grounding_status,
            "quote_matched_ref": quote_matches[0] if quote_matches else None,
            "rejected_evidence_refs": rejected_refs,
        })
    declared_counter = [row for row in clean if row["posture"] != "target"]
    counter = [row for row in declared_counter if row["grounding_status"] == "grounded_context"]
    unverified = [row for row in declared_counter if row["grounding_status"] != "grounded_context"]
    return {
        "schema": "sonaloop.cohort_representation.v1",
        "declarations": clean,
        "undeclared_persona_ids": [pid for pid in persona_ids if pid not in seen],
        "complete": len(seen) == len(persona_ids),
        "declared_countervoice_persona_ids": [row["persona_id"] for row in declared_counter],
        "countervoice_persona_ids": [row["persona_id"] for row in counter],
        "countervoice_count": len(counter),
        "unverified_countervoice_persona_ids": [row["persona_id"] for row in unverified],
        "required_minimum": DEFAULT_THRESHOLDS["min_countervoices"],
        "allowed_counterpostures": ["skeptical", "indifferent", "non_target"],
        "verification_rule": (
            "countervoice needs an exact basis_quote (>=8 chars) in a cited independent "
            "pre-project fact/event/evidence record"
        ),
        "satisfied": len(counter) >= DEFAULT_THRESHOLDS["min_countervoices"],
    }


def _semantic(rows: dict[str, Any] | None,
              expected: dict[str, str]) -> dict[str, Any]:
    if not rows:
        return {"provided": False, "schema": SEMANTIC_OVERLAP_SCHEMA,
                "threshold": DEFAULT_THRESHOLDS["semantic_overlap_reselection"],
                "scores": []}
    if not isinstance(rows, dict) or rows.get("schema") != SEMANTIC_OVERLAP_SCHEMA:
        raise IntegrityError("BAD_SEMANTIC_FEATURE",
                             f"semantic_feature must use {SEMANTIC_OVERLAP_SCHEMA}")
    feature_version = str(rows.get("feature_version") or "").strip()
    if not feature_version:
        raise IntegrityError("BAD_SEMANTIC_FEATURE", "semantic_feature.feature_version is required")
    clean, seen = [], set()
    for index, raw in enumerate(rows.get("scores") or []):
        pid = str((raw or {}).get("persona_id") or "")
        if pid not in expected or pid in seen:
            raise IntegrityError("BAD_SEMANTIC_FEATURE",
                                 f"semantic score {index} has unknown/duplicate persona_id")
        if str(raw.get("input_digest") or "") != expected[pid]:
            raise IntegrityError("SEMANTIC_INPUT_MISMATCH",
                                 f"semantic score for {pid} does not match the current stimulus/profile pair")
        score = raw.get("score")
        if not isinstance(score, (int, float)) or isinstance(score, bool) or not 0 <= score <= 1:
            raise IntegrityError("BAD_SEMANTIC_FEATURE", "semantic scores must be numbers in 0..1")
        seen.add(pid)
        clean.append({"persona_id": pid, "input_digest": expected[pid],
                      "score": round(float(score), 4)})
    return {
        "provided": True, "schema": SEMANTIC_OVERLAP_SCHEMA,
        "feature_version": feature_version,
        "model_id": str(rows.get("model_id") or ""),
        "threshold": DEFAULT_THRESHOLDS["semantic_overlap_reselection"],
        "scores": clean,
    }


def evaluate_cohort(project: dict[str, Any], hypotheses: list[str] | None,
                    representation: list[dict[str, Any]] | None,
                    semantic_feature: dict[str, Any] | None, store: Store,
                    *, evaluated_at: str) -> dict[str, Any]:
    """Return the complete provider-invariant gate result (without id/version)."""
    persona_ids = list(dict.fromkeys(str(x) for x in project.get("persona_ids") or [] if str(x)))
    stimulus = stimulus_text(project, hypotheses)
    segments = stimulus_segments(project, hypotheses)
    stimulus_digest = digest(stimulus)
    depth_rows = [persona_depth(pid, project, store, evaluated_at=evaluated_at)
                  for pid in persona_ids]
    lexical_rows, semantic_inputs = [], {}
    for row in depth_rows:
        persona = store.get_persona(row["persona_id"]) if row.get("exists") else None
        profile_text = _selected_text(persona or {})
        candidates = [lexical_overlap(segment, profile_text) for segment in segments]
        feature = max(candidates, key=lambda row: row["score"], default=lexical_overlap("", ""))
        feature["matched_stimulus_segment_digest"] = digest(
            segments[candidates.index(feature)] if candidates else "")
        pair_digest = digest({"stimulus": stimulus, "profile_claims": profile_text,
                              "feature_schema": COHORT_FEATURE_SCHEMA})
        semantic_inputs[row["persona_id"]] = pair_digest
        lexical_rows.append({"persona_id": row["persona_id"], "input_digest": pair_digest,
                             **feature})
    semantic = _semantic(semantic_feature, semantic_inputs)
    representation_state = _representation(representation, persona_ids, project, store)
    missing = [row["persona_id"] for row in depth_rows if not row.get("exists")]
    thin = [row["persona_id"] for row in depth_rows if row.get("thin")]
    thin_fraction = len(thin) / max(1, len(persona_ids))
    lexical_high = [row for row in lexical_rows
                    if row["score"] >= DEFAULT_THRESHOLDS["lexical_overlap_reselection"]]
    semantic_high = [row for row in semantic["scores"]
                     if row["score"] >= DEFAULT_THRESHOLDS["semantic_overlap_reselection"]]
    high_overlap = sorted({row["persona_id"] for row in [*lexical_high, *semantic_high]})

    required_work: list[dict[str, Any]] = []
    if len(persona_ids) < DEFAULT_THRESHOLDS["min_personas"] or missing:
        required_work.append({
            "kind": "reselect", "code": "COHORT_MISSING_OR_TOO_SMALL",
            "persona_ids": missing,
            "minimum": DEFAULT_THRESHOLDS["min_personas"],
            "tools": ["catalog_recommend", "catalog_pull", "record_cohort_preflight"],
        })
    if high_overlap:
        required_work.append({
            "kind": "reselect", "code": "HYPOTHESIS_PROFILE_LEAKAGE",
            "persona_ids": high_overlap,
            "note": "independent depth does not waive strong stimulus/profile overlap; reselect, reframe, or override with a limitation",
            "tools": ["catalog_recommend", "catalog_pull", "record_cohort_preflight"],
        })
    if not representation_state["satisfied"]:
        required_work.append({
            "kind": "reselect",
            "code": ("COUNTERVOICE_UNVERIFIED"
                     if representation_state["unverified_countervoice_persona_ids"]
                     else "COUNTERVOICE_MISSING"),
            "minimum": DEFAULT_THRESHOLDS["min_countervoices"],
            "accepted_postures": ["skeptical", "indifferent", "non_target"],
            "unverified_persona_ids": representation_state["unverified_countervoice_persona_ids"],
            "tools": ["recall_memory", "get_persona", "catalog_recommend", "catalog_pull",
                      "record_cohort_preflight"],
        })
    if not representation_state["complete"]:
        required_work.append({
            "kind": "reselect", "code": "REPRESENTATION_INCOMPLETE",
            "persona_ids": representation_state["undeclared_persona_ids"],
            "tools": ["get_persona", "recall_memory", "record_cohort_preflight"],
        })
    if thin_fraction > DEFAULT_THRESHOLDS["max_thin_fraction"]:
        required_work.append({
            "kind": "deepen", "code": "INDEPENDENT_CONTEXT_TOO_THIN",
            "persona_ids": thin,
            "minimums": {
                "context_items": DEFAULT_THRESHOLDS["min_independent_context_items_per_persona"],
                "events": DEFAULT_THRESHOLDS["min_independent_events_per_persona"],
                "evidence_alternative":
                    DEFAULT_THRESHOLDS["min_independent_evidence_per_persona_alternative"],
            },
            "tools": ["brief_day", "record_day", "continue_simulation", "ingest_corpus",
                      "record_grounding", "record_cohort_preflight"],
        })

    reselect = any(row["kind"] in {"reselect", "reselect_or_ground"}
                   for row in required_work)
    status = ("needs_reselection" if reselect else
              "needs_deepening" if required_work else "pass")
    return {
        "schema": COHORT_PREFLIGHT_SCHEMA,
        "policy_version": COHORT_POLICY_VERSION,
        "status": status,
        "thresholds": dict(DEFAULT_THRESHOLDS),
        "cohort_ids": persona_ids,
        "cohort_ids_digest": cohort_ids_digest(persona_ids),
        "stimulus_boundary": {
            "kind": "project_created_at", "at": project.get("created_at"),
            "product_stimulus_digest": stimulus_digest,
            "project_goal_description_digest": project_brief_digest(project),
            "effective_hypotheses_digest": digest(hypotheses or []),
            "product_understanding_id": str((current_product_understanding(project) or {}).get("id") or ""),
            "independent_target_context": "persona facts/events/evidence at or before project creation",
            "product_stimulus": "project goal/description + hypotheses + Product Understanding",
        },
        "depth": {
            "personas": depth_rows,
            "totals": {
                "personas": len(persona_ids), "missing": len(missing), "thin": len(thin),
                "thin_fraction": round(thin_fraction, 4),
                "facts": sum((row.get("depth") or {}).get("facts", 0) for row in depth_rows),
                "events": sum((row.get("depth") or {}).get("events", 0) for row in depth_rows),
                "evidence": sum((row.get("depth") or {}).get("evidence", 0) for row in depth_rows),
                "independent_context_items": sum(
                    (row.get("depth") or {}).get("independent_context_items", 0)
                    for row in depth_rows),
            },
        },
        "leakage": {
            "lexical": lexical_rows,
            "semantic": semantic,
            "semantic_inputs": semantic_inputs,
            "high_overlap_persona_ids": high_overlap,
            # Compatibility name retained in v1; it now includes deep profiles too.
            "circular_persona_ids": high_overlap,
        },
        "representation": representation_state,
        "required_work": required_work,
        "evaluated_at": evaluated_at,
    }


def current_cohort_preflight(project: dict[str, Any] | None) -> dict[str, Any] | None:
    versions = (project or {}).get("cohort_preflight_versions") or []
    current_id = str((project or {}).get("cohort_preflight_current_id") or "")
    if current_id:
        found = next((row for row in versions if str(row.get("id") or "") == current_id), None)
        if found:
            return found
    return versions[-1] if versions else None


def preflight_satisfies_project(project: dict[str, Any], store: Store | None = None) -> bool:
    current = current_cohort_preflight(project)
    understanding_id = str((current_product_understanding(project) or {}).get("id") or "")
    framed = framed_research_inputs(str(project.get("id") or ""), store or Store())
    boundary = (current or {}).get("stimulus_boundary") or {}
    return bool(current and current.get("status") in {"pass", "overridden"}
                and current.get("cohort_ids_digest") ==
                cohort_ids_digest(list(project.get("persona_ids") or []))
                and str(boundary.get("product_understanding_id") or "") == understanding_id
                and str(boundary.get("project_goal_description_digest") or "") ==
                project_brief_digest(project)
                and str(boundary.get("frame_questions_digest") or "") ==
                framed["questions_digest"]
                and str(boundary.get("frame_hypotheses_digest") or "") ==
                framed["hypotheses_digest"])
