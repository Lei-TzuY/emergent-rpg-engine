from __future__ import annotations

from emergent_rpg.domain.events import CharacterDamaged
from emergent_rpg.domain.models import WorldState


class CombatPolicy:
    UNARMED_DAMAGE = 2
    UNARMED_MINUTES = 1

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
        return None
