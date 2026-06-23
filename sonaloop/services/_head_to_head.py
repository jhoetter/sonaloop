"""Head-to-Head Format (taxonomy id `head_to_head`): run a council on a DIRECT comparison of two
(or more) concrete options — two prices, two messages, two captured A/B variants — and return a
*reasoned, segmented preference* (which option, how decisively, why, and who-prefers-what) instead
of two separate yes/no runs. This is a FORMAT that Job presets compose, NOT a Job of its own.

Built ON TOP OF the artifacts/variant plumbing (services/_artifacts_service.py + brief_council):
- ARTIFACT options reuse `council_artifact_briefs` → the labelled, captured variant briefs, folded
  into each participant's context exactly like a normal artifact council.
- TEXT options (no artifact — "$29/mo" vs "$49/mo", message A vs message B) are built into the SAME
  labelled A/B comparison block so personas compare them side-by-side. Both kinds coexist.

Host-authors-all-text contract (README): the host (Claude) authors the prose verdict; this module is
the SCAFFOLD — it assembles the comparison brief, collects each persona's per-option stance + which
option they prefer, and does the DETERMINISTIC aggregation server-side (tally who preferred which
option → preference + margin, group by persona segment → segment-splits). No server-side text-LLM
call ever happens here; qualitative synthesis stays the host's job.

A recorded head-to-head IS a CouncilSession (so it reuses council persistence, the project graph, and
the inspector UI for free), carrying a `head_to_head` block — the labelled options + the deterministic
aggregate — plus a `finding` of kind `head_to_head` so the result is a stored, queryable seam that a
future calibration/analytics surface can read against real outcomes (none exists yet — clean seam).
"""
from __future__ import annotations

from typing import Any

from ..config import utc_now_iso, ensure_content_language, language_instruction
from ..storage import Store
from .. import artifacts as _artifacts

from ._common import *  # noqa: F401,F403  (stable_id, _require_research_project, list_personas, …)


def _label_for(i: int) -> str:
    """A/B/C… label by index (matches artifact auto-labelling), V<n> past Z."""
    return chr(ord("A") + i) if i < 26 else f"V{i + 1}"


def _option_order(labels: list[str], persona_id: str, prompt: str) -> list[str]:
    """Deterministic per-persona variant order — the A/B POSITION-BIAS guard (taxonomy job
    `ab_test`, protocol step `randomized_order`): a Fisher-Yates permutation driven by a hash of
    (persona_id, prompt), so different personas see different orders yet the same brief is stable
    across calls (testable, resumable — no RNG state). The order actually shown is recorded back
    via `variant_meta.order_shown` on record_head_to_head."""
    import hashlib
    seed = int.from_bytes(hashlib.sha256(f"{persona_id}|{prompt}".encode()).digest()[:8], "big")
    out = list(labels)
    for i in range(len(out) - 1, 0, -1):
        seed, j = divmod(seed, i + 1)
        out[i], out[j] = out[j], out[i]
    return out


