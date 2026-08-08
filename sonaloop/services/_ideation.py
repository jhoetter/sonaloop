"""Structured HMW ideation for the `ideation_hmw` Job (taxonomy `jobs[ideation_hmw].protocol`):
reframe → diverge → converge, end-to-end on existing record primitives — no parallel store.

- REFRAME: the host turns the raw problem into 3–5 How-Might-We questions, persisted as the
  project's open-question records (the existing question primitive — stable ids, queryable).
  A bare HMW question is not falsifiable, so it is NOT forced into the hypotheses table (that
  would pollute the eval scorecard's calibration math); instead, whenever the host can state a
  checkable bet for an HMW it passes `prediction` and the question is ALSO promoted to a real
  Hypothesis via record_hypothesis (full falsifiability validation, derived_from the question).
- DIVERGE: the council generates ideas (brief_council with the HMW questions as prompts); every
  idea is persisted as a first-class NOTE node of kind `idea` (the existing affinity primitive)
  carrying structured data {persona_id, hmw_ref, cluster} — attributed or rejected, queryable
  via list_ideas for synthesis.
- CONVERGE: a FORCED ranking (ordered picks, host-authored rationale per pick) is recorded as an
  `ideation` block on a CouncilSession (the head_to_head/price_ladder pattern), so the summary is
  a graph node a DecisionRecord can cite as based_on evidence ({kind:'council', id}) — the output
  shape is decision-record compatible by construction.

Host-authors-all-text contract (README): the host authors the HMW questions, the idea texts, the
cluster tags and every rationale; this module validates structure (counts, attribution, refs that
resolve) and persists. No server-side text-LLM call ever happens here.
"""
from __future__ import annotations

from typing import Any

from ..config import utc_now_iso
from ..storage import Store
from .. import artifacts as _artifacts
from ..research_integrity import stamp_derived_finding

from ._common import *  # noqa: F401,F403  (stable_id, _require_research_project, …)


def _project_hmw_questions(project_id: str, store: Store) -> dict[str, dict[str, Any]]:
    """The project's recorded HMW questions, keyed by open-question id (study_id 'hmw' marks the
    reframe-recorded ones, but ANY open question may anchor an idea — the host may reframe in
    several passes)."""
    return {oq["id"]: oq for oq in store.list_open_questions(project_id)}


# --------------------------------------------------------------------------- reframe

def record_hmw_reframe(project_id: str, problem: str, hmws: list[Any],
                       store: Store | None = None) -> dict[str, Any]:
    """REFRAME (protocol step 1): persist the host-authored How-Might-We reframe of a raw problem —
    3 to 5 HMW questions (fewer is under-reframed, more is a backlog), each a string or
    {question, prediction?, derived_from?}. Every question becomes an open-question record (stable
    id — the `hmw_ref` ideas attach to). When the host supplies a falsifiable `prediction`
    ({metric, expected_value|expected_direction, …}) the question is ALSO promoted to a real
    Hypothesis (record_hypothesis — full validation), linked derived_from the question record."""
    store = store or Store()
    project = _require_research_project(store, project_id)
    problem = str(problem or "").strip()
    if not problem:
        raise ValueError("problem is required (the raw problem being reframed)")
    items = []
    for raw in (hmws or []):
        if isinstance(raw, dict):
            q = str(raw.get("question") or raw.get("text") or "").strip()
            items.append({"question": q, "prediction": raw.get("prediction"),
                          "derived_from": raw.get("derived_from")})
        else:
            items.append({"question": str(raw).strip(), "prediction": None, "derived_from": None})
    items = [it for it in items if it["question"]]
    if not 3 <= len(items) <= 5:
        raise ValueError(f"a reframe is 3–5 HMW questions (got {len(items)}) — fewer is "
                         "under-reframed, more is a backlog; pick the sharpest")
    texts = [it["question"] for it in items]
    if len(set(texts)) != len(texts):
        raise ValueError("HMW questions must be distinct")

    out = []
    for it in items:
        oq = record_open_questions(project["id"], [it["question"]], study_id="hmw",  # noqa: F821 (bound)
                                   store=store)[0]
        rec: dict[str, Any] = {"id": oq["id"], "question": oq["text"]}
        if it["prediction"]:
            refs = [{"kind": "open_question", "id": oq["id"], "role": "derived_from"},
                    *(it["derived_from"] or [])]
            hyp = record_hypothesis(project["id"], it["question"], it["prediction"],  # noqa: F821 (bound)
                                    derived_from=refs, store=store)["hypothesis"]
            rec["hypothesis_id"] = hyp["id"]
        out.append(rec)
    return {"schema": "hmw_reframe", "project_id": project["id"], "problem": problem, "hmw": out,
            "next": ("Run the diverge council (brief_council with these questions as prompts), "
                     "then record_ideas — every idea attributed to a persona + one of these "
                     "hmw ids.")}


