<p align="center">
  <img src="docs/assets/sonaloop-banner-v2.png" alt="Sonaloop" width="100%">
</p>

# Sonaloop

> **Naming note:** this repository was renamed from `sonaloop` to
> `sonaloop-research` (2026-07-05). On PyPI the package is still called
> **`sonaloop`** — TODO: publish under the new name in the future.

[![PyPI](https://img.shields.io/pypi/v/sonaloop)](https://pypi.org/project/sonaloop/)
[![Python](https://img.shields.io/pypi/pyversions/sonaloop)](https://pypi.org/project/sonaloop/)
[![License](https://img.shields.io/pypi/l/sonaloop)](LICENSE)
[![Docs](https://img.shields.io/badge/docs-sonaloop--docs-1c2733)](https://jhoetter.github.io/sonaloop-docs/)

**An MCP server for customer-persona simulation, councils, and design-research synthesis.**

Sonaloop models customer profiles as persistent agents — durable `SOUL.md` files,
timestamped calendars, activity logs, inner thoughts, evidence, and council-style
debates. The **host agent authors all text**; Sonaloop gathers context, validates,
and persists. There are no server-side text-LLM calls, and simulation is
non-directional: profiles are never nudged toward a product thesis unless their own
evidence supports it.

![Sonaloop inspector — a memory-grounded council with executive summary, sentiment breakdown, and links into the synthesis](docs/assets/sonaloop-council.png)

**Docs:** <https://jhoetter.github.io/sonaloop-docs/> — start with
[Getting started](https://jhoetter.github.io/sonaloop-docs/getting-started/).

## Get started

One sentence per host (needs [`uv`](https://docs.astral.sh/uv/)):

- **Claude Code**

  ```bash
  claude mcp add sonaloop -- uvx sonaloop-mcp
  ```

- **Claude Desktop / Cursor / any MCP host** — add to the host's MCP config (`mcpServers`):

  ```json
  { "sonaloop": { "command": "uvx", "args": ["sonaloop-mcp"] } }
  ```

That's it — no data dir, no `.env`, no setup step. The server bootstraps itself, and the
first tool call on a fresh database returns the first steps (project → personas → council).
Complete **example projects** ship with the install, including an onboarding showcase:
ask your agent to call
`load_example`, or click **Load example** in the inspector. `sonaloop info` checks the
wiring; `sonaloop setup` adds the optional headless browser for prototype testing.

<details>
<summary><b>No setup knowledge? Paste this to your AI agent instead.</b></summary>

Paste into an **AI agent that can run commands on your machine** (Claude Code, Cursor,
Codex, or a desktop agent with terminal access). It installs Sonaloop, starts the
inspector, and walks you through a first project — you just talk.

```text
Set up Sonaloop for me and walk me through a first project. Do every step yourself and keep
me posted; I just want to talk, not configure anything.

1. Install the `sonaloop` CLI in whatever way fits this environment — try `uv tool install
   sonaloop`, else `pipx install sonaloop`, else `pip install --user sonaloop`.
2. Run `sonaloop setup` (it fetches a headless browser) and `sonaloop info` to confirm.
3. Start the web inspector in the background by running `sonaloop-web`, then tell me the URL
   it prints — http://localhost:8787 — so I can watch everything live.
4. If this app supports MCP servers, also register Sonaloop as one (command: `sonaloop-mcp`)
   so you can call its tools directly. Otherwise just drive it via the `sonaloop` CLI — both work.
5. Run `sonaloop guide` and follow it exactly. The key rule: YOU author every piece of text
   (personas, days, council answers, syntheses) — Sonaloop only gathers context and persists.
6. Ask me what I want to research or simulate (any domain). Then create a few personas,
   simulate a little of their lives, run a council on my question, and synthesize the result —
   pointing me to the inspector to read each one.
```
</details>

<details>
<summary><b>Prefer a permanent install instead of uvx?</b></summary>

```bash
uv tool install sonaloop      # or: pipx install sonaloop / pip install --user sonaloop
sonaloop setup                # headless browser for prototype screenshots + PDF export
sonaloop guide                # the agent operating contract + first-run recipe
```

Works in **any MCP host**: the server ships its operating contract as MCP `instructions`
and its workflows as MCP **prompts** — provider-agnostic. Claude Code additionally gets
the `claude-skills/` adapter. Full rules: [AGENTS.md](AGENTS.md).
</details>

## The model in one minute

- **Personas** — host-authored profiles, simulated day by day into a **memory graph** they recall + time-travel.
- **Research project** — driven by a plan engine (`next_action` → analyze / act / verify) along a methodology framework.
- **Evidence** — memory-grounded **councils**, **head-to-heads**, **price ladders**, **prototype tests**, and notes.
- **Synthesis / report** — converges the evidence into the answer (web report, PDF, deck).

Every generative step follows one contract: `brief_*` (gather) → the host authors JSON →
`record_*` (validate + persist). Which study shape fits which question — A/B test, pricing,
ideation, positioning — is the [Job → Framework → Format
taxonomy](https://jhoetter.github.io/sonaloop-docs/job-framework-format/).

## The inspector (web UI)

A Linear/Notion-grade web app (`sonaloop-web`, <http://localhost:8787>) that updates
**live** while your agent works: an SSE event stream feeds activity toasts, the
[activity feed](https://jhoetter.github.io/sonaloop-docs/live-inspector/), and the runs
panel. ⌘K command palette, `?` keyboard cheat sheet, an opt-in product tour, structural
editing (projects, personas, notes — [authored prose stays
host-only](https://jhoetter.github.io/sonaloop-docs/web-editing/)), built-in feedback,
dark mode, bilingual (de/en).

| Synthesis as a report | Persona memory page |
| --- | --- |
| [![Meta-report — a Notion-style document with table of contents and callouts](docs/assets/sonaloop-report.png)](docs/assets/sonaloop-report.png) | [![Persona detail — voices in analyses, goals, and pain points](docs/assets/sonaloop-persona.png)](docs/assets/sonaloop-persona.png) |

## Configuration

Everything is optional. `OPENAI_API_KEY` enables persona avatars + semantic memory recall
(never text generation). Writable state lives in a per-user data dir
(`~/.local/share/sonaloop`; override with `SONALOOP_DATA_DIR`); `sonaloop
purge-runtime-data` gives a clean slate. Every supported variable is enumerated with a
one-line explanation in [.env.example](.env.example).

## From source (development)

```bash
git clone https://github.com/jhoetter/sonaloop-research && cd sonaloop-research
uv sync
make skills                   # symlink claude-skills/* for Claude Code discovery
make dev                      # web inspector on :8787
make mcp                      # MCP server (stdio)
```

Dev checks: `make test` (hermetic pytest suite) · `make ux` (the UX drift gate —
pixel-diffs the canonical screens against committed goldens, see
[spec/ux-contract.md](spec/ux-contract.md)) · `make check-icons` (vendored design-system
sync with `../sonaloop-design`).

Releases: bump `version` in `pyproject.toml`, then `uv build && uv publish`. The
`uvx sonaloop-mcp` one-liner is backed by the shim in
[`packaging/sonaloop-mcp/`](packaging/sonaloop-mcp/) — bump and publish it in lockstep.

Move your exact state between machines without regenerating: `make snapshot` writes
`data/export/`, `make restore` rebuilds the runtime DB + avatars + SOULs from it. All of
`data/` is git-ignored and local-only — your content never leaves your machine.

## Operating rules & docs

The host agent follows [AGENTS.md](AGENTS.md) (and [CLAUDE.md](CLAUDE.md), which delegates
to it). Canonical product docs live in
[sonaloop-docs](https://jhoetter.github.io/sonaloop-docs/); deep technical notes under
[`docs/`](docs/) and [`spec/`](spec/).

## Credits

The council format was inspired by Leo Püttmann's
[`ai-council`](https://github.com/LeonardPuettmann/ai-council) — its markdown-defined
agents and select → debate → propose → vote → persist flow seeded this project.
Sonaloop takes it further with durable persona state, persistent memory, longitudinal
simulation, and MCP-host-authored text.
