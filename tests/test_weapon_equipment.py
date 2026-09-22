from __future__ import annotations

from pathlib import Path

import pytest

from emergent_rpg.domain.actions import AttackAction, EquipAction
from emergent_rpg.domain.events import (
    CharacterDamaged,
    CharacterStaminaSpent,
    PlayerItemGiven,
    WeaponEquipmentChanged,
)
from emergent_rpg.domain.models import GameSession, NPC, WorldState
from emergent_rpg.engine.combat import CombatPolicy
from emergent_rpg.engine.narrative import ScenePlan
from emergent_rpg.engine.reducer import ReductionError, apply_event
from emergent_rpg.engine.resolver import DeterministicResolver
from emergent_rpg.engine.service import GameEngine
from emergent_rpg.persistence.db import SQLiteStore
from emergent_rpg.providers.base import NarrativeGenerator
from emergent_rpg.providers.errors import ProviderRequestError
from emergent_rpg.providers.scripted import DeterministicActionParser
from emergent_rpg.validation.validator import validate_event_preconditions, validate_state
from emergent_rpg.world.demo import build_demo_world


class FailingNarrativeGenerator(NarrativeGenerator):
    def generate(self, scene_plan: ScenePlan) -> str:
        del scene_plan
        raise ProviderRequestError("simulated equipment narration outage")


def _lio(state: WorldState) -> NPC:
    entity = state.entities["npc_lio"]
    assert isinstance(entity, NPC)
    return entity


def _owned_wrench_state() -> WorldState:
    state = build_demo_world()
    wrench = state.items["item_relay_wrench"]
    wrench.location_id = None
    wrench.owner_id = state.player_id
    state.player().state.inventory.append(wrench.id)
    return state


def test_deterministic_parser_supports_equip_and_unequip() -> None:
    parser = DeterministicActionParser()
    state = build_demo_world()

    equip = parser.parse("equip relay wrench", state)
    unequip = parser.parse("unequip", state)

    assert isinstance(equip, EquipAction)
    assert equip.item == "relay wrench"
    assert isinstance(unequip, EquipAction)
    assert unequip.item is None


def test_take_equip_weapon_attack_retaliation_persists_and_replays(
    tmp_path: Path,
) -> None:
    store = SQLiteStore(tmp_path / "weapon-lifecycle.db")
    engine = GameEngine(store)
    session = engine.new_session()

    taken, _, state = engine.process_text(session.id, "take relay wrench")
    assert taken.accepted
    assert state.items["item_relay_wrench"].owner_id == state.player_id
    assert "item_relay_wrench" in state.player().state.inventory

    equipped, _, state = engine.process_text(session.id, "equip relay wrench")
    assert equipped.accepted
    assert state.player().state.equipped_weapon_id == "item_relay_wrench"

    attacked, narration, state = engine.process_text(session.id, "attack Lio Marr")
    assert attacked.accepted
    assert narration
    assert {"combat", "attack", "weapon", "retaliation"} <= attacked.tags

    player_spend = next(
        event
        for event in attacked.emitted_events
        if isinstance(event, CharacterStaminaSpent)
        and event.entity_id == state.player_id
    )
    player_damage = next(
        event
        for event in attacked.emitted_events
        if isinstance(event, CharacterDamaged)
        and event.source_id == state.player_id
    )
    assert player_spend.reason == "weapon_attack"
    assert player_spend.weapon_id == "item_relay_wrench"
    assert player_spend.amount == 4
    assert player_damage.cause == "weapon_attack"
    assert player_damage.weapon_id == "item_relay_wrench"
    assert player_damage.amount == 4
    assert player_damage.stamina_cost == 4

    assert state.player().state.stamina == 6
    assert state.player().state.health == 8
    assert _lio(state).state.health == 6
    assert _lio(state).state.stamina == 7
    assert engine.replay_session(session.id) == state


