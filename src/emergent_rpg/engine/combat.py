from __future__ import annotations

from emergent_rpg.domain.events import (
    CharacterDamaged,
    CharacterStaminaRecovered,
    CharacterStaminaSpent,
)
from emergent_rpg.domain.models import NPC, WorldState


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
    def _validate_unarmed_participants(
        cls,
        state: WorldState,
        source_id: str,
        target_id: str,
    ) -> str | None:
        source = state.entities.get(source_id)
        target = state.entities.get(target_id)
        if source is None:
            return f"unarmed attack source {source_id} does not exist"
        if target is None:
            return f"unarmed attack target {target_id} does not exist"
        if source.id == target.id:
            return "unarmed attack source and target must differ"
        if not source.state.alive or not source.state.conscious:
            return "unarmed attack source must be alive and conscious"
        if cls._incapacitated(source):
            return "unarmed attack source must not be incapacitated"
        if not target.state.alive or not target.state.conscious:
            return "unarmed attack target must be alive and conscious"
        if source.state.current_location != target.state.current_location:
            return "unarmed attack participants must be co-located"
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
        if not isinstance(npc, NPC):
            return False
        if npc.state.health <= incoming_damage:
            return False
        if not npc.state.alive or not npc.state.conscious:
            return False
        if cls._incapacitated(npc):
            return False
        if npc.state.stamina < cls.UNARMED_STAMINA_COST:
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
        participant_error = cls._validate_unarmed_participants(
            state,
            event.entity_id,
            event.target_id,
        )
        if participant_error is not None:
            return participant_error

        source = state.entities[event.entity_id]
        target = state.entities[event.target_id]
        if event.amount != cls.UNARMED_STAMINA_COST:
            return f"unarmed stamina spend must equal {cls.UNARMED_STAMINA_COST}"
        if source.state.stamina < event.amount:
            return "insufficient stamina for unarmed attack"

        if event.reason == "unarmed_attack":
            if source.id != state.player_id:
                return "player attack stamina spend must belong to the canonical player"
            if not isinstance(target, NPC):
                return "player attack stamina spend target must be an NPC"
            if event.trigger_damage_event_id is not None:
                return "player attack stamina spend cannot carry retaliation trigger"
            return None

        if event.reason == "retaliation":
            if not isinstance(source, NPC):
                return "retaliation stamina spend source must be an NPC"
            if target.id != state.player_id:
                return "retaliation stamina spend target must be the canonical player"
            if event.trigger_damage_event_id is None:
                return "retaliation stamina spend requires trigger damage provenance"
            return None

        return f"unsupported stamina spend reason {event.reason}"

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
            ):
                return "non-unarmed damage cannot carry combat provenance"
            return None

        if event.cause != "unarmed_attack":
            return f"unsupported damage cause {event.cause}"
        if event.source_id is None:
            return "unarmed attack damage requires source provenance"

        participant_error = cls._validate_unarmed_participants(
            state,
            event.source_id,
            event.entity_id,
        )
        if participant_error is not None:
            return participant_error

        source = state.entities[event.source_id]
        target = state.entities[event.entity_id]
        if event.amount != cls.UNARMED_DAMAGE:
            return f"unarmed attack damage must equal {cls.UNARMED_DAMAGE}"

        has_spend_id = event.stamina_spend_event_id is not None
        has_stamina_cost = event.stamina_cost is not None
        if has_spend_id != has_stamina_cost:
            return "unarmed attack stamina provenance is incomplete"

        if not has_spend_id:
            if source.id != state.player_id or not isinstance(target, NPC):
                return "legacy unarmed damage must originate from the canonical player"
            if event.retaliation_trigger_event_id is not None:
                return "legacy unarmed damage cannot carry retaliation provenance"
            return None

        assert event.stamina_cost is not None
        if event.stamina_cost != cls.UNARMED_STAMINA_COST:
            return (
                "unarmed attack stamina cost must equal "
                f"{cls.UNARMED_STAMINA_COST}"
            )
        if source.state.stamina > cls.MAX_STAMINA - event.stamina_cost:
            return "unarmed attack damage requires prior stamina spend provenance"

        if source.id == state.player_id:
            if not isinstance(target, NPC):
                return "player unarmed attack target must be an NPC"
            if event.retaliation_trigger_event_id is not None:
                return "player unarmed damage cannot carry retaliation trigger"
            return None

        if not isinstance(source, NPC):
            return "retaliation damage source must be an NPC"
        if target.id != state.player_id:
            return "retaliation damage target must be the canonical player"
        if event.retaliation_trigger_event_id is None:
            return "retaliation damage requires trigger damage provenance"
        return None
