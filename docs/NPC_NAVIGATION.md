# Knowledge-scoped NPC navigation

Milestone 17 extends autonomous `reach_location` goals from one-hop movement to deterministic multi-hop navigation without giving the planner omniscient world access.

## Canonical navigation knowledge

`NPCKnowledge.mapped_locations` is canonical state. It identifies locations whose static outgoing topology the NPC knows. The planner is never handed `WorldState.locations` directly.

`build_npc_planning_context()` constructs a bounded navigation graph:

```text
NPC.knowledge.mapped_locations
→ static exits for mapped locations only
+ currently observable local exits
→ current local exits filtered through EnvironmentalRules
→ NPCPlanningContext.known_routes
```

The current location is special because its exits are directly observable. Its adjacency is replaced with the currently accessible exits, so an active environmental closure immediately changes the next-hop decision. Remote mapped locations retain only static known topology; an active remote hazard is not projected into the NPC context until the NPC reaches that location.

This preserves the epistemic boundary: map knowledge may be incomplete or stale, but the planner never obtains hidden current-world information merely because that information exists in canonical state.

## Deterministic bounded path selection

`deterministic_next_hop()` performs breadth-first search over the already scoped `known_routes` graph. It is bounded to eight hops and visits neighbors in lexical order, producing a stable result when multiple equal-length paths exist.

The result is only the first hop. There is no multi-location teleport and no route-level mutation event.

```text
bounded known topology
→ deterministic shortest path
→ one NPCMoveIntent for the first hop
→ resolver revalidation
→ ordinary NPCMoved event
→ next autonomous phase replans from new canonical state
```

If no bounded path exists in the NPC's known graph, the planner emits no move intent for that goal.

## Execution authority

The planner still has no mutation authority. `DeterministicNPCResolver` independently checks:

1. the NPC exists and can act;
2. the referenced goal is an unfinished `reach_location` goal;
3. the proposed destination is an actual local exit;
4. current environmental route policy permits that exit;
5. recomputing the deterministic path from the NPC's own scoped context yields exactly that proposed next hop.

An accessible local detour that is not the deterministic known-route next hop is therefore rejected. A route blocked by Milestone 16 is rejected before route-choice validation, preserving the environmental closure contract.

Intermediate hops emit only `NPCMoved`. `NPCGoalCompleted(method="reached_location")` is emitted only when a legal step reaches the final target. Existing event validation, reducer, SQLite persistence, replay, simulation budgets, and atomic phase commits are reused unchanged.

## Rerouting without omniscience

A closure on a remote mapped location is intentionally not known in advance. The NPC may choose a route based on its static map, reach the affected location, observe that the next exit is currently closed, and then deterministically replan using the locally filtered adjacency.

This distinction is important:

- known topology answers "where do I believe routes exist?";
- current local observation answers "which of those exits can I use right now?";
- hidden remote world state never becomes planner input.

## Verification evidence

The first fully green Milestone 17 implementation head passed:

- wheel build and packaged browser-asset verification;
- Ruff;
- strict mypy across 45 source files;
- **110 pytest tests**;
- the seeded 1,000-accepted-turn consistency evaluation and JSON verifier.

Focused integration coverage proves deterministic equal-length tie-breaking, the eight-hop bound, refusal to route through unmapped global topology, intermediate movement without premature goal completion, forged-detour rejection, local rerouting after a previously remote closure becomes observable, and three persisted/replayed autonomous phases completing `bunkhouse → yard → operations → archive`.

For seed `20260911`, the long-run gate completed 1,058 submitted actions, 1,000 accepted turns, 58 deterministic rejections, 2,270 events, 1,058 persisted turns, 1,000 episodes, and final canonical clock minute 4,361. Replay equality, state validity, monotonic clock/knowledge/event log, item ownership, and unique event IDs all remained true with `failures=[]`.

These figures are deterministic correctness evidence, not performance measurements.

## Promotion gate for Milestone 18

`mapped_locations` is currently canonical but mostly configured ahead of time. The planner can observe current exits transiently, yet merely visiting a location does not create replayable map knowledge. After leaving, an NPC can therefore fail to retain topology it just observed unless that location was already preconfigured as mapped.

The next architectural slice should make route discovery itself canonical and replayable. A typed NPC mapping/observation event should be the only normal way to expand `mapped_locations`; validation must require the NPC to be alive/conscious and physically present at the mapped location, and the reducer must update only that NPC's knowledge. Arrival/current-location observation should produce the event through the existing autonomous simulation path, with no player-knowledge leakage and no direct dictionary/set mutation outside the reducer.

Acceptance evidence should cover initial-location observation, mapping after movement, persistence/replay equality, rejection of forged remote mapping, no cross-NPC knowledge transfer, idempotent already-known locations, interaction with off-screen simulation, and the existing 1,000-turn continuity gate.