def test_unequip_restores_unarmed_attack_profile() -> None:
    state = _owned_wrench_state()
    equipped = apply_event(
        state,
        WeaponEquipmentChanged(
            turn_number=1,
            entity_id=state.player_id,
            from_item_id=None,
            to_item_id="item_relay_wrench",
        ),
    )

    weapon_result = DeterministicResolver().resolve(
        equipped,
        AttackAction(target="Lio Marr"),
    )
    weapon_damage = next(
        event
        for event in weapon_result.emitted_events
        if isinstance(event, CharacterDamaged)
        and event.source_id == equipped.player_id
    )
    assert weapon_damage.amount == 4
    assert weapon_damage.weapon_id == "item_relay_wrench"

    unequipped = apply_event(
        equipped,
        WeaponEquipmentChanged(
            turn_number=2,
            entity_id=equipped.player_id,
            from_item_id="item_relay_wrench",
            to_item_id=None,
        ),
    )
    unarmed_result = DeterministicResolver().resolve(
        unequipped,
        AttackAction(target="Lio Marr"),
    )
    unarmed_damage = next(
        event
        for event in unarmed_result.emitted_events
        if isinstance(event, CharacterDamaged)
        and event.source_id == unequipped.player_id
    )
    assert unarmed_damage.amount == CombatPolicy.UNARMED_DAMAGE
    assert unarmed_damage.weapon_id is None
    assert unarmed_damage.cause == "unarmed_attack"


def test_forged_equipment_event_fails_precheck_and_reducer() -> None:
    state = build_demo_world()
    forged = WeaponEquipmentChanged(
        turn_number=1,
        entity_id=state.player_id,
        from_item_id=None,
        to_item_id="item_flask",
    )

    report = validate_event_preconditions(state, forged)

    assert not report.valid
    assert "invalid_weapon_equipment" in {issue.code for issue in report.issues}
    with pytest.raises(ReductionError):
        apply_event(state, forged)


def test_direct_equipment_state_mutation_requires_typed_event() -> None:
    before = _owned_wrench_state()
    after = before.model_copy(deep=True)
    after.player().state.equipped_weapon_id = "item_relay_wrench"

    report = validate_state(after, previous=before, transition_events=[])

    assert not report.valid
    assert "weapon_equipment_changed_without_event" in {
        issue.code for issue in report.issues
    }


def test_weapon_damage_must_match_exact_equipment_and_spend_provenance() -> None:
    before = _owned_wrench_state()
    equipped_event = WeaponEquipmentChanged(
        turn_number=1,
        entity_id=before.player_id,
        from_item_id=None,
        to_item_id="item_relay_wrench",
    )
    equipped = apply_event(before, equipped_event)

    result = DeterministicResolver().resolve(
        equipped,
        AttackAction(target="Lio Marr"),
    )
    player_spend = next(
        event
        for event in result.emitted_events
        if isinstance(event, CharacterStaminaSpent)
        and event.entity_id == equipped.player_id
    )
    player_damage = next(
        event
        for event in result.emitted_events
        if isinstance(event, CharacterDamaged)
        and event.source_id == equipped.player_id
    )

    forged_damage = player_damage.model_copy(
        update={
            "weapon_id": None,
            "amount": CombatPolicy.UNARMED_DAMAGE,
        }
    )
    report = validate_event_preconditions(
        apply_event(equipped, player_spend),
        forged_damage,
    )

    assert not report.valid
    assert "invalid_character_damage" in {issue.code for issue in report.issues}


def test_equipped_weapon_cannot_be_transferred_without_unequipping() -> None:
    state = _owned_wrench_state()
    state = apply_event(
        state,
        WeaponEquipmentChanged(
            turn_number=1,
            entity_id=state.player_id,
            from_item_id=None,
            to_item_id="item_relay_wrench",
        ),
    )
    forged_transfer = PlayerItemGiven(
        turn_number=2,
        source_player_id=state.player_id,
        receiver_npc_id="npc_lio",
        item_id="item_relay_wrench",
    )

    with pytest.raises(ReductionError, match="cannot transfer an equipped weapon"):
        apply_event(state, forged_transfer)


def test_provider_failure_keeps_equipment_change_zero_commit(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "weapon-provider.db")
    initial = _owned_wrench_state()
    session = GameSession(
        id="weapon-provider",
        name="Weapon provider atomicity",
        world_pack="ashfall-relay",
        created_at="2026-09-22T00:00:00+00:00",
    )
    store.create_session(session, initial)
    before = store.load_state(session.id)
    engine = GameEngine(store, generator=FailingNarrativeGenerator())

    with pytest.raises(ProviderRequestError, match="equipment narration outage"):
        engine.process_text(session.id, "equip relay wrench")

    assert store.load_state(session.id) == before
    assert store.load_events(session.id) == []
    assert store.list_turns(session.id) == []
