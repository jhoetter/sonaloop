# Screen walkthrough playbooks — drop-off testing, artifact-first

The killer use-case: a persona walks through a real onboarding flow or
prototype and shows exactly where it drops off. ~80% of that value is more
reliable via reaction-to-artifacts than via live app control, so this path
needs **no browser anywhere** — the playbook is made of real screens the host
actually looks at.

In UI language this is a **screen walkthrough playbook**: a reusable plan for a
session. The service/storage name is still `flow` for compatibility, and the
service fidelity value is
still `artifact` for compatibility, but it does not mean "any artifact"; the
playbook is surfaced in `/playbooks`, and its replayable traces surface as
sessions.

## The playbook

```
attach_asset(project, "welcome.png") …            # the screenshots become evidence assets
define_flow(project, "Onboarding v2",
            steps=[{asset_id, caption?}, …])      # the ORDERED flow, citable per step
brief_flow_walkthrough(persona, project, flow)    # persona context + the ordered screens
   ↓   the HOST view_asset()s every screen (real pixels) and authors the timeline
record_usability_session(subject={kind:'flow', id}, fidelity='artifact', …)
   ↓   friction per step, dropoff_step + reason, predicted_behaviors with likelihoods
flow_funnel(project, flow)                        # the segment view
```

- **Defining**: steps reference the project's image/screenshot assets
  (`attach_asset` / `attach_prototype_shot` first); captions default to asset
  titles; a stable `key` makes re-definition an idempotent upsert. Document
  assets are rejected — personas react to pixels.
- **Walking**: the brief carries the persona's loaded context plus per-step
  `view_asset(...)` calls. The host looks at each screen before reacting,
  records one timeline step per screen, sets `outcome.dropoff_step` where this
  persona would genuinely bail (the reason lives in that step's verdict), and
  authors `predicted_behaviors` on the canonical likelihood scale.
- **The funnel**: `flow_funnel` aggregates every session of the flow —
  per step entered / continued / dropped, the drop reasons, the dropping
  personas, the step captions, and a `biggest_dropoff` headline:
  *where the segment abandons, and why*.

## Downstream

Walkthrough predictions are scoreable: point `record_prediction_outcome` at a
session's prediction (`{kind:'session', id, anchor:'pb1'}`) when the real
funnel data arrives — the walkthrough feeds the calibration loop
(docs/calibration.md). Live actuation is the separate, complementary path
(the walkthrough/live modules); this one works from artifacts alone.

CLI: `flow-define <json>`, `flows-list`, `flow-funnel`.
