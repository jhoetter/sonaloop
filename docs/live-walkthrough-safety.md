# Live walkthrough safety — the WalkPolicy contract

Rung 3 of the Deep Persona ladder: "here's a URL and a test login — go use it." A persona
drives a REAL SaaS in a headless browser. That power needs a hard safety model, and the
model is most of the feature: every live session opened via `walk_open` runs under a
**WalkPolicy** (`sonaloop/walk_policy.py`) the harness (`sonaloop/browser.py`) enforces
in-session. It is the SAME harness as prototype sessions — `proto_act` / `proto_read` /
`proto_close` drive and end a walkthrough transparently, and
`record_usability_session(fidelity='live', session_id=…)` persists the verified trace.

`register_remote_prototype` is a separate metadata-only admission path for a
hosted app. It validates and stores an HTTP(S) URL but performs no DNS lookup,
network fetch or host execution. Remote MCP can therefore expose this registration
primitive while keeping `proto_open`, local-path registration and runners denied.

## The policy object

`walk_policy_defaults()` returns the safe defaults including the resolved denylist;
`walk_open(url, persona_id, policy?, credentials?)` normalizes a host patch over them:

```json
{
  "allowed_origins": ["https://app.example.com"],
  "blocked_categories": ["payment", "destructive", "outbound", "account"],
  "max_actions": 60,
  "max_duration_s": 900
}
```

- **`allowed_origins`** — an explicit origin allowlist (scheme + host + port; default ports
  normalized away). Defaults to the opening URL's own origin. Only http(s) origins are
  valid; a non-http(s) opening URL is rejected outright.
- **`blocked_categories`** — the deny-by-default risk classes, data-driven from
  `sonaloop/suggestions/walk_denylist.json` (EN + DE terms per category): `payment`,
  `destructive`, `outbound`, `account`. All enabled by default; a policy may disable a
  category explicitly. Add a term, no code change — but never narrow the file to make a
  session "work": over-blocking is the intended failure mode.
- **`max_actions` / `max_duration_s`** — hard caps (60 actions / 900 s by default).
- Unknown keys, unknown categories, non-positive caps and an opening URL outside the
  allowlist are **rejected** at open — the safety contract never degrades silently.

## The guarantees

1. **Origin containment.** Every observed page state is checked against
   `allowed_origins` — after every action AND on every read, so direct navigations,
   link-clicks, redirects and *delayed* JS redirects that fire while the session is idle
   are all caught. An off-origin landing is undone (the harness navigates back to the
   last on-policy URL) and comes back as a structured refusal; a redirect at OPEN refuses
   the whole session (there is no on-policy state to fall back to). An unparseable /
   non-http(s) landing URL counts as off-origin.
2. **No risky actions.** A `click`/`select` on an element whose accessible name/text
   matches an enabled denylist category (case-insensitive substring), or an Enter keypress
   whose focused element / form-submit control matches, is refused before it runs.
3. **Hard caps.** Reaching either cap logs `{kind:'cap_reached', cap:…}` and auto-closes
   the browser; the tripping `act` returns `{cap_reached, closed:true}` and every later
   `act`/`read` fails with the stable `CAP_REACHED` error.
4. **Violations never crash the host loop.** Origin and denylist blocks are RESULTS: the
   `act` envelope carries `policy_block` {rule, detail, …} next to the (unchanged or
   recovered) snapshot, AND the session log gets the matching entry — the block itself is
   evidence the replay can cite.

## Credentials & the redaction scope

Test logins are passed ONCE, at `walk_open(credentials={username?, password?})`, and live
only inside the session's worker thread. Filling happens via the dedicated act
`{type:'fill_credential', field:'username'|'password', ref:…}` — the secret never transits
the host loop, and the action echo logs only the field name. Argument values are never
logged at open.

**Redaction layer:** before any snapshot or log entry is retained or returned, every exact
credential value is replaced with `***` — including page echoes ("signed in as …" banners,
input values). The scope is exact-string replacement: pixel content of screenshots and
server-side TRANSFORMS of a secret (hashes, masked variants) are not covered — use
throwaway test accounts, never real ones.

## Audit trail

The session log is the audit trail, retained past `proto_close` (the same retention that
grounds prototype sessions): one entry per snapshot (`url`, `title`, refs, text,
`screenshot`), per action (redacted echo), per `policy_block` and per `cap_reached`. Every
snapshot also writes a per-step screenshot to
`data/sessions/<browser_session_id>/step-<n>.png` (fail-soft), referenced from the snapshot
as `<browser_session_id>/step-<n>.png` relative to the sessions dir —
`record_usability_session` validates those paths (containment under the data dir stays
enforced) and the replay view serves them via `/sessions-files/`.
