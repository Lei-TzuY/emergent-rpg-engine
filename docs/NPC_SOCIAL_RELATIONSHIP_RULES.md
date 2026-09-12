# NPC social relationship progression

Milestone 25 closes the remaining relationship-progression gap between player dialogue and NPC-to-NPC social execution. A successful NPC fact transfer can now trigger the same canonical `DialogueRelationshipRule` policy used by player-facing conversation; no second relationship engine or mutation path is introduced.

## Authority invariant

```text
NPC social planner chooses a local receiver
→ deterministic resolver chooses one disclosure-eligible fact
→ NPCFactShared(source, receiver, fact)
→ receiver canonical fact knowledge changes
→ DialogueRelationshipPolicy evaluates source → receiver rules
→ at most one RelationshipChanged(rule_id=...)
→ reducer revalidates rule provenance against updated receiver knowledge
→ optional receiver inference
→ ordinary persistence / replay
```

The ordering is material. The resolver may consider the fact pending in the same social action when selecting a rule, but it emits `NPCFactShared` first. When the following `RelationshipChanged` reaches the reducer, the receiver already canonically knows the prerequisite fact, so `DialogueRelationshipPolicy.validate_rule_event()` can independently recompute the same highest-priority eligible rule.

`RelationshipChanged` remains the only relationship mutation event. Source-to-receiver directionality, bounded deltas, priority/lexical rule ordering, one-shot anti-farming through `applied_dialogue_relationship_rule_ids`, liveness, co-location, and participant validation are inherited from Milestone 24. A relationship consequence does not consume another social action slot; it is a consequence of the already accepted share.

Because explicit `run_npc_social_phase()` and scheduled off-screen social diffusion both execute the same `DeterministicNPCResolver`, the relationship rule has one execution surface rather than separate explicit/background implementations.

## Focused verification

The M25 regression suite proves:

- `NPCFactShared` precedes the rule-driven `RelationshipChanged`;
- reducing the relationship event before the prerequisite share is rejected by reducer provenance validation;
- the directed source→receiver relationship changes while the reverse score remains unchanged;
- a one-shot rule cannot be farmed by a later social action;
- one share plus its relationship consequence still counts as one attempted/executed social action;
- explicit social execution persists, restarts, and replays exactly;
- automatic off-screen simulation produces `NPCFactShared → RelationshipChanged → SimulationCycleProcessed` in one transaction; and
- existing ordinary NPC planning, disclosure policy, player dialogue, and simulation behavior remain compatible.

## Verification evidence

The first complete M25 implementation head `0db148349b69cbfc348b84d30ee2ce80c0409e0a` passed:

- standard wheel build and packaged browser-asset verification;
- Ruff;
- strict mypy across **47 source files**;
- **159 pytest tests**;
- the seeded **1,000 accepted-turn** consistency evaluation; and
- JSON report verification.

For seed `20260911`, the long-run gate produced 1,058 submissions, 1,000 accepted turns, 58 deterministic rejections, 2,274 events, 1,058 persisted turns, 1,000 episodes, and final canonical clock minute 4,361. Replay equality, state validity, monotonic clock/player knowledge/event log, item ownership, and event-id uniqueness were all true with `failures=[]`. The default workload does not configure the synthetic M25 NPC relationship rule; M25 behavior is therefore established by the focused explicit/off-screen SQLite regressions, while the long-run gate proves continuity was not regressed.

## Promotion boundary: Milestone 26

NPC behavior is now reactive to location, environment, map knowledge, item-location beliefs, facts, disclosure policy, and relationships, but configured `NPCGoal` objects are still statically eligible. Learning a new fact can change what an NPC knows without changing which structured goal it will pursue.

Milestone 26 should add **knowledge-gated reactive NPC goals** as canonical goal policy rather than planner-side special cases:

```text
NPCGoal.required_fact_ids
+ NPC's own canonical facts_known
→ planning-context goal eligibility
→ existing priority ordering / bounded path planning
→ existing typed NPC intents / deterministic resolver
→ ordinary movement / inspection / goal completion events
→ persistence / replay
```

The planner must only use the acting NPC's own knowledge. A goal whose prerequisites are not known must remain dormant even if those facts are objectively true or known by another entity; acquiring the final prerequisite through ordinary inspection, inference, explicit social sharing, or automatic off-screen diffusion should make the goal eligible on a later NPC phase without a direct mutation or global-truth lookup. Existing static goals must remain backwards-compatible through an empty prerequisite set. Focused tests should prove cross-observer isolation, deterministic priority interaction between newly eligible and already eligible goals, social-learning activation, explicit/off-screen execution, and persistence/replay, followed by the existing 1,000-turn continuity gate.