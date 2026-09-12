# Read-only whole-database audit

`emergent-rpg-db-check` inspects an existing engine SQLite database without creating, adopting, repairing, migrating, or otherwise mutating it.

```bash
emergent-rpg-db-check --db emergent-rpg.db
```

The command emits a machine-readable JSON report and exits with:

- `0` when the whole database passes the audit;
- `1` when the database exists but physical, schema, or logical verification fails;
- `2` when the audit cannot be started, such as when the requested database path does not exist.

## Audit authority boundary

```text
existing SQLite file only
→ open with SQLite URI mode=ro
→ PRAGMA quick_check
→ read-only schema compatibility probe
→ enumerate persisted session ids
→ existing verify_session() for every session
→ JSON report only
```

The audit never enters a gameplay mutation path and never creates domain events, turns, episodes, sessions, schema metadata, or backup files.

### Schema behavior

Normal `SQLiteStore` startup is allowed to create an empty engine database and to adopt the exact pre-version legacy application schema by writing the current `schema_metadata` marker. The database audit deliberately does neither.

Its `inspect_schema_compatible()` probe accepts an exact legacy application shape as compatible with the current schema version while returning `schema_marker_present=false`. The source remains byte-for-byte unchanged and `schema_metadata` remains absent. Empty, partial, malformed, older-version, future-version, or otherwise incompatible schemas fail closed instead of being repaired.

### Logical verification

After physical and schema checks succeed, the audit enumerates every persisted session and reuses the ordinary read-only `verify_session()` path. Each session must therefore pass:

- persisted-current-state equality with event replay;
- canonical state validation;
- portable session archive consistency;
- normal decoding of session, event, turn, episode, and world-state records.

One failing session makes the whole database report `passed=false`; healthy sessions are still listed in `verified_session_ids` so automation can identify the failure scope.

## Report

`DatabaseAuditReport` includes:

- database path;
- compatible schema version when available;
- whether an explicit schema marker was present;
- raw SQLite `quick_check` rows;
- total persisted session count;
- verified session ids;
- failure messages;
- source SHA-256 and byte size;
- final `passed` boolean.

The hash and size describe the inspected source. They are evidence/reporting fields, not cryptographic authenticity, tamper-proofing, or durability guarantees.

## Verification evidence

The first fully green implementation candidate passed package/browser-asset verification, Ruff, strict mypy across **58 source files**, **239 pytest tests**, the seeded 1,000-accepted-turn consistency evaluation, and the autonomy/custody/social integration evaluation.

For seed `20260911`, the long-run gate remained at 1,058 submissions / 1,000 accepted turns / 58 deterministic rejections / 2,274 events / final canonical clock minute 4,361, with replay equality and all tracked continuity invariants true and `failures=[]`.

The autonomy scenario remained green for 20 rounds with 63 events, 27 persisted turns, all 10 subsystem milestone checks true, and `failures=[]`.

Focused regressions prove byte-for-byte non-mutation for a healthy database, logical corruption, an exact legacy schema, and a future schema marker. They also prove that auditing an exact legacy database does not silently adopt `schema_metadata`, and that a missing path does not create a SQLite file.

These are correctness and integration results, not database throughput, crash-durability, or security benchmark claims.
