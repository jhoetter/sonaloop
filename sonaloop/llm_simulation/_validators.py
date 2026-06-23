from __future__ import annotations

import json
from typing import Any

from ._schemas import (
    ACTIVITY_SCHEMA_KEYS,
    DAY_PLAN_SCHEMA_KEYS,
    PROFILE_SCHEMA_KEYS,
    _CRITIC_DIMENSIONS,
    _KINDS,
    _json_from_text,
    _recs,
    _require_keys,
    _strings,
)
from ._prompts import build_profile_prompt


def validate_activity_payload(payload: dict[str, Any], frame: dict[str, Any]) -> dict[str, Any]:
    out = dict(payload)
    for key, expected in ACTIVITY_SCHEMA_KEYS.items():
        if key not in out:
            raise ValueError(f"LLM activity payload missing `{key}`.")
        if not isinstance(out[key], expected):
            raise ValueError(f"LLM activity payload `{key}` has wrong type.")
    allowed_tools = set(frame["allowed_tools"])
    artifacts = [str(x) for x in out["artifacts_touched"]]
    out["artifacts_touched"] = artifacts[:8]
    if frame["tool"] not in allowed_tools:
        raise ValueError("Activity frame tool is outside persona tool enum.")
    out["conversation"] = [
        {"speaker": str(item.get("speaker", ""))[:80], "text": str(item.get("text", ""))[:500]}
        for item in out["conversation"][:8]
        if isinstance(item, dict)
    ]
    out["key_quotes"] = [str(x)[:300] for x in out["key_quotes"][:5]]
    out["actions_done"] = [str(x)[:300] for x in out["actions_done"][:8]]
    out["open_loops"] = [str(x)[:300] for x in out["open_loops"][:5]]
    out["pain_points"] = [p for p in [str(x) for x in out["pain_points"]] if p in frame["allowed_pain_points"]][:5]
    out["mood"] = str(out["mood"])[:80]
    out["persona_thought"] = str(out["persona_thought"])[:500]
    out["what_happened"] = str(out["what_happened"])[:1200]
    out["decision"] = str(out["decision"])[:300] if out["decision"] else None
    try:
        out["energy_delta"] = max(-3, min(2, int(float(out["energy_delta"]))))
    except (TypeError, ValueError):
        out["energy_delta"] = -1
    return out


def validate_profile_payload(payload: dict[str, Any]) -> dict[str, Any]:
    out = _require_keys(payload, PROFILE_SCHEMA_KEYS, "Profile")
    out["display_name"] = str(out["display_name"]).strip()[:120] or "Unnamed Profile"
    out["goals"] = _strings(out["goals"], 8)
    out["constraints"] = _strings(out["constraints"], 8)
    out["tool_ids"] = _strings(out["tool_ids"], 12, 80)
    out["tools"] = _strings(out["tools"], 12, 80)
    out["pain_points"] = _strings(out["pain_points"], 8)
    out["success_criteria"] = _strings(out["success_criteria"], 8)
    out["relationships"] = [
        {
            "name": str(item.get("name", "")).strip()[:120],
            "type": str(item.get("type", "")).strip()[:80],
            "friction": str(item.get("friction", "")).strip()[:220],
        }
        for item in out["relationships"][:8]
        if isinstance(item, dict) and item.get("name")
    ]
    if not out["tools"]:
        raise ValueError("Profile payload must contain at least one concrete tool/channel/work surface.")
    if not out["relationships"]:
        raise ValueError("Profile payload must contain specific relationships.")
    for key in ["goals", "constraints", "pain_points", "success_criteria"]:
        if not out[key]:
            raise ValueError(f"Profile payload must contain `{key}`.")
    nested_requirements = {
        "identity_traits": ["gender_presentation", "gender_confidence", "age_range", "appearance_notes", "avatar_profile", "avatar_constraints"],
        "role": ["title", "responsibilities", "seniority", "decision_power"],
        "company_context": ["industry", "size", "stack", "operating_model"],
        "personality": ["working_style", "communication_style", "risk_tolerance", "character_notes"],
    }
    for obj_key, required in nested_requirements.items():
        for nested_key in required:
            if nested_key not in out[obj_key]:
                raise ValueError(f"Profile `{obj_key}` missing `{nested_key}`.")
    for key in ["working_style", "communication_style", "risk_tolerance"]:
        if not str(out["personality"].get(key, "")).strip():
            raise ValueError(f"Profile personality missing `{key}`.")
    return out


