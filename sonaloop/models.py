from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


Json = dict[str, Any]


@dataclass
class Persona:
    id: str
    slug: str
    display_name: str
    source_description: str
    provenance: Json
    identity_traits: Json
    segment: Json
    demographics: Json
    role: Json
    company_context: Json
    goals: list[str]
    constraints: list[str]
    tool_ids: list[str]
    tools: list[str]
    relationships: list[Json]
    personality: Json
    pain_points: list[str]
    success_criteria: list[str]
    avatar: Json | None
    soul: Json | None
    created_at: str
    updated_at: str
    # Capability profile — which session fidelities this persona can be simulated at + how it
    # actually moves through an interface: {rungs:{see,walk,drive,login}, tech_comfort: 1-5
    # (vocabulary: suggestions/tech_comfort.json), devices:[…], accessibility: str,
    # provenance: authored|derived|evidence}. None = never declared: reads return a DERIVED
    # profile (services/_personas.capability_profile) without rewriting the stored persona.
    capabilities: Json | None = None

    def to_dict(self) -> Json:
        return asdict(self)


@dataclass
class CalendarEvent:
    id: str
    persona_id: str
    start: str
    end: str
    title: str
    participants: list[str]
    location_or_tool: str
    intent: str
    outcome: str
    created_at: str

    def to_dict(self) -> Json:
        return asdict(self)


@dataclass
class ExperienceEvent:
    id: str
    persona_id: str
    timestamp: str
    event_type: str
    summary: str
    task: str
    tool: str
    participants: list[str]
    collaboration_mode: str
    what_happened: str
    conversation: list[Json]
    key_quotes: list[str]
    actions_done: list[str]
    artifacts_touched: list[str]
    persona_thought: str
    decision: str | None
    open_loops: list[str]
    impact: Json
    pain_points: list[str]
    goal_refs: list[str]
    calendar_event_id: str | None
    created_at: str

    def to_dict(self) -> Json:
        return asdict(self)


@dataclass
class DailySummary:
    id: str
    persona_id: str
    date: str
    mood: str
    completed: list[str]
    blockers: list[str]
    open_loops: list[str]
    pain_points: list[str]
    notable_memories: list[str]
    created_at: str

    def to_dict(self) -> Json:
        return asdict(self)


@dataclass
class Reflection:
    id: str
    persona_id: str
    period_start: str
    period_end: str
    summary: str
    themes: list[str]
    pain_points: list[str]
    created_at: str

    def to_dict(self) -> Json:
        return asdict(self)


@dataclass
class PainPointObservation:
    id: str
    persona_id: str
    issue: str
    severity: int
    frequency: int
    evidence_event_ids: list[str]
    affected_workflow: str
    opportunity: str
    created_at: str

    def to_dict(self) -> Json:
        return asdict(self)


@dataclass
class CouncilSession:
    id: str
    prompt: str
    persona_ids: list[str]
    selection_reason: str
    proposal: str
    votes: list[Json]            # formal decision votes — kept (drives council mode + the vote tally)
    summary: str
    created_at: str
    exec_summary: str = ""  # rich markdown synthesis shown in the UI
    # `questions`: the OPEN, conversational user-research questions a DISCOVERY council asked
    # ("Welche Versicherungen hast du? Wie sparst du gerade?"). When present (and proposal/votes empty)
    # the council is a discovery conversation, not a hypothesis-and-vote. Mode is DERIVED from these
    # three fields — see council_mode() (spec/methodology-and-clarity-redesign.md Q1/Q2).
    questions: list[str] = field(default_factory=list)
    # A council is a research artefact and is ALWAYS scoped to a research project
    # (spec/research-graph-and-meta-report.md §4-5: personas are global, but studies/
    # councils/reports are encapsulated at the Project level). Enforced at creation.
    project_id: str = ""
    # Unified primitives (spec/unified-artifact-schema.md) — native shape, optional during the
    # transition. When present the renderers/adapters prefer them over turns/votes/questions.
    statements: list = field(default_factory=list)
    findings: list = field(default_factory=list)
    prompts: list = field(default_factory=list)

    def to_dict(self) -> Json:
        return asdict(self)


