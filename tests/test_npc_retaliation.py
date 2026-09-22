from __future__ import annotations

from pathlib import Path

from emergent_rpg.domain.actions import AttackAction
from emergent_rpg.domain.events import (
    CharacterDamaged,
    CharacterStaminaSpent,
    Event,
    TimeAdvanced,
)
from emergent_rpg.domain.models import GameSession, NPC, StatusCondition, WorldState
from emergent_rpg.engine.combat import CombatPolicy
from emergent_rpg.engine.reducer import apply_event
from emergent_rpg.engine.resolver import DeterministicResolver
from emergent_rpg.engine.service import GameEngine
from emergent_rpg.persistence.db import SQLiteStore
from emergent_rpg.validation.validator import validate_state
from emergent_rpg.world.demo import build_demo_world


def _lio(state: WorldState) -> NPC:
    entity = state.entities["npc_lio"]
    assert isinstance(entity, NPC)
    return entity


def _apply_all(state: WorldState, events: list[Event]) -> WorldState:
    current = state
    for event in events:
        current = apply_event(current, event)
    return current


def _combat_events(events: list[Event]) -> list[Event]:
    return [
        event
        for event in events
        if isinstance(event, (CharacterStaminaSpent, CharacterDamaged, TimeAdvanced))
    ]


def test_resolver_emits_exact_single_retaliation_chain() -> None:
    before = build_demo_world()

    result = DeterministicResolver().resolve(
        before,
        AttackAction(target="Lio Marr"),
    )

    assert result.accepted
    combat_events = _combat_events(result.emitted_events)
    assert [event.type for event in combat_events] == [
        "character_stamina_spent",
        "character_damaged",
        "time_advanced",
        "character_stamina_spent",
        "character_damaged",
        "time_advanced",
    ]

    player_spend = combat_events[0]
    player_damage = combat_events[1]
    retaliation_spend = combat_events[3]
    retaliation_damage = combat_events[4]
    assert isinstance(player_spend, CharacterStaminaSpent)
    assert isinstance(player_damage, CharacterDamaged)
    assert isinstance(retaliation_spend, CharacterStaminaSpent)
    assert isinstance(retaliation_damage, CharacterDamaged)

    assert player_spend.entity_id == before.player_id
    assert player_spend.target_id == "npc_lio"
    assert player_spend.reason == "unarmed_attack"
    assert player_spend.trigger_damage_event_id is None

    assert player_damage.source_id == before.player_id
    assert player_damage.entity_id == "npc_lio"
    assert player_damage.stamina_spend_event_id == player_spend.event_id
    assert player_damage.retaliation_trigger_event_id is None

    assert retaliation_spend.entity_id == "npc_lio"
    assert retaliation_spend.target_id == before.player_id
    assert retaliation_spend.reason == "retaliation"
    assert retaliation_spend.trigger_damage_event_id == player_damage.event_id

    assert retaliation_damage.source_id == "npc_lio"
    assert retaliation_damage.entity_id == before.player_id
    assert retaliation_damage.stamina_spend_event_id == retaliation_spend.event_id
    assert retaliation_damage.retaliation_trigger_event_id == player_damage.event_id
    assert {"combat", "attack", "retaliation"} <= result.tags

    after = _apply_all(before, result.emitted_events)

    assert after.player().state.health == 8
    assert after.player().state.stamina == 7
    assert _lio(after).state.health == 8
    assert _lio(after).state.stamina == 7
    assert validate_state(
        after,
        previous=before,
        transition_events=result.emitted_events,
    ).valid


def test_killed_exhausted_or_incapacitated_target_does_not_retaliate() -> None:
    resolver = DeterministicResolver()

    killed = build_demo_world()
    _lio(killed).state.health = CombatPolicy.UNARMED_DAMAGE
    killed_result = resolver.resolve(killed, AttackAction(target="Lio Marr"))
    assert killed_result.accepted
    assert not any(
        isinstance(event, CharacterStaminaSpent) and event.reason == "retaliation"
        for event in killed_result.emitted_events
    )

    exhausted = build_demo_world()
    _lio(exhausted).state.stamina = CombatPolicy.UNARMED_STAMINA_COST - 1
    exhausted_result = resolver.resolve(exhausted, AttackAction(target="Lio Marr"))
    assert exhausted_result.accepted
    assert not any(
        isinstance(event, CharacterStaminaSpent) and event.reason == "retaliation"
        for event in exhausted_result.emitted_events
    )

    incapacitated = build_demo_world()
    _lio(incapacitated).state.status_conditions.append(
        StatusCondition(
            code="pinned",
            name="Pinned",
            incapacitating=True,
        )
    )
    incapacitated_result = resolver.resolve(
        incapacitated,
        AttackAction(target="Lio Marr"),
    )
    assert incapacitated_result.accepted
    assert not any(
        isinstance(event, CharacterStaminaSpent) and event.reason == "retaliation"
        for event in incapacitated_result.emitted_events
    )


