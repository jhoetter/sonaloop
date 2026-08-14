from __future__ import annotations

import json
from typing import Any

from ..config import language_instruction


def build_profile_prompt(description: str, segment_hint: str | None = None, evidence: str | None = None, language: str | None = None) -> str:
    return f"""Create one authentic synthetic customer profile from the source description.

Return ONLY one JSON object with exactly these keys:
display_name: string
identity_traits: object
segment: object
demographics: object
role: object
company_context: object
goals: array of strings
constraints: array of strings
tool_ids: array of strings
tools: array of strings
relationships: array of objects {{name:string,type:string,friction:string}}
personality: object
pain_points: array of strings
success_criteria: array of strings

Rules:
- Derive the profile from the source description and evidence. Do not use shared stock defaults.
- identity_traits must include gender_presentation, gender_confidence, age_range, appearance_notes, avatar_profile, avatar_constraints.
- role must include title, responsibilities, seniority, decision_power.
- company_context must include industry, size, stack, operating_model.
- personality must include working_style, communication_style, risk_tolerance, character_notes.
- If a detail is not supported, mark it as unspecified or low-confidence in the relevant object.
- Make relationships, goals, constraints, pains, and personality specific to this person's actual work context.
- Do not infer interest in BIM, AI, automation, or any product direction unless source/evidence says so.
- Do not include vendor-friendly language. This is a lived customer profile, not a sales persona.
- tools must be only actual tools, media, channels, or recurring work surfaces mentioned or strongly implied.
- tool_ids must be lowercase stable slugs matching tools, e.g. "e_mail" for "E-Mail".
- Avoid slogans, repeated catchphrases, and generic consultant language.
- {language_instruction(language)} (proper names and tool names keep their real spelling).

Source description:
{description}

Segment hint:
{segment_hint or "none"}

Evidence:
{evidence or "none"}
"""


def build_consolidation_prompt(frame: dict[str, Any], language: str | None = None) -> str:
    return f"""You consolidate ONE simulated workday into persistent memory for a synthetic persona.

You are given the day's activities and the persona's currently known entities.
Return ONLY one JSON object with exactly these keys:
entities: array of {{mention:string, kind:one of [project,person,org,building,authority,topic], status:string|null, aliases:array of strings}}
facts: array of {{entity:string(mention), fact:string, status:string|null, valid_from:"YYYY-MM-DD", valid_to:string|null, importance:1-5, invalidates:string|null}}
threads: array of {{text:string, entity:string|null, action:one of [open,resolve], ref:string|null}}
event_links: array of {{activity_title:string, entities:array of strings(mention)}}

Rules:
- Extract the REAL entities the day touched (projects, people, authorities, buildings). Reuse existing names from known_entities verbatim when it is the same thing (avoid duplicates / aliases drift).
- A status/outcome (won, lost, delayed, in construction, approved, finished, …) is YOUR judgement from the day — never a fixed rule. Justify implausible jumps via the fact text.
- `valid_from` is the simulation date of the day (or earlier if the fact clearly started before). `valid_to` only if it definitively ended.
- `invalidates` = the prior fact text this fact supersedes (e.g. an old status), so it can be retired.
- threads: open NEW loops or resolve existing ones (ref = the loop text you are closing).
- Do not invent product interest / BIM / AI / automation adoption unless the day's evidence shows it.
- {language_instruction(language)} Match the persona's voice.

Frame:
{json.dumps(frame, indent=2, ensure_ascii=False)}
"""


def build_plan_prompt(frame: dict[str, Any], language: str | None = None) -> str:
    scope = frame.get("scope", "day")
    extra = (
        "Because this is a PERIOD plan, also pick `sample_days` (YYYY-MM-DD): the few "
        "representative days within the period worth simulating in detail (milestones, "
        "conflicts, and ordinary routine — not only drama)."
        if scope != "day" else
        "Because this is a DAY plan, `sample_days` should be just this one date."
    )
    return f"""You plan a synthetic persona's upcoming {scope} BEFORE simulation, using memory.

Return ONLY one JSON object with exactly these keys:
summary: string (the arc — what is interesting / at stake in this {scope})
intentions: array of strings (threads/projects to advance, foci)
expected_milestones: array of strings
mood_trajectory: string
sample_days: array of strings ("YYYY-MM-DD")

Rules:
- Ground the plan in the supplied active projects, open threads, recent digests, and world context.
- {extra}
- This is analysis, not narration: name what plausibly moves, what stays stuck, what is overdue.
- Do not steer the persona toward any product/tool adoption unless memory supports it.
- {language_instruction(language)}

Frame:
{json.dumps(frame, indent=2, ensure_ascii=False)}
"""