def validate_day_plan_payload(payload: dict[str, Any], frame: dict[str, Any]) -> dict[str, Any]:
    out = _require_keys(payload, DAY_PLAN_SCHEMA_KEYS, "Day plan")
    allowed_tools = set(frame["allowed_tools"])
    blocks = []
    for item in out["blocks"]:
        if not isinstance(item, dict):
            continue
        block = {
            "title": str(item.get("title", "")).strip()[:120],
            "event_type": str(item.get("event_type", "")).strip(),
            "duration_minutes": int(item.get("duration_minutes", 45)),
            "collaboration_mode": str(item.get("collaboration_mode", "")).strip(),
            "participants": _strings(item.get("participants", []), 6, 80) if isinstance(item.get("participants", []), list) else [],
            "tool": str(item.get("tool", "")).strip(),
            "why_it_happens": str(item.get("why_it_happens", "")).strip()[:300],
        }
        if not block["title"]:
            continue
        if block["event_type"] not in {"meeting", "focus", "interruption", "admin", "decision", "site_visit"}:
            raise ValueError(f"Day plan has unsupported event_type `{block['event_type']}`.")
        if block["tool"] not in allowed_tools:
            raise ValueError(f"Day plan tool `{block['tool']}` is outside allowed tools.")
        block["duration_minutes"] = max(15, min(150, block["duration_minutes"]))
        blocks.append(block)
    if len(blocks) < 5:
        raise ValueError("Day plan must contain at least five usable blocks.")
    out["blocks"] = blocks[:8]
    out["mood_forecast"] = str(out["mood_forecast"]).strip()[:160]
    return out


def validate_memory_deltas_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("Memory deltas must be a JSON object.")
    out: dict[str, Any] = {"entities": [], "facts": [], "threads": [], "event_links": []}
    for e in payload.get("entities", []) or []:
        if not isinstance(e, dict) or not str(e.get("mention", "")).strip():
            continue
        kind = str(e.get("kind", "topic")).strip().lower()
        out["entities"].append({
            "mention": str(e["mention"]).strip()[:160],
            "kind": kind if kind in _KINDS else "topic",
            "status": (str(e["status"]).strip()[:80] if e.get("status") else None),
            "aliases": _strings(e.get("aliases", []) or [], 6, 160),
        })
    for f in payload.get("facts", []) or []:
        if not isinstance(f, dict) or not str(f.get("fact", "")).strip() or not str(f.get("entity", "")).strip():
            continue
        try:
            imp = max(1, min(5, int(f.get("importance", 3))))
        except (TypeError, ValueError):
            imp = 3
        out["facts"].append({
            "entity": str(f["entity"]).strip()[:160],
            "fact": str(f["fact"]).strip()[:400],
            "status": (str(f["status"]).strip()[:80] if f.get("status") else None),
            "valid_from": str(f.get("valid_from", "")).strip()[:10] or None,
            "valid_to": (str(f["valid_to"]).strip()[:10] if f.get("valid_to") else None),
            "importance": imp,
            "invalidates": (str(f["invalidates"]).strip()[:400] if f.get("invalidates") else None),
        })
    for t in payload.get("threads", []) or []:
        if not isinstance(t, dict) or not str(t.get("text", "")).strip():
            continue
        action = str(t.get("action", "open")).strip().lower()
        out["threads"].append({
            "text": str(t["text"]).strip()[:300],
            "entity": (str(t["entity"]).strip()[:160] if t.get("entity") else None),
            "action": action if action in {"open", "resolve"} else "open",
            "ref": (str(t["ref"]).strip()[:300] if t.get("ref") else None),
        })
    for link in payload.get("event_links", []) or []:
        if not isinstance(link, dict) or not str(link.get("activity_title", "")).strip():
            continue
        out["event_links"].append({
            "activity_title": str(link["activity_title"]).strip()[:200],
            "entities": _strings(link.get("entities", []) or [], 8, 160),
        })
    return out


