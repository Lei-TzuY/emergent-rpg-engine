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
→ Due world-simulation cycles
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

## Mystery graph

Mystery logic is represented in canonical state rather than inferred from narration. `Fact` supports discovery prerequisites and explicit contradiction edges, while `FactInferenceRule` maps a set of premise fact IDs to one derived conclusion.

After accepted resolver events are reduced into the candidate state, `MysteryGraph` deterministically evaluates player inference rules to a fixpoint. Each newly derived conclusion is emitted as `FactInferred`, carrying both the `rule_id` and exact `premise_fact_ids`. Those inference events pass the same precondition validation, reducer, persistence, and replay path as other material state changes.

The validator enforces the provenance boundary: a fact marked `discoverability="inferred"` cannot be introduced through an ordinary `FactDiscovered` event, a discovery gate cannot be bypassed without its prerequisites, and an inference event is rejected unless its observer already knows every registered premise. World validation also rejects dangling mystery references and rules whose conclusion is not marked inferred.

Contradictions are observer-scoped. `MysteryGraph.contradictions(state, observer_id)` compares only facts known by that player/NPC; learning a conflicting claim does not magically transfer either side of the contradiction to another observer. The current engine automatically evaluates derived knowledge for the player after accepted player turns.

## NPC autonomous planning

NPC autonomy is split into planning and execution so that intent generation cannot mutate canonical state. `build_npc_planning_context()` projects a deliberately scoped view containing only that NPC's configured structured goals, completed-goal set, own known facts/beliefs/relationships, current location, local exits, visible local NPCs/items, inventory, and blocking status. It does not expose player knowledge, another NPC's private knowledge, or the full world fact graph.

`DeterministicNPCPlanner` emits a bounded `NPCPlan` of typed intents. Milestone 5 currently supports reach-location and investigate-item goals. `DeterministicNPCResolver` rechecks the evolving canonical candidate before producing `NPCMoved`, `FactDiscovered`, and `NPCGoalCompleted` events; the planner itself has no event/state write API.

`GameEngine.run_npc_phase()` applies a global attempted-intent budget, validates/reduces each emitted event, evaluates mystery inference for the acting NPC using only that NPC's knowledge, validates the resulting world, and commits the whole autonomous phase atomically. A phase with no material events is not persisted. The debug/admin CLI exposes this explicitly as `emergent-rpg npc-step`.

## Deterministic world simulation

`WorldState.simulation` carries canonical cadence configuration and the next due absolute minute. `DeterministicSimulationScheduler` is read-only: it computes a bounded list of due cycle minutes from the canonical clock/cursor and reports whether backlog remains. It cannot write state.

After an accepted player action is resolved, validated, planned, and successfully narrated, the engine processes any due cycles in the same in-memory candidate. Each cycle invokes the existing NPC planning/resolution path with `offscreen_only=True`, so an NPC currently co-located with the player cannot silently act between visible interactions. NPC events still pass ordinary precondition validation, reduction, mystery inference, and world validation.

Every processed cadence slot ends with a `SimulationCycleProcessed` event. Its validator requires the exact current cursor and rejects future/out-of-order markers; the reducer advances the cursor by the configured cadence. The whole set of player events plus background events plus cadence markers is committed in one SQLite transaction and replays to the same projection. Automatic simulation does not create extra player turn numbers.

Background identities/events stay out of the player-facing `Turn.involved_entities` and `Episode` metadata unless the player action itself involved them. This prevents retrieval metadata from becoming an accidental private-world side channel.

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
→ process due deterministic world-simulation cycles
→ validate final candidate
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
