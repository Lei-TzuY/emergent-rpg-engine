# Declarative World Packs

A world pack is a UTF-8 JSON document that can seed a new persisted session without importing or executing world-specific Python code.

## Format

The top-level schema is versioned and strict:

```json
{
  "format_version": 1,
  "id": "my-world",
  "name": "My World",
  "initial_state": { "...": "WorldState JSON" }
}
```

- `format_version` must currently be `1`.
- `id` is the stable persisted world-pack identity and uses lowercase letters, digits, `.`, `_`, and `-`.
- `name` is the default session display name.
- `initial_state` is validated through the canonical `WorldState` model and must start at turn `0`.
- Unknown top-level fields are rejected instead of silently ignored.

After schema parsing, the loader runs the same `validate_state()` continuity validation used by the engine. Missing entities, impossible ownership, invalid rule references, broken mystery graphs, invalid scheduled-world state, and other canonical-state errors therefore fail before session persistence.

## CLI

Create a session from a pack with:

```bash
emergent-rpg new --world ./my-world.json --db my-world.db
```

The pack name becomes the session name by default. `--name` changes only the session display name; the persisted `GameSession.world_pack` remains the pack `id`:

```bash
emergent-rpg new --world ./my-world.json --name "Campaign One"
```

Running `emergent-rpg new` without `--world` retains the built-in Ashfall Relay behavior and `ashfall-relay` pack identity.

## Authority boundary

World-pack loading is bootstrap, not a second runtime mutation path:

```text
UTF-8 JSON
→ strict WorldPack envelope
→ canonical WorldState parsing
→ validate_state()
→ fresh GameSession metadata
→ SQLiteStore.create_session(initial snapshot)
→ ordinary GameEngine actions/events/validation/replay thereafter
```

No code, plugin, provider call, or arbitrary import is executed from a pack. Validation completes before the SQLite store is created by the CLI, so malformed or invalid packs cannot leave a partially created game session.

The stored initial snapshot is deep-copied from the parsed pack. The ordinary event log remains empty at creation, and replay from the initial snapshot plus that event log must equal the persisted current state. Subsequent play uses exactly the same deterministic resolver, typed-event, validation, simulation, provider, persistence, and replay paths as the built-in world.

## Compatibility

The envelope version and canonical state schema are intentionally separate. New backwards-compatible `WorldState` fields with defaults can be consumed by existing version-1 packs without a SQLite migration. A future incompatible pack-envelope change must use a new `format_version` rather than guessing how to reinterpret old files.
