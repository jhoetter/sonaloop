# Markdown authoring harness — generated prose is Markdown, not ALL-CAPS

Status: **DONE** (2026-06-06) — harness + Markdown-first demo project.

## 1. Problem (the big picture)

All content in this app is **host/subagent-authored via MCP** — there is no in-process LLM text
generation (`spec` memory: the host writes every word; the OpenAI key is embeddings + images only). The
authoring loop is:

```
brief_*  (MCP tool → returns a scaffold + `instructions`)  →  host authors the text  →  record_*  (persists)
                                                                                         ↓
                                                                    web/ renders it (markdown via _md)
```

Today the host authors emphasis with **ALL-CAPS** and literal section headers inside the prose
("WHAT THIS COUNCIL FOUND: …", "VOTES: …", "WO DIE GEGENTHESE GEWINNT:"). That reads shouty and
duplicates headers the UI already draws. The renderer (`web/_components._md`) is a real Markdown
renderer and is already wired for the prose fields — so if the host authored **Markdown** instead
(`**bold**`, `_italic_`, `-`/`1.` lists, `>` quotes), it would render cleanly with zero UI change.

**The fix is in the harness, not the UI:** make the just-in-time `brief_*.instructions` (and the skills)
require Markdown body prose and forbid ALL-CAPS-for-emphasis / literal headers. The skills already *hint*
"Markdown exec_summary", but the brief the host reads at authoring time does not — that's the gap.

## 2. The authoring contract (one shared rule)

A single constant — `sonaloop/services/_authoring.MARKDOWN_CONTRACT` — appended to the
`instructions` of every prose-authoring brief, and stated in the skills:

> **Author body prose as GitHub-flavored Markdown.** Use `**bold**` / `_italic_` for emphasis, `-` or
> `1.` lists for enumerations, `>` for quotes, `` `code` `` for verbatim. **Never use ALL-CAPS for
> emphasis** and **never write a literal section header** (e.g. "SUMMARY:", "VOTES:", "WHAT THIS
> COUNCIL FOUND") — the UI renders the headers/labels around your text. Keep `\n\n` between paragraphs.
> Persona/proband turn `content` may stay in the persona's own natural voice (it is a quote, not a
> report) — the contract is for the moderator/analysis fields below.

## 3. Scope — which fields are Markdown

**IN (moderator / analysis prose → Markdown, rendered via `_md`):**
- council: `exec_summary`, `summary`, `proposal`, `selection_reason`
- synthesis: `gesamtbild`, `positionierung`, `arc_narrative`; list items `key_problems`, `pain_solvers`,
  `handlungsempfehlungen`, `offene_fragen`, `shortlist` (inline emphasis allowed)
- meta-report: every section body
- notes/concepts: `text`
- prototype session `reaction` analysis fields (verdict/notes) — light Markdown ok

**OUT (stay as-is):**
- persona turn `content` (a proband quote, in-voice — not a report)
- titles / labels / kinds / tags (these are short identifiers; the UI styles them — see the title and
  Executive-Summary work already shipped)
- numeric/enum fields (votes, scores)

## 4. Touchpoints (exact, to implement)

1. **`services/_authoring.py`** (new): `MARKDOWN_CONTRACT` constant.
2. **`services/_councils.py` → `brief_council`**: append the contract to `instructions` (all 3 mode
   branches share the final string). Note: proband turns in-voice; `exec_summary`/`summary` = Markdown.
3. **`services/_synthesis.py` → `brief_synthesis`, `brief_meta_report`, `brief_meta_section`**: append
   the contract (gesamtbild/sections/recommendations = Markdown).
4. **Skills** (state the contract explicitly): `claude-skills/run-council/SKILL.md`,
   `synthesize/SKILL.md`, `design-thinking/SKILL.md`, `design-thinking-deep/SKILL.md`,
   `methodology-run/SKILL.md`.
5. **UI render audit** — the prose fields ALREADY render via `_md` (council exec_summary/summary,
   synthesis gesamtbild/positionierung/arc_narrative, meta report, notes). ✅ no change needed.
   *Follow-up (noted, not blocking):* the list items (`key_problems`, `pain_solvers`,
   `handlungsempfehlungen`) render via `_srcchips(_esc(x))` (plain + source-chips), so block markdown
   won't apply; inline emphasis is fine to add later via an inline-md pass that preserves `[C#]` chips.

## 5. Migration of existing data

Existing records keep their ALL-CAPS prose (not rewritten — lossy/risky, and historical). The contract
governs **new** authoring. The new design-thinking project (below) is authored Markdown-first, so it
showcases the target style immediately.

## 6. Verification

- `t()`/i18n + full suite stay green (the harness change is server-side prose; no UI/CSS change).
- The new project's council `exec_summary`/`summary` and synthesis `gesamtbild` render with real
  `<strong>`/`<ul>` (not shouting caps) in the web UI.

## 7. Checklist
- [x] `_authoring.MARKDOWN_CONTRACT`
- [x] inject into `brief_council`
- [x] inject into `brief_synthesis` / `brief_meta_report` / `brief_meta_section`
- [x] skills updated (5)
- [x] suite green
- [x] new Markdown-first design-thinking project created & viewable (since purged — store reset to a
  clean, zero-compatibility slate at the user's request; new content authors natively via the primitives)
