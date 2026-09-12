# Project status

This file is the compact current-phase status. Historical milestone invariants and evidence remain in `docs/ROADMAP.md` and the milestone-specific documents.

## Current checkpoint

- Milestones 1–23: **Complete**.
- Milestone 24 — **Data-driven dialogue relationship progression**: **Complete candidate** on PR #25, pending final exact-head CI / merge gate.
- Milestone 25 — **Replayable NPC social relationship progression**: **Next** after Milestone 24 is merged and merged-main CI is green.

## Milestone 24 authority boundary

Dialogue-triggered relationship progression is now canonical world data:

```text
DialogueRelationshipRule world data
+ canonical listener knowledge
→ deterministic priority/id rule selection
→ ordinary RelationshipChanged(rule_id=...)
→ reducer-side provenance validation
→ bounded relationship mutation
→ canonical one-shot applied-rule marker
→ SQLite persistence / replay
```

The generic resolver contains no Ashfall-specific NPC/fact branch for relationship progression. World-specific identifiers and observation prose are configured by the world pack. `RelationshipChanged(rule_id=None)` remains compatible for unrelated/manual relationship transitions.

The first complete executable M24 candidate `9f96bbf7150bf8284f4c35fb8f99d597ff769b70` passed wheel/package verification, Ruff, strict mypy across 47 source files, 156 pytest tests, the seeded 1,000-accepted-turn consistency evaluation, and JSON report verification. The long-run report preserved 1,058 submissions / 1,000 accepted / 58 rejected / 2,274 events / final clock 4,361 with every tracked invariant true and `failures=[]`.

See `docs/DIALOGUE_RELATIONSHIP_RULES.md` for the full invariant and focused verification surface.

## Next frontier: Milestone 25

The same canonical dialogue relationship rule model already supports NPC listeners, but NPC-to-NPC `NPCFactShared` execution does not yet evaluate relationship consequences. Milestone 25 should integrate the existing rule engine after a successful share, in the same explicit/off-screen social transaction, without adding another relationship authority or consuming an additional social action slot.

Acceptance requires the newly shared fact to become canonical receiver knowledge before rule validation, directed source→receiver semantics, one-shot anti-farming, reducer provenance validation, parity between explicit `npc-social-step` and automatic off-screen social diffusion, SQLite replay, and the existing 1,000-turn continuity gate.