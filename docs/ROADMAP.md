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
20. **Replayable NPC information exchange / fact sharing** — source-aware typed fact transfer between co-located NPCs, speaker-knowledge validation, receiver-only canonical updates, explicit bounded social execution, CLI integration, and replayable provenance without bulk private-memory copying. **Complete.**
21. **Relationship-gated social disclosure / trust policy** — data-driven per-fact disclosure requirements, source→receiver relationship scoring, resolver-enforced eligibility, and deterministic selective sharing without exposing receiver-private knowledge to the planner. **Complete.**
22. **Automatic off-screen social diffusion / simulation integration** — independent canonical social-action budget per simulation cycle, off-screen-only trust-gated fact propagation, ordinary NPC-budget isolation, atomic persistence/replay, and no player-facing metadata leakage. **Complete.**
23. **NPC→player dialogue disclosure / trust-gated conversation** — canonical social-disclosure policy reused by `TalkAction`, directed NPC→player trust thresholds, deterministic public fallback, and replayable relationship-based unlock across CLI/API/browser paths. **Complete.**
24. **Data-driven dialogue relationship rules** — canonical world-pack relationship rules, deterministic priority, replayable one-shot provenance, and generic resolver/reducer policy without Ashfall-specific branches. **Complete.**
25. **Replayable NPC social relationship progression** — NPC fact sharing reuses the same canonical relationship-rule engine with source→receiver directionality, one-shot anti-farming, and explicit/off-screen execution parity. **Complete.**
26. **Knowledge-gated reactive NPC goals** — canonical `required_fact_ids`, acting-NPC-only eligibility, planner/resolver/reducer backstops, and social-learning activation on later goal phases. **Complete.**
27. **Autonomous NPC item acquisition / custody** — knowledge-scoped acquisition goals, existing `ItemAcquired` authority, generic custody validation, observer-scoped memory cleanup, persistence/replay, and off-screen execution. **Complete.**
28. **Replayable item handoff / delivery goals** — canonical owner-to-owner custody transfer with exact source/receiver/item/goal provenance, knowledge-scoped rendezvous planning, unique ownership, and replay-safe inventory movement. **Complete.**
29. **Player→NPC item handoff / quest turn-in** — typed player `GiveAction`, local receiver visibility, deterministic custody transfer, parser/API/browser parity, transactional rejection, replay-safe player-to-NPC inventory movement, and matching acquisition-goal completion. **Complete.**
30. **Data-driven item turn-in consequences / rewards** — canonical world-pack rules that match validated handoffs or turn-ins and emit bounded replayable consequences through existing fact/relationship authority. **Complete.**
31. **Replayable player objective progression** — canonical data-driven objective definitions, deterministic activation/completion fixed-point, typed lifecycle events, hidden-prerequisite-safe player projection, persistence/replay, and provider-failure atomicity. **Complete.**
32. **Replayable player objective deadlines / failure lifecycle** — canonical absolute-minute deadlines, typed validated failure events, completion-before-failure precedence, active/completed/failed provenance, and CLI/API/browser projection. **Complete.**
33. **Data-driven objective outcome consequences** — bind validated completion/failure outcomes to bounded replayable fact/relationship consequences through existing event authorities, deterministic priority, and one-shot outcome provenance. **Complete.**
34. **Objective-triggered scheduled world consequences** — allow validated objective outcomes to enqueue bounded replayable environmental consequences into the existing canonical world-event timeline. **Complete.**
35. **Deterministic player combat / damage provenance** — add a typed player attack action and provenance-rich validated damage authority across parser/resolver/reducer/API/browser paths without allowing prose to decide damage. **Next.**

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

Derived facts cannot be injected as ordinary `FactDiscovered` events. Inference events must match a registered rule exactly, the observer must already know every premise, and the conclusion must be marked inferred. Contradictions are computed from each observer's own knowledge set, so player/NPC epistemic boundaries remain intact.

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

## Milestone 20 invariant

NPC information exchange is an explicit social action path rather than an implicit planner-side memory copy or ordinary-goal fallback:

```text
source NPC own known facts + locally visible NPC ids
→ social planner chooses receiver only
→ NPCShareFactIntent(receiver_id)
→ resolver reads canonical source/receiver knowledge
→ lexical first source-known / receiver-unknown fact
→ NPCFactShared(source, receiver, fact)
→ generic precondition validation
→ reducer updates receiver facts only
→ receiver-scoped mystery inference
→ state validation / SQLite commit / replay
```

