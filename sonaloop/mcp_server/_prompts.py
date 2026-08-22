"""Provider-agnostic MCP layer: server `instructions` + workflow `prompts`.

The `claude-skills/` are Claude-Code-specific packaging (SKILL.md + subagent fan-out). The portable
equivalent lives HERE, in the MCP server itself — the one surface EVERY host reads:

  - SERVER_INSTRUCTIONS is returned in the `initialize` response; most hosts inject it into the model
    context automatically, so any client (Claude, Cursor, ChatGPT, …) gets the operating contract.
  - The prompts below are the cross-provider equivalent of skills: ready playbooks any MCP host can
    list + run. They describe a SEQUENTIAL single-agent core that works everywhere; parallel sub-agent
    fan-out is an optional acceleration where the host supports it (the methodology is identical).

Canonical knowledge still lives in AGENTS.md / spec/; this module is the machine-delivered projection.
"""
from __future__ import annotations


SERVER_INSTRUCTIONS = """\
Sonaloop simulates customer personas and runs memory-grounded councils, prototypes, and \
design-research syntheses. It is MCP-first; the web inspector (sonaloop-web, http://127.0.0.1:8787) \
is read-only.

How to operate (every host):
- THE FRONT DOOR: when the user asks a research question (an HMW, "explore X", "what would \
users think of Y"), that question IS the assignment to run a research project end-to-end \
(personas -> start_project -> the governed run loop below) — never answer it from your own \
knowledge, even if it arrives as a bare one-line prompt. Your brainstorm is a hypothesis; the \
personas' grounded reactions are the product. For the cohort, check the curated catalog FIRST \
(300+ ready-made personas with lived memory: catalog_search / catalog_recommend -> catalog_pull); \
author new personas only for what the catalog lacks.
- CLOUD FRONT DOOR (feature-detect): if this host exposes `begin_research_job`, use exactly that ONE
external call to create the cloud job + governed run. Pass the user's full initial request, one stable
non-sensitive `operation_id`, and `methodology` (`auto`, `freeform`, or an exact methodology name/key).
On timeout/transport failure repeat the exact same `begin_research_job` call with the exact same inputs;
never recover by calling start_project/start_run separately or by minting another operation_id. Only
when `begin_research_job` is absent use the core start_project -> start_run fallback below.
- YOU (the agent) author ALL text. Sonaloop never calls a text LLM. Each generative step follows one \
contract: call a `brief_*` tool to gather context -> you author the JSON -> call the matching \
`record_*`/`put_*` tool to validate + persist. OPENAI_API_KEY (optional) is used only for avatar \
images and embedding-based recall.
- Before speaking from a persona's perspective, load its context via `prepare_persona_agent_context` \
(SOUL + memory + recall). Never invent persona facts.
- Be non-directional: do not steer personas toward any product thesis unless their own source, \
evidence, calendar, or the explicit task supports it. Skepticism, indifference, and rejection are \
valid outcomes.
- Author analysis prose as Markdown (no ALL-CAPS, no literal section headers -- the UI renders those). \
A persona's statement text stays in that persona's natural voice (it is a quote).
- Generated content follows the language the user writes in (auto-detected, then persisted).
- Multi-step projects run on the GOVERNED loop, never on your own sense of "enough": \
start_project(operation_id=<stable create-intent key; reuse on retries>) -> \
start_run(project_id, operation_id=<stable run-create key; reuse on retries>) \
-> loop run_step(run_id) -> execute each dispatch with its exact `dispatch_token` -> persist through
the token-aware recorder, which auto-links + auto-checkpoints. Do NOT manually checkpoint again when
the recorder reports dispatch.checkpointed=true. Continue until run_step returns kind=='done'. Gates
passed != finished — a project is DONE \
only when `assess_project.finish.finished` is true and the required completeness critics pass. Never stop \
silently at a phase boundary ("Discover and Define are complete" is the START of the second \
diamond, not an ending). If your session must end mid-run, say so explicitly and hand off the \
resume call: start_run(project_id, run_id=<open run>) replays the journal with no lost work.
- REACTION TEST integrity: before any persona reaction, inspect real target material and complete the
Product Understanding preflight (target + explicit revision/time + routes/flows/states + capability
postures observed_present|observed_absent|inferred|unknown + exact project evidence refs). Unknown is
better than a guessed absence; observed_absent additionally needs a documented verification attempt.
Next author the initial evidence-grounded research frame; its real questions and hypotheses are
server-bound inputs to the structured Cohort Integrity preflight that follows. The server separates independent target
context (persona facts/events/evidence predating the project) from product stimulus, reports versioned
depth/source/age and lexical-overlap features, and may accept an optional provider-neutral semantic
feature. A thin/circular cohort injects required deepening/reselection work. Declare at least one
skeptical, indifferent or non-target countervoice with an exact basis quote and cited independent
pre-project persona fact/event/evidence; an unverified host label fails closed. The council must
include that persona and an explicit matching non-positive structured stance. Never reinterpret a failed status from prose;
an override needs an explicit rationale and remains visible in report limitations.
Councils/reports must inventory factual claims with posture observed|memory_grounded|inferred|simulated|
unsupported and refs. A screenshot proves product state, never observed user behavior; `observed`
behavior requires an exact step anchor in a grounded verified session. Uncovered prose/unsupported
claims stay visible as a hypothesis draft and cannot close the gate.
- Ready playbooks are exposed as MCP prompts: run_council, synthesize, design_thinking, \
compose_research_plan, autonomous_research_run (resume). Browse every tool via the \
`sonaloop://guide/catalogue` resource.
- Parallelism: if your host supports parallel sub-agents, fan out independent work (one per persona / \
per angle) and persist sequentially; otherwise run the same steps sequentially -- the methodology is \
identical.
- Invocation ladder (don't probe, don't give up at "command not found"): (1) these MCP tools when the \
`sonaloop` server is connected -- the richest surface; (2) else, from the repo checkout, \
`uv run sonaloop <cmd>` (no install needed -- uv resolves the project venv); (3) no uv? \
`python -m sonaloop.cli <cmd>` from the checkout; (4) only if a step fails for missing deps, \
`uv sync` once and retry. Never install globally unless the user asks. The CLI and MCP are the \
SAME service surface (incl. the governed run loop: run-start/run-step/run-checkpoint).
"""


