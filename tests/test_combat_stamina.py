from __future__ import annotations

from pathlib import Path

import pytest

from emergent_rpg.cli.app import _render_state
from emergent_rpg.domain.actions import AttackAction, WaitAction
from emergent_rpg.domain.events import (
    CharacterDamaged,
    CharacterStaminaRecovered,
    CharacterStaminaSpent,
    TimeAdvanced,
    parse_event,
)
from emergent_rpg.domain.models import NPC, WorldState
from emergent_rpg.engine.combat import CombatPolicy
from emergent_rpg.engine.reducer import ReductionError, apply_event
from emergent_rpg.engine.resolver import DeterministicResolver
from emergent_rpg.engine.service import GameEngine
from emergent_rpg.persistence.db import SQLiteStore
from emergent_rpg.validation.validator import validate_event_preconditions, validate_state
from emergent_rpg.world.demo import build_demo_world


def _lio(state: WorldState) -> NPC:
    entity = state.entities["npc_lio"]
    assert isinstance(entity, NPC)
    return entity


def _apply_all(state: WorldState, events: list[object]) -> WorldState:
    current = state
    for event in events:
        current = apply_event(current, event)  # type: ignore[arg-type]
    return current


def test_attack_emits_spend_damage_and_combat_time_as_one_valid_transition() -> None:
    before = build_demo_world()
    result = DeterministicResolver().resolve(
        before,
        AttackAction(target="Lio Marr"),
    )

    assert result.accepted
    assert [event.type for event in result.emitted_events] == [
        "character_stamina_spent",
        "character_damaged",
        "time_advanced",
    ]
    spend = result.emitted_events[0]
    damage = result.emitted_events[1]
    advance = result.emitted_events[2]
    assert isinstance(spend, CharacterStaminaSpent)
    assert isinstance(damage, CharacterDamaged)
    assert isinstance(advance, TimeAdvanced)
    assert spend.entity_id == before.player_id
    assert spend.target_id == "npc_lio"
    assert spend.amount == CombatPolicy.UNARMED_STAMINA_COST
    assert damage.entity_id == spend.target_id
    assert damage.source_id == spend.entity_id
    assert damage.stamina_spend_event_id == spend.event_id
    assert damage.stamina_cost == spend.amount
    assert advance.cause == "combat"
    assert advance.minutes == CombatPolicy.UNARMED_MINUTES

    after = _apply_all(before, result.emitted_events)

    assert after.player().state.stamina == (
        CombatPolicy.MAX_STAMINA - CombatPolicy.UNARMED_STAMINA_COST
    )
    assert _lio(after).state.health == 10 - CombatPolicy.UNARMED_DAMAGE
    assert validate_state(after, previous=before, transition_events=result.emitted_events).valid


def test_insufficient_stamina_rejects_attack_without_material_events() -> None:
    state = build_demo_world()
    state.player().state.stamina = CombatPolicy.UNARMED_STAMINA_COST - 1

    result = DeterministicResolver().resolve(
        state,
        AttackAction(target="Lio Marr"),
    )

    assert not result.accepted
    assert "enough stamina" in (result.reason or "")
    assert result.emitted_events == []


def test_engine_requires_recovery_before_additional_attacks_and_replays(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "stamina-loop.db")
    engine = GameEngine(store)
    session = engine.new_session()

    state = store.load_state(session.id)
    for _ in range(3):
        result, _, state = engine.process_text(session.id, "attack Lio Marr")
        assert result.accepted

    assert state.player().state.stamina == 1
    assert _lio(state).state.health == 4
    before_rejected = state.model_copy(deep=True)

    rejected, _, state = engine.process_text(session.id, "attack Lio Marr")
    assert not rejected.accepted
    assert rejected.emitted_events == []
    assert state == before_rejected

    waited, _, state = engine.process_text(session.id, "wait 2")
    assert waited.accepted
    assert state.player().state.stamina == 3

    attacked, _, state = engine.process_text(session.id, "attack Lio Marr")
    assert attacked.accepted
    assert state.player().state.stamina == 0
    assert _lio(state).state.health == 2
    assert engine.replay_session(session.id) == state


def test_wait_recovery_is_bounded_by_minutes_and_maximum_stamina() -> None:
    state = build_demo_world()
    state.player().state.stamina = 5
    result = DeterministicResolver().resolve(state, WaitAction(minutes=3))

    recovery = next(
        event
        for event in result.emitted_events
        if isinstance(event, CharacterStaminaRecovered)
    )
    advance = next(
        event for event in result.emitted_events if isinstance(event, TimeAdvanced)
    )
    assert recovery.amount == 3
    assert recovery.wait_minutes == 3
    assert advance.cause == "wait"
    assert advance.minutes == 3

    after = _apply_all(state, result.emitted_events)
    assert after.player().state.stamina == 8
    assert validate_state(after, previous=state, transition_events=result.emitted_events).valid

    capped = build_demo_world()
    capped.player().state.stamina = 9
    capped_result = DeterministicResolver().resolve(capped, WaitAction(minutes=20))
    capped_recovery = next(
        event
        for event in capped_result.emitted_events
        if isinstance(event, CharacterStaminaRecovered)
    )
    assert capped_recovery.amount == 1

    full = build_demo_world()
    full_result = DeterministicResolver().resolve(full, WaitAction(minutes=20))
    assert not any(
        isinstance(event, CharacterStaminaRecovered)
        for event in full_result.emitted_events
    )