The intent contains no `fact_id`, so the planner cannot invent a fact, choose one the source does not know, or inspect the receiver's private fact set. The event validator independently requires distinct existing alive/conscious co-located NPCs, an existing fact, a source that already knows it, and a receiver that does not. The reducer changes only `receiver.knowledge.facts_known`; player knowledge, route maps, item-location beliefs, relationships, inventories, and objective truth metadata remain untouched.

Sharing is deliberately separated from ordinary goal planning and automatic world simulation. The first implementation used an ordinary planner fallback, and full pytest exposed four regressions where blocked/unresolved/completed goals no longer idled and sharing could consume movement/investigation budget. The corrected design adds `GameEngine.run_npc_social_phase()` with its own attempted-action budget and the explicit `emergent-rpg npc-social-step` CLI surface. Ordinary `npc-step` behavior and background simulation retain their previous semantics.

A successful share may immediately unlock ordinary deterministic inference for the receiver, but only from that receiver's post-share knowledge. The source does not inherit receiver-only conclusions. Social phases are persisted as ordinary events/state/turns and must replay exactly after restart.

The final executable M20 implementation head `0dd4b35ac191d72817a66dfa76e6cf2ac31a7f3f` passed standard wheel/package checks, browser-asset verification, Ruff, strict mypy across 45 source files, **134 pytest tests**, and the seeded 1,000-accepted-turn evaluation plus JSON verifier. Focused coverage proves ordinary-goal isolation, planner receiver-only scoping, lexical resolver selection, forged/remote/duplicate/inactive rejection, receiver-only updates, receiver inference, SQLite persistence/restart/replay, and the CLI execution surface.

For seed `20260911`, the long-run gate produced 1,058 submissions, 1,000 accepted turns, 58 deterministic rejections, 2,272 events, 1,058 persisted turns, 1,000 episodes, and final canonical clock minute 4,361. Replay equality, state validity, monotonic clock/player knowledge/event log, item ownership, and event-id uniqueness all remained true with `failures=[]`. The seeded player workload does not invoke the explicit social phase, so the event count remains the M19 baseline; M20 social behavior is covered by dedicated engine/validator/CLI integration regressions.

## Milestone 21 invariant

Selective NPC disclosure is canonical policy rather than a planner convention or fact-id branch:

```text
Fact.disclosure_min_relationship
+ source NPC directed relationship toward a visible receiver
→ social planner ranks receiver using source-owned social state only
→ NPCShareFactIntent(receiver_id)
→ resolver computes source-known / receiver-unknown facts
→ SocialDisclosurePolicy filters by source→receiver relationship
→ lexical first eligible fact
→ NPCFactShared
→ generic validator repeats disclosure policy
→ receiver-only reduction / inference / persistence / replay
```

Every fact carries a bounded relationship threshold. The default is `-100`, so existing/public facts remain shareable and the M20 contract is backwards-compatible. Missing source→receiver relationships resolve to deterministic neutral score `0`. Relationships are directed: receiver→source trust does not authorize disclosure in the opposite direction. Ashfall Relay's `fact_relay_sabotage` is an executable restricted clue requiring source→receiver score `20`.

The planner still never receives receiver-private fact knowledge and cannot choose a fact. It only ranks locally visible receivers by the source NPC's own relationship map, with lexical id tie-breaking. The resolver distinguishes merely-new facts from disclosure-eligible facts, skipping restricted facts when an eligible public fact exists. If every new fact is blocked, the social action is rejected. `validate_event_preconditions()` calls the same `SocialDisclosurePolicy`, so a forged restricted `NPCFactShared` cannot bypass the threshold.

Existing replayable `RelationshipChanged(source_id, target_id, delta)` events can deterministically unlock later disclosure. Focused regressions prove source-directionality, neutral public sharing, restricted withholding, relationship-based unlock, receiver ranking, eligible-public fallback, generic forged-event rejection, and SQLite persistence/replay.

The fully green M21 implementation head `31d73f5695969af26905e40e59c71aa2e30ab920` passed standard wheel/package checks, browser-asset verification, Ruff, strict mypy across **46 source files**, **140 pytest tests**, and the seeded 1,000-accepted-turn evaluation plus JSON verifier.

