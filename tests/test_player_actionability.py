from __future__ import annotations

from pathlib import Path

import pytest

from emergent_rpg.domain.actions import (
    AttackAction,
    EquipAction,
    FreeformAction,
    GiveAction,
    InspectAction,
    MoveAction,
    TakeAction,
    TalkAction,
    WaitAction,
)
from emergent_rpg.domain.events import (
    ItemAcquired,
    PlayerItemGiven,
    PlayerMoved,
    TimeAdvanced,
)
from emergent_rpg.domain.models import GameSession, StatusCondition
from emergent_rpg.engine.reducer import ReductionError, apply_event
from emergent_rpg.engine.resolver import DeterministicResolver
from emergent_rpg.engine.service import GameEngine
from emergent_rpg.persistence.db import SQLiteStore
from emergent_rpg.validation.validator import validate_event_preconditions
from emergent_rpg.world.demo import build_demo_world


def _all_player_actions() -> list[object]:
    return [
        MoveAction(destination="operations"),
        InspectAction(target="room"),
        TalkAction(target="Lio Marr"),
        TakeAction(target="brass key"),
        GiveAction(item="brass key", receiver="Lio Marr"),
        AttackAction(target="Lio Marr"),
        EquipAction(item="relay wrench"),
        WaitAction(minutes=1),
        FreeformAction(text="do something impossible"),
    ]


def test_dead_player_rejects_every_player_action_before_dispatch() -> None:
    state = build_demo_world()
    player = state.player()
    player.state.health = 0
    player.state.alive = False
    player.state.conscious = False
    resolver = DeterministicResolver()

    for action in _all_player_actions():
        result = resolver.resolve(state, action)  # type: ignore[arg-type]
        assert not result.accepted
        assert result.emitted_events == []
        assert "defeated" in (result.reason or "")


def test_unconscious_player_rejects_every_player_action_before_dispatch() -> None:
    state = build_demo_world()
    player = state.player()
    player.state.health = 5
    player.state.alive = True
    player.state.conscious = False
    resolver = DeterministicResolver()

    for action in _all_player_actions():
        result = resolver.resolve(state, action)  # type: ignore[arg-type]
        assert not result.accepted
        assert result.emitted_events == []
        assert "unconscious" in (result.reason or "")


def test_incapacitation_blocks_physical_actions_but_allows_passive_social_actions() -> None:
    state = build_demo_world()
    state.player().state.status_conditions.append(
        StatusCondition(
            code="pinned",
            name="Pinned",
            incapacitating=True,
        )
    )
    resolver = DeterministicResolver()

    physical_actions = [
        MoveAction(destination="operations"),
        TakeAction(target="brass key"),
        GiveAction(item="brass key", receiver="Lio Marr"),
        EquipAction(item="relay wrench"),
        AttackAction(target="Lio Marr"),
    ]
    for action in physical_actions:
        result = resolver.resolve(state, action)
        assert not result.accepted
        assert result.emitted_events == []
        assert "physical actions" in (result.reason or "")

    assert resolver.resolve(state, InspectAction(target="room")).accepted
    assert resolver.resolve(state, TalkAction(target="Lio Marr")).accepted
    assert resolver.resolve(state, WaitAction(minutes=1)).accepted


def test_defeated_player_typed_events_fail_precheck_and_reducer() -> None:
    state = build_demo_world()
    player = state.player()
    player.state.health = 0
    player.state.alive = False
    player.state.conscious = False

    move = PlayerMoved(
        turn_number=1,
        entity_id=state.player_id,
        from_location="yard",
        to_location="operations",
    )
    wait = TimeAdvanced(
        turn_number=1,
        minutes=1,
        cause="wait",
    )

    for event in (move, wait):
        report = validate_event_preconditions(state, event)
        assert not report.valid
        assert "inactive_participant" in {issue.code for issue in report.issues}
        with pytest.raises(ReductionError):
            apply_event(state, event)


def test_incapacitated_player_cannot_take_or_give_through_typed_events() -> None:
    state = build_demo_world()
    state.player().state.status_conditions.append(
        StatusCondition(
            code="pinned",
            name="Pinned",
            incapacitating=True,
        )
    )

    take = ItemAcquired(
        turn_number=1,
        item_id="item_brass_key",
        actor_id=state.player_id,
        from_location="yard",
    )
    take_report = validate_event_preconditions(state, take)
    assert not take_report.valid
    assert "inactive_participant" in {issue.code for issue in take_report.issues}
    with pytest.raises(ReductionError):
        apply_event(state, take)

    key = state.items["item_brass_key"]
    key.location_id = None
    key.owner_id = state.player_id
    state.player().state.inventory.append(key.id)
    give = PlayerItemGiven(
        turn_number=1,
        source_player_id=state.player_id,
        receiver_npc_id="npc_lio",
        item_id=key.id,
    )
    give_report = validate_event_preconditions(state, give)
    assert not give_report.valid
    assert "inactive_participant" in {issue.code for issue in give_report.issues}
    with pytest.raises(ReductionError):
        apply_event(state, give)


def test_lethal_retaliation_persists_defeat_and_future_actions_are_zero_event(
    tmp_path: Path,
) -> None:
    store = SQLiteStore(tmp_path / "defeat-actionability.db")
    initial = build_demo_world()
    initial.player().state.health = 2
    session = GameSession(
        id="defeat-actionability",
        name="Defeat actionability",
        world_pack="ashfall-relay",
        created_at="2026-09-22T00:00:00+00:00",
    )
    store.create_session(session, initial)
    engine = GameEngine(store)

    attack, _, defeated = engine.process_text(session.id, "attack Lio Marr")

    assert attack.accepted
    assert defeated.player().state.health == 0
    assert not defeated.player().state.alive
    assert not defeated.player().state.conscious
    events_after_defeat = list(store.load_events(session.id))

    for command in ("move operations", "inspect room", "talk Lio Marr", "wait 1"):
        rejected, _, state = engine.process_text(session.id, command)
        assert not rejected.accepted
        assert rejected.emitted_events == []
        assert "defeated" in (rejected.reason or "")
        assert state == defeated
        assert store.load_events(session.id) == events_after_defeat

    assert engine.replay_session(session.id) == defeated
