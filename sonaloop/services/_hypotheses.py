"""Hypotheses — falsifiable predictions scored against reality.

A Hypothesis stamps "we predict X on metric M" BEFORE reality answers and scores it when it does —
the only way to show the simulations are PREDICTIVE rather than merely plausible. House triplet:
brief_hypothesis GATHERS what is worth betting on (contested council findings, predicted behaviors
from usability sessions, open questions); the host authors the falsifiable statement + checkable
prediction; record_hypothesis VALIDATES (metric + expected_value OR expected_direction required —
a bet nothing can refute is rejected) + persists with status=open. record_hypothesis_result
attaches the real-world observation (the source Ref must resolve: a survey's imported responses,
attached evidence, or a free observation carried as text) and DERIVES the status
(validated|refuted|inconclusive) by comparing observed against predicted — the host argues the
verdict in `note`, but BOTH raw values are kept so the verdict is auditable. eval_scorecard
aggregates the hit-rate across resolved hypotheses (per project and global) and writes the
sim-vs-reality calibration record into eval_reports — that table's first writer.
Cross-module function references are bound at import time by services/__init__.py."""

from __future__ import annotations

from typing import Any

from .. import artifacts as _A
from ..config import utc_now_iso
from ..models import Hypothesis
from ..storage import Store
from ._common import _require_research_project, stable_id


_HYPOTHESIS_STATUSES = ("open", "validated", "refuted", "inconclusive", "dropped")
_RESOLVED_STATUSES = ("validated", "refuted", "inconclusive")
_DECISIVE_STATUSES = ("validated", "refuted")

# Direction tokens (case/whitespace-insensitive) → the sign a numeric observation is scored
# against. Stored predictions normalize onto the two canonical terms (increase|decrease).
_DIRECTIONS = {"increase": 1, "up": 1, "rise": 1, "grow": 1, "higher": 1, "more": 1,
               "decrease": -1, "down": -1, "fall": -1, "shrink": -1, "lower": -1, "less": -1,
               "drop": -1}


def _require_hypothesis(store: Store, hypothesis_id: str) -> dict[str, Any]:
    hyp = store.get_hypothesis(hypothesis_id)
    if not hyp:
        raise KeyError(f"Unknown hypothesis: {hypothesis_id}")
    return hyp


def _num(v: Any) -> float | None:
    """Read a value as a number when it is one ('+12%', '38', 40) — None when it isn't."""
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).strip().replace("%", ""))
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------------------------- validation

def _validate_prediction(raw: Any) -> dict[str, Any]:
    """A prediction must be CHECKABLE — that is the whole artifact. Required: metric + exactly one
    of expected_value / expected_direction. Optional: tolerance (>= 0; for a value prediction the
    accepted |observed - expected| band, for a direction prediction the |delta| dead zone that
    counts as noise) and confidence (0..1)."""
    if not isinstance(raw, dict):
        raise ValueError("prediction must be a dict {metric, expected_value | expected_direction, "
                         "confidence?, tolerance?}")
    metric = str(raw.get("metric") or "").strip()
    if not metric:
        raise ValueError("prediction.metric is required — without a metric the hypothesis is "
                         "unfalsifiable")
    has_value = raw.get("expected_value") not in (None, "")
    direction = str(raw.get("expected_direction") or "").strip().lower()
    if not has_value and not direction:
        raise ValueError("prediction needs expected_value OR expected_direction — a bet nothing "
                         "can refute is unfalsifiable")
    if has_value and direction:
        raise ValueError("prediction takes expected_value OR expected_direction, not both — "
                         "pick the sharper claim")
    out: dict[str, Any] = {"metric": metric}
    if has_value:
        out["expected_value"] = raw["expected_value"]
    else:
        if direction not in _DIRECTIONS:
            raise ValueError(f"prediction.expected_direction {raw.get('expected_direction')!r} is "
                             f"not scoreable — use one of {sorted(set(_DIRECTIONS))}")
        out["expected_direction"] = "increase" if _DIRECTIONS[direction] > 0 else "decrease"
    tol = raw.get("tolerance")
    if tol is not None:
        tnum = _num(tol)
        if tnum is None or tnum < 0:
            raise ValueError(f"prediction.tolerance must be a number >= 0, got {tol!r}")
        out["tolerance"] = tnum
    conf = raw.get("confidence")
    if conf is not None:
        cnum = _num(conf)
        if cnum is None or not 0 <= cnum <= 1:
            raise ValueError(f"prediction.confidence must be within 0..1, got {conf!r}")
        out["confidence"] = cnum
    return out