def build_digest_prompt(frame: dict[str, Any], language: str | None = None) -> str:
    return f"""You write a consolidated {frame.get('scope','period')} digest for a synthetic persona.

Return ONLY one JSON object with exactly these keys:
text: string (a compact narrative of what actually happened and where things stand)
themes: array of strings
project_arcs: array of {{name:string, arc:string}}
trends: array of strings (longer-running tendencies, e.g. workload, market, mood)

Rules:
- Summarize from the supplied days, facts, and threads. Capture arcs and trends, not every detail.
- Be honest about stalls and unresolved loops; do not invent progress or product enthusiasm.
- {language_instruction(language)}

Frame:
{json.dumps(frame, indent=2, ensure_ascii=False)}
"""


def build_persona_revision_prompt(frame: dict[str, Any], language: str | None = None) -> str:
    return f"""You propose SLOW, evidence-backed drift in a synthetic persona's identity.

Return ONLY one JSON object with exactly these keys:
rationale: string (why this drift is justified by consolidated facts — cite them)
effective_on: "YYYY-MM-DD"
refs: array of exact source objects {{kind: fact|digest|event|evidence, id: string}}
changes: object with optional keys:
  goals_add, goals_remove, constraints_add, constraints_remove,
  pains_add, pains_remove, tools_add, tools_remove: arrays of strings
  personality: object (partial overrides of working_style/communication_style/risk_tolerance/character_notes)
  notes: string

Rules:
- Change is the EXCEPTION, not the default. Inertia is realistic; most periods need little or no change.
- Every change must be justified by the supplied facts/digests — never from nothing — and
  every non-empty change set must carry at least one exact `refs` entry.
- Never drift the persona toward product/tool enthusiasm unless evidence forces it (and then say why).
- If nothing should change, return empty `changes` and say so in `rationale`.
- {language_instruction(language)}

Frame:
{json.dumps(frame, indent=2, ensure_ascii=False)}
"""


def build_eval_critic_prompt(frame: dict[str, Any], language: str | None = None) -> str:
    return f"""You are a strict quality critic for a synthetic persona simulation.
Judge the SAMPLE below against the persona's own SOUL and source description.

Return ONLY one JSON object with exactly these keys:
dimensions: object with integer 0-5 scores for each of:
  anti_steering        (5 = stays true to the brief; LOW if the persona drifts toward
                        unsupported enthusiasm/adoption of any tool/method/product not
                        in its source — judge against THIS persona's source, any industry)
  in_character         (consistency with SOUL personality/stance; a skeptic stays skeptical)
  dialogue_believability (conversations sound real and specific, not generic)
  arc_plausibility     (project status/time progressions are realistic)
  mundane_balance      (enough ordinary routine/friction, not constant drama)
findings: array of short strings (what is good / what is off)
flagged_items: array of {{ref_id:string, dimension:string, issue:string, severity:1-5}}
  (ref_id = an event/fact id from the sample that evidences the problem)
overall_note: string

Rules:
- Be specific and skeptical. Cite ref_ids in flagged_items.
- anti_steering is the priority: any ungrounded product/method drift => low score + flag.
- Do not reward vendor-friendly narratives; reward honest, ordinary, in-character work.
- The acceptance bar is {frame.get("threshold", 4)}/5 per dimension: any dimension below
  it marks the run as not "top". Score honestly against that bar.
- {language_instruction(language)}

Frame (persona source, SOUL, sampled activities with ids, project arcs, digests):
{json.dumps(frame, indent=2, ensure_ascii=False)}
"""


