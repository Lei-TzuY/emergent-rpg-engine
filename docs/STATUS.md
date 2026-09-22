# Project status

This file is the compact current-phase status. Historical milestone invariants and evidence remain in `docs/ROADMAP.md` and milestone-specific documents.

## Current checkpoint

- Milestones 1–37: **Complete**.
- Milestone 38 — **Data-driven weapon profiles / equipment authority**: **Next**.

## Milestone 37 authority boundary

NPC retaliation is now one bounded deterministic response inside the shared combat authority:

```text
accepted player unarmed attack
→ player stamina spend + player damage
→ if struck NPC remains actionable and funded:
     one NPC retaliation spend
   → one provenance-linked NPC damage against player
→ shared combat-time / health / stamina transition validation
→ atomic persistence / replay
```

The retaliation spend identifies the exact triggering player damage event. Retaliation damage identifies both its exact stamina spend and the same player-damage trigger. Whole-transition validation rejects missing/mismatched triggers and consumes each player-damage trigger at most once, so duplicated responses fail closed.

Dead, unconscious, incapacitated, remote, or exhausted NPCs do not retaliate. Normal player attack spends are still restricted to the canonical player, while retaliation spends are restricted to NPC→canonical-player response. The provider cannot request or suppress retaliation; it remains deterministic resolver policy.

The same canonical health/stamina stores and fixed unarmed cost/damage apply to both actors. Retaliation can lethally transition the player through the existing reducer and transition-aware narration path. Provider failure remains zero-commit across both sides of the exchange.

The fully green implementation head `3f6f70a34bf5a503028ddf771a2f3f357564ca76` passed wheel/browser packaging, Ruff, strict mypy, **298 pytest tests**, the seeded 1,000-turn consistency evaluation and verifier (**1,058 submissions / 1,000 accepted / failures=[]**), and the autonomy/custody/social evaluation and verifier with `failures=[]`.

## Next frontier: Milestone 38

Combat is now symmetric enough to expose the next real limitation: attack damage and stamina cost are still hard-coded unarmed constants, while canonical items have only generic `item_type` / `flags` metadata.

Milestone 38 should add explicit structured weapon profiles and typed equipment authority. A weapon must be canonically owned before it can be equipped; equipment changes must be typed/replayable; an attack must carry weapon identity in its spend/damage provenance so validation can re-derive the exact bounded damage and stamina cost from world data. No equipped weapon means the current unarmed fallback.

This phase should not expand into armor, hit chance, randomness, durability, arbitrary loot generation, initiative rounds, or broad combat AI.
