"""Red-Team / Falsification Format (taxonomy id `red_team`): run a council that deliberately argues the
NEGATIVE case — "why would this segment NOT adopt / NOT pay / churn?" — so the output STRESS-TESTS the
idea instead of flattering it. Persona work easily becomes confirmation bias; this Format reframes the
SAME council briefing toward DISCONFIRMATION and assigns each persona an explicit, deterministic
skeptic/adversarial lens (skeptic / blocker / switching-cost / status-quo / risk) so objections, blockers
and failure modes get surfaced concretely — not boilerplate.

Built ON TOP OF the council/artifact plumbing (services/_councils.py:brief_council + _artifacts_service):
- it REUSES `prepare_persona_agent_context` (SOUL + memory) and the captured-artifact briefs, so a
  red-team can be grounded in a REAL artifact (a live URL/price page/prototype) exactly like a council —
  it only RE-FRAMES the task ("attack this, do not flatter it") and STAMPS each persona's adversarial role
  into the brief. No council/briefing logic is duplicated.

Host-authors-all-text contract (README): the host (Claude) authors the prose objections; this module is
the SCAFFOLD — it assembles the disconfirmation brief with per-persona adversarial roles, collects each
persona's concrete objections (a `theme`, a severity, the persona who raised it), and does the
DETERMINISTIC aggregation server-side (group objections by theme → the structured "case against": how many
personas raise each blocker + worst severity). No server-side text-LLM call ever happens here. Theme
grouping folds case/whitespace ONLY — semantic merging ('price' vs 'pricing') stays with the host, nudged
by the brief surfacing the project's prior themes + a starter vocabulary for REUSE over invention.

`stance` runs the SAME question in both directions easily: "against" (the default — only the case against),
"for" (the confirming case), or "both" (a paired confirm+disconfirm so case-for and case-against sit side
by side and are directly comparable). A recorded red-team IS a CouncilSession (so it reuses council
persistence, the project graph, and the inspector UI for free), carrying a `red_team` block — the
adversarial roles + the deterministic case-against (and optional case-for) — plus a `finding` of kind
`red_team` so the result is a stored, queryable seam.
"""
from __future__ import annotations

from typing import Any

from ..config import utc_now_iso, ensure_content_language, language_instruction
from ..storage import Store
from ..suggestions import suggest_blocker_themes
from .. import artifacts as _artifacts
from ..research_integrity import stamp_derived_finding

from ._common import *  # noqa: F401,F403  (stable_id, _require_research_project, list_personas, …)


# The deterministic adversarial lenses a red-team assigns. Each persona gets ONE, round-robin, so the
# panel covers the distinct ways an idea breaks (no LLM choice — stable, visible in the brief).
RED_TEAM_ROLES: list[dict[str, str]] = [
    {"id": "skeptic", "name": "Skeptic",
     "lens": "Doubt the core claim. Why might it simply not be true / not work for you?"},
    {"id": "blocker", "name": "Adoption blocker",
     "lens": "Name the concrete blocker that stops you adopting — onboarding, integration, trust, proof."},
    {"id": "switching_cost", "name": "Switching cost",
     "lens": "What does leaving your current solution actually cost you (effort, risk, lock-in, habit)?"},
    {"id": "status_quo", "name": "Status-quo defender",
     "lens": "Argue why 'good enough today' wins — why you do nothing and keep what you have."},
    {"id": "risk", "name": "Risk & failure mode",
     "lens": "Surface the risk / failure mode / worst case that would make you regret this or churn."},
]

_STANCES = ("against", "for", "both")


def _assign_roles(persona_ids: list[str]) -> dict[str, dict[str, str]]:
    """Deterministically assign ONE adversarial lens to each persona, round-robin over RED_TEAM_ROLES, so
    the panel covers the distinct ways an idea breaks and the assignment is stable/reproducible."""
    return {pid: RED_TEAM_ROLES[i % len(RED_TEAM_ROLES)] for i, pid in enumerate(persona_ids)}


def _normalize_stance(stance: str | None) -> str:
    s = (stance or "against").strip().lower()
    if s in ("disconfirm", "negative", "case_against"):
        return "against"
    if s in ("confirm", "positive", "case_for"):
        return "for"
    return s if s in _STANCES else "against"


