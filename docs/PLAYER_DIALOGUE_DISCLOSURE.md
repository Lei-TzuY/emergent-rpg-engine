# Player dialogue disclosure

Milestone 23 closes the trust-policy gap between NPC-to-NPC information exchange and player-facing conversation. `TalkAction` now uses the same canonical `SocialDisclosurePolicy` as explicit and automatic NPC social sharing rather than introducing a dialogue-only trust system.

## Authority boundary

Player-facing dialogue follows one deterministic path:

```text
local conscious NPC
→ NPC-known / player-unknown facts
→ MysteryGraph discovery prerequisite gate
→ SocialDisclosurePolicy(NPC → player)
→ lexical first eligible fact
→ ordinary FactDiscovered(observer=player)
→ GameEngine validation / narration / persistence / replay
```

`Fact.disclosure_min_relationship` remains canonical world data. The relationship lookup is directed from the speaking NPC toward the player; a reverse score does not authorize disclosure. Public facts retain the backwards-compatible default threshold `-100`, while restricted facts can require higher trust.

The resolver still emits the ordinary `FactDiscovered` event. No player-dialogue knowledge event, direct state mutation, API-only rule, or browser-only rule exists.

## Withholding and fallback

A valid conversation remains accepted and advances canonical time when every new fact is disclosure-blocked. In that case no `FactDiscovered` event is emitted and the restricted proposition is not placed in the resolver observations that feed narration.

If a restricted lexical candidate is blocked but another public candidate is eligible, dialogue deterministically falls back to the lexical first eligible public fact. Discovery prerequisites and disclosure policy are independent gates: a fact must satisfy both before it can be revealed.

Existing replayable `RelationshipChanged(source=npc, target=player, delta=...)` events can cross a fact threshold and unlock that fact on a later conversation. The trust change itself remains canonical event-driven state.

## Transport parity

CLI input, the FastAPI action endpoint, the browser client, and structured LLM-parsed `talk` requests all converge on the same `DeterministicResolver`. Milestone 23 therefore changes the resolver once instead of adding transport-specific trust branches.

An API integration regression creates low-trust and high-trust sessions over the same SQLite store. The low-trust session returns an accepted conversation with no restricted fact in the player-visible projection; the high-trust session returns the same canonical fact object that was persisted and replayed by the engine.

## Verification evidence

The first fully green M23 implementation head `03255797e789713787212b6983c6fc22bde19578` passed standard wheel/package verification, packaged browser-asset checks, Ruff, strict mypy across **46 source files**, **149 pytest tests**, the seeded 1,000-accepted-turn consistency evaluation, and the JSON verifier.

Focused coverage proves restricted withholding without conversation rejection, absence of restricted proposition leakage in resolver observations/API response, deterministic public fallback, directed replayable trust unlock, SQLite persistence/replay, and API low/high-trust parity.

For seed `20260911`, the long-run gate produced 1,058 submitted actions, 1,000 accepted turns, 58 deterministic rejections, **2,274 events**, 1,058 persisted turns, 1,000 episodes, and final canonical clock minute 4,361. Replay equality, state validity, monotonic clock/player knowledge/event log, item ownership, and event-id uniqueness all remained true with `failures=[]`. The seeded workload does not contain `talk` actions, so M23 leaves the M22 long-run event count unchanged; dialogue behavior is covered by dedicated resolver/SQLite/API integration regressions.

## Promotion boundary

The next social-architecture debt is relationship progression itself. Generic `DeterministicResolver` still contains an Ashfall-specific branch that grants Arden +5 trust toward the player when `fact_relay_sabotage` is already known. Milestone 24 should replace world-specific NPC/fact-id branching with canonical data-driven dialogue relationship rules that emit the existing replayable `RelationshipChanged` event.

The rule layer should define trigger conditions and bounded directed relationship effects as world data, evaluate them deterministically after dialogue outcomes, prevent uncontrolled repeated farming when a rule is intended to be one-shot, and keep the generic resolver free of Ashfall entity/fact literals. Persistence/replay and all existing disclosure semantics must remain unchanged.
