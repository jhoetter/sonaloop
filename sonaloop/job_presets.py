"""Job presets + the "sharpen the question" helper — the JOB layer of the taxonomy, made real.

A **job preset** is a thin recipe card derived ENTIRELY from the canonical taxonomy
(`taxonomy.json` via `job_taxonomy` — nothing here re-declares the mapping): for a named
research Job it picks the Framework, suggests the Formats, and declares the persona coverage,
so the preset can SEED a plan (`services.start_job_study`). Presets are starting recipes, not
constraints — swappable, editable, never enforced. The general framework+format engine
(`start_project` with any methodology) still cooks anything off-menu.

The **"sharpen the question" helper** is deterministic/structural (NO server-side text-LLM
call, per the architecture): it inspects a fuzzy goal, returns the checklist of what a
well-formed study needs (decision at stake, audience, comparator, success signal), targeted
clarifying questions for the missing pieces, matches the goal to likely Job presets via
transparent keyword signals, and emits a structured study spec. The HOST agent does all the
language work — asking the user, filling the answers, confirming the match — and calls back
with `answers=`; think "interactive form the host drives", not NLP magic.
"""
from __future__ import annotations

from typing import Any

from . import job_taxonomy as _T


# ----------------------------------------------------------------------------------- presets

# Format id → the MCP gather/write-back pair that RUNS it. The only knowledge added on top of
# the taxonomy (which names the tools only in prose); everything else is read from taxonomy.json.
FORMAT_TOOLS: dict[str, dict[str, str]] = {
    "council": {"brief": "brief_council", "record": "record_council"},
    "prototype_test": {"brief": "brief_prototype_session", "record": "record_prototype_session"},
    "head_to_head": {"brief": "brief_head_to_head", "record": "record_head_to_head"},
    "red_team": {"brief": "brief_red_team", "record": "record_red_team"},
}

PRESET_NOTE = ("Starting recipe, not a constraint: swap the framework, drop or add formats, adjust "
               "the coverage — the general framework+format engine (start_project with any "
               "methodology) still runs anything off-menu.")


def job_presets(store: Any | None = None) -> list[dict[str, Any]]:
    """One preset per taxonomy Job, in taxonomy order — each a recipe card that seeds a plan:
    the default Framework (full plain-language description), the suggested Formats (each with
    its brief/record MCP tools), and the declared persona coverage. Derived from the canonical
    taxonomy at call time, so presets can never drift from the website's Jobs."""
    descs = {d["id"]: d for d in _T.framework_descriptions(store)}
    fmts = {f["id"]: f for f in _T.formats()}
    presets: list[dict[str, Any]] = []
    for job in _T.jobs():
        presets.append({
            "schema": "job_preset",
            "id": job["id"],
            "name": job["name"],
            "sells_as": job["sells_as"],
            "user_question": job["user_question"],
            "framework": descs[job["default_framework"]],
            "framework_options": list(job["frameworks"]),
            "formats": [{
                "id": fid,
                "name": fmts[fid]["name"],
                "definition": fmts[fid]["definition"],
                "tools": dict(FORMAT_TOOLS.get(fid, {})),
            } for fid in job["formats"]],
            "coverage": dict(job["coverage"]),
            # The Job's run discipline (e.g. ab_test: variants frozen up front, hypothesis before
            # exposure, randomized order, forced preference, segmented verdict) rides into the
            # preset verbatim so the host sees the protocol where it plans the run.
            **({"protocol": dict(job["protocol"])} if job.get("protocol") else {}),
            "note": PRESET_NOTE,
        })
    return presets


def get_job_preset(job_id: str, store: Any | None = None) -> dict[str, Any]:
    """One Job preset by stable taxonomy id (e.g. 'positioning'). Raises KeyError if unknown."""
    for preset in job_presets(store):
        if preset["id"] == job_id:
            return preset
    raise KeyError(f"No taxonomy job '{job_id}'")


# ------------------------------------------------------------------- sharpen the question