# --------------------------------------------------------------------------- diverge

def record_ideas(project_id: str, ideas: list[dict[str, Any]],
                 store: Store | None = None) -> list[dict[str, Any]]:
    """DIVERGE (protocol step 2): persist host-authored ideas as first-class NOTE nodes of kind
    `idea`. Every idea MUST be attributed — {text, persona_id (the source voice — must exist),
    hmw_ref (the recorded HMW question it answers — must resolve), cluster? (host-authored
    affinity tag)} — an unattributed or unanchored idea is rejected, that is the protocol.
    Idea notes live in the project graph (sections/edges work on them) and are queryable via
    list_ideas for synthesis."""
    store = store or Store()
    project = _require_research_project(store, project_id)
    hmw = _project_hmw_questions(project["id"], store)
    if not ideas:
        raise ValueError("ideas is required — [{text, persona_id, hmw_ref, cluster?}, …]")
    texts = [str(i.get("text") or "").strip() for i in ideas]
    if len(set(texts)) != len(texts):
        raise ValueError("idea texts must be distinct (duplicates would collapse into one note)")
    out = []
    for raw in ideas:
        text = str(raw.get("text") or "").strip()
        if not text:
            raise ValueError("every idea needs non-empty text")
        pid = str(raw.get("persona_id") or "").strip()
        if not pid or not store.get_persona(pid):
            raise ValueError(f"idea {text[:40]!r}: persona_id {pid!r} does not resolve — every "
                             "idea is attributed to the persona whose voice produced it")
        ref = str(raw.get("hmw_ref") or "").strip()
        if ref not in hmw:
            raise ValueError(f"idea {text[:40]!r}: hmw_ref {ref!r} is not a recorded HMW question "
                             "of this project — record_hmw_reframe first")
        data = {"persona_id": pid, "hmw_ref": ref}
        cluster = str(raw.get("cluster") or "").strip()
        if cluster:
            data["cluster"] = cluster
        note = create_note(project["id"], text, kind="idea", data=data, store=store)  # noqa: F821 (bound)
        out.append({**note, "hmw_question": hmw[ref]["text"]})
    return out


def list_ideas(project_id: str, hmw_ref: str | None = None, persona_id: str | None = None,
               cluster: str | None = None, store: Store | None = None) -> list[dict[str, Any]]:
    """The project's idea notes (kind `idea`), filterable by HMW question, source persona, or
    host-authored cluster — the queryable synthesis surface for the diverge output."""
    store = store or Store()
    out = []
    for n in list_notes(project_id, store=store):  # noqa: F821 (bound)
        if n.get("kind") != "idea":
            continue
        d = n.get("data") or {}
        if hmw_ref and d.get("hmw_ref") != hmw_ref:
            continue
        if persona_id and d.get("persona_id") != persona_id:
            continue
        if cluster and d.get("cluster") != cluster:
            continue
        out.append(n)
    return out


# --------------------------------------------------------------------------- converge