def _reframing(stance: str) -> str:
    """The DISCONFIRMATION reframing folded into every persona's task — the heart of red-team. It flips a
    normal council from 'react honestly' to 'deliberately argue the case against', and demands concrete,
    specific objections grounded in this persona's lived context (not boilerplate)."""
    against = (
        "RED-TEAM / FALSIFICATION — you are deliberately arguing the CASE AGAINST. Do NOT flatter this idea. "
        "Your job is to STRESS-TEST it: surface why THIS persona would NOT adopt, NOT pay, or would CHURN. "
        "Give CONCRETE, SPECIFIC objections, blockers and failure modes grounded in your lived context — "
        "name the actual friction, the real switching cost, the proof you'd need and don't have. Generic "
        "boilerplate ('it might be expensive') is useless; say what specifically breaks for YOU and why.")
    confirm = (
        "Confirming pass — argue the CASE FOR honestly from your lived context: what genuinely pulls you in, "
        "why you would adopt/pay. Stay anti-steering; only what is real for YOU.")
    if stance == "for":
        return confirm
    if stance == "both":
        return (against + "\n\n" + confirm +
                "\n\nRun BOTH directions on the SAME question so the case-for and case-against are comparable.")
    return against


def _render_roles_block(roles: dict[str, dict[str, str]],
                        personas: dict[str, dict[str, Any]]) -> str:
    """Render the explicit adversarial-role assignment so the roles are VISIBLE in the brief (a reviewer can
    see who must attack from which angle)."""
    lines = ["ADVERSARIAL ROLES — each persona must attack from their assigned lens:"]
    for pid, role in roles.items():
        who = (personas.get(pid) or {}).get("display_name") or pid
        lines.append(f"- {who} → {role['name']}: {role['lens']}")
    return "\n".join(lines)


