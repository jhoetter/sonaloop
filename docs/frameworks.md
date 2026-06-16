# Frameworks — the processes a study runs through

A **Framework** is the second layer of the [Job → Framework → Format taxonomy](job-framework-format.md):
*the process a run follows end-to-end.* A Job runs **through** a Framework **using** Formats.

Frameworks already exist in the core as the methodology specs under
[`sonaloop/methodologies/*.json`](../sonaloop/methodologies/) (keyed by `key`); starting a study with
one **seeds the plan engine** (`start_project(methodology=<id>)` / `set_project_methodology`). This
page explains the concept; the inspector's **Methodologies** tab is the per-methodology catalogue.

Every Framework shares the same **rhythm**: it alternates **diverge** (explore broadly) and
**converge** (narrow to a decision). Double Diamond does it twice — once in the problem space, once
in the solution space; the others are variations on that beat.

## Consume this as structured data

The descriptions below are not just prose — they are produced from one structured accessor so the
website "how it works" page and the job presets draw on a **single source**:

```python
from sonaloop import job_taxonomy

job_taxonomy.framework_descriptions()
# -> [{id, name, what, when, stages: [{id, name, what}]}, ...]   (in taxonomy order)

job_taxonomy.get_framework_description("double_diamond")
# -> one {id, name, what, when, stages} entry
```

The same shape is exposed over MCP as **`list_frameworks`** and **`describe_framework`** (see
[the MCP surface](../README.md)). `what` is the one-line "what shape it is", `when` is "when to use
it", and `stages` is the ordered diverge→converge shape. The data is read live from the methodology
specs and joined with the canonical [`taxonomy.json`](../sonaloop/taxonomy.json), so ids and labels
stay in lock-step across the core, the website IA and the tracker.

## What a Framework contains

A Framework is a small DAG of named stages. Each stage declares:

- **Intent** — what the run is trying to learn or decide at this point.
- **Inputs** — which earlier stage or evidence it consumes.
- **Mode** — whether it opens the space broadly or converges behind a gate.
- **Evidence requirements** — e.g. minimum upstream inputs, prototype/session requirements, or a judgment gate.
- **Output role** — what kind of evidence or hand-off it produces for later stages.

That structure is deliberately open-tagged. Frameworks can name their own stages, tags and output
roles; the engine enforces the graph mechanics and evidence gates, not a fixed design-method
vocabulary.

## Choosing a Framework

The [taxonomy](job-framework-format.md) maps each **Job** to a default Framework. To run a study
through one explicitly:

```text
start_project(title=…, goal=…, methodology="lean_jtbd")   # seed the plan from this Framework
set_project_methodology(project_id, "double_diamond")     # or (re)bind an existing project
```

In the inspector, a running study shows its Framework + current stage on the **Plan** drawer
(`/projects/{id}/plan`). The sidebar's **Methodologies** tab (`/methodologies`) lists every
Framework with its own icon, page, process visualization, stages, and matching Jobs; the
**Documentation → Methodology** page remains the conceptual overview.
