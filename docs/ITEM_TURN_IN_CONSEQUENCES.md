# Item Turn-In Consequences

Milestone 30 adds data-driven, replayable consequences to validated player-to-NPC item handoffs without creating a second reward authority.

## Authority boundary

```text
player owns portable item + local active NPC
→ GiveAction
→ PlayerItemGiven
→ optional matching NPC acquire-item goal completion
→ canonical ItemTurnInConsequenceRule selection
→ optional ordinary FactDiscovered
→ ordinary RelationshipChanged(rule_id=turn-in-rule)
→ reducer revalidates post-handoff custody / prerequisites
→ canonical applied rule id
→ ordinary persistence / replay
```

`ItemTurnInConsequenceRule` is world-pack data. Rules match an exact NPC receiver and item and may additionally require a matching acquisition goal completed by the handoff plus player/NPC fact prerequisites. Eligible rules are ordered by descending priority and then lexical rule id; at most one rule is proposed by a handoff.

The rule does not mutate state directly. Player fact rewards remain ordinary `FactDiscovered` events and must pass the existing discovery authority. Relationship rewards remain ordinary `RelationshipChanged` events. The relationship event carries the turn-in rule id, so its successful reduction is both the typed consequence provenance and the point at which the one-shot rule id becomes canonical applied state.

## Reducer backstop

The resolver is not trusted as the only gate. Before a turn-in relationship consequence is reduced, `ItemTurnInConsequencePolicy` independently requires:

- a configured, not-yet-applied rule id;
- exact receiver→player relationship participants and configured delta;
- alive/conscious, co-located player and receiver;
- the item already in receiver custody and inventory;
- all configured player and receiver fact prerequisites;
- the configured acquisition goal, when present, to already be complete.

Dialogue relationship-rule ids and item turn-in rule ids are required to be disjoint, so the reducer can dispatch provenance unambiguously while preserving the existing dialogue rule path.

## Determinism and farming resistance

Rule matching never branches on Ashfall item names or quest names. A repeated handoff cannot fire the same one-shot rule again because the reducer records its id in `applied_item_turn_in_consequence_rule_ids`. Priority and lexical tie-breaking are deterministic. Invalid or unmatched handoffs simply produce no reward events.

Provider narration still happens before persistence. A provider failure therefore leaves the item with the player and leaves rewarded facts, relationships, applied-rule ids, events, and turns uncommitted.

## Verification evidence

The fully green implementation head `18e0cc12b4308a6944fd17055891634a965766bf` passed:

- wheel build and packaged browser-asset verification;
- Ruff;
- strict mypy across 48 source files;
- 200 pytest tests;
- the seeded 1,000-accepted-turn consistency evaluation;
- JSON report verification.

Focused coverage proves reward event ordering, deterministic priority and fact gating, acquisition-goal completion in the same handoff, one-shot anti-farming behavior, forged pre-custody reward rejection, invalid world-pack references, SQLite persistence/replay equality, and provider-failure zero-commit semantics.

For seed `20260911`, the long-run gate remained at 1,058 submitted actions, 1,000 accepted turns, 58 deterministic rejections, 2,274 events, 1,058 persisted turns, 1,000 episodes, and final canonical clock minute 4,361. Replay equality, state validity, monotonic clock/player knowledge/event log, item ownership, and event-id uniqueness were all true with `failures=[]`. The default seeded workload does not configure turn-in reward rules, so the event count remains the Milestone 29 baseline; Milestone 30 behavior is exercised by dedicated integration regressions.

## Promotion boundary

Milestone 31 should introduce canonical player objectives / quest progression rather than adding more reward variants. Objective activation and completion must be derived from typed canonical facts, custody, and applied consequence provenance; narration must not decide quest truth. The player-visible API/UI may project objective state, but hidden prerequisites and NPC-private knowledge must remain hidden. Objective progress must persist/replay exactly and must not create a second item/fact/relationship mutation path.
