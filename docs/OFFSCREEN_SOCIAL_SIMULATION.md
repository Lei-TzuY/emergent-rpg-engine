# Automatic off-screen social simulation

Milestone 22 integrates the existing replayable NPC social path into deterministic world simulation. Scheduling decides *when* a social phase may run; it does not become a new knowledge or relationship authority.

## Authority boundary

Each due NPC cadence slot executes in this order:

```text
canonical simulation cadence
→ ordinary off-screen NPC goal phase
→ bounded off-screen social phase
→ SimulationCycleProcessed
→ one atomic player-turn commit
```

The ordinary phase keeps `SimulationState.max_npc_actions_per_cycle`. Social diffusion has its own canonical `SimulationState.max_social_actions_per_cycle`, so information exchange cannot consume movement or investigation capacity.

Automatic social execution reuses the Milestone 20–21 path unchanged: `NPCShareFactIntent(receiver_id)` → deterministic resolver → `SocialDisclosurePolicy` → validated `NPCFactShared` → receiver-only reduction → receiver-scoped mystery inference. The scheduler never copies facts or changes relationships directly.

## Visibility isolation

Automatic social sources exclude NPCs at the player's current location. The source set is recomputed after the ordinary NPC phase, so an NPC that just moved into the player's location cannot immediately take part in hidden social exchange. Because a valid share also requires source and receiver to be physically co-located, an accepted automatic share is off-screen from the player.

The explicit `emergent-rpg npc-social-step` command remains available and deliberately runs with `offscreen_only=False`; that operator surface is separate from background simulation.

Off-screen NPC ids and private facts are not copied into the accepted player's `Turn` or `Episode` metadata. Automatic social events remain ordinary canonical events in the same SQLite transaction as the triggering player turn.

## Transaction ordering

Narrative generation still completes before due simulation starts. A narrative-provider failure therefore commits no player events, simulation marker, NPC goal action, or social share. The social phase and `SimulationCycleProcessed` marker are reduced only on the candidate state and persist together when the complete turn transaction succeeds.

## Verification evidence

The first fully green M22 implementation head `d1d5a1753381e5c3d81f656018ba311549178fb3` passed standard wheel/package verification, browser-asset checks, Ruff, strict mypy across **46 source files**, **144 pytest tests**, the seeded 1,000-accepted-turn evaluation, and the JSON verifier.

Focused SQLite regressions prove bounded automatic sharing, exclusion of player-visible NPCs, independent ordinary/social budgets, goal→social→marker event ordering, replay equality, player metadata isolation, and provider-failure zero-commit behavior.

For seed `20260911`, the long-run gate produced 1,058 submitted actions, 1,000 accepted turns, 58 deterministic rejections, **2,274 events**, 1,058 persisted turns, 1,000 episodes, and final canonical clock minute 4,361. Replay equality, state validity, monotonic clock/player knowledge/event log, item ownership, and event-id uniqueness all remained true with `failures=[]`. The event log increased by two from the M21 baseline while all other tracked continuity metrics stayed unchanged; this is correctness evidence, not a performance claim.

## Promotion boundary

Milestone 22 completes background NPC-to-NPC diffusion. The next social-authority gap is player-facing dialogue: deterministic `TalkAction` currently selects NPC-known/player-unknown facts without applying `Fact.disclosure_min_relationship`. Milestone 23 should reuse `SocialDisclosurePolicy` for NPC→player disclosure so public facts remain available at neutral trust, restricted facts require the NPC's directed relationship toward the player, and ordinary replayable `RelationshipChanged` events can unlock later dialogue without adding a second trust system.
