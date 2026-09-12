# Portable Session Archives

Portable session archives move a persisted campaign between SQLite databases without treating a cached `current_state` blob as authority.

## CLI

Export an existing session:

```bash
emergent-rpg export-session SESSION_ID --db source.db --output campaign.json
```

If `SESSION_ID` is omitted, the latest session is exported. Existing output files are refused unless `--overwrite` is supplied.

Import into another database:

```bash
emergent-rpg import-session campaign.json --db restored.db
```

The import receives a fresh session id. `--name` may override the imported display name, while the original `world_pack` identity is preserved.

## Archive contents

Format version 1 stores:

- source session id, display name, world-pack id, and source creation timestamp;
- the canonical initial `WorldState`;
- ordered typed domain events with original event ids and timestamps;
- turn history;
- episodic memory records; and
- a SHA-256 digest of the canonical replayed current state.

A current-state payload is intentionally not trusted as a second authority. The imported current state is rebuilt by replaying the typed event log from the initial snapshot.

## Validation boundary

Export refuses a source session when its persisted current state differs from `replay(initial_state, events)` or fails canonical validation.

Import validates the archive before constructing the target `SQLiteStore`:

```text
UTF-8 JSON
→ strict versioned archive schema
→ initial-state validation
→ ordered unique event ids
→ per-event canonical precondition validation
→ event reduction + transition-state validation
→ final-state validation
→ replayed-state SHA-256 check
→ turn / episode reference-range validation
→ one target SQLite transaction
```

This prevents corrupted archives from leaving a target database file or partially imported session. Once validation passes, the target database transaction writes session metadata, the initial/replayed current states, events, turns, and episodes together. Database uniqueness failures roll back the entire import.

Turns are rebound to the fresh imported session id. Event ids and episode ids remain unchanged so their persisted provenance is preserved. Because those ids are globally unique in the current SQLite schema, importing the same non-empty archive twice into one database is rejected atomically rather than silently renumbering provenance.

## Relationship to world packs

A world pack is a **new-game template** and must start at turn zero. A session archive is a **played-game transport** and includes the event/history/memory record needed to resume exactly.

Neither format executes external code. After import, all new gameplay continues through the ordinary `GameEngine` parser/resolver, typed events, validators, simulation, provider boundaries, SQLite persistence, and replay paths.