@dataclass
class Synthesis:
    """A Report — folds inputs into a structured, presentation-grade document (spec/unified-synthesis-
    report.md). ONE concept; `scope` is an internal property, never a separate identity.
    scope="convergence" = a methodology graph node over councils (the structured layer: findings → 2×2);
    scope="project" = a cross-graph hand-off document (the narrative layer: sections + figures). The two
    layers compose; one renderer and one export (md/pdf) serve every scope. (Named `Synthesis` in
    code/storage; shown as "Report" in the UI.)"""
    id: str
    title: str
    start_input: str
    council_ids: list[str]
    arc_narrative: str
    gesamtbild: str
    positionierung: str
    references: list[Json]
    created_at: str
    goal: str = ""                       # what this study arc is trying to learn
    status: str = "done"                 # in_progress | done
    next_council_question: str = ""      # self-contained Q for the next council (if continuing)
    stop_reason: str = ""                # why the loop stopped (goal reached / no follow-up / max)
    iterations: int = 0                  # councils consumed so far
    citations: list[Json] = field(default_factory=list)  # inline provenance: [{kind, ref, quote}]
    # --- methodology-engine metadata (spec/methodology-engine-and-prototyping.md) ---
    phase: str = ""          # which constellation step produced this node (step id, e.g. "discover")
    mode: str = ""           # display label: "diverge" (one of a fan) | "converge" (the waist)
    role: str = ""           # free role tag (= the step's produces.role)
    methodology: str = ""    # methodology key this node belongs to
    # Unified primitives (spec/unified-artifact-schema.md) — the ONE representation. findings carry the
    # former key_problems/pain_solvers/recommendations/clusters/segmente/ranking/shortlist/offene_fragen;
    # statements carry the former per-persona voices; prompts the study question.
    statements: list = field(default_factory=list)
    findings: list = field(default_factory=list)
    prompts: list = field(default_factory=list)
    # --- scope + narrative document layer (spec/unified-synthesis-report.md) ---
    scope: str = "convergence"           # convergence (graph node) | project (report) | custom
    project_id: str = ""                 # set for scope=project reports (which project they summarise)
    lead: str = ""                       # the report lead paragraph
    sections: list = field(default_factory=list)   # [{id, heading, markdown, citations, figures,
    #                                                   theme_tags, source_study_ids, intent}]
    graph_snapshot: Json = None          # project-scope keeps the graph it summarised

    def to_dict(self) -> Json:
        return asdict(self)


@dataclass
class ResearchProject:
    """A research container: a themed GRAPH of studies (syntheses) plus the
    personas in scope. Distinct from a persona's memory `project` entity."""
    id: str
    slug: str
    title: str
    goal: str
    description: str
    persona_ids: list[str]
    study_ids: list[str]
    study_tags: Json            # {study_id: [theme tag, ...]} (LLM-assigned, not fixed)
    themes: list[str]           # the theme vocabulary that emerged
    status: str
    created_at: str
    updated_at: str
    # --- methodology-engine binding (spec/methodology-engine-and-prototyping.md) ---
    methodology: str = ""       # methodology key, "" = freeform project
    phase: str = ""             # primary ready step id (display), or "__complete__"
    phase_log: Json = field(default_factory=dict)
    # phase_log: {step_id: {status, node_ids:[], decision_node_id?, decided_at?}}
    #   (tag-driven constellation; spec/methodology-constellations.md)
    # --- Sections: methodology-INDEPENDENT overlay groupings of graph nodes
    #   (spec/sections-and-composable-graph.md). A list of Section dicts; pure views over
    #   nodes (reference, not containment). Old projects default to [] on read. ---
    sections: Json = field(default_factory=list)
    # --- Notes: lightweight first-class observation nodes (the atomic unit for affinity),
    #   creatable without any methodology. List of {id,title,text,created_at}. ---
    notes: Json = field(default_factory=list)
    # --- Councils belonging to this project. A council is created INSIDE a project and
    #   later folded into a synthesis (study). Tracked here so the project owns its
    #   councils directly, even before a synthesis cites them. Old projects default to []. ---
    council_ids: Json = field(default_factory=list)
    # Immutable snapshot of the authenticated server request that first created the project.
    # None/missing is the honest legacy/local value; never infer it from later editors or tool text.
    created_by: Json | None = None

    def to_dict(self) -> Json:
        return asdict(self)


