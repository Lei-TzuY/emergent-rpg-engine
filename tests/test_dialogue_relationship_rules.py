from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from emergent_rpg.domain.actions import TalkAction
from emergent_rpg.domain.events import FactDiscovered, RelationshipChanged
from emergent_rpg.domain.models import NPC, DialogueRelationshipRule, GameSession, WorldState
from emergent_rpg.engine.reducer import ReductionError, apply_event
from emergent_rpg.engine.resolver import DeterministicResolver
from emergent_rpg.engine.service import GameEngine
from emergent_rpg.persistence.db import SQLiteStore
from emergent_rpg.world.demo import build_demo_world

DEMO_RULE_ID = "arden_trusts_sabotage_evidence"


def _apply_events(state: WorldState, events) -> WorldState:
    current = state
    for event in events:
        current = apply_event(current, event)
    return current


def _co_locate_player_with(state: WorldState, npc_id: str, location_id: str) -> NPC:
    state.player().state.current_location = location_id
    npc = state.entities[npc_id]
    assert isinstance(npc, NPC)
    npc.state.current_location = location_id
    return npc


def _relationship_events(result) -> list[RelationshipChanged]:
    return [
        event
        for event in result.emitted_events
        if isinstance(event, RelationshipChanged)
    ]


def test_demo_arden_rule_is_canonical_and_one_shot() -> None:
    state = build_demo_world()
    arden = _co_locate_player_with(state, "npc_arden", "operations")
    state.player_known_facts.add("fact_relay_sabotage")
    resolver = DeterministicResolver()

    first = resolver.resolve(state, TalkAction(target=arden.name))
    relationship_events = _relationship_events(first)

    assert len(relationship_events) == 1
    assert relationship_events[0].rule_id == DEMO_RULE_ID
    assert relationship_events[0].delta == 5
    assert "earned a little trust" in first.observations[-1]

    after_first = _apply_events(state, first.emitted_events)
    assert after_first.applied_dialogue_relationship_rule_ids == {DEMO_RULE_ID}
    after_arden = after_first.entities[arden.id]
    assert isinstance(after_arden, NPC)
    assert after_arden.relationships[state.player_id] == 5

    second = resolver.resolve(after_first, TalkAction(target=arden.name))
    assert _relationship_events(second) == []
    after_second = _apply_events(after_first, second.emitted_events)
    after_second_arden = after_second.entities[arden.id]
    assert isinstance(after_second_arden, NPC)
    assert after_second_arden.relationships[state.player_id] == 5


def test_same_dialogue_fact_can_trigger_generic_non_ashfall_rule() -> None:
    state = build_demo_world()
    lio = _co_locate_player_with(state, "npc_lio", "yard")
    state.player_known_facts.clear()
    state.dialogue_relationship_rules = [
        DialogueRelationshipRule(
            id="lio_respects_generator_check",
            speaker_id=lio.id,
            listener_id=state.player_id,
            required_listener_fact_ids={"fact_generator_stable"},
            delta=7,
            observation="Lio nods at your careful reading of the generator evidence.",
        )
    ]

    result = DeterministicResolver().resolve(state, TalkAction(target=lio.name))
    discovered_index = next(
        index
        for index, event in enumerate(result.emitted_events)
        if isinstance(event, FactDiscovered)
        and event.fact_id == "fact_generator_stable"
    )
    relationship_index = next(
        index
        for index, event in enumerate(result.emitted_events)
        if isinstance(event, RelationshipChanged)
    )

    assert discovered_index < relationship_index
    changed = _relationship_events(result)[0]
    assert changed.rule_id == "lio_respects_generator_check"
    assert changed.delta == 7

    after = _apply_events(state, result.emitted_events)
    after_lio = after.entities[lio.id]
    assert isinstance(after_lio, NPC)
    assert "fact_generator_stable" in after.player_known_facts
    assert after_lio.relationships[state.player_id] == 7
    assert "lio_respects_generator_check" in after.applied_dialogue_relationship_rule_ids


