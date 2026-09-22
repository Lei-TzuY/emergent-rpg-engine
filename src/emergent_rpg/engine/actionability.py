from __future__ import annotations

from emergent_rpg.domain.actions import (
    AttackAction,
    EquipAction,
    GiveAction,
    MoveAction,
    PlayerAction,
    TakeAction,
)
from emergent_rpg.domain.models import WorldState


class PlayerActionabilityPolicy:
    """Canonical legality policy for player life/consciousness/actionability."""

    @staticmethod
    def is_incapacitated(state: WorldState) -> bool:
        return any(
            status.incapacitating
            for status in state.player().state.status_conditions
        )

    @classmethod
    def validate_player_state(
        cls,
        state: WorldState,
        *,
        physical: bool,
    ) -> str | None:
        player = state.player()
        if not player.state.alive:
            return "You cannot act after being defeated."
        if not player.state.conscious:
            return "You cannot act while unconscious."
        if physical and cls.is_incapacitated(state):
            return "You cannot perform physical actions while incapacitated."
        return None

    @classmethod
    def validate_action(
        cls,
        state: WorldState,
        action: PlayerAction,
    ) -> str | None:
        physical = isinstance(
            action,
            (MoveAction, TakeAction, GiveAction, EquipAction, AttackAction),
        )
        return cls.validate_player_state(state, physical=physical)
