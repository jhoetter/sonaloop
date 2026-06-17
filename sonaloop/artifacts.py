"""Unified artifact primitives (spec/unified-artifact-schema.md + -rollout.md).

The whole research corpus reduces to five content primitives — Statement, Finding, Prompt, Ref, Stance —
that every artifact composes. This module is the DOMAIN layer (no web imports): the primitive
constructors, the data-driven vocabularies (stance scale, finding kinds), and — added in Phase 1 — the
read adapters that map current records onto the primitives. Reusable by web, export, report, search.
"""
from __future__ import annotations

import ast
import json
import re
from functools import lru_cache
from typing import Any

from .config import suggestions_dir


# --------------------------------------------------------------------------- vocabularies (data-driven)

@lru_cache(maxsize=1)
def _stance_scale() -> dict[str, Any]:
    """Load suggestions/stance_scale.json → {"by_term": {term: {value,label,color}}, "by_value": {...},
    "aliases": {alias: term}}. The ONE positivity vocabulary; no stance words hardcoded in engine/UI."""
    p = suggestions_dir() / "stance_scale.json"
    by_term: dict[str, dict] = {}
    by_value: dict[int, dict] = {}
    aliases: dict[str, str] = {}
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            data = {}
        for it in data.get("items", []) or []:
            term = it.get("tag")
            if not term:
                continue
            pres = it.get("presentation") or {}
            rec = {"value": int(it.get("value", 0)), "term": term,
                   "label_key": it.get("label_key") or term, "color": pres.get("color") or "var(--muted)"}
            by_term[term] = rec
            by_value[rec["value"]] = rec
            aliases[term] = term
        for alias, term in (data.get("aliases") or {}).items():
            aliases[str(alias).strip().lower()] = term     # lookup is case/whitespace-insensitive
    return {"by_term": by_term, "by_value": by_value, "aliases": aliases}


def _canon_term(label: Any) -> str | None:
    """Alias-map a free stance token onto its canonical term (case/whitespace-insensitive); None if unknown."""
    return _stance_scale()["aliases"].get(str(label).strip().lower())


def _clamp_value(v: int) -> int:
    """Snap an off-scale numeric value onto the nearest scale endpoint (data-driven, no -2/+2 literal)."""
    vals = sorted(_stance_scale()["by_value"]) or [0]
    return max(vals[0], min(vals[-1], v))


def resolve_stance(term: Any) -> dict[str, Any] | None:
    """Map any legacy stance/sentiment/vote token (or a numeric value) onto a canonical Stance dict
    {value,label}. Nothing degrades silently: an unknown non-empty token falls back to neutral (value 0)
    with the original kept as `label_raw`; an off-scale numeric clamps to the nearest endpoint with the
    original kept as `value_raw`. Returns None for empty input."""
    if term in (None, "", []):
        return None
    sc = _stance_scale()
    if isinstance(term, (int, float)) and not isinstance(term, bool):
        rec = sc["by_value"].get(int(term))
        if rec is None:
            v = _clamp_value(int(term))
            return {"value": v, "label": sc["by_value"][v]["term"], "value_raw": int(term)}
        return {"value": int(term), "label": rec["term"]}
    canon = _canon_term(term)
    rec = sc["by_term"].get(canon) if canon else None
    if rec is None:
        neutral = sc["by_value"].get(0) or {"value": 0, "term": "neutral"}
        return {"value": neutral["value"], "label": neutral["term"], "label_raw": str(term).strip()}
    return {"value": rec["value"], "label": rec["term"]}


def stance_meta(value: int) -> dict[str, str]:
    """Render fields for a stance value: an i18n `label_key` + `color`. Data-driven via the scale; the
    web layer resolves label_key through t() (this module stays web-free)."""
    rec = _stance_scale()["by_value"].get(int(value))
    return {"label_key": (rec or {}).get("label_key", "stance_neutral"),
            "color": (rec or {}).get("color", "var(--muted)")}


def stance_terms() -> list[dict[str, Any]]:
    """The scale's items ({term,value,label_key,color}) ordered +2 → −2 — the ONE order/color/label
    source for vote analytics (charts iterate this; no hardcoded vote vocabulary in web code)."""
    return sorted((dict(r) for r in _stance_scale()["by_term"].values()), key=lambda r: -r["value"])