@dataclass
class Section:
    """A methodology-independent, labeled overlay grouping a SET of graph nodes by id.

    A Section is a VIEW, not a container: it references nodes by id and never owns/moves/mutates
    them (reference, not containment). Membership is explicit + set-based (overlap allowed); the
    on-canvas geometry is DERIVED from member node bounds at render time, never stored. `kind` is an
    OPEN tag (e.g. "theme" | "phase" | invented) resolved for display via presentation/suggestions
    — no hardcoded vocabulary. See spec/sections-and-composable-graph.md.
    """
    id: str
    project_id: str
    title: str
    kind: str = "theme"
    member_ids: list[str] = field(default_factory=list)
    parent_id: str | None = None
    order: int = 0
    presentation: Json | None = None
    note: str = ""
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> Json:
        return asdict(self)


# NOTE: the old StudyEdge model is retired — project-graph edges are DERIVED (from the plan DAG +
# cross-references, spec/artifact-cross-references.md), never stored as edge records.


@dataclass
class OpenQuestion:
    """A promotable open question raised by a study — a first-class graph node
    that a later study can `answers`."""
    id: str
    project_id: str
    study_id: str | None
    text: str
    status: str                 # open|being_studied|answered|dropped
    created_at: str

    def to_dict(self) -> Json:
        return asdict(self)


@dataclass
class MethodologyJudgment:
    """An LLM-made, evidence-backed decision at a methodology gate. The engine
    requires its PRESENCE (you can't converge without a divergence_complete) but
    never dictates its content or a number."""
    id: str
    project_id: str
    phase_key: str              # the step id the judgment is recorded against
    kind: str                   # the gate_tag — a FREE tag (e.g. divergence_complete, loop_back, …)
    decided: bool
    rationale: str
    evidence_refs: list[str]    # council_id | synthesis_id | session_id
    created_at: str

    def to_dict(self) -> Json:
        return asdict(self)


@dataclass
class Prototype:
    """A real, minimal, locally-runnable app artifact (versioned)."""
    id: str
    slug: str
    project_id: str | None
    name: str
    version: str
    kind: str                   # web
    path: str                   # prototypes/<slug>/
    entry: str                  # index.html or entry file
    run: str                    # static | node | python
    run_cmd: str | None
    notes: str
    created_at: str
    fidelity: str = "midfi"     # compatibility discriminator (now just one of `tags`)
    type: str = "prototype"     # free artifact-type tag (spec/methodology-presentation-from-data.md)
    tags: list[str] = field(default_factory=list)  # free discriminator/extra tags (e.g. fidelity)

    def to_dict(self) -> Json:
        return asdict(self)


@dataclass
class PrototypeSession:
    """A persona's recorded use of a prototype (Playwright session), with the
    observed-state evidence the reaction is grounded in.

    SUPERSEDED by UsabilitySession (the durable, replayable per-step trace) for new
    recordings — kept working for back-compat (existing records, record_prototype_session)."""
    id: str
    persona_id: str
    prototype_id: str
    session_id: str
    date: str
    reaction: Json
    observed_state_refs: list[str]
    created_at: str
    statements: list = field(default_factory=list)   # unified primitive (spec/unified-artifact-schema.md)

    def to_dict(self) -> Json:
        return asdict(self)


@dataclass
class UsabilitySession:
    """The durable, replayable usability-session trace — THE SESSION IS THE DELIVERABLE, not a
    summary of it. One schema serves all three fidelity rungs (artifact flow → prototype → live
    browser); only the fidelity of each step's `state` changes. Supersedes PrototypeSession for
    new recordings.

    steps: the ordered dual timeline — each step is
      {index, action:{type,target,detail}, monologue, state:{url?,title?,screen,screenshot?},
       friction:{level,note}, verdict:{would_continue,reason}}
    (friction levels are data-driven via suggestions/friction_levels.json; screenshots live under
    data/sessions/<id>/step-<index>.png). `outcome` is {completed, dropoff_step, summary,
    predicted_behaviors}; `statements` are the unified primitives, whose session refs
    ({kind:'session', id, anchor:'step:<index>'}) are validated against existing steps."""
    id: str
    project_id: str
    persona_id: str
    date: str
    subject: Json                # {kind: flow|prototype|live_url, id?, url?, label}
    fidelity: str                # artifact | prototype | live
    steps: list[Json]
    outcome: Json
    created_at: str
    statements: list = field(default_factory=list)   # unified primitive (spec/unified-artifact-schema.md)

    def to_dict(self) -> Json:
        return asdict(self)


