from __future__ import annotations

import hashlib
import sqlite3
from contextlib import closing
from pathlib import Path

from pydantic import BaseModel, Field
from sqlalchemy import create_engine, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from emergent_rpg.persistence.db import Base, SessionRow, SQLiteStore
from emergent_rpg.persistence.schema import StoreSchemaError, inspect_schema_compatible
from emergent_rpg.persistence.verification import verify_session


class DatabaseAuditError(RuntimeError):
    """Raised when a database audit cannot be started safely."""


class DatabaseAuditReport(BaseModel):
    database_path: str
    schema_version: int | None = Field(default=None, ge=1)
    schema_marker_present: bool | None = None
    sqlite_quick_check: list[str] = Field(default_factory=list)
    session_count: int = Field(ge=0)
    verified_session_ids: list[str] = Field(default_factory=list)
    failures: list[str] = Field(default_factory=list)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size_bytes: int = Field(ge=0)
    passed: bool


class _ReadOnlySQLiteStore(SQLiteStore):
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        uri = f"{self.path.resolve().as_uri()}?mode=ro"
        self.engine = create_engine(
            "sqlite://",
            creator=lambda: sqlite3.connect(uri, uri=True, timeout=5.0),
        )
        self.schema_version, self.schema_marker_present = inspect_schema_compatible(
            self.engine,
            Base.metadata,
        )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _quick_check_read_only(path: Path) -> list[str]:
    uri = f"{path.resolve().as_uri()}?mode=ro"
    with closing(sqlite3.connect(uri, uri=True, timeout=5.0)) as connection:
        return [str(row[0]) for row in connection.execute("PRAGMA quick_check").fetchall()]


def _base_report(
    path: Path,
    *,
    quick_check: list[str],
    failures: list[str],
    schema_version: int | None = None,
    schema_marker_present: bool | None = None,
    session_count: int = 0,
    verified_session_ids: list[str] | None = None,
) -> DatabaseAuditReport:
    return DatabaseAuditReport(
        database_path=str(path),
        schema_version=schema_version,
        schema_marker_present=schema_marker_present,
        sqlite_quick_check=quick_check,
        session_count=session_count,
        verified_session_ids=verified_session_ids or [],
        failures=failures,
        sha256=_sha256_file(path),
        size_bytes=path.stat().st_size,
        passed=not failures,
    )


def audit_database(path: str | Path) -> DatabaseAuditReport:
    """Audit one existing engine SQLite database without mutating it."""

    database_path = Path(path)
    if not database_path.exists() or not database_path.is_file():
        raise DatabaseAuditError(f"database does not exist: {database_path}")

    try:
        quick_check = _quick_check_read_only(database_path)
    except sqlite3.Error as exc:
        return _base_report(
            database_path,
            quick_check=[],
            failures=[f"SQLite quick_check failed to execute: {exc}"],
        )
    if quick_check != ["ok"]:
        return _base_report(
            database_path,
            quick_check=quick_check,
            failures=[f"SQLite quick_check failed: {quick_check}"],
        )

    try:
        store = _ReadOnlySQLiteStore(database_path)
    except (StoreSchemaError, SQLAlchemyError, sqlite3.Error) as exc:
        return _base_report(
            database_path,
            quick_check=quick_check,
            failures=[f"schema validation failed: {exc}"],
        )

    try:
        with Session(store.engine) as db:
            session_ids = list(
                db.scalars(select(SessionRow.id).order_by(SessionRow.id)).all()
            )

        failures: list[str] = []
        verified_session_ids: list[str] = []
        for session_id in session_ids:
            try:
                report = verify_session(store, session_id)
            except (KeyError, ValueError, SQLAlchemyError) as exc:
                failures.append(f"{session_id}: persisted data could not be verified: {exc}")
                continue
            if report.passed:
                verified_session_ids.append(session_id)
            else:
                failures.append(f"{session_id}: {'; '.join(report.failures)}")

        return _base_report(
            database_path,
            quick_check=quick_check,
            failures=failures,
            schema_version=store.schema_version,
            schema_marker_present=store.schema_marker_present,
            session_count=len(session_ids),
            verified_session_ids=verified_session_ids,
        )
    finally:
        store.engine.dispose()