For seed `20260911`, the long-run gate produced 1,058 submissions, 1,000 accepted turns, 58 deterministic rejections, 2,272 events, 1,058 persisted turns, 1,000 episodes, and final canonical clock minute 4,361. Replay equality, state validity, monotonic clock/player knowledge/event log, item ownership, and event-id uniqueness all remained true with `failures=[]`. The seeded player workload does not invoke the explicit social phase, so the event count remains the M20 baseline; M21 behavior is covered by dedicated trust/disclosure integration regressions.

## Milestone 22 invariant

Automatic social diffusion is a scheduled use of the existing social authority path, not a second knowledge-mutation subsystem:

```text
canonical simulation cadence
→ ordinary off-screen NPC goal phase under max_npc_actions_per_cycle
→ off-screen social phase under max_social_actions_per_cycle
→ existing planner / SocialDisclosurePolicy / resolver / validator
→ NPCFactShared + receiver-scoped inference
→ SimulationCycleProcessed
→ one atomic player-turn commit / replay
```

The ordinary and social phases have independent canonical budgets, so information exchange cannot consume movement or investigation capacity. Social-source eligibility is recomputed after the ordinary phase and excludes NPCs at the player's current location. Because a valid share also requires source and receiver to be physically co-located, accepted automatic transfers remain off-screen. The explicit `npc-social-step` path deliberately retains `offscreen_only=False` for operator-driven execution.

Scheduling does not copy facts or change relationships directly. Every automatic transfer still passes the Milestone 20–21 planner, resolver, `SocialDisclosurePolicy`, generic event validation, receiver-only reducer, and receiver-scoped mystery inference. Off-screen participant ids/private facts remain absent from player-facing `Turn` and `Episode` metadata.

Narrative generation still occurs before due simulation. Provider failure therefore leaves player events, NPC goal events, social events, simulation markers, turns, and state uncommitted. Goal actions, social transfers, and the cadence marker are reduced on one candidate state and persist only when the complete player-turn transaction succeeds.

The first fully green M22 implementation head `d1d5a1753381e5c3d81f656018ba311549178fb3` passed standard wheel/package checks, browser-asset verification, Ruff, strict mypy across **46 source files**, **144 pytest tests**, the seeded 1,000-accepted-turn evaluation, and the JSON verifier. Focused SQLite regressions prove bounded automatic sharing, player-visible NPC exclusion, independent ordinary/social budgets, goal→social→marker ordering, replay equality, player-metadata isolation, and provider-failure zero-commit behavior.

For seed `20260911`, the long-run gate produced 1,058 submissions, 1,000 accepted turns, 58 deterministic rejections, **2,274 events**, 1,058 persisted turns, 1,000 episodes, and final canonical clock minute 4,361. Replay equality, state validity, monotonic clock/player knowledge/event log, item ownership, and event-id uniqueness all remained true with `failures=[]`. The event log increased by two from the M21 baseline while all other tracked continuity metrics stayed unchanged; these figures are correctness evidence, not performance measurements.

## Milestone 23 invariant

Player-facing dialogue now uses the same disclosure authority as NPC-to-NPC sharing:

```text
local conscious NPC
→ NPC-known / player-unknown facts
→ MysteryGraph discovery gate
→ SocialDisclosurePolicy using NPC → player relationship
→ lexical first eligible fact
→ ordinary FactDiscovered(observer=player)
→ validation / narration / persistence / replay
```

Restricted facts can be withheld while the conversation itself remains accepted. If a restricted lexical candidate is blocked but a public candidate is eligible, the resolver deterministically falls back to the public fact. Existing directed `RelationshipChanged` state can unlock a restricted fact on a later conversation, and CLI/API/browser/LLM-parsed talk inputs all converge on the same resolver path.

The fully green M23 implementation head `03255797e789713787212b6983c6fc22bde19578` passed strict mypy across **46 source files**, **149 pytest tests**, and the real 1,000-turn gate with 1,058 submissions / 1,000 accepted / 58 rejected / 2,274 events / final clock 4,361 and `failures=[]`. Detailed evidence is in `docs/PLAYER_DIALOGUE_DISCLOSURE.md`.

## Milestone 24 invariant

Dialogue relationship progression is canonical world data rather than an Ashfall-specific resolver branch. `DialogueRelationshipRule` defines directed participants, fact prerequisites, bounded delta, priority, and one-shot behavior. Accepted dialogue may emit the existing `RelationshipChanged(rule_id=...)`, and reducer-side `DialogueRelationshipPolicy` independently revalidates the rule after any same-conversation fact discovery. Applied one-shot rule IDs are canonical replayed state, preventing farming.

