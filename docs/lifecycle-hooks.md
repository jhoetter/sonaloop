# Lifecycle hooks

The core emits a documented event at every durable lifecycle moment — persona
created, council recorded ("session finished"), synthesis recorded, run finished —
and exposes three subscription seams. Hooks are the connective tissue for
automations: a Slack/Notion/CRM push, a cloud alerting connector, a recurring-jobs
trigger. Local hooks work fully standalone; sonaloop-cloud builds delivery and
alerting on top of the same envelope.

Emission is **best-effort by contract**: events fire *after* the state is
persisted, a failing subscriber is logged and never breaks the operation that
emitted the event, and payloads carry ids + lean summaries — never authored text.

## The envelope

Every subscriber — in-process handler, command, or webhook — receives the same
version-stamped envelope. This shape is the stable surface connectors depend on:

```json
{
  "event": "council.recorded",
  "schema": 1,
  "emitted_at": "2026-06-10T12:00:00.000000+00:00",
  "data": { "council_id": "council_…", "project_id": "research_…", "…": "…" }
}
```

## The events

| Event | Fires when | Payload |
|---|---|---|
| `persona.created` | a host-authored profile is validated + persisted | `persona_id`, `slug`, `display_name` |
| `persona.updated` | a profile patch lands (audit reason included) | `persona_id`, `reason` |
| `evidence.attached` | a real-world source is attached to a persona | `persona_id`, `evidence_id`, `source_type` |
| `chat.recorded` | a persona chat exchange is persisted (docs/substrate.md) | `chat_id`, `persona_id`, `turns` |
| `persona.grounded` | a persona was grounded in real source material (docs/grounding.md) | `persona_id`, `corpus_ids`, `claims` |
| `prediction.scored` | a real outcome was matched to a predicted behavior (docs/calibration.md) | `project_id`, `outcome_id`, `brier`, `hit` |
| `calibration.round_recorded` | a correction round was stamped after calibration misses | `scope`, `corrections`, `mean_brier` |
| `asset.attached` | a file/image/screenshot is attached to a project as evidence (docs/project-assets.md) | `project_id`, `asset_id`, `kind`, `filename` |
| `day.recorded` | one simulated day is persisted | `persona_id`, `date`, `events` |
| `council.recorded` | a council session finishes inside its project — the **"session finished"** moment | `council_id`, `project_id`, `prompt`, `persona_ids`, `statements`, `votes` |
| `synthesis.recorded` | a synthesis (answer/report node) is created or updated | `synthesis_id`, `title`, `status`, `council_ids` |
| `project.created` | a research project is created + its plan seeded | `project_id`, `title`, `goal`, `methodology` |
| `run.finished` | a governed run ends — the study completed | `run_id`, `project_id`, `status`, `steps` |

The live catalogue (always current, including payload contracts) is
`list_lifecycle_events` over MCP or `sonaloop hooks-events` on the CLI.

Subscriptions accept an exact event name, a domain wildcard (`persona.*`), or `*`.

## Subscribing

### 1. Durable hooks (user-facing; persisted in the DB)

```bash
# A command hook: the envelope arrives as JSON on stdin (+ SONALOOP_EVENT in env)
sonaloop hook-register council.recorded command \
  'jq -r .data.prompt >> ~/council-log.txt' --label "council log"

# A webhook: the envelope is POSTed as JSON (X-Sonaloop-Event header set)
sonaloop hook-register run.finished webhook https://hooks.slack.com/services/…

sonaloop hooks-list          # all registrations
sonaloop hook-test <id>      # fire a sample envelope through one hook
sonaloop hook-remove <id>
```

The same four operations exist as MCP tools: `register_hook`, `list_hooks`,
`test_hook`, `unregister_hook` (+ `list_lifecycle_events` for the catalogue).
Registration is idempotent on `(event, kind, target)`.

### 2. Entry-point extensions (`sonaloop.hooks`)

The hooks counterpart of the `sonaloop.web.extensions` seam — how
sonaloop-cloud / sonaloop-research plug connectors in without touching core:

```toml
# the extension package's pyproject.toml
[project.entry-points."sonaloop.hooks"]
alerting = "sonaloop_cloud.alerting:setup"
```

```python
def setup() -> None:
    from sonaloop import services
    services.add_hook_handler("run.finished", push_to_slack)
```

Extensions load lazily on first emit; a broken extension is logged and skipped.

### 3. In-process handlers

```python
from sonaloop import services
services.add_hook_handler("council.recorded", lambda env: ...)
```

## The event bus + live inspector (SSE)

The MCP server, the CLI and the web inspector are separate processes sharing one
SQLite DB, so the inspector can't see in-process emissions directly. A built-in
`'*'` subscriber (`sonaloop/services/_events.py`, registered whenever the services
layer loads — i.e. in whichever process records data) appends every emitted event
to a durable `events` table: monotonic id, timestamp, event name, the primary
entity (+ owning project), and a short label + inspector URL. The table is capped
to the newest ~1000 rows on append; like every subscriber, the append is
best-effort and never breaks the recording operation. These rows are a transient
live-view cache, not audit history: deleting a project also removes bus rows whose
exact `project_id` matches it, while workspace-level/persona events remain.

The web app tails that table:

- `GET /api/events` — a plain SSE stream (heartbeat comment every ~15s; the table
  is polled about once a second). Each frame's `id:` is the bus row id, so an
  `EventSource` reconnect replays missed rows via `Last-Event-ID` automatically.
- Every inspector page connects on load: new events show a small activity toast
  linking to the recorded entity, and the page reloads itself when an event
  concerns the entity/project currently on screen — Claude records a council over
  MCP in one window, the open project page updates in the other.
- `/activity` — the Activity feed page listing the recent bus rows.

Knobs: `SONALOOP_EVENTS_POLL` (table-poll seconds, default 1) and
`SONALOOP_EVENTS_HEARTBEAT` (heartbeat seconds, default 15).

## Operational knobs

- `SONALOOP_DISABLE_HOOKS=1` — skip command/webhook delivery entirely
  (in-process handlers still run).
- `SONALOOP_HOOK_TIMEOUT` — per-delivery timeout in seconds (default 10,
  clamped 1–120).