def test_forged_retaliation_without_prior_player_damage_fails_transition() -> None:
    before = build_demo_world()
    spend = CharacterStaminaSpent(
        turn_number=1,
        entity_id="npc_lio",
        amount=CombatPolicy.UNARMED_STAMINA_COST,
        reason="retaliation",
        target_id=before.player_id,
        trigger_damage_event_id="missing-player-damage",
    )
    damage = CharacterDamaged(
        turn_number=1,
        entity_id=before.player_id,
        amount=CombatPolicy.UNARMED_DAMAGE,
        source_id="npc_lio",
        cause="unarmed_attack",
        stamina_spend_event_id=spend.event_id,
        stamina_cost=CombatPolicy.UNARMED_STAMINA_COST,
        retaliation_trigger_event_id="missing-player-damage",
    )
    advance = TimeAdvanced(
        turn_number=1,
        minutes=CombatPolicy.UNARMED_MINUTES,
        cause="combat",
    )
    events: list[Event] = [spend, damage, advance]

    after = _apply_all(before, events)
    report = validate_state(after, previous=before, transition_events=events)

    assert not report.valid
    codes = {issue.code for issue in report.issues}
    assert "retaliation_without_player_attack" in codes
    assert "invalid_retaliation_provenance" in codes


def test_same_player_damage_cannot_trigger_two_retaliations() -> None:
    before = build_demo_world()
    result = DeterministicResolver().resolve(
        before,
        AttackAction(target="Lio Marr"),
    )
    player_damage = next(
        event
        for event in result.emitted_events
        if isinstance(event, CharacterDamaged)
        and event.source_id == before.player_id
    )
    after_first = _apply_all(before, result.emitted_events)

    duplicate_spend = CharacterStaminaSpent(
        turn_number=1,
        entity_id="npc_lio",
        amount=CombatPolicy.UNARMED_STAMINA_COST,
        reason="retaliation",
        target_id=before.player_id,
        trigger_damage_event_id=player_damage.event_id,
    )
    duplicate_damage = CharacterDamaged(
        turn_number=1,
        entity_id=before.player_id,
        amount=CombatPolicy.UNARMED_DAMAGE,
        source_id="npc_lio",
        cause="unarmed_attack",
        stamina_spend_event_id=duplicate_spend.event_id,
        stamina_cost=CombatPolicy.UNARMED_STAMINA_COST,
        retaliation_trigger_event_id=player_damage.event_id,
    )
    duplicate_time = TimeAdvanced(
        turn_number=1,
        minutes=CombatPolicy.UNARMED_MINUTES,
        cause="combat",
    )
    duplicate_events: list[Event] = [
        duplicate_spend,
        duplicate_damage,
        duplicate_time,
    ]
    after_duplicate = _apply_all(after_first, duplicate_events)

    report = validate_state(
        after_duplicate,
        previous=before,
        transition_events=result.emitted_events + duplicate_events,
    )

    assert not report.valid
    assert "duplicate_retaliation" in {issue.code for issue in report.issues}


def test_engine_retaliation_persists_and_replays(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "retaliation.db")
    engine = GameEngine(store)
    session = engine.new_session()

    result, _, state = engine.process_text(session.id, "attack Lio Marr")

    assert result.accepted
    assert "retaliation" in result.tags
    assert state.player().state.health == 8
    assert state.player().state.stamina == 7
    assert _lio(state).state.health == 8
    assert _lio(state).state.stamina == 7
    assert engine.replay_session(session.id) == state


def test_retaliation_can_lethally_transition_player_and_replay(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "lethal-retaliation.db")
    initial = build_demo_world()
    initial.player().state.health = CombatPolicy.UNARMED_DAMAGE
    session = GameSession(
        id="lethal-retaliation",
        name="Lethal retaliation",
        world_pack="ashfall-relay",
        created_at="2026-09-22T00:00:00+00:00",
    )
    store.create_session(session, initial)
    engine = GameEngine(store)

    result, narration, state = engine.process_text(session.id, "attack Lio Marr")

    assert result.accepted
    assert narration
    assert state.player().state.health == 0
    assert not state.player().state.alive
    assert not state.player().state.conscious
    assert _lio(state).state.health == 8
    assert engine.replay_session(session.id) == state
