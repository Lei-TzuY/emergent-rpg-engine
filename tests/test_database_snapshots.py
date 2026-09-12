from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy.orm import Session
from typer.testing import CliRunner

from emergent_rpg.backup_cli import app
from emergent_rpg.engine.service import GameEngine
from emergent_rpg.persistence.db import SessionRow, SQLiteStore
from emergent_rpg.persistence.snapshot import (
    DatabaseSnapshotError,
    create_verified_database_snapshot,
)


def _populated_database(path: Path) -> tuple[SQLiteStore, list[str]]:
    engine = GameEngine(SQLiteStore(path))
    first = engine.new_session("Snapshot One")
    taken, _, _ = engine.process_text(first.id, "take brass key")
    assert taken.accepted
    moved, _, _ = engine.process_text(first.id, "move operations")
    assert moved.accepted

    second = engine.new_session("Snapshot Two")
    waited, _, _ = engine.process_text(second.id, "wait 5")
    assert waited.accepted
    return engine.store, [first.id, second.id]


def test_snapshot_preserves_every_persisted_session_and_schema(tmp_path: Path) -> None:
    source_path = tmp_path / "source.db"
    destination_path = tmp_path / "snapshot.db"
    source, session_ids = _populated_database(source_path)

    report = create_verified_database_snapshot(source_path, destination_path)

    assert report.passed
    assert report.sqlite_quick_check == "ok"
    assert report.session_count == 2
    assert report.verified_session_ids == sorted(session_ids)
    assert len(report.sha256) == 64
    assert report.size_bytes == destination_path.stat().st_size
    snapshot = SQLiteStore(destination_path)
    assert snapshot.schema_version == source.schema_version
    for session_id in session_ids:
        assert snapshot.get_session(session_id) == source.get_session(session_id)
        assert snapshot.load_initial_state(session_id) == source.load_initial_state(session_id)
        assert snapshot.load_state(session_id) == source.load_state(session_id)
        assert snapshot.load_events(session_id) == source.load_events(session_id)
        assert snapshot.list_turns(session_id) == source.list_turns(session_id)
        assert snapshot.list_episodes(session_id) == source.list_episodes(session_id)


def test_snapshot_refuses_missing_source_without_creating_files(tmp_path: Path) -> None:
    source_path = tmp_path / "missing.db"
    destination_path = tmp_path / "snapshot.db"

    with pytest.raises(DatabaseSnapshotError, match="source database does not exist"):
        create_verified_database_snapshot(source_path, destination_path)

    assert not source_path.exists()
    assert not destination_path.exists()


def test_snapshot_refuses_same_source_and_destination(tmp_path: Path) -> None:
    source_path = tmp_path / "game.db"
    _populated_database(source_path)

    with pytest.raises(DatabaseSnapshotError, match="paths must differ"):
        create_verified_database_snapshot(source_path, source_path, overwrite=True)


def test_snapshot_refuses_existing_destination_by_default(tmp_path: Path) -> None:
    source_path = tmp_path / "source.db"
    destination_path = tmp_path / "snapshot.db"
    _populated_database(source_path)
    destination_path.write_bytes(b"sentinel")

    with pytest.raises(DatabaseSnapshotError, match="destination already exists"):
        create_verified_database_snapshot(source_path, destination_path)

    assert destination_path.read_bytes() == b"sentinel"


def test_snapshot_overwrite_publishes_verified_replacement(tmp_path: Path) -> None:
    source_path = tmp_path / "source.db"
    destination_path = tmp_path / "snapshot.db"
    source, session_ids = _populated_database(source_path)
    destination_path.write_bytes(b"sentinel")

    report = create_verified_database_snapshot(
        source_path,
        destination_path,
        overwrite=True,
    )

    assert report.passed
    assert destination_path.read_bytes() != b"sentinel"
    snapshot = SQLiteStore(destination_path)
    for session_id in session_ids:
        assert snapshot.load_state(session_id) == source.load_state(session_id)


def test_failed_verification_does_not_publish_or_clobber_destination(tmp_path: Path) -> None:
    source_path = tmp_path / "source.db"
    destination_path = tmp_path / "snapshot.db"
    source, session_ids = _populated_database(source_path)
    with Session(source.engine) as db:
        row = db.get(SessionRow, session_ids[0])
        assert row is not None
        row.current_state_json = row.initial_state_json
        db.commit()
    destination_path.write_bytes(b"sentinel")

    with pytest.raises(DatabaseSnapshotError, match="snapshot session verification failed"):
        create_verified_database_snapshot(
            source_path,
            destination_path,
            overwrite=True,
        )

    assert destination_path.read_bytes() == b"sentinel"
    assert list(tmp_path.glob(f".{destination_path.name}.*.tmp")) == []


def test_snapshot_cli_emits_machine_readable_report(tmp_path: Path) -> None:
    source_path = tmp_path / "source.db"
    destination_path = tmp_path / "snapshot.db"
    _, session_ids = _populated_database(source_path)

    result = CliRunner().invoke(
        app,
        [str(destination_path), "--db", str(source_path)],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["passed"] is True
    assert payload["session_count"] == 2
    assert payload["verified_session_ids"] == sorted(session_ids)
    assert payload["sqlite_quick_check"] == "ok"
    assert destination_path.exists()