def vote_stance(v: Any) -> dict[str, Any] | None:
    """A council vote IS a stance. Resolve a stored vote — normalized ({vote: term, stance: {...}}) or
    legacy ({vote: "SUPPORT"}) — onto the scale; None for an empty vote. No token can vanish: an
    unresolvable one buckets at neutral with `label_raw` (resolve_stance contract)."""
    if not isinstance(v, dict):
        return resolve_stance(v)
    if isinstance(v.get("stance"), dict):
        return validate_stance(v["stance"])
    return resolve_stance(v.get("vote") or v.get("stance") or v.get("label"))


def vote_tally(votes: list | None) -> dict[str, int]:
    """Tally votes by canonical stance term — every term present (+2 → −2 order, legend-stable),
    legacy tokens resolved via the scale's aliases, so no vote can vanish from a tally."""
    out = {r["term"]: 0 for r in stance_terms()}
    by_value = _stance_scale()["by_value"]
    for v in votes or []:
        st = vote_stance(v)
        if st is None:
            continue
        term = (by_value.get(st["value"]) or {}).get("term", str(st["value"]))
        out[term] = out.get(term, 0) + 1
    return out


@lru_cache(maxsize=1)
def _friction_scale() -> dict[str, Any]:
    """Load suggestions/friction_levels.json → the same shape as _stance_scale(): {"by_term": {...},
    "by_value": {...}, "aliases": {...}}. The ONE per-step friction vocabulary for usability sessions
    (0 none … 3 blocked); no friction words hardcoded in engine/UI."""
    p = suggestions_dir() / "friction_levels.json"
    by_term: dict[str, dict] = {}
    by_value: dict[int, dict] = {}
    aliases: dict[str, str] = {}
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            data = {}
        for it in data.get("items", []) or []:
            term = it.get("tag")
            if not term:
                continue
            pres = it.get("presentation") or {}
            rec = {"value": int(it.get("value", 0)), "term": term,
                   "label_key": it.get("label_key") or term, "color": pres.get("color") or "var(--muted)"}
            by_term[term] = rec
            by_value[rec["value"]] = rec
            aliases[term] = term
        for alias, term in (data.get("aliases") or {}).items():
            aliases[str(alias).strip().lower()] = term     # lookup is case/whitespace-insensitive
    return {"by_term": by_term, "by_value": by_value, "aliases": aliases}


def resolve_friction(term: Any) -> dict[str, Any] | None:
    """Map a friction token (or its numeric value) onto a canonical level {value, label}; aliases
    resolve case/whitespace-insensitively like resolve_stance. Unlike stances there is NO silent
    fallback: an unknown token returns None so the recorder can REJECT it — bucketing a 'blocked'
    read at 'none' would corrupt the session funnel."""
    if term in (None, "", []):
        return None
    sc = _friction_scale()
    if isinstance(term, (int, float)) and not isinstance(term, bool):
        rec = sc["by_value"].get(int(term))
        return {"value": rec["value"], "label": rec["term"]} if rec else None
    canon = sc["aliases"].get(str(term).strip().lower())
    rec = sc["by_term"].get(canon) if canon else None
    return {"value": rec["value"], "label": rec["term"]} if rec else None


def friction_terms() -> list[dict[str, Any]]:
    """The friction scale's items ({term,value,label_key,color}) in severity order (none → blocked) —
    the ONE order/color/label source for funnel/step rendering (mirror of stance_terms)."""
    return sorted((dict(r) for r in _friction_scale()["by_term"].values()), key=lambda r: r["value"])


@lru_cache(maxsize=1)
def _likelihood_scale() -> dict[str, Any]:
    """Load suggestions/likelihood_levels.json -> the same shape as _friction_scale(). The ONE
    likelihood vocabulary for predicted behaviors; each level's numeric midpoint is what the
    calibration loop scores against (ticket behavioral-prediction-output)."""
    p = suggestions_dir() / "likelihood_levels.json"
    by_term: dict[str, dict] = {}
    aliases: dict[str, str] = {}
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            data = {}
        for it in data.get("items", []) or []:
            term = it.get("tag")
            if not term:
                continue
            pres = it.get("presentation") or {}
            rec = {"value": float(it.get("value", 0.5)), "term": term,
                   "label_key": it.get("label_key") or term, "color": pres.get("color") or "var(--muted)"}
            by_term[term] = rec
            aliases[term] = term
        for alias, term in (data.get("aliases") or {}).items():
            aliases[str(alias).strip().lower()] = term
    return {"by_term": by_term, "aliases": aliases}


