from __future__ import annotations

from pydantic import BaseModel, Field

from emergent_rpg.domain.models import WorldState


class TraversalCost(BaseModel):
    base_minutes: int = Field(default=5, ge=1)
    extra_minutes: int = Field(default=0, ge=0)
    condition_codes: list[str] = Field(default_factory=list)
    condition_names: list[str] = Field(default_factory=list)

    @property
    def total_minutes(self) -> int:
        return self.base_minutes + self.extra_minutes


class EnvironmentalRules:
    BASE_MOVE_MINUTES = 5

    def traversal_cost(self, state: WorldState, location_id: str) -> TraversalCost:
        location = state.locations[location_id]
        active = sorted(location.active_conditions.values(), key=lambda item: item.code)
        modifiers = [
            condition
            for condition in active
            if condition.traversal is not None and condition.traversal.extra_minutes > 0
        ]
        return TraversalCost(
            base_minutes=self.BASE_MOVE_MINUTES,
            extra_minutes=sum(
                condition.traversal.extra_minutes
                for condition in modifiers
                if condition.traversal is not None
            ),
            condition_codes=[condition.code for condition in modifiers],
            condition_names=[condition.name for condition in modifiers],
        )
