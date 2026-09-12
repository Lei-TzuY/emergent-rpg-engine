# Replayable NPC fact sharing

Milestone 20 adds explicit NPC-to-NPC information exchange without turning prose, planner output, or background simulation into a knowledge authority.

## Executable surface

Run a bounded social phase with:

```bash
emergent-rpg npc-social-step --max-actions 3
```

The command resolves the selected/latest SQLite session, executes `GameEngine.run_npc_social_phase()`, prints accepted/rejected social decisions, and persists the resulting canonical state/events atomically when material events exist.

Ordinary `npc-step` goal execution and automatic off-screen world simulation remain unchanged. Social sharing is deliberately explicit rather than an automatic fallback that can consume movement/investigation action budget.

## Authority path

```text
source NPC's own known facts + locally visible NPC ids
→ social planner selects receiver only
→ NPCShareFactIntent(receiver_id)
→ deterministic resolver reads canonical source/receiver knowledge
→ lexical first source-known / receiver-unknown fact
→ NPCFactShared(source_npc_id, receiver_npc_id, fact_id)
→ generic event precondition validation
→ reducer updates receiver facts_known only
→ receiver-scoped mystery inference
→ final world validation
→ SQLite event/state/turn commit
→ replay
```

The intent intentionally carries no `fact_id`. The planner therefore cannot invent a fact, select one it does not know, or inspect the receiver's private fact set. The resolver remains the authority that chooses a concrete shareable fact from canonical state.

`NPCFactShared` is independently rejected unless:

- source and receiver are distinct existing NPCs;
- both are alive and conscious;
- both occupy the same location;
- the fact exists;
- the source already knows the fact;
- the receiver does not already know it.

The reducer changes only `receiver.knowledge.facts_known`. Player knowledge, route maps, item-location beliefs, relationships, inventories, and objective fact truth metadata are not copied by a share event.

## Inference and persistence

After a successful share, the engine evaluates deterministic mystery inference for the receiver using the receiver's post-share knowledge. Any derived conclusions are ordinary `FactInferred` events with existing rule/premise provenance. The source does not inherit receiver-only conclusions.

A social phase has its own bounded attempted-action budget and persists through the same SQLite store used by ordinary turns. Restart and event replay must reconstruct the same canonical state.

## Regression discovered during implementation

The first implementation made sharing a fallback inside ordinary NPC planning. Full pytest exposed four real regressions: blocked/unresolved/completed goals no longer idled, and social actions could consume ordinary NPC action budget ahead of multi-hop navigation.

The fix was architectural rather than a test expectation change: ordinary goal planning and automatic background simulation retained their previous semantics, while sharing moved into the explicit separately bounded social phase.

## Verification evidence

The final executable implementation candidate passed:

- standard wheel build and packaged browser-asset verification;
- Ruff;
- strict mypy across 45 source files;
- **134 pytest tests**;
- the seeded 1,000-accepted-turn consistency evaluation;
- machine-readable JSON report verification.

For seed `20260911`, the long-run gate produced 1,058 submitted actions, 1,000 accepted turns, 58 deterministic rejections, 2,272 events, 1,058 persisted turns, 1,000 episodes, and final canonical clock minute 4,361. Replay equality, state validity, monotonic clock/player knowledge/event log, item ownership, and event-id uniqueness were all true with `failures=[]`.

The unchanged 2,272-event long-run count is expected: the seeded player-action scenario does not invoke the explicit social phase. M20 behavior is therefore proven by focused engine/validator/CLI persistence regressions while the existing long-run gate proves no continuity regression in the normal player/simulation workload.

## Promotion boundary

The next architectural gap is selective disclosure policy. Relationships are already canonical and replayable, but M20 intentionally does not use trust to decide which facts may be shared. Milestone 21 should make disclosure data-driven and relationship-sensitive without giving the planner access to receiver-private knowledge or weakening event validation.
