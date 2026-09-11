# Scheduled world events and environmental state

Milestone 13 adds replayable non-NPC world consequences without introducing a background mutation path.

## Canonical schedule

Future environmental consequences live inside `WorldState.scheduled_location_conditions`. Each entry has:

- a unique schedule id;
- an absolute canonical world minute;
- a target location;
- a typed `LocationCondition` payload.

The queue is world data. It is not a wall-clock timer, process-local task, thread, cron job, or provider-side callback. Restarting the process does not change what is due because the schedule is persisted inside the same canonical state snapshot as the rest of the world.

## Deterministic execution

`DeterministicWorldEventScheduler` sorts pending entries by `(due_absolute_minute, id)`, selects only entries whose due minute is at or before the canonical world clock, and caps processing with `SimulationState.max_scheduled_events_per_turn`.

The world-event schedule is merged with the existing NPC simulation cadence into one deterministic timeline. At the same world minute, scheduled environmental events run before NPC simulation cycles. The two subsystems keep independent catch-up limits so a large time jump cannot create an unbounded transaction.

A due event becomes a `ScheduledLocationConditionApplied` domain event. Validation requires that it refer to the first canonical pending schedule entry, match the stored due minute exactly, and not execute before world time reaches that minute. The reducer then performs both state changes atomically:

```text
pending ScheduledLocationCondition
→ validated ScheduledLocationConditionApplied
→ add Location.active_conditions[condition.code]
→ remove that exact pending schedule entry
```

Because schedule consumption itself is event-reduced, ordinary event replay reconstructs both the environmental consequence and the remaining future queue.

## Player visibility

Future schedule metadata is deliberately absent from `PlayerStateView`. The API exposes only `location_conditions` already active at the player's current location. The browser renders those active conditions but receives no pending event ids or future due times.

The Ashfall Relay demo contains one scheduled environmental event: `yard_ash_squall` becomes due at Day 1 08:20. Before 08:20, the player projection reports no active yard condition and does not contain that schedule id. At the due world minute, the condition becomes canonical state and is visible through the normal API/UI state projection.

## Failure atomicity

Narrative generation still occurs before automatic world simulation and before persistence. If the provider fails on a player action that would make a world event due, neither the player action nor the scheduled environmental event is committed. State, event log, and turn history remain unchanged.

## Validation and regression evidence

`tests/test_world_events.py` covers:

- exact due-minute activation;
- same-minute ordering relative to NPC simulation;
- replay equality and SQLite restart persistence;
- hidden future schedule metadata in API/UI projections;
- too-early, out-of-order, and duplicate execution rejection;
- bounded backlog selection and replay;
- invalid duplicate schedule-state rejection;
- provider-failure zero-commit atomicity;
- browser rendering of active location conditions.

The first complete implementation head passed wheel/package verification, Ruff, strict mypy, and **83 pytest tests**. The existing seeded 1,000-accepted-turn evaluation also passed unchanged in semantics: 1,058 submitted actions, 1,000 accepted turns, 58 deterministic rejections, 1,000 episodes, and 2,269 events. Replay equality, state validity, monotonic clock/knowledge/event-log properties, item ownership, and unique event ids all remained true with `failures=[]`.

Those numbers are deterministic correctness evidence for that scenario, not a performance benchmark.
