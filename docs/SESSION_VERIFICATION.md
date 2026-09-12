# Persisted Session Integrity Verification

`emergent-rpg-verify` is a read-only integrity check for an existing SQLite session. It is intended to answer whether persisted canonical data is internally consistent; it never repairs or rewrites a session.

## Usage

```bash
emergent-rpg-verify SESSION_ID --db emergent-rpg.db
```

When `SESSION_ID` is omitted, the latest persisted session is selected. The database path must already exist; verification deliberately refuses a missing path rather than constructing an empty SQLite database as a side effect.

The command writes a JSON `SessionVerificationReport` and exits with:

- `0` when all verification checks pass;
- `1` when persisted data can be read but fails integrity verification;
- `2` when the requested database/session cannot be selected.

## Verification authority

Verification does not introduce another state authority:

```text
persisted initial canonical state + typed event log
→ deterministic replay
→ compare with persisted current state
→ validate current canonical state
→ reuse portable-archive history/range/digest consistency checks
→ structured read-only report
```

The report contains session/world-pack identity, event/turn/episode counts, replay equality, current-state validity, archive/history consistency, the current-state SHA-256 digest when available, explicit failures, and a final `passed` flag.

The verifier intentionally reuses the same replay, `validate_state()`, and portable-session-archive validation path already used by export/import. A mismatch is reported; no event, state snapshot, turn, episode, or schema row is repaired or deleted.

## Failure coverage

Focused regressions prove that verification:

- passes a healthy persisted session without changing state, events, turns, or episodes;
- detects a directly tampered `current_state_json` through replay mismatch;
- detects turn-history corruption even when canonical state and replay still match;
- produces machine-readable JSON from the standalone executable;
- refuses a nonexistent database without creating it.

## Verification evidence

The first complete implementation candidate passed wheel/package and browser-asset verification, Ruff, strict mypy across **53 source files**, and **219 pytest tests**.

The seeded 1,000-accepted-turn consistency gate produced 1,058 submitted actions, 1,000 accepted turns, 58 deterministic rejections, 2,274 events, 1,058 persisted turns, 1,000 episodes, and final canonical clock minute 4,361. Replay equality, state validity, clock/player-knowledge/event-log monotonicity, item ownership, and event-id uniqueness were all true with `failures=[]`.

The 20-round `autonomy-custody-social-v1` integration gate produced 63 events and 27 persisted turns. Replay equality, state validity, unique event ids, item ownership, private-fact isolation, and all ten subsystem milestone checks were true with `failures=[]`.

These are deterministic correctness results, not performance or durability benchmark claims.

## Current boundary

This milestone verifies logical persistence integrity under the current schema. It does not yet provide a database schema-version/migration protocol, automatic repair, filesystem-level checksums, or crash-recovery guarantees beyond SQLite's existing transaction semantics.
