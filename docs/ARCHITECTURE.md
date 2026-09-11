# Architecture

## Turn pipeline

```text
Action
→ Resolution
→ Events
→ Validation
→ State
→ Retrieval
→ ScenePlan
→ Narration
```

### 1. Action

`ActionParser` converts input into a structured action (`move`, `inspect`, `talk`, `take`, `wait`, or freeform fallback). The demo uses `DeterministicActionParser`; an LLM parser can later implement the same interface.

### 2. Resolution

`DeterministicResolver` checks local rules before proposing any change. Impossible exits, absent NPCs, missing items, and incapacitating conditions produce structured `ActionResult` failures.

### 3. Events

Accepted material changes become typed domain events such as `PlayerMoved`, `ItemAcquired`, `FactDiscovered`, `NPCLearnedFact`, `RelationshipChanged`, and `TimeAdvanced`. Events are append-only in SQLite.

### 4. Validation

Each event is prechecked, then reduced into a candidate state. The candidate is validated before persistence. Validators detect missing references, invalid locations, ownership disagreement, duplicate unique items, unknown-fact disclosure, resurrection, and backward time/turn movement.

### 5. Canonical state

`WorldState` is authoritative. It contains entities, character state, locations, items, facts, factions, player knowledge, and the world clock. Current-state snapshots are a convenience projection: the initial state plus the persisted event stream can reconstruct the same state.

## Knowledge boundaries

### Objective truth

`Fact` objects exist in canonical world state and describe propositions with truth status, source, discoverability, related entities, and tags.

### NPC knowledge

Each `NPC` owns `NPCKnowledge`. A fact existing globally does not imply that an NPC knows it. `NPCLearnedFact` is required to expand NPC knowledge.

### Player knowledge

Player-discovered facts live separately in `WorldState.player_known_facts`, normally added by `FactDiscovered`.

### Narrative text

Narration is non-authoritative. `ScenePlan` lists only events/observations that actually occurred plus allowed/forbidden information. `NarrativeGenerator` receives the plan but has no state mutation API.

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

The built-in scripted/deterministic implementations keep tests and the demo fully offline.
