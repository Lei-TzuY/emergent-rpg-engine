# Knowledge-gated reactive NPC goals

Milestone 26 makes NPC goal eligibility a deterministic projection of each NPC's own canonical knowledge rather than a mutable activation flag or a planner-side guess.

## Authority boundary

`NPCGoal.required_fact_ids` is canonical world-pack data. The field defaults to an empty set, so existing goals remain immediately eligible. For a configured prerequisite set, a goal is active only when every required fact is present in the acting NPC's own `knowledge.facts_known`.

```text
NPC own facts + configured goals
→ filter completed and knowledge-dormant goals
→ deterministic priority/id ordering
→ typed NPC intent
→ resolver repeats prerequisite gate
→ ordinary movement / inspection / goal-completion events
→ reducer backstop before NPCGoalCompleted
→ persistence / replay
```

The planner does not inspect objective fact truth or another observer's knowledge. The deterministic resolver independently rejects forged intents targeting a dormant goal, and reduction refuses a forged `NPCGoalCompleted` while prerequisites are still unknown. World-model validation also rejects goal prerequisite IDs that do not reference configured facts.

Investigate-item goals do not receive passive item-observation side effects while dormant. Learning remains authoritative only through the existing fact discovery, inference, and sharing transitions.

## Simulation ordering

Automatic cadence keeps the existing order:

```text
ordinary off-screen NPC goal phase
→ off-screen social phase
→ SimulationCycleProcessed
```

Therefore a fact received during the social phase may activate a goal only for a later goal phase/cycle. It cannot retroactively cause an action in the ordinary phase that already ran in the same cadence slot.

## Verification evidence

The first complete implementation candidate `cb62a3445288a4defbc7f6e2a861f200916bdfdb` passed:

- standard wheel build and browser-asset verification;
- Ruff;
- strict mypy across 47 source files;
- 164 pytest tests;
- the real seeded 1,000-accepted-turn consistency evaluation and JSON verifier.

For seed `20260911`, the evaluation produced 1,058 submissions, 1,000 accepted turns, 58 deterministic rejections, 2,274 events, 1,058 persisted turns, 1,000 episodes, and final canonical clock minute 4,361. Replay equality, state validity, monotonic clock/player knowledge/event log, item ownership, and event-id uniqueness were all true with `failures=[]`.

Focused regressions cover cross-observer isolation, deterministic reprioritization after learning, forged intent/completion rejection, invalid world-pack references, explicit social-learning activation, next-cycle activation after off-screen social learning, SQLite restart, and replay.

## Promotion boundary

The next coherent frontier is autonomous NPC item acquisition / custody. NPCs can already remember, pursue, locally search, and inspect items, but they cannot take physical custody as a goal outcome. The next slice should reuse the existing `ItemAcquired` event rather than create a second inventory authority, add deterministic acquisition planning over observer-scoped item memory and known topology, independently validate forged acquisition events, and prove ownership/inventory consistency, restart/replay, off-screen simulation, and provider-failure atomicity.
