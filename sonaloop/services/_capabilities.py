"""Persona capability profile: which session fidelities a persona can be simulated at + how it
actually moves through an interface.

Stored on the persona as `capabilities` ({rungs:{see,walk,drive,login}, tech_comfort: 1-5
(vocabulary: suggestions/tech_comfort.json), devices, accessibility, provenance}); personas
persisted WITHOUT one get a DERIVED heuristic profile in the returned dict only — the stored
persona is never rewritten on read. Session briefs (usability + prototype) surface the profile and
WARN (never block) when the requested fidelity exceeds the declared rungs.
Cross-module function references are bound at import time by services/__init__.py."""

from __future__ import annotations

import re
from typing import Any

from .. import artifacts as _A


CAPABILITY_RUNGS = ("see", "walk", "drive", "login")
_CAPABILITY_KEYS = ("rungs", "tech_comfort", "devices", "accessibility", "provenance")
_CAPABILITY_PROVENANCES = ("authored", "derived", "evidence")
# Which rung a session fidelity needs: look at an artifact -> see, click a prototype -> walk,
# drive the live thing -> drive. Login is orthogonal (credential-gated subjects).
_RUNG_FOR_FIDELITY = {"artifact": "see", "prototype": "walk", "live": "drive"}
_LOGIN_HINTS = ("login", "log in", "log-in", "sign in", "sign-in", "signin", "anmeld",
                "passwor", "credential", "konto")
_EXPERT_ROLE_HINTS = ("software", "developer", "entwickler", "programmier", "devops", "sysadmin",
                      "informatik")
_TECHNICAL_ROLE_HINTS = ("engineer", "ingenieur", "techni", "it-", "data scien")
_SENIOR_HINTS = ("retired", "rentner", "pension", "ruhestand")


def default_capabilities() -> dict[str, Any]:
    """The safe default profile: every rung except login, mid comfort, the common devices."""
    return {"rungs": {"see": True, "walk": True, "drive": True, "login": False},
            "tech_comfort": 3, "devices": ["desktop", "mobile"], "accessibility": "",
            "provenance": "authored"}


def _capability_age(persona: dict[str, Any]) -> int | None:
    """Best-effort age signal: demographics.age, else the max number in identity_traits.age_range."""
    for raw in ((persona.get("demographics") or {}).get("age"),
                (persona.get("identity_traits") or {}).get("age_range")):
        if isinstance(raw, (int, float)) and not isinstance(raw, bool):
            return int(raw)
        nums = re.findall(r"\d+", str(raw or ""))
        if nums:
            return max(int(n) for n in nums)
    return None


def derive_capabilities(persona: dict[str, Any]) -> dict[str, Any]:
    """A pure, deterministic heuristic profile for personas that never declared capabilities.

    Intentionally SIMPLE (a documented contract, not a model) — scanned over role title/
    responsibilities, the company stack and the tools:
      - software/developer/devops roles        -> expert (5)
      - other engineering/technical/IT roles   -> fluent (4)
      - senior age (>= 75)                     -> novice (1)
      - senior age (>= 65) or retirement hints -> cautious (2)
      - everyone else                          -> comfortable (3)
    Rungs/devices stay at the safe defaults. Marked provenance='derived'; NEVER persisted —
    declare the real profile via update_persona or the brief_persona -> record_persona path."""
    role = persona.get("role") or {}
    haystack = " ".join(str(x) for x in (
        role.get("title"), role.get("responsibilities"),
        (persona.get("company_context") or {}).get("stack"),
        " ".join(persona.get("tools") or []))).lower()
    age = _capability_age(persona)
    if any(k in haystack for k in _EXPERT_ROLE_HINTS):
        comfort = 5
    elif any(k in haystack for k in _TECHNICAL_ROLE_HINTS):
        comfort = 4
    elif age is not None and age >= 75:
        comfort = 1
    elif (age is not None and age >= 65) or any(k in haystack for k in _SENIOR_HINTS):
        comfort = 2
    else:
        comfort = 3
    return {**default_capabilities(), "tech_comfort": comfort, "provenance": "derived"}


