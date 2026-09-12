from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from emergent_rpg.domain.actions import GiveAction
from emergent_rpg.domain.events import (
    FactDiscovered,
    NPCGoalCompleted,
    PlayerItemGiven,
    RelationshipChanged,
)
from emergent_rpg.domain.models import (
    GameSession,
    ItemTurnInConsequenceRule,
    NPC,
    NPCGoal,
    WorldState,
)
from emergent_rpg.engine.narrative import ScenePlan
from emergent_rpg.engine.reducer import ReductionError, apply_event, replay
from emergent_rpg.engine.resolver import DeterministicResolver
from emergent_rpg.engine.service import GameEngine
from emergent_rpg.persistence.db import SQLiteStore
from emergent_rpg.providers.base import NarrativeGenerator
from emergent_rpg.providers.errors import ProviderRequestError
from emergent_rpg.world.demo import build_demo_world


class FailingNarrativeGenerator(NarrativeGenerator):
    def generate(self, scene_plan: ScenePlan) -> str:
        del scene_plan
        raise ProviderRequestError("simulated outage during item turn-in")


def _player_owns_key(state: WorldState) -> None:
    item = state.items["item_brass_key"]
    item.location_id = None
    item.owner_id = state.player_id
    if item.id not in state.player().state.inventory:
        state.player().state.inventory.append(item.id)


def _lio(state: WorldState) -> NPC:
    npc = state.entities["npc_lio"]
    assert isinstance(npc, NPC)
    return npc


def _rule(
    rule_id: str,
    *,
    priority: int = 0,
    required_goal_id: str | None = None,
    required_player_fact_ids: set[str] | None = None,
    required_receiver_fact_ids: set[str] | None = None,
    relationship_delta: int = 7,
    reward_fact_id: str | None = None,
) -> ItemTurnInConsequenceRule:
    return ItemTurnInConsequenceRule(
        id=rule_id,
        receiver_npc_id="npc_lio",
        item_id="item_brass_key",
        required_goal_id=required_goal_id,
        required_player_fact_ids=required_player_fact_ids or set(),
        required_receiver_fact_ids=required_receiver_fact_ids or set(),
        relationship_delta=relationship_delta,
        reward_fact_id=reward_fact_id,
        priority=priority,
        observation="Lio acknowledges the completed handoff.",
    )


def _apply_events(state: WorldState, events) -> WorldState:
    candidate = state
    for event in events:
        candidate = apply_event(candidate, event)
    return candidate


def _relationship_events(result) -> list[RelationshipChanged]:
    return [
        event
        for event in result.emitted_events
        if isinstance(event, RelationshipChanged)
    ]


