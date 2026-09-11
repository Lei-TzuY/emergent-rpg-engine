from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from fastapi.testclient import TestClient

from emergent_rpg.api.app import create_app
from emergent_rpg.engine.service import GameEngine
from emergent_rpg.persistence.db import SQLiteStore
from emergent_rpg.providers.errors import ProviderRequestError
from emergent_rpg.providers.factory import NarrativeProviderName


class FailingTransport:
    def post_json(
        self,
        url: str,
        headers: Mapping[str, str],
        payload: Mapping[str, object],
        timeout: float,
    ) -> dict[str, object]:
        del url, headers, payload, timeout
        raise ProviderRequestError("simulated API provider outage")


def make_client(tmp_path: Path) -> tuple[TestClient, Path]:
    db_path = tmp_path / "game.db"
    return TestClient(create_app(db_path)), db_path


def create_session(client: TestClient) -> str:
    response = client.post("/sessions", json={"name": "API test"})
    assert response.status_code == 201
    return str(response.json()["session"]["id"])


def test_create_and_read_session_exposes_only_player_visible_state(tmp_path: Path) -> None:
    client, _ = make_client(tmp_path)
    session_id = create_session(client)

    response = client.get(f"/sessions/{session_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["state"]["location_name"] == "Ashfall Yard"
    assert body["state"]["known_facts"] == []
    wire = response.text
    assert "02:13" not in wire
    assert "fact_blackout_window" not in wire
    assert "planning_goals" not in wire
    assert "knowledge" not in wire


def test_action_endpoint_uses_existing_engine_and_persists_result(tmp_path: Path) -> None:
    client, db_path = make_client(tmp_path)
    session_id = create_session(client)

    response = client.post(
        f"/sessions/{session_id}/actions",
        json={"text": "take brass key"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["accepted"] is True
    assert any(item["name"] == "brass key" for item in body["state"]["inventory"])

    store = SQLiteStore(db_path)
    state = store.load_state(session_id)
    assert "item_brass_key" in state.player().state.inventory
    assert len(store.load_events(session_id)) > 0
    assert len(store.list_turns(session_id)) == 1
    assert GameEngine(store).replay_session(session_id) == state


def test_history_is_bounded_player_facing_projection(tmp_path: Path) -> None:
    client, _ = make_client(tmp_path)
    session_id = create_session(client)
    client.post(f"/sessions/{session_id}/actions", json={"text": "wait 1"})
    client.post(f"/sessions/{session_id}/actions", json={"text": "move nowhere"})

    response = client.get(f"/sessions/{session_id}/history?limit=10")

    assert response.status_code == 200
    turns = response.json()["turns"]
    assert len(turns) == 2
    assert set(turns[0]) == {
        "turn_number",
        "raw_input",
        "accepted",
        "reason",
        "narration",
        "location_id",
    }
    assert "involved_entities" not in response.text
    assert "tags" not in response.text


def test_unknown_session_and_invalid_body_do_not_create_turns(tmp_path: Path) -> None:
    client, db_path = make_client(tmp_path)
    session_id = create_session(client)

    missing = client.post("/sessions/does-not-exist/actions", json={"text": "wait 1"})
    invalid = client.post(f"/sessions/{session_id}/actions", json={"text": ""})

    assert missing.status_code == 404
    assert invalid.status_code == 422
    assert SQLiteStore(db_path).list_turns(session_id) == []


def test_provider_failure_is_http_502_and_remains_transactionally_atomic(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "provider.db"
    client = TestClient(
        create_app(
            db_path,
            narrative_provider=NarrativeProviderName.OPENAI_COMPATIBLE,
            env={
                "EMERGENT_RPG_LLM_BASE_URL": "http://provider.invalid/v1",
                "EMERGENT_RPG_LLM_MODEL": "test-model",
            },
            transport=FailingTransport(),
        )
    )
    session_id = create_session(client)
    store = SQLiteStore(db_path)
    before = store.load_state(session_id)

    response = client.post(
        f"/sessions/{session_id}/actions",
        json={"text": "take brass key"},
    )

    assert response.status_code == 502
    assert "simulated API provider outage" in response.json()["detail"]
    assert store.load_state(session_id) == before
    assert store.load_events(session_id) == []
    assert store.list_turns(session_id) == []


def test_health_endpoint_is_side_effect_free(tmp_path: Path) -> None:
    client, db_path = make_client(tmp_path)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert SQLiteStore(db_path).latest_session_id() is None
