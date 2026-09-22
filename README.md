# emergent-rpg-engine

A deterministic, persistent foundation for long-running AI-driven text RPGs.

Most chatbot RPGs eventually lose continuity because the transcript is treated as the world: old facts fall out of context, inventory duplicates, NPCs learn secrets they never heard, and prose silently mutates reality. This project instead treats **canonical state + append-only events** as authoritative. Narrative text is a projection of accepted events, never the source of truth.

## Architecture

```text
Player Action
→ Action Parsing
→ Deterministic Resolution
→ Typed Events
→ Continuity Validation
→ Canonical State
→ Memory Retrieval
→ ScenePlan
→ Narrative Generation
→ Append-only Event Log
```

Key boundaries:

- Canonical world state owns location, time, inventory, health, facts, relationships, and NPC knowledge.
- NPC knowledge is separate from objective truth and from player knowledge.
- Every material change is a typed event that can be replayed.
- Mystery deductions are replayable `FactInferred` events with rule/premise provenance.
- NPC autonomy uses scoped planning contexts, bounded typed intents, and deterministic resolution before any state change.
- NPC-to-NPC fact sharing uses source-aware replayable events; the planner chooses a receiver only, while the resolver chooses an actually shareable canonical fact.
- Social disclosure is data-driven: each fact may require a source→receiver relationship threshold, and forged restricted sharing is rejected by generic event validation.
- Player-facing `TalkAction` reuses the same directed `SocialDisclosurePolicy`; blocked facts stay out of player knowledge and narration observations while eligible public facts remain deterministic fallbacks.
- Scheduled off-screen simulation gives ordinary NPC goals and social diffusion independent canonical action budgets; background sharing never consumes movement/investigation capacity.
- Narrative providers cannot mutate canonical state.
- Provider failure happens before the state/event transaction is committed.
- Memory retrieval uses recent turns + persisted episodes + canonical facts; optional vectors only rerank existing episodes.
- The Web API is a thin player-visible projection over the same `GameEngine`, not a second mutation path.
- All tests remain offline; no API key or external service is required for CI.

## Quick start

Requires Python 3.12+.

```bash
python -m venv .venv
# activate the environment
pip install -e ".[dev]"

emergent-rpg new
emergent-rpg play
```

Useful commands:

```bash
emergent-rpg status
emergent-rpg history
emergent-rpg npc-step --max-actions 3
emergent-rpg npc-social-step --max-actions 3
emergent-rpg play
emergent-rpg-api --db emergent-rpg.db
```

Inside the demo:

```text
> inspect room
> take brass key
> talk Lio Marr
> move operations
> inspect console
> talk Arden Vale
> wait 15
```

Sessions persist in `emergent-rpg.db` by default. Pass `--db PATH` to use another SQLite database.

## Real narrative provider

The default `scripted` provider is deterministic and offline. A real OpenAI-compatible Chat Completions endpoint can be selected without changing domain or engine code:

```bash
export EMERGENT_RPG_LLM_BASE_URL="http://127.0.0.1:11434/v1"
export EMERGENT_RPG_LLM_MODEL="your-model"
# Optional for endpoints that require authentication:
export EMERGENT_RPG_LLM_API_KEY="..."

emergent-rpg play --provider openai-compatible
```

The same endpoint can also parse natural-language player actions into strict typed commands:

```bash
emergent-rpg play --action-parser openai-compatible
# Or use the endpoint for both stages:
emergent-rpg play --action-parser openai-compatible --provider openai-compatible
```

Optional controls:

```text
EMERGENT_RPG_LLM_TIMEOUT       default 30 seconds
EMERGENT_RPG_LLM_TEMPERATURE   default 0.7
EMERGENT_RPG_LLM_MAX_TOKENS    default 500
```

Provider credentials are read from the environment rather than command-line flags. The narrative provider receives a constrained `ScenePlan`, not mutable canonical state. Facts known only by an NPC are not automatically made available to player-facing narration.

