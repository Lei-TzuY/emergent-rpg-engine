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
12. **Evaluation harness for 1,000+ turn consistency** — deterministic seeded/adversarial workload, periodic replay/invariant checkpoints, machine-readable reports, and a real 1,000-accepted-turn CI gate. **Complete.**
13. **Scheduled world events / environmental simulation** — canonical future-event queue, deterministic due-time execution, replayable schedule consumption, bounded catch-up, API/UI-visible active location conditions, and atomic integration with NPC simulation. **Complete.**
14. **Environmental rules / traversal hazards** — declarative active-condition traversal effects, deterministic additive movement cost, ordinary event emission, player-visible explanation, and long-run replay evidence. **Complete.**
15. **Environmental condition lifecycle / expiry** — canonical lifespans, typed validated expiry events, explicit replayable expiry queues, bounded lifecycle processing, provenance-aware removal, and restoration of baseline rules. **Complete.**
16. **Environmental route access / closures** — data-driven blocked exits, deterministic player/NPC enforcement, planner-visible route filtering, player-visible closure explanation, and automatic route restoration after expiry. **Next.**

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

## Milestone 12 invariant

Long-run evaluation measures deterministic continuity properties, not CI speed:

```text
fixed seed + mixed legal/adversarial action policy
→ ordinary GameEngine execution path
→ accepted canonical turns + explicit rejected submissions
→ periodic persisted-state validation and event replay
→ machine-readable correctness report
```

The harness targets accepted canonical turns rather than merely looping a command. Its seeded scenario mixes valid movement, inspection, item acquisition, and waits with deterministic impossible moves and missing-item attempts. Rejected actions must leave canonical state unchanged while remaining visible in turn history.

At checkpoints, the evaluator independently reloads persisted data and verifies state validity, replay equality, append-only event growth, unique event IDs, item ownership consistency, monotonic world time, and monotonic player knowledge. Final persisted turn and episode counts must match submitted and accepted actions respectively. CI executes a real 1,000-accepted-turn scenario and parses its JSON report rather than trusting process exit alone.

The first complete candidate with seed `20260911` produced 1,058 submitted actions, 1,000 accepted turns, 58 deterministic rejections, 2,268 events, and 1,000 episodes, with checkpoints through turn 1,000, all tracked invariants true, `failures=[]`, and `passed=true`. This is correctness evidence for that deterministic scenario, not a performance, throughput, model-quality, or billing claim.

## Milestone 13 invariant

Future environmental consequences are canonical world data rather than hidden timers:

```text
WorldState.scheduled_location_conditions
→ canonical world clock reaches due minute
→ deterministic bounded scheduler ordered by (due minute, id)
→ ScheduledLocationConditionApplied
→ validator checks exact first pending entry and due time
→ reducer activates Location.active_conditions and consumes schedule entry
→ ordinary persistence / replay
```

The environmental scheduler is merged with existing NPC simulation into one deterministic world-time timeline. Environmental events execute before NPC cycles at the same minute, while both subsystems retain independent catch-up bounds. Narrative generation still precedes automatic simulation, so provider failure preserves zero-partial-commit semantics for both player actions and due world events.

Pending schedule ids/times never enter `PlayerStateView`; only conditions already active at the player's current location are projected to the API/browser. The Ashfall Relay demo therefore does not reveal `yard_ash_squall` before Day 1 08:20, but after the due event the `ash_squall` condition is replayable canonical state and visible in the UI.

The first complete M13 implementation head passed 83 pytest tests and the existing seeded 1,000-accepted-turn gate. That run preserved the same 1,058 submissions / 1,000 accepted / 58 rejected / 1,000 episode behavior while the event log increased from 2,268 to 2,269 events, exactly accounting for the newly scheduled environmental event. All tracked continuity invariants remained true with `failures=[]`.

## Milestone 14 invariant

Environmental mechanics are declarative canonical policy rather than condition-name branches:

```text
Location.active_conditions
→ optional TraversalEffect payloads
→ EnvironmentalRules.traversal_cost()
→ deterministic resolver
→ PlayerMoved + TimeAdvanced
→ ordinary validation / persistence / replay
```

The resolver does not compare against `ash_squall` or any named condition. Baseline movement costs five canonical minutes; active traversal modifiers contribute deterministic additive extra minutes. A synthetic non-Ashfall condition regression proves the rule layer is data-driven, and multiple modifiers compose without adding new resolver branches.

The scheduled Ashfall Yard squall carries `extra_minutes=5`, so movement from the yard costs five minutes before activation and ten minutes after activation. The API exposes the active condition's `traversal_extra_minutes`, and the browser displays the mechanical effect. Narration describes an already-determined outcome and retains no mutation authority; provider failure before commit leaves hazardous movement and its time advance unapplied.

The first fully green M14 candidate passed 90 pytest tests plus the seeded 1,000-accepted-turn evaluation. That run produced 1,058 submissions, 1,000 accepted turns, 58 rejections, 2,414 events, 1,000 episodes, and final canonical clock minute 5,086. Replay equality, state validity, monotonic clock/knowledge/event log, item ownership, and event-id uniqueness all remained true with `failures=[]`. These numbers are correctness evidence, not a throughput benchmark.

## Milestone 15 invariant

Environmental removal is a scheduled typed transition, not arbitrary state deletion:

```text
canonical activation due minute + lifespan
→ deterministic activation slot
→ ScheduledLocationConditionApplied
→ reducer materializes canonical expiry queue
→ deterministic expiry slot
→ ScheduledLocationConditionExpired
→ validated condition removal + expiry consumption
→ persistence / replay
```

The scheduler may derive an expiry slot from a still-pending activation, so a single large world-time jump can execute activation and expiry in one correctly ordered player-turn transaction. Once activation is reduced, the expiry is also explicit persisted state, making restart behavior deterministic.

Expiry validation requires the exact first pending world event, canonical due minute, materialized expiry id, matching location/condition target, and an active condition. `validate_state()` only permits an environmental condition to disappear when the same transition contains matching typed expiry provenance; manual dictionary deletion still fails with `environment_went_backward`.

The demo Ashfall Yard squall activates at Day 1 08:20 and expires at 08:40. Its +5 minute traversal modifier therefore applies only during that canonical interval; after expiry, movement returns to the five-minute baseline and the existing player projection naturally stops exposing the condition.

The first fully green M15 implementation candidate passed 97 pytest tests plus the seeded 1,000-accepted-turn evaluation. That run produced 1,058 submissions, 1,000 accepted turns, 58 rejections, 2,270 events, 1,000 episodes, and final canonical clock minute 4,361. Replay equality, state validity, monotonic clock/knowledge/event log, item ownership, and event-id uniqueness all remained true with `failures=[]`. These are correctness results, not performance measurements.

## Promotion gate for Milestone 16

Environmental conditions should next affect route legality, not only traversal cost. The rule must remain data-driven: active canonical condition payloads may identify blocked destination/location ids, while no resolver branch may special-case `ash_squall` or another content name.

Player movement must reject a blocked local exit without emitting movement/time events. NPC planning context must omit blocked exits so autonomous planning does not repeatedly propose impossible routes, while the NPC resolver must independently reject a forged blocked move intent. The player-facing API/UI should explain currently blocked exits without exposing future schedule metadata. Expiry of the responsible condition must automatically restore the route through ordinary lifecycle replay.

Tests must cover player rejection/state immutability, NPC planner filtering, forged NPC intent rejection, multiple-condition composition, API/UI explanation, automatic reopening after expiry, replay/restart equality, provider/simulation atomicity where applicable, and the existing 1,000-turn continuity gate.