def resolve_likelihood(term: Any) -> dict[str, Any] | None:
    """Map a likelihood token onto {value (0..1), label}. A canonical term/alias resolves to its
    level midpoint; a NUMBER in 0..1 keeps its exact value and is labelled with the nearest level
    (calibration wants the raw probability when the author has one). Like friction there is NO
    silent fallback: an unknown token returns None so the recorder REJECTS it."""
    if term in (None, "", []):
        return None
    sc = _likelihood_scale()
    if isinstance(term, (int, float)) and not isinstance(term, bool):
        v = float(term)
        if not 0.0 <= v <= 1.0 or not sc["by_term"]:
            return None
        nearest = min(sc["by_term"].values(), key=lambda r: abs(r["value"] - v))
        return {"value": round(v, 4), "label": nearest["term"]}
    canon = sc["aliases"].get(str(term).strip().lower())
    rec = sc["by_term"].get(canon) if canon else None
    return {"value": rec["value"], "label": rec["term"]} if rec else None


def likelihood_terms() -> list[dict[str, Any]]:
    """The likelihood scale's items ({term,value,label_key,color}) in probability order — the ONE
    order/label source for prediction rendering (mirror of friction_terms)."""
    return sorted((dict(r) for r in _likelihood_scale()["by_term"].values()), key=lambda r: r["value"])


@lru_cache(maxsize=1)
def _tech_comfort_scale() -> dict[str, Any]:
    """Load suggestions/tech_comfort.json → the same shape as _friction_scale(): {"by_term": {...},
    "by_value": {...}, "aliases": {...}}. The ONE tech-comfort vocabulary for a persona's capability
    profile (1 novice … 5 expert); each rec also carries the behavioral `hint` session briefs surface.
    No comfort words hardcoded in engine/UI."""
    p = suggestions_dir() / "tech_comfort.json"
    by_term: dict[str, dict] = {}
    by_value: dict[int, dict] = {}
    aliases: dict[str, str] = {}
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            data = {}
        for it in data.get("items", []) or []:
            term = it.get("tag")
            if not term:
                continue
            pres = it.get("presentation") or {}
            rec = {"value": int(it.get("value", 0)), "term": term,
                   "label_key": it.get("label_key") or term, "hint": it.get("hint") or "",
                   "color": pres.get("color") or "var(--muted)"}
            by_term[term] = rec
            by_value[rec["value"]] = rec
            aliases[term] = term
        for alias, term in (data.get("aliases") or {}).items():
            aliases[str(alias).strip().lower()] = term     # lookup is case/whitespace-insensitive
    return {"by_term": by_term, "by_value": by_value, "aliases": aliases}


def resolve_tech_comfort(term: Any) -> dict[str, Any] | None:
    """Map a tech-comfort token (or its numeric 1-5 value) onto a canonical level {value, label, hint};
    aliases resolve case/whitespace-insensitively like resolve_friction. Like friction there is NO
    silent fallback: an unknown token returns None so the writer can REJECT it — calling a novice
    'comfortable' would corrupt every session simulated from the profile."""
    if term in (None, "", []):
        return None
    sc = _tech_comfort_scale()
    if isinstance(term, (int, float)) and not isinstance(term, bool):
        rec = sc["by_value"].get(int(term))
        return {"value": rec["value"], "label": rec["term"], "hint": rec["hint"]} if rec else None
    canon = sc["aliases"].get(str(term).strip().lower())
    rec = sc["by_term"].get(canon) if canon else None
    return {"value": rec["value"], "label": rec["term"], "hint": rec["hint"]} if rec else None


def tech_comfort_terms() -> list[dict[str, Any]]:
    """The tech-comfort scale's items ({term,value,label_key,hint,color}) in comfort order
    (novice → expert) — the ONE order/color/label/hint source for capability rendering (mirror of
    friction_terms)."""
    return sorted((dict(r) for r in _tech_comfort_scale()["by_term"].values()), key=lambda r: r["value"])


def tech_comfort_meta(value: Any) -> dict[str, str]:
    """Render fields for a tech-comfort value: an i18n `label_key` + `color` + the behavioral `hint`.
    Data-driven via the scale; the web layer resolves label_key through t() (this module stays
    web-free). Mirror of stance_meta."""
    rec = _tech_comfort_scale()["by_value"].get(int(value)) if isinstance(value, (int, float)) else None
    return {"label_key": (rec or {}).get("label_key", "tech_comfort_comfortable"),
            "color": (rec or {}).get("color", "var(--muted)"),
            "hint": (rec or {}).get("hint", "")}