def build_cohort_critic_prompt(frame: dict[str, Any], language: str | None = None) -> str:
    return f"""You are a quality critic comparing a COHORT of synthetic personas against
each other (not against their own brief). Find the personas that fall OUT of the
cohort's range.

You are given a compact profile per persona (source, segment, role, pains, and — when
available — its per-persona critic dimensions and a couple of sample utterances).

Return ONLY one JSON object with exactly these keys:
outliers: array of {{persona_id:string, persona_name:string, reason:string,
  dimension:string (one of: believability | consistency | distinctiveness | tone | range),
  severity:1-5}}
  Include a persona ONLY if it genuinely stands out from the others — e.g. it reads as
  far less believable/consistent than its peers, or it is a near-clone that contributes
  no distinct perspective. An empty list is a valid, good result.
cohort_note: string (one paragraph: is the cohort balanced and diverse, or skewed?)

Rules:
- Judge RELATIVE to the cohort, not against an absolute ideal.
- Do not invent problems to fill the list; flag only real outliers.
- Distinctiveness matters: two interchangeable personas are an outlier pair, not a strength.
- {language_instruction(language)}

Cohort frame (one compact record per persona):
{json.dumps(frame, indent=2, ensure_ascii=False)}
"""


def build_evidence_check_prompt(frame: dict[str, Any], language: str | None = None) -> str:
    return f"""Compare a SYNTHETIC persona profile against attached REAL evidence.

Return ONLY one JSON object with exactly these keys:
confirmed: array of strings (profile claims the evidence supports)
contradicted: array of {{claim:string, evidence_says:string}}
unsupported: array of strings (profile claims with no evidence either way — stay assumptions)
notes: string

Rules:
- Judge goals, pain_points, tools, constraints, relationships against the evidence only.
- Be conservative: only 'confirmed' when the evidence clearly supports it.
- 'contradicted' must quote what the evidence actually says.
- Do not invent evidence. If evidence is thin, most claims are 'unsupported'.
- {language_instruction(language)}

Frame (profile claims + attached evidence):
{json.dumps(frame, indent=2, ensure_ascii=False)}
"""


def build_synthesis_outline_prompt(frame: dict[str, Any], language: str | None = None) -> str:
    return f"""You are writing a REPORT over a whole research PROJECT: a graph of studies
(each study = a council chain consolidated into a synthesis). Derive the report's OUTLINE
from the graph — its themes and dependency edges — not from a fixed template.

Return ONLY one JSON object with exactly these keys:
build_order_narrative: string (how the understanding was BUILT over time — read the studies
  in creation order and describe the trajectory: what was asked first, what each answer spawned)
sections: array of objects {{heading:string, theme_tags:array of strings,
  source_study_ids:array of strings (the study ids this section draws on — use ids from the frame),
  intent:string (one line: what this section establishes)}}
  Organize by THEME/logic (cluster studies by theme + dependency), NOT by chronology. Always
  include three cross-cutting sections somewhere: one for how-understanding-was-built (trajectory),
  one for tensions & deliberate non-targets, and one for the open frontier (unresolved questions).

Rules:
- Derive structure from the actual graph (themes, edges, build order in the frame). Different
  graphs must yield different outlines.
- Every section's source_study_ids must be real ids present in the frame.
- {language_instruction(language)}

Project graph frame (project, nodes with themes/sentiment, edges, build order, open questions,
and each study's compact content):
{json.dumps(frame, indent=2, ensure_ascii=False)}
"""


def build_synthesis_section_prompt(frame: dict[str, Any], language: str | None = None) -> str:
    return f"""You are authoring ONE section of a research report. Write it grounded in the
source studies provided — every load-bearing claim must cite a study (and, where possible, the
council inside it).

Return ONLY one JSON object with exactly these keys:
markdown: string (the section body in Markdown; clear, concise, honest — preserve dissent and
  non-targets where relevant; do not invent consensus)
citations: array of objects {{study_id:string, council_id:string (may be empty), quote:string}}
  (the provenance behind the section's claims; use study ids/council ids from the frame)

Rules:
- Ground every claim; a section with zero citations is wrong. Use only ids present in the frame.
- {language_instruction(language)}

Section frame (heading + intent + the full content of the source studies + their councils):
{json.dumps(frame, indent=2, ensure_ascii=False)}
"""


