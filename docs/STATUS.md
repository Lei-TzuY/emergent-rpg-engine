# Project status

This file is the compact current-phase status. Historical milestone invariants and evidence remain in `docs/ROADMAP.md` and milestone-specific documents.

## Current checkpoint

- Milestones 1–35: **Complete**.
- Milestone 36 — **Replayable combat stamina economy / rest recovery**: **Next**.

## Milestone 35 authority boundary

Player combat now has one executable deterministic vertical slice:

```text
visible local NPC target
→ AttackAction
→ deterministic resolver
→ provenance-rich CharacterDamaged
→ generic validator + reducer revalidation
→ canonical health / lethal life-state transition
→ TimeAdvanced
→ narration
→ atomic persistence / replay
```

For `cause="unarmed_attack"`, the damage source must be the canonical player, source/target must be distinct active co-located entities, and the amount must equal `CombatPolicy.UNARMED_DAMAGE`. The provider/parser can propose the target but cannot choose damage.

Health and lethal `alive/conscious` transitions are checked again at whole-transition validation time. Direct state mutation without matching damage/healing event provenance fails closed. Lethal narration keeps the struck target in event/scene evidence while allowing inactivity only when the entity was active before the turn and became inactive during that accepted transition; stale inactive participants remain rejected.

The implementation preserves the pre-existing serialized `CharacterDamaged` shape by defaulting absent provenance to `source_id=None` and `cause="other"`, so old replay data remains readable while the new player-combat path is strictly validated.

The fully green implementation head `07d76ea56a4c985549241f03f910b2de21d6bd14` passed wheel/browser packaging, Ruff, strict mypy, **281 pytest tests**, the seeded 1,000-turn consistency evaluation and verifier (1,058 submissions / 1,000 accepted / `failures=[]`), and the autonomy/custody/social integration evaluation and verifier.

## Next frontier: Milestone 36

Combat damage exists, but stamina is still canonical data with no executable authority. Milestone 36 should make it a replayable action-economy resource before expanding combat AI.

An unarmed attack should require sufficient canonical stamina and emit a typed stamina-spend event before damage. Explicit rest/wait should recover stamina through a typed bounded recovery event. Validator/reducer/transition provenance must reject forged amounts, overspend, over-recovery, direct stamina mutation, and wrong actor/reason combinations. Provider failure must keep both stamina and damage zero-commit.

Because stamina will affect action legality, player-facing CLI/API/browser state should expose health and stamina. NPC retaliation, initiative, weapons/armor, and combat AI should remain outside this phase and be promoted only after the resource authority is proven.
