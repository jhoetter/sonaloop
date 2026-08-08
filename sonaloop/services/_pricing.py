"""Price-ladder Format support for the `pricing` Job (taxonomy `jobs[pricing].protocol`,
"Willingness-to-pay ladder"): a fixed ascending ladder of price points, every persona reacting to
EVERY point with one of four van-Westendorp-style anchor bands — too_cheap (suspiciously cheap),
bargain, getting_expensive, too_expensive — grounded in their profile budget/constraints.

Host-authors-all-text contract (README): the host (Claude) authors each persona's band choice +
grounding quote and the prose pricing story; this module is the SCAFFOLD — it assembles the ladder
brief, VALIDATES the structured responses (closed band vocabulary, every price resolves to a rung)
and does the DETERMINISTIC aggregation server-side: per price point the band counts and acceptance
share (bargain + getting_expensive), per segment the acceptable-price range (rungs where a majority
accepts) and the CLIFF point (the largest acceptance drop between adjacent rungs). No server-side
text-LLM call ever happens here.

A recorded price ladder IS a CouncilSession (same pattern as head_to_head: council persistence, the
project graph and the inspector for free), carrying a `price_ladder` block — the ladder, the raw
per-persona/per-rung responses (persona, price point, band, quote — queryable for analytics) and the
derived result — plus a `finding` of kind `price_ladder`. Tier comparisons deliberately REUSE the
head_to_head Format with price as variant metadata (protocol step `tier_head_to_head`) instead of
growing a parallel comparison path here.
"""
from __future__ import annotations

import re
from typing import Any

from ..config import utc_now_iso, ensure_content_language, language_instruction
from ..storage import Store
from .. import artifacts as _artifacts
from ..research_integrity import stamp_derived_finding

from ._common import *  # noqa: F401,F403  (stable_id, _require_research_project, list_personas, …)


# The CLOSED anchor-band vocabulary (van Westendorp's four questions, as reaction bands).
PRICE_BANDS = ("too_cheap", "bargain", "getting_expensive", "too_expensive")
# A rung is "acceptable" to a persona when their band is one of these two middle anchors.
ACCEPTABLE_BANDS = frozenset({"bargain", "getting_expensive"})

_NUM = re.compile(r"-?\d+(?:[.,]\d+)?")


def _amount(v: Any) -> float | None:
    """Read a price amount from a number or a string ('$29/mo', '49,90 €') — None when unreadable."""
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    m = _NUM.search(str(v))
    return float(m.group().replace(",", ".")) if m else None


def _normalize_price_points(price_points: list[Any]) -> list[dict[str, Any]]:
    """Turn the host's ladder into uniform ascending rungs [{label, amount}]. Each entry is a number,
    a price string ('$29/mo' — the label survives verbatim, the amount is parsed out), or an explicit
    {label?, amount}. At least two distinct rungs; ascending by amount; labels unique."""
    out: list[dict[str, Any]] = []
    for raw in price_points or []:
        if isinstance(raw, dict):
            amount = _amount(raw.get("amount", raw.get("price")))
            label = str(raw.get("label") or "").strip()
        else:
            amount = _amount(raw)
            label = str(raw).strip()
        if amount is None:
            raise ValueError(f"price point {raw!r} has no readable amount — pass a number, a price "
                             "string ('$29/mo') or {label, amount}")
        out.append({"label": label or f"{amount:g}", "amount": amount})
    out.sort(key=lambda p: p["amount"])
    if len(out) < 2:
        raise ValueError(f"a price ladder needs at least two price points (got {len(out)})")
    labels = [p["label"] for p in out]
    amounts = [p["amount"] for p in out]
    if len(set(labels)) != len(labels) or len(set(amounts)) != len(amounts):
        raise ValueError(f"price points must be distinct (labels {labels}, amounts {amounts})")
    return out