def brief_red_team(project_id: str, prompt: str, persona_ids: list[str] | None = None,
                   filters: dict[str, Any] | None = None, count: int = 4, context: str | None = None,
                   stance: str = "against", artifact_ids: list[str] | None = None,
                   store: Store | None = None) -> dict[str, Any]:
    """Gather everything to run a host-authored RED-TEAM (falsification) over a research project's personas.
    It REFRAMES a normal council toward DISCONFIRMATION ("why would this segment NOT adopt / NOT pay /
    churn?") and assigns each persona an explicit, deterministic adversarial lens (skeptic / blocker /
    switching-cost / status-quo / risk) so concrete objections and failure modes get surfaced. Ground it in
    a REAL artifact with `artifact_ids` (a captured URL/price page/prototype). `stance` runs the SAME
    question in both directions: 'against' (default — case against), 'for' (confirming), or 'both'. Without
    persona_ids: returns candidate personas to select from. With persona_ids: returns each participant's
    loaded context (with its adversarial role stamped in) to author concrete objections, then call
    record_red_team."""
    store = store or Store()
    project = _require_research_project(store, project_id)
    stance = _normalize_stance(stance)
    artifact_briefs = council_artifact_briefs(project["id"], artifact_ids, store=store)
    artifacts_context = render_artifacts_context(artifact_briefs)
    reframing = _reframing(stance)
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
            "schema": "red_team_selection", "language": language, "project_id": project["id"],
            "prompt": prompt, "stance": stance, "artifacts": artifact_briefs,
            "roles": RED_TEAM_ROLES,
            "count": min(max(1, count), len(candidates)) if candidates else 0,
            "candidate_personas": candidates,
            "instructions": (
                "Pick a segment-DIVERSE panel that can attack the idea from many angles (cover the segments "
                "the idea serves AND the sceptics it doesn't). Then call brief_red_team again with "
                f"persona_ids=[...]; each persona will be assigned an adversarial lens. {language_instruction(language)}"
                if candidates else "No personas exist yet. Create some first."),
        }

    roles = _assign_roles(persona_ids)
    personas = {pid: store.get_persona(pid) for pid in persona_ids}
    personas = {pid: p for pid, p in personas.items() if p}
    roles_block = _render_roles_block({pid: roles[pid] for pid in personas}, personas)
    prior_themes = _prior_themes(store, project["id"])
    suggested_themes = [i.get("tag") for i in suggest_blocker_themes().get("items") or []]

    task_context = "\n\n".join(filter(None, [context or "", artifacts_context])) or None
    participants = []
    for pid in persona_ids:
        p = personas.get(pid)
        if not p:
            continue
        role = roles[pid]
        ctx = prepare_persona_agent_context(
            p["id"], f"Red-team prompt: {prompt}\nExternal context: {task_context or 'none'}", store=store)
        agent_context = (
            f"{ctx['agent_context']}\n\n=== RED-TEAM ({stance.upper()}) ===\n{reframing}\n\n"
            f"YOUR ADVERSARIAL LENS — {role['name']}: {role['lens']}")
        if artifacts_context:
            agent_context = f"{agent_context}\n\n=== ARTIFACTS ===\n{artifacts_context}"
        participants.append({
            "persona_id": p["id"], "display_name": p["display_name"],
            "segment": p.get("segment", {}), "soul_path": ctx["soul_path"],
            "role": {"id": role["id"], "name": role["name"], "lens": role["lens"]},
            "agent_context": agent_context,
        })
    return {
        "schema": "red_team", "language": language, "project_id": project["id"], "prompt": prompt,
        "stance": stance, "external_context": context, "artifacts": artifact_briefs,
        "roles": {pid: roles[pid] for pid in personas}, "roles_block": roles_block,
        "reframing": reframing, "participants": participants,
        "prior_themes": prior_themes, "suggested_themes": suggested_themes,
        "instructions": (
            "THE IDEA IS ON TRIAL. Each participant's agent_context ends with the disconfirmation reframing "
            "AND their assigned adversarial lens. For EACH persona author one or more `objections` = the "
            "CONCRETE, SPECIFIC reasons they would NOT adopt/pay or would churn — each {persona_id, theme (a "
            "short blocker label, e.g. 'switching cost', 'no proof', 'price'), text (the objection in their "
            "voice), severity ('low'|'medium'|'high'|'critical')}. Stay anti-steering and grounded: no "
            "boilerplate, quote the artifact / lived context. Also author each as a `statement` "
            "(about={kind:'prompt', id:'red_team'}, "
            "stance:{value -2..2, label?: support|conditional|neutral|skeptical|oppose}) so it renders "
            "in the transcript. "
            + ("Because stance='both', ALSO collect the case FOR (`endorsements`=[{persona_id, theme, text}]) "
               "so case-for and case-against sit side by side. " if stance == "both" else
               "Pass stance='both' to ALSO collect the case for (run the same question both directions). ")
            + "REUSE themes over inventing: pick a label from `prior_themes` (this project's earlier "
              "red-teams) or `suggested_themes` (common blocker families) when one fits — a new label only "
              "when none does, so one shared blocker is not fragmented across near-duplicates. "
            + "Then call record_red_team(project_id, prompt, objections=[...], endorsements=[...], statements="
            "[...], stance, exec_summary, summary). The server groups objections by theme (case/whitespace-"
            f"insensitive) into the structured case-against (count + worst severity); you author the prose. "
            f"{language_instruction(language)}"),
    }


_SEVERITY_RANK = {"low": 1, "medium": 2, "high": 3, "critical": 4}


def _theme_fold(theme: Any) -> str:
    """STRUCTURAL normalization only (case + whitespace) — 'Pricing'/'pricing ' must not split one blocker.
    No stemming/fuzzy matching: semantic merging is the host's job, never the server's guess."""
    return " ".join(str(theme or "").split()).casefold()


def _prior_themes(store: Store, project_id: str) -> list[str]:
    """The themes already recorded in THIS project's red-team sessions (case-against + case-for), newest
    first, fold-deduped. The brief hands them to the host so an existing theme gets REUSED instead of
    re-invented — near-duplicate labels fragment a shared blocker and demote it in the reach ranking."""
    seen: dict[str, str] = {}
    for c in store.list_council_sessions():   # newest-first (store orders by created_at DESC)
        rt = c.get("red_team")
        if not rt or c.get("project_id") != project_id:
            continue
        for case in (rt.get("case_against"), rt.get("case_for")):
            for t in (case or {}).get("themes") or []:
                seen.setdefault(_theme_fold(t.get("theme")), t.get("theme"))
    return list(seen.values())