def _normalize_options(project_id: str, options: list[Any], store: Store) -> list[dict[str, Any]]:
    """Turn the host's `options` into a uniform list of labelled comparison options. Each entry is either
    an ARTIFACT (an id/label of an artifact already ingested via add_artifact → reuse its captured brief)
    or a plain TEXT option (a string, or {label?, title?, text}). Labels are assigned/preserved so A/B/…
    line up across kinds; an artifact keeps its own A/B label."""
    art_briefs = {b.get("label"): b for b in council_artifact_briefs(project_id, store=store)}
    art_by_id = {b.get("id"): b for b in art_briefs.values()}
    out: list[dict[str, Any]] = []
    used = set()
    for raw_opt in options:
        brief = None
        text = ""
        title = ""
        label = None
        if isinstance(raw_opt, dict):
            # An explicit artifact reference, or an inline text option.
            ref = raw_opt.get("artifact_id") or raw_opt.get("artifact")
            if ref and (ref in art_by_id or ref in art_briefs):
                brief = art_by_id.get(ref) or art_briefs.get(ref)
            title = (raw_opt.get("title") or "").strip()
            text = (raw_opt.get("text") or raw_opt.get("option") or "").strip()
            label = (raw_opt.get("label") or "").strip() or None
        else:
            tok = str(raw_opt).strip()
            if tok in art_by_id or tok in art_briefs:      # bare artifact id/label
                brief = art_by_id.get(tok) or art_briefs.get(tok)
            else:
                text = tok
        if label is None:
            label = (brief or {}).get("label")
        if label is None or label in used:
            label = next(l for i in range(99) if (l := _label_for(i)) not in used)
        used.add(label)
        if brief is not None:
            out.append({"label": label, "kind": "artifact", "artifact_id": brief.get("id"),
                        "title": title or brief.get("title") or brief.get("url"), "brief": brief})
        else:
            out.append({"label": label, "kind": "text", "title": title or text[:60], "text": text})
    return out


def _render_options_context(options: list[dict[str, Any]]) -> str:
    """Render the options as ONE labelled comparison block the host folds into each persona's context, so
    every persona weighs the SAME options side-by-side. Artifact options carry their captured copy (via
    render_artifacts_context); text options carry their literal text — uniformly labelled OPTION A/B/…."""
    head = ("HEAD-TO-HEAD — compare the options below DIRECTLY and state which one you prefer and WHY. "
            "Do not score them in isolation; weigh A vs B (vs C…) against each other for YOUR context.")
    parts = [head]
    for o in options:
        tag = f"OPTION {o['label']}: {o.get('title') or ''}".strip().rstrip(":")
        if o["kind"] == "artifact":
            body = render_artifacts_context([o["brief"]]) or f"(artifact {o.get('artifact_id')})"
        else:
            body = o.get("text") or "(empty option)"
        parts.append(f"--- {tag} ---\n{body}")
    return "\n\n".join(parts)


