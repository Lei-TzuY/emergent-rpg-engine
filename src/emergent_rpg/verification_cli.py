from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from emergent_rpg.persistence.db import SQLiteStore
from emergent_rpg.persistence.verification import verify_session

app = typer.Typer(
    help="Read-only integrity verification for a persisted emergent-rpg session.",
    invoke_without_command=True,
)
DEFAULT_DB = Path("emergent-rpg.db")


@app.callback(invoke_without_command=True)
def verify_session_command(
    session_id: Annotated[str | None, typer.Argument(help="Session id; latest when omitted.")] = None,
    db: Annotated[Path, typer.Option("--db", help="Existing SQLite database path.")] = DEFAULT_DB,
) -> None:
    if not db.exists():
        typer.echo(f"Verification failed: database does not exist: {db}", err=True)
        raise typer.Exit(code=2)

    store = SQLiteStore(db)
    resolved = session_id or store.latest_session_id()
    if resolved is None:
        typer.echo("Verification failed: database contains no sessions.", err=True)
        raise typer.Exit(code=2)

    try:
        report = verify_session(store, resolved)
    except KeyError as exc:
        typer.echo(f"Verification failed: {exc.args[0]}", err=True)
        raise typer.Exit(code=2) from exc
    except ValueError as exc:
        typer.echo(f"Verification failed: persisted data could not be decoded: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(report.model_dump_json(indent=2))
    if not report.passed:
        raise typer.Exit(code=1)
