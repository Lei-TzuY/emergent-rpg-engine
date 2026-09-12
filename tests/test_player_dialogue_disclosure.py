from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from emergent_rpg.api.app import create_app
from emergent_rpg.domain.actions import TalkAction
from emergent_rpg.domain.events import FactDiscovered, RelationshipChanged
from emergent_rpg.domain.models import NPC, GameSession
from emergent_rpg.engine.reducer import apply_event
from emergent_rpg.engine.resolver import DeterministicResolver
from emergent_rpg.engine.service import GameEngine
from emergent_rpg.persistence.db import SQLiteStore
from emergent_rpg.world.demo import build_demo_world

RESTRICTED_FACT_ID = "fact_relay_sabotage"
PUBLIC_FACT_ID = "fact_blackout_window"


def _dialogue_state(
    *,
    fact_ids: set[str],
    relationship_score: int = 0,
):
    state = build_demo_world()
    player = state.player()
    player.state.current_location = "operations"
    state.player_known_facts.clear()

    arden = state.entities["npc_arden"]
    assert isinstance(arden, NPC)
    arden.state.current_location = "operations"
    arden.knowledge.facts_known = set(fact_ids)
    arden.relationships[player.id] = relationship_score
    return state, arden


def _discovered_fact_ids(result) -> list[str]:
    return [
        event.fact_id
        for event in result.emitted_events
        if isinstance(event, FactDiscovered)
    ]


def test_neutral_trust_withholds_restricted_fact_without_rejecting_conversation() -> None:
    state, arden = _dialogue_state(fact_ids={RESTRICTED_FACT_ID})
    restricted = state.facts[RESTRICTED_FACT_ID].proposition

    result = DeterministicResolver().resolve(state, TalkAction(target=arden.name))

    assert result.accepted is True
    assert _discovered_fact_ids(result) == []
    assert all(restricted not in observation for observation in result.observations)


def test_dialogue_falls_back_to_public_fact_when_restricted_fact_is_blocked() -> None:
    state, arden = _dialogue_state(
        fact_ids={RESTRICTED_FACT_ID, PUBLIC_FACT_ID},
    )

    result = DeterministicResolver().resolve(state, TalkAction(target=arden.name))

    assert _discovered_fact_ids(result) == [PUBLIC_FACT_ID]
    assert state.facts[PUBLIC_FACT_ID].proposition in result.observations[-1]
    assert state.facts[RESTRICTED_FACT_ID].proposition not in result.observations[-1]


def test_replayable_npc_to_player_relationship_change_unlocks_restricted_fact() -> None:
    state, arden = _dialogue_state(
        fact_ids={RESTRICTED_FACT_ID},
        relationship_score=15,
    )
    resolver = DeterministicResolver()

    blocked = resolver.resolve(state, TalkAction(target=arden.name))
    assert _discovered_fact_ids(blocked) == []

    trusted = apply_event(
        state,
        RelationshipChanged(
            turn_number=1,
            source_id=arden.id,
            target_id=state.player_id,
            delta=5,
        ),
    )
    unlocked = resolver.resolve(trusted, TalkAction(target=arden.name))

    assert _discovered_fact_ids(unlocked) == [RESTRICTED_FACT_ID]


def test_trusted_dialogue_persists_and_replays_through_game_engine(tmp_path: Path) -> None:
    state, arden = _dialogue_state(
        fact_ids={RESTRICTED_FACT_ID},
        relationship_score=20,
    )
    store = SQLiteStore(tmp_path / "dialogue.db")
    session = GameSession(
        id="trusted-dialogue",
        name="Trusted dialogue",
        world_pack="test-dialogue",
        created_at="2026-09-12T00:00:00+00:00",
    )
    store.create_session(session, state)
    engine = GameEngine(store)

    _, _, after = engine.execute_action(
        session.id,
        TalkAction(target=arden.name),
        "talk Arden Vale",
    )

    assert RESTRICTED_FACT_ID in after.player_known_facts
    assert len(store.list_turns(session.id)) == 1
    assert engine.replay_session(session.id) == after


def _create_api_dialogue_session(
    db_path: Path,
    *,
    session_id: str,
    relationship_score: int,
) -> str:
    state, _ = _dialogue_state(
        fact_ids={RESTRICTED_FACT_ID},
        relationship_score=relationship_score,
    )
    store = SQLiteStore(db_path)
    store.create_session(
        GameSession(
            id=session_id,
            name="API dialogue",
            world_pack="test-dialogue",
            created_at="2026-09-12T00:00:00+00:00",
        ),
        state,
    )
    return session_id


def test_api_dialogue_uses_same_disclosure_policy_for_low_and_high_trust(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "api-dialogue.db"
    low_id = _create_api_dialogue_session(
        db_path,
        session_id="api-low-trust",
        relationship_score=0,
    )
    high_id = _create_api_dialogue_session(
        db_path,
        session_id="api-high-trust",
        relationship_score=20,
    )
    client = TestClient(create_app(db_path))
    proposition = build_demo_world().facts[RESTRICTED_FACT_ID].proposition

    low = client.post(f"/sessions/{low_id}/actions", json={"text": "talk Arden Vale"})
    high = client.post(f"/sessions/{high_id}/actions", json={"text": "talk Arden Vale"})

    assert low.status_code == 200
    assert low.json()["accepted"] is True
    assert proposition not in low.text
    assert low.json()["state"]["known_facts"] == []

    assert high.status_code == 200
    assert high.json()["accepted"] is True
    assert high.json()["state"]["known_facts"] == [
        {"id": RESTRICTED_FACT_ID, "proposition": proposition}
    ]

    store = SQLiteStore(db_path)
    assert GameEngine(store).replay_session(low_id) == store.load_state(low_id)
    assert GameEngine(store).replay_session(high_id) == store.load_state(high_id)
