# Player-to-NPC item handoff

Milestone 29 adds a player-facing custody handoff without introducing another inventory store or bypassing the existing action/event authority.

## Executable path

```text
player text / structured provider output
→ GiveAction(item, receiver)
→ deterministic resolver
→ PlayerItemGiven(source_player_id, receiver_npc_id, item_id)
→ reducer custody preconditions
→ shared owner-to-owner transfer helper
→ optional NPCGoalCompleted(method="acquired_item")
→ TimeAdvanced(1)
→ ordinary narration / persistence / replay
```

The deterministic parser accepts `give <item> to <npc>` and quoted multi-word names. The OpenAI-compatible/Ollama action schema exposes the same typed action. Its visible surface was not expanded: providers already receive only the player's inventory and co-located active NPC names, plus the existing player-visible interaction fields.

## Custody authority

`PlayerItemGiven` records exact player, NPC receiver, and item provenance. The resolver requires canonical player custody, a portable item, and a locally visible alive/conscious NPC receiver. The reducer independently rechecks the canonical player, NPC type, liveness/consciousness, co-location, portability, source ownership/inventory, and duplicate receiver custody before mutation.

The actual owner-to-owner mutation is centralized in `_transfer_owned_item()`, which is also used by `NPCItemDelivered`. It removes the item from the source inventory, appends it to the receiver inventory, updates `Item.owner_id`, and leaves `Item.location_id=None`. M29 therefore does not create a second inventory authority.

Invalid raw actions emit no handoff event. A forged invalid typed event fails closed in reduction before a custody mutation can succeed.

## Quest turn-in

After a valid handoff, the resolver checks only the receiver's canonical planning goals. Matching incomplete `acquire_item` goals whose own fact prerequisites are already known to that receiver emit the existing `NPCGoalCompleted(method="acquired_item")` after custody transfer. Player-facing observations report only the visible handoff and do not expose private goal identifiers or prerequisites.

## Integration surface

The browser and HTTP API require no new mutation endpoint. They continue to submit raw text through `GameEngine.process_text()`, so CLI, API, browser, deterministic parsing, OpenAI-compatible parsing, validation/reduction, narration, SQLite persistence, and replay converge on the same path.

Focused regressions cover:

- quoted multi-word deterministic parsing;
- structured-provider `give` JSON without hidden NPC state;
- non-owned, remote, inactive, and nonportable rejection;
- matching acquisition-goal turn-in;
- forged remote typed-event rejection in the reducer;
- SQLite persistence and exact replay;
- FastAPI/browser raw-text `take → give` parity.

## Verification evidence

The first fully green implementation head `b50dfccfb9d0111f090f46718b15ad52df2d1e7c` passed:

- wheel build and packaged browser-asset verification;
- Ruff;
- strict mypy across **47 source files**;
- **192 pytest tests**;
- the seeded 1,000-accepted-turn consistency evaluation;
- JSON report verification.

For seed `20260911`, the long-run gate produced **1,058 submissions / 1,000 accepted / 58 rejected / 2,274 events / 1,058 persisted turns / 1,000 episodes / final clock 4,361**. Replay equality, state validity, clock/player-knowledge/event-log monotonicity, item ownership, and unique event IDs were all true with `failures=[]`.

These are correctness results for the deterministic scenario, not performance measurements.

## Promotion boundary

Milestone 30 should make item turn-in consequences data-driven rather than embedding rewards in `GiveAction` or a named quest. A world-pack rule should be able to match a validated handoff/goal completion and produce bounded replayable consequences such as directed relationship change or fact discovery through existing typed authority. Matching, one-shot behavior, provenance, and consequence ordering must be generic; failed or unmatched handoffs must produce no reward, and provider failure must preserve the existing atomic zero-commit guarantee.