def validate_capabilities(patch: Any) -> dict[str, Any]:
    """Validate a capabilities dict/patch (shape + vocabulary); returns only the validated fields.
    Unknown keys, unknown/non-bool rungs, off-scale tech_comfort (vocabulary: suggest_tech_comfort,
    aliases resolve), non-string devices and unknown provenance are REJECTED — capability claims
    gate session fidelity, so they never degrade silently."""
    if not isinstance(patch, dict):
        raise ValueError("capabilities must be an object {rungs?, tech_comfort?, devices?, "
                         "accessibility?, provenance?}")
    unknown = sorted(set(patch) - set(_CAPABILITY_KEYS))
    if unknown:
        raise ValueError(f"unknown capabilities key(s) {unknown} — valid: {list(_CAPABILITY_KEYS)}")
    out: dict[str, Any] = {}
    if "rungs" in patch:
        rungs = patch["rungs"]
        if not isinstance(rungs, dict):
            raise ValueError("capabilities.rungs must be an object {see, walk, drive, login}")
        bad = sorted(set(rungs) - set(CAPABILITY_RUNGS))
        if bad:
            raise ValueError(f"unknown rung(s) {bad} — valid: {list(CAPABILITY_RUNGS)}")
        for k, v in rungs.items():
            if not isinstance(v, bool):
                raise ValueError(f"capabilities.rungs.{k} must be a bool")
        out["rungs"] = dict(rungs)
    if "tech_comfort" in patch:
        level = _A.resolve_tech_comfort(patch["tech_comfort"])
        if level is None:
            raise ValueError(f"capabilities.tech_comfort {patch['tech_comfort']!r} is not on the "
                             "1-5 comfort scale — suggest_tech_comfort() names the valid levels "
                             "(aliases resolve)")
        out["tech_comfort"] = level["value"]
    if "devices" in patch:
        devices = patch["devices"]
        if not isinstance(devices, list) or not all(isinstance(d, str) and d.strip() for d in devices):
            raise ValueError("capabilities.devices must be a list of non-empty strings")
        out["devices"] = [d.strip() for d in devices]
    if "accessibility" in patch:
        if not isinstance(patch["accessibility"], str):
            raise ValueError("capabilities.accessibility must be a string (notes briefs must surface)")
        out["accessibility"] = patch["accessibility"].strip()
    if "provenance" in patch:
        if patch["provenance"] not in _CAPABILITY_PROVENANCES:
            raise ValueError(f"capabilities.provenance must be one of {'|'.join(_CAPABILITY_PROVENANCES)}")
        out["provenance"] = patch["provenance"]
    return out


def merge_capabilities(base: Any, patch: Any) -> dict[str, Any]:
    """A validated `patch` merged onto the persona's declared profile (else the safe defaults) into
    a FULL normalized profile. A patch marks the profile authored unless it says otherwise — a host
    explicitly declaring capabilities IS authorship."""
    valid = validate_capabilities(patch)
    base = base if isinstance(base, dict) else {}
    out = {**default_capabilities(), **base}
    out["rungs"] = {**default_capabilities()["rungs"],
                    **(base.get("rungs") if isinstance(base.get("rungs"), dict) else {}),
                    **valid.pop("rungs", {})}
    provenance = valid.pop("provenance", "authored")
    out.update(valid)
    out["provenance"] = provenance
    return out


def capability_profile(persona: dict[str, Any]) -> dict[str, Any]:
    """The capability profile IN EFFECT for a persona: its declared `capabilities` normalized over
    the safe defaults (missing fields filled, compatibility extra keys preserved), or — when none was ever
    declared — the derived heuristic profile. Pure read: never rewrites the stored persona."""
    declared = persona.get("capabilities")
    if not isinstance(declared, dict):
        return derive_capabilities(persona)
    out = {**default_capabilities(), **declared}
    out["rungs"] = {**default_capabilities()["rungs"],
                    **(declared.get("rungs") if isinstance(declared.get("rungs"), dict) else {})}
    level = _A.resolve_tech_comfort(out.get("tech_comfort"))     # compatibility tokens tolerated on READ
    out["tech_comfort"] = level["value"] if level else default_capabilities()["tech_comfort"]
    if out.get("provenance") not in _CAPABILITY_PROVENANCES:
        out["provenance"] = "authored"
    return out


def capability_fidelity_warnings(profile: dict[str, Any], fidelity: str,
                                 subject_text: str = "") -> list[str]:
    """Fidelity gating (WARN, never block): flags a requested session fidelity that exceeds the
    persona's declared rungs into the brief instead of silently simulating past it. Mapping:
    artifact→see, prototype→walk, live→drive; a subject that smells like credentials/login also
    needs rungs.login."""
    rungs = (profile or {}).get("rungs") or {}
    out: list[str] = []
    rung = _RUNG_FOR_FIDELITY.get(fidelity)
    if rung and not rungs.get(rung, True):
        out.append(f"FIDELITY_EXCEEDS_RUNGS: fidelity '{fidelity}' needs rungs.{rung}, but this "
                   f"persona's capability profile ({profile.get('provenance', 'derived')}) declares "
                   f"rungs.{rung}=false — simulate at a lower rung, or treat the session as speculative.")
    if not rungs.get("login", False) and any(k in (subject_text or "").lower() for k in _LOGIN_HINTS):
        out.append("LOGIN_RUNG: the subject involves credentials/login but the persona's capability "
                   "profile declares rungs.login=false — keep the session outside authenticated "
                   "areas, or treat what happens behind the sign-in as speculative.")
    return out


def capability_context_line(profile: dict[str, Any]) -> str:
    """The one-line capability framing session briefs append to their anti-steering instructions:
    the tech-comfort behavioral hint is the pace/voice contract the simulated steps must honor."""
    level = _A.resolve_tech_comfort(profile.get("tech_comfort")) or \
        _A.resolve_tech_comfort(default_capabilities()["tech_comfort"])
    extras = []
    if profile.get("devices"):
        extras.append("devices: " + ", ".join(profile["devices"]))
    if profile.get("accessibility"):
        extras.append("accessibility: " + profile["accessibility"])
    return (f" Capability profile ({profile.get('provenance', 'derived')}): tech comfort "
            f"{level['value']}/5 ({level['label']}) — {level['hint']} — pace every step accordingly"
            + ("; " + "; ".join(extras) if extras else "") + ".")