The LLM action parser receives only the player's current interaction surface: current location name, exits, visible items, co-located conscious NPC names, inventory, and whether movement is blocked. Canonical facts, hidden clues, NPC beliefs, goals, and private NPC knowledge are deliberately omitted. Its JSON output is validated against strict Pydantic action schemas with extra fields forbidden, then passed through the ordinary deterministic resolver.

If action parsing fails, the engine logs the provider failure and falls back to the deterministic command parser. If narrative generation fails, the accepted candidate state is **not committed**. In either case, a provider cannot directly mutate canonical state.

## Ollama / local models

Ollama is an explicit provider/parser preset rather than a separate engine path. With a local Ollama daemon exposing its OpenAI-compatible API, only the model name is required:

```bash
export EMERGENT_RPG_OLLAMA_MODEL="qwen3.5:27b"

emergent-rpg play --provider ollama
emergent-rpg play --action-parser ollama --provider ollama
```

The preset defaults to `http://127.0.0.1:11434/v1`. Optional local-only overrides are `EMERGENT_RPG_OLLAMA_BASE_URL`, `EMERGENT_RPG_OLLAMA_API_KEY`, `EMERGENT_RPG_OLLAMA_TIMEOUT`, `EMERGENT_RPG_OLLAMA_TEMPERATURE`, and `EMERGENT_RPG_OLLAMA_MAX_TOKENS`. Generic `EMERGENT_RPG_LLM_API_KEY` is deliberately not inherited by the Ollama preset.

Both Ollama narration and action parsing reuse the existing OpenAI-compatible transport and safety boundaries. Tests use an injected fake transport, so CI never requires Ollama to be installed or running.

## Web API

The FastAPI layer is executable through:

```bash
emergent-rpg-api --db emergent-rpg.db --host 127.0.0.1 --port 8000
```

It exposes `GET /health`, session create/read, bounded history, and `POST /sessions/{session_id}/actions`. Raw player text still enters `GameEngine.process_text()`, so HTTP requests use the same parser, deterministic resolver, typed events, validators, simulation, persistence, and replay path as the CLI.

Session/action responses serialize a dedicated player-visible projection instead of raw `WorldState`: current location/time, local exits/items/NPCs, inventory, and already-known facts. Hidden propositions, truth/source metadata, NPC private knowledge, goals, relationships, inference rules, and simulation internals are not exposed. Provider failure maps to HTTP `502` without committing state/events/turns. See `docs/API.md` for the endpoint and error contract.

The API can use the same provider/parser modes at process startup:

```bash
emergent-rpg-api --provider scripted --action-parser deterministic
emergent-rpg-api --provider ollama --action-parser ollama
```

## NPC autonomous planning

Milestone 5 adds deterministic autonomous NPC execution without giving a planner mutation authority. NPCs can carry structured goals such as reaching a location or investigating an item. The planner receives only the NPC's own knowledge/social state plus local observations, emits a bounded typed intent, and the deterministic NPC resolver must accept it before normal validated events can change canonical state.

Run one explicit autonomous goal phase with:

```bash
emergent-rpg npc-step --max-actions 3
```

Run one explicit NPC social-information phase with:

```bash
emergent-rpg npc-social-step --max-actions 3
```

The social authority path remains separate from ordinary goal planning. Its planner ranks locally visible receivers using only the source NPC's directed relationship scores, but it still does not see receiver-private facts or choose a fact. The deterministic resolver computes source-known / receiver-unknown facts and filters them through each fact's canonical `disclosure_min_relationship`; missing source→receiver relationship entries are neutral score `0`, while ordinary facts default to public threshold `-100`. Generic event validation repeats the same policy so forged restricted sharing cannot bypass trust requirements. Ashfall Relay's `fact_relay_sabotage` is a real restricted clue requiring relationship score `20`. Player-facing `talk` uses that same source-directed policy before emitting the ordinary player `FactDiscovered`, so a restricted fact can be withheld while another eligible public fact is revealed. Existing replayable NPC→player `RelationshipChanged` events can unlock later dialogue. The same social authority is therefore shared by player dialogue, explicit `npc-social-step`, and automatic off-screen simulation. See `docs/NPC_FACT_SHARING.md`, `docs/SOCIAL_DISCLOSURE.md`, `docs/OFFSCREEN_SOCIAL_SIMULATION.md`, and `docs/PLAYER_DIALOGUE_DISCLOSURE.md` for invariants and verification evidence.

