# The documentation surfaces — and the split rule

Sonaloop documentation lives on **two surfaces with different audiences**, plus one
canonical published home:

1. **`/docs/*.md` (this folder) — deep, agent-facing.** Technical contracts, formats,
   protocols and seams, written for the engineer or agent working *on or against* the
   code. English only, precise, allowed to reference module paths and internals.
2. **The in-app docs hub (`sonaloop/web/_docs.py` + `web/_docs_content.py`) — user-facing,
   bilingual (de/en).** A concise snapshot for the HUMAN using the inspector: what each
   thing is, why it matters, how to work live. Plain language, no module paths.
3. **The canonical published home is the [sonaloop-docs repo](https://github.com/jhoetter/sonaloop-docs)**
   (MkDocs Material → <https://jhoetter.github.io/sonaloop-docs/>, machine index at
   `/llms.txt`). Product-facing pages land there first; this folder keeps the deep notes
   that are inseparable from the code and links out rather than duplicating.

> **A feature isn't done until the surfaces are updated.** When a change is user-visible,
> update the in-app docs hub; when it changes a contract, update the relevant `/docs/*.md`;
> when it's product-facing, sync the sonaloop-docs page + its `mkdocs.yml` nav +
> `docs/llms.txt` index. (Also stated in [AGENTS.md](../AGENTS.md).)

## Where each surface is enumerated (the discoverability map)

| Surface | Where it self-documents | Notes |
| --- | --- | --- |
| MCP tools | The in-app **MCP reference** (`/documentation/mcp`) — auto-generated from the live tool modules (`mcp_server/_catalogue.py`); tool docstrings are the descriptions | Never hand-maintain a tool list in prose |
| CLI commands | `sonaloop --help` / `sonaloop <cmd> --help`; the workflow recipes in [AGENTS.md](../AGENTS.md) | CLI and MCP are the SAME service surface |
| Env vars | [`.env.example`](../.env.example) — the complete annotated list | Add every new `os.getenv` there, with a one-liner |
| Web inspector | The in-app docs hub (`/documentation`) | Bilingual; parity/leak tests guard it |
| Jobs/protocols | [job-framework-format.md](job-framework-format.md) + `taxonomy.json` | `sonaloop taxonomy-lint` greps this doc for a section per Job |

## Index of the deep notes in this folder

- [job-framework-format.md](job-framework-format.md) — the Job → Framework → Format taxonomy, protocols, Adding-a-Job recipe
- [frameworks.md](frameworks.md) — the methodology frameworks in plain language
- [retry-safe-run-contract.md](retry-safe-run-contract.md) — methodology resolution, create/checkpoint idempotency, fail-closed run completion
- [research-integrity.md](research-integrity.md) — cloud/Core front door selection, dispatch-token writes, Product + Cohort Integrity preflights, Reaction Test claim posture
- [remote-stimulus-admission.md](remote-stimulus-admission.md) — direct-byte Remote-MCP screenshots, pre-admission scanning, immutable flow versions and Product Understanding coverage
- [provider-qualification.md](provider-qualification.md) — held-out SHKB/Fink fixtures, invariant provider contracts, hard scores, semantic review and external-host blind spots
- [lifecycle-hooks.md](lifecycle-hooks.md) — lifecycle events, hooks, the event bus + SSE live inspector
- [web-mutations.md](web-mutations.md) — the inspector's write boundary (structural writes vs host-authored text)
- [keyboard-conventions.md](keyboard-conventions.md) — the cross-surface keyboard contract
- [i18n.md](i18n.md) — bilingual chrome + the `register_strings` extension seam
- [pagination.md](pagination.md) — cursor pagination (MCP) + `?page`/`?q` web lists
- [persona-readiness.md](persona-readiness.md), [grounding.md](grounding.md), [calibration.md](calibration.md), [embeddings.md](embeddings.md) — persona lifecycle, evidence, prediction quality, recall
- [product-telemetry.md](product-telemetry.md) — provider-neutral semantic events, privacy boundary and hosted outbox adapter
- [substrate.md](substrate.md), [artifact-inventory.md](artifact-inventory.md), [project-assets.md](project-assets.md), [opt-in-aggregation-design.md](opt-in-aggregation-design.md)
- [design-delivery.md](design-delivery.md) — sanitized workspace PowerPoint masters and the provider-neutral MCP research-to-design hand-off
- [taxonomy-audit-current-primitives-forms.md](taxonomy-audit-current-primitives-forms.md) — current primitive/form inventory, aliases, migration owners and compatibility requirements
- [taxonomy-registry-schema.md](taxonomy-registry-schema.md) — machine-readable primitive/form registry contract and validation rules
- [taxonomy-backcompat-migration.md](taxonomy-backcompat-migration.md) — lazy migration plan for old records, URLs, MCP tools and stores
- [flow-walkthrough.md](flow-walkthrough.md), [live-walkthrough-safety.md](live-walkthrough-safety.md), [selective-live-actuation.md](selective-live-actuation.md)