# What a WELL-FORMED study needs — the checklist the helper walks a fuzzy goal through. Each
# field carries the targeted clarifying question the host asks the user and the reason it
# matters, so "sharpening" is a structured form, not prose generation.
QUESTION_CHECKLIST: list[dict[str, str]] = [
    {"id": "decision", "label": "Decision at stake",
     "question": "What decision will the answer change — what will you do differently depending on the result?",
     "why": "A study that changes no decision is not worth running; the decision anchors what 'answered' means."},
    {"id": "audience", "label": "Audience",
     "question": "Whose reaction decides it — which segment(s) must the persona panel cover?",
     "why": "The persona coverage (who sits in the council) follows directly from this."},
    {"id": "comparator", "label": "Comparator / alternative",
     "question": "Compared to WHAT — the status quo, a competitor, another variant or price point?",
     "why": "Preferences only mean something against an explicit alternative (a head-to-head needs two options)."},
    {"id": "success_signal", "label": "Success signal",
     "question": "What observable signal counts as a clear answer — a preference margin, a recurring objection theme, a stated willingness to pay?",
     "why": "Without a signal to look for, the run cannot converge — the verify gate has nothing to judge."},
]
_FIELD_IDS = [f["id"] for f in QUESTION_CHECKLIST]

# Per-field structural CUES: substrings whose presence in the goal HINTS the field may already
# be in there (the clarifying question becomes a confirmation). Hints only — never auto-filled
# as answers; the host confirms with the user.
_FIELD_CUES: dict[str, list[str]] = {
    "decision": ["should we", "should i", "decide", "whether", "launch", "kill", "invest", "go/no-go"],
    "audience": ["customer", "user", "buyer", "segment", "audience", "founder", "developer",
                 "team", "smb", "enterprise", "persona"],
    "comparator": [" vs ", " vs. ", " versus ", "compare", "compared", "against", "instead of",
                   "alternative", "competitor"],
    "success_signal": ["sign up", "signup", "convert", "willing to pay", "prefer", "retention",
                       "margin", "objection"],
}

# Per-Job keyword SIGNALS for the deterministic preset match: a job scores one point per signal
# found in the lowercased goal. Transparent (matched terms are returned) and never forced — an
# unmatched goal simply stays off-menu and runs through the general engine.
_JOB_SIGNALS: dict[str, list[str]] = {
    "positioning": ["positioning", "position", "value prop", "differentiat", "messaging",
                    "stand out", "against whom", "competitor", "land"],
    "pricing": ["pricing", "price", "charge", "willing to pay", "willingness to pay", "tier",
                "per month", "/mo", "expensive", "cheap"],
    "jtbd_demand": ["demand", "jtbd", "job to be done", "jobs to be done", "hire", "would anyone",
                    "want this", "need this", "use case"],
    "ideation_hmw": ["how might we", "hmw", "ideate", "ideation", "brainstorm", "idea",
                     "what could we build", "concept"],
    "continuous_discovery": ["continuous", "cadence", "weekly", "every week", "ongoing",
                             "learn next", "discovery loop", "regularly"],
    "churn_reasons": ["churn", "leaving", "cancel", "retention", "stop using", "switched away",
                      "win back"],
    "ab_test": ["a/b test", "ab test", "a/b-test", "split test", "variant", "which version",
                "version a", "two versions", "which wins", "winner"],
    "content_reaction": ["blog post", "copy", "wording", "headline", "messaging", "landing page",
                         "react to", "reaction", "how does it land", "tone", "does this read",
                         "first impression", "comprehen"],
}


