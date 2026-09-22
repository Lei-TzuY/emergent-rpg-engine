# Project status

This file is the compact current-phase status. Historical milestone invariants and evidence remain in `docs/ROADMAP.md` and milestone-specific documents.

## Current checkpoint

- Milestones 1–36: **Complete**.
- Milestone 37 — **Actor-symmetric bounded NPC retaliation**: **Next**.

## Milestone 36 authority boundary

Stamina is now canonical executable state with typed provenance:

```text
AttackAction
→ CharacterStaminaSpent
→ provenance-linked CharacterDamaged
→ TimeAdvanced(cause=combat)
→ transition validation
→ atomic persistence / replay

WaitAction
→ bounded CharacterStaminaRecovered when below max
→ TimeAdvanced(cause=wait)
→ transition validation
→ atomic persistence / replay
```

An unarmed player attack costs exactly `CombatPolicy.UNARMED_STAMINA_COST`. The spend event identifies the canonical player and exact target; the damage event links back to that spend's event id and repeats the cost. Validator and reducer independently enforce actor, target, co-location, liveness/consciousness, fixed damage/cost, and affordability. Whole-transition validation reconstructs stamina and rejects missing/mismatched spend↔damage, combat-time, or wait↔recovery provenance.

Wait recovery is deterministic and bounded by both elapsed wait minutes and the canonical stamina maximum. Waiting at full stamina emits no fake zero-value recovery event.

M35 event logs remain replayable: an older `CharacterDamaged(cause="unarmed_attack")` with both stamina provenance fields absent uses the pre-stamina compatibility path. New M36 attacks always carry both fields; partial provenance is invalid.

Health and stamina are now exposed in API, CLI, browser UI, and the structured action parser's visible state. Provider failure remains zero-commit across stamina, damage, time, state, events, and turn history.

The fully green implementation head `cec776e0c850d43c0d2d6e14f92fc970c1b84e1e` passed wheel/browser packaging, Ruff, strict mypy, **292 pytest tests**, the seeded 1,000-turn consistency evaluation and verifier (**1,058 submissions / 1,000 accepted / failures=[]**), and the autonomy/custody/social evaluation and verifier with `failures=[]`.

## Next frontier: Milestone 37

The next combat milestone should prove actor symmetry with one bounded deterministic NPC retaliation after a surviving legal player attack.

A retaliating NPC should spend its own canonical stamina and damage the player through the same provenance-rich authority, with at most one retaliation per player attack. Dead, unconscious, remote, incapacitated, or exhausted NPCs must not retaliate. Retaliation must be engine policy, not provider prose.

This phase should not expand into weapons, armor, generic initiative rounds, arbitrary aggression goals, hit chance, or broad combat AI. Those become later promotions only after symmetric retaliation is replayably proven.
