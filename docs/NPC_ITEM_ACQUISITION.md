# Autonomous NPC item acquisition

Milestone 27 turns item pursuit into physical custody without creating a second inventory authority. NPCs can now configure an `acquire_item` goal, pursue the target using only their own replayable item-location belief and known topology, take a locally visible portable target through the existing `ItemAcquired` event, and complete the goal only after canonical ownership proves the item is actually in their inventory.

## Authority boundary

```text
NPCGoal(kind="acquire_item", target_id)
+ acting NPC own facts / item-location belief / known routes
→ deterministic NPC planner
→ move / local stale-belief search / NPCAcquireIntent
→ deterministic NPC resolver
→ ordinary ItemAcquired
→ NPCItemLocationObserved(present=False)
→ NPCGoalCompleted(method="acquired_item")
→ validation / persistence / replay
```

The planner never receives authoritative remote `Item.location_id`. It can act immediately on a locally visible target, complete an already-satisfied goal when the item is already in the NPC inventory, or navigate toward its own remembered location through the existing bounded known-route graph. A stale memory remains allowed: reaching the remembered location and finding the item absent follows the existing local-search path and clears only that observer's belief.

`ItemAcquired` remains the only custody mutation used by both player and NPC acquisition. The generic event validator independently requires an existing alive/conscious actor, an existing item at the actor's physical location, matching event origin, an unowned source item, and the `portable` flag. Owned-item transfer is still rejected; Milestone 27 does not silently introduce handoff semantics. Player `take` now performs the same portability rejection before emitting the event, preserving deterministic resolver failure rather than turning a normal impossible action into a transition exception.

After local NPC acquisition, a typed negative `NPCItemLocationObserved` removes the now-stale ground-location belief, and `NPCGoalCompleted(method="acquired_item")` is accepted only when the target's canonical `owner_id` and the NPC inventory both prove custody. The goal-prerequisite gate from Milestone 26 remains active for planning, forged intents, passive item observations, and goal completion.

## Regressions found and fixed

The first candidate exposed a strict-mypy control-flow issue because a local completion method widened to `str`; it was fixed with an explicit `Literal["reached_location", "acquired_item"]` annotation rather than an ignore.

The next candidate exposed a backwards-compatibility regression in the existing Milestone 19 investigate-item rejection text after acquisition and investigation had been partially generalized. The production resolver was corrected so `investigate_item` preserves its existing rejection contract while `acquire_item` has acquisition-specific reasons. Existing tests were not weakened.

## Verification evidence

The fully green Milestone 27 implementation head `2e67bb2b132c6a67fb3d56b67f866dd3df308312` passed:

- standard wheel build and packaged browser-asset verification;
- Ruff;
- strict mypy across **47 source files**;
- **175 pytest tests**;
- the real seeded 1,000-accepted-turn consistency evaluation and JSON verifier.

For seed `20260911`, the long-run gate produced 1,058 submitted actions, 1,000 accepted turns, 58 deterministic rejections, **2,274 events**, 1,058 persisted turns, 1,000 episodes, and final canonical clock minute 4,361. Replay equality, state validity, monotonic clock/player knowledge/event log, item ownership, and event-id uniqueness were all true with `failures=[]`.

Focused regressions cover local acquisition, remote pursuit using private memory, stale-belief correction, already-owned completion, forged remote/non-portable/owned acquisition events, forged acquisition completion, knowledge-gated acquisition, player portability parity, SQLite restart/replay, and automatic off-screen simulation.

These are correctness results, not performance measurements.

## Promotion boundary

Milestone 27 gives NPCs custody but deliberately rejects transfer from an existing owner. The next coherent frontier is **Milestone 28: replayable item handoff / delivery goals**. The engine already carries `ItemAcquired.from_owner` and `ItemDropped`, but current validation explicitly forbids owned-item transfer.

Milestone 28 should introduce one canonical owner-to-owner handoff path rather than a second inventory store. A delivery-capable NPC must possess the item, reach or share a location with the intended receiver using existing knowledge-scoped navigation, and transfer custody only through a typed validated event with exact source/receiver/item provenance. The reducer must atomically remove the item from the source inventory and add it to the receiver inventory while preserving unique ownership. Forged remote transfers, dead/unconscious participants, source-without-item, wrong receiver, and duplicate ownership must be rejected. Item-location beliefs must not be globally synchronized merely because custody changed, and persistence/restart/replay plus the existing 1,000-turn continuity gate must remain green.