def record_ideation_summary(project_id: str, problem: str, shortlist: list[dict[str, Any]],
                            statements: list | None = None, summary: str = "",
                            exec_summary: str = "", selection_reason: str = "",
                            key: str | None = None, created_at: str | None = None,
                            store: Store | None = None,
                            claims: list[dict[str, Any]] | None = None,
                            dispatch_token: str | None = None) -> dict[str, Any]:
    """CONVERGE (protocol step 3): persist the FORCED ranking as an `ideation` block on a
    CouncilSession. `shortlist` is the ordered picks — [{idea_id, rationale}] — rank = position
    (1-based); every pick must be a recorded idea note and carry a host-authored rationale (a
    ranking without reasons is a mood board). The session aggregates the run end-to-end (HMW
    questions as prompts, the full idea pool, the ranked shortlist) and is the node a
    DecisionRecord cites as based_on evidence — see the returned `cite_as`."""
    store = store or Store()
    project = _require_research_project(store, project_id)
    problem = str(problem or "").strip()
    if not problem:
        raise ValueError("problem is required (the problem the ideation answered)")
    pool = {n["id"]: n for n in list_ideas(project["id"], store=store)}
    if not pool:
        raise ValueError("no ideas recorded yet — diverge first (record_ideas)")
    if not shortlist:
        raise ValueError("shortlist is required — the ordered picks [{idea_id, rationale}]")
    hmw = _project_hmw_questions(project["id"], store)

    picks, seen = [], set()
    for rank, raw in enumerate(shortlist, start=1):
        iid = str(raw.get("idea_id") or raw.get("id") or "").strip()
        idea = pool.get(iid)
        if not idea:
            raise ValueError(f"shortlist rank {rank}: idea_id {iid!r} is not a recorded idea of "
                             "this project")
        if iid in seen:
            raise ValueError(f"shortlist rank {rank}: idea {iid} ranked twice — a forced ranking "
                             "is a strict order")
        seen.add(iid)
        rationale = str(raw.get("rationale") or "").strip()
        if not rationale:
            raise ValueError(f"shortlist rank {rank}: rationale is required — a ranking without "
                             "reasons is a mood board, not a convergence")
        d = idea.get("data") or {}
        picks.append({"rank": rank, "idea_id": iid, "text": idea["text"],
                      "persona_id": d.get("persona_id", ""), "hmw_ref": d.get("hmw_ref", ""),
                      "cluster": d.get("cluster"), "rationale": rationale})

    # The HMW questions referenced by the pool become the session prompts (id 'hmw:<n>') so the
    # inspector groups the run by question — the same trick as head_to_head's options.
    hmw_ids = list(dict.fromkeys(
        (n.get("data") or {}).get("hmw_ref") for n in pool.values()
        if (n.get("data") or {}).get("hmw_ref") in hmw))
    hmw_out = [{"id": hid, "question": hmw[hid]["text"]} for hid in hmw_ids]
    prompts = [_artifacts.prompt(hmw[hid]["text"], kind="question", id=f"hmw:{i}")
               for i, hid in enumerate(hmw_ids)]
    persona_ids = list(dict.fromkeys(
        (n.get("data") or {}).get("persona_id") for n in pool.values()
        if (n.get("data") or {}).get("persona_id")))

    verdict = (f"Shortlist: {len(picks)} of {len(pool)} ideas, spanning "
               f"{len({p['hmw_ref'] for p in picks if p['hmw_ref']})} HMW question(s) and "
               f"{len({p['persona_id'] for p in picks if p['persona_id']})} persona voice(s).")
    id_finding = stamp_derived_finding(
        _artifacts.finding(verdict, kind="ideation",
                           score={"ideas": len(pool), "shortlisted": len(picks)},
                           meta={"shortlist": picks}),
        statements,
    )

    session = record_council(
        project["id"], problem, persona_ids, statements=statements, proposal="",
        summary=summary, exec_summary=exec_summary,
        selection_reason=selection_reason or "ideation council (HMW diverge→converge)",
        prompts=prompts, findings=[id_finding], key=key, created_at=created_at, store=store,
        claims=claims, dispatch_token=dispatch_token)

    session["ideation"] = {
        "problem": problem,
        "hmw": hmw_out,
        "ideas": [{"id": n["id"], "text": n["text"], **(n.get("data") or {})} for n in pool.values()],
        "shortlist": picks,
        "recorded_at": utc_now_iso(),
    }
    store.insert_council_session(session)
    # The decision-record seam: cite THIS session as based_on evidence (resolves via resolve_ref).
    return {**session, "cite_as": {"kind": "council", "id": session["id"], "role": "based_on"}}


def get_ideation(session_id: str, store: Store | None = None) -> dict[str, Any]:
    """One ideation summary by council-session id — the problem, the HMW questions, the full idea
    pool and the ranked shortlist, plus the ready-made `cite_as` ref a decision record can use.
    Raises if the session carries no ideation block."""
    store = store or Store()
    c = store.get_council_session(session_id)
    if not c:
        raise KeyError(f"Unknown council session: {session_id}")
    block = c.get("ideation")
    if not block:
        raise KeyError(f"Council {session_id} is not an ideation summary")
    return {"id": c["id"], "prompt": c["prompt"], "project_id": c.get("project_id", ""),
            "created_at": c["created_at"], **block,
            "cite_as": {"kind": "council", "id": c["id"], "role": "based_on"}}


def is_ideation(council: dict[str, Any]) -> bool:
    """True when a council session carries a recorded ideation block."""
    return bool(council.get("ideation"))