def build_synthesis_prompt(frame: dict[str, Any], language: str | None = None) -> str:
    return f"""You synthesize an ordered CHAIN of councils (a study arc) into cross-council learnings.
This is like the meta-analysis over several iterations of user studies.

Return ONLY one JSON object with exactly these keys:
arc_narrative: string (the trajectory: what we started with -> how positions/sentiment evolved across the councils in order -> where we landed)
gesamtbild: string (the overall picture)
handlungsempfehlungen: array of {{text, aufwand (1-5), nutzen (1-5)}} (prioritized actions on an effort/value matrix; plain strings also accepted, then unscored)
positionierung: string (positioning statement(s) implied by the evidence)
pain_solvers: array of strings (the validated pains/delight-engines the product addresses)
segmente: array of objects {{segment:string, stance:string, why:string}} (who to win, who is a deliberate non-target)
offene_fragen: array of strings (open questions / what to study next)
references: array of objects {{council_id:string, role:string}} (each council's role in the arc)
citations: array of objects {{kind:"evidence"|"recall"|"council", ref:string, quote:string}}
  (inline provenance for the load-bearing conclusions: when a pain_solver / positionierung /
  recommendation rests on attached real EVIDENCE or a specific RECALLed fact, cite it here using
  the ids from frame.provenance; council quotes use kind="council" + the council_id. May be empty.)
voices: array of objects, ONE per persona that appears in the chain — the structured per-persona record:
  {{persona_id:string, persona_name:string, segment:string (which segment from `segmente` they belong to),
    sentiment: one of "positiv"|"bedingt"|"neutral"|"skeptisch"|"ablehnend",
    relevance: one of "stark"|"teilweise"|"kaum"|"irrelevant" (how much the topic touches THEIR work),
    key_argument:string (the ONE-LINE reason WHY they hold this stance — the single most important point, in their voice),
    shift: object {{from:string, to:string, trigger:string, council_id:string}} OR null
      (ONLY if their stance moved across the chain — e.g. neutral->positiv — with the concrete argument/feature that moved them and the council where it happened),
    evidence: array of objects {{council_id:string, quote:string}} (1-3 grounded quotes from that persona's turns/votes)}}
status: "in_progress" | "done"  (is the study arc finished, given the goal?)
next_council_question: string (ONLY if status=in_progress: the SELF-CONTAINED question to run as the next council — see rule below; else "")
stop_reason: string (ONLY if status=done: why you stop — goal reached / no productive follow-up / max councils)

Rules:
- Capture the PROGRESSION, do not flatten: how did sentiment/positions change across the ordered councils?
- Keep every conclusion traceable to a council (use references; mention which council a learning came from).
- Be honest: preserve who stays neutral/negative and why that is fine; do not invent consensus or product enthusiasm.
- PROVENANCE: prefer conclusions you can ground. Where `frame.provenance` offers attached evidence or
  recalled facts that back a pain_solver / positioning / recommendation, cite them in `citations`. Never
  fabricate a citation ref — only use ids present in the frame.
- VOICES: author one voice per distinct persona across the chain. `key_argument` must be the persona's
  actual point (grounded in their turns/votes), not a generic label. Set `shift` ONLY when the evidence shows
  a real change of stance across councils; otherwise null. `relevance` reflects how much the topic touches the
  persona's own work — independent of whether they like the product (a skeptic can have relevance "stark").
  `sentiment` and `relevance` are independent axes. Use the persona_id/persona_name exactly as in the frame.
- ITERATION DECISION (driver loop): given the `goal`, decide whether ANOTHER council
  would yield materially new insight. If yes → status="in_progress" and write
  `next_council_question` as a **fully self-contained** prompt: the personas are
  STATELESS across councils and remember nothing, so it must include all needed
  context (the product briefing essentials + the precise new angle) to stand alone.
  If the goal is reached or follow-ups would only repeat → status="done" + stop_reason.
- {language_instruction(language)}

Frame (start input + the councils in order with exec_summaries, per-persona turns and votes — use the turns/votes to author `voices`):
{json.dumps(frame, indent=2, ensure_ascii=False)}
"""
