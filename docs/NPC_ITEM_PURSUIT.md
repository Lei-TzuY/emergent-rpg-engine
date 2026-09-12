# NPC Item Pursuit and Search

Milestone 19 extends NPC autonomy from route knowledge into observer-scoped item search without granting planners access to authoritative remote item state.

## Authority boundary

```text
local visible/inventory items + NPC item-location beliefs + known routes
→ NPCPlanningContext
→ deterministic investigate-item intent
→ deterministic NPC resolver
→ typed local observation / movement / inspection events
→ validation + reducer + persistence + replay
```

`NPCPlanningContext.known_item_locations` is copied only from the acting NPC's canonical `NPCKnowledge.item_location_beliefs`. The planner does not receive remote `Item.location_id`, another NPC's item beliefs, or a global item-search API.

## Replayable observations

`NPCItemLocationObserved` records a physical observation by one NPC at its current location. A positive observation may set or refresh that NPC's remembered location for the item. A negative observation may clear only a belief that currently points at the observed location.

The validator requires the NPC to exist, be alive and conscious, and be physically present at the observation location. Positive observations must match a ground item actually present there; negative observations require a matching stale belief and an item that is no longer there. State validation reconstructs the expected belief dictionary from transition events and rejects unproven mutation.

## Stale beliefs are intentional

Item-location memory is knowledge, not truth. If another actor moves an item while the NPC is elsewhere, the NPC's remembered location does not update automatically. The planner may therefore pursue a stale location through the NPC's already-known topology. Once the NPC reaches that location, an ordinary inspect intent becomes a local search; if the item is absent, the resolver emits a negative observation and leaves the investigation goal incomplete.

This behavior is deliberate: the engine models discovery and correction rather than remote clairvoyance.

## Pursuit behavior

For an `investigate_item` goal, deterministic planning follows this order:

1. If the item is locally visible or in the NPC's inventory, inspect it.
2. Otherwise, consult only that NPC's remembered item location.
3. If the remembered location is the current location, perform a local search so stale memory can be invalidated.
4. Otherwise, use the existing bounded deterministic navigation over `known_routes` to take one next hop toward the remembered location.
5. If no belief or no known route exists, emit no intent.

The resolver independently recomputes the expected next hop and rejects forged detours. Reaching a remembered location never completes an item-investigation goal by itself; only an accessible successful inspection may emit `NPCGoalCompleted(method="inspected_item")`.

## Observation scope

Accepted NPC actions may also notice configured investigation targets at the NPC's current location. Observation remains observer-specific: only the acting NPC's belief dictionary changes. Idle simulation scans do not create observation events merely because an NPC exists at a location, preserving the existing attempted-action budget semantics.

## Persistence and compatibility

`item_location_beliefs` is part of `NPCKnowledge` and has an empty default, so older serialized world states remain loadable without a SQLite schema migration. Observation events travel through the existing event table and ordinary replay pipeline.

Focused regressions cover remote-observation rejection, positive and negative observation, provenance enforcement, cross-NPC isolation, stale-belief pursuit and correction, forged pursuit moves, successful inspection, SQLite restart, and replay.

The first fully green implementation candidate (`7c5db0c819f01ef2fef1be6e47b7984e8a8a3706`) passed 127 pytest tests, strict mypy over 45 source files, Ruff, wheel/browser-asset verification, and the seeded 1,000-accepted-turn consistency gate. The long-run report remained 1,058 submissions / 1,000 accepted / 58 rejected / 2,272 events / 1,000 episodes with final canonical clock minute 4,361; replay equality and every tracked continuity invariant were true with `failures=[]`. These are correctness results, not performance measurements.

## Promotion gate

Milestone 20 should add replayable NPC-to-NPC fact communication rather than widening planners' private views. A fact-sharing transition must identify source and receiver, require physical co-location and a source that already knows the fact, reject duplicate/forged transfer, update only the receiver, and remain replayable. Communication should not bulk-copy route maps or item-location memories, and it must not grant player knowledge unless a separate player-facing interaction explicitly does so.