def _derive_status(prediction: dict[str, Any], observed: Any) -> str:
    """The MECHANICAL verdict — derived at result-recording time by comparing observed against
    predicted (the host argues it in the result note; both raw values stay on the record).
    Value predictions: a numeric expectation scores numerically within tolerance (validated inside,
    refuted outside; an observation that can't be read as a number is inconclusive); a non-numeric
    expectation compares case-insensitively. Direction predictions: a numeric observation scores by
    sign (|delta| within tolerance is noise → inconclusive); a direction token compares directly;
    anything unreadable is inconclusive."""
    tol = float(prediction.get("tolerance") or 0)
    if "expected_value" in prediction:
        exp = prediction["expected_value"]
        en, on = _num(exp), _num(observed)
        if en is not None:
            if on is None:
                return "inconclusive"
            return "validated" if abs(on - en) <= tol else "refuted"
        return ("validated"
                if str(observed).strip().lower() == str(exp).strip().lower() else "refuted")
    want = _DIRECTIONS[prediction["expected_direction"]]
    on = _num(observed)
    if on is not None:
        if abs(on) <= tol:
            return "inconclusive"                      # no real movement — the bet didn't resolve
        return "validated" if (on > 0) == (want > 0) else "refuted"
    got = _DIRECTIONS.get(str(observed).strip().lower())
    if got is None:
        return "inconclusive"
    return "validated" if got == want else "refuted"


# --------------------------------------------------------------------------- brief → record

def brief_hypothesis(project_id: str, store: Store | None = None) -> dict[str, Any]:
    """GATHER what is worth betting on: the project's CONTESTED findings (councils whose statements
    span support AND opposition — exactly where reality's answer is informative), the PREDICTED
    behaviors recorded in usability sessions (each with a ref into its session, ready to promote
    into a hypothesis without reshaping), and the OPEN questions. The host authors the falsifiable
    statement + checkable prediction; record_hypothesis validates + persists."""
    store = store or Store()
    project = _require_research_project(store, project_id)
    open_qs = [o for o in store.list_open_questions(project["id"]) if o.get("status") == "open"]
    predicted = []
    for sess in store.list_usability_sessions(project_id=project["id"]):
        for p in (sess.get("outcome") or {}).get("predicted_behaviors") or []:
            predicted.append({**p, "persona_id": sess.get("persona_id", ""),
                              "subject": (sess.get("subject") or {}).get("label", ""),
                              "ref": {"kind": "session", "id": sess["id"], "role": "derived_from"}})
    return {
        "schema": "hypothesis", "project_id": project["id"], "goal": project.get("goal", ""),
        "open_questions": open_qs,
        "contested_findings": contested_findings(project["id"], store),  # noqa: F821 (bound)
        "predicted_behaviors": predicted,
        # The segment view: the same predictions rolled up by (action, step, subject) across the
        # whole project incl. councils/syntheses — a recurring predicted behavior with a high mean
        # likelihood is the strongest bet candidate (ticket behavioral-prediction-output).
        "predicted_behaviors_aggregate": aggregate_predictions(project["id"], store=store)["groups"][:12],
        "instructions": (
            "Author the hypothesis YOURSELF — the server never writes text. Turn a contested "
            "finding, a predicted behavior or an open question above into ONE falsifiable "
            "statement with a checkable prediction: {metric, expected_value (+tolerance?) OR "
            "expected_direction (increase|decrease), confidence?}. record_hypothesis REJECTS "
            "unfalsifiable predictions (no metric, no expected value/direction) and unresolvable "
            "derived_from refs ({kind: open_question|council|synthesis|session, id, anchor?, "
            "role}). Stamp the bet BEFORE reality answers; when it does, attach the observation "
            "via record_hypothesis_result — the status (validated|refuted|inconclusive) is "
            "DERIVED from observed vs predicted, your argument goes in `note`."),
    }


