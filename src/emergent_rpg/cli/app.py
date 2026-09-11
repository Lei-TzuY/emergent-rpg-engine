from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from emergent_rpg.domain.models import NPC, WorldState
from emergent_rpg.engine.service import GameEngine
from emergent_rpg.persistence.db import SQLiteStore
from emergent_rpg.providers.errors import ProviderError
from emergent_rpg.providers.factory import (
    ActionParserName,
    NarrativeProviderName,
    build_action_parser,
    build_narrative_generator,
)

app = typer.Typer(help="Persistent canonical-state text-RPG engine demo.")
DEFAULT_DB = Path("emergent-rpg.db")
DB_OPTION = typer.Option("--db", help="SQLite database path.")
PROVIDER_OPTION = typer.Option(
    "--provider",
    help="Narrative provider: scripted or openai-compatible.",
)
ACTION_PARSER_OPTION = typer.Option(
    "--action-parser",
    help="Action parser: deterministic or openai-compatible.",
)


def _engine(
    db: Path,
    provider: NarrativeProviderName = NarrativeProviderName.SCRIPTED,
    action_parser: ActionParserName = ActionParserName.DETERMINISTIC,
) -> GameEngine:
    generator = build_narrative_generator(provider)
    parser = build_action_parser(action_parser)
    return GameEngine(SQLiteStore(db), generator=generator, parser=parser)


def _resolve_session(store: SQLiteStore, session_id: str | None) -> str:
    resolved = session_id or store.latest_session_id()
    if resolved is None:
        raise typer.BadParameter("No session exists. Run `emergent-rpg new` first.")
    return resolved


def _render_state(state: WorldState) -> str:
    player = state.player()
    location = state.locations[player.state.current_location]
    visible_items = [item.name for item in state.items.values() if item.location_id == location.id]
    npcs = [
        entity.name
        for entity in state.entities.values()
        if isinstance(entity, NPC) and entity.state.current_location == location.id
    ]
    exits = [state.locations[dest].name for dest in location.exits.values()]
    inventory = [state.items[item_id].name for item_id in player.state.inventory]
    return "\n".join(
        [
            f"Location: {location.name}",
            f"Time: {state.clock.display()} | Turn: {state.turn_number}",
            f"Visible: {', '.join(visible_items) if visible_items else 'nothing portable'}",
            f"NPCs: {', '.join(npcs) if npcs else 'none'}",
            f"Exits: {', '.join(exits)}",
            f"Inventory: {', '.join(inventory) if inventory else 'empty'}",
        ]
    )


@app.command("new")
def new_game(
    db: Annotated[Path, DB_OPTION] = DEFAULT_DB,
    name: Annotated[str, typer.Option(help="Session name.")] = "Ashfall Relay",
) -> None:
    engine = _engine(db)
    session = engine.new_session(name)
    typer.echo(f"Created session {session.id} ({session.name})")
    typer.echo(_render_state(engine.store.load_state(session.id)))


@app.command()
def status(
    session_id: Annotated[str | None, typer.Argument()] = None,
    db: Annotated[Path, DB_OPTION] = DEFAULT_DB,
) -> None:
    store = SQLiteStore(db)
    resolved = _resolve_session(store, session_id)
    typer.echo(f"Session: {resolved}")
    typer.echo(_render_state(store.load_state(resolved)))


@app.command()
def history(
    session_id: Annotated[str | None, typer.Argument()] = None,
    db: Annotated[Path, DB_OPTION] = DEFAULT_DB,
    limit: Annotated[int, typer.Option(min=1, max=500)] = 20,
) -> None:
    store = SQLiteStore(db)
    resolved = _resolve_session(store, session_id)
    for turn in store.list_turns(resolved, limit=limit):
        marker = "OK" if turn.accepted else "REJECTED"
        typer.echo(f"T{turn.turn_number:03d} [{marker}] > {turn.raw_input}")
        typer.echo(f"  {turn.narration}")


@app.command()
def play(
    session_id: Annotated[str | None, typer.Argument()] = None,
    db: Annotated[Path, DB_OPTION] = DEFAULT_DB,
    provider: Annotated[NarrativeProviderName, PROVIDER_OPTION] = NarrativeProviderName.SCRIPTED,
    action_parser: Annotated[
        ActionParserName, ACTION_PARSER_OPTION
    ] = ActionParserName.DETERMINISTIC,
) -> None:
    try:
        engine = _engine(db, provider, action_parser)
    except ProviderError as exc:
        raise typer.BadParameter(str(exc)) from exc

    resolved = _resolve_session(engine.store, session_id)
    typer.echo(
        "Ashfall Relay — "
        f"provider={provider.value}, action-parser={action_parser.value}; "
        "type `help` for commands, `quit` to exit."
    )
    typer.echo(_render_state(engine.store.load_state(resolved)))
    while True:
        try:
            text = typer.prompt("\n>")
        except (EOFError, KeyboardInterrupt):
            typer.echo("\nSession saved.")
            break
        if text.casefold().strip() in {"quit", "exit"}:
            typer.echo("Session saved.")
            break
        if text.casefold().strip() == "help":
            typer.echo(
                "Commands: move <exit>, inspect <target>, talk <npc>, "
                "take <item>, wait [minutes]. With an LLM action parser, "
                "natural phrasing is allowed."
            )
            continue
        try:
            result, narration, state = engine.process_text(resolved, text)
        except ProviderError as exc:
            typer.echo(f"Provider failed; turn was not committed: {exc}", err=True)
            continue
        typer.echo(narration)
        if result.accepted:
            typer.echo(_render_state(state))


if __name__ == "__main__":
    app()
