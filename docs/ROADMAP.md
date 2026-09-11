# Roadmap

The project advances by coherent executable slices rather than placeholder subsystems.

1. **Deterministic core** — canonical state, typed events, validation, replay, memory tiers, persistent CLI demo. **Complete.**
2. **Real LLM provider** — replaceable OpenAI-compatible narration, constrained `ScenePlan` input, offline transport tests, and provider-failure atomicity. **Complete.**
3. **Structured LLM action parsing** — strict typed action JSON, visible-state-only prompt surface, deterministic fallback, and resolver-enforced legality. **Complete.**
4. **Mystery graph** — deterministic clue dependencies, replayable inference provenance, observer-scoped contradictions, and discovery gates. **Complete.**
5. **NPC autonomous planning** — structured goals, epistemically scoped planning contexts, bounded typed intents, deterministic NPC resolution, and replayable goal progress. **Complete.**
6. **World simulation between player turns** — canonical simulation cursor, replayable cadence markers, bounded catch-up, and time-aware off-screen NPC consequences. **Complete.**
7. **Vector/embedding retrieval** — optional vector cosine reranking over persisted episodes, deterministic fallback, malformed-output rejection, and no truth authority. **Complete.**
8. **Local-model support / Ollama** — explicit Ollama narration/action-parser presets, local defaults, namespaced configuration, and offline transport tests. **Complete.**
9. **Web API** — thin FastAPI boundary over `GameEngine`, player-visible state projection, persisted session/history/action endpoints, and HTTP failure atomicity. **Complete.**
10. **Web UI** — same-origin API-backed browser client with session lifecycle, player-visible state/history rendering, action submission, explicit loading/error states, and packaged static assets. **Complete.**
11. **Model routing / cost controls** — per-stage provider/model configuration, finite request/reserved-token budgets, bounded completion caching, and failure atomicity. **Complete.**
12. **Evaluation harness for 1,000+ turn consistency** — repeatable long-run continuity metrics and adversarial scenarios. **Next.**

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

## Milestone 7 invariant

Vector retrieval is a ranking aid, never a source of truth:

```text
persisted candidate episodes
→ deterministic baseline ranking inputs
→ optional EmbeddingBackend(query + existing episode summaries)
→ validated fixed-width finite vectors
→ cosine score blended with deterministic score
→ bounded episode list
```

The embedding backend cannot return episode IDs or facts, so it cannot inject new memory objects. Canonical semantic facts remain sourced only from the observer's already-known fact IDs. Wrong vector counts, inconsistent dimensions, non-finite values, and backend exceptions discard semantic enrichment and fall back to deterministic ranking. The built-in feature-hashing backend is deterministic, dependency-free, and keeps CI offline.

## Milestone 8 invariant

Local-model support is a configuration/routing preset, not a new authority path:

```text
provider/parser name = ollama
→ namespaced Ollama configuration
→ default http://127.0.0.1:11434/v1
→ existing OpenAICompatibleClient transport
→ existing narration or action-parser boundary
→ deterministic resolver / transactional engine unchanged
```

`EMERGENT_RPG_OLLAMA_MODEL` is explicit and required; base URL, proxy API key, timeout, temperature, and token budget have separate `EMERGENT_RPG_OLLAMA_*` controls. The preset does not inherit generic `EMERGENT_RPG_LLM_API_KEY`, preventing accidental credential bleed into a local endpoint. CI uses injected fake transport and never requires a live Ollama daemon.

## Milestone 9 invariant

The Web API is a transport boundary, not a second engine:

```text
HTTP request
→ Pydantic/FastAPI validation
→ existing ActionParser
→ GameEngine.process_text()
→ resolver / typed events / validators / reducer
→ provider narration + world simulation
→ SQLite atomic commit
→ player-visible HTTP projection
```

Handlers do not construct or reduce domain events and do not write canonical state directly. Session/action responses serialize a dedicated player-visible projection instead of raw `WorldState`, so undiscovered fact truth/source metadata, NPC private knowledge, planning goals, relationships, inference rules, and simulation internals remain hidden. History omits internal involved-entity/tag metadata. Malformed requests are rejected before engine execution; unknown sessions map to `404`, transition invariant failures to `409`, and provider failures to `502` while preserving the engine's pre-commit atomicity. In-process API tests also prove persisted state remains replay-equivalent after accepted HTTP actions.

## Milestone 10 invariant

The browser is a client of the Web API, never a client-side engine:

```text
browser DOM
→ same-origin fetch()
→ player-visible Web API contract
→ GameEngine authority boundary
→ player-visible response
→ DOM rendering
```

The JavaScript does not import Python engine code, read SQLite, create domain events, or infer hidden canonical state. It renders only the bounded Milestone 9 response models and writes returned world/player strings with DOM `textContent`. Session creation/loading, bounded history, action submission, busy state, deterministic rejection, and request/provider errors all flow through the existing API contract. Static browser assets are explicitly included in the wheel and CI opens the built wheel to verify the three required distribution paths, preventing a source-checkout-only UI from being treated as a completed feature.

## Milestone 11 invariant

Model controls remain process-local policy around the existing provider boundary:

```text
stage-specific provider/model configuration
→ bounded completion-cache lookup
→ finite request + reserved-output-token reservation on miss
→ existing provider transport
→ language result only
→ parser proposal or narration prose
→ deterministic GameEngine authority unchanged
```

Narration and action parsing may independently override endpoint, model, credential, timeout, temperature, and max-token configuration while preserving generic configuration as a fallback. Completion-cache keys include stage, endpoint/model, credential fingerprint, prompts, structured payload, temperature, and max-token ceiling. Successful cache hits perform no external request and consume no provider budget.

Budgets count attempted external requests and reserved output-token ceilings, not actual provider token usage or monetary cost. The current transport contract does not require trustworthy usage metadata, so no billing claim is inferred from request limits. A narration budget denial occurs before persistence and leaves state/events/turns unchanged. An action-parser budget denial remains a typed `ProviderError`, allowing the existing deterministic parser fallback; the resolver still decides legality.

Budget/cache metadata is not canonical state and is never persisted as world truth. Offline tests prove route selection, budget accounting, cache isolation, LRU bounds, parser fallback, and transaction atomicity.

## Promotion gate for Milestone 12

The long-run evaluation harness must measure deterministic continuity properties rather than manufacture a score from CI runtime. It should execute repeatable seeded/adversarial scenarios for at least 1,000 turns, validate replay equality and invariant preservation throughout, report machine-readable metrics/failures, and distinguish engine correctness from provider-quality observations. Any performance metric must come from an explicit controlled benchmark configuration rather than ordinary CI timing.