def record_hypothesis(project_id: str, text: str, prediction: dict, derived_from: list | None = None,
                      key: str | None = None, store: Store | None = None) -> dict[str, Any]:
    """Persist a host-authored hypothesis with status=open — the bet stamped BEFORE reality
    answers. Validates falsifiability (prediction.metric + exactly one of expected_value /
    expected_direction; tolerance >= 0; confidence within 0..1) and that every derived_from Ref
    resolves (open questions of this project; councils/syntheses/sessions live via resolve_ref,
    anchors included). A stable `key` gives a deterministic id (idempotent upsert → resumable
    runs); a RESOLVED hypothesis can NOT be re-authored — the record is the audit trail."""
    store = store or Store()
    project = _require_research_project(store, project_id)
    text = str(text or "").strip()
    if not text:
        raise ValueError("text is required (the falsifiable statement)")
    pred = _validate_prediction(prediction)
    refs = _validate_derived_from(derived_from, project["id"], store)  # noqa: F821 (bound)
    now = utc_now_iso()
    # The key hash is project-scoped — a key-only hash would let one project's record_hypothesis
    # silently re-author and adopt another project's open bet on key collision.
    hid = stable_id("hyp", project["id"], key) if key else stable_id("hyp", project["id"], text, now)
    existing = store.get_hypothesis(hid)
    if existing and existing.get("status") != "open":
        raise ValueError(f"hypothesis {hid} is already {existing.get('status')} — a scored bet "
                         "cannot be re-authored; record a new hypothesis")
    rec = Hypothesis(id=hid, project_id=project["id"], text=text, prediction=pred,
                     derived_from=refs, status="open", result=None,
                     created_at=(existing or {}).get("created_at", now), updated_at=now).to_dict()
    store.upsert_hypothesis(rec)
    out = {"hypothesis": rec, "url": web_url(f"/hypotheses/{hid}"),  # noqa: F821 (bound)
           "project_url": web_url(f"/jobs/{project['id']}")}  # noqa: F821 (bound)
    # Governance parity with record_council: a hypothesis stamped while the plan has ready work
    # and no active run is fine, but say so — remote hosts demonstrably record past the loop.
    try:
        from ..plan_assess import project_run_state
        rs = project_run_state(project["id"], store=store)
        if rs and rs.get("state") == "stalled":
            out["warnings"] = [
                "recorded OUTSIDE the governed run loop — the project's plan has ready work and "
                f"no active run ({rs.get('note', '')}); drive via start_run → run_step → "
                "checkpoint_step so plan gates and assess_project stay honest"]
    except Exception:
        pass
    return out


def get_hypothesis(hypothesis_id: str, store: Store | None = None) -> dict[str, Any]:
    """One hypothesis by id — the bet, its prediction, and (once resolved) the recorded result."""
    store = store or Store()
    return _require_hypothesis(store, hypothesis_id)


def list_hypotheses(project_id: str | None = None, status: str | None = None,
                    store: Store | None = None) -> list[dict[str, Any]]:
    """List hypotheses (optionally per project and/or status)."""
    store = store or Store()
    if status and status not in _HYPOTHESIS_STATUSES:
        raise ValueError(f"status must be one of {'|'.join(_HYPOTHESIS_STATUSES)}, got {status!r}")
    return store.list_hypotheses(project_id, status)


# --------------------------------------------------------------------------- result (reality answers)

def record_hypothesis_result(hypothesis_id: str, observed_value: Any, source: dict,
                             note: str = "", store: Store | None = None) -> dict[str, Any]:
    """Attach the REAL-WORLD observation and flip the status. The source Ref must RESOLVE — a
    survey's imported responses ({kind:'survey', id}), attached evidence ({kind:'evidence', id}),
    a council/synthesis/session, or a free observation carried as text ({kind:'external', text}).
    The status (validated|refuted|inconclusive) is DERIVED by comparing observed against predicted;
    both raw values stay on the record and the host's argument goes in `note` — the verdict is
    auditable, never asserted."""
    store = store or Store()
    hyp = _require_hypothesis(store, hypothesis_id)
    if hyp.get("status") == "dropped":
        raise ValueError("this hypothesis was dropped — a dropped bet is not scored")
    if hyp.get("status") != "open":
        raise ValueError(f"this hypothesis is already {hyp['status']} — a scored verdict is the "
                         "audit trail and cannot be rewritten; record a new hypothesis to re-test")
    if observed_value in (None, ""):
        raise ValueError("observed_value is required — a result without an observation scores nothing")
    if not isinstance(source, dict):
        raise ValueError("source must be a Ref dict {kind, id?, anchor?, text?} — where did "
                         "reality answer?")
    src = _A.validate_ref(source)
    src.setdefault("role", "observed_in")
    # Record kinds must point at an actual record — an id-less ref resolves on bare text, which
    # would let free prose masquerade as e.g. a survey-grounded observation.
    if src.get("kind") != "external" and not src.get("id"):
        raise ValueError(f"source kind {src.get('kind')!r} needs an id (the record reality answered "
                         "in) — only {kind:'external', text} may carry a free observation")
    if not _A.resolve_ref(src, store).get("exists"):
        anchor = f"#{src['anchor']}" if src.get("anchor") else ""
        raise ValueError(f"source does not resolve: {src.get('kind')}:{src.get('id') or ''}{anchor}"
                         " — point at a survey / evidence / session record, or carry the free "
                         "observation as text")
    status = _derive_status(hyp["prediction"], observed_value)
    now = utc_now_iso()
    hyp["result"] = {"observed_value": observed_value, "source": src,
                     "note": str(note or ""), "recorded_at": now}
    hyp["status"] = status
    hyp["updated_at"] = now
    store.upsert_hypothesis(hyp)
    return {"hypothesis": hyp, "status": status}


