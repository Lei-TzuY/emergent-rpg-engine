# Environmental Route Access

Milestone 16 turns active environmental conditions into deterministic route-access policy without mutating canonical location topology.

## Canonical rule data

A `LocationCondition` may carry a `RouteEffect`:

```text
LocationCondition
└── route.blocked_destination_ids
```

The payload is canonical data. It names destination ids that are already local exits of the condition's location. State validation rejects route effects that reference non-local destinations, preventing malformed world packs from creating impossible closure rules.

The demo Ashfall Yard `ash_squall` condition blocks the outbound Yard → Glass Ridge route while it is active. The condition still carries its existing traversal-cost modifier; other Yard exits remain usable and pay the ordinary environmental traversal cost.

## Derived route policy

`EnvironmentalRules` is the single deterministic projection layer:

```text
Location.exits + active LocationCondition.route payloads
→ EnvironmentalRules.route_access()
→ accessible exits / blocked exits
```

It never deletes or rewrites `Location.exits`. Activation and expiry from Milestone 15 remain the only authority that changes which conditions are active. When the squall expires at Day 1 08:40, the Ridge route reappears automatically because the blocking condition is no longer active; no separate unblock event exists.

## Movement authority

Player movement is guarded twice:

```text
PlayerAction(move)
→ DeterministicResolver route-access check
→ PlayerMoved proposal only when allowed
→ event precondition validation checks route access again
→ reducer / persistence
```

A blocked move is rejected without movement or time events. A forged `PlayerMoved` event cannot bypass the resolver because event validation independently checks adjacency and active route policy.

NPC movement uses the same rule layer at two boundaries. `build_npc_planning_context()` receives only currently accessible local exits, so the planner does not propose a known-blocked route. `DeterministicNPCResolver` and `NPCMoved` validation independently reject forged blocked intents/events.

No resolver or planner branch compares against `ash_squall` or another content name. A synthetic unrelated route condition regression proves the rule is payload-driven.

## Player-visible surfaces

Current route access is projected consistently across the engine surfaces:

- the action-parser visible surface lists accessible exits separately from current blocked routes;
- the Web API exposes `exits` and bounded `blocked_exits` records with blocker names;
- the browser renders a dedicated blocked-routes section;
- the CLI status uses the same `EnvironmentalRules` projection.

Future schedule ids and due times remain hidden. Before 08:20, the Ridge route appears normally and the future squall is not exposed. Between 08:20 and 08:40, Ridge is shown as blocked by the active Ash squall. After expiry, it becomes available again through ordinary replayed lifecycle state.

## Verification evidence

The first fully green Milestone 16 implementation head passed:

- wheel build and packaged browser-asset verification;
- Ruff;
- strict mypy across 44 source files;
- 104 pytest tests;
- the seeded 1,000-accepted-turn consistency evaluation and JSON verifier.

For seed `20260911`, the long-run scenario completed 1,058 submissions, 1,000 accepted turns, 58 deterministic rejections, 2,270 events, 1,000 episodes, and final canonical clock minute 4,361. Replay equality, state validity, monotonic clock/knowledge/event log, item ownership, and event-id uniqueness all remained true with `failures=[]`.

These figures are deterministic correctness evidence for this scenario, not a performance benchmark.

## Remaining boundary

`reach_location` NPC goals still only generate movement when the target is a directly adjacent accessible exit. The next architectural frontier is knowledge-scoped deterministic multi-hop navigation: NPCs should be able to follow and re-plan routes over topology they canonically know, without giving the planner omniscient access to the full `WorldState` or bypassing the route-closure checks established here.