@lru_cache(maxsize=1)
def _finding_kinds() -> dict[str, dict[str, Any]]:
    """Load suggestions/finding_kinds.json → {kind: {id, label_key}}. The section id/label vocabulary for
    Finding lists (the synthesis minimap anchors come from here)."""
    p = suggestions_dir() / "finding_kinds.json"
    out: dict[str, dict] = {}
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            data = {}
        for it in data.get("items", []) or []:
            k = it.get("tag")
            if k:
                out[k] = {"id": it.get("id") or k, "label_key": it.get("label_key") or k}
    return out


def finding_kind(kind: str) -> dict[str, Any]:
    """{id, label_key} for a finding kind; generic fallback for an invented kind (no code change needed)."""
    return _finding_kinds().get(kind, {"id": kind, "label_key": kind})


def reload_vocab() -> None:                # mirror presentation.reload_hints() for tests
    _stance_scale.cache_clear()
    _friction_scale.cache_clear()
    _likelihood_scale.cache_clear()
    _finding_kinds.cache_clear()


# --------------------------------------------------------------------------- primitive constructors

def _clean(d: dict) -> dict:
    """Drop empty optionals so the stored JSON stays lean (None / "" / [] / {})."""
    return {k: v for k, v in d.items() if v not in (None, "", [], {})}


_REF_ROUTES = {"council": "/councils/", "synthesis": "/syntheses/", "persona": "/personas/",
               "survey": "/surveys/", "session": "/sessions/", "prototype_session": "/sessions/",
               "hypothesis": "/hypotheses/",
               "decision": "/decisions/", "prototype": "/prototypes/", "note": "/notes/"}


def ref_href(r: dict) -> str | None:
    """The internal link for a record-pointing Ref (kept in the DOMAIN layer so the web renderer never
    hardcodes a kind→route literal — the kind-vocabulary grep gate). When the ref carries an `anchor`
    (a part within the artifact) the link deep-links to that part via `#<anchor>`. A usability-session
    step anchor (`step:<index>`) maps onto the replay view's per-step DOM id (`#step-<index>`)."""
    base = _REF_ROUTES.get(r.get("kind"))
    if not (base and r.get("id")):
        return None
    anchor = r.get("anchor")
    if anchor and r.get("kind") == "session" and anchor.startswith("step:"):
        anchor = "step-" + anchor.split(":", 1)[1]
    return base + r["id"] + (f"#{anchor}" if anchor else "")


def ref(kind: str, *, id: str | None = None, anchor: str | None = None, role: str | None = None,
        text: str | None = None, quote: str | None = None) -> dict:
    """A typed cross-reference (spec/artifact-cross-references.md). kind: memory|council|synthesis|note|
    prototype|persona|prototype_state|session|external. `id` points at a record; `anchor` addresses a PART
    within it (a statement/finding/prose-block id — or `step:<index>` for a usability-session step,
    None = whole artifact); `role` is the typed relation
    (cites|reinterprets|derived_from|answers|supports|refutes|…, open vocab). `quote` is an OPTIONAL
    cached display hint — the source of truth is resolved LIVE from the addressed part. `text` is only for
    anchor-less observed-state strings."""
    return _clean({"kind": kind, "id": id, "anchor": anchor, "role": role, "text": text, "quote": quote})


def part_address(kind: str, id: str, anchor: str | None = None) -> str:
    """Canonical URI for an artifact or one of its parts: 'kind:id' or 'kind:id#part'."""
    return f"{kind}:{id}" + (f"#{anchor}" if anchor else "")


def parse_address(addr: str) -> dict[str, Any]:
    """Inverse of part_address: 'kind:id#part' -> {kind, id, anchor}."""
    kind, _, rest = (addr or "").partition(":")
    rid, _, anchor = rest.partition("#")
    return {"kind": kind, "id": rid, "anchor": anchor or None}


def assign_part_ids(parts: list[dict], prefix: str) -> list[dict]:
    """Give each part a STABLE id (prefix + 1-based index) if it lacks one, so other artifacts can address
    it via a Ref anchor + the UI can deep-link to it. Returns the same list (ids assigned in place)."""
    for i, p in enumerate(parts, 1):
        if isinstance(p, dict) and not p.get("id"):
            p["id"] = f"{prefix}{i}"
    return parts


