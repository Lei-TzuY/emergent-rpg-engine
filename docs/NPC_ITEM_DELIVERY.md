# NPC Item Delivery

Milestone 28 adds deterministic, replayable owner-to-owner item delivery without giving the NPC planner remote receiver-location knowledge or introducing another inventory store.

## Authority path

```text
canonical deliver_item goal
+ source NPC inventory
+ configured delivery rendezvous
+ source-owned mapped topology
→ NPCPlanningContext
→ deterministic route toward rendezvous
→ intended receiver must become locally visible/co-located
→ NPCDeliverIntent
→ deterministic resolver
→ NPCItemDelivered(source, receiver, item, goal)
→ generic event validation
→ atomic canonical custody transfer
→ NPCGoalCompleted(delivered_item)
→ persistence / replay
```

The configured `delivery_location_id` is part of the goal contract. The planner routes toward that location through the same bounded knowledge-scoped navigation used by earlier milestones; it does not inspect the receiver's remote live location. If the source reaches the rendezvous and the receiver is absent, the planner idles rather than omnisciently chasing the receiver.

`NPCItemDelivered` is the typed owner-to-owner handoff transition for this milestone. It changes the existing canonical `Item.owner_id` and source/receiver inventories atomically; no delivery inventory, hidden parcel state, or second custody store exists. The event carries exact source, receiver, item, and goal provenance.

## Validation

A delivery is accepted only when all of the following hold:

- the source is the configured NPC for an incomplete `deliver_item` goal;
- the item, receiver, and rendezvous location are valid canonical references;
- required source knowledge for the goal is satisfied;
- source and receiver are alive, conscious, distinct, and physically co-located;
- the handoff occurs at the configured rendezvous;
- the source canonically owns the portable item and carries it in inventory;
- the receiver does not already contain the item.

The generic event validator repeats these checks for forged `NPCItemDelivered` events. Delivery goal completion additionally requires the receiver to own the evidence item and the source to no longer carry it.

Item-location beliefs remain observer-specific memory. A handoff does not globally synchronize another NPC's stale location belief merely because canonical custody changed.

## Verification evidence

Implementation candidate `7fbe17d0bfa79dadf3056634e17e5649e9801a32` passed:

- standard wheel build and packaged browser-asset verification;
- Ruff;
- strict mypy across 47 source files;
- **185 pytest tests**;
- the seeded 1,000-accepted-turn consistency evaluation;
- JSON report verification.

Focused regressions cover multi-hop Bunkhouse → Yard → Operations → Archive rendezvous travel, no premature goal completion, exact handoff provenance, unique custody after delivery, remote/wrong/inactive receiver rejection, wrong-location/source-without-item/nonportable rejection, forged delivery and forged completion rejection, required-fact gating, stale private-belief isolation, explicit SQLite persistence/restart/replay, and off-screen simulation under the ordinary NPC action budget.

For seed `20260911`, the long-run gate produced 1,058 submissions, 1,000 accepted turns, 58 deterministic rejections, 2,274 events, 1,058 persisted turns, 1,000 episodes, and final canonical clock minute 4,361. Replay equality, state validity, monotonic clock/player knowledge/event log, item ownership, and unique event IDs all remained true with `failures=[]`. The default long-run workload does not contain a delivery goal, so M28 behavior is established by the focused integration regressions rather than by a changed event count.

## Promotion boundary

Milestone 28 gives NPCs a replayable handoff path, including delivery to the player when the player is the configured co-located receiver. The player action surface still has no reciprocal way to hand an owned item to an NPC: player actions are currently limited to move, inspect, talk, take, wait, and freeform.

The next coherent frontier is Milestone 29: **player-to-NPC item handoff / quest turn-in**. It should add a typed player `GiveAction` and deterministic parser/resolver path, require a locally visible active intended receiver and canonical player custody, reuse the same item ownership invariants rather than inventing another inventory store, remain transactional on rejection/provider failure, and expose no NPC-private state through parser/API/UI projections. Structured-provider parsing, deterministic command parsing, persistence/replay, and the existing 1,000-turn gate must remain green.