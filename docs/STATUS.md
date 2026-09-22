# Project status

This file is the compact current-phase status. Historical milestone invariants and evidence remain in `docs/ROADMAP.md` and milestone-specific documents.

## Current checkpoint

- Milestones 1–30: **Complete**.
- Milestone 31 — **Replayable player objective progression**: **Complete**.
- Milestone 32 — **Replayable player objective deadlines / failure lifecycle**: **Complete**.
- Milestone 33 — **Data-driven objective outcome consequences**: **Next**.

## Milestone 32 authority boundary

Objective failure is canonical lifecycle state, not a side effect of prose or a wall-clock timer:

```text
accepted player action
→ canonical TimeAdvanced / ordinary player events
→ deterministic objective fixed-point
→ activate eligible objectives
→ complete every earned objective
→ fail remaining due objectives
→ typed lifecycle validation / reduction
→ narration
→ one atomic commit / replay
```

The fixed-point gives completion precedence when completion and deadline coincide. A downstream objective that becomes activation-ready because another objective completes in the same turn receives another activation/completion pass before deadline failure can terminate it.

`PlayerObjectiveFailed` is independently validated against canonical objective configuration and world time. Reducer-owned active/completed/failed sets are mutually exclusive, and transition validation reconstructs their expected state from lifecycle events so direct mutation fails closed.

Active objectives expose their public deadline through CLI/API/browser. Completed and failed objectives are also player-visible, while pending objective definitions and prerequisite ids remain hidden.

The implementation preserves provider-failure atomicity: narration failure occurs before persistence, so deadline-triggered lifecycle events, canonical state, event log, and turn history remain unchanged.

## Next frontier: Milestone 33

Objective outcomes now have deterministic truth but do not yet provide a generic way to alter the wider world. Milestone 33 should add **data-driven objective outcome consequences**.

A canonical rule should match a validated `PlayerObjectiveCompleted` or `PlayerObjectiveFailed` outcome and emit only bounded consequences through existing typed authorities such as fact discovery, relationship change, or scheduled world events. Rules need deterministic ordering, one-shot provenance, forged-event backstops, persistence/replay equality, hidden-prerequisite safety, and provider-failure zero-commit behavior.

The goal is to make quest outcomes causally affect the world without creating a second mutation engine or embedding named quest branches in generic runtime code.