# Named prose blocks a Ref can anchor to (synthesis), kept here so the addressing vocab is in one place.
_PROSE_PARTS = ("gesamtbild", "positionierung", "arc_narrative", "exec_summary", "summary")


def _find_part(art: dict, anchor: str) -> dict | None:
    """Find the part with id == anchor inside an artifact (statements/findings/prompts), a named prose
    block wrapped as {text}, or a usability-session step addressed as `step:<index>`. Returns None for
    a broken anchor."""
    if anchor in _PROSE_PARTS:
        return {"text": art.get(anchor, "")} if art.get(anchor) else None
    if anchor.startswith("step:") and isinstance(art.get("steps"), list):
        try:
            idx = int(anchor.split(":", 1)[1])
        except ValueError:
            return None
        for s in art["steps"]:
            if isinstance(s, dict) and s.get("index") == idx:
                return {"text": s.get("monologue") or (s.get("action") or {}).get("detail", "")}
        return None
    for key in ("statements", "findings", "prompts"):
        for p in (art.get(key) or []):
            if isinstance(p, dict) and p.get("id") == anchor:
                return p
    # sessions live outside the artifact dict; the resolver handles those by id directly
    return None


def resolve_ref(r: dict, store: Any) -> dict[str, Any]:
    """Resolve a Ref to the LIVE content of the artifact/part it addresses — never a stale copy
    (spec/artifact-cross-references.md). `store` is duck-typed (get_council_session/get_synthesis/
    get_prototype/get_persona). Returns {kind,id,anchor,role,href,exists,title,text,persona_id}; a missing
    record or broken anchor yields exists=False so the UI can show it honestly."""
    kind, rid, anchor = r.get("kind"), r.get("id"), r.get("anchor")
    out = {"kind": kind, "id": rid, "anchor": anchor, "role": r.get("role"), "href": ref_href(r),
           "exists": False, "title": "", "text": r.get("quote") or r.get("text") or "", "persona_id": ""}
    if not rid:                                          # free observed-state / external string ref
        out["exists"] = bool(out["text"])
        return out
    getter = {"council": "get_council_session", "synthesis": "get_synthesis",
              "prototype": "get_prototype", "persona": "get_persona",
              "session": "get_usability_session", "survey": "get_survey",
              "prototype_session": "get_prototype_session",
              "hypothesis": "get_hypothesis", "decision": "get_decision",
              "evidence": "get_evidence"}.get(kind)
    art = getattr(store, getter)(rid) if (getter and hasattr(store, getter)) else None
    if not art and kind == "session" and hasattr(store, "get_prototype_session"):
        art = store.get_prototype_session(rid)
    if not art:
        return out
    out["exists"] = True
    out["title"] = (art.get("title") or art.get("prompt") or art.get("name")
                    or art.get("text") or art.get("notes") or rid)
    if anchor:
        part = _find_part(art, anchor)
        if part is None:
            out["exists"] = False                       # broken anchor (part edited away / renumbered)
        else:
            out["text"] = part.get("text") or part.get("body") or out["text"]
            out["persona_id"] = part.get("persona_id", "")
    return out


def stance(value: int, *, label: str | None = None) -> dict:
    """A point on the one positivity scale (-2 oppose … +2 support). The stored value is ALWAYS on-scale
    and the label ALWAYS its canonical term: a free label is alias-resolved; on disagreement the explicit
    (on-scale) value wins. An OFF-scale value is an invalid signal, so a resolvable label decides instead;
    failing that the value clamps to the nearest endpoint. Whatever loses survives as `label_raw` /
    `value_raw` — never silently dropped."""
    sc = _stance_scale()
    rec = sc["by_value"].get(int(value))
    canon = _canon_term(label) if label is not None else None
    if rec is None:                          # off-scale value: the resolvable label is the better signal
        if canon is not None:
            term = sc["by_term"][canon]
            return {"value": term["value"], "label": term["term"], "value_raw": int(value)}
        v = _clamp_value(int(value))
        return _clean({"value": v, "label": sc["by_value"][v]["term"], "value_raw": int(value),
                       "label_raw": str(label).strip() if label is not None else None})
    if label is None or canon is not None:
        return {"value": int(value), "label": rec["term"]}
    return _clean({"value": int(value), "label": rec["term"], "label_raw": str(label).strip()})


def prompt(text: str, *, kind: str = "question", id: str | None = None) -> dict:
    """The thing posed. kind: question|proposal|goal|focus|hypothesis."""
    return _clean({"text": text or "", "kind": kind, "id": id})


