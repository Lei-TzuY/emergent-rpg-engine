from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from emergent_rpg.domain.events import (
    CharacterDamaged,
    CharacterStaminaRecovered,
    CharacterStaminaSpent,
    WeaponEquipmentChanged,
)
from emergent_rpg.domain.models import NPC, WorldState


@dataclass(frozen=True)
class AttackProfile:
    damage: int
    stamina_cost: int
    weapon_id: str | None
    cause: Literal["unarmed_attack", "weapon_attack"]


class CombatPolicy:
    MAX_STAMINA = 10
    UNARMED_DAMAGE = 2
    UNARMED_MINUTES = 1
    UNARMED_STAMINA_COST = 3
    WAIT_RECOVERY_PER_MINUTE = 1

    @staticmethod
    def _incapacitated(entity: object) -> bool:
        state = getattr(entity, "state", None)
        if state is None:
            return True
        return any(status.incapacitating for status in state.status_conditions)

    @classmethod
    def attack_profile(
        cls,
        state: WorldState,
        source_id: str,
    ) -> AttackProfile | None:
        source = state.entities.get(source_id)
        if source is None:
            return None
        weapon_id = source.state.equipped_weapon_id
        if weapon_id is None:
            return AttackProfile(
                damage=cls.UNARMED_DAMAGE,
                stamina_cost=cls.UNARMED_STAMINA_COST,
                weapon_id=None,
                cause="unarmed_attack",
            )
        weapon = state.items.get(weapon_id)
        if (
            weapon is None
            or weapon.weapon is None
            or weapon.owner_id != source_id
            or weapon_id not in source.state.inventory
        ):
            return None
        return AttackProfile(
            damage=weapon.weapon.damage,
            stamina_cost=weapon.weapon.stamina_cost,
            weapon_id=weapon_id,
            cause="weapon_attack",
        )

    @classmethod
    def validate_weapon_equipment_event(
        cls,
        state: WorldState,
        event: WeaponEquipmentChanged,
    ) -> str | None:
        entity = state.entities.get(event.entity_id)
        if entity is None:
            return f"equipment actor {event.entity_id} does not exist"
        if not entity.state.alive or not entity.state.conscious:
            return "equipment actor must be alive and conscious"
        if cls._incapacitated(entity):
            return "equipment actor must not be incapacitated"
        if event.from_item_id != entity.state.equipped_weapon_id:
            return "equipment source does not match canonical equipped weapon"
        if event.from_item_id == event.to_item_id:
            return "equipment change must select a different weapon"
        if event.to_item_id is None:
            return None
        item = state.items.get(event.to_item_id)
        if item is None:
            return "equipped weapon item does not exist"
        if item.weapon is None:
            return "equipped item does not have a weapon profile"
        if item.owner_id != entity.id or item.id not in entity.state.inventory:
            return "equipped weapon must be owned by the actor"
        return None

    @classmethod
    def _validate_attack_participants(
        cls,
        state: WorldState,
        source_id: str,
        target_id: str,
    ) -> str | None:
        source = state.entities.get(source_id)
        target = state.entities.get(target_id)
        if source is None:
            return f"attack source {source_id} does not exist"
        if target is None:
            return f"attack target {target_id} does not exist"
        if source.id == target.id:
            return "attack source and target must differ"
        if not source.state.alive or not source.state.conscious:
            return "attack source must be alive and conscious"
        if cls._incapacitated(source):
            return "attack source must not be incapacitated"
        if not target.state.alive or not target.state.conscious:
            return "attack target must be alive and conscious"
        if source.state.current_location != target.state.current_location:
            return "attack participants must be co-located"
        return None

    @classmethod
    def retaliation_eligible_after_player_damage(
        cls,
        state: WorldState,
        npc_id: str,
        incoming_damage: int,
    ) -> bool:
        npc = state.entities.get(npc_id)
        player = state.player()
        profile = cls.attack_profile(state, npc_id)
        if not isinstance(npc, NPC) or profile is None:
            return False
        if npc.state.health <= incoming_damage:
            return False
        if not npc.state.alive or not npc.state.conscious:
            return False
        if cls._incapacitated(npc):
            return False
        if npc.state.stamina < profile.stamina_cost:
            return False
        if not player.state.alive or not player.state.conscious:
            return False
        if cls._incapacitated(player):
            return False
        return npc.state.current_location == player.state.current_location

    @classmethod
    def validate_stamina_spend_event(
        cls,
        state: WorldState,
        event: CharacterStaminaSpent,
    ) -> str | None:
        participant_error = cls._validate_attack_participants(
            state,
            event.entity_id,
            event.target_id,
        )
        if participant_error is not None:
            return participant_error

        source = state.entities[event.entity_id]
        target = state.entities[event.target_id]
        profile = cls.attack_profile(state, source.id)
        if profile is None:
            return "attack source has invalid equipped weapon state"
        if event.weapon_id != profile.weapon_id:
            return "stamina spend weapon does not match canonical equipment"
        if event.amount != profile.stamina_cost:
            return f"attack stamina spend must equal {profile.stamina_cost}"
        if source.state.stamina < event.amount:
            return "insufficient stamina for attack"

        if source.id == state.player_id:
            expected_reason = (
                "weapon_attack" if profile.weapon_id is not None else "unarmed_attack"
            )
            if event.reason != expected_reason:
                return f"player stamina spend reason must be {expected_reason}"
            if not isinstance(target, NPC):
                return "player attack stamina spend target must be an NPC"
            if event.trigger_damage_event_id is not None:
                return "player attack stamina spend cannot carry retaliation trigger"
            return None

        if event.reason != "retaliation":
            return "NPC combat stamina spend must be a retaliation"
        if not isinstance(source, NPC):
            return "retaliation stamina spend source must be an NPC"
        if target.id != state.player_id:
            return "retaliation stamina spend target must be the canonical player"
        if event.trigger_damage_event_id is None:
            return "retaliation stamina spend requires trigger damage provenance"
        return None

    @classmethod
    def expected_wait_recovery(
        cls,
        state: WorldState,
        wait_minutes: int,
    ) -> int:
        player = state.player()
        missing = cls.MAX_STAMINA - player.state.stamina
        return min(missing, wait_minutes * cls.WAIT_RECOVERY_PER_MINUTE)

    @classmethod
    def validate_stamina_recovery_event(
        cls,
        state: WorldState,
        event: CharacterStaminaRecovered,
    ) -> str | None:
        entity = state.entities.get(event.entity_id)
        if entity is None:
            return f"stamina recovery target {event.entity_id} does not exist"
        if entity.id != state.player_id:
            return "wait stamina recovery must target the canonical player"
        if not entity.state.alive or not entity.state.conscious:
            return "wait stamina recovery target must be alive and conscious"
        if event.reason != "wait":
            return f"unsupported stamina recovery reason {event.reason}"

        expected = cls.expected_wait_recovery(state, event.wait_minutes)
        if expected <= 0:
            return "stamina is already full"
        if event.amount != expected:
            return f"wait stamina recovery must equal {expected}"
        return None

    @staticmethod
    def is_attack_damage(event: CharacterDamaged) -> bool:
        return event.cause in {"unarmed_attack", "weapon_attack"}

    @classmethod
    def validate_damage_event(
        cls,
        state: WorldState,
        event: CharacterDamaged,
    ) -> str | None:
        target = state.entities.get(event.entity_id)
        if target is None:
            return f"damage target {event.entity_id} does not exist"

        if event.cause == "other":
            if event.source_id is not None and event.source_id not in state.entities:
                return f"damage source {event.source_id} does not exist"
            if (
                event.stamina_spend_event_id is not None
                or event.stamina_cost is not None
                or event.retaliation_trigger_event_id is not None
                or event.weapon_id is not None
            ):
                return "non-combat damage cannot carry combat provenance"
            return None

        if not cls.is_attack_damage(event):
            return f"unsupported damage cause {event.cause}"
        if event.source_id is None:
            return "attack damage requires source provenance"

        participant_error = cls._validate_attack_participants(
            state,
            event.source_id,
            event.entity_id,
        )
        if participant_error is not None:
            return participant_error

        source = state.entities[event.source_id]
        target = state.entities[event.entity_id]
        has_spend_id = event.stamina_spend_event_id is not None
        has_stamina_cost = event.stamina_cost is not None
        if has_spend_id != has_stamina_cost:
            return "attack stamina provenance is incomplete"

        if not has_spend_id:
            if (
                event.cause != "unarmed_attack"
                or event.weapon_id is not None
                or source.id != state.player_id
                or not isinstance(target, NPC)
            ):
                return "legacy unarmed damage must originate from the canonical player"
            if event.retaliation_trigger_event_id is not None:
                return "legacy unarmed damage cannot carry retaliation provenance"
            if event.amount != cls.UNARMED_DAMAGE:
                return f"unarmed attack damage must equal {cls.UNARMED_DAMAGE}"
            return None

        profile = cls.attack_profile(state, source.id)
        if profile is None:
            return "attack source has invalid equipped weapon state"
        assert event.stamina_cost is not None
        if event.weapon_id != profile.weapon_id:
            return "damage weapon does not match canonical equipment"
        if event.cause != profile.cause:
            return f"damage cause must be {profile.cause}"
        if event.amount != profile.damage:
            return f"attack damage must equal {profile.damage}"
        if event.stamina_cost != profile.stamina_cost:
            return f"attack stamina cost must equal {profile.stamina_cost}"
        if source.state.stamina > cls.MAX_STAMINA - profile.stamina_cost:
            return "attack damage requires prior stamina spend provenance"

        if source.id == state.player_id:
            if not isinstance(target, NPC):
                return "player attack target must be an NPC"
            if event.retaliation_trigger_event_id is not None:
                return "player damage cannot carry retaliation trigger"
            return None

        if not isinstance(source, NPC):
            return "retaliation damage source must be an NPC"
        if target.id != state.player_id:
            return "retaliation damage target must be the canonical player"
        if event.retaliation_trigger_event_id is None:
            return "retaliation damage requires trigger damage provenance"
        return None
