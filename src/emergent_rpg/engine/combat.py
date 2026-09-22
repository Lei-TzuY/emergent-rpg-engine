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

    @classmethod
    def validate_stamina_spend_event(
        cls,
        state: WorldState,
        event: CharacterStaminaSpent,
    ) -> str | None:
        source = state.entities.get(event.entity_id)
        if source is None:
            return f"stamina source {event.entity_id} does not exist"
        if source.id != state.player_id:
            return "unarmed stamina spend must belong to the canonical player"
        if not source.state.alive or not source.state.conscious:
            return "unarmed stamina spend source must be alive and conscious"
        if event.reason != "unarmed_attack":
            return f"unsupported stamina spend reason {event.reason}"
        if event.amount != cls.UNARMED_STAMINA_COST:
            return f"unarmed stamina spend must equal {cls.UNARMED_STAMINA_COST}"
        if source.state.stamina < event.amount:
            return "insufficient stamina for unarmed attack"

        target = state.entities.get(event.target_id)
        if not isinstance(target, NPC):
            return "unarmed stamina spend target must be an NPC"
        if target.id == source.id:
            return "unarmed stamina spend source and target must differ"
        if not target.state.alive or not target.state.conscious:
            return "unarmed stamina spend target must be alive and conscious"
        if target.state.current_location != source.state.current_location:
            return "unarmed stamina spend participants must be co-located"
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
            return None

        if event.cause != "unarmed_attack":
            return f"unsupported damage cause {event.cause}"
        if event.source_id is None:
            return "unarmed attack damage requires source provenance"
        source = state.entities.get(event.source_id)
        if source is None:
            return f"damage source {event.source_id} does not exist"
        if source.id != state.player_id:
            return "unarmed attack source must be the canonical player"
        if source.id == target.id:
            return "unarmed attack source and target must differ"
        if not source.state.alive or not source.state.conscious:
            return "unarmed attack source must be alive and conscious"
        if not target.state.alive or not target.state.conscious:
            return "unarmed attack target must be alive and conscious"
        if source.state.current_location != target.state.current_location:
            return "unarmed attack participants must be co-located"
        if event.amount != cls.UNARMED_DAMAGE:
            return f"unarmed attack damage must equal {cls.UNARMED_DAMAGE}"
        if source.state.stamina > cls.MAX_STAMINA - cls.UNARMED_STAMINA_COST:
            return "unarmed attack damage requires prior stamina spend provenance"
        return None
