"""Usability sessions — the durable, replayable session trace (THE SESSION IS THE DELIVERABLE).

One schema serves all three fidelity rungs (artifact flow → prototype → live browser); only the
fidelity of each step's `state` changes. House triplet: brief_usability_session GATHERS (persona
context + anti-steering + the subject's how-to-drive), the host authors the dual timeline, and
record_usability_session VALIDATES + persists — no server-side text. Supersedes the reaction-only
PrototypeSession record (kept for back-compat).
Cross-module function references are bound at import time by services/__init__.py."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .. import artifacts as _A
from .. import browser as _browser
from .. import primitive_taxonomy_registry as _taxonomy_registry
from .. import prototypes as _proto
from .. import walk_policy as _wp
from .. import config
from ..config import sessions_dir, utc_now_iso
from ..models import UsabilitySession
from ..storage import Store
from ..suggestions import suggest_friction_levels
from ._authoring import PRIMITIVES_CONTRACT
from ._common import _require_persona, stable_id


_SUBJECT_KINDS = ("flow", "prototype", "live_url", "variant")
_FIDELITIES = ("artifact", "prototype", "live")
_ACTION_TYPES = ("look", "click", "type", "select", "scroll", "key", "navigate", "back",
                 "wait", "give_up")


def _validate_subject(subject: Any) -> dict[str, Any]:
    if not isinstance(subject, dict):
        raise ValueError("subject must be a dict {kind: " + "|".join(_SUBJECT_KINDS) + ", id?, url?, label}")
    kind = subject.get("kind")
    if kind not in _SUBJECT_KINDS:
        raise ValueError(f"subject.kind must be one of {'|'.join(_SUBJECT_KINDS)}, got {kind!r}")
    label = str(subject.get("label") or "").strip()
    if not label:
        raise ValueError("subject.label is required (what the persona was asked to use)")
    if not (subject.get("id") or subject.get("url")):
        raise ValueError("subject needs an `id` (flow/prototype) or a `url` (live_url)")
    out = {"kind": kind, "label": label}
    if subject.get("id"):
        out["id"] = str(subject["id"])
    if subject.get("url"):
        # The stored subject.url lands in an href on the replay page — only http(s) is a
        # walkthrough subject (origin_of rejects javascript:/data:/file: with a clear error).
        _wp.origin_of(subject["url"])
        out["url"] = str(subject["url"])
    return out


def _subject_key(subject: dict[str, Any]) -> str:
    return str(subject.get("id") or subject.get("url") or "")


def session_form(session: dict[str, Any]) -> str:
    """Classify usability/prototype-session records through the form registry.

    A `flow` subject is material; the test run form is `walkthrough`. Compatibility
    PrototypeSession records have `prototype_id` rather than a `subject`, and
    still resolve to `prototype_use`.
    """
    subject = session.get("subject") or {}
    if session.get("variants") or subject.get("kind") == "variant":
        alias = "variant_test"
    elif session.get("prototype_id") and not subject:
        alias = "prototype_session"
    else:
        alias = {
            "flow": "walkthrough_session",
            "prototype": "prototype_session",
            "live_url": "live_session",
        }.get(str(subject.get("kind") or ""), str(subject.get("kind") or ""))
    form = _taxonomy_registry.resolve_form("session", alias)
    return str((form or {}).get("id") or alias)


def session_form_definition(session: dict[str, Any]) -> dict[str, Any]:
    form_id = session_form(session)
    form = _taxonomy_registry.resolve_form("session", form_id)
    if form is None:
        raise KeyError(f"No registered session form '{form_id}'")
    return form


def _require_fidelity(fidelity: str) -> None:
    if fidelity not in _FIDELITIES:
        raise ValueError(f"fidelity must be one of {'|'.join(_FIDELITIES)}, got {fidelity!r}")


def _concept_screens(prototype_id: str, store: Store) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    """The prototype record + its concept screens (graceful: missing artifact/concept → (None, []))."""
    try:
        proto = _proto.get_prototype(prototype_id, store=store)
    except Exception:
        proto = None
    if not proto:
        return None, []
    screens: list[dict[str, Any]] = []
    try:
        cpath = _proto._prototype_app_dir(proto) / "concept.json"
        if cpath.exists():
            screens = [{"id": s["id"], "title": s.get("title", s["id"])}
                       for s in json.loads(cpath.read_text(encoding="utf-8")).get("screens", [])]
    except Exception:
        pass
    return proto, screens


def brief_usability_session(persona_id, subject, fidelity, project_id=None, store: Store | None = None):
    """GATHER everything needed to run + author ONE usability session: the persona's loaded context
    (SOUL + state + task-keyed memory recall), its capability profile (declared, else derived) with
    the tech-comfort behavioral hint woven into the anti-steering framing — plus explicit `warnings`
    when the requested fidelity exceeds the declared rungs (warn, never block) — the friction
    vocabulary, and the subject's context (prototype how-to-drive when the subject is a
    prototype/flow artifact). The host authors the step timeline; record_usability_session
    validates + persists."""
    store = store or Store()
    subject = _validate_subject(subject)
    _require_fidelity(fidelity)
    persona = _require_persona(store, persona_id)
    profile = capability_profile(persona)  # noqa: F821 (bound) — declared, else derived heuristic
    ctx = prepare_persona_agent_context(  # noqa: F821 (bound)
        persona_id,
        task=f"Use '{subject['label']}' as you really would, thinking aloud at every step",
        recent_events=8, store=store)
    brief = {
        "schema": "usability_session", "persona_id": persona["id"], "project_id": project_id,
        "subject": subject, "fidelity": fidelity,
        "agent_context": ctx.get("agent_context"),
        "capabilities": profile,
        "friction_levels": suggest_friction_levels(),
        "instructions": (
            "Drive the subject like THIS persona and record the DUAL TIMELINE — one entry per step: "
            "{index (0,1,2,…), action:{type,target,detail}, monologue (concurrent think-aloud), "
            "state:{url?, title?, screen, screenshot?}, friction:{level, note}, "
            "verdict:{would_continue, reason}} — then the outcome {completed, dropoff_step, summary, "
            "predicted_behaviors:[{action, step, likelihood (suggest_likelihood_levels or 0..1), "
            "trigger, refs: the evidence ({kind:'evidence'|'session'|'memory', id, quote?})}]}. Anti-steering: only praise "
            "what you actually exercised; honest hesitation, confusion, dead ends and giving up are "
            "first-class outcomes — a persona whose context does not support enthusiasm should stall "
            "or drop off. The session is the deliverable, not a summary of it: record every step you "
            "took, not the highlights."
        ) + capability_context_line(profile) + PRIMITIVES_CONTRACT,  # noqa: F821 (bound)
    }
    gate = capability_fidelity_warnings(                              # noqa: F821 (bound)
        profile, fidelity, " ".join(str(subject.get(k) or "") for k in ("label", "url", "id")))
    if gate:
        brief["warnings"] = gate
    if subject["kind"] == "flow" and subject.get("id") and project_id:
        # An asset-backed defined flow (ticket prototype-walkthrough-dropoff): the brief carries
        # the ordered screens; brief_flow_walkthrough adds the full artifact-first how_to_drive.
        try:
            brief["flow_screens"] = flow_screens_brief(project_id, subject["id"], store=store)  # noqa: F821 (bound)
        except KeyError:
            pass
    if subject["kind"] in ("prototype", "flow") and subject.get("id"):
        proto, screens = _concept_screens(subject["id"], store)
        if proto:
            brief["prototype"] = {"id": proto["id"], "name": proto["name"], "slug": proto["slug"],
                                  "screens": screens}
        if subject["kind"] == "prototype":
            brief["how_to_drive"] = (
                "Run the app (run_prototype), open it headless (proto_open) and act on snapshot refs "
                "(proto_act click/type/select) — observe the REAL state per step, then record from the "
                "SAME session_id so the claimed states verify against the browser session log.")
    elif subject["kind"] == "live_url":
        brief["how_to_drive"] = (
            "Open the live page (proto_open(url=…)) and act on snapshot refs (proto_act) — observe "
            "the REAL state per step, then record from the SAME session_id so the states verify.")
    return brief


def _validate_step(raw: Any, i: int) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError(f"steps[{i}] must be a dict")
    if type(raw.get("index")) is not int or raw["index"] != i:
        raise ValueError(f"step indices must be ordered & contiguous from 0: steps[{i}].index "
                         f"is {raw.get('index')!r}")
    action = raw.get("action") or {}
    typ = action.get("type")
    if typ not in _ACTION_TYPES:
        raise ValueError(f"steps[{i}].action.type must be one of {'|'.join(_ACTION_TYPES)}, got {typ!r}")
    state = raw.get("state") or {}
    screen = str(state.get("screen") or "").strip()
    if not screen:
        raise ValueError(f"steps[{i}].state.screen is required (an artifact ref / snapshot excerpt)")
    friction = raw.get("friction") or {}
    level = _A.resolve_friction(friction.get("level"))
    if level is None:
        raise ValueError(f"steps[{i}].friction.level {friction.get('level')!r} is not on the friction "
                         "scale — suggest_friction_levels() names the valid levels (aliases resolve)")
    verdict = raw.get("verdict") or {}
    if not isinstance(verdict.get("would_continue"), bool):
        raise ValueError(f"steps[{i}].verdict.would_continue must be a bool")
    out_state = {k: v for k, v in (("url", state.get("url")), ("title", state.get("title")),
                                   ("screen", screen), ("screenshot", state.get("screenshot")))
                 if v}
    return {"index": i,
            "action": {"type": typ, "target": str(action.get("target") or ""),
                       "detail": str(action.get("detail") or "")},
            "monologue": str(raw.get("monologue") or ""),
            "state": out_state,
            "friction": {"level": level["label"], "note": str(friction.get("note") or "")},
            "verdict": {"would_continue": verdict["would_continue"],
                        "reason": str(verdict.get("reason") or "")}}


def _validate_outcome(raw: Any, n_steps: int) -> dict[str, Any]:
    if not isinstance(raw, dict) or not isinstance(raw.get("completed"), bool):
        raise ValueError("outcome.completed must be a bool")
    drop = raw.get("dropoff_step")
    if drop is not None and (not isinstance(drop, int) or isinstance(drop, bool)
                             or not 0 <= drop < n_steps):
        raise ValueError(f"outcome.dropoff_step must reference an existing step (0..{n_steps - 1}) or null")
    if raw["completed"] is False and drop is None:
        raise ValueError("outcome.dropoff_step must be set when completed=false (where did the persona drop?)")
    if raw["completed"] is True and drop is not None:
        raise ValueError("outcome.dropoff_step must be null when completed=true (a completed session has no drop-off)")
    preds = []
    for j, p in enumerate(raw.get("predicted_behaviors") or []):
        try:
            pb = _A.validate_predicted_behavior(p)   # canonical likelihood + evidence refs (the primitive)
        except ValueError as exc:
            raise ValueError(f"outcome.predicted_behaviors[{j}]: {exc}") from None
        step = pb.get("step")
        if step is not None and not 0 <= step < n_steps:
            raise ValueError(f"outcome.predicted_behaviors[{j}].step must reference an existing step or null")
        preds.append(pb)
    _A.assign_part_ids(preds, "pb")                  # citable: refs can anchor a specific prediction
    return {"completed": raw["completed"], "dropoff_step": drop,
            "summary": str(raw.get("summary") or ""), "predicted_behaviors": preds}


def _validate_statements(raw_statements, sess_id: str, n_steps: int, store: Store) -> list[dict[str, Any]]:
    """Validate authored statements through the primitive constructors, then check every session ref:
    {kind:'session', id?, anchor:'step:<index>'} must point at an EXISTING step (of this session — a
    missing id is backfilled, the host can't know it pre-record — or of another stored one)."""
    out = []
    for s in raw_statements or []:
        st = _A.validate_statement(s)
        refs = list(st.get("refs") or [])
        if st.get("about"):
            refs.append(st["about"])
        for r in refs:
            if r.get("kind") != "session":
                continue
            if not r.get("id"):
                r["id"] = sess_id
            steps_n = n_steps
            if r["id"] != sess_id:
                other = store.get_usability_session(r["id"])
                if not other:
                    raise ValueError(f"statement ref points at an unknown session: {r['id']}")
                steps_n = len(other.get("steps") or [])
            anchor = r.get("anchor") or ""
            if not anchor:
                continue                                      # whole-session ref
            if not anchor.startswith("step:"):
                raise ValueError(f"session ref anchors must be 'step:<index>', got {anchor!r}")
            try:
                idx = int(anchor.split(":", 1)[1])
            except ValueError:
                raise ValueError(f"session ref anchors must be 'step:<index>', got {anchor!r}") from None
            if not 0 <= idx < steps_n:
                raise ValueError(f"session ref {anchor!r} points at a nonexistent step "
                                 f"(session {r['id']} has steps 0..{steps_n - 1})")
        out.append(st)
    return out


def _require_screenshots(steps: list[dict[str, Any]], sess_id: str) -> None:
    """Referenced screenshot files must exist under the data dir (convention:
    data/sessions/<session_id>/step-<index>.png; relative paths resolve against the session's dir,
    then the sessions dir — the harness writes <browser_session_id>/step-<n>.png relative to it —
    then the data dir). Paths that resolve OUTSIDE the data dir are rejected — the trace may only
    claim files the store actually owns."""
    from ..config import partition_dir
    base = sessions_dir() / sess_id
    data_root = partition_dir().resolve()
    missing = []
    for s in steps:
        shot = (s.get("state") or {}).get("screenshot")
        if not shot:
            continue
        p = Path(shot)
        candidates = [p] if p.is_absolute() else [base / p, sessions_dir() / p, partition_dir() / p]
        contained = [c for c in candidates if c.resolve().is_relative_to(data_root)]
        if not contained:
            raise ValueError(f"screenshot path escapes the data dir ({data_root}): {shot!r} "
                             "(convention: data/sessions/<session_id>/step-<index>.png)")
        if not any(c.exists() for c in contained):
            missing.append(shot)
    if missing:
        raise ValueError(f"screenshot files not found under {base} "
                         f"(convention: data/sessions/<session_id>/step-<index>.png): {missing}")


def _verify_states_against_log(steps: list[dict[str, Any]], log: list[dict[str, Any]]) -> None:
    """Every claimed per-step state must be present in the browser session log (the
    record_prototype_session groundedness contract, per step instead of per reaction)."""
    seen_refs: set[str] = set()
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()
    seen_text = ""
    for entry in log:
        if entry.get("kind") == "snapshot":
            seen_refs.update(entry.get("refs", []))
            seen_text += " " + (entry.get("text") or "")
            for k, acc in (("url", seen_urls), ("title", seen_titles)):
                if entry.get(k):
                    acc.add(entry[k])
    low = seen_text.lower()
    unmatched = []
    for s in steps:
        st = s.get("state") or {}
        screen = st.get("screen", "")
        if screen and screen not in seen_refs and screen.lower() not in low:
            unmatched.append(f"step {s['index']}: screen {screen!r}")
        if st.get("url") and st["url"] not in seen_urls:
            unmatched.append(f"step {s['index']}: url {st['url']!r}")
        if st.get("title") and st["title"] not in seen_titles:
            unmatched.append(f"step {s['index']}: title {st['title']!r}")
    if unmatched:
        raise ValueError("usability-session groundedness: claimed states not present in the browser "
                         f"session log: {unmatched}")


def record_usability_session(persona_id, subject, fidelity, date_value, steps, outcome,
                             statements=None, project_id=None, session_id=None,
                             key: str | None = None, store: Store | None = None,
                             dispatch_token: str | None = None):
    """Persist a host-authored usability session — the durable, REPLAYABLE trace. Validates: step
    indices ordered & contiguous from 0, each step's action type + state.screen + friction level
    (data-driven vocabulary, aliases resolve) + verdict shape, the outcome shape (dropoff_step must
    reference an existing step; required when completed=false), session refs in statements (must
    point at existing steps), and referenced screenshot files. When fidelity is prototype/live and a
    browser `session_id` is passed, the claimed per-step states are verified against the harness
    session log (unmatched claims are rejected; a missing log records with an UNVERIFIED_SESSION
    warning). The persona's capability profile in effect is stamped onto the stored session as
    `capabilities_snapshot` so traces stay interpretable after the persona evolves. Pass a stable
    `key` for a deterministic id (idempotent upsert → resumable runs)."""
    store = store or Store()
    # Historical usability-session rows were allowed to carry an arbitrary project label even
    # when no research-project record existed. Keep that read/filter compatibility, but never
    # present such a row as governed: only a real project can enter the dispatch validator and an
    # unbound reference is explicitly stamped as outside-run. Conversely, a supplied token always
    # goes through the validator (including when project_id is empty/unknown), so it cannot be
    # laundered into this compatibility path.
    known_project = bool(project_id and store.get_research_project(str(project_id)))
    if dispatch_token or known_project:
        dispatch_ctx = prepare_dispatch_write(  # noqa: F821 (bound)
            str(project_id or ""), dispatch_token, key, "session", store,
            allowed_buckets={"act", "verify"})
    else:
        dispatch_ctx = {
            "state": "outside_run",
            "project_id": str(project_id or ""),
            "output_kind": "session",
            "operation_id": str(key or ""),
            "key": str(key or ""),
            **({"project_reference": "unbound"} if project_id else {}),
        }
    effective_key = str(dispatch_ctx.get("primitive_key") or key or "") or None
    subject = _validate_subject(subject)
    _require_fidelity(fidelity)
    if not isinstance(steps, list) or not steps:
        raise ValueError("steps must be a non-empty list — the session is the deliverable, record every step")
    norm_steps = [_validate_step(s, i) for i, s in enumerate(steps)]
    norm_outcome = _validate_outcome(outcome, len(norm_steps))
    now = utc_now_iso()
    sess_id = (stable_id("usession", effective_key) if effective_key
               else stable_id("usession", persona_id, _subject_key(subject), now))
    norm_statements = _validate_statements(statements, sess_id, len(norm_steps), store)
    _require_screenshots(norm_steps, sess_id)
    grounded = None
    warnings: list[str] = []
    if fidelity in ("prototype", "live") and session_id:
        log = _browser.session_log(session_id)
        if log:
            _verify_states_against_log(norm_steps, log)
            grounded = True
        else:
            grounded = False
            msg = ("UNVERIFIED_SESSION: no observed-state log for this session_id, so the claimed "
                   "states are NOT verified against real usage.")
            if _browser.available():
                msg += (" Playwright IS available here — drive the subject (proto_open/proto_act/"
                        "proto_read) and record from the SAME session_id; the log is retained across "
                        "proto_close, so a real drive will verify.")
            warnings.append(msg)
    sess = UsabilitySession(
        id=sess_id, project_id=project_id or "", persona_id=persona_id, date=date_value,
        subject=subject, fidelity=fidelity, steps=norm_steps, outcome=norm_outcome,
        created_at=now, statements=norm_statements).to_dict()
    if subject.get("kind") == "prototype":
        proto = store.get_prototype(str(subject.get("id") or "")) or {}
        # Snapshot at record time; an absent stamp on older rows means unknown, never "current".
        sess["prototype_version"] = str(proto.get("version") or "unknown")
    persona = store.get_persona(persona_id)
    if persona:
        # The capability profile IN EFFECT at record time — sessions stay interpretable after
        # the persona evolves. (Sessions of unknown/ad-hoc persona ids record without one.)
        sess["capabilities_snapshot"] = capability_profile(persona)   # noqa: F821 (bound)
    if session_id:
        sess["session_id"] = session_id          # the browser session the trace was verified against
    if grounded is not None:
        sess["grounded_verified"] = grounded
    if project_id:
        sess["dispatch_provenance"] = {
            "state": dispatch_ctx.get("state", "outside_run"),
            **({"project_reference": dispatch_ctx["project_reference"]}
               if dispatch_ctx.get("project_reference") else {}),
            **({"dispatch_token": dispatch_ctx["dispatch_token"],
                "run_id": dispatch_ctx["run_id"], "task_id": dispatch_ctx["task_id"],
                "operation_id": dispatch_ctx["operation_id"]}
               if dispatch_ctx.get("dispatch_token") else {}),
        }
    store.insert_usability_session(sess)
    out: dict[str, Any] = {"usability_session": sess}
    if project_id:
        out["dispatch"] = bind_dispatch_output(  # noqa: F821 (bound)
            dispatch_ctx, {"kind": "session", "id": sess_id},
            "recorded replayable usability session", store)
    if grounded is not None:
        out["grounded_verified"] = grounded
    if warnings:
        out["warnings"] = warnings
    return out


def get_usability_session(session_id, store: Store | None = None):
    """One recorded usability session by id — the full replayable trace."""
    store = store or Store()
    sess = store.get_usability_session(session_id)
    if not sess:
        raise KeyError(f"Unknown usability session: {session_id}")
    return sess


def list_usability_sessions(project_id=None, persona_id=None, subject=None, store: Store | None = None):
    """List recorded usability sessions, optionally filtered by project, persona and/or subject
    (`subject` is {kind?, id?|url?} or the bare id/url string)."""
    store = store or Store()
    kind = key = None
    if isinstance(subject, dict):
        kind = subject.get("kind")
        key = subject.get("id") or subject.get("url")
    elif subject:
        key = str(subject)
    return store.list_usability_sessions(project_id, persona_id, kind, key)


def get_session_funnel(subject_kind, subject_id_or_url, store: Store | None = None):
    """Aggregate ALL sessions of one subject into a step-indexed funnel: per step the number of
    sessions that reached it, continued past it, or dropped there (outcome.dropoff_step), with the
    drop reasons (the dropping step's verdict.reason, else the outcome summary) — the cross-session
    read the replayable traces exist for."""
    store = store or Store()
    sessions = store.list_usability_sessions(subject_kind=subject_kind,
                                             subject_key=str(subject_id_or_url))
    rows = []
    for i in range(max((len(s.get("steps") or []) for s in sessions), default=0)):
        reached = [s for s in sessions if len(s.get("steps") or []) > i]
        dropped = [s for s in reached if (s.get("outcome") or {}).get("dropoff_step") == i
                   and not (s.get("outcome") or {}).get("completed")]
        reasons = []
        for s in dropped:
            step = (s.get("steps") or [])[i]
            reason = ((step.get("verdict") or {}).get("reason")
                      or (s.get("outcome") or {}).get("summary") or "")
            if reason:
                reasons.append(reason)
        rows.append({"step": i, "entered": len(reached),
                     "continued": len(reached) - len(dropped), "dropped": len(dropped),
                     "drop_reasons": reasons})
    return {"subject": {"kind": subject_kind, "key": str(subject_id_or_url)},
            "sessions": len(sessions),
            "completed": sum(1 for s in sessions if (s.get("outcome") or {}).get("completed")),
            "rows": rows}
