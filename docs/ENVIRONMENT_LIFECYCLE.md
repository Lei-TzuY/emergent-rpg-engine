# Environmental Condition Lifecycle

Milestone 15 gives environmental conditions a replayable canonical end-of-life instead of making every activated hazard permanent.

## Canonical lifecycle

A scheduled location condition carries an optional lifetime. Its expiry identity and due minute are derived from the activation schedule rather than wall-clock timers:

```text
ScheduledLocationCondition(due minute + lifespan)
→ deterministic activation slot
→ ScheduledLocationConditionApplied
→ reducer materializes ScheduledLocationConditionExpiry
→ deterministic expiry slot
→ ScheduledLocationConditionExpired
→ reducer removes the active condition and consumes the expiry schedule
```

The scheduler can derive a future expiry slot from still-pending activation data. Therefore a single large canonical time jump can correctly process both activation and expiry in due-time order. Once activation is reduced, the expiry is also represented explicitly in canonical state for persistence and restart.

## Authority and validation

Expiry has no direct dictionary-mutation API. `ScheduledLocationConditionExpired` must match the first deterministic pending world event, the exact canonical due minute, the materialized expiry schedule, location, condition code, and an actually active condition.

`validate_state()` retains the earlier environment monotonicity defense. A condition may disappear between two states only when the same validated transition contains a matching typed expiry event. Manual deletion without lifecycle provenance remains `environment_went_backward`.

Activation, expiry, and NPC simulation share the same canonical world-time timeline. World-event catch-up remains bounded by `max_scheduled_events_per_turn`; backlog stays explicit instead of being silently dropped. Narration still completes before automatic simulation, so provider failure at the expiry boundary leaves state, events, and turn history unchanged.

## Demo behavior

The Ashfall Yard squall activates at Day 1 08:20 and has the generic default 20-minute scheduled lifetime, expiring at 08:40.

- before 08:20: no squall condition;
- 08:20 through 08:39: `ash_squall` is active and traversal from the yard costs ten canonical minutes;
- at 08:40: the typed expiry removes the condition;
- after expiry: traversal returns to the five-minute baseline.

The API and browser need no separate lifecycle authority. They already project only currently active conditions, so the visible squall disappears after canonical expiry.

## Verification evidence

The first fully green implementation candidate passed:

- wheel build and packaged browser-asset verification;
- Ruff;
- strict mypy across 44 source files;
- 97 pytest tests;
- the seeded 1,000-accepted-turn consistency evaluation and JSON verifier.

For seed `20260911`, the long-run scenario completed 1,058 submissions, 1,000 accepted turns, 58 deterministic rejections, 2,270 events, and 1,000 episodes. Final canonical clock minute was 4,361. Replay equality, state validity, monotonic clock/knowledge/event log, item ownership, and event-id uniqueness all remained true with `failures=[]`.

These numbers are correctness evidence for that deterministic scenario, not a performance benchmark.

## Next architectural frontier

The lifecycle now lets environment rules appear and disappear safely, but current traversal rules only change cost. The next phase should add data-driven route legality: conditions may block selected exits, the player resolver and NPC resolver must independently enforce those closures, the NPC planner should not propose blocked routes, and the player-facing API/UI should explain blocked exits without exposing hidden future schedules. Expiry must automatically restore the route without a special-case condition name.
