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
16. **Environmental route access / closures** — data-driven blocked exits, deterministic player/NPC enforcement, parser/API/CLI/UI projection, validator backstop, and automatic route restoration after expiry. **Complete.**
17. **Knowledge-scoped NPC multi-hop navigation / rerouting** — explicit NPC route knowledge, bounded deterministic path selection over known topology, dynamic closure-aware replanning, resolver-validated step execution, persistence, and replay without global-world omniscience. **Complete.**
18. **Replayable NPC map learning / route discovery** — typed observation-driven expansion of NPC map knowledge, physical-presence validation, reducer-owned knowledge updates, monotonic provenance, off-screen simulation integration, and persistence/replay without cross-observer leakage. **Complete.**
19. **Knowledge-scoped NPC item pursuit / search** — replayable observer-specific item-location beliefs, pursuit over known topology, stale-belief correction by local observation, and deterministic local inspection without global item-truth leakage. **Complete.**
20. **Replayable NPC information exchange / fact sharing** — source-aware typed fact transfer between co-located NPCs, speaker-knowledge validation, receiver-only canonical updates, and replayable provenance without bulk private-memory copying. **Next.**

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

The scheduler never mutates state directly. `SimulationCycleProcessed` must match the exact current cursor and cannot be applied before world time reaches that minute. Automatic cycles skip NPCs currently co-located with the player, preventing hidden background execution from invalidating an interaction that is visibly in progress. Catch-up is bounded per player turn, and backlog remains explicit in the cursor for later turns. Off-screen NPC identities and private consequences are not copied into the player-facing turn/episode memory surface.

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

## Milestone 16 invariant

Environmental route access is derived from canonical active conditions rather than by mutating topology:

```text
Location.exits + active LocationCondition.route payloads
→ EnvironmentalRules.route_access()
→ accessible exits / blocked exits
→ player resolver + NPC planning/resolver
→ independent movement-event validation
→ ordinary reducer / persistence / replay
```

`RouteEffect` identifies blocked local destination ids. State validation rejects non-local route targets, and neither the player nor NPC resolver contains a condition-name branch. Blocked player actions emit no movement/time events; forged `PlayerMoved` and `NPCMoved` events are independently rejected by validator preconditions.

NPC planning receives only currently accessible local exits, so it does not intentionally propose a route already blocked by the active environment. The NPC resolver remains a second backstop for forged intents. The action-parser visible state, Web API, CLI, and browser all use the same current route policy and explain active blockers without exposing future scheduled-event ids or due times.

The demo Ashfall squall temporarily blocks Yard → Glass Ridge from 08:20 until its typed expiry at 08:40 while retaining its existing traversal-cost effect on routes that remain open. Because `Location.exits` is never rewritten, expiry automatically restores the Ridge route through ordinary lifecycle replay; there is no separate unblock event.

The first fully green M16 implementation head passed 104 pytest tests plus the seeded 1,000-accepted-turn evaluation. That run produced 1,058 submissions, 1,000 accepted turns, 58 deterministic rejections, 2,270 events, 1,000 episodes, and final canonical clock minute 4,361. Replay equality, state validity, monotonic clock/knowledge/event log, item ownership, and event-id uniqueness all remained true with `failures=[]`. These figures are correctness evidence, not performance measurements.

## Milestone 17 invariant

NPC navigation is deterministic over epistemically scoped map knowledge, not the full world graph:

```text
NPC.knowledge.mapped_locations
→ static topology for mapped locations only
+ currently observable local exits
→ local exits filtered by EnvironmentalRules
→ bounded NPCPlanningContext.known_routes
→ deterministic <=8-hop BFS with lexical tie-breaking
→ one local NPCMoveIntent
→ resolver recomputes and validates the same next hop
→ ordinary NPCMoved / final NPCGoalCompleted
→ persistence / replay
```

The current location is always directly observable, so its adjacency reflects active local closures. Remote mapped locations expose only their static known topology; remote current hazards are deliberately absent until the NPC reaches that location. The planner therefore can re-route when a closure becomes locally observable without receiving omniscient live-world data.

Multi-hop travel remains phase-by-phase. Intermediate steps emit `NPCMoved` only, while `NPCGoalCompleted(method="reached_location")` is emitted only when the accepted step reaches the final target. The resolver independently checks liveness, local adjacency, environmental route access, and recomputes the deterministic next hop, so a forged accessible detour that does not match the NPC's own known route is rejected.

The first fully green M17 implementation head passed wheel/package checks, Ruff, strict mypy across 45 source files, **110 pytest tests**, and the seeded 1,000-accepted-turn evaluation plus JSON verifier. The focused suite proves stable equal-length tie-breaking, an eight-hop bound, refusal to route through unmapped global topology, local rerouting after remote closure discovery, final-hop-only goal completion, and a three-phase SQLite persistence/replay path from Bunkhouse through Yard and Operations to Archive.

For seed `20260911`, the long-run gate produced 1,058 submissions, 1,000 accepted turns, 58 deterministic rejections, 2,270 events, 1,058 persisted turns, 1,000 episodes, and final canonical clock minute 4,361. Replay equality, state validity, monotonic clock/knowledge/event log, item ownership, and event-id uniqueness all remained true with `failures=[]`. These figures are correctness evidence, not performance measurements.

## Milestone 18 invariant

NPC map learning is a typed observer-specific transition rather than planner-side memory or direct state mutation:

```text
accepted NPC intent
→ local observation at current location
→ NPCLocationMapped if fresh
→ ordinary reducer updates only that NPC
→ optional movement
→ NPCLocationMapped at arrival if fresh
→ persistence / replay
```

A valid mapping event requires an existing location and an NPC who is alive, conscious, and physically present there. Duplicate observations are rejected at event-precondition level. Final-state validation requires every newly added `(npc_id, location_id)` relative to the previous state to have matching transition-event provenance, rejects missing mapped locations, and treats map knowledge as monotonic: an NPC cannot silently forget a previously mapped location.

Mapping does not bypass the existing NPC action budget. Idle NPCs with no accepted intent do not generate background observation events. For movement, the current location is mapped before `NPCMoved` and the arrival location only after movement has placed the NPC there; inspection and already-satisfied reach goals map only the current location before their ordinary completion events. The planner still receives scoped `NPCPlanningContext` and retains no mutation authority.

Explicit autonomous phases pass their emitted events to final provenance validation. Automatic off-screen simulation already aggregates the same events in the player-turn simulation transaction. Provider narration failure occurs before scheduled simulation, so map learning cannot leak into a failed player turn.

The first fully green M18 implementation head passed wheel/package checks, browser-asset verification, Ruff, strict mypy across 45 source files, **119 pytest tests**, and the seeded 1,000-accepted-turn evaluation plus JSON verifier. Focused coverage proves remote/duplicate observation rejection, unauthorized direct map mutation rejection, map-memory monotonicity, current/arrival event ordering, idempotence for known locations, acting-NPC-only knowledge, SQLite restart/replay equality, off-screen simulation isolation, and provider-failure atomicity.

For seed `20260911`, the long-run gate produced 1,058 submissions, 1,000 accepted turns, 58 deterministic rejections, **2,272 events**, 1,058 persisted turns, 1,000 episodes, and final canonical clock minute 4,361. Replay equality, state validity, monotonic clock/player knowledge/event log, item ownership, and event-id uniqueness all remained true with `failures=[]`. The two-event increase over M17 is explained by real replayable off-screen Dax map observations. These figures are correctness evidence, not performance measurements.

## Milestone 19 invariant

NPC item pursuit is driven by observer-specific memory rather than authoritative remote item truth:

```text
accepted NPC action at a physical location
→ local NPCItemLocationObserved when configured target is seen/missing
→ NPCKnowledge.item_location_beliefs for that NPC only
→ NPCPlanningContext.known_item_locations
→ bounded deterministic route over known topology toward remembered location
→ local inspection/search
→ positive confirmation, ordinary inspection, or negative stale-belief correction
→ persistence / replay
```

`NPCPlanningContext` never receives authoritative remote `Item.location_id`. A belief is allowed to become stale when another actor moves an item elsewhere, and the engine deliberately does not synchronize that private memory from global state. The planner may chase the stale location only through map topology already known to that NPC. Reaching the remembered location does not complete the investigation; an accessible item must still pass the ordinary inspection path, while an absent item produces an accepted local search and a replayable negative observation that clears only the matching stale belief.

`NPCItemLocationObserved` requires an existing, alive, conscious NPC physically present at the observation location. Positive observation requires the ground item to actually be present; negative observation requires a matching remembered location and an item that is no longer there. State validation checks item/location references and reconstructs every belief change from transition-event provenance, so direct dictionary mutation and forged remote observation are rejected. Observation affects only the acting NPC and does not transfer knowledge to the player or another NPC.

The first fully green M19 implementation head `7c5db0c819f01ef2fef1be6e47b7984e8a8a3706` passed wheel/package checks, browser-asset verification, Ruff, strict mypy across 45 source files, **127 pytest tests**, and the seeded 1,000-accepted-turn evaluation plus JSON verifier. Focused coverage proves scoped planning context, remote observation rejection, positive/negative observation, provenance enforcement, cross-NPC isolation, stale-belief pursuit and correction, forged pursuit rejection, successful local inspection, SQLite restart, and replay equality.

For seed `20260911`, the long-run gate produced 1,058 submissions, 1,000 accepted turns, 58 deterministic rejections, 2,272 events, 1,058 persisted turns, 1,000 episodes, and final canonical clock minute 4,361. Replay equality, state validity, monotonic clock/player knowledge/event log, item ownership, and event-id uniqueness all remained true with `failures=[]`. The default long-run scenario does not exercise additional item-memory events, so the event count remains the M18 baseline; M19 behavior is covered by dedicated integration regressions. These figures are correctness evidence, not performance measurements.

## Promotion gate for Milestone 20

NPC facts, maps, and item-location beliefs are still private unless independently learned. The existing `NPCLearnedFact` event can add a fact to one NPC, but it carries no source identity and currently does not represent a validated social transfer. The next coherent slice should make deliberate NPC-to-NPC fact communication replayable without bulk-copying private memory:

```text
source NPC known fact + physical co-location with receiver
→ bounded deterministic share decision / explicit sharing operation
→ typed source→receiver fact-sharing event
→ validator proves source knows fact and both NPCs can interact locally
→ reducer expands receiver facts only
→ ordinary inference / persistence / replay
```

A transfer must reject missing/dead/unconscious/remote participants, an unknown source fact, and a receiver that already knows the fact. It must not copy map topology, item-location beliefs, relationships, or the source's entire fact set. Player knowledge remains separate unless an explicit player-facing interaction independently reveals the fact. Persistence/restart/replay and the existing 1,000-turn continuity gate must remain green.