@dataclass
class Survey:
    """An outbound survey instrument — the first artifact that COLLECTS data instead of presenting
    it. Authored from simulation findings (open questions, contested council stances) via
    brief_survey → record_survey, exported as a sendable static HTML form (export_survey), and the
    real responses flow back through import_survey_responses as calibration evidence.

    questions: [{id, text, kind (single|multi|scale|text), options[], stance_mapped}] —
    `stance_mapped` scale questions map their options onto suggestions/stance_scale.json so real
    answers are directly comparable to persona stances (the predicted-vs-actual strip).
    derived_from: Ref[] — the synthesis findings / open questions / council prompts this instrument
    operationalizes (validated to resolve on record)."""
    id: str
    slug: str
    project_id: str
    title: str
    intro: str
    status: str                  # draft | open | closed
    questions: list[Json]
    derived_from: list[Json]
    created_at: str
    updated_at: str

    def to_dict(self) -> Json:
        return asdict(self)


@dataclass
class SurveyResponse:
    """One real human's answers to a Survey — its OWN table row, never embedded in the survey
    document (response counts grow unbounded). `respondent_key` is an opaque token (no PII);
    `answers` is [{question_id, value}] (value: option string, option list for multi, or free
    text); `source` labels the import batch (e.g. 'html_form', a panel name)."""
    id: str
    survey_id: str
    respondent_key: str
    submitted_at: str
    answers: list[Json]
    source: str
    created_at: str

    def to_dict(self) -> Json:
        return asdict(self)


@dataclass
class Hypothesis:
    """A falsifiable prediction — "we expect X on metric M" stamped BEFORE reality answers, scored
    when it does. The sim-vs-reality calibration artifact: councils/synthesis only ever argue what
    is plausible; a Hypothesis records what was PREDICTED so eval_scorecard can show whether the
    simulations are predictive (it gives the eval_reports table its writer).

    prediction: {metric, expected_value (+tolerance?) OR expected_direction (increase|decrease),
    confidence?} — record_hypothesis rejects anything unfalsifiable. derived_from: Ref[] — the
    council statements / synthesis findings / predicted behaviors / open questions the bet
    operationalizes (validated to resolve on record). status is DERIVED at result-recording time by
    comparing observed against predicted; result ({observed_value, source (Ref), note, recorded_at})
    keeps BOTH raw values so the verdict stays auditable — the host argues it in `note`."""
    id: str
    project_id: str
    text: str
    prediction: Json
    derived_from: list[Json]
    status: str                  # open | validated | refuted | inconclusive | dropped
    result: Json | None
    created_at: str
    updated_at: str

    def to_dict(self) -> Json:
        return asdict(self)


@dataclass
class DecisionRecord:
    """An ADR-style node that captures the moment a human ACTS on the research: "we decided X,
    based on syntheses A and B, rejecting alternative C." Closes the research loop — months later
    the graph can answer "why does the product look like this?".

    based_on: Ref[] — the syntheses / findings / hypotheses the decision rests on;
    record_decision REJECTS a decision without at least one resolvable based_on ref (decisions
    must cite evidence, that is the point). rejected: Ref[] — the alternatives considered, each
    may carry a why-not `note`; those refs must resolve too. Superseding is recorded in BOTH
    directions: the old record is demoted to status=superseded and points forward via
    `superseded_by`; the successor points back via `supersedes`."""
    id: str
    project_id: str
    title: str
    decision: str
    status: str                  # proposed | adopted | superseded
    based_on: list[Json]
    rejected: list[Json]
    superseded_by: str | None
    supersedes: str | None
    created_at: str
    updated_at: str

    def to_dict(self) -> Json:
        return asdict(self)


@dataclass
class Evidence:
    id: str
    persona_id: str
    source_type: str
    content_or_path: str
    notes: str | None
    created_at: str

    def to_dict(self) -> Json:
        return asdict(self)


@dataclass
class SimulationResult:
    persona: Json
    date: str
    calendar_events: list[Json] = field(default_factory=list)
    experience_events: list[Json] = field(default_factory=list)
    daily_summary: Json | None = None
    reflection: Json | None = None

    def to_dict(self) -> Json:
        return asdict(self)
