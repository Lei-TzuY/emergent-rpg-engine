# Project status

This file is the compact current-phase status. Historical milestone invariants and evidence remain in `docs/ROADMAP.md` and milestone-specific documents.

## Current checkpoint

- Milestones 1–38: **Complete**.
- Milestone 39 — **Canonical player defeat / actionability authority**: **Next**.

## Milestone 38 authority boundary

Weapons now participate in the same canonical, typed, replayable combat pipeline as unarmed attacks:

```text
owned Item.weapon profile
→ typed equip / unequip event
→ canonical equipped_weapon_id
→ attack profile derived from canonical item data
→ provenance-linked stamina spend + damage
→ optional bounded retaliation
→ whole-transition equipment/combat validation
→ atomic persistence / replay
```

Equipment changes require canonical custody, liveness/consciousness, non-incapacitation, an actual weapon profile, and an exact `from_item_id` match. Direct equipment-state mutation without a corresponding typed event is rejected by transition validation.

Weapon attacks carry the exact weapon id through stamina spend and damage provenance. Damage and stamina cost are re-derived from the canonical weapon profile, not accepted from prose or arbitrary event numbers. Unequipping restores the existing deterministic unarmed profile. Equipped weapons cannot be dropped or transferred until unequipped.

Ashfall Relay includes an executable `relay wrench` weapon (damage 4 / stamina cost 4), and the equipment state is visible through API, CLI, browser, and structured action parsing. The complete take → equip → attack → retaliation → persistence/replay path is covered.

The fully green implementation head `391b1cf2294ebe975b3f9d2d4e3ae8b271f5265c` passed wheel/browser packaging, Ruff, strict mypy across 62 source files, **306 pytest tests**, the seeded 1,000-turn consistency evaluation (**1,058 submissions / 1,000 accepted / failures=[] / passed=true**), and the autonomy/custody/social integration evaluation with `failures=[] / passed=true`.

## Next frontier: Milestone 39

Lethal retaliation already transitions the player to `health=0`, `alive=false`, and `conscious=false`, but player action legality is still partly distributed across individual resolver branches. That means defeat is canonical in state but not yet canonical in action authority.

Milestone 39 should centralize player actionability so dead/unconscious actors cannot continue to mutate world state, and incapacitating conditions use one shared policy rather than scattered per-action checks. Rejected defeated-state actions must emit no material events and must preserve persistence/replay invariants.

Armor, hit chance, initiative, resurrection/respawn, and broad combat AI remain outside this phase.