def _render_ladder_context(points: list[dict[str, Any]]) -> str:
    """The ladder as ONE block folded into each persona's context: react to EVERY rung with exactly
    one anchor band, grounded in YOUR budget/constraints (protocol steps anchor_band_reactions +
    grounded_in_profile)."""
    head = ("PRICE LADDER — react to EVERY price point below with exactly ONE band: "
            "too_cheap (suspiciously cheap — what's wrong with it?), bargain, getting_expensive "
            "(I'd think twice), or too_expensive (out of the question). Ground each reaction in "
            "YOUR budget, authority and constraints — quote them, don't invent a wallet.")
    rungs = [f"- PRICE {p['label']}" + (f" (={p['amount']:g})" if p["label"] != f"{p['amount']:g}" else "")
             for p in points]
    return "\n".join([head, *rungs])


def brief_price_ladder(project_id: str, prompt: str, price_points: list[Any],
                       persona_ids: list[str] | None = None, filters: dict[str, Any] | None = None,
                       count: int = 4, context: str | None = None,
                       store: Store | None = None) -> dict[str, Any]:
    """Gather everything to run a host-authored PRICE LADDER (pricing Job protocol) over a research
    project's personas. `price_points` is the fixed ascending ladder (numbers, price strings, or
    {label, amount}). Without persona_ids: returns candidate personas — pick a panel that spans
    willingness-to-pay and includes the budget holder (the Job's coverage axes). With persona_ids:
    returns each participant's loaded context with the ladder folded in, to author one banded
    reaction per persona per rung, then call record_price_ladder."""
    store = store or Store()
    project = _require_research_project(store, project_id)
    points = _normalize_price_points(price_points)
    ladder_context = _render_ladder_context(points)
    language = ensure_content_language(" ".join(filter(None, [prompt, context])))

    if not persona_ids:
        personas = list_personas(filters, store)
        candidates = [
            {"persona_id": p["id"], "display_name": p["display_name"],
             "source_description": p["source_description"], "segment": p.get("segment", {}),
             "role": p.get("role", {}), "goals": p.get("goals", []), "pain_points": p.get("pain_points", [])}
            for p in personas
        ]
        return {
            "schema": "price_ladder_selection", "language": language, "project_id": project["id"],
            "prompt": prompt, "price_points": points,
            "count": min(max(2, count), len(candidates)) if candidates else 0,
            "candidate_personas": candidates,
            "instructions": (
                "Pick a panel that SPANS willingness-to-pay (low to high) and includes the budget "
                "holder, so the acceptable range and the cliff can be split by segment. Then call "
                f"brief_price_ladder again with persona_ids=[...]. {language_instruction(language)}"
                if candidates else "No personas exist yet. Create some first."),
        }

    context_block = "\n\n".join(filter(None, [context or "", ladder_context]))
    participants = []
    for pid in persona_ids:
        p = store.get_persona(pid)
        if not p:
            continue
        ctx = prepare_persona_agent_context(
            p["id"], f"Price-ladder prompt: {prompt}\n{context_block}", store=store)
        participants.append({
            "persona_id": p["id"], "display_name": p["display_name"],
            "segment": p.get("segment", {}), "soul_path": ctx["soul_path"],
            "agent_context": f"{ctx['agent_context']}\n\n=== PRICE LADDER ===\n{ladder_context}",
        })
    return {
        "schema": "price_ladder", "language": language, "project_id": project["id"], "prompt": prompt,
        "external_context": context, "price_points": points, "bands": list(PRICE_BANDS),
        "participants": participants, "ladder_context": ladder_context,
        "instructions": (
            "THE LADDER IS IN THE ROOM — each participant's agent_context ends with the rungs. For "
            "EACH persona author ONE reaction PER price point: {persona_id, price (a rung label or "
            "amount), band (too_cheap|bargain|getting_expensive|too_expensive), quote (their words, "
            "grounded in THEIR budget/constraints from agent_context — quote the profile, don't "
            "invent)}. Optionally add per-rung `statements` (about={kind:'prompt', id:'price:<label>'}). "
            "Then call record_price_ladder(project_id, prompt, price_points, responses=[...], "
            "exec_summary, summary). The server validates the closed band vocabulary and derives the "
            "acceptable-price range + cliff per segment; you author the pricing story. "
            f"{language_instruction(language)}"),
    }