def drop_hypothesis(hypothesis_id: str, note: str = "", store: Store | None = None) -> dict[str, Any]:
    """Retire an OPEN bet without scoring it (the question became moot, the metric unmeasurable).
    Dropped bets stay on the record but are excluded from the scorecard — only reality may
    validate or refute; a resolved verdict cannot be dropped after the fact."""
    store = store or Store()
    hyp = _require_hypothesis(store, hypothesis_id)
    if hyp.get("status") != "open":
        raise ValueError(f"only an open bet can be dropped — this hypothesis is "
                         f"{hyp.get('status')}")
    hyp["status"] = "dropped"
    hyp["drop_note"] = str(note or "")
    hyp["updated_at"] = utc_now_iso()
    store.upsert_hypothesis(hyp)
    return {"hypothesis": hyp}


# --------------------------------------------------------------------------- scorecard (calibration)

def _scorecard_bucket(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts = {s: 0 for s in _HYPOTHESIS_STATUSES}
    for hx in rows:
        st = hx.get("status", "open")
        counts[st] = counts.get(st, 0) + 1
    resolved = sum(counts[s] for s in _RESOLVED_STATUSES)
    decisive = sum(counts[s] for s in _DECISIVE_STATUSES)
    return {"counts": counts, "n": len(rows), "resolved": resolved, "decisive": decisive,
            "hit_rate": (counts["validated"] / decisive) if decisive else None}


def eval_scorecard(project_id: str | None = None, store: Store | None = None) -> dict[str, Any]:
    """Aggregate the hit-rate across RESOLVED hypotheses (per project, or global with a per-project
    breakdown) and write the sim-vs-reality calibration record into eval_reports. Open and dropped
    bets are EXCLUDED; the hit-rate is validated / (validated + refuted) — an inconclusive
    resolution counts as resolved but not decisive. green = at least one decisive resolution and a
    hit-rate >= 0.5 (more predictions confirmed than refuted)."""
    store = store or Store()
    if project_id:
        _require_research_project(store, project_id)
    hyps = store.list_hypotheses(project_id)
    total = _scorecard_bucket(hyps)
    by_project: dict[str, Any] = {}
    if not project_id:
        grouped: dict[str, list] = {}
        for hx in hyps:
            grouped.setdefault(hx.get("project_id", ""), []).append(hx)
        by_project = {pid: _scorecard_bucket(rows) for pid, rows in grouped.items()}
    now = utc_now_iso()
    report = {
        "id": stable_id("evalrep", "hypothesis_scorecard", project_id or "global", now),
        "kind": "hypothesis_scorecard",
        "persona_id": None, "period_start": None, "period_end": None,
        "scope": project_id or "global",
        "green": bool(total["decisive"]) and total["hit_rate"] >= 0.5,
        **total,
        "by_project": by_project,
        "resolved_hypotheses": [{"id": hx["id"], "status": hx["status"],
                                 "metric": (hx.get("prediction") or {}).get("metric", "")}
                                for hx in hyps if hx.get("status") in _RESOLVED_STATUSES],
        "created_at": now,
    }
    store.insert_eval_report(report)
    store.commit()
    return {"scorecard": report}