def test_dialogue_rule_priority_is_stable_and_one_rule_fires_per_talk() -> None:
    state = build_demo_world()
    lio = _co_locate_player_with(state, "npc_lio", "yard")
    state.dialogue_relationship_rules = [
        DialogueRelationshipRule(
            id="low_priority",
            speaker_id=lio.id,
            listener_id=state.player_id,
            delta=2,
            priority=1,
        ),
        DialogueRelationshipRule(
            id="high_priority",
            speaker_id=lio.id,
            listener_id=state.player_id,
            delta=3,
            priority=10,
        ),
    ]
    resolver = DeterministicResolver()

    first = resolver.resolve(state, TalkAction(target=lio.name))
    assert [event.rule_id for event in _relationship_events(first)] == ["high_priority"]
    after_first = _apply_events(state, first.emitted_events)

    second = resolver.resolve(after_first, TalkAction(target=lio.name))
    assert [event.rule_id for event in _relationship_events(second)] == ["low_priority"]
    after_second = _apply_events(after_first, second.emitted_events)
    after_lio = after_second.entities[lio.id]
    assert isinstance(after_lio, NPC)
    assert after_lio.relationships[state.player_id] == 5


def test_reducer_rejects_forged_rule_delta_and_out_of_order_rule() -> None:
    state = build_demo_world()
    lio = _co_locate_player_with(state, "npc_lio", "yard")
    state.dialogue_relationship_rules = [
        DialogueRelationshipRule(
            id="high_priority",
            speaker_id=lio.id,
            listener_id=state.player_id,
            delta=4,
            priority=10,
        ),
        DialogueRelationshipRule(
            id="low_priority",
            speaker_id=lio.id,
            listener_id=state.player_id,
            delta=2,
            priority=1,
        ),
    ]

    with pytest.raises(ReductionError, match="delta"):
        apply_event(
            state,
            RelationshipChanged(
                turn_number=1,
                source_id=lio.id,
                target_id=state.player_id,
                delta=99,
                rule_id="high_priority",
            ),
        )

    with pytest.raises(ReductionError, match="expected dialogue relationship rule high_priority"):
        apply_event(
            state,
            RelationshipChanged(
                turn_number=1,
                source_id=lio.id,
                target_id=state.player_id,
                delta=2,
                rule_id="low_priority",
            ),
        )


def test_manual_relationship_change_remains_backward_compatible() -> None:
    state = build_demo_world()
    lio = state.entities["npc_lio"]
    assert isinstance(lio, NPC)

    after = apply_event(
        state,
        RelationshipChanged(
            turn_number=1,
            source_id=lio.id,
            target_id=state.player_id,
            delta=6,
        ),
    )

    after_lio = after.entities[lio.id]
    assert isinstance(after_lio, NPC)
    assert after_lio.relationships[state.player_id] == 6
    assert after.applied_dialogue_relationship_rule_ids == set()


def test_world_model_rejects_invalid_dialogue_rule_references() -> None:
    state = build_demo_world()
    payload = state.model_dump(mode="json")
    payload["dialogue_relationship_rules"] = [
        {
            "id": "invalid_rule",
            "speaker_id": "missing_npc",
            "listener_id": state.player_id,
            "required_listener_fact_ids": ["missing_fact"],
            "delta": 5,
        }
    ]

    with pytest.raises(ValidationError):
        WorldState.model_validate(payload)


def test_dialogue_rule_persists_and_replays_without_farming(tmp_path: Path) -> None:
    state = build_demo_world()
    arden = _co_locate_player_with(state, "npc_arden", "operations")
    state.player_known_facts.add("fact_relay_sabotage")
    store = SQLiteStore(tmp_path / "dialogue-rules.db")
    session = GameSession(
        id="dialogue-rules",
        name="Dialogue rules",
        world_pack="ashfall-relay",
        created_at="2026-09-12T00:00:00+00:00",
    )
    store.create_session(session, state)
    engine = GameEngine(store)

    _, _, first_state = engine.execute_action(
        session.id,
        TalkAction(target=arden.name),
        "talk Arden Vale",
    )
    first_arden = first_state.entities[arden.id]
    assert isinstance(first_arden, NPC)
    assert first_arden.relationships[state.player_id] == 5
    assert first_state.applied_dialogue_relationship_rule_ids == {DEMO_RULE_ID}
    assert engine.replay_session(session.id) == first_state

    _, _, second_state = engine.execute_action(
        session.id,
        TalkAction(target=arden.name),
        "talk Arden Vale again",
    )
    second_arden = second_state.entities[arden.id]
    assert isinstance(second_arden, NPC)
    assert second_arden.relationships[state.player_id] == 5
    assert second_state.applied_dialogue_relationship_rule_ids == {DEMO_RULE_ID}
    assert engine.replay_session(session.id) == second_state