The fully green M24 implementation head `9f96bbf7150bf8284f4c35fb8f99d597ff769b70` passed strict mypy across **47 source files**, **156 pytest tests**, and the seeded 1,000-turn gate with 2,274 events and `failures=[]`. Detailed evidence is in `docs/DIALOGUE_RELATIONSHIP_RULES.md`.

## Milestone 25 invariant

NPC-to-NPC social execution reuses the same relationship-rule engine after an accepted `NPCFactShared`. Event ordering is `NPCFactShared → optional RelationshipChanged`, so reducer provenance validation sees the receiver's newly canonical fact before evaluating the rule. The consequence remains inside the same social action budget slot; source→receiver directionality, one-shot anti-farming, explicit/off-screen parity, persistence, and replay all use the existing authority path.

The fully green M25 implementation head `0db148349b69cbfc348b84d30ee2ce80c0409e0a` passed strict mypy across **47 source files**, **159 pytest tests**, and the seeded 1,000-turn gate with 2,274 events and `failures=[]`. Detailed evidence is in `docs/NPC_SOCIAL_RELATIONSHIP_RULES.md`.

## Milestone 26 invariant

Goal eligibility is a deterministic projection of each NPC's own canonical knowledge:

```text
NPCGoal.required_fact_ids
+ acting NPC facts_known
→ planner filters dormant goals
→ deterministic priority / route / intent
→ resolver repeats prerequisite gate
→ ordinary events
→ reducer backstop before NPCGoalCompleted
→ persistence / replay
```

Empty prerequisite sets preserve older worlds. Objective truth or another observer's knowledge cannot activate a goal. A fact learned during the off-screen social phase becomes actionable only in a later ordinary goal phase, preserving cadence ordering.

The fully green M26 implementation head `cb62a3445288a4defbc7f6e2a861f200916bdfdb` passed strict mypy across **47 source files**, **164 pytest tests**, and the seeded 1,000-turn gate with 2,274 events and `failures=[]`. Detailed evidence is in `docs/NPC_REACTIVE_GOALS.md`.

## Milestone 27 invariant

NPC item acquisition extends the existing custody authority rather than creating a second inventory subsystem:

```text
knowledge-gated acquire_item goal
+ NPC own item-location belief / known routes / local visibility
→ deterministic planner
→ movement / stale local search / NPCAcquireIntent
→ deterministic resolver
→ existing ItemAcquired
→ NPCItemLocationObserved(present=False)
→ NPCGoalCompleted(method="acquired_item")
→ validation / persistence / replay
```

The planner never receives authoritative remote item location. Generic `ItemAcquired` validation requires an existing alive/conscious actor, a local unowned portable item, and matching origin. Goal completion is valid only when canonical owner and inventory agree. The older investigate-item resolver contract remains backwards-compatible, and acquisition-specific rejection reasons do not overwrite it.

The fully green M27 implementation head `2e67bb2b132c6a67fb3d56b67f866dd3df308312` passed strict mypy across **47 source files**, **175 pytest tests**, and the seeded 1,000-turn gate with 1,058 submissions / 1,000 accepted / 58 rejected / **2,274 events** / final clock 4,361 and `failures=[]`. Detailed evidence is in `docs/NPC_ITEM_ACQUISITION.md`.

## Milestone 28 invariant

NPC delivery is a replayable owner-to-owner custody transition coupled to a knowledge-scoped rendezvous goal rather than remote receiver tracking:

```text
knowledge-gated deliver_item goal
+ source canonical custody
+ configured receiver + rendezvous location
+ source-owned mapped topology
→ deterministic planner routes only to rendezvous
→ receiver must become locally visible / co-located
→ NPCDeliverIntent
→ deterministic resolver
→ NPCItemDelivered(source, receiver, item, goal)
→ generic event validation
→ atomic canonical custody transfer
→ NPCGoalCompleted(method="delivered_item")
→ persistence / replay
```

The planner does not receive the receiver's remote live location. Reaching the configured rendezvous while the receiver is absent produces no delivery intent; the source does not omnisciently chase the receiver. `NPCItemDelivered` carries exact source/receiver/item/goal provenance and mutates the existing canonical `Item.owner_id` plus source/receiver inventories atomically, without introducing another inventory store. The generic validator independently enforces co-location, configured rendezvous, active participants, source custody, receiver uniqueness, portability, and goal consistency. Goal completion is valid only after receiver custody is canonical and source custody is gone.