def statement(persona_id: str, text: str, *, id: str | None = None, stance: dict | None = None,
              about: dict | None = None, refs: list | tuple = (), relevance: str | None = None,
              shift: dict | None = None, meta: dict | None = None) -> dict:
    """A persona's utterance — the unifier for council turns, synthesis voices and prototype reactions.
    `id` is the stable part id (for addressing/deep-link); `about` is a Ref/Prompt-id it responds to;
    `refs` is the grounding; artifact extras go in `meta`."""
    return _clean({"id": id, "persona_id": persona_id or "", "text": text or "", "stance": stance,
                   "about": about, "refs": list(refs), "relevance": relevance,
                   "shift": shift, "meta": meta})


def finding(text: str, *, kind: str, id: str | None = None, score: dict | int | None = None,
            refs: list | tuple = (), meta: dict | None = None) -> dict:
    """An authored analysis item (key_problem, recommendation, open_question, cluster, …): markdown text,
    optional score (e.g. {effort,value}), optional grounding refs, kind-specific extras in `meta`. `id` is
    the stable part id (for addressing/deep-link)."""
    return _clean({"id": id, "text": text or "", "kind": kind, "score": score, "refs": list(refs), "meta": meta})


def event(persona_id: str, time: str, *, kind: str, body: str, refs: list | tuple = (),
          meta: dict | None = None) -> dict:
    """A time-stamped thing in a persona's life (Layer 3 — spec/unified-artifact-schema.md §5b). Unifies
    ExperienceEvent / CalendarEvent / DailySummary / Reflection: actor + time + kind + Markdown body + refs."""
    return _clean({"persona_id": persona_id or "", "time": time or "", "kind": kind,
                   "body": body or "", "refs": list(refs), "meta": meta})


def pain_point_finding(obs: dict) -> dict:
    """A PainPointObservation → a persona-scoped Finding (kind='pain_point'): the issue is the text, the
    opportunity the detail, severity/frequency the score, evidence the refs (Layer 3, §5b)."""
    sev, freq = obs.get("severity"), obs.get("frequency")
    return finding(obs.get("issue", ""), kind="pain_point",
                   score=({"severity": sev, "frequency": freq} if sev else None),
                   refs=[ref("memory", id=str(e)) for e in (obs.get("evidence_event_ids") or [])],
                   meta=({"detail": obs.get("opportunity", "")} if obs.get("opportunity") else None))


# --------------------------------------------------------------------------- validators (Phase 2 native authoring)
# Lenient normalizers for host-authored primitives — re-run input dicts through the constructors so a
# recorded record is always well-shaped (stance resolved through the scale, empties dropped).

def validate_ref(d: dict) -> dict:
    return ref(d.get("kind", "external"), id=d.get("id"), anchor=d.get("anchor"), role=d.get("role"),
               text=d.get("text"), quote=d.get("quote"))


def validate_stance(d) -> dict | None:
    if d in (None, "", []):
        return None
    if isinstance(d, dict) and "value" in d:
        out = stance(int(d["value"]), label=d.get("label"))
        for raw in ("label_raw", "value_raw"):              # idempotent: re-validating keeps the raw signals
            if d.get(raw) is not None and raw not in out:
                out[raw] = d[raw]
        return out
    return resolve_stance(d)


def validate_prompt(d: dict) -> dict:
    return prompt(d.get("text", ""), kind=d.get("kind", "question"), id=d.get("id"))


def validate_statement(d: dict) -> dict:
    return statement(d.get("persona_id", ""), d.get("text", ""), id=d.get("id"),
                     stance=validate_stance(d.get("stance")),
                     about=(validate_ref(d["about"]) if d.get("about") else None),
                     refs=[validate_ref(r) for r in (d.get("refs") or [])],
                     relevance=d.get("relevance"), shift=d.get("shift") or None, meta=d.get("meta") or None)


def validate_finding(d: dict) -> dict:
    return finding(d.get("text", ""), kind=d.get("kind", "note"), id=d.get("id"), score=d.get("score") or None,
                   refs=[validate_ref(r) for r in (d.get("refs") or [])], meta=d.get("meta") or None)