def getting_started() -> str:
    """The agent-facing getting-started guide — printed by `sonaloop guide`.

    The operating contract (same as the MCP instructions, so CLI-driven agents that never see the MCP
    `instructions` get the identical rules) plus a concrete first-run recipe."""
    return (
        SERVER_INSTRUCTIONS
        + "\n"
        "First run (drive via the `sonaloop` CLI, or the MCP tools of the same name):\n"
        "1. Start the inspector in the background: `sonaloop-web` -> open http://127.0.0.1:8787.\n"
        "2. Create a persona (host-authored): `sonaloop brief-persona \"<who they are>\"` -> YOU write the\n"
        "   profile JSON from that briefing -> `sonaloop record-persona profile.json`. Repeat for a few.\n"
        "3. (Optional) simulate some life: `sonaloop brief-day <slug> --date <YYYY-MM-DD>` -> author the\n"
        "   day JSON -> `sonaloop record-day <slug> <date> day.json`.\n"
        "4. Run a council: pick personas, gather with `sonaloop brief-council \"<question>\" --personas …`,\n"
        "   author each persona's statement in character, then `sonaloop record-council council.json`.\n"
        "   (Or use the `run_council` / `synthesize` / `design_thinking` MCP prompts as ready playbooks.)\n"
        "5. Tell the user to watch it all at http://127.0.0.1:8787 (read-only inspector).\n"
    )