Item-location beliefs remain observer-specific and are not globally synchronized merely because custody changes. Focused regressions cover deterministic multi-hop Bunkhouse → Yard → Operations → Archive delivery, absent/wrong/remote/inactive receiver rejection, wrong-location/source-without-item/nonportable rejection, forged transfer and forged goal-completion rejection, knowledge prerequisites, stale-belief isolation, SQLite restart/replay, and off-screen simulation under the ordinary NPC budget.

The fully green M28 implementation head `7fbe17d0bfa79dadf3056634e17e5649e9801a32` passed standard wheel/package checks, browser-asset verification, Ruff, strict mypy across **47 source files**, **185 pytest tests**, and the seeded 1,000-accepted-turn evaluation plus JSON verifier. For seed `20260911`, the long-run gate produced 1,058 submissions, 1,000 accepted turns, 58 deterministic rejections, 2,274 events, 1,058 persisted turns, 1,000 episodes, and final canonical clock minute 4,361. Replay equality, state validity, monotonic clock/player knowledge/event log, item ownership, and unique event IDs all remained true with `failures=[]`. Detailed evidence is in `docs/NPC_ITEM_DELIVERY.md`.

## Milestone 29 invariant

Player-to-NPC handoff extends the same canonical custody model through the player action surface:

```text
player-visible inventory + local active NPC names
→ deterministic or structured GiveAction(item, receiver)
→ deterministic resolver checks custody / portability / local receiver
→ PlayerItemGiven(source_player_id, receiver_npc_id, item_id)
→ reducer rechecks canonical participants and custody
→ shared owner-to-owner transfer helper
→ optional NPCGoalCompleted(method="acquired_item")
→ TimeAdvanced(1)
→ narration / persistence / replay
```

The provider-visible interaction surface is unchanged; `give` consumes only inventory and co-located active NPC names that were already available to the parser. The player resolver never reads or exposes an NPC's private goal identifiers in observations. A matching receiver-side acquisition goal can complete only after the canonical handoff event and only when its existing fact prerequisites are already known to that NPC.

`PlayerItemGiven` records exact player, receiver, and item provenance. The reducer independently verifies the canonical player, NPC receiver, liveness/consciousness, co-location, portability, source ownership/inventory, and duplicate receiver custody before delegating to the same `_transfer_owned_item()` helper used by `NPCItemDelivered`. Invalid raw actions emit no custody event; forged invalid typed events fail closed before successful mutation.

The fully green M29 implementation head `b50dfccfb9d0111f090f46718b15ad52df2d1e7c` passed standard wheel/package checks, browser-asset verification, Ruff, strict mypy across **47 source files**, **192 pytest tests**, and the seeded 1,000-accepted-turn evaluation plus JSON verifier. Focused coverage proves quoted multi-word deterministic parsing, structured-provider give JSON without hidden NPC state, non-owned/remote/inactive/nonportable rejection, acquisition-goal turn-in, forged remote typed-event rejection, SQLite persistence/replay, and FastAPI/browser raw-text parity.

For seed `20260911`, the long-run gate produced 1,058 submissions, 1,000 accepted turns, 58 deterministic rejections, **2,274 events**, 1,058 persisted turns, 1,000 episodes, and final canonical clock minute 4,361. Replay equality, state validity, monotonic clock/player knowledge/event log, item ownership, and unique event IDs all remained true with `failures=[]`. Detailed evidence is in `docs/PLAYER_ITEM_HANDOFF.md`.

## Promotion gate for Milestone 30

Milestone 29 completes bidirectional player/NPC custody movement and acquisition-goal turn-in, but a successful handoff has no generic world-pack consequence layer beyond custody and goal completion. The next coherent slice should make item turn-in rewards declarative rather than adding quest names or item ids to the resolver:

```text
validated PlayerItemGiven / matching turn-in context
+ canonical world-pack turn-in rule
→ deterministic rule match / priority / one-shot gate
→ existing typed relationship/fact consequence authority
→ ordinary validation / reduction
→ canonical applied-rule provenance
→ narration / persistence / replay
```