def test_turn_in_rule_emits_fact_then_relationship_reward() -> None:
    state = build_demo_world()
    _player_owns_key(state)
    state.item_turn_in_consequence_rules = [
        _rule(
            "key_reward",
            relationship_delta=10,
            reward_fact_id="fact_generator_stable",
        )
    ]

    result = DeterministicResolver().resolve(
        state,
        GiveAction(item="brass key", receiver="Lio Marr"),
    )

    assert result.accepted
    assert isinstance(result.emitted_events[0], PlayerItemGiven)
    fact_index = next(
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
    assert fact_index < relationship_index

    changed = _relationship_events(result)
    assert len(changed) == 1
    assert changed[0].rule_id == "key_reward"
    assert changed[0].delta == 10
    assert "reward" in result.tags

    candidate = _apply_events(state, result.emitted_events)
    lio = _lio(candidate)
    assert candidate.items["item_brass_key"].owner_id == lio.id
    assert "fact_generator_stable" in candidate.player_known_facts
    assert lio.relationships[state.player_id] == 10
    assert candidate.applied_item_turn_in_consequence_rule_ids == {"key_reward"}
    assert replay(state, result.emitted_events) == candidate


def test_turn_in_rule_priority_and_fact_prerequisites_are_deterministic() -> None:
    state = build_demo_world()
    _player_owns_key(state)
    state.item_turn_in_consequence_rules = [
        _rule(
            "low",
            priority=1,
            relationship_delta=2,
        ),
        _rule(
            "high",
            priority=10,
            required_player_fact_ids={"fact_key_mark"},
            required_receiver_fact_ids={"fact_generator_stable"},
            relationship_delta=9,
        ),
    ]
    resolver = DeterministicResolver()

    low_only = resolver.resolve(
        state,
        GiveAction(item="brass key", receiver="Lio Marr"),
    )
    assert [event.rule_id for event in _relationship_events(low_only)] == ["low"]

    state.player_known_facts.add("fact_key_mark")
    high = resolver.resolve(
        state,
        GiveAction(item="brass key", receiver="Lio Marr"),
    )
    assert [event.rule_id for event in _relationship_events(high)] == ["high"]


def test_turn_in_rule_can_require_goal_completed_by_same_handoff() -> None:
    state = build_demo_world()
    _player_owns_key(state)
    lio = _lio(state)
    lio.planning_goals.append(
        NPCGoal(
            id="lio_receive_key",
            kind="acquire_item",
            target_id="item_brass_key",
            priority=100,
        )
    )
    state.item_turn_in_consequence_rules = [
        _rule(
            "quest_turn_in",
            required_goal_id="lio_receive_key",
            relationship_delta=8,
        )
    ]

    result = DeterministicResolver().resolve(
        state,
        GiveAction(item="brass key", receiver="Lio Marr"),
    )

    goal_index = next(
        index
        for index, event in enumerate(result.emitted_events)
        if isinstance(event, NPCGoalCompleted)
        and event.goal_id == "lio_receive_key"
    )
    relationship_index = next(
        index
        for index, event in enumerate(result.emitted_events)
        if isinstance(event, RelationshipChanged)
    )
    assert goal_index < relationship_index

    candidate = _apply_events(state, result.emitted_events)
    updated_lio = _lio(candidate)
    assert "lio_receive_key" in updated_lio.completed_goal_ids
    assert updated_lio.relationships[state.player_id] == 8
    assert candidate.applied_item_turn_in_consequence_rule_ids == {"quest_turn_in"}


def test_turn_in_reward_is_one_shot_even_if_item_returns_to_player() -> None:
    state = build_demo_world()
    _player_owns_key(state)
    state.item_turn_in_consequence_rules = [_rule("one_shot", relationship_delta=6)]
    resolver = DeterministicResolver()

    first = resolver.resolve(state, GiveAction(item="brass key", receiver="Lio Marr"))
    after_first = _apply_events(state, first.emitted_events)
    lio = _lio(after_first)
    assert lio.relationships[state.player_id] == 6

    item = after_first.items["item_brass_key"]
    lio.state.inventory.remove(item.id)
    after_first.player().state.inventory.append(item.id)
    item.owner_id = after_first.player_id
    item.location_id = None

    second = resolver.resolve(
        after_first,
        GiveAction(item="brass key", receiver="Lio Marr"),
    )
    assert second.accepted
    assert _relationship_events(second) == []
    assert not any(isinstance(event, FactDiscovered) for event in second.emitted_events)

    after_second = _apply_events(after_first, second.emitted_events)
    updated_lio = _lio(after_second)
    assert updated_lio.relationships[state.player_id] == 6
    assert after_second.applied_item_turn_in_consequence_rule_ids == {"one_shot"}


def test_forged_reward_before_receiver_custody_is_rejected() -> None:
    state = build_demo_world()
    _player_owns_key(state)
    state.item_turn_in_consequence_rules = [_rule("custody_gate", relationship_delta=5)]

    forged = RelationshipChanged(
        turn_number=1,
        source_id="npc_lio",
        target_id=state.player_id,
        delta=5,
        rule_id="custody_gate",
    )

    with pytest.raises(ReductionError, match="completed receiver custody"):
        apply_event(state, forged)


def test_world_model_rejects_invalid_turn_in_rule_references() -> None:
    state = build_demo_world()
    payload = state.model_dump(mode="json")
    payload["item_turn_in_consequence_rules"] = [
        {
            "id": "bad_rule",
            "receiver_npc_id": "npc_lio",
            "item_id": "missing_item",
            "relationship_delta": 5,
        }
    ]

    with pytest.raises(ValidationError):
        WorldState.model_validate(payload)


def _persist_turn_in_state(
    tmp_path: Path,
    *,
    generator: NarrativeGenerator | None = None,
) -> tuple[GameEngine, str]:
    state = build_demo_world()
    _player_owns_key(state)
    state.item_turn_in_consequence_rules = [
        _rule(
            "persisted_reward",
            relationship_delta=11,
            reward_fact_id="fact_generator_stable",
        )
    ]
    store = SQLiteStore(tmp_path / "turn-in.db")
    session = GameSession(
        id="turn-in-session",
        name="Turn-in rewards",
        world_pack="test-turn-in",
        created_at="2026-09-12T00:00:00+00:00",
    )
    store.create_session(session, state)
    return GameEngine(store, generator=generator), session.id


def test_turn_in_reward_persists_and_replays_exactly(tmp_path: Path) -> None:
    engine, session_id = _persist_turn_in_state(tmp_path)

    result, _, state = engine.process_text(session_id, "give brass key to Lio Marr")

    assert result.accepted
    lio = _lio(state)
    assert state.items["item_brass_key"].owner_id == lio.id
    assert lio.relationships[state.player_id] == 11
    assert "fact_generator_stable" in state.player_known_facts
    assert state.applied_item_turn_in_consequence_rule_ids == {"persisted_reward"}
    assert engine.replay_session(session_id) == state


def test_provider_failure_keeps_handoff_and_reward_zero_commit(tmp_path: Path) -> None:
    engine, session_id = _persist_turn_in_state(
        tmp_path,
        generator=FailingNarrativeGenerator(),
    )
    before = engine.store.load_state(session_id)
    before_events = engine.store.load_events(session_id)

    with pytest.raises(ProviderRequestError, match="item turn-in"):
        engine.process_text(session_id, "give brass key to Lio Marr")

    after = engine.store.load_state(session_id)
    assert after == before
    assert engine.store.load_events(session_id) == before_events
    assert after.items["item_brass_key"].owner_id == after.player_id
    assert "fact_generator_stable" not in after.player_known_facts
    lio = _lio(after)
    assert lio.relationships.get(after.player_id, 0) == 0
    assert after.applied_item_turn_in_consequence_rule_ids == set()