def register_prompts(mcp) -> None:
    """Register the provider-agnostic workflow prompts on the FastMCP server."""

    @mcp.prompt(title="Run a memory-grounded council",
                description="Personas react to a topic grounded in their own memory; optional moderated debate.")
    def run_council(topic: str) -> str:
        return f"""\
Run a memory-grounded council on: {topic}

For each participating persona (parallel if your host supports sub-agents, else sequentially):
1. Load context: prepare_persona_agent_context(persona, task=the council question).
2. Reflect: does this genuinely connect to something concrete in the persona's memory? If yes, do 1-2
   targeted recall_memory lookups; if not, answer from the loaded context (over-researching is as wrong
   as never researching). Aim for 0-2 lookups, driven by the persona's judgement.
3. React in character -- support, skepticism, indifference, or rejection are all valid; never force
   approval; no vendor tone. Author a `statement`: {{persona_id, text (Markdown, in voice),
   stance:{{value -2..2, label?: support|conditional|neutral|skeptical|oppose}} (the closed scale --
   see suggest_stances), about:{{kind:"prompt", id}}, refs:[{{kind:"memory", text}}, ...]}}.

Optional moderated back-and-forth (rich topics): after the openings, author a mediator `finding`
(kind "summary") that names the sharpest tensions and selects who replies next; run 1-2 directed rounds
(strategy: positive-deepdive | pain-discovery | tension | goal); use hand-raising to stop when the
energy is spent (never loop unbounded).

Then (host): author proposal, votes (the same stance-scale terms: support|conditional|neutral|skeptical|oppose),
a short summary, and a rich
Markdown exec_summary, and persist with record_council(...). For a Reaction Test first complete the
Product Understanding, initial research frame, and final Cohort Integrity preflight; include a declared countervoice in the council,
cite its independent basis in the preflight, express its matching structured stance, cite the admitted stimulus, and pass a `claims` inventory whose every
summary assertion declares observed|memory_grounded|inferred|simulated|unsupported + refs. Synthetic
persona reactions are `simulated`; a screenshot never proves observed behavior. brief_council(prompt) returns candidate
personas; brief_council(prompt, persona_ids) returns each one's loaded context to author against.
Modes: DISCOVERY (questions + one statement per persona*question), EVALUATION (proposal + stances),
DECISION (+ votes). Point the user to the web inspector to read the result.
"""

    @mcp.prompt(title="Synthesize across iterated councils",
                description="Iteratively run councils from a statement+goal until enough insight; one growing report.")
    def synthesize(statement: str, goal: str) -> str:
        return f"""\
Drive an iterative synthesis until the goal is met.

statement (under study): {statement}
goal (what to learn): {goal}

Loop (cap ~10 councils):
- Derive a SELF-CONTAINED question from the statement (round 1).
- Run a council on it (see the run_council prompt; pass a strategy if useful).
- brief_synthesis(chain_of_council_ids, title, start_input=statement, goal) -> author + record_synthesis(
  ..., goal, synthesis_id=previous_id) for one growing report.
- If status == "done" (goal reached / diminishing returns) stop; else take next_council_question and repeat.

Hard rule: personas are STATELESS across councils -- every next question must stand alone (include the
essential briefing + the precise new angle); never write "building on the last council". Cross-reference
councils by id; never copy their voices verbatim. When the report is complete, call
brief_presentation(id, audience, duration) -> author a decision-led presentation_plan.v1 from the
methodology profile, evidence, personas and assets -> record_presentation_plan(id, plan, stable
operation_id) -> export_synthesis(id). The presentation is a visual meeting story with native speaker
notes and a detail appendix, not one slide per report section. The report remains the complete answer.
"""

    @mcp.prompt(title="Run a Double-Diamond design-thinking project",
                description="Drive a How-Might-We through Discover/Define/Develop/Deliver over the plan engine.")
    def design_thinking(how_might_we: str) -> str:
        return f"""\
Run a Double-Diamond design-thinking project on: {how_might_we}

Use the plan engine as the spine, on the GOVERNED loop. If the host exposes begin_research_job, call
that ONE cloud front door with the full HMW, methodology="double_diamond", and one stable operation_id;
repeat the exact call on transport retry and do not separately call start_project/start_run. Otherwise:
start_project(... same stable operation_id) -> start_run(... stable run operation_id). Then loop
run_step(run_id). Execute each analyze|act|verify dispatch with its exact dispatch_token: author the
step grounded in next_action and persist via the token-aware recorder (automatic evidence link + task
checkpoint; do not checkpoint it again when dispatch.checkpointed=true). Verify also records its gate
judgment with the same token. A verify dispatch with step_id="__report_handoff__" is special: follow
its blocking_action, keep its exact report_id + dispatch_token, and iterate
brief_synthesis_section → record_synthesis_section for every incomplete_section_id. Do not create a
second report; only the final authored section checkpoints, after which you call run_step again. For
critic dispatches author
the completeness verdict via record_completeness_critic + record_critic_round) until run_step returns
kind=='done'. The engine — not your judgment — ends the run: gates passed != finished, and "Discover
and Define are complete" is the midpoint, not an ending. assess_project is the pulse along the way.
After the engine is done and its report exists, brief_presentation -> author +
record_presentation_plan -> export_synthesis for the stakeholder hand-off.

- Discover -> Define: frame user-research questions grounded in persona memory -> a FEW real
  multi-persona councils (run_council) -> synthesize key problems + a sharp POV (the surprising core
  segment). Not one micro-council per persona.
- Develop -> Deliver: ideate -> build a few VARIED prototypes (scaffold_prototype; lo -> mid -> hi
  fidelity) -> proband test sessions (record_prototype_session, grounded) -> down-select -> a final,
  evidence-backed synthesis/report answering the HMW (who wins, deliberate non-targets, validated pain
  solvers, the build spec).

Fan out act steps in parallel if your host supports sub-agents; otherwise run them sequentially. All
text host-authored via MCP; no in-process LLM.
"""

    @mcp.prompt(title="Compose & run a research plan (front door)",
                description="Take any plain research/design request end-to-end: design a plan, seed it, run it.")
    def compose_research_plan(request: str) -> str:
        return f"""\
Front door for any research/design request -- take it end-to-end.

request: {request}

1. Design the plan yourself: decide which methods to stitch together (councils, prototypes, affinity
   clustering, proband sessions, syntheses, sections) and in what analyze -> act -> verify shape. Fit it
   to the request; do not force a fixed template.
2. Seed it: when `begin_research_job` is exposed, call that ONE cloud front door with the full request,
   methodology=auto|freeform|exact name and one stable operation_id; repeat that exact call on a retry
   and never also call start_project/start_run. Otherwise use start_project(title, goal=request,
   methodology=..., operation_id=<stable key>) and start_run(... stable run key). Add tasks as needed.
3. Run it to a documented result on the GOVERNED loop, then loop
   run_step(run_id) -> execute each dispatch (author the step grounded in cited persona memory + prior
   syntheses -> pass its exact dispatch_token to the output recorder; linking/completion/checkpoint are
   automatic when dispatch.checkpointed=true; critic dispatches author the
   completeness verdict) until run_step returns kind=='done'. Do NOT freestyle next_action and stop
   when it feels answered: gates passed != finished — done means `assess_project.finish.finished` is
   true and the critic passed. Organize with sections; conclude with a synthesis/report. If the
   session must end mid-run, say so and hand off start_run(project_id, run_id=...) to resume.

Everything host-authored via MCP; no in-process LLM. Parallel sub-agents optional -- the loop is the
same sequentially.
"""

    @mcp.prompt(title="Resume an autonomous research run",
                description="Continue an existing project's run to DONE — the resume front door for any host.")
    def autonomous_research_run(project_id: str) -> str:
        return f"""\
Resume/continue the autonomous run of project {project_id} until the ENGINE says done.

1. Orient: assess_project({project_id}) — the recommendation, open gates, gaps and finish state.
2. Attach the governed loop: start_run({project_id}, operation_id=<stable run-create key>) — if the
   initial response is ambiguous, reuse that key; a known open run is resumed with run_id
   (journal replay, no lost work); otherwise a fresh run object is created.
3. Loop: s = run_step(run_id)
   - s.kind == 'done'   -> the run is over (finished | capped | stopped). Only THIS ends the run.
   - s.kind == 'critic' -> author the completeness verdict from s.brief (independent judgment) ->
     record_completeness_critic + record_critic_round; the engine injects each missing gap as work.
   - s.step_id == '__report_handoff__' -> follow s.blocking_action with the exact report_id and
     dispatch_token; brief + author each incomplete section, then run_step again. Never create a
     replacement report, and do not manually checkpoint the partial draft.
   - else (analyze|act|verify) -> author ONE step grounded in s.next_action and pass s.dispatch_token
     into every write. Analyze: record_frame (or record_product_understanding when requested).
     Act/verify: persist the output primitive; token-aware recorders link it and checkpoint automatically.
     Verify records the gate judgment with the same token. Only call checkpoint_step manually when the
     recorder explicitly reports checkpointed=false after all required writes are present.
4. Gates passed != finished: keep looping until `assess_project.finish.finished` is true (organized
   sections + a substantial terminal synthesis + the meta-report) AND the critic passes.

Never conclude at a phase boundary, never report done early; if the session must end mid-run, state
it and hand off start_run({project_id}, run_id=...) so the next session continues seamlessly.
"""