def _bucket_analysis(points: list[dict[str, Any]],
                     rows: list[dict[str, Any]]) -> dict[str, Any]:
    """The deterministic ladder math for ONE bucket (overall, or one segment): per rung the band
    counts + acceptance share (bargain/getting_expensive over the rung's respondents), the
    acceptable RANGE (lowest→highest rung where acceptance >= 0.5) and the CLIFF (the adjacent
    ascending pair with the largest positive acceptance drop). Rungs nobody answered carry
    acceptance None and stay out of range/cliff math."""
    per_point = []
    for p in points:
        hits = [r for r in rows if r["price"] == p["label"]]
        counts = {b: sum(1 for r in hits if r["band"] == b) for b in PRICE_BANDS}
        acceptance = (round(sum(counts[b] for b in ACCEPTABLE_BANDS) / len(hits), 3)
                      if hits else None)
        per_point.append({"label": p["label"], "amount": p["amount"], "respondents": len(hits),
                          "counts": counts, "acceptance": acceptance})
    accepted = [pp for pp in per_point if pp["acceptance"] is not None and pp["acceptance"] >= 0.5]
    acceptable_range = ({"low": accepted[0]["label"], "low_amount": accepted[0]["amount"],
                         "high": accepted[-1]["label"], "high_amount": accepted[-1]["amount"]}
                        if accepted else None)
    cliff = None
    answered = [pp for pp in per_point if pp["acceptance"] is not None]
    for a, b in zip(answered, answered[1:]):
        drop = round(a["acceptance"] - b["acceptance"], 3)
        if drop > 0 and (cliff is None or drop > cliff["drop"]):
            cliff = {"from": a["label"], "to": b["label"], "from_amount": a["amount"],
                     "to_amount": b["amount"], "drop": drop}
    return {"respondents": len({r["persona_id"] for r in rows}), "points": per_point,
            "acceptable_range": acceptable_range, "cliff": cliff}