def validate_plan_payload(payload: dict[str, Any], scope: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("Plan must be a JSON object.")
    return {
        "scope": scope,
        "summary": str(payload.get("summary", "")).strip()[:1200],
        "intentions": _strings(payload.get("intentions", []) or [], 12, 300),
        "expected_milestones": _strings(payload.get("expected_milestones", []) or [], 12, 300),
        "mood_trajectory": str(payload.get("mood_trajectory", "")).strip()[:300],
        "sample_days": _strings(payload.get("sample_days", []) or [], 31, 10),
    }


def validate_digest_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict) or not str(payload.get("text", "")).strip():
        raise ValueError("Digest must contain non-empty `text`.")
    arcs = []
    for a in payload.get("project_arcs", []) or []:
        if isinstance(a, dict) and str(a.get("name", "")).strip():
            arcs.append({"name": str(a["name"]).strip()[:160], "arc": str(a.get("arc", "")).strip()[:400]})
    return {
        "text": str(payload["text"]).strip()[:3000],
        "themes": _strings(payload.get("themes", []) or [], 10, 160),
        "project_arcs": arcs[:20],
        "trends": _strings(payload.get("trends", []) or [], 10, 240),
    }


def validate_persona_revision_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("Persona revision must be a JSON object.")
    raw = payload.get("changes", {}) or {}
    changes: dict[str, Any] = {}
    for key in ["goals_add", "goals_remove", "constraints_add", "constraints_remove",
                "pains_add", "pains_remove", "tools_add", "tools_remove"]:
        vals = _strings(raw.get(key, []) or [], 10, 220)
        if vals:
            changes[key] = vals
    if isinstance(raw.get("personality"), dict):
        pers = {k: str(v).strip()[:400] for k, v in raw["personality"].items()
                if k in {"working_style", "communication_style", "risk_tolerance", "character_notes"} and str(v).strip()}
        if pers:
            changes["personality"] = pers
    if str(raw.get("notes", "")).strip():
        changes["notes"] = str(raw["notes"]).strip()[:600]
    return {
        "rationale": str(payload.get("rationale", "")).strip()[:1200],
        "effective_on": str(payload.get("effective_on", "")).strip()[:10] or None,
        "changes": changes,
    }


def validate_eval_critic_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("Critic verdict must be a JSON object.")
    dims_in = payload.get("dimensions", {}) or {}
    dims: dict[str, int] = {}
    for key in _CRITIC_DIMENSIONS:
        try:
            dims[key] = max(0, min(5, int(dims_in.get(key, 3))))
        except (TypeError, ValueError):
            dims[key] = 3
    flagged = []
    for it in payload.get("flagged_items", []) or []:
        if not isinstance(it, dict) or not str(it.get("issue", "")).strip():
            continue
        try:
            sev = max(1, min(5, int(it.get("severity", 3))))
        except (TypeError, ValueError):
            sev = 3
        dim = str(it.get("dimension", "")).strip()
        flagged.append({
            "ref_id": str(it.get("ref_id", "")).strip()[:80],
            "dimension": dim if dim in _CRITIC_DIMENSIONS else "general",
            "issue": str(it["issue"]).strip()[:300],
            "severity": sev,
        })
    return {
        "dimensions": dims,
        "findings": _strings(payload.get("findings", []) or [], 12, 300),
        "flagged_items": flagged[:20],
        "overall_note": str(payload.get("overall_note", "")).strip()[:1000],
    }


