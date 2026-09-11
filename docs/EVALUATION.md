# Long-run consistency evaluation

Milestone 12 adds a deterministic evaluation harness for continuity and replay correctness over long-running sessions. It is an executable correctness workload, not a performance benchmark and not a model-quality score.

## Run

```bash
emergent-rpg-eval \
  --db emergent-rpg-eval.db \
  --turns 1000 \
  --seed 20260911 \
  --checkpoint-interval 100 \
  --output evaluation.json
```

The command prints the same machine-readable JSON report to stdout and exits non-zero when any tracked invariant fails. It refuses to overwrite an existing evaluation database.

`--turns` means **canonical accepted turns**, not raw action submissions. Deliberately rejected adversarial actions are submitted in addition to that target and are reported separately.

## Seeded mixed-action scenario

`seeded-mixed-actions-v1` uses a local deterministic `random.Random(seed)` and the ordinary scripted `GameEngine`. No external model service participates.

The workload mixes:

- valid moves over the current location graph;
- room inspections;
- acquisition of currently visible items;
- waits of 1, 2, 5, or 10 world-clock minutes;
- deterministic impossible-move submissions;
- deterministic missing-item submissions.

The invalid submissions exercise rejection behavior alongside normal state growth. A rejected action must leave canonical state unchanged while still being represented in persisted turn history.

## Checkpoint invariants

At each configured accepted-turn checkpoint the harness reloads persisted data and checks:

- `validate_state()` remains valid;
- replay from initial state + append-only events exactly equals the persisted projection;
- the event log never shrinks;
- all event IDs remain unique;
- each item has a consistent single location/owner projection;
- world-clock absolute minutes never move backward;
- player-known facts never disappear.

The final report also checks:

- the requested accepted-turn target was actually reached;
- persisted turn count equals total submitted actions, including deterministic rejections;
- persisted episode count equals accepted canonical turns;
- final replay equality and state validity still hold.

## Report fields

The JSON report includes scenario/seed/turn targets, submitted and rejected counts, event/turn/episode totals, checkpoint turns, action-kind counts, final canonical clock position, each continuity invariant, a bounded list of failure codes, and a final `passed` boolean.

No wall-clock duration, throughput, token cost, or provider-quality metric is part of the evaluation report. Ordinary GitHub Actions timing is therefore not presented as benchmark evidence.

## CI evidence

The first full Milestone 12 candidate (`seed=20260911`) completed the real 1,000-accepted-turn gate with:

```text
submitted_actions: 1058
accepted_turns: 1000
rejected_actions: 58
event_count: 2268
persisted_turn_count: 1058
episode_count: 1000
checkpoint_turns: 100, 200, ..., 1000
action_counts: move=517, inspect=238, take=28, wait=275
```

All tracked correctness flags were true:

```text
replay_equal
state_valid
clock_monotonic
player_knowledge_monotonic
event_log_monotonic
item_ownership_valid
unique_event_ids
```

The report contained `failures: []` and `passed: true`. These numbers are evidence for that deterministic scenario and seed; they are not a claim about performance or every possible future world pack.

## Authority boundary

The evaluator is a client of the normal engine path:

```text
seeded scenario policy
→ ordinary typed PlayerAction
→ GameEngine.execute_action()
→ resolver / events / validation / provider / simulation / persistence
→ periodic independent reload + replay verification
→ JSON correctness report
```

The evaluation subsystem does not mutate canonical state directly, bypass validators, write synthetic success results, or modify expected state to hide a mismatch.
