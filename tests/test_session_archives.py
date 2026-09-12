from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from emergent_rpg.cli.app import app
from emergent_rpg.engine.service import GameEngine
from emergent_rpg.persistence.archive import load_session_archive
from emergent_rpg.persistence.db import SQLiteStore


def _source_session(db_path: Path) -> tuple[GameEngine, str]:
    engine = GameEngine(SQLiteStore(db_path))
    session = engine.new_session("Portable Ashfall")
    taken, _, _ = engine.process_text(session.id, "take brass key")
    assert taken.accepted
    moved, _, _ = engine.process_text(session.id, "move operations")
    assert moved.accepted
    return engine, session.id


def _event_payloads(store: SQLiteStore, session_id: str) -> list[dict[str, object]]:
    return [event.model_dump(mode="json") for event in store.load_events(session_id)]


def _turn_payloads(store: SQLiteStore, session_id: str) -> list[dict[str, object]]:
    return [
        turn.model_copy(update={"session_id": "normalized"}).model_dump(mode="json")
        for turn in store.list_turns(session_id)
    ]


def test_cli_export_import_round_trip_preserves_session_history(tmp_path: Path) -> None:
    source_db = tmp_path / "source.db"
    target_db = tmp_path / "target.db"
    archive_path = tmp_path / "save.json"
    source_engine, source_id = _source_session(source_db)
    source_store = source_engine.store

    runner = CliRunner()
    exported = runner.invoke(
        app,
        [
            "export-session",
            source_id,
            "--db",
            str(source_db),
            "--output",
            str(archive_path),
        ],
    )
    assert exported.exit_code == 0, exported.output
    assert archive_path.exists()

    imported = runner.invoke(
        app,
        ["import-session", str(archive_path), "--db", str(target_db)],
    )
    assert imported.exit_code == 0, imported.output

    target_store = SQLiteStore(target_db)
    imported_id = target_store.latest_session_id()
    assert imported_id is not None
    assert imported_id != source_id
    source_session = source_store.get_session(source_id)
    imported_session = target_store.get_session(imported_id)
    assert imported_session.name == source_session.name
    assert imported_session.world_pack == source_session.world_pack
    assert target_store.load_initial_state(imported_id) == source_store.load_initial_state(source_id)
    assert target_store.load_state(imported_id) == source_store.load_state(source_id)
    assert _event_payloads(target_store, imported_id) == _event_payloads(source_store, source_id)
    assert _turn_payloads(target_store, imported_id) == _turn_payloads(source_store, source_id)
    assert target_store.list_episodes(imported_id) == source_store.list_episodes(source_id)
    assert GameEngine(target_store).replay_session(imported_id) == target_store.load_state(imported_id)


def test_import_name_override_preserves_world_pack_identity(tmp_path: Path) -> None:
    source_db = tmp_path / "source.db"
    target_db = tmp_path / "target.db"
    archive_path = tmp_path / "save.json"
    _, source_id = _source_session(source_db)
    runner = CliRunner()
    assert runner.invoke(
        app,
        ["export-session", source_id, "--db", str(source_db), "-o", str(archive_path)],
    ).exit_code == 0

    imported = runner.invoke(
        app,
        [
            "import-session",
            str(archive_path),
            "--db",
            str(target_db),
            "--name",
            "Restored Campaign",
        ],
    )
    assert imported.exit_code == 0, imported.output
    store = SQLiteStore(target_db)
    imported_id = store.latest_session_id()
    assert imported_id is not None
    session = store.get_session(imported_id)
    assert session.name == "Restored Campaign"
    assert session.world_pack == "ashfall-relay"


def test_tampered_digest_is_rejected_before_target_database_creation(tmp_path: Path) -> None:
    source_db = tmp_path / "source.db"
    target_db = tmp_path / "target.db"
    archive_path = tmp_path / "save.json"
    _, source_id = _source_session(source_db)
    runner = CliRunner()
    assert runner.invoke(
        app,
        ["export-session", source_id, "--db", str(source_db), "-o", str(archive_path)],
    ).exit_code == 0

    payload = json.loads(archive_path.read_text(encoding="utf-8"))
    payload["current_state_sha256"] = "0" * 64
    archive_path.write_text(json.dumps(payload), encoding="utf-8")

    result = runner.invoke(
        app,
        ["import-session", str(archive_path), "--db", str(target_db)],
    )
    assert result.exit_code != 0
    assert "digest does not match replay" in result.output
    assert not target_db.exists()


def test_forged_event_precondition_is_rejected_before_target_database_creation(
    tmp_path: Path,
) -> None:
    source_db = tmp_path / "source.db"
    target_db = tmp_path / "target.db"
    archive_path = tmp_path / "save.json"
    _, source_id = _source_session(source_db)
    runner = CliRunner()
    assert runner.invoke(
        app,
        ["export-session", source_id, "--db", str(source_db), "-o", str(archive_path)],
    ).exit_code == 0

    payload = json.loads(archive_path.read_text(encoding="utf-8"))
    first_event = payload["events"][0]
    assert first_event["type"] == "item_acquired"
    first_event["from_location"] = "archive"
    archive_path.write_text(json.dumps(payload), encoding="utf-8")

    result = runner.invoke(
        app,
        ["import-session", str(archive_path), "--db", str(target_db)],
    )
    assert result.exit_code != 0
    assert "violates preconditions" in result.output
    assert not target_db.exists()


def test_duplicate_import_rolls_back_without_partial_session(tmp_path: Path) -> None:
    source_db = tmp_path / "source.db"
    target_db = tmp_path / "target.db"
    archive_path = tmp_path / "save.json"
    _, source_id = _source_session(source_db)
    runner = CliRunner()
    assert runner.invoke(
        app,
        ["export-session", source_id, "--db", str(source_db), "-o", str(archive_path)],
    ).exit_code == 0
    first = runner.invoke(
        app,
        ["import-session", str(archive_path), "--db", str(target_db)],
    )
    assert first.exit_code == 0, first.output
    store = SQLiteStore(target_db)
    first_import_id = store.latest_session_id()
    assert first_import_id is not None

    duplicate = runner.invoke(
        app,
        ["import-session", str(archive_path), "--db", str(target_db)],
    )
    assert duplicate.exit_code != 0
    assert "conflicts with existing event or episode provenance" in duplicate.output
    assert SQLiteStore(target_db).latest_session_id() == first_import_id


def test_archive_loader_rejects_unknown_fields_and_existing_export_without_overwrite(
    tmp_path: Path,
) -> None:
    source_db = tmp_path / "source.db"
    archive_path = tmp_path / "save.json"
    _, source_id = _source_session(source_db)
    runner = CliRunner()
    first = runner.invoke(
        app,
        ["export-session", source_id, "--db", str(source_db), "-o", str(archive_path)],
    )
    assert first.exit_code == 0, first.output

    second = runner.invoke(
        app,
        ["export-session", source_id, "--db", str(source_db), "-o", str(archive_path)],
    )
    assert second.exit_code != 0
    assert "archive already exists" in second.output

    payload = json.loads(archive_path.read_text(encoding="utf-8"))
    payload["unknown"] = True
    archive_path.write_text(json.dumps(payload), encoding="utf-8")
    try:
        load_session_archive(archive_path)
    except ValueError as exc:
        assert "invalid session archive schema" in str(exc)
    else:
        raise AssertionError("unknown archive field should be rejected")
