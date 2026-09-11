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
- LLM-facing interfaces are replaceable; the deterministic demo and all tests require no API key or network.
- Memory retrieval uses recent turns + ranked deterministic episodes + canonical facts, not the full transcript.

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

## Demo world: Ashfall Relay

Ashfall Relay is an original frontier mystery with six locations, five NPCs, two factions, eight items, and a chain of clues around a suspicious communications blackout. Different NPCs know different facts. Evidence can remain untouched for hundreds of turns and still be recovered because it lives in canonical state, not narration context.

## Development

```bash
ruff check .
mypy src/emergent_rpg
pytest
```

CI runs all three checks on Python 3.12.

## Current limitations

This first vertical slice deliberately keeps the surface small. Freeform natural-language action parsing is only an interface/fallback; autonomous NPC planning, real LLM providers, vector retrieval, web APIs, web UI, richer combat/stat systems, and world simulation between turns are future work.

There is intentionally no `LICENSE` file yet: the repository did not state a license intent, so this implementation does not guess one on the owner's behalf.