def test_forged_stamina_events_fail_closed_in_validator_and_reducer() -> None:
    state = build_demo_world()
    state.player().state.stamina = 2
    overspend = CharacterStaminaSpent(
        turn_number=1,
        entity_id=state.player_id,
        amount=CombatPolicy.UNARMED_STAMINA_COST,
        reason="unarmed_attack",
        target_id="npc_lio",
    )
    report = validate_event_preconditions(state, overspend)
    assert not report.valid
    assert "insufficient stamina" in str(report.issues)
    with pytest.raises(ReductionError, match="insufficient stamina"):
        apply_event(state, overspend)

    state = build_demo_world()
    wrong_amount = CharacterStaminaSpent(
        turn_number=1,
        entity_id=state.player_id,
        amount=1,
        reason="unarmed_attack",
        target_id="npc_lio",
    )
    wrong_report = validate_event_preconditions(state, wrong_amount)
    assert not wrong_report.valid
    assert "must equal" in str(wrong_report.issues)

    dax = state.entities["npc_dax"]
    assert isinstance(dax, NPC)
    dax.state.current_location = "yard"
    wrong_actor = CharacterStaminaSpent(
        turn_number=1,
        entity_id=dax.id,
        amount=CombatPolicy.UNARMED_STAMINA_COST,
        reason="unarmed_attack",
        target_id="npc_lio",
    )
    actor_report = validate_event_preconditions(state, wrong_actor)
    assert not actor_report.valid
    assert "canonical player" in str(actor_report.issues)

    recovery_state = build_demo_world()
    recovery_state.player().state.stamina = 5
    forged_recovery = CharacterStaminaRecovered(
        turn_number=1,
        entity_id=recovery_state.player_id,
        amount=2,
        reason="wait",
        wait_minutes=1,
    )
    recovery_report = validate_event_preconditions(recovery_state, forged_recovery)
    assert not recovery_report.valid
    assert "must equal 1" in str(recovery_report.issues)
    with pytest.raises(ReductionError, match="must equal 1"):
        apply_event(recovery_state, forged_recovery)


def test_transition_validator_requires_attack_spend_damage_pairing() -> None:
    before = build_demo_world()
    before.player().state.stamina = CombatPolicy.MAX_STAMINA - CombatPolicy.UNARMED_STAMINA_COST
    damage = CharacterDamaged(
        turn_number=1,
        entity_id="npc_lio",
        source_id=before.player_id,
        cause="unarmed_attack",
        amount=CombatPolicy.UNARMED_DAMAGE,
        stamina_spend_event_id="missing-spend",
        stamina_cost=CombatPolicy.UNARMED_STAMINA_COST,
    )
    advance = TimeAdvanced(
        turn_number=1,
        minutes=CombatPolicy.UNARMED_MINUTES,
        cause="combat",
    )
    after = _apply_all(before, [damage, advance])

    report = validate_state(after, previous=before, transition_events=[damage, advance])

    assert not report.valid
    assert "combat_damage_without_stamina_spend" in {
        issue.code for issue in report.issues
    }

    spend_before = build_demo_world()
    spend = CharacterStaminaSpent(
        turn_number=1,
        entity_id=spend_before.player_id,
        amount=CombatPolicy.UNARMED_STAMINA_COST,
        reason="unarmed_attack",
        target_id="npc_lio",
    )
    spend_after = apply_event(spend_before, spend)
    spend_report = validate_state(
        spend_after,
        previous=spend_before,
        transition_events=[spend],
    )
    assert not spend_report.valid
    assert "stamina spend lacks matching damage provenance" in str(spend_report.issues)


def test_transition_validator_requires_wait_provenance_for_recovery() -> None:
    before = build_demo_world()
    before.player().state.stamina = 5
    recovery = CharacterStaminaRecovered(
        turn_number=1,
        entity_id=before.player_id,
        amount=1,
        reason="wait",
        wait_minutes=1,
    )
    after = apply_event(before, recovery)

    report = validate_state(after, previous=before, transition_events=[recovery])

    assert not report.valid
    assert "stamina recovery does not match wait time provenance" in str(report.issues)


def test_direct_stamina_mutation_requires_typed_event_provenance() -> None:
    before = build_demo_world()
    after = before.model_copy(deep=True)
    after.player().state.stamina = 1

    report = validate_state(after, previous=before, transition_events=[])

    assert not report.valid
    assert "character stamina does not match spend/recovery event provenance" in str(
        report.issues
    )


def test_milestone35_unarmed_damage_without_stamina_marker_still_replays() -> None:
    state = build_demo_world()
    event = parse_event(
        {
            "type": "character_damaged",
            "turn_number": 1,
            "entity_id": "npc_lio",
            "amount": CombatPolicy.UNARMED_DAMAGE,
            "source_id": state.player_id,
            "cause": "unarmed_attack",
        }
    )

    assert isinstance(event, CharacterDamaged)
    assert event.stamina_spend_event_id is None
    assert event.stamina_cost is None
    assert validate_event_preconditions(state, event).valid

    after = apply_event(state, event)

    assert _lio(after).state.health == 10 - CombatPolicy.UNARMED_DAMAGE
    assert after.player().state.stamina == CombatPolicy.MAX_STAMINA


def test_legacy_time_advanced_shape_defaults_to_other_cause() -> None:
    event = parse_event(
        {
            "type": "time_advanced",
            "turn_number": 1,
            "minutes": 2,
        }
    )

    assert isinstance(event, TimeAdvanced)
    assert event.cause == "other"


def test_cli_state_renders_player_combat_resources() -> None:
    state = build_demo_world()
    state.player().state.health = 8
    state.player().state.stamina = 4

    rendered = _render_state(state)

    assert "Health: 8/10 | Stamina: 4/10" in rendered
