# emergent-rpg-engine

A deterministic, persistent foundation for long-running AI-driven text RPGs.

Most chatbot RPGs eventually lose continuity because the transcript is treated as the world: old facts fall out of context, inventory duplicates, NPCs learn secrets they never heard, and prose silently mutates reality. This project instead treats **canonical state + append-only events** as authoritative. Narrative text is a projection of accepted events, never the source of truth.

## Architecture

```text
Player Action
→ Action Parsing
→ Deterministic Resolution
→ Typed Events
→ Continuity Validation
→ Canonical State
→ Memory Retrieval
→ ScenePlan
→ Narrative Generation
→ Append-only Event Log
```

Key boundaries:

- Canonical world state owns location, time, inventory, health, facts, relationships, and NPC knowledge.
- NPC knowledge is separate from objective truth and from player knowledge.
- Every material change is a typed event that can be replayed.
- Narrative providers cannot mutate canonical state.
- Provider failure happens before the state/event transaction is committed.
- Memory retrieval uses recent turns + ranked deterministic episodes + canonical facts, not the full transcript.
- All tests remain offline; no API key or network is required for CI.

## Quick start

Requires Python 3.12+.

```bash
python -m venv .venv
# activate the environment
pip install -e ".[dev]"

emergent-rpg new
emergent-rpg play
```

Useful commands:

```bash
emergent-rpg status
emergent-rpg history
emergent-rpg play
```

Inside the demo:

```text
> inspect room
> take brass key
> talk Lio Marr
> move operations
> inspect console
> talk Arden Vale
> wait 15
```

Sessions persist in `emergent-rpg.db` by default. Pass `--db PATH` to use another SQLite database.

## Real narrative provider

The default `scripted` provider is deterministic and offline. A real OpenAI-compatible Chat Completions endpoint can be selected without changing domain or engine code:

```bash
export EMERGENT_RPG_LLM_BASE_URL="http://127.0.0.1:11434/v1"
export EMERGENT_RPG_LLM_MODEL="your-model"
# Optional for endpoints that require authentication:
export EMERGENT_RPG_LLM_API_KEY="..."

emergent-rpg play --provider openai-compatible
```

Optional controls:

```text
EMERGENT_RPG_LLM_TIMEOUT       default 30 seconds
EMERGENT_RPG_LLM_TEMPERATURE   default 0.7
EMERGENT_RPG_LLM_MAX_TOKENS    default 500
```

Provider credentials are read from the environment rather than command-line flags. The provider receives a constrained `ScenePlan`, not mutable canonical state. Facts known only by an NPC are not automatically made available to player-facing narration.

If an external provider request fails or returns malformed output, the accepted candidate state is **not committed**. The player can retry without a half-applied event stream.

## Demo world: Ashfall Relay

Ashfall Relay is an original frontier mystery with six locations, five NPCs, two factions, eight items, and a chain of clues around a suspicious communications blackout. Different NPCs know different facts. Evidence can remain untouched for hundreds of turns and still be recovered because it lives in canonical state, not narration context.

## Development

```bash
ruff check .
mypy src/emergent_rpg
pytest
```

CI runs all three checks on Python 3.12. Provider tests inject an in-memory transport and never contact an external service.

## Current limitations

Freeform natural-language action parsing is still deterministic/fallback-only. Structured LLM action parsing, autonomous NPC planning, world simulation between turns, vector retrieval, web APIs, web UI, richer combat/stat systems, provider routing, and cost controls are future work.

The OpenAI-compatible provider currently targets the common `/chat/completions` JSON shape and intentionally supports text responses only. Live endpoint interoperability depends on the selected server/model and is not claimed by offline CI.

There is intentionally no `LICENSE` file yet: the repository did not state a license intent, so this implementation does not guess one on the owner's behalf.
