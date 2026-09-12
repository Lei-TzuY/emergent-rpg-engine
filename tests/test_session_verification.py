from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session
from typer.testing import CliRunner

from emergent_rpg.engine.service import GameEngine
from emergent_rpg.persistence.db import SessionRow, SQLiteStore, TurnRow
from emergent_rpg.persistence.verification import verify_session
from emergent_rpg.verification_cli import app


def _persisted_session(db_path: Path) -> tuple[SQLiteStore, str]:
    engine = GameEngine(SQLiteStore(db_path))
    session = engine.new_session("Integrity Check")
    taken, _, _ = engine.process_text(session.id, "take brass key")
    assert taken.accepted
    moved, _, _ = engine.process_text(session.id, "move operations")
    assert moved.accepted
    return engine.store, session.id


def test_verify_session_is_read_only_and_reports_consistent_state(tmp_path: Path) -> None:
    store, session_id = _persisted_session(tmp_path / "game.db")
    state_before = store.load_state(session_id)
    events_before = store.load_events(session_id)
    turns_before = store.list_turns(session_id)
    episodes_before = store.list_episodes(session_id)

    report = verify_session(store, session_id)

    assert report.passed
    assert report.replay_equal
    assert report.current_state_valid
    assert report.archive_consistent
    assert report.current_state_sha256 is not None
    assert report.event_count == len(events_before)
    assert report.turn_count == len(turns_before)
    assert report.episode_count == len(episodes_before)
    assert report.failures == []
    assert store.load_state(session_id) == state_before
    assert store.load_events(session_id) == events_before
    assert store.list_turns(session_id) == turns_before
    assert store.list_episodes(session_id) == episodes_before


def test_verify_session_detects_current_state_replay_mismatch(tmp_path: Path) -> None:
    store, session_id = _persisted_session(tmp_path / "game.db")
    with Session(store.engine) as db:
        row = db.get(SessionRow, session_id)
        assert row is not None
        row.current_state_json = row.initial_state_json
        db.commit()

    report = verify_session(store, session_id)

    assert not report.passed
    assert not report.replay_equal
    assert report.current_state_valid
    assert not report.archive_consistent
    assert any("does not match event replay" in failure for failure in report.failures)


def test_verify_session_detects_history_corruption_independently_of_state(tmp_path: Path) -> None:
    store, session_id = _persisted_session(tmp_path / "game.db")
    with Session(store.engine) as db:
        row = db.scalars(
            select(TurnRow)
            .where(TurnRow.session_id == session_id)
            .order_by(TurnRow.id)
        ).first()
        assert row is not None
        row.location_id = "missing-location"
        db.commit()

    report = verify_session(store, session_id)

    assert not report.passed
    assert report.replay_equal
    assert report.current_state_valid
    assert not report.archive_consistent
    assert any("turn references a missing location" in failure for failure in report.failures)


def test_verification_cli_emits_machine_readable_report(tmp_path: Path) -> None:
    db_path = tmp_path / "game.db"
    _, session_id = _persisted_session(db_path)

    result = CliRunner().invoke(app, [session_id, "--db", str(db_path)])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["session_id"] == session_id
    assert payload["passed"] is True
    assert payload["replay_equal"] is True
    assert payload["archive_consistent"] is True


def test_verification_cli_does_not_create_missing_database(tmp_path: Path) -> None:
    db_path = tmp_path / "missing.db"

    result = CliRunner().invoke(app, ["session-x", "--db", str(db_path)])

    assert result.exit_code == 2
    assert "database does not exist" in result.output
    assert not db_path.exists()