def predicted_behavior(action: str, *, step: int | None = None, subject: str = "",
                       likelihood: Any = None, trigger: str = "", refs: list | None = None,
                       persona_id: str = "", id: str | None = None, meta: dict | None = None) -> dict:
    """The behavioral-prediction primitive (ticket behavioral-prediction-output): a concrete
    predicted ACTION — "abandons at the price reveal" — not a sentiment. `likelihood` resolves on
    the canonical scale (or a raw 0..1 number, kept exact); `refs` is the evidence layer (grounding
    chunks {kind:'evidence'}, session steps, memory) that makes the prediction auditable; the
    structured shape is what the calibration loop scores against."""
    act = str(action or "").strip()
    if not act:
        raise ValueError("predicted_behavior.action is required (the concrete action, not a vibe)")
    lk = None
    if likelihood not in (None, "", []):
        lk = resolve_likelihood(likelihood)
        if lk is None:
            raise ValueError(f"likelihood {likelihood!r} is not on the scale — "
                             "suggest_likelihood_levels() names the valid levels (or pass 0..1)")
    if step is not None and (not isinstance(step, int) or isinstance(step, bool)):
        raise ValueError("predicted_behavior.step must be an int step index or null")
    return _clean({"id": id, "action": act, "step": step, "subject": str(subject or ""),
                   "likelihood": lk, "trigger": str(trigger or ""), "persona_id": str(persona_id or ""),
                   "refs": [validate_ref(r) for r in (refs or [])], "meta": meta or None})


def validate_predicted_behavior(d: dict) -> dict:
    return predicted_behavior(d.get("action", ""), step=d.get("step"), subject=d.get("subject", ""),
                              likelihood=(d.get("likelihood") if not isinstance(d.get("likelihood"), dict)
                                          else d["likelihood"].get("value")),
                              trigger=d.get("trigger", ""), refs=d.get("refs") or [],
                              persona_id=d.get("persona_id", ""), id=d.get("id"), meta=d.get("meta") or None)


def validate_event(d: dict) -> dict:
    return event(d.get("persona_id", ""), d.get("time", ""), kind=d.get("kind", "event"),
                 body=d.get("body", ""), refs=[validate_ref(r) for r in (d.get("refs") or [])],
                 meta=d.get("meta") or None)


# --------------------------------------------------------------------------- primitive accessors
# Storage is primitives-only: councils/syntheses carry their statements/findings natively (these return
# them). council_prompts BUILDS the prompt primitives from the council's canonical question/proposal
# fields; session_statements maps a prototype session's reaction → a statement.

_UESC = re.compile(r"\\u([0-9a-fA-F]{4})")


def heal_text(value: Any) -> str:
    """Defensive read for the second real host slip (owner round 5): prompt/title text that
    carries LITERAL ``\\uXXXX`` escape sequences ("Premium \\u2013 Pricing") — another agent
    authored on a sibling store with double-escaped JSON. Decodes the escapes (surrogate
    pairs included) to the real characters ("Premium – Pricing"); text without the pattern
    passes through untouched, and decoding never raises."""
    s = str(value or "")
    if "\\u" not in s:
        return s
    try:
        decoded = _UESC.sub(lambda m: chr(int(m.group(1), 16)), s)
        # re-join any surrogate pairs the literal escapes spelled out (e.g. \\ud83d\\ude00)
        return decoded.encode("utf-16", "surrogatepass").decode("utf-16")
    except (ValueError, UnicodeError):
        return s


def _prompt_text(value: Any) -> str:
    """Defensive read for a real host slip: a prompt/question recorded as the REPR of a prompt
    dict ("{'id': 'q0', 'kind': 'question', 'text': '…'}") unwraps to the inner text instead of
    surfacing as JSON on the page. Literal \\uXXXX escapes heal too (heal_text). Anything else
    passes through untouched."""
    s = str(value or "")
    t = s.strip()
    if t.startswith("{") and t.endswith("}"):
        try:
            parsed = ast.literal_eval(t)
        except (ValueError, SyntaxError):
            return heal_text(s)
        if isinstance(parsed, dict) and parsed.get("text"):
            return heal_text(str(parsed["text"]))
    return heal_text(s)


def council_prompts(c: dict) -> list[dict]:
    if c.get("prompts"):
        return [{**p, "text": _prompt_text(p.get("text"))} for p in c["prompts"]]
    out = []
    if c.get("prompt"):
        out.append(prompt(_prompt_text(c["prompt"]), kind="question", id="prompt"))
    if c.get("proposal"):
        out.append(prompt(_prompt_text(c["proposal"]), kind="proposal", id="proposal"))
    for i, q in enumerate(c.get("questions") or []):
        out.append(prompt(_prompt_text(q), kind="question", id=f"q{i}"))
    return out