The current demo lets Dax pursue a location goal and Lio investigate a locally visible clue. Explicit `npc-step` and `npc-social-step` phases remain available for debugging/operator control, while accepted player actions also trigger deterministic off-screen goal and social simulation when the canonical world clock reaches a scheduled cadence.

## Deterministic world simulation

The canonical world carries a five-minute simulation cadence and replayable next-due cursor. Accepted player actions that advance time can trigger bounded off-screen NPC cycles before the turn is committed. Each processed slot is recorded as a `SimulationCycleProcessed` event, so the scheduling decision itself can be replayed and validated rather than existing as hidden process state.

Each due NPC slot first runs the ordinary off-screen goal phase under `max_npc_actions_per_cycle`, then a separately bounded off-screen social phase under `max_social_actions_per_cycle`, then emits the simulation marker. Both phases use the same candidate state and commit atomically with the triggering player turn. The social source set is recomputed after ordinary NPC movement, so an NPC that just entered the player's location cannot immediately take part in hidden social exchange.

Automatic cycles skip NPCs currently sharing the player's location. This keeps visible conversations/interactions stable while still allowing remote NPCs to move, investigate evidence, update private knowledge, and exchange disclosure-eligible facts. A large time jump processes at most the configured catch-up budget in one player turn; any remaining backlog stays explicit for later turns. Player narration and episodic-memory metadata do not receive hidden NPC identities merely because a background goal or social cycle occurred.

## Optional vector memory retrieval

`MemoryRetriever` keeps its deterministic recency/entity/location/tag/importance ranking by default. An optional `EmbeddingBackend` can add cosine similarity as a reranking signal over the **same persisted Episode objects**. The backend receives text and returns vectors only; it cannot return new episode IDs, facts, or state changes.

`HashingEmbeddingBackend` is a built-in offline feature-hashing implementation that produces normalized deterministic vectors without a network service or extra dependency. It proves the vector path end-to-end and can be replaced by a neural embedding backend later. Malformed batches, inconsistent dimensions, NaN/Inf values, or backend exceptions automatically fall back to deterministic ranking.

Canonical semantic facts are still selected only from `player_known_facts`, so vector retrieval cannot reveal NPC-private facts or promote unobserved world truth into player memory.

## Demo world: Ashfall Relay

Ashfall Relay is an original frontier mystery with six locations, five NPCs, two factions, eight items, and a chain of clues around a suspicious communications blackout. Different NPCs know different facts. Clues can have prerequisite gates, deterministic deductions can unlock derived facts with replayable provenance, and contradictory testimony remains scoped to the observer who actually learned it. Evidence can remain untouched for hundreds of turns and still be recovered because it lives in canonical state, not narration context.

## Development

```bash
ruff check .
mypy src/emergent_rpg
pytest
```

CI runs all three checks on Python 3.12, builds the wheel, verifies packaged browser assets, and executes the seeded 1,000-accepted-turn consistency gate. Provider, embedding, FastAPI, NPC social, social-simulation, and dialogue-disclosure integration tests remain offline.

## Current limitations

Basic deterministic unarmed combat now includes replayable stamina expenditure/recovery, provenance-linked damage, bounded deterministic NPC retaliation, player-visible health/stamina, and lethal state transitions. Weapon/equipment data, armor, initiative, hit chance, and broader combat AI remain future work. Authentication/multi-user API concerns and neural embedding integration also remain future work.

The OpenAI-compatible provider currently targets the common `/chat/completions` JSON shape and intentionally supports text responses only. Live endpoint interoperability depends on the selected server/model and is not claimed by offline CI.

There is intentionally no `LICENSE` file yet: the repository did not state a license intent, so this implementation does not guess one on the owner's behalf.
