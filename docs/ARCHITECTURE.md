# Architecture

## Turn pipeline

```text
Action
→ Resolution
→ Events
→ Validation
→ Candidate State
→ Retrieval
→ ScenePlan
→ Narrative Provider
→ Atomic Commit
```

### 1. Action

`ActionParser` converts input into a structured action (`move`, `inspect`, `talk`, `take`, `wait`, or freeform fallback). The default is `DeterministicActionParser`; `OpenAICompatibleActionParser` can optionally translate natural language into the same strict action union before deterministic resolution.

### 2. Resolution

`DeterministicResolver` checks local rules before proposing any change. Impossible exits, absent NPCs, missing items, and incapacitating conditions produce structured `ActionResult` failures.

### 3. Events

Accepted material changes become typed domain events such as `PlayerMoved`, `ItemAcquired`, `FactDiscovered`, `NPCLearnedFact`, `RelationshipChanged`, and `TimeAdvanced`. Events are append-only in SQLite.

### 4. Validation and candidate state

Each event is prechecked, then reduced into an in-memory candidate state. The candidate is validated before persistence. Validators detect missing references, invalid locations, ownership disagreement, duplicate unique items, unknown-fact disclosure, resurrection, and backward time/turn movement.

The persisted `WorldState` is not changed during this stage.

### 5. Canonical state

`WorldState` is authoritative. It contains entities, character state, locations, items, facts, factions, player knowledge, and the world clock. Current-state snapshots are a convenience projection: the initial state plus the persisted event stream can reconstruct the same state.

## Knowledge boundaries

### Objective truth

`Fact` objects exist in canonical world state and describe propositions with truth status, source, discoverability, related entities, and tags.

### NPC knowledge

Each `NPC` owns `NPCKnowledge`. A fact existing globally does not imply that an NPC knows it. `NPCLearnedFact` is required to expand NPC knowledge.

### Player knowledge

Player-discovered facts live separately in `WorldState.player_known_facts`, normally added by `FactDiscovered`.

### Narrative permission

Player-facing narration may use only facts in `player_known_facts` after the accepted events have been applied to the candidate state. Merely placing an NPC in a scene does **not** grant the player that NPC's private knowledge.

`ScenePlan.information_forbidden_to_reveal` carries fact IDs, not hidden propositions, so an external provider does not need secret content merely to know that it must not invent or disclose it.

### Narrative text

Narration is non-authoritative. `ScenePlan` lists only accepted events, resolver observations, allowed information, and continuity constraints. `NarrativeGenerator` receives the plan but has no state mutation API.

## Memory

Three tiers are present:

1. **Working memory** — recent persisted turns.
2. **Episodic memory** — deterministic `Episode` records with turn range, entities, location, tags, summary, and importance.
3. **Semantic/canonical memory** — current entities, facts, relationships, NPC knowledge, and unresolved world state.

`MemoryRetriever.retrieve_context()` ranks episodes using recency, entity overlap, location overlap, tags, and importance. Full transcript replay is not required for each turn.

## Persistence and replay

SQLite stores:

- session metadata
- initial canonical state
- current-state projection
- append-only events
- turns
- episodic memory

`replay(initial_state, events)` deterministically rebuilds canonical state. Tests compare replayed state against the persisted projection.

## Provider boundary

The provider layer defines replaceable interfaces for:

- `ActionParser`
- `NarrativePlanner`
- `NarrativeGenerator`
- `MemorySummarizer`

Two narrative generators currently exist:

- `ScriptedNarrativeGenerator` — deterministic, offline, used by default and by long-run tests.
- `OpenAICompatibleNarrativeGenerator` — sends a constrained `ScenePlan` to a configurable `/chat/completions` endpoint through a small injectable JSON transport.

The provider implementation lives entirely outside domain models, resolution, reducers, validators, and persistence.

### Failure atomicity

The engine order is intentionally:

```text
resolve
→ reduce into candidate
→ validate candidate
→ build + validate ScenePlan
→ generate narration
→ commit events + state + turn + episode
```

If the external provider times out, rejects the request, or returns malformed JSON, narration raises a typed `ProviderError` before `SQLiteStore.commit_turn()` is reached. The previous canonical state and append-only event log remain unchanged. Integration tests prove this property.

### Transport and secrets

The production transport uses the Python standard library (`urllib`) and enforces a bounded response size. Tests inject a fake transport, so CI never requires network access.

Provider credentials come from environment variables and are only used to build the HTTP `Authorization` header. They are not persisted in game state, event payloads, turns, episodes, or repository files.

## Structured action parsing boundary

An optional `OpenAICompatibleActionParser` translates natural language into the existing `PlayerAction` union. It does not resolve or execute actions.

The provider sees only a deliberately reduced interaction surface:

- current location name
- exit aliases / destination names
- visible item names
- co-located alive and conscious NPC names
- player inventory names
- whether an incapacitating condition blocks movement

It does **not** receive canonical facts, clue propositions, NPC goals, relationships, beliefs, or private NPC knowledge. This keeps action understanding separate from privileged world truth.

Action JSON is parsed through the same Pydantic discriminated union used by the engine, with extra fields forbidden. A provider cannot smuggle mutation instructions beside a valid action. `FallbackActionParser` catches typed provider failures and delegates to `DeterministicActionParser`, with a standard-library warning log for observability.

A successfully parsed action still has no authority. For example, a model may propose `{"kind":"move","destination":"moon"}`; `DeterministicResolver` rejects it because no such exit exists. The rejection may be recorded as a turn, but canonical state and the append-only material event stream remain unchanged.