Rules must match canonical participants/item and optional goal/fact prerequisites without exposing NPC-private planning state to the player or provider. Repeated delivery must not farm one-shot rewards. Consequences should reuse existing `RelationshipChanged`, fact discovery/learning, or other established event authority rather than mutating state directly. Unmatched/invalid handoffs must produce no reward, and provider/narration failure must preserve the existing zero-partial-commit guarantee. CLI/API/browser execution, persistence/replay, and the real 1,000-turn continuity gate must remain green.


## Milestone 30 invariant

Item turn-in consequences are canonical world-pack policy rather than resolver-specific quest branches. Validated player-to-NPC handoff context is matched against deterministic one-shot rules, and consequences reuse existing fact/relationship event authority. Applied-rule provenance is persisted so repeated handoffs cannot farm rewards. Unmatched or invalid handoffs produce no reward, and provider failure preserves zero-partial-commit semantics. Detailed evidence remains in `docs/ITEM_TURN_IN_CONSEQUENCES.md`.

## Milestone 31 invariant

Player objectives are derived from canonical state, not narration:

```text
player facts / custody / applied turn-in provenance / completed objectives
→ deterministic PlayerObjectivePolicy fixed-point
→ PlayerObjectiveActivated / PlayerObjectiveCompleted
→ generic validation
→ reducer-owned lifecycle state
→ player-visible active/completed projection
→ persistence / replay
```

Pending objective definitions and prerequisite ids remain hidden from player-facing transports. Dependency graphs must be acyclic, forged lifecycle events fail closed, and provider failure before commit leaves objective progression unpersisted.

## Milestone 32 invariant

Objective deadlines extend the same lifecycle authority instead of introducing a timer-side mutation path:

```text
accepted action advances canonical world time
→ objective activation/completion fixed-point
→ earned completion takes precedence
→ otherwise due objective emits PlayerObjectiveFailed
→ generic event validation
→ reducer-owned active/completed/failed state
→ CLI/API/browser projection
→ atomic persistence / replay
```

Deadlines are absolute canonical world minutes. Failure may terminate either an active objective or a still-pending objective whose activation prerequisites were never met by its deadline. If an objective becomes activation-ready because another objective completes in the same fixed-point, it receives another activation/completion pass before failure is considered. Active, completed, and failed sets are mutually disjoint and transition-state validation requires exact lifecycle-event provenance.

Provider failure remains before persistence, so deadline-triggered activation/failure events, turns, and state remain uncommitted on narration failure. Pending objective definitions and prerequisites are still hidden; only active/completed/failed public objective metadata is projected.

## Promotion gate for Milestone 33

Milestone 32 makes objective lifecycle truth replayable, including terminal failure, but objective outcomes are still mostly observational: completion/failure changes objective state without a generic cross-world consequence layer.

The next coherent slice should make objective outcomes capable of triggering declarative, bounded consequences without adding quest-specific branches:

```text
validated PlayerObjectiveCompleted / PlayerObjectiveFailed
+ canonical objective-outcome rule
→ deterministic priority / one-shot provenance
→ existing typed fact / relationship / scheduled-world consequence authority
→ ordinary validation / reduction
→ atomic persistence / replay
```

Outcome rules must not mutate canonical state directly. They should reuse existing typed event authorities, remain deterministic under replay, reject forged provenance, preserve hidden objective prerequisites, and retain provider-failure zero-commit semantics. Completion/failure consequences must have explicit ordering and bounded fan-out rather than recursively creating an unbounded rule engine.


## Milestone 33 invariant

Objective completion/failure consequences are declarative world policy, not quest-specific resolver branches:

```text
validated PlayerObjectiveCompleted / PlayerObjectiveFailed
→ highest-priority matching ObjectiveOutcomeConsequenceRule
→ optional ordinary FactDiscovered
→ ordinary RelationshipChanged(rule_id=...)
→ reducer revalidates terminal outcome / priority / participants / delta
→ canonical one-shot applied-rule provenance
→ player inference
→ objective progression reconverges in the same turn
→ one atomic commit / replay
```

Rule ids are globally non-overlapping across dialogue, item-turn-in, and objective-outcome relationship policies, so reducer routing is explicit rather than heuristic. A given objective + terminal outcome may be consumed only once: once the selected rule is applied, lower-priority sibling rules are no longer eligible.

Optional reward facts still pass the existing discovery authority and can trigger ordinary player inference. The engine then reruns objective progression in a bounded fixed-point, so a reward fact may activate or complete downstream objectives in the same canonical turn without recursive unbounded rule execution.

