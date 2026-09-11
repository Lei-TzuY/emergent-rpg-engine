# Web API

Milestone 9 exposes a thin FastAPI service boundary over the existing `GameEngine`. The HTTP layer validates and serializes requests; it does not resolve actions, create domain events, reduce state, or commit SQLite transactions itself.

## Run the service

```bash
emergent-rpg-api --db emergent-rpg.db --host 127.0.0.1 --port 8000
```

The server accepts the same provider/parser modes as the CLI:

```bash
emergent-rpg-api --provider scripted --action-parser deterministic
emergent-rpg-api --provider ollama --action-parser ollama
emergent-rpg-api --provider openai-compatible --action-parser openai-compatible
```

Provider configuration still comes from the existing environment variables. Invalid provider configuration fails at server startup instead of creating a partially configured application.

## Endpoints

- `GET /health` — side-effect-free liveness check.
- `POST /sessions` — create a persisted Ashfall Relay session.
- `GET /sessions/{session_id}` — read the session plus a player-visible state projection.
- `GET /sessions/{session_id}/history?limit=N` — read bounded player-facing turn history.
- `POST /sessions/{session_id}/actions` — submit raw player text through `GameEngine.process_text()`.

FastAPI also exposes the generated OpenAPI document at `/openapi.json` and interactive documentation at `/docs` when the server is running.

## Authority boundary

```text
HTTP request
→ Pydantic request validation
→ existing ActionParser
→ GameEngine.process_text()
→ deterministic resolver
→ typed events / validators / reducer
→ provider narration
→ due world simulation
→ SQLite atomic commit
→ player-visible response projection
```

No HTTP handler has a reducer, event writer, or direct state mutation path. Accepted actions therefore use the same event log, replay, validation, mystery inference, NPC simulation, and provider-failure atomicity as the CLI.

## Player-visible state projection

The API deliberately does not serialize raw `WorldState`. Session/action responses include only the current player-facing surface:

- turn number and display time
- current location id/name
- local exits
- visible local items
- co-located living/conscious NPCs
- player inventory
- facts already present in `player_known_facts`

The projection omits global fact truth/source metadata, undiscovered propositions, NPC knowledge/beliefs, planning goals, relationships, inference rules, simulation internals, and unrelated world entities. A client therefore cannot obtain privileged canonical state merely by switching from the CLI to HTTP.

History responses also omit internal `involved_entities` and tag metadata. Automatic off-screen simulation does not create player history turns, so background NPC execution is not surfaced through this endpoint.

## Error and atomicity contract

- malformed request bodies are rejected by FastAPI/Pydantic with HTTP `422` before engine execution;
- unknown session ids return HTTP `404`;
- deterministic transition invariant failures return HTTP `409`;
- external provider request/response failures return HTTP `502`.

Provider failures still occur before `SQLiteStore.commit_turn()`. API integration tests verify that a failed narrative provider leaves canonical state, the append-only event log, and turn history unchanged.

## Offline verification

`tests/test_api.py` uses `fastapi.testclient.TestClient` and injected provider transport. CI does not start a network listener or contact an external model service. Tests cover session creation/readback, knowledge-safe state projection, action persistence + replay equality, bounded history, malformed/unknown requests, provider-failure atomicity, and the side-effect-free health endpoint.
