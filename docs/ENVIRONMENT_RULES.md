# Environmental Rules

Milestone 14 turns canonical environmental conditions into deterministic gameplay mechanics without creating a second mutation authority.

## Canonical effect data

A `LocationCondition` may carry an optional `TraversalEffect`:

```text
LocationCondition
└── traversal.extra_minutes
```

The effect payload is canonical state. The resolver never branches on a condition code such as `ash_squall`; named demo content is only data.

## Traversal authority

Movement follows this path:

```text
active conditions at current location
→ EnvironmentalRules.traversal_cost()
→ deterministic base + additive extra minutes
→ DeterministicResolver
→ PlayerMoved + TimeAdvanced
→ ordinary validation / persistence / replay
```

The baseline cost remains five minutes. Conditions with positive traversal modifiers are sorted by canonical condition code before their codes/names are reported, while their numeric modifiers are added deterministically. Conditions without traversal effects do not change movement.

`EnvironmentalRules` returns derived policy data only. It does not mutate `WorldState`, create database writes, or bypass the existing event pipeline.

## Demo behavior

The scheduled Day 1 08:20 Ashfall Yard `ash_squall` condition now carries `TraversalEffect(extra_minutes=5)`. Before activation, movement from the yard still costs five canonical minutes. After activation, movement from the yard costs ten canonical minutes.

A regression also installs an unrelated synthetic `mud_bank` condition and proves its payload changes movement without any condition-name branch in the resolver. Multiple active modifiers are additive.

## Player-visible explanation

The API projection exposes `traversal_extra_minutes` only for conditions already active at the player's current location. The browser renders the extra travel cost alongside the visible condition. Future scheduled-condition metadata remains hidden under the Milestone 13 boundary.

Narration may describe the deterministic result but does not decide the cost. Provider failure still occurs before persistence, so a failed narration request cannot commit a hazard-modified move or its time advance.

## Verification evidence

The first fully green Milestone 14 candidate passed:

- wheel build and packaged browser-asset verification;
- Ruff;
- strict mypy across 44 source files;
- 90 pytest tests;
- the seeded 1,000-accepted-turn consistency evaluation and JSON verifier.

For seed `20260911`, the long-run scenario completed 1,058 submissions, 1,000 accepted turns, 58 deterministic rejections, 2,414 events, and 1,000 episodes. The final canonical clock reached absolute minute 5,086 because the activated traversal hazard legitimately increased movement time. Replay equality, state validity, monotonic clock/knowledge/event log, item ownership, and event-id uniqueness all remained true with `failures=[]`.

These numbers are correctness evidence for this deterministic scenario, not a performance benchmark.

## Remaining boundary

Active environmental conditions currently have no canonical expiry lifecycle. Once the demo ash squall activates, it remains active indefinitely. The next architectural phase should add replayable condition expiration/removal driven by canonical world time, replacing the current monotonic-only condition rule with typed, validator-authorized lifecycle transitions rather than arbitrary deletion.