def _norm_severity(value: Any) -> str:
    """Unknown tokens coerce to 'medium' — callers must keep the raw value inspectable (severity_raw)."""
    s = str(value or "").strip().lower()
    return s if s in _SEVERITY_RANK else "medium"


def _aggregate_case(items: list[dict[str, Any]], personas: dict[str, dict[str, Any]],
                    *, with_severity: bool) -> dict[str, Any]:
    """The DETERMINISTIC red-team math (no LLM): group objections (or endorsements) by `theme` into the
    structured case — for each theme, how many DISTINCT personas raise it, which personas, and (for
    objections) the worst severity. Themes are ranked by reach (personas raising), then severity, so the
    most-shared, most-severe blocker leads. Grouping keys are case/whitespace-folded (display keeps the
    first-seen casing) so trivially-identical labels cannot split a theme — and nothing more."""
    by_theme: dict[str, dict[str, Any]] = {}
    for it in items:
        pid = it.get("persona_id")
        theme = " ".join(str(it.get("theme") or it.get("label") or "other").split()) or "other"
        entry = by_theme.setdefault(_theme_fold(theme), {"theme": theme, "personas": [], "count": 0,
                                                         "items": [], "severity": "low"})
        if pid and pid not in entry["personas"]:
            entry["personas"].append(pid)
        item: dict[str, Any] = {"persona_id": pid, "text": str(it.get("text") or "").strip()}
        if with_severity:
            sev, raw = _norm_severity(it.get("severity")), str(it.get("severity") or "").strip()
            item["severity"] = sev
            if raw and raw.lower() not in _SEVERITY_RANK:   # coerced: keep the host's token inspectable
                item["severity_raw"] = raw
        entry["items"].append(item)
        if with_severity:
            if _SEVERITY_RANK[sev] > _SEVERITY_RANK[entry["severity"]]:
                entry["severity"] = sev
    for entry in by_theme.values():
        entry["count"] = len(entry["personas"])
        if not with_severity:
            entry.pop("severity", None)

    def _rank(e: dict[str, Any]) -> tuple:
        return (e["count"], _SEVERITY_RANK.get(e.get("severity", ""), 0) if with_severity else 0)

    themes = sorted(by_theme.values(), key=_rank, reverse=True)
    voices = {pid for it in items if (pid := it.get("persona_id")) in personas}
    worst = None
    if with_severity and themes:
        worst = max((t["severity"] for t in themes), key=lambda s: _SEVERITY_RANK[s])
    return {
        "themes": themes,
        "theme_count": len(themes),
        "voices": len(voices),
        "total": len(items),
        **({"worst_severity": worst, "top_blocker": themes[0]["theme"] if themes else None}
           if with_severity else {}),
    }


def _fragmentation_note(case: dict[str, Any]) -> str | None:
    """Visibility, never a gate: when most themes are single-persona, near-duplicate labels may have split
    a shared blocker and demoted it in the reach ranking — describe it, let the host decide. Purely
    structural (counts only); a single-voice session can't fragment, so it never trips this."""
    themes = case["themes"]
    singles = sum(1 for t in themes if t["count"] == 1)
    if case["voices"] < 2 or len(themes) < 4 or singles * 10 < len(themes) * 7:
        return None
    return (f"{len(themes)} themes, {singles} raised by a single persona — the case-against looks "
            "fragmented (near-duplicate labels like 'price'/'pricing' split one blocker's reach); "
            "consider re-recording with merged themes so shared blockers rank by their real reach.")