def brief_head_to_head(project_id: str, prompt: str, options: list[Any],
                       persona_ids: list[str] | None = None, filters: dict[str, Any] | None = None,
                       count: int = 4, context: str | None = None,
                       store: Store | None = None) -> dict[str, Any]:
    """Gather everything to run a host-authored HEAD-TO-HEAD (X vs Y) over a research project's personas.
    `options` are the things being compared — each is an ARTIFACT (an id/label already ingested via
    add_artifact, e.g. two A/B variants) or a plain TEXT option (a string, or {label?, title?, text} for
    "$29/mo" vs "$49/mo"). They are labelled A/B/… and folded into each participant's context as ONE
    side-by-side comparison block. Without persona_ids: returns candidate personas to select from. With
    persona_ids: returns each participant's loaded context + the labelled options to author per-option
    stances and a per-persona `preference` against, then call record_head_to_head."""
    store = store or Store()
    project = _require_research_project(store, project_id)
    opts = _normalize_options(project["id"], options or [], store)
    if len(opts) < 2:
        raise ValueError("head_to_head needs at least two options to compare (got "
                         f"{len(opts)}). Add artifacts (add_artifact) or pass plain text options.")
    options_context = _render_options_context(opts)
    language = ensure_content_language(" ".join(filter(None, [prompt, context])))
    public_options = [{k: v for k, v in o.items() if k != "brief"} for o in opts]
    label_ids = [o["label"] for o in opts]

    if not persona_ids:
        personas = list_personas(filters, store)
        candidates = [
            {"persona_id": p["id"], "display_name": p["display_name"],
             "source_description": p["source_description"], "segment": p.get("segment", {}),
             "role": p.get("role", {}), "goals": p.get("goals", []), "pain_points": p.get("pain_points", [])}
            for p in personas
        ]
        return {
            "schema": "head_to_head_selection", "language": language, "project_id": project["id"],
            "prompt": prompt, "options": public_options,
            "count": min(max(2, count), len(candidates)) if candidates else 0,
            "candidate_personas": candidates,
            "instructions": (
                "Pick a segment-DIVERSE panel so the preference can be split by segment (cover the "
                "segments the options serve and those they don't). Then call brief_head_to_head again "
                f"with persona_ids=[...]. {language_instruction(language)}"
                if candidates else "No personas exist yet. Create some first."),
        }

    context_block = "\n\n".join(filter(None, [context or "", options_context]))
    by_label = {o["label"]: o for o in opts}
    participants = []
    for pid in persona_ids:
        p = store.get_persona(pid)
        if not p:
            continue
        ctx = prepare_persona_agent_context(
            p["id"], f"Head-to-head prompt: {prompt}\nOptions:\n{context_block}", store=store)
        # Each participant sees the options in THEIR randomized order (position-bias guard) —
        # record the order actually shown via variant_meta.order_shown.
        order = _option_order(label_ids, p["id"], prompt)
        ordered_context = _render_options_context([by_label[lab] for lab in order])
        agent_context = f"{ctx['agent_context']}\n\n=== HEAD-TO-HEAD OPTIONS ===\n{ordered_context}"
        participants.append({
            "persona_id": p["id"], "display_name": p["display_name"],
            "segment": p.get("segment", {}), "soul_path": ctx["soul_path"],
            "option_order": order,
            "agent_context": agent_context,
        })
    return {
        "schema": "head_to_head", "language": language, "project_id": project["id"], "prompt": prompt,
        "external_context": context, "options": public_options, "option_labels": label_ids,
        "participants": participants, "options_context": options_context,
        "instructions": (
            "THE OPTIONS ARE IN THE ROOM, labelled A/B/… — each participant's agent_context ends with the "
            "side-by-side comparison. For EACH persona author: (1) one `statement` per option giving that "
            "persona's stance on it (about={kind:'prompt', id:'opt:A'|'opt:B'|…}, "
            "stance:{value -2..2, label?: support|conditional|neutral|skeptical|oppose}); "
            "(2) the persona's single `preference` = the option label they'd pick, with a one-line reason. "
            "Stay anti-steering — a persona may genuinely prefer either side or be torn. Ground every "
            "statement in agent_context; quote the captured artifact / the literal text option, don't "
            "invent. Each participant carries `option_order` — present the options in THAT order (the "
            "position-bias guard) and record it back via variant_meta.order_shown. Then call "
            "record_head_to_head(project_id, prompt, options, preferences=[{persona_id, "
            "choice, intensity?, reason}], statements=[...], exec_summary, summary, variant_meta?). "
            "For an ab_test Job also pass variant_meta.hypothesis_id — the ONE bet stamped before "
            "exposure (record_hypothesis). The server tallies preference + margin + abstentions + "
            f"segment-splits; you author the prose verdict. {language_instruction(language)}"),
    }


