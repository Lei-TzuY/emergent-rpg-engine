# Project status

This file is the compact current-phase status. Historical milestone invariants and evidence remain in `docs/ROADMAP.md` and milestone-specific documents.

## Current checkpoint

- Milestones 1–32: **Complete**.
- Milestone 33 — **Data-driven objective outcome consequences**: **Complete**.
- Milestone 34 — **Objective-triggered scheduled world consequences**: **Next**.

## Milestone 33 authority boundary

Objective terminal outcomes can now affect the wider canonical world without giving the objective policy direct mutation authority:

```text
PlayerObjectiveCompleted / PlayerObjectiveFailed
→ deterministic highest-priority outcome rule
→ optional existing FactDiscovered authority
→ existing RelationshipChanged authority
→ canonical applied-rule provenance
→ inference + objective reconvergence
→ narration
→ one atomic persistence / replay path
```

Each objective + outcome can consume at most one consequence rule. Rule ids cannot overlap dialogue or item-turn-in relationship rules, so reducer validation always knows which policy owns a `RelationshipChanged(rule_id=...)` event. A forged consequence before the configured terminal outcome fails closed, and a lower-priority sibling cannot fire after the selected rule has consumed that outcome.

Reward facts remain subject to ordinary discovery prerequisites. Any resulting player inference is replayable, and the engine performs a bounded same-turn objective fixed-point so consequence facts can unlock downstream objectives immediately.

Provider failure still occurs before persistence. Objective lifecycle events, outcome reward facts, relationship changes, inferred facts, applied-rule provenance, turns, and canonical state therefore remain uncommitted if narration fails.

The fully green implementation head `a063b598a893265857c45d2db97dfe7c6846ae15` passed wheel/browser packaging, Ruff, strict mypy, full pytest, the seeded 1,000-turn consistency evaluation and verifier, and the autonomy integration evaluation and verifier.

## Next frontier: Milestone 34

Milestone 33 supports immediate fact and relationship consequences but does not yet let an objective outcome schedule future environmental change. Milestone 34 should add a typed, replayable queueing path into the existing canonical scheduled-world timeline.

The objective consequence layer should emit a dedicated validated queue event carrying exact objective/rule/schedule provenance. Reduction may append a validated `ScheduledLocationCondition` entry, but actual activation must remain owned by the existing world-event scheduler at the configured canonical due minute. Duplicate ids, missing locations, invalid route targets, past-due schedules, and forged objective provenance must fail closed.

This promotes quest outcomes from immediate social/knowledge effects to delayed world simulation while preserving one scheduler, one environmental authority, and one replayable event log.
