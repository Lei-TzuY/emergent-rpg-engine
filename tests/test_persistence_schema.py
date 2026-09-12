from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

from emergent_rpg.domain.models import GameSession
from emergent_rpg.persistence.db import Base, SessionRow, SQLiteStore
from emergent_rpg.persistence.schema import CURRENT_SCHEMA_VERSION, StoreSchemaError
from emergent_rpg.world.demo import build_demo_world


def _schema_version(path: Path) -> int:
    engine = create_engine(f"sqlite:///{path}")
    with engine.connect() as connection:
        value = connection.execute(
            text("SELECT schema_version FROM schema_metadata WHERE id = 1")
        ).scalar_one()
    assert isinstance(value, int)
    return value


def test_new_database_records_and_reopens_current_schema_version(tmp_path: Path) -> None:
    path = tmp_path / "game.db"

    first = SQLiteStore(path)
    second = SQLiteStore(path)

    assert first.schema_version == CURRENT_SCHEMA_VERSION
    assert second.schema_version == CURRENT_SCHEMA_VERSION
    assert _schema_version(path) == CURRENT_SCHEMA_VERSION
    assert "schema_metadata" in inspect(second.engine).get_table_names()


def test_exact_legacy_schema_is_adopted_without_losing_session_data(tmp_path: Path) -> None:
    path = tmp_path / "legacy.db"
    legacy_engine = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(legacy_engine)
    initial = build_demo_world()
    session = GameSession(
        id="legacy-session",
        name="Legacy campaign",
        world_pack="ashfall-relay",
        created_at=datetime.now(UTC).isoformat(),
    )
    with Session(legacy_engine) as db:
        payload = SQLiteStore._dump_model(initial)
        db.add(
            SessionRow(
                id=session.id,
                name=session.name,
                world_pack=session.world_pack,
                created_at=session.created_at,
                initial_state_json=payload,
                current_state_json=payload,
            )
        )
        db.commit()

    store = SQLiteStore(path)

    assert store.schema_version == CURRENT_SCHEMA_VERSION
    assert _schema_version(path) == CURRENT_SCHEMA_VERSION
    assert store.get_session(session.id) == session
    assert store.load_state(session.id) == initial


def test_future_schema_version_is_rejected_without_rewriting_version(tmp_path: Path) -> None:
    path = tmp_path / "future.db"
    store = SQLiteStore(path)
    with store.engine.begin() as connection:
        connection.execute(text("UPDATE schema_metadata SET schema_version = 2 WHERE id = 1"))

    with pytest.raises(StoreSchemaError, match="newer than supported"):
        SQLiteStore(path)

    assert _schema_version(path) == 2


def test_older_version_requires_explicit_migration(tmp_path: Path) -> None:
    path = tmp_path / "old.db"
    store = SQLiteStore(path)
    with store.engine.begin() as connection:
        connection.execute(text("UPDATE schema_metadata SET schema_version = 0 WHERE id = 1"))

    with pytest.raises(StoreSchemaError, match="requires a migration"):
        SQLiteStore(path)

    assert _schema_version(path) == 0


def test_partial_legacy_schema_is_rejected_without_auto_repair(tmp_path: Path) -> None:
    path = tmp_path / "partial.db"
    engine = create_engine(f"sqlite:///{path}")
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE game_sessions ("
                "id VARCHAR PRIMARY KEY, "
                "name VARCHAR NOT NULL"
                ")"
            )
        )

    with pytest.raises(StoreSchemaError, match="database table set does not match"):
        SQLiteStore(path)

    tables = set(inspect(engine).get_table_names())
    assert tables == {"game_sessions"}
    assert "schema_metadata" not in tables
