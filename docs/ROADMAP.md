# Roadmap

The project advances by coherent executable slices rather than placeholder subsystems.

1. **Deterministic core** — canonical state, typed events, validation, replay, memory tiers, persistent CLI demo. **Complete.**
2. **Real LLM provider** — replaceable OpenAI-compatible narration, constrained `ScenePlan` input, offline transport tests, and provider-failure atomicity. **Complete.**
3. **Structured LLM action parsing** — strict typed action JSON, visible-state-only prompt surface, deterministic fallback, and resolver-enforced legality. **Complete.**
4. **Mystery graph** — deterministic clue dependencies, replayable inference provenance, observer-scoped contradictions, and discovery gates. **Complete.**
5. **NPC autonomous planning** — structured goals, epistemically scoped planning contexts, bounded typed intents, deterministic NPC resolution, and replayable goal progress. **Complete.**
6. **World simulation between player turns** — canonical simulation cursor, replayable cadence markers, bounded catch-up, and time-aware off-screen NPC consequences. **Complete.**
7. **Vector/embedding retrieval** — optional semantic retrieval alongside deterministic ranking, with deterministic fallback and no truth authority. **Next.**
8. **Local-model support / Ollama** — explicit local-model presets/routing beyond the generic OpenAI-compatible endpoint.
9. **Web API** — stable service boundary over the core engine.
10. **Web UI** — presentation layer over persisted sessions.
11. **Model routing / cost controls** — per-stage provider selection, budgets, and caching.
12. **Evaluation harness for 1,000+ turn consistency** — repeatable long-run continuity metrics and adversarial scenarios.

## Milestone 3 invariant

The parser never receives mutation authority:

```text
freeform player text
→ visible interaction surface only
→ provider proposes strict PlayerAction JSON
→ Pydantic schema validation (extra fields forbidden)
→ deterministic resolver
→ ordinary event / validation / commit pipeline
```

Provider request/response failures fall back to the deterministic command parser. A syntactically valid but impossible model-proposed action is rejected by the resolver without changing canonical state or appending material events.

## Milestone 4 invariant

Mystery reasoning is canonical and replayable rather than prose-derived:

```text
known canonical facts
→ discovery prerequisite gate
→ deterministic inference rule
→ FactInferred(rule_id + premise_fact_ids)
→ ordinary event validation / reducer / persistence
```

Derived facts cannot be injected as ordinary `FactDiscovered` events. Inference events must match a registered rule exactly, the observer must already know every premise, and the conclusion must be marked `discoverability="inferred"`. Contradictions are computed from each observer's own knowledge set, so player/NPC epistemic boundaries remain intact.

## Milestone 5 invariant

NPC planning is an intent layer, never a mutation layer:

```text
NPC structured goals + own knowledge + local observations
→ bounded NPCPlanningContext
→ typed NPCPlan / NPCIntent
→ deterministic NPC resolver
→ ordinary validated domain events
→ persistence / replay
```

The planner never receives the full `WorldState`. Its context contains only the NPC's own known facts/beliefs/relationships, configured goals, current location, local exits, visible NPCs/items, inventory, and blocking status. A global `max_actions` budget counts attempted intents, not only successful actions. Goal completion is canonical and replayable through `NPCGoalCompleted`, while movement and discovered facts still pass the normal validator/reducer path.

## Milestone 6 invariant

World simulation decides *when* autonomous phases run without becoming a mutation authority:

```text
accepted player events advance canonical clock
→ deterministic scheduler reads SimulationState cursor
→ bounded due-cycle list
→ off-screen NPC planner / deterministic resolver
→ ordinary validated NPC events
→ SimulationCycleProcessed cursor marker
→ one atomic player-turn commit
```

The scheduler never mutates state directly. `SimulationCycleProcessed` must match the exact canonical cursor and cannot be applied before world time reaches that minute. Automatic cycles skip NPCs currently co-located with the player, preventing hidden background execution from invalidating an interaction that is visibly in progress. Catch-up is bounded per player turn, and backlog remains explicit in the cursor for later turns. Off-screen NPC identities and private consequences are not copied into the player-facing turn/episode memory surface.

## Promotion gate for Milestone 7

Vector/embedding retrieval may improve ranking, but it must remain an optional retrieval aid rather than canonical truth. Missing, stale, malformed, or adversarial vector results must not alter world state or disclose facts outside the observer's canonical knowledge. Deterministic retrieval must remain available as a fallback and CI must not require an external vector service.
