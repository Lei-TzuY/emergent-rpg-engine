from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from emergent_rpg.persistence.database_audit import DatabaseAuditError, audit_database

app = typer.Typer(
    help="Read-only integrity audit for an entire emergent-rpg SQLite database.",
    invoke_without_command=True,
    context_settings={"allow_interspersed_args": True},
)
DEFAULT_DB = Path("emergent-rpg.db")


@app.callback(invoke_without_command=True)
def audit_database_command(
    db: Annotated[
        Path,
        typer.Option("--db", help="Existing SQLite database path."),
    ] = DEFAULT_DB,
) -> None:
    try:
        report = audit_database(db)
    except DatabaseAuditError as exc:
        typer.echo(f"Database audit failed: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    typer.echo(report.model_dump_json(indent=2))
    if not report.passed:
        raise typer.Exit(code=1)
