# The queryable substrate

Sonaloop as infrastructure: everything the interactive runs produce — personas,
projects, councils, syntheses — is queryable programmatically over MCP (and the
CLI mirrors every call 1:1). This is the contract recurring jobs, multi-user
workspaces, the analytics dashboard and the client delivery portal build on.

## The contract (pin this)

`substrate_schema` returns the machine-readable version of everything below.

- **Versioned** — every envelope carries `substrate_version` (currently `1`);
  any shape change bumps it. Automations should assert on it.
- **Stable** — ids are the durable handles. Ordering is deterministic (newest
  first by `updated_at`/`created_at`, id tie-break), so pagination never
  shuffles between pages.
- **Paginated** — every list returns
  `{substrate_version, total, limit, offset, next_offset, items}`;
  pass `next_offset` back to continue; `limit` is clamped to 200.
- **Guarded** — every operation passes the access-guard seam (below).

## Queries

| Tool | Filters | Row |
|---|---|---|
| `query_personas` | `q` | compact persona summary (id, slug, name, age, role, segment) |
| `query_projects` | `status`, `q`, `since` | lean project (id, title, goal, status, methodology, counts, timestamps) |
| `query_councils` | `project_id`, `persona_id`, `q`, `since` | lean council (id, project_id, prompt, participants, counts) |
| `query_syntheses` | `status`, `q`, `since` | lean synthesis (id, title, status, council_ids, counts) |

`q` is free text over the row; `since` is an ISO lower bound on
`updated_at`/`created_at` — the natural shape for a recurring job's
"what changed since my last run?".

**`get_study_result(project_id)`** is the one-call structured result automations
poll: the lean project row + live run state + council rows + the **full**
syntheses in the project's graph (the answer nodes) + open questions + counts.

## Chat with one persona (durable)

Host-authored like everything else — the server never generates text:

1. `chat_with_persona(persona_id, message)` → the persona's loaded agent
   context + prior turns (`history`); omit `chat_id` to open, pass it to continue.
2. You author the in-character reply, then
   `record_chat_turn(persona_id, chat_id, user_message, persona_reply)` —
   the exchange persists and emits the `chat.recorded` lifecycle event.
3. `get_chat(chat_id)` / `list_chats(persona_id?)` read the durable artifact back.

A recorded exchange does not silently become persona memory. To preserve continuity across
separate chats, gather selected turns with `brief_memory_from_chat`, persist a pending
`record_memory_proposal`, then explicitly `review_memory_proposal` with approve/reject and a reason.
Approved notes are loaded only into later chats and are labelled synthetic conversation — never
independent evidence, lived experience, facts or identity revision.

CLI: `chat-brief`, `chat-record`, `chat-get`, `chat-list`, plus `query-*`,
`study-result`, `substrate-schema` and the `chat-memory-*` review commands.

## The auth seam (cloud builds on this)

```python
from sonaloop import services

def workspace_guard(operation: str, resource: dict) -> None:
    if resource.get("project_id") not in current_workspace_projects():
        raise PermissionError("outside workspace scope")

services.register_access_guard(workspace_guard)
```

Every substrate operation calls the registered guards (operation name +
resource descriptor) before touching data; raising `PermissionError` denies.
Locally no guards are registered and everything passes — the same surface works
single-user now and multi-tenant in sonaloop-cloud later, which is the point.

## How recurring jobs compose (the dependent ticket)

A scheduled job is: `query_projects(since=last_run)` → `get_study_result` per
hit → compare → act via a lifecycle hook (`register_hook` on `run.finished` /
`synthesis.recorded` / `chat.recorded` for push instead of poll). No other
surface needed.
