# Replayable NPC map learning

Milestone 18 closes the gap between transient local observation and canonical NPC route knowledge. NPCs no longer have to rely entirely on world-pack-preconfigured `mapped_locations`: accepted autonomous actions can now create typed, validated, replayable map observations.

## Canonical authority

Map learning is represented by the ordinary domain event:

```text
NPCLocationMapped(npc_id, location_id)
```

The planner never mutates `NPCKnowledge.mapped_locations` directly. A valid event must identify an existing NPC and location, the NPC must be alive and conscious, and the NPC must physically occupy the mapped location at validation time. Mapping an already-known location is rejected rather than creating redundant log churn.

The reducer changes only the named NPC:

```text
validated NPCLocationMapped
→ NPC.knowledge.mapped_locations.add(location_id)
→ ordinary persistence / replay
```

No player knowledge, other NPC knowledge, location topology, or item state is changed by the mapping event.

## Observation timing

Milestone 18 deliberately does not turn every simulation cycle into a broad NPC observation sweep. Mapping events are attached only to an already accepted NPC intent, preserving the existing global attempted-action budget.

For movement:

```text
accepted NPCMoveIntent
→ map current location if fresh
→ NPCMoved
→ map arrival location if fresh
→ optional final NPCGoalCompleted
```

The arrival observation comes after `NPCMoved`, so the physical-presence validator sees the NPC at the destination. An intermediate multi-hop step therefore learns both the location being departed and the location actually reached without introducing a teleport or route-level event.

For accepted inspection or an already-satisfied reach goal, the NPC maps only its current location before the ordinary inspection/completion events. Rejected intents produce no map-learning event.

## Provenance and monotonicity

`validate_state()` enforces map knowledge as an append-only observer-specific capability:

- every mapped location must exist in canonical world topology;
- previously mapped locations cannot disappear;
- every newly added `(npc_id, location_id)` relative to the previous state must have a matching `NPCLocationMapped` in the same transition;
- direct mutation of `mapped_locations` without event provenance is rejected;
- a forged event for a remote location is rejected before reduction.

Explicit `run_npc_phase()` passes its emitted events into final-state provenance validation. Automatic off-screen simulation already aggregates NPC events into the player-turn simulation event list, so the same proof applies to both execution paths.

## Epistemic boundary

The event records what one NPC actually observed; it does not expose the fact to the player or another NPC. In the demo, an off-screen Dax movement can map Bunkhouse and Yard while Lio remains unmapped when he is co-located with the player and therefore skipped by automatic simulation.

Provider narration remains outside the authority path. A narration failure happens before scheduled NPC simulation, so no map observation can be committed as a partial side effect of a failed player turn.

## Verification evidence

The first fully green Milestone 18 implementation head passed:

- wheel build and packaged browser-asset verification;
- Ruff;
- strict mypy across 45 source files;
- **119 pytest tests**;
- the seeded 1,000-accepted-turn consistency evaluation and JSON verifier.

Focused tests cover remote and duplicate observation rejection, direct-state mutation without provenance, map-memory monotonicity, invalid location references, current/arrival event ordering, idempotence for already-known locations, acting-NPC-only learning, SQLite restart and replay equality, off-screen simulation isolation, and provider-failure atomicity.

For seed `20260911`, the long-run gate produced 1,058 submitted actions, 1,000 accepted turns, 58 deterministic rejections, **2,272 events**, 1,058 persisted turns, 1,000 episodes, and final canonical clock minute 4,361. Replay equality, state validity, monotonic clock/player knowledge/event log, item ownership, and unique event IDs all remained true with `failures=[]`.

The event count is two higher than Milestone 17 because the long-run scenario now persists two real off-screen Dax map observations. These figures are deterministic correctness evidence, not performance measurements.

## Promotion gate for Milestone 19

The next epistemic gap is item pursuit. `investigate_item` currently works only when the target item is already visible at the NPC's current location or in its inventory. Giving the planner direct access to `WorldState.items[target].location_id` would violate the same non-omniscience boundary that Milestones 17–18 established for navigation.

Milestone 19 should therefore add observer-scoped, replayable item-location knowledge before expanding pursuit behavior:

```text
local visible item observation
→ typed NPC item-observation event
→ canonical NPC item-location belief
→ NPCPlanningContext receives only that NPC's beliefs
→ investigate_item may route through known topology toward remembered location
→ local re-observation validates or corrects stale belief
→ ordinary local inspect when item is actually accessible
```

Acceptance criteria should require that item-location beliefs come only from local visibility or ownership, never from global item truth; a planner can pursue a remotely remembered item only through its known map; stale beliefs are not automatically updated when another actor moves the item; arriving at the remembered location must use local observation to confirm, update, or invalidate the belief; forged remote observations and cross-NPC knowledge transfer are rejected; and persistence/restart/replay plus the existing 1,000-turn continuity gate remain green.