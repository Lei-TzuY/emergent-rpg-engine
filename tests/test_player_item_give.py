from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from emergent_rpg.api.app import create_app
from emergent_rpg.domain.actions import GiveAction
from emergent_rpg.domain.events import NPCGoalCompleted, PlayerItemGiven
from emergent_rpg.domain.models import NPC, NPCGoal, WorldState
from emergent_rpg.engine.reducer import ReductionError, apply_event
from emergent_rpg.engine.resolver import DeterministicResolver
from emergent_rpg.engine.service import GameEngine
from emergent_rpg.persistence.db import SQLiteStore
from emergent_rpg.providers.openai_compatible import (
    OpenAICompatibleActionParser,
    OpenAICompatibleConfig,
)
from emergent_rpg.providers.scripted import DeterministicActionParser
from emergent_rpg.world.demo import build_demo_world


class RecordingTransport:
    def __init__(self, content: str) -> None:
        self.content = content
        self.payload: dict[str, object] | None = None

    def post_json(
        self,
        url: str,
        headers: Mapping[str, str],
        payload: Mapping[str, object],
        timeout: float,
    ) -> dict[str, object]:
        del url, headers, timeout
        self.payload = dict(payload)
        return {"choices": [{"message": {"content": self.content}}]}


def _player_owns_key(state: WorldState) -> None:
    item = state.items["item_brass_key"]
    item.location_id = None
    item.owner_id = state.player_id
    if item.id not in state.player().state.inventory:
        state.player().state.inventory.append(item.id)


def test_deterministic_parser_parses_multiword_give_command() -> None:
    parser = DeterministicActionParser()

    action = parser.parse('give "brass key" to "Lio Marr"', build_demo_world())

    assert action == GiveAction(item="brass key", receiver="Lio Marr")


def test_structured_provider_can_propose_give_without_hidden_state() -> None:
    state = build_demo_world()
    _player_owns_key(state)
    transport = RecordingTransport(
        '{"kind":"give","item":"brass key","receiver":"Lio Marr"}'
    )
    parser = OpenAICompatibleActionParser(
        OpenAICompatibleConfig(base_url="http://localhost:11434/v1", model="local-model"),
        transport=transport,
    )

    action = parser.parse("Hand the brass key to Lio.", state)

    assert action == GiveAction(item="brass key", receiver="Lio Marr")
    assert transport.payload is not None
    wire = str(transport.payload)
    assert "brass key" in wire
    assert "Lio Marr" in wire
    assert "planning_goals" not in wire
    assert "knowledge" not in wire


def test_give_requires_owned_portable_item_and_local_active_receiver() -> None:
    state = build_demo_world()
    resolver = DeterministicResolver()

    missing = resolver.resolve(state, GiveAction(item="brass key", receiver="Lio Marr"))
    assert not missing.accepted
    assert missing.emitted_events == []

    _player_owns_key(state)
    remote = resolver.resolve(state, GiveAction(item="brass key", receiver="Arden Vale"))
    assert not remote.accepted
    assert remote.emitted_events == []

    lio = state.entities["npc_lio"]
    assert isinstance(lio, NPC)
    lio.state.conscious = False
    inactive = resolver.resolve(state, GiveAction(item="brass key", receiver="Lio Marr"))
    assert not inactive.accepted
    assert inactive.emitted_events == []

    lio.state.conscious = True
    state.items["item_brass_key"].flags.discard("portable")
    nonportable = resolver.resolve(state, GiveAction(item="brass key", receiver="Lio Marr"))
    assert not nonportable.accepted
    assert nonportable.emitted_events == []


def test_give_can_turn_in_matching_npc_acquisition_goal() -> None:
    state = build_demo_world()
    _player_owns_key(state)
    lio = state.entities["npc_lio"]
    assert isinstance(lio, NPC)
    lio.planning_goals.append(
        NPCGoal(
            id="lio_receive_key",
            kind="acquire_item",
            target_id="item_brass_key",
            priority=200,
        )
    )

    result = DeterministicResolver().resolve(
        state,
        GiveAction(item="brass key", receiver="Lio Marr"),
    )

    assert result.accepted
    assert isinstance(result.emitted_events[0], PlayerItemGiven)
    completions = [
        event for event in result.emitted_events if isinstance(event, NPCGoalCompleted)
    ]
    assert [event.goal_id for event in completions] == ["lio_receive_key"]

    candidate = state
    for event in result.emitted_events:
        candidate = apply_event(candidate, event)
    updated_lio = candidate.entities["npc_lio"]
    assert isinstance(updated_lio, NPC)
    assert candidate.items["item_brass_key"].owner_id == "npc_lio"
    assert "item_brass_key" not in candidate.player().state.inventory
    assert "item_brass_key" in updated_lio.state.inventory
    assert "lio_receive_key" in updated_lio.completed_goal_ids


def test_forged_remote_player_handoff_is_rejected_by_reducer() -> None:
    state = build_demo_world()
    _player_owns_key(state)
    lio = state.entities["npc_lio"]
    assert isinstance(lio, NPC)
    lio.state.current_location = "operations"
    event = PlayerItemGiven(
        turn_number=1,
        source_player_id="player",
        receiver_npc_id="npc_lio",
        item_id="item_brass_key",
    )

    with pytest.raises(ReductionError, match="not co-located"):
        apply_event(state, event)


def test_engine_give_persists_and_replays_exact_custody(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "give.db")
    engine = GameEngine(store)
    session = engine.new_session()

    rejected, _, before_take = engine.process_text(
        session.id,
        "give brass key to Lio Marr",
    )
    assert not rejected.accepted
    assert store.load_events(session.id) == []

    taken, _, _ = engine.process_text(session.id, "take brass key")
    assert taken.accepted
    given, _, state = engine.process_text(session.id, "give brass key to Lio Marr")

    assert given.accepted
    assert any(isinstance(event, PlayerItemGiven) for event in given.emitted_events)
    lio = state.entities["npc_lio"]
    assert isinstance(lio, NPC)
    assert state.items["item_brass_key"].owner_id == "npc_lio"
    assert "item_brass_key" not in state.player().state.inventory
    assert "item_brass_key" in lio.state.inventory
    assert engine.replay_session(session.id) == state


def test_browser_api_raw_text_path_supports_take_then_give(tmp_path: Path) -> None:
    db_path = tmp_path / "api-give.db"
    client = TestClient(create_app(db_path))
    assert client.get("/ui/").status_code == 200
    created = client.post("/sessions", json={"name": "give parity"})
    assert created.status_code == 201
    session_id = str(created.json()["session"]["id"])

    take = client.post(
        f"/sessions/{session_id}/actions",
        json={"text": "take brass key"},
    )
    give = client.post(
        f"/sessions/{session_id}/actions",
        json={"text": "give brass key to Lio Marr"},
    )

    assert take.status_code == 200
    assert take.json()["accepted"] is True
    assert give.status_code == 200
    assert give.json()["accepted"] is True
    assert all(item["name"] != "brass key" for item in give.json()["state"]["inventory"])

    store = SQLiteStore(db_path)
    state = store.load_state(session_id)
    lio = state.entities["npc_lio"]
    assert isinstance(lio, NPC)
    assert state.items["item_brass_key"].owner_id == "npc_lio"
    assert "item_brass_key" in lio.state.inventory
    assert GameEngine(store).replay_session(session_id) == state
