# Project status

This file is the compact current-phase status. Historical milestone invariants and evidence remain in `docs/ROADMAP.md` and the milestone-specific documents.

## Current checkpoint

- Milestones 1–26: **Complete** on merged `main`.
- Milestone 27 — **Autonomous NPC item acquisition / custody**: **Complete candidate** on PR #28; executable head `2e67bb2b132c6a67fb3d56b67f866dd3df308312` passed the full verification gate.
- Milestone 28 — **Replayable item handoff / delivery goals**: **Next** after Milestone 27 final docs-head CI, merge gate, and merged-main CI are green.

## Milestone 27 authority boundary

NPC item acquisition extends existing custody semantics instead of creating a parallel inventory subsystem:

```text
knowledge-gated acquire_item goal
+ NPC own item-location belief / known routes / local visibility
→ deterministic planner
→ movement / stale local search / NPCAcquireIntent
→ deterministic resolver
→ existing ItemAcquired
→ observer-scoped item-memory cleanup
→ NPCGoalCompleted(method="acquired_item")
→ persistence / replay
```

The planner never receives authoritative remote item location. The existing `ItemAcquired` event remains the only acquisition mutation path for player and NPC actors. Generic event validation independently requires an existing alive/conscious actor, local unowned portable target, and matching event origin. Acquisition completion is accepted only when canonical item ownership and NPC inventory agree.

The implementation also preserves the older Milestone 19 investigate-item rejection contract. A full-suite regression caught generalized error text that changed existing deterministic behavior; production was corrected rather than weakening the test.

The fully green M27 implementation head `2e67bb2b132c6a67fb3d56b67f866dd3df308312` passed wheel/package verification, Ruff, strict mypy across **47 source files**, **175 pytest tests**, the seeded 1,000-accepted-turn evaluation, and JSON report verification. The long-run report produced 1,058 submissions / 1,000 accepted / 58 rejected / 2,274 events / final clock 4,361 with every tracked invariant true and `failures=[]`.

See `docs/NPC_ITEM_ACQUISITION.md` for focused authority and verification details.

## Next frontier: Milestone 28

Milestone 27 can acquire an unowned ground item but deliberately rejects transfer from an existing owner. The next coherent slice should add replayable owner-to-owner item handoff / delivery goals without creating a second custody store.

A delivery-capable NPC must canonically possess the item, reach or share a location with the intended receiver, and transfer through a typed event carrying exact source/receiver/item provenance. Validation must reject remote transfer, inactive participants, source-without-item, wrong receiver, and duplicate ownership. Reduction must atomically move the unique item between inventories, while observer item-location beliefs remain scoped rather than globally synchronized. Explicit/off-screen execution, SQLite restart/replay, and the existing 1,000-turn consistency gate must remain green.