def validate_cohort_critic_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("Cohort critic verdict must be a JSON object.")
    allowed_dims = {"believability", "consistency", "distinctiveness", "tone", "range"}
    outliers = []
    for it in payload.get("outliers", []) or []:
        if not isinstance(it, dict) or not str(it.get("persona_id", "")).strip():
            continue
        try:
            sev = max(1, min(5, int(it.get("severity", 3))))
        except (TypeError, ValueError):
            sev = 3
        dim = str(it.get("dimension", "")).strip().lower()
        outliers.append({
            "persona_id": str(it["persona_id"]).strip()[:80],
            "persona_name": str(it.get("persona_name", "")).strip()[:120],
            "reason": str(it.get("reason", "")).strip()[:400],
            "dimension": dim if dim in allowed_dims else "range",
            "severity": sev,
        })
    return {"outliers": outliers[:50], "cohort_note": str(payload.get("cohort_note", "")).strip()[:1000]}


def validate_evidence_check_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("Evidence check must be a JSON object.")
    contradicted = []
    for c in payload.get("contradicted", []) or []:
        if isinstance(c, dict) and str(c.get("claim", "")).strip():
            contradicted.append({"claim": str(c["claim"]).strip()[:300],
                                 "evidence_says": str(c.get("evidence_says", "")).strip()[:300]})
    return {
        "confirmed": _strings(payload.get("confirmed", []) or [], 30, 300),
        "contradicted": contradicted[:30],
        "unsupported": _strings(payload.get("unsupported", []) or [], 30, 300),
        "notes": str(payload.get("notes", "")).strip()[:1000],
    }