def match_jobs(goal: str) -> list[dict[str, Any]]:
    """Rank the taxonomy Jobs a fuzzy goal likely belongs to — deterministic keyword scoring,
    ties broken by taxonomy order. Each match carries the terms that fired, so the host can
    show the user WHY a preset was suggested. Empty when nothing fires (off-menu is fine)."""
    goal_l = (goal or "").lower()
    order = [j["id"] for j in _T.jobs()]
    names = {j["id"]: j["name"] for j in _T.jobs()}
    scored = []
    for jid in order:
        terms = [s for s in _JOB_SIGNALS.get(jid, []) if s in goal_l]
        if terms:
            scored.append({"job": jid, "name": names[jid], "score": len(terms), "matched": terms})
    return sorted(scored, key=lambda m: (-m["score"], order.index(m["job"])))


def sharpen_question(goal: str, answers: dict[str, str] | None = None, job: str | None = None,
                     store: Any | None = None) -> dict[str, Any]:
    """Turn a fuzzy goal into a well-formed study spec — deterministically (no text-LLM call).

    Inspects `goal` against the well-formed-study checklist (decision at stake, audience,
    comparator, success signal): per field it reports the host-provided `answer`, any structural
    `hints` found in the goal, and a status (answered|hinted|missing). Unanswered fields become
    targeted `clarifying_questions` the host asks the user; call again with
    `answers={field_id: answer}` until `ready`. The goal is also matched to likely Job presets
    (keyword signals, transparent + overridable via `job=`); the resulting `study_spec` carries
    the matched preset's framework/formats/coverage — or stays off-menu (job=None) and runs
    through the general engine. The host authors all language; this is the structured form."""
    goal = (goal or "").strip()
    if not goal:
        raise ValueError("sharpen_question needs a goal (the fuzzy research question)")
    answers = {k: str(v).strip() for k, v in (answers or {}).items() if str(v or "").strip()}
    unknown = sorted(set(answers) - set(_FIELD_IDS))
    if unknown:
        raise ValueError(f"unknown answer fields {unknown} — the checklist fields are {_FIELD_IDS}")
    goal_l = goal.lower()

    checklist = []
    for f in QUESTION_CHECKLIST:
        ans = answers.get(f["id"])
        hints = [c.strip() for c in _FIELD_CUES[f["id"]] if c in goal_l]
        status = "answered" if ans else ("hinted" if hints else "missing")
        checklist.append({**f, "answer": ans, "hints": hints, "status": status})
    clarifying = [{"field": e["id"], "question": e["question"], "hints": e["hints"]}
                  for e in checklist if e["status"] != "answered"]
    ready = not clarifying

    if job:
        try:
            preset = get_job_preset(job, store)
        except KeyError:
            raise ValueError(f"unknown job '{job}' — list_job_presets() names the valid ids")
        matches = [{"job": preset["id"], "name": preset["name"], "score": None, "matched": ["explicit"]}]
    else:
        matches = match_jobs(goal)
        preset = get_job_preset(matches[0]["job"], store) if matches else None

    study_spec = {
        "schema": "study_spec",
        "goal": goal,
        "job": preset["id"] if preset else None,
        "framework": preset["framework"]["id"] if preset else None,
        "formats": [f["id"] for f in preset["formats"]] if preset else [],
        "coverage": preset["coverage"] if preset else None,
        "fields": {fid: answers.get(fid) for fid in _FIELD_IDS},
        "ready": ready,
        "off_menu": preset is None,
    }
    if not ready:
        nxt = ("Ask the user the clarifying_questions (you author the language), then call "
               "sharpen_question again with answers={field_id: answer} until ready.")
    elif preset:
        nxt = (f"start_job_study(job_id='{preset['id']}', title=…, goal=…) seeds the plan from the "
               f"preset (framework '{preset['framework']['id']}'; override framework= freely), then "
               f"assess_coverage(project, job='{preset['id']}') checks the panel against the "
               "declared coverage.")
    else:
        nxt = ("No preset matched — run it through the general engine: "
               "start_project(title, goal, methodology=<any framework key>).")
    return {"schema": "sharpen_question", "goal": goal, "checklist": checklist,
            "clarifying_questions": clarifying, "job_matches": matches, "preset": preset,
            "study_spec": study_spec, "ready": ready, "next": nxt}
