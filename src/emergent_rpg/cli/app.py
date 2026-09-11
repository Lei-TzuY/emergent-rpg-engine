from __future__ import annotations

from pathlib import Path

import typer

from emergent_rpg.domain.models import NPC, WorldState
from emergent_rpg.engine.service import GameEngine
from emergent_rpg.persistence.db import SQLiteStore

app = typer.Typer(help="Persistent deterministic text-RPG engine demo.")
DEFAULT_DB = Path("emergent-rpg.db")


def _engine(db: Path) -> GameEngine:
    return GameEngine(SQLiteStore(db))


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
    db: Path = typer.Option(DEFAULT_DB, "--db", help="SQLite database path."),
    name: str = typer.Option("Ashfall Relay", help="Session name."),
) -> None:
    engine = _engine(db)
    session = engine.new_session(name)
    typer.echo(f"Created session {session.id} ({session.name})")
    typer.echo(_render_state(engine.store.load_state(session.id)))


@app.command()
def status(
    session_id: str | None = typer.Argument(None),
    db: Path = typer.Option(DEFAULT_DB, "--db", help="SQLite database path."),
) -> None:
    store = SQLiteStore(db)
    resolved = _resolve_session(store, session_id)
    typer.echo(f"Session: {resolved}")
    typer.echo(_render_state(store.load_state(resolved)))


@app.command()
def history(
    session_id: str | None = typer.Argument(None),
    db: Path = typer.Option(DEFAULT_DB, "--db", help="SQLite database path."),
    limit: int = typer.Option(20, min=1, max=500),
) -> None:
    store = SQLiteStore(db)
    resolved = _resolve_session(store, session_id)
    for turn in store.list_turns(resolved, limit=limit):
        marker = "OK" if turn.accepted else "REJECTED"
        typer.echo(f"T{turn.turn_number:03d} [{marker}] > {turn.raw_input}")
        typer.echo(f"  {turn.narration}")


@app.command()
def play(
    session_id: str | None = typer.Argument(None),
    db: Path = typer.Option(DEFAULT_DB, "--db", help="SQLite database path."),
) -> None:
    engine = _engine(db)
    resolved = _resolve_session(engine.store, session_id)
    typer.echo("Ashfall Relay — type `help` for commands, `quit` to exit.")
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
                "take <item>, wait [minutes]"
            )
            continue
        result, narration, state = engine.process_text(resolved, text)
        typer.echo(narration)
        if result.accepted:
            typer.echo(_render_state(state))


if __name__ == "__main__":
    app()
