from __future__ import annotations

import hashlib
import os
import sqlite3
from contextlib import closing
from pathlib import Path
from tempfile import mkstemp

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from emergent_rpg.persistence.db import SQLiteStore, SessionRow
from emergent_rpg.persistence.verification import verify_session


class DatabaseSnapshotError(RuntimeError):
    """Raised when a whole-database snapshot cannot be published safely."""


class DatabaseSnapshotReport(BaseModel):
    source_path: str
    destination_path: str
    schema_version: int = Field(ge=1)
    session_count: int = Field(ge=0)
    verified_session_ids: list[str]
    sqlite_quick_check: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size_bytes: int = Field(ge=0)
    passed: bool


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sqlite_backup(source: Path, destination: Path) -> None:
    source_uri = f"{source.resolve().as_uri()}?mode=ro"
    try:
        with closing(sqlite3.connect(source_uri, uri=True, timeout=5.0)) as source_db:
            with closing(sqlite3.connect(destination, timeout=5.0)) as destination_db:
                source_db.backup(destination_db)
    except sqlite3.Error as exc:
        raise DatabaseSnapshotError(f"SQLite backup failed: {exc}") from exc


def _quick_check(path: Path) -> str:
    try:
        with closing(sqlite3.connect(path, timeout=5.0)) as connection:
            rows = [str(row[0]) for row in connection.execute("PRAGMA quick_check").fetchall()]
    except sqlite3.Error as exc:
        raise DatabaseSnapshotError(f"SQLite quick_check failed to execute: {exc}") from exc
    if rows != ["ok"]:
        raise DatabaseSnapshotError(f"SQLite quick_check failed: {rows}")
    return rows[0]


def _verify_snapshot(path: Path) -> tuple[int, list[str]]:
    try:
        store = SQLiteStore(path)
    except (OSError, ValueError, RuntimeError) as exc:
        raise DatabaseSnapshotError(f"snapshot schema validation failed: {exc}") from exc

    try:
        with Session(store.engine) as db:
            session_ids = list(
                db.scalars(select(SessionRow.id).order_by(SessionRow.id)).all()
            )
        failures: list[str] = []
        for session_id in session_ids:
            try:
                report = verify_session(store, session_id)
            except (KeyError, ValueError) as exc:
                failures.append(f"{session_id}: persisted data could not be verified: {exc}")
                continue
            if not report.passed:
                failures.append(f"{session_id}: {'; '.join(report.failures)}")
        if failures:
            raise DatabaseSnapshotError(
                "snapshot session verification failed: " + " | ".join(failures)
            )
        return store.schema_version, session_ids
    finally:
        store.engine.dispose()


def create_verified_database_snapshot(
    source_path: str | Path,
    destination_path: str | Path,
    *,
    overwrite: bool = False,
) -> DatabaseSnapshotReport:
    """Create and publish a verified whole-SQLite snapshot.

    The source database is opened read-only through SQLite's online backup API. The
    destination is published only after the temporary copy passes physical, schema,
    and per-session logical verification.
    """

    source = Path(source_path)
    destination = Path(destination_path)
    if not source.exists() or not source.is_file():
        raise DatabaseSnapshotError(f"source database does not exist: {source}")
    if source.resolve() == destination.resolve():
        raise DatabaseSnapshotError("source and destination database paths must differ")
    if destination.exists() and not overwrite:
        raise DatabaseSnapshotError(f"destination already exists: {destination}")
    if destination.exists() and destination.is_dir():
        raise DatabaseSnapshotError(f"destination is a directory: {destination}")

    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = mkstemp(
        prefix=f".{destination.name}.",
        suffix=".tmp",
        dir=destination.parent,
    )
    os.close(fd)
    temporary_path = Path(temporary_name)

    try:
        _sqlite_backup(source, temporary_path)
        quick_check = _quick_check(temporary_path)
        schema_version, session_ids = _verify_snapshot(temporary_path)
        digest = _sha256_file(temporary_path)
        size_bytes = temporary_path.stat().st_size

        if destination.exists() and not overwrite:
            raise DatabaseSnapshotError(f"destination already exists: {destination}")
        os.replace(temporary_path, destination)
    except DatabaseSnapshotError:
        temporary_path.unlink(missing_ok=True)
        raise
    except OSError as exc:
        temporary_path.unlink(missing_ok=True)
        raise DatabaseSnapshotError(f"snapshot publication failed: {exc}") from exc

    return DatabaseSnapshotReport(
        source_path=str(source),
        destination_path=str(destination),
        schema_version=schema_version,
        session_count=len(session_ids),
        verified_session_ids=session_ids,
        sqlite_quick_check=quick_check,
        sha256=digest,
        size_bytes=size_bytes,
        passed=True,
    )