def council_statements(c: dict) -> list[dict]:
    """The council's persona statements (the ONE voice representation — authored natively)."""
    return list(c.get("statements") or [])


def synthesis_statements(s: dict) -> list[dict]:
    """The synthesis's voice statements (authored natively)."""
    return list(s.get("statements") or [])


# ---- read projections: readers (markdown export / briefs / graph node / sentiment strip) that think in
# the old field shapes get them reconstructed from the stored findings/statements. Storage is
# primitives-only; these are READ helpers, never written (spec/unified-artifact-schema).

# stance value (-2..+2) → the legacy sentiment word, for the synthesis header's count strip.
_STANCE_SENTIMENT = {2: "positiv", 1: "bedingt", 0: "neutral", -1: "skeptisch", -2: "ablehnend"}


def finding_texts(s: dict, kind: str) -> list[str]:
    """The text of every finding of `kind` (e.g. 'key_problem', 'pain_solver', 'open_question')."""
    return [f.get("text", "") for f in synthesis_findings(s) if f.get("kind") == kind]


def synthesis_recommendations(s: dict) -> list[tuple]:
    """[(text, effort, value)] for the recommendation findings — the effort·impact chart + report."""
    out = []
    for f in synthesis_findings(s):
        if f.get("kind") == "recommendation":
            sc = f.get("score") or {}
            out.append((f.get("text", ""), sc.get("effort"), sc.get("value")))
    return out


def synthesis_sentiment_counts(s: dict, store: Any = None) -> dict[str, int]:
    """Counts keyed by the legacy sentiment word, aggregated over the REAL council voices the synthesis
    consolidates (the synthesis no longer holds its own voices — spec/artifact-cross-references.md).
    `store` is duck-typed (get_council_session); without it, falls back to any stored synthesis voices."""
    stmts: list[dict] = []
    if store is not None:
        for cid in s.get("council_ids") or []:
            stmts.extend((store.get_council_session(cid) or {}).get("statements") or [])
    if not stmts:
        stmts = synthesis_statements(s)
    counts: dict[str, int] = {}
    for st in stmts:
        val = (st.get("stance") or {}).get("value")
        if val is None:
            continue
        word = _STANCE_SENTIMENT.get(val, "neutral")
        counts[word] = counts.get(word, 0) + 1
    return counts


def synthesis_findings(s: dict) -> list[dict]:
    """The synthesis's findings (key_problem/pain_solver/recommendation/cluster/segment/ranking/… —
    authored natively as the ONE finding primitive)."""
    return list(s.get("findings") or [])


def session_statements(se: dict, persona_name: str | None = None) -> list[dict]:
    if se.get("statements"):
        return list(se["statements"])
    r = se.get("reaction") if isinstance(se.get("reaction"), dict) else {}
    refs = [ref("prototype_state", text=str(x)) for x in (se.get("observed_state_refs") or r.get("observed_state_refs") or [])]
    text = r.get("verdict") or r.get("reaction_text") or r.get("summary") or ""
    extra = {k: v for k, v in r.items()
             if k not in ("persona", "fidelity", "version", "observed_state_refs", "self_authored",
                          "session_id", "grounded_verified", "grounded", "verdict", "reaction_text", "summary", "focus")
             and v not in (None, "", [], {})}
    meta = {"grounded": bool(se.get("grounded_verified"))}   # → the grounded chip in the card header
    ctx = " · ".join(x for x in [r.get("fidelity"), r.get("version")] if x)
    if ctx:
        meta["context"] = ctx                       # → the card's ctx line (fidelity · version)
    meta.update(extra)
    # the session's `focus` (what was tested) becomes the prompt BANNER above the cards (uniform with
    # council/synthesis voices) — not a line inside the card; see session_focus().
    about = ref("prompt", id="focus") if r.get("focus") else None
    return [statement(se.get("persona_id", ""), text, about=about, refs=refs, meta=meta or None)]


def session_focus(se: dict) -> str:
    """The session's test focus — rendered as the prompt banner above the session cards (id 'focus')."""
    return ((se.get("reaction") or {}).get("focus") or "") if isinstance(se.get("reaction"), dict) else ""


def note_findings(n: dict) -> list[dict]:
    if n.get("findings"):
        return list(n["findings"])
    return [finding(n.get("text", ""), kind=(n.get("kind") or "note"))] if n.get("text") else []