def validate_synthesis_outline_payload(payload: dict[str, Any], study_ids: list[str] | None = None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("Meta outline must be a JSON object.")
    allowed = set(study_ids or [])
    sections = []
    for i, s in enumerate(payload.get("sections", []) or []):
        if not isinstance(s, dict) or not str(s.get("heading", "")).strip():
            continue
        srcs = [str(x).strip() for x in (s.get("source_study_ids", []) or []) if str(x).strip()]
        if allowed:
            srcs = [x for x in srcs if x in allowed]
        sections.append({
            "id": f"sec{i + 1}",
            "heading": str(s["heading"]).strip()[:200],
            "theme_tags": _strings(s.get("theme_tags", []) or [], 8, 40),
            "source_study_ids": srcs[:50],
            "intent": str(s.get("intent", "")).strip()[:400],
        })
    if not sections:
        raise ValueError("Meta outline must contain at least one section with a heading.")
    return {"build_order_narrative": str(payload.get("build_order_narrative", "")).strip()[:6000],
            "title": str(payload.get("title", "")).strip()[:200],
            "sections": sections[:40]}


def validate_synthesis_section_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("Meta section must be a JSON object.")
    citations = []
    for c in payload.get("citations", []) or []:
        if isinstance(c, dict) and str(c.get("study_id", "")).strip():
            citations.append({"study_id": str(c["study_id"]).strip()[:80],
                              "council_id": str(c.get("council_id", "")).strip()[:80],
                              "quote": str(c.get("quote", "")).strip()[:600]})
    # figures (spec/meta-report-presentation-and-pdf §2): typed refs the renderer resolves to visuals —
    # {kind: asset|prototype|chart|avatar|graph, id|of|source_id, caption}. A chart figure carries an
    # author-supplied `series` whose per-item shape depends on `of` (see charts_catalogue): value+color
    # (bar/pie/column/progress_strip), +max (gauge), +sub (stats), nested segments (stacked_bar/column),
    # positive/negative (diverging_bar), a numeric `values` list (dot_plot/strip, heatmap rows), or a
    # `points` list (line/burnup/stacked_area). Figure-level keys: `labels`/`columns` (x ticks & headers),
    # `target`/`now` (burnup), `min`/`max`/`unit` (strip), `table` (column).
    # of="effort_impact" derives from source_id's synthesis.
    def _series_item(s: dict) -> dict:
        return {"label": str(s.get("label", "")).strip()[:120], "value": s.get("value"),
                "color": str(s.get("color", "")).strip()[:40]}

    def _num_list(xs: Any, cap: int) -> list:
        return [(v if isinstance(v, (int, float)) and not isinstance(v, bool) else None)
                for v in (xs[:cap] if isinstance(xs, (list, tuple)) else [])]
    figures = []
    for f in payload.get("figures", []) or []:
        if isinstance(f, dict) and str(f.get("kind", "")).strip():
            series = []
            for s in (f.get("series") or [])[:24]:
                if isinstance(s, dict) and str(s.get("label", "")).strip() != "":
                    item = _series_item(s)
                    if s.get("max") is not None:  # gauge scale
                        item["max"] = s.get("max")
                    if str(s.get("sub", "")).strip():  # stats secondary line
                        item["sub"] = str(s["sub"]).strip()[:80]
                    if s.get("positive") is not None or s.get("negative") is not None:  # diverging_bar
                        item["positive"], item["negative"] = s.get("positive"), s.get("negative")
                    if isinstance(s.get("segments"), list):  # stacked-bar composition
                        item["segments"] = [_series_item(g) for g in s["segments"][:12]
                                            if isinstance(g, dict) and str(g.get("label", "")).strip() != ""]
                    if isinstance(s.get("values"), list):  # dot_plot points / heatmap row
                        item["values"] = _num_list(s["values"], 40)
                    if isinstance(s.get("points"), list):  # line trend
                        item["points"] = _num_list(s["points"], 60)
                    series.append(item)
            fig = {"kind": str(f["kind"]).strip()[:24], "id": str(f.get("id", "")).strip()[:160],
                   "of": str(f.get("of", "")).strip()[:40], "source_id": str(f.get("source_id", "")).strip()[:120],
                   "caption": str(f.get("caption", "")).strip()[:300], "series": series}
            cols = [str(c).strip()[:60] for c in (f.get("columns") or [])[:20] if str(c).strip()]
            if cols:  # heatmap column headers
                fig["columns"] = cols
            labs = [str(x).strip()[:40] for x in (f.get("labels") or [])[:60]]
            if labs:  # line/burnup/stacked_area x-axis labels
                fig["labels"] = labs
            for k in ("target", "now", "min", "max"):  # burnup ideal/today · strip scale
                if isinstance(f.get(k), (int, float)) and not isinstance(f.get(k), bool):
                    fig[k] = f[k]
            if str(f.get("unit", "")).strip():  # strip unit suffix
                fig["unit"] = str(f["unit"]).strip()[:8]
            if f.get("table"):  # column breakdown table
                fig["table"] = True
            figures.append(fig)
    return {"markdown": str(payload.get("markdown", "")).strip()[:20000],
            "citations": citations[:50], "figures": figures[:20]}


def validate_synthesis_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate the host-authored synthesis PROSE + provenance. The structured content is the unified
    primitives (findings/statements/prompts) validated separately at record time — no compatibility list/voice
    shapes (spec/unified-artifact-schema.md)."""
    if not isinstance(payload, dict):
        raise ValueError("Synthesis must be a JSON object.")
    refs = []
    for r in payload.get("references", []) or []:
        if isinstance(r, dict) and str(r.get("council_id", "")).strip():
            refs.append({"council_id": str(r["council_id"]).strip()[:80], "role": str(r.get("role", "")).strip()[:300]})
    cite_kinds = {"evidence", "recall", "council"}
    citations = []
    for c in payload.get("citations", []) or []:
        if not isinstance(c, dict) or not str(c.get("ref", "")).strip():
            continue
        kind = str(c.get("kind", "")).strip().lower()
        citations.append({"kind": kind if kind in cite_kinds else "council",
                          "ref": str(c["ref"]).strip()[:80], "quote": str(c.get("quote", "")).strip()[:600]})
    return {
        "arc_narrative": str(payload.get("arc_narrative", "")).strip()[:6000],
        "gesamtbild": str(payload.get("gesamtbild", "")).strip()[:4000],
        "positionierung": str(payload.get("positionierung", "")).strip()[:2000],
        "references": refs[:50],
        "citations": citations[:50],
        "status": ("in_progress" if str(payload.get("status", "")).strip().lower() == "in_progress" else "done"),
        "next_council_question": str(payload.get("next_council_question", "")).strip()[:2000],
        "stop_reason": str(payload.get("stop_reason", "")).strip()[:600],
    }