def _aggregate(options: list[dict[str, Any]], preferences: list[dict[str, Any]],
               personas: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """The DETERMINISTIC head-to-head math (no LLM): tally who preferred which option → overall preference
    + margin, and break the same tally down by persona segment → who-prefers-what. `margin` is the
    winner's lead over the runner-up as a share of the cast votes (0 = a tie, 1 = unanimous); `decisive`
    labels it for the UI. Segment is `persona.segment.customer_type` (the archetype axis), falling back to
    'unspecified'."""
    labels = [o["label"] for o in options]
    title_by = {o["label"]: o.get("title", o["label"]) for o in options}
    valid = set(labels)
    tally = {lab: 0 for lab in labels}
    seg_tally: dict[str, dict[str, int]] = {}
    seg_abst: dict[str, int] = {}
    cast = 0
    abstentions = 0
    for pref in preferences:
        choice = str(pref.get("choice") or pref.get("label") or pref.get("preference") or "").strip()
        seg = "unspecified"
        p = personas.get(pref.get("persona_id", ""))
        if p:
            seg = (p.get("segment") or {}).get("customer_type") or seg
        if choice not in valid:                            # abstention / unparseable → counted as such
            abstentions += 1
            seg_abst[seg] = seg_abst.get(seg, 0) + 1
            seg_tally.setdefault(seg, {lab: 0 for lab in labels})
            continue
        cast += 1
        tally[choice] += 1
        seg_tally.setdefault(seg, {lab: 0 for lab in labels})[choice] += 1

    ranked = sorted(labels, key=lambda lab: tally[lab], reverse=True)
    winner = ranked[0] if cast else None
    top = tally.get(winner, 0) if winner else 0
    runner = tally[ranked[1]] if len(ranked) > 1 else 0
    margin = round((top - runner) / cast, 3) if cast else 0.0
    tie = bool(winner) and sum(1 for lab in labels if tally[lab] == top) > 1
    decisive = ("tie" if (tie or margin == 0) else "narrow" if margin < 0.34
                else "clear" if margin < 0.67 else "decisive")

    segment_splits = []
    for seg, counts in sorted(seg_tally.items()):
        seg_cast = sum(counts.values())
        seg_ranked = sorted(labels, key=lambda lab: counts[lab], reverse=True)
        seg_winner = seg_ranked[0] if seg_cast else None
        seg_top = counts[seg_winner] if seg_winner else 0
        seg_runner = counts[seg_ranked[1]] if len(seg_ranked) > 1 else 0
        seg_tie = bool(seg_winner) and sum(1 for lab in labels if counts[lab] == seg_top) > 1
        segment_splits.append({
            "segment": seg, "voters": seg_cast, "tally": counts,
            "prefers": (None if (seg_tie or not seg_cast) else seg_winner),
            "margin": round((seg_top - seg_runner) / seg_cast, 3) if seg_cast else 0.0,
            "abstentions": seg_abst.get(seg, 0),
        })

    return {
        "options": [{"label": lab, "title": title_by[lab], "votes": tally[lab]} for lab in labels],
        "voters": cast,
        "abstentions": abstentions,
        "preference": (None if tie else winner),
        "preference_title": (title_by.get(winner) if winner and not tie else None),
        "tally": tally,
        "margin": margin,
        "decisive": decisive,
        "segment_splits": segment_splits,
    }


def _validate_variant_meta(meta: dict[str, Any] | None, opts: list[dict[str, Any]],
                           store: Store) -> dict[str, Any] | None:
    """Validate the OPTIONAL A/B-protocol metadata (taxonomy job `ab_test`) so a recorded
    head-to-head is auditable: `variants` maps option labels → external variant ids/details
    (a bare string becomes {id}); `order_shown` records the per-persona presentation order —
    each value must be a permutation of the option labels (the position-bias guard, made
    checkable); `hypothesis_id` references the ONE bet stamped BEFORE exposure (must resolve).
    All keys optional; recordings without metadata stay valid (backward-compatible)."""
    if not meta:
        return None
    if not isinstance(meta, dict):
        raise ValueError("variant_meta must be a dict {variants?, order_shown?, hypothesis_id?}")
    unknown = set(meta) - {"variants", "order_shown", "hypothesis_id"}
    if unknown:
        raise ValueError(f"unknown variant_meta keys {sorted(unknown)} — allowed: "
                         "variants, order_shown, hypothesis_id")
    labels = [o["label"] for o in opts]
    out: dict[str, Any] = {}
    variants = meta.get("variants")
    if variants:
        if not isinstance(variants, dict) or not set(variants) <= set(labels):
            raise ValueError(f"variant_meta.variants keys must be option labels {labels}, got "
                             f"{sorted(variants) if isinstance(variants, dict) else variants!r}")
        out["variants"] = {lab: (dict(v) if isinstance(v, dict) else {"id": str(v)})
                           for lab, v in variants.items()}
    order_shown = meta.get("order_shown")
    if order_shown:
        if not isinstance(order_shown, dict):
            raise ValueError("variant_meta.order_shown must map persona_id -> [option labels]")
        for pid, order in order_shown.items():
            if sorted(str(x) for x in (order or [])) != sorted(labels):
                raise ValueError(f"variant_meta.order_shown[{pid!r}] must be a permutation of the "
                                 f"option labels {labels}, got {order!r} — record the order "
                                 "actually shown to that persona")
        out["order_shown"] = {pid: [str(x) for x in order] for pid, order in order_shown.items()}
    hyp = meta.get("hypothesis_id")
    if hyp:
        if not store.get_hypothesis(str(hyp)):
            raise ValueError(f"variant_meta.hypothesis_id does not resolve: {hyp!r} — stamp the "
                             "bet FIRST (record_hypothesis), then expose the variants")
        out["hypothesis_id"] = str(hyp)
    return out or None


def record_head_to_head(project_id: str, prompt: str, options: list[Any],
                        preferences: list[dict[str, Any]] | None = None,
                        persona_ids: list[str] | None = None, statements: list | None = None,
                        summary: str = "", exec_summary: str = "", selection_reason: str = "",
                        findings: list | None = None, key: str | None = None,
                        variant_meta: dict[str, Any] | None = None,
                        created_at: str | None = None, store: Store | None = None) -> dict[str, Any]:
    """Persist a host-authored HEAD-TO-HEAD as a CouncilSession carrying a `head_to_head` block. The host
    passes the labelled `options`, each persona's `preferences` ([{persona_id, choice (a label),
    intensity?, reason}]), and the authored `statements` (per-option stances) + exec_summary/summary (the
    prose verdict). The SERVER does the deterministic aggregation (preference + margin + abstentions +
    segment-splits) from `preferences` and stores it — a queryable result. `variant_meta` is the OPTIONAL
    A/B-protocol metadata (job `ab_test`): {variants: {label: {id,…}}, order_shown: {persona_id:
    [labels]}, hypothesis_id} — validated, persisted, queryable; recordings without it stay valid.
    Pass a stable `key` for a deterministic id (idempotent upsert)."""
    store = store or Store()
    project = _require_research_project(store, project_id)
    opts = _normalize_options(project["id"], options or [], store)
    if len(opts) < 2:
        raise ValueError("head_to_head needs at least two options to compare.")
    vmeta = _validate_variant_meta(variant_meta, opts, store)
    public_options = [{k: v for k, v in o.items() if k != "brief"} for o in opts]
    prefs = [dict(p) for p in (preferences or []) if p.get("persona_id")]
    pids = persona_ids or [p["persona_id"] for p in prefs]
    personas = {pid: store.get_persona(pid) for pid in pids}
    personas = {pid: p for pid, p in personas.items() if p}

    aggregate = _aggregate(opts, prefs, personas)

    # The head-to-head result is ALSO surfaced as a council finding so it is queryable next to other
    # study findings (the analytics/calibration seam — no analytics system is built; this is the hook).
    win = aggregate["preference"]
    verdict = (f"Preference: Option {win} — {aggregate['preference_title']} "
               f"({aggregate['decisive']}, margin {aggregate['margin']})." if win
               else f"No clear preference — tie ({aggregate['voters']} voters).")
    ht_finding = _artifacts.finding(verdict, kind="head_to_head",
                                    score={"margin": aggregate["margin"], "voters": aggregate["voters"]},
                                    meta={"aggregate": aggregate})
    findings_in = list(findings or []) + [ht_finding]

    # The labelled options become the council prompts (id 'opt:<label>') so each per-option statement's
    # about-ref resolves and the discovery-style Q→A grouping renders one card-group per option.
    option_prompts = [_artifacts.prompt(o.get("title") or o["label"], kind="proposal", id=f"opt:{o['label']}")
                      for o in opts]

    # Reuse record_council for ALL the persistence/graph wiring; head_to_head rides as extra metadata.
    session = record_council(
        project["id"], prompt, pids, statements=statements, proposal="",
        summary=summary, exec_summary=exec_summary,
        selection_reason=selection_reason or "head-to-head panel",
        prompts=option_prompts, findings=findings_in, key=key, created_at=created_at, store=store)

    session["head_to_head"] = {
        "options": public_options,
        "preferences": prefs,
        "result": aggregate,
        "recorded_at": utc_now_iso(),
        **({"variant_meta": vmeta} if vmeta else {}),
    }
    store.insert_council_session(session)
    return {**session, "url": web_url(f"/councils/{session['id']}"),  # noqa: F821 (bound)
            "project_url": web_url(f"/jobs/{project_id}")}  # noqa: F821 (bound)


def get_head_to_head(session_id: str, store: Store | None = None) -> dict[str, Any]:
    """One head-to-head result by council-session id — its options, per-persona preferences and the
    deterministic aggregate (preference + margin + segment-splits). Raises if not a head-to-head."""
    store = store or Store()
    c = store.get_council_session(session_id)
    if not c:
        raise KeyError(f"Unknown council session: {session_id}")
    ht = c.get("head_to_head")
    if not ht:
        raise KeyError(f"Council {session_id} is not a head-to-head")
    out = {"id": c["id"], "prompt": c["prompt"], "project_id": c.get("project_id", ""),
           "created_at": c["created_at"], "url": web_url(f"/councils/{c['id']}"), **ht}  # noqa: F821 (bound)
    if c.get("project_id"):
        out["project_url"] = web_url(f"/jobs/{c['project_id']}")  # noqa: F821 (bound)
    return out


def is_head_to_head(council: dict[str, Any]) -> bool:
    """True when a council session carries a recorded head-to-head result (drives the UI branch)."""
    return bool(council.get("head_to_head"))


def segmented_verdict(session_id: str, store: Store | None = None) -> dict[str, Any]:
    """The SEGMENTED verdict of a recorded head-to-head (job `ab_test`, protocol step
    `segmented_verdict`), derived from the STORED block — works for recordings made before the A/B
    variant metadata existed: overall winner + margin + decisiveness + abstentions, one row per
    segment (winner, margin, voters, abstentions), plus — when the run followed the ab_test
    protocol — the hypothesis ref and variant ids the verdict answers. Deterministic math only;
    the prose verdict stays the host's."""
    store = store or Store()
    ht = get_head_to_head(session_id, store=store)
    res = ht.get("result") or {}
    prefs = ht.get("preferences") or []
    voters = res.get("voters", 0)
    segments = []
    for s in res.get("segment_splits") or []:
        counts = s.get("tally") or {}
        seg_cast = s.get("voters", 0)
        if "margin" in s:                                  # post-metadata recording: stored as-is
            seg_margin = s["margin"]
        else:                                              # compatibility recording: derive from the tally
            ranked = sorted(counts, key=lambda lab: counts[lab], reverse=True)
            top = counts[ranked[0]] if ranked else 0
            runner = counts[ranked[1]] if len(ranked) > 1 else 0
            seg_margin = round((top - runner) / seg_cast, 3) if seg_cast else 0.0
        segments.append({"segment": s.get("segment", "unspecified"), "winner": s.get("prefers"),
                         "voters": seg_cast, "margin": seg_margin,
                         "abstentions": s.get("abstentions", 0)})
    meta = ht.get("variant_meta") or {}
    return {
        "schema": "segmented_verdict",
        "session_id": ht["id"], "project_id": ht.get("project_id", ""), "prompt": ht.get("prompt", ""),
        "overall": {
            "winner": res.get("preference"), "winner_title": res.get("preference_title"),
            "margin": res.get("margin", 0.0), "decisive": res.get("decisive", "tie"),
            "voters": voters,
            "abstentions": res.get("abstentions", max(0, len(prefs) - voters)),
        },
        "segments": segments,
        "hypothesis_id": meta.get("hypothesis_id"),
        "variants": meta.get("variants") or {},
    }
