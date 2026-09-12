from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session
from typer.testing import CliRunner

from emergent_rpg.database_audit_cli import app
from emergent_rpg.engine.service import GameEngine
from emergent_rpg.persistence.database_audit import DatabaseAuditError, audit_database
from emergent_rpg.persistence.db import SessionRow, SQLiteStore
from emergent_rpg.persistence.schema import CURRENT_SCHEMA_VERSION


def _populated_database(path: Path) -> tuple[SQLiteStore, list[str]]:
    engine = GameEngine(SQLiteStore(path))
    first = engine.new_session("Audit One")
    taken, _, _ = engine.process_text(first.id, "take brass key")
    assert taken.accepted
    moved, _, _ = engine.process_text(first.id, "move operations")
    assert moved.accepted

    second = engine.new_session("Audit Two")
    waited, _, _ = engine.process_text(second.id, "wait 5")
    assert waited.accepted
    return engine.store, [first.id, second.id]


def test_audit_verifies_all_sessions_without_mutating_database(tmp_path: Path) -> None:
    path = tmp_path / "game.db"
    _, session_ids = _populated_database(path)
    bytes_before = path.read_bytes()

    report = audit_database(path)

    assert report.passed
    assert report.schema_version == CURRENT_SCHEMA_VERSION
    assert report.schema_marker_present is True
    assert report.sqlite_quick_check == ["ok"]
    assert report.session_count == 2
    assert report.verified_session_ids == sorted(session_ids)
    assert report.failures == []
    assert len(report.sha256) == 64
    assert report.size_bytes == path.stat().st_size
    assert path.read_bytes() == bytes_before


def test_audit_reports_logical_corruption_without_mutating_database(tmp_path: Path) -> None:
    path = tmp_path / "game.db"
    store, session_ids = _populated_database(path)
    with Session(store.engine) as db:
        row = db.get(SessionRow, session_ids[0])
        assert row is not None
        row.current_state_json = row.initial_state_json
        db.commit()
    store.engine.dispose()
    bytes_before = path.read_bytes()

    report = audit_database(path)

    assert not report.passed
    assert report.session_count == 2
    assert report.verified_session_ids == [session_ids[1]]
    assert any(session_ids[0] in failure for failure in report.failures)
    assert path.read_bytes() == bytes_before


def test_audit_accepts_exact_legacy_shape_without_adopting_schema_marker(
    tmp_path: Path,
) -> None:
    path = tmp_path / "legacy.db"
    store = SQLiteStore(path)
    with store.engine.begin() as connection:
        connection.execute(text("DROP TABLE schema_metadata"))
    store.engine.dispose()
    bytes_before = path.read_bytes()

    report = audit_database(path)

    assert report.passed
    assert report.schema_version == CURRENT_SCHEMA_VERSION
    assert report.schema_marker_present is False
    assert report.session_count == 0
    assert path.read_bytes() == bytes_before
    inspection_engine = create_engine(f"sqlite:///{path}")
    try:
        assert "schema_metadata" not in inspect(inspection_engine).get_table_names()
    finally:
        inspection_engine.dispose()


def test_audit_rejects_future_schema_without_rewriting_version(tmp_path: Path) -> None:
    path = tmp_path / "future.db"
    store = SQLiteStore(path)
    with store.engine.begin() as connection:
        connection.execute(text("UPDATE schema_metadata SET schema_version = 2 WHERE id = 1"))
    store.engine.dispose()
    bytes_before = path.read_bytes()

    report = audit_database(path)

    assert not report.passed
    assert report.schema_version is None
    assert any("newer than supported" in failure for failure in report.failures)
    assert path.read_bytes() == bytes_before


def test_audit_missing_database_does_not_create_file(tmp_path: Path) -> None:
    path = tmp_path / "missing.db"

    with pytest.raises(DatabaseAuditError, match="database does not exist"):
        audit_database(path)

    assert not path.exists()


def test_database_audit_cli_emits_json_and_failure_exit_codes(tmp_path: Path) -> None:
    healthy_path = tmp_path / "healthy.db"
    _populated_database(healthy_path)

    healthy = CliRunner().invoke(app, ["--db", str(healthy_path)])

    assert healthy.exit_code == 0, healthy.output
    healthy_payload = json.loads(healthy.output)
    assert healthy_payload["passed"] is True
    assert healthy_payload["session_count"] == 2

    missing_path = tmp_path / "missing.db"
    missing = CliRunner().invoke(app, ["--db", str(missing_path)])
    assert missing.exit_code == 2
    assert "database does not exist" in missing.output
    assert not missing_path.exists()