def _derive_ladder(points: list[dict[str, Any]], responses: list[dict[str, Any]],
                   personas: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """The full deterministic price-ladder result: the overall bucket plus one bucket per persona
    segment (`segment.customer_type`, the same axis head_to_head splits on)."""
    seg_rows: dict[str, list[dict[str, Any]]] = {}
    for r in responses:
        p = personas.get(r["persona_id"])
        seg = ((p or {}).get("segment") or {}).get("customer_type") or "unspecified"
        seg_rows.setdefault(seg, []).append(r)
    return {
        "bands": list(PRICE_BANDS),
        "overall": _bucket_analysis(points, responses),
        "segments": [{"segment": seg, **_bucket_analysis(points, rows)}
                     for seg, rows in sorted(seg_rows.items())],
    }


def record_price_ladder(project_id: str, prompt: str, price_points: list[Any],
                        responses: list[dict[str, Any]] | None = None,
                        persona_ids: list[str] | None = None, statements: list | None = None,
                        summary: str = "", exec_summary: str = "", selection_reason: str = "",
                        findings: list | None = None, key: str | None = None,
                        created_at: str | None = None, store: Store | None = None,
                        claims: list[dict[str, Any]] | None = None,
                        dispatch_token: str | None = None) -> dict[str, Any]:
    """Persist a host-authored PRICE LADDER as a CouncilSession carrying a `price_ladder` block
    (the pricing Job's structured willingness-to-pay data). `responses` is the structured payload —
    one row per persona per rung: {persona_id, price (rung label or amount), band (closed
    vocabulary), quote (grounding, the persona's words)}. The SERVER validates every row (an
    off-vocabulary band or an off-ladder price is rejected, never coerced) and derives the
    deterministic result: acceptance per rung, acceptable-price range + cliff point, overall and
    per segment. Pass a stable `key` for a deterministic id (idempotent upsert)."""
    store = store or Store()
    project = _require_research_project(store, project_id)
    points = _normalize_price_points(price_points)
    by_label = {p["label"]: p for p in points}
    by_amount = {p["amount"]: p for p in points}

    rows: list[dict[str, Any]] = []
    for raw in (responses or []):
        pid = str(raw.get("persona_id") or "").strip()
        if not pid:
            continue
        band = str(raw.get("band") or "").strip().lower()
        if band not in PRICE_BANDS:
            raise ValueError(f"band {raw.get('band')!r} is not on the anchor scale — use one of "
                             f"{list(PRICE_BANDS)} (closed vocabulary, never coerced)")
        price_raw = raw.get("price", raw.get("price_point"))
        point = by_label.get(str(price_raw).strip()) if price_raw is not None else None
        if point is None:
            amt = _amount(price_raw)
            point = by_amount.get(amt) if amt is not None else None
        if point is None:
            raise ValueError(f"price {price_raw!r} is not a rung of this ladder "
                             f"({[p['label'] for p in points]}) — responses must stay on the ladder")
        rows.append({"persona_id": pid, "price": point["label"], "amount": point["amount"],
                     "band": band, "quote": str(raw.get("quote") or "").strip()})

    pids = persona_ids or list(dict.fromkeys(r["persona_id"] for r in rows))
    personas = {pid: p for pid in pids if (p := store.get_persona(pid))}
    result = _derive_ladder(points, rows, personas)

    rng = result["overall"]["acceptable_range"]
    cliff = result["overall"]["cliff"]
    verdict = ((f"Acceptable range {rng['low']}–{rng['high']}." if rng
                else "No price point reaches majority acceptance.")
               + (f" Cliff after {cliff['from']} (acceptance −{cliff['drop']})." if cliff else ""))
    pl_finding = _artifacts.finding(verdict, kind="price_ladder",
                                    score={"respondents": result["overall"]["respondents"]},
                                    meta={"result": result})
    findings_in = list(findings or []) + [stamp_derived_finding(pl_finding, statements)]
    # Each rung becomes a council prompt (id 'price:<label>') so per-rung statements resolve and
    # the inspector renders one card-group per price point (same trick as head_to_head's options).
    rung_prompts = [_artifacts.prompt(p["label"], kind="question", id=f"price:{p['label']}")
                    for p in points]

    session = record_council(
        project["id"], prompt, pids, statements=statements, proposal="",
        summary=summary, exec_summary=exec_summary,
        selection_reason=selection_reason or "price-ladder panel",
        prompts=rung_prompts, findings=findings_in, key=key, created_at=created_at, store=store,
        claims=claims, dispatch_token=dispatch_token)

    session["price_ladder"] = {
        "price_points": points,
        "responses": rows,
        "result": result,
        "recorded_at": utc_now_iso(),
    }
    store.insert_council_session(session)
    return session


def get_price_ladder(session_id: str, store: Store | None = None) -> dict[str, Any]:
    """One price-ladder result by council-session id — the ladder, the raw per-persona/per-rung
    responses and the derived result (acceptance, range, cliffs). Raises if not a price ladder."""
    store = store or Store()
    c = store.get_council_session(session_id)
    if not c:
        raise KeyError(f"Unknown council session: {session_id}")
    pl = c.get("price_ladder")
    if not pl:
        raise KeyError(f"Council {session_id} is not a price ladder")
    return {"id": c["id"], "prompt": c["prompt"], "project_id": c.get("project_id", ""),
            "created_at": c["created_at"], **pl}


def is_price_ladder(council: dict[str, Any]) -> bool:
    """True when a council session carries a recorded price-ladder block."""
    return bool(council.get("price_ladder"))


def price_ladder_analysis(session_id: str, store: Store | None = None) -> dict[str, Any]:
    """The ANALYTICS shape of a recorded price ladder (pricing protocol step `range_and_cliffs`),
    next to head_to_head's segmented_verdict: acceptable-price range + cliff point, overall and one
    row per segment — derived deterministically at record time and read back from the stored block.
    The host argues the pricing story; these are the numbers it stands on."""
    store = store or Store()
    pl = get_price_ladder(session_id, store=store)
    res = pl.get("result") or {}
    overall = res.get("overall") or {}
    return {
        "schema": "price_ladder_analysis",
        "session_id": pl["id"], "project_id": pl.get("project_id", ""), "prompt": pl.get("prompt", ""),
        "bands": res.get("bands", list(PRICE_BANDS)),
        "overall": {"respondents": overall.get("respondents", 0),
                    "acceptable_range": overall.get("acceptable_range"),
                    "cliff": overall.get("cliff"),
                    "points": overall.get("points", [])},
        "segments": res.get("segments", []),
    }
