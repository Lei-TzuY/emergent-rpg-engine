# Relationship-gated social disclosure

Milestone 21 makes NPC fact sharing selective through canonical, source-directed relationship policy rather than hard-coded fact IDs or planner convention.

## Canonical policy

Every `Fact` carries:

```text
disclosure_min_relationship: -100..100
```

The default is `-100`, preserving Milestone 20 behavior for ordinary/public facts. World packs opt into restricted disclosure by raising the threshold. Ashfall Relay marks `fact_relay_sabotage` with threshold `20` as a real executable restricted clue.

A missing source→receiver relationship entry has deterministic neutral score `0`. Relationships are directed: a high receiver→source score never authorizes the source to disclose a restricted fact in the opposite direction.

## Authority path

```text
source NPC own relationships + locally visible NPC ids
→ social planner ranks receiver by source-owned trust, lexical id tie-break
→ NPCShareFactIntent(receiver_id)
→ resolver computes source-known / receiver-unknown facts
→ SocialDisclosurePolicy filters by fact threshold and source→receiver score
→ lexical first eligible fact
→ NPCFactShared(source, receiver, fact)
→ generic validator repeats disclosure-policy check
→ receiver-only knowledge update / inference / persistence / replay
```

The planner still does not receive receiver-private fact knowledge and still cannot choose a fact. Relationship-aware receiver ranking uses only the source NPC's own canonical `relationships` projection already present in `NPCPlanningContext`.

`SocialDisclosurePolicy` centralizes relationship lookup and threshold evaluation so resolver and validator do not carry separate interpretations of trust. A forged `NPCFactShared` event for a restricted fact is rejected with `npc_disclosure_blocked` when the source-directed relationship score is below the fact's threshold.

If all new facts are restricted, the resolver rejects the attempted social action. If both restricted and public new facts exist, the resolver skips blocked facts and deterministically selects the lexical first eligible fact.

## Replayable trust changes

Existing `RelationshipChanged(source_id, target_id, delta)` events remain the only ordinary relationship mutation path. Because disclosure reads the canonical source→receiver score at resolution and validation time, replaying a relationship change deterministically changes later disclosure eligibility without copying receiver-private knowledge into the planner.

The regression suite proves that applying `RelationshipChanged(source→receiver, +20)` unlocks the Ashfall restricted sabotage fact, while setting only the reverse receiver→source relationship to `100` does not.

## Verification evidence

The fully green implementation candidate `31d73f5695969af26905e40e59c71aa2e30ab920` passed:

- standard wheel build and packaged browser-asset verification;
- Ruff;
- strict mypy across **46 source files**;
- **140 pytest tests**;
- the seeded 1,000-accepted-turn consistency evaluation;
- machine-readable JSON report verification.

For seed `20260911`, the long-run gate produced 1,058 submitted actions, 1,000 accepted turns, 58 deterministic rejections, 2,272 events, 1,058 persisted turns, 1,000 episodes, and final canonical clock minute 4,361. Replay equality, state validity, monotonic clock/player knowledge/event log, item ownership, and event-id uniqueness were all true with `failures=[]`.

The seeded player workload does not invoke the explicit social phase, so its event count remains the M20 baseline. Relationship/disclosure behavior is proven by focused resolver/validator/social-phase persistence regressions while the long-run gate proves no continuity regression in the ordinary player/simulation workload.

## Promotion boundary

The next architectural gap is autonomous social diffusion. Milestone 20 deliberately separated social actions from ordinary NPC goal execution after automatic fallback caused budget regressions; Milestone 21 then made that explicit social path trust-aware. Milestone 22 should integrate the already-validated social path into scheduled off-screen simulation using an **independent canonical social-action budget**.

Automatic social diffusion must not consume the existing movement/investigation budget, must skip NPCs sharing the player's current location, must retain trust-gated resolver/validator authority, must remain in the same atomic player-turn transaction, and must not leak hidden social participants or private facts into player-facing turn/episode metadata.
