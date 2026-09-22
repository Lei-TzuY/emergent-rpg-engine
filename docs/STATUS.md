# Project status

This file is the compact current-phase status. Historical milestone invariants and evidence remain in `docs/ROADMAP.md` and milestone-specific documents.

## Current checkpoint

- Milestones 1–34: **Complete**.
- Milestone 35 — **Deterministic player combat / damage provenance**: **Next**.

## Milestone 34 authority boundary

Objective terminal outcomes can now schedule future environmental changes without creating a second environmental mutation path:

```text
PlayerObjectiveCompleted / PlayerObjectiveFailed
→ deterministic highest-priority schedule rule
→ ScheduledLocationConditionQueued
→ canonical pending schedule
→ existing world-event scheduler at due minute
→ ScheduledLocationConditionApplied
→ existing expiry / traversal / route rules
→ persistence / replay
```

The queue event carries exact objective, outcome, rule, scheduled-event id, and due-minute provenance. Validation rejects forged terminal provenance, wrong due times, duplicate pending ids, missing locations, invalid route targets, active/pending target conflicts, and lower-priority sibling rules after an outcome has been consumed.

Transition validation also protects the pending queue itself: a schedule cannot appear without a typed queue event, an existing pending schedule cannot be silently rewritten in place, and the canonical applied schedule-rule set must match queue-event provenance.

Objective policy never directly activates a location condition. Activation and expiry remain owned by the existing deterministic scheduler and environmental reducer. Pending scheduled consequences remain hidden from player-visible API/browser state until they actually become active.

Provider failure still occurs before persistence, so queued consequences, objective events, canonical state, event log, and turn history remain unchanged on narration failure. The fully green implementation head `c397483943d05b871cb9bac27a413b85312e87c3` passed wheel/browser packaging, Ruff, strict mypy, full pytest, the seeded 1,000-turn consistency evaluation and verifier, and the autonomy integration evaluation and verifier.

## Next frontier: Milestone 35

The objective subsystem now spans replayable activation, completion/failure, immediate fact/relationship outcomes, and delayed scheduled-world effects. The next high-value architectural gap is combat.

The engine already models health, stamina, alive/conscious state, and `CharacterDamaged`, but players have no typed attack action and existing damage lacks attacker provenance. Milestone 35 should add a bounded deterministic player-combat vertical slice: local-target `AttackAction`, provenance-rich validated damage, reducer-owned health/death transitions, parser/provider/API/browser parity, persistence/replay, and provider-failure zero-commit behavior.

This should not become a placeholder “combat system.” The acceptance boundary is one executable, deterministic unarmed attack path with explicit legality and damage authority; richer weapons, armor, NPC retaliation, initiative, and combat AI can be promoted only after that base path is proven.
