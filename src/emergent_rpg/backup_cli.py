from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from emergent_rpg.persistence.snapshot import (
    DatabaseSnapshotError,
    create_verified_database_snapshot,
)

app = typer.Typer(
    help="Create a verified whole-database SQLite snapshot.",
    invoke_without_command=True,
    context_settings={"allow_interspersed_args": True},
)
DEFAULT_DB = Path("emergent-rpg.db")


@app.callback(invoke_without_command=True)
def backup_database_command(
    output: Annotated[
        Path,
        typer.Argument(help="Destination SQLite snapshot path."),
    ],
    db: Annotated[
        Path,
        typer.Option("--db", help="Existing source SQLite database path."),
    ] = DEFAULT_DB,
    overwrite: Annotated[
        bool,
        typer.Option("--overwrite", help="Replace an existing destination after verification."),
    ] = False,
) -> None:
    try:
        report = create_verified_database_snapshot(db, output, overwrite=overwrite)
    except DatabaseSnapshotError as exc:
        typer.echo(f"Snapshot failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(report.model_dump_json(indent=2))
