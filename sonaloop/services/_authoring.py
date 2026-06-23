"""Shared host-authoring contract (spec/markdown-authoring-harness.md).

Appended to the `instructions` of every prose-authoring brief so the host writes Markdown body prose
instead of ALL-CAPS-for-emphasis and literal section headers. The web UI renders these fields with a
real Markdown renderer (web/_components._md), so authoring Markdown 'just works' with no UI change."""
from __future__ import annotations

PRIMITIVES_CONTRACT = (
    "\n\nUNIFIED PRIMITIVES (spec/unified-artifact-schema.md) — the ONLY accepted content shape:\n"
    "• `statements`: one per persona utterance — {persona_id, text (Markdown), "
    "stance:{value -2..2, label?: support|conditional|neutral|skeptical|oppose}, "
    "about:{kind:'prompt', id}, refs:[{kind:'memory'|'council'|'synthesis'|'prototype_state', id, anchor, "
    "role} | {kind:'memory', text}], meta}. The ONE voice shape (council voices, synthesis voices, "
    "prototype reactions).\n"
    "• `findings`: the analysis items — {text (Markdown), kind: summary|key_problem|pain_solver|"
    "open_question|recommendation|cluster|segment|ranking|shortlist, score:{effort,value}, refs}. The ONE "
    "analysis shape.\n"
    "• `prompts`: {text, kind: question|proposal|goal|focus, id} — the questions/proposal posed; statements "
    "reference them via `about.id`.\n"
    "CROSS-REFERENCE, never copy (spec/artifact-cross-references.md): when a synthesis reflects a council "
    "statement, author your OWN finding text + a ref {kind:'council', id, anchor:'<statement-id>', "
    "role:'derived_from'} — the source words are resolved live, not duplicated.\n"
    "One positivity scale only (oppose -2 / skeptical -1 / neutral 0 / conditional +1 / support +2) for "
    "every stance. A DECISION council may also pass `votes` (the formal tally). There are NO compatibility "
    "turns/voices/key_problems inputs."
)

MARKDOWN_CONTRACT = (
    "\n\nAUTHORING STYLE (body prose): write analysis/summary fields as GitHub-flavored **Markdown** — "
    "use **bold** / _italic_ for emphasis, `-` or `1.` lists for enumerations, `>` for quotes, "
    "`code` for verbatim, and blank lines between paragraphs. Do NOT use ALL-CAPS for emphasis, and do "
    "NOT write a literal section header inside the text (e.g. 'SUMMARY:', 'VOTES:', 'WHAT THIS COUNCIL "
    "FOUND') — the UI already renders the headers/labels around your text. This applies to the "
    "moderator/analysis fields (exec_summary, summary, gesamtbild, positionierung, recommendations, "
    "report sections, key problems, open questions, notes). A persona/proband turn `content` may "
    "stay in that persona's own natural voice — it is a quote, not a report."
)
