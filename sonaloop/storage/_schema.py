from __future__ import annotations


SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS personas (
  id TEXT PRIMARY KEY,
  slug TEXT UNIQUE NOT NULL,
  data TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS calendar_events (
  id TEXT PRIMARY KEY,
  persona_id TEXT NOT NULL,
  start TEXT NOT NULL,
  "end" TEXT NOT NULL,
  data TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS experience_events (
  id TEXT PRIMARY KEY,
  persona_id TEXT NOT NULL,
  timestamp TEXT NOT NULL,
  event_type TEXT NOT NULL,
  data TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS daily_summaries (
  id TEXT PRIMARY KEY,
  persona_id TEXT NOT NULL,
  date TEXT NOT NULL,
  data TEXT NOT NULL,
  UNIQUE(persona_id, date)
);

CREATE TABLE IF NOT EXISTS reflections (
  id TEXT PRIMARY KEY,
  persona_id TEXT NOT NULL,
  period_start TEXT NOT NULL,
  period_end TEXT NOT NULL,
  data TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pain_points (
  id TEXT PRIMARY KEY,
  persona_id TEXT NOT NULL,
  issue TEXT NOT NULL,
  data TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS council_sessions (
  id TEXT PRIMARY KEY,
  created_at TEXT NOT NULL,
  data TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS syntheses (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  data TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS evidence (
  id TEXT PRIMARY KEY,
  persona_id TEXT NOT NULL,
  source_type TEXT NOT NULL,
  data TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS prediction_outcomes (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  created_at TEXT NOT NULL,
  data TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS corpora (
  id TEXT PRIMARY KEY,
  data TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS corpus_chunks (
  id TEXT PRIMARY KEY,
  corpus_id TEXT NOT NULL,
  idx INTEGER NOT NULL,
  text TEXT NOT NULL,
  data TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS persona_chats (
  id TEXT PRIMARY KEY,
  persona_id TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  data TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS lifecycle_hooks (
  id TEXT PRIMARY KEY,
  event TEXT NOT NULL,
  data TEXT NOT NULL
);

-- Cross-process event bus (docs/lifecycle-hooks.md): one lean row per emitted lifecycle
-- event, appended by the services-layer '*' subscriber in WHICHEVER process records data
-- (MCP server / CLI) and tailed by the web inspector's SSE stream + Activity feed.
-- Monotonic AUTOINCREMENT id = the SSE cursor; the table is capped on append (~1000 rows).
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL,
  event TEXT NOT NULL,
  entity_type TEXT NOT NULL,
  entity_id TEXT NOT NULL,
  project_id TEXT,
  data TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  entity_type TEXT NOT NULL,
  entity_id TEXT NOT NULL,
  action TEXT NOT NULL,
  reason TEXT,
  created_at TEXT NOT NULL,
  data TEXT
);

CREATE TABLE IF NOT EXISTS meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

-- Memory layer 2: entities (project|person|org|building|authority|topic)
CREATE TABLE IF NOT EXISTS entities (
  id TEXT PRIMARY KEY,
  persona_id TEXT NOT NULL,
  kind TEXT NOT NULL,
  name TEXT NOT NULL,
  status TEXT,
  data TEXT NOT NULL,
  first_seen TEXT,
  last_seen TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_entities_persona ON entities(persona_id, kind);

-- Memory layer 2: bi-temporal facts (valid-time intervals = time-travel)
CREATE TABLE IF NOT EXISTS entity_facts (
  id TEXT PRIMARY KEY,
  persona_id TEXT NOT NULL,
  entity_id TEXT NOT NULL,
  fact TEXT NOT NULL,
  status TEXT,
  t_valid TEXT NOT NULL,
  t_invalid TEXT,
  importance INTEGER DEFAULT 3,
  source_event_id TEXT,
  data TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_facts_entity ON entity_facts(entity_id);
CREATE INDEX IF NOT EXISTS idx_facts_persona ON entity_facts(persona_id);

-- Episode <-> entity links
CREATE TABLE IF NOT EXISTS event_entities (
  event_id TEXT NOT NULL,
  entity_id TEXT NOT NULL,
  persona_id TEXT NOT NULL,
  role TEXT,
  PRIMARY KEY (event_id, entity_id)
);
CREATE INDEX IF NOT EXISTS idx_event_entities_entity ON event_entities(entity_id);

-- Open loops with identity
CREATE TABLE IF NOT EXISTS threads (
  id TEXT PRIMARY KEY,
  persona_id TEXT NOT NULL,
  entity_id TEXT,
  text TEXT NOT NULL,
  status TEXT NOT NULL,
  opened_on TEXT,
  closed_on TEXT,
  data TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_threads_persona ON threads(persona_id, status);

-- Plans across resolutions: day|week|month|quarter|year
CREATE TABLE IF NOT EXISTS plans (
  id TEXT PRIMARY KEY,
  persona_id TEXT NOT NULL,
  scope TEXT NOT NULL,
  period_start TEXT NOT NULL,
  period_end TEXT NOT NULL,
  data TEXT NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE(persona_id, scope, period_start)
);

-- Layer 3: consolidated digests
CREATE TABLE IF NOT EXISTS memory_digests (
  id TEXT PRIMARY KEY,
  persona_id TEXT NOT NULL,
  scope TEXT NOT NULL,
  period_start TEXT NOT NULL,
  period_end TEXT NOT NULL,
  data TEXT NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE(persona_id, scope, period_start)
);

-- Embeddings for hybrid semantic retrieval
CREATE TABLE IF NOT EXISTS embeddings (
  obj_type TEXT NOT NULL,
  obj_id TEXT NOT NULL,
  persona_id TEXT NOT NULL,
  model TEXT NOT NULL,
  dim INTEGER NOT NULL,
  vector BLOB NOT NULL,
  text TEXT,
  created_at TEXT NOT NULL,
  PRIMARY KEY (obj_type, obj_id)
);
CREATE INDEX IF NOT EXISTS idx_embeddings_persona ON embeddings(persona_id, obj_type);

-- Slow, evidence-backed persona identity drift
CREATE TABLE IF NOT EXISTS persona_revisions (
  id TEXT PRIMARY KEY,
  persona_id TEXT NOT NULL,
  effective_on TEXT NOT NULL,
  data TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_revisions_persona ON persona_revisions(persona_id, effective_on);

-- Exogenous world backdrop (not shared persona knowledge)
CREATE TABLE IF NOT EXISTS world_context (
  id TEXT PRIMARY KEY,
  category TEXT NOT NULL,
  fact TEXT NOT NULL,
  t_valid TEXT NOT NULL,
  t_invalid TEXT,
  relevance_tags TEXT,
  data TEXT NOT NULL,
  created_at TEXT NOT NULL
);

-- Consistency / quality anomalies (non-blocking, visible)
CREATE TABLE IF NOT EXISTS memory_anomalies (
  id TEXT PRIMARY KEY,
  persona_id TEXT,
  kind TEXT NOT NULL,
  severity INTEGER DEFAULT 2,
  data TEXT NOT NULL,
  created_at TEXT NOT NULL
);

-- Evaluation reports (how we measure "top")
CREATE TABLE IF NOT EXISTS eval_reports (
  id TEXT PRIMARY KEY,
  persona_id TEXT,
  period_start TEXT,
  period_end TEXT,
  green INTEGER NOT NULL,
  data TEXT NOT NULL,
  created_at TEXT NOT NULL
);

-- Research graph: a Project groups studies (syntheses, incl. project-scope reports)
-- into a themed graph, with typed edges between studies and promotable open questions.
-- (Distinct from the memory "project" entity, which is a persona's own work project.)
CREATE TABLE IF NOT EXISTS research_projects (
  id TEXT PRIMARY KEY,
  slug TEXT UNIQUE NOT NULL,
  title TEXT NOT NULL,
  data TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);


CREATE TABLE IF NOT EXISTS research_open_questions (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  study_id TEXT,
  status TEXT NOT NULL,
  data TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_roq_project ON research_open_questions(project_id);

-- ESV: the resumable run object (driver journal). One run drives one project's plan to a
-- self-verified, finished result; `data` holds the step journal + critic rounds (resume = replay it).
CREATE TABLE IF NOT EXISTS runs (
  run_id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  status TEXT NOT NULL,
  cursor INTEGER NOT NULL DEFAULT 0,
  data TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_runs_project ON runs(project_id);

-- Methodology engine (spec/methodology-engine-and-prototyping.md): user-defined
-- methodology specs + the LLM-judged gate decisions recorded per phase.
CREATE TABLE IF NOT EXISTS methodologies (
  key TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  data TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS methodology_judgments (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  phase_key TEXT NOT NULL,
  kind TEXT NOT NULL,
  decided INTEGER NOT NULL,
  data TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_mjudge_project ON methodology_judgments(project_id);

-- Research plan (spec/research-plan-engine.md): one plan per project — the orchestrator's
-- source of truth (analyze/act/verify task DAG + evidence refs), rendered to plan.md on demand.
CREATE TABLE IF NOT EXISTS research_plans (
  project_id TEXT PRIMARY KEY,
  data TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

-- Prototype artifacts (real, minimal, locally-runnable apps) + recorded persona use.
CREATE TABLE IF NOT EXISTS prototypes (
  id TEXT PRIMARY KEY,
  slug TEXT UNIQUE NOT NULL,
  project_id TEXT,
  version TEXT,
  data TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_prototypes_project ON prototypes(project_id);

CREATE TABLE IF NOT EXISTS prototype_sessions (
  id TEXT PRIMARY KEY,
  persona_id TEXT NOT NULL,
  prototype_id TEXT NOT NULL,
  session_id TEXT,
  data TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_protosess_proto ON prototype_sessions(prototype_id);

-- Outbound surveys: the instrument document (questions + derived_from refs in `data`).
CREATE TABLE IF NOT EXISTS surveys (
  id TEXT PRIMARY KEY,
  slug TEXT UNIQUE NOT NULL,
  project_id TEXT,
  status TEXT NOT NULL,
  data TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_surveys_project ON surveys(project_id);

-- Survey responses: OWN table, never embedded in the survey document — response counts grow
-- unbounded. One row per real respondent submission (answers live in `data`).
CREATE TABLE IF NOT EXISTS survey_responses (
  id TEXT PRIMARY KEY,
  survey_id TEXT NOT NULL,
  respondent_key TEXT NOT NULL,
  submitted_at TEXT NOT NULL,
  data TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_survey_responses_survey ON survey_responses(survey_id);

-- Hypotheses: falsifiable predictions stamped BEFORE reality answers, scored when it does
-- (prediction / derived_from refs / the recorded result live in `data`). Resolved hypotheses
-- aggregate into eval_reports via eval_scorecard — the sim-vs-reality calibration record.
CREATE TABLE IF NOT EXISTS hypotheses (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  status TEXT NOT NULL,
  data TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_hypotheses_project ON hypotheses(project_id);

-- Decision records: ADR-style nodes — what was decided, on which evidence (based_on refs),
-- rejecting what (rejected refs + why-not notes). Superseding links both directions
-- (superseded_by on the old record, supersedes on the successor); details live in `data`.
CREATE TABLE IF NOT EXISTS decision_records (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  status TEXT NOT NULL,
  data TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_decision_records_project ON decision_records(project_id);

-- Usability sessions: the durable, replayable per-step session trace (one schema across the
-- artifact/prototype/live fidelity rungs; supersedes prototype_sessions for new recordings).
-- subject_key = subject.id or subject.url, so the funnel can aggregate sessions of one subject.
CREATE TABLE IF NOT EXISTS usability_sessions (
  id TEXT PRIMARY KEY,
  project_id TEXT,
  persona_id TEXT NOT NULL,
  subject_kind TEXT NOT NULL,
  subject_key TEXT NOT NULL,
  fidelity TEXT NOT NULL,
  data TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_usess_subject ON usability_sessions(subject_kind, subject_key);
CREATE INDEX IF NOT EXISTS idx_usess_subject_created ON usability_sessions(subject_kind, subject_key, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_usess_project_created ON usability_sessions(project_id, created_at DESC);

-- User feedback (ticket feedback-button): free-text submissions from the web inspector.
-- read_at flips when an operator views them (/feedback page or `sonaloop feedback`);
-- `sonaloop info` surfaces the unread count. page/app_version are the transparent
-- context shown to the submitter and sent along.
CREATE TABLE IF NOT EXISTS feedback (
  id TEXT PRIMARY KEY,
  message TEXT NOT NULL,
  email TEXT,
  page TEXT,
  app_version TEXT,
  created_at TEXT NOT NULL,
  read_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_feedback_created ON feedback(created_at);
"""