Focused regressions prove completion and failure outcomes, deterministic priority, lower-priority anti-forgery, pre-terminal forged consequence rejection, fact/relationship ordering, same-turn downstream objective convergence, SQLite persistence/replay equality, invalid world-data rejection, and provider-failure zero-commit behavior. The fully green implementation head `a063b598a893265857c45d2db97dfe7c6846ae15` passed wheel/browser packaging, Ruff, strict mypy, full pytest, the seeded 1,000-accepted-turn consistency evaluation and verifier, and the autonomy integration evaluation and verifier.

## Promotion gate for Milestone 34

Milestone 33 lets objective outcomes change facts and relationships immediately, but it deliberately does not create or mutate the future environmental event queue. The next coherent cross-subsystem slice should connect objective outcomes to the already established scheduled-world authority rather than embedding direct location-condition mutation into the consequence policy:

```text
validated objective terminal outcome
+ canonical scheduled-world consequence rule
→ typed event queues a future location-condition activation
→ existing deterministic world-event scheduler
→ ScheduledLocationConditionApplied at due canonical minute
→ existing expiry / traversal / route rules
→ persistence / replay
```

The queueing transition must be typed and independently validated. It must reject duplicate schedule ids, missing locations, invalid route targets, past-due schedules, and forged objective provenance. Objective policy must never directly activate or remove environmental conditions. Queue fan-out must remain bounded, scheduling order deterministic, pending schedules hidden from player-facing state, and provider failure must preserve zero-partial-commit semantics.


## Milestone 34 invariant

Objective outcomes may schedule future environmental changes, but they still do not directly mutate active world conditions:

```text
validated PlayerObjectiveCompleted / PlayerObjectiveFailed
→ highest-priority ObjectiveOutcomeScheduledConditionRule
→ ScheduledLocationConditionQueued
→ validated canonical pending ScheduledLocationCondition
→ existing DeterministicWorldEventScheduler at due world minute
→ existing ScheduledLocationConditionApplied
→ existing expiry / traversal / route authorities
→ one replayable event log
```

The queue transition carries exact rule, objective, outcome, schedule id, and due-minute provenance. Generic event validation rechecks terminal objective truth, deterministic priority, future due time, schedule-id uniqueness, target location, route-locality, active/pending target conflicts, and one-shot outcome consumption. Transition-state validation independently requires queue-event provenance for newly added pending schedules, rejects in-place mutation of existing pending schedules, and reconstructs the applied schedule-rule set from typed queue events.

The objective consequence layer never writes `Location.active_conditions`. It only appends a validated future `ScheduledLocationCondition`; the existing world-event scheduler remains the sole authority that activates it, and the existing expiry path remains the sole authority that later removes it. Pending schedules remain absent from the player-visible projection until activation.

Focused integration coverage proves completion- and failure-triggered queueing, deterministic priority and anti-forgery, wrong due/duplicate-id rejection, direct pending-queue mutation rejection, hidden pending state, provider-failure zero-commit behavior, SQLite replay equality, and the complete objective → queue → scheduled activation → expiry path. The fully green implementation head `c397483943d05b871cb9bac27a413b85312e87c3` passed wheel/browser packaging, Ruff, strict mypy, full pytest, the seeded 1,000-accepted-turn consistency evaluation and verifier, and the autonomy integration evaluation and verifier.

## Promotion gate for Milestone 35

Milestones 31–34 complete a coherent objective lifecycle stack from activation through terminal outcomes and delayed environmental consequences. Further objective prerequisite/reward variants would now be lower-value expansion. The next architectural frontier should move to the underdeveloped combat subsystem.

Canonical characters already own health, stamina, alive/conscious state, and a `CharacterDamaged` event exists, but there is no executable player combat action and the damage event does not encode attacker provenance. Milestone 35 should establish a deterministic combat authority rather than treating free-form prose as damage truth:

```text
player-visible local target
→ typed AttackAction
→ deterministic resolver checks target / co-location / liveness / stamina
→ provenance-rich validated damage event
→ reducer-owned health / alive / conscious transition
→ TimeAdvanced / narration
→ persistence / replay
```

The first combat slice should stay deliberately bounded: deterministic unarmed player attacks, local conscious NPC targets, explicit attacker provenance, fixed or data-driven bounded damage, ordinary transaction/provider-failure semantics, parser/API/browser parity, and forged/remote/dead-target rejection. It should reuse canonical health rather than introducing a second combat-state store.
