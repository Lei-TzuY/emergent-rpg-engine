# Data-driven dialogue relationship rules

Milestone 24 removes the remaining Ashfall-specific trust mutation from the generic player-action resolver. Relationship progression caused by dialogue is now canonical world-pack policy rather than an `npc_id` / `fact_id` branch in engine code.

## Canonical rule data

`WorldState.dialogue_relationship_rules` contains `DialogueRelationshipRule` objects with:

- a stable rule id;
- exact speaker and listener entity ids;
- listener facts required before the rule may fire;
- a bounded relationship delta;
- deterministic priority;
- one-shot versus repeatable behavior; and
- optional player-facing observation text.

`WorldState.applied_dialogue_relationship_rule_ids` records consumed one-shot rules. World-state model validation rejects duplicate rule ids, unknown applied ids, non-NPC speakers, missing listeners, and missing prerequisite facts.

Ashfall Relay now expresses the old Arden behavior as world data:

```text
rule: arden_trusts_sabotage_evidence
speaker: npc_arden
listener: player
requires listener fact: fact_relay_sabotage
delta: +5
once: true
```

No generic resolver, reducer, or dialogue-policy branch contains those Ashfall identifiers.

## Execution invariant

```text
accepted TalkAction
→ ordinary disclosure policy chooses at most one revealable fact
→ optional FactDiscovered(player)
→ DialogueRelationshipPolicy evaluates canonical rules
→ highest priority, lexical-id tie break
→ RelationshipChanged(rule_id=...)
→ reducer independently revalidates rule provenance
→ relationship mutation
→ one-shot rule id persisted in canonical state
→ SQLite persistence / replay
```

A fact revealed by the same conversation can satisfy a rule. The resolver is allowed to consider the pending reveal only for deterministic selection; the emitted `FactDiscovered` precedes `RelationshipChanged`, so reducer-side revalidation observes the fact as canonical listener knowledge before applying the relationship consequence.

The existing `RelationshipChanged` event remains the only relationship mutation path. Its optional `rule_id` preserves backward compatibility for pre-existing/manual relationship events while giving rule-driven events replayable provenance. For a rule-tagged event, the reducer recomputes the next eligible canonical rule and rejects a wrong rule id, wrong delta, inactive participant, remote participant, missing prerequisite, or out-of-order lower-priority rule.

One-shot rules are marked applied only after successful reduction. Replaying the event log reconstructs the applied-rule set, so repeated conversations cannot farm the same relationship consequence even if the numeric relationship later changes for another reason.

## Verification evidence

The first complete M24 implementation head `9f96bbf7150bf8284f4c35fb8f99d597ff769b70` passed:

- wheel build and packaged browser-asset verification;
- Ruff;
- strict mypy across **47 source files**;
- **156 pytest tests**;
- the seeded **1,000 accepted-turn** consistency evaluation; and
- JSON report verification.

Focused regressions prove the Ashfall rule is one-shot, a same-dialogue reveal can trigger a rule in correct event order, a synthetic non-Ashfall rule uses the same generic policy, priority ordering is stable, forged delta/out-of-order rule events are rejected, invalid world-pack references fail model validation, manual `RelationshipChanged(rule_id=None)` remains compatible, and SQLite restart/replay preserves consumed-rule state.

For seed `20260911`, the long-run gate produced 1,058 submissions, 1,000 accepted turns, 58 deterministic rejections, 2,274 events, 1,058 persisted turns, 1,000 episodes, and final canonical clock minute 4,361. Replay equality, state validity, monotonic clock/player knowledge/event log, item ownership, and event-id uniqueness were all true with `failures=[]`. These are deterministic correctness results, not performance measurements.

## Promotion boundary: Milestone 25

The canonical rule model already permits an NPC listener, but Milestone 24 intentionally evaluates relationship progression only for player `TalkAction`. NPC-to-NPC `NPCFactShared` execution does not yet evaluate the same rule layer.

Milestone 25 should close that integration gap without adding another social authority:

```text
accepted NPCFactShared(source, receiver, fact)
→ receiver canonical knowledge update
→ same DialogueRelationshipPolicy over source → receiver
→ at most one eligible relationship consequence
→ ordinary RelationshipChanged(rule_id=...)
→ reducer provenance validation
→ persistence / replay
```

The newly shared fact may satisfy a rule only after `NPCFactShared` is reduced. Relationship consequences must remain part of the same social phase transaction, must not consume an additional NPC/social action budget slot, and must work identically for explicit `npc-social-step` and automatic off-screen social diffusion. One-shot anti-farming and directed relationship semantics must remain unchanged.