def record_red_team(project_id: str, prompt: str, objections: list[dict[str, Any]] | None = None,
                    endorsements: list[dict[str, Any]] | None = None, stance: str = "against",
                    persona_ids: list[str] | None = None, statements: list | None = None,
                    summary: str = "", exec_summary: str = "", selection_reason: str = "",
                    findings: list | None = None, key: str | None = None,
                    created_at: str | None = None, store: Store | None = None,
                    claims: list[dict[str, Any]] | None = None,
                    dispatch_token: str | None = None) -> dict[str, Any]:
    """Persist a host-authored RED-TEAM as a CouncilSession carrying a `red_team` block. The host passes the
    per-persona `objections` ([{persona_id, theme, text, severity}]) — the case AGAINST — plus the authored
    `statements` and prose exec_summary/summary. The SERVER deterministically groups objections by theme
    into the structured case-against (count of personas per blocker + worst severity) and stores it — a
    queryable result. With `stance='both'`, pass `endorsements` ([{persona_id, theme, text}]) to also store
    the case FOR side by side. Pass a stable `key` for a deterministic id (idempotent upsert)."""
    store = store or Store()
    project = _require_research_project(store, project_id)
    stance = _normalize_stance(stance)
    objs = [dict(o) for o in (objections or []) if o.get("persona_id")]
    ends = [dict(e) for e in (endorsements or []) if e.get("persona_id")]
    pids = persona_ids or list(dict.fromkeys(
        [o["persona_id"] for o in objs] + [e["persona_id"] for e in ends]))
    personas = {pid: store.get_persona(pid) for pid in pids}
    personas = {pid: p for pid, p in personas.items() if p}
    roles = _assign_roles(pids)

    case_against = _aggregate_case(objs, personas, with_severity=True)
    case_for = _aggregate_case(ends, personas, with_severity=False) if (stance == "both" or ends) else None

    # The red-team result is ALSO surfaced as a council finding so it is queryable next to other study
    # findings (the analytics/calibration seam). The verdict headlines the case against.
    top = case_against.get("top_blocker")
    verdict = (f"Case against: {case_against['theme_count']} blocker themes from {case_against['voices']} "
               f"personas; top blocker '{top}' (worst severity {case_against.get('worst_severity')})." if top
               else f"No substantive objections raised ({case_against['voices']} personas).")
    rt_finding = _artifacts.finding(verdict, kind="red_team",
                                    score={"blockers": case_against["theme_count"],
                                           "voices": case_against["voices"]},
                                    meta={"case_against": case_against, "case_for": case_for,
                                          "stance": stance})
    findings_in = list(findings or []) + [stamp_derived_finding(rt_finding, statements)]

    # One canonical prompt the objections hang off (id 'red_team') so each statement's about-ref resolves.
    rt_prompt = _artifacts.prompt(prompt, kind="proposal", id="red_team")

    session = record_council(
        project["id"], prompt, pids, statements=statements, proposal="",
        summary=summary, exec_summary=exec_summary,
        selection_reason=selection_reason or "red-team panel",
        prompts=[rt_prompt], findings=findings_in, key=key, created_at=created_at, store=store,
        claims=claims, dispatch_token=dispatch_token)

    session["red_team"] = {
        "stance": stance,
        "roles": {pid: roles[pid] for pid in personas},
        "objections": objs,
        "endorsements": ends,
        "case_against": case_against,
        "case_for": case_for,
        "recorded_at": utc_now_iso(),
    }
    store.insert_council_session(session)
    # Response-only (set AFTER the insert, so the stored record stays clean): advice to the host, not data.
    note = _fragmentation_note(case_against)
    if note:
        session["hints"] = [note]
    return session


def get_red_team(session_id: str, store: Store | None = None) -> dict[str, Any]:
    """One red-team result by council-session id — its stance, adversarial roles, per-persona objections and
    the deterministic case-against (and optional case-for). Raises if not a red-team."""
    store = store or Store()
    c = store.get_council_session(session_id)
    if not c:
        raise KeyError(f"Unknown council session: {session_id}")
    rt = c.get("red_team")
    if not rt:
        raise KeyError(f"Council {session_id} is not a red-team")
    return {"id": c["id"], "prompt": c["prompt"], "project_id": c.get("project_id", ""),
            "created_at": c["created_at"], **rt}


def is_red_team(council: dict[str, Any]) -> bool:
    """True when a council session carries a recorded red-team result (drives the UI branch)."""
    return bool(council.get("red_team"))
