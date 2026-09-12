# Project status

This file is the compact current-phase status. Historical milestone invariants and evidence remain in `docs/ROADMAP.md` and the milestone-specific documents.

## Current checkpoint

- Milestones 1–24: **Complete** on merged `main`.
- Milestone 25 — **Replayable NPC social relationship progression**: **Complete candidate** on PR #26; executable head `0db148349b69cbfc348b84d30ee2ce80c0409e0a` passed the full verification gate.
- Milestone 26 — **Knowledge-gated reactive NPC goals**: **Next** after Milestone 25 final docs-head CI, merge gate, and merged-main CI are green.

## Milestone 25 authority boundary

NPC social relationship progression reuses the existing canonical dialogue relationship-rule engine:

```text
accepted NPC social action
→ NPCFactShared(source, receiver, fact)
→ receiver canonical knowledge update
→ DialogueRelationshipPolicy over source → receiver
→ optional RelationshipChanged(rule_id=...)
→ reducer-side rule provenance validation
→ one-shot applied-rule state
→ optional receiver inference
→ persistence / replay
```

`NPCFactShared` is reduced before a relationship consequence, so a fact learned in the same social action can legitimately satisfy the rule while reducer validation still recomputes eligibility from canonical state. `RelationshipChanged` remains the only relationship mutation event; M25 adds no second social trust store or mutation authority. The relationship consequence stays inside the accepted share and does not consume another social-action slot.

Explicit `npc-social-step` and automatic off-screen diffusion use the same resolver, so the same event ordering, directed source→receiver semantics, one-shot anti-farming, bounded delta, persistence, and replay rules apply to both surfaces.

The first complete M25 implementation head `0db148349b69cbfc348b84d30ee2ce80c0409e0a` passed wheel/package verification, Ruff, strict mypy across **47 source files**, **159 pytest tests**, the seeded 1,000-accepted-turn evaluation, and JSON report verification. The long-run report preserved 1,058 submissions / 1,000 accepted / 58 rejected / 2,274 events / final clock 4,361 with every tracked invariant true and `failures=[]`.

See `docs/NPC_SOCIAL_RELATIONSHIP_RULES.md` for focused authority and verification details.

## Next frontier: Milestone 26

NPCs can now acquire facts through local discovery, inference, explicit sharing, and automatic off-screen diffusion, but every configured `NPCGoal` is still statically eligible. Milestone 26 should make goal eligibility react to the acting NPC's own canonical knowledge without introducing a planner-side mutation path.

The first coherent slice is a backwards-compatible `NPCGoal.required_fact_ids` prerequisite set. Goals with no prerequisites preserve current behavior. A gated goal remains dormant until all prerequisites are in that NPC's `facts_known`; objective world truth or another observer's knowledge must not activate it. Once the final prerequisite is learned through an ordinary canonical event, the next explicit or off-screen goal phase should deterministically consider the goal under the existing priority/path/resolver pipeline.

Acceptance requires cross-observer isolation, deterministic priority interaction with existing goals, social-learning activation, explicit/off-screen execution parity, persistence/replay, and the existing 1,000-turn continuity gate.