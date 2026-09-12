from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from emergent_rpg.cli.app import app
from emergent_rpg.domain.models import WorldState
from emergent_rpg.engine.reducer import replay
from emergent_rpg.persistence.db import SQLiteStore
from emergent_rpg.world.demo import build_demo_world
from emergent_rpg.world.pack import WorldPackLoadError, load_world_pack


def _write_pack(
    path: Path,
    *,
    pack_id: str = "custom-relay",
    name: str = "Custom Relay",
    state: WorldState | None = None,
    format_version: int = 1,
    extra: dict[str, object] | None = None,
) -> Path:
    world = state or build_demo_world()
    payload: dict[str, object] = {
        "format_version": format_version,
        "id": pack_id,
        "name": name,
        "initial_state": world.model_dump(mode="json"),
    }
    if extra:
        payload.update(extra)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_load_world_pack_returns_deep_copy_session_seed(tmp_path: Path) -> None:
    state = build_demo_world()
    state.locations["yard"].name = "Copper Yard"
    pack = load_world_pack(_write_pack(tmp_path / "world.json", state=state))

    session, initial = pack.instantiate()

    assert pack.id == "custom-relay"
    assert session.name == "Custom Relay"
    assert session.world_pack == "custom-relay"
    assert initial == pack.initial_state
    initial.locations["yard"].name = "Mutated After Instantiate"
    assert pack.initial_state.locations["yard"].name == "Copper Yard"


def test_cli_new_from_world_pack_persists_metadata_state_and_replay(tmp_path: Path) -> None:
    db_path = tmp_path / "game.db"
    state = build_demo_world()
    state.locations["yard"].name = "Copper Yard"
    pack_path = _write_pack(tmp_path / "world.json", state=state)

    result = CliRunner().invoke(
        app,
        ["new", "--db", str(db_path), "--world", str(pack_path)],
    )

    assert result.exit_code == 0, result.output
    assert "Custom Relay" in result.output
    assert "Copper Yard" in result.output
    store = SQLiteStore(db_path)
    session_id = store.latest_session_id()
    assert session_id is not None
    session = store.get_session(session_id)
    assert session.name == "Custom Relay"
    assert session.world_pack == "custom-relay"
    initial = store.load_initial_state(session_id)
    current = store.load_state(session_id)
    assert current.locations["yard"].name == "Copper Yard"
    assert store.load_events(session_id) == []
    assert replay(initial, store.load_events(session_id)) == current


def test_cli_world_pack_name_override_does_not_change_pack_identity(tmp_path: Path) -> None:
    db_path = tmp_path / "game.db"
    pack_path = _write_pack(tmp_path / "world.json")

    result = CliRunner().invoke(
        app,
        [
            "new",
            "--db",
            str(db_path),
            "--world",
            str(pack_path),
            "--name",
            "Campaign One",
        ],
    )

    assert result.exit_code == 0, result.output
    store = SQLiteStore(db_path)
    session_id = store.latest_session_id()
    assert session_id is not None
    session = store.get_session(session_id)
    assert session.name == "Campaign One"
    assert session.world_pack == "custom-relay"


def test_play_banner_uses_persisted_custom_session_name(tmp_path: Path) -> None:
    db_path = tmp_path / "game.db"
    pack_path = _write_pack(tmp_path / "world.json", name="Copper Frontier")
    runner = CliRunner()
    created = runner.invoke(
        app,
        ["new", "--db", str(db_path), "--world", str(pack_path)],
    )
    assert created.exit_code == 0, created.output
    store = SQLiteStore(db_path)
    session_id = store.latest_session_id()
    assert session_id is not None

    played = runner.invoke(
        app,
        ["play", session_id, "--db", str(db_path)],
        input="quit\n",
    )

    assert played.exit_code == 0, played.output
    assert "Copper Frontier — provider=scripted" in played.output


def test_invalid_world_pack_fails_before_database_creation(tmp_path: Path) -> None:
    db_path = tmp_path / "game.db"
    state = build_demo_world()
    initial_state = state.model_dump(mode="json")
    initial_state["player_id"] = "missing-player"
    payload = {
        "format_version": 1,
        "id": "broken-world",
        "name": "Broken World",
        "initial_state": initial_state,
    }
    pack_path = tmp_path / "broken.json"
    pack_path.write_text(json.dumps(payload), encoding="utf-8")

    result = CliRunner().invoke(
        app,
        ["new", "--db", str(db_path), "--world", str(pack_path)],
    )

    assert result.exit_code != 0
    assert "invalid world pack state" in result.output
    assert not db_path.exists()


def test_world_pack_rejects_invalid_json_version_extra_fields_and_nonzero_turn(
    tmp_path: Path,
) -> None:
    malformed = tmp_path / "malformed.json"
    malformed.write_text("{not-json", encoding="utf-8")
    with pytest.raises(WorldPackLoadError, match="invalid JSON"):
        load_world_pack(malformed)

    unsupported = _write_pack(tmp_path / "v2.json", format_version=2)
    with pytest.raises(WorldPackLoadError, match="invalid world pack schema"):
        load_world_pack(unsupported)

    extra = _write_pack(tmp_path / "extra.json", extra={"surprise": True})
    with pytest.raises(WorldPackLoadError, match="invalid world pack schema"):
        load_world_pack(extra)

    advanced_state = build_demo_world()
    advanced_state.turn_number = 3
    advanced = _write_pack(tmp_path / "advanced.json", state=advanced_state)
    with pytest.raises(WorldPackLoadError, match="turn_number must be 0"):
        load_world_pack(advanced)


def test_cli_new_without_world_pack_keeps_ashfall_defaults(tmp_path: Path) -> None:
    db_path = tmp_path / "game.db"

    result = CliRunner().invoke(app, ["new", "--db", str(db_path)])

    assert result.exit_code == 0, result.output
    store = SQLiteStore(db_path)
    session_id = store.latest_session_id()
    assert session_id is not None
    session = store.get_session(session_id)
    assert session.name == "Ashfall Relay"
    assert session.world_pack == "ashfall-relay"
