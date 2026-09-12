from __future__ import annotations

from pydantic import BaseModel, Field

from emergent_rpg.domain.models import LocationCondition, WorldState


class TraversalCost(BaseModel):
    base_minutes: int = Field(default=5, ge=1)
    extra_minutes: int = Field(default=0, ge=0)
    condition_codes: list[str] = Field(default_factory=list)
    condition_names: list[str] = Field(default_factory=list)

    @property
    def total_minutes(self) -> int:
        return self.base_minutes + self.extra_minutes


class RouteAccess(BaseModel):
    allowed: bool = True
    condition_codes: list[str] = Field(default_factory=list)
    condition_names: list[str] = Field(default_factory=list)


class EnvironmentalRules:
    BASE_MOVE_MINUTES = 5

    @staticmethod
    def _active_conditions(state: WorldState, location_id: str) -> list[LocationCondition]:
        return sorted(
            state.locations[location_id].active_conditions.values(),
            key=lambda item: item.code,
        )

    def traversal_cost(self, state: WorldState, location_id: str) -> TraversalCost:
        modifiers = [
            condition
            for condition in self._active_conditions(state, location_id)
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

    def route_access(
        self,
        state: WorldState,
        location_id: str,
        destination_id: str,
    ) -> RouteAccess:
        blockers = [
            condition
            for condition in self._active_conditions(state, location_id)
            if condition.route is not None
            and destination_id in condition.route.blocked_destination_ids
        ]
        return RouteAccess(
            allowed=not blockers,
            condition_codes=[condition.code for condition in blockers],
            condition_names=[condition.name for condition in blockers],
        )

    def accessible_exits(self, state: WorldState, location_id: str) -> dict[str, str]:
        location = state.locations[location_id]
        return {
            alias: destination
            for alias, destination in sorted(location.exits.items())
            if self.route_access(state, location_id, destination).allowed
        }

    def blocked_exits(self, state: WorldState, location_id: str) -> dict[str, RouteAccess]:
        location = state.locations[location_id]
        blocked: dict[str, RouteAccess] = {}
        for alias, destination in sorted(location.exits.items()):
            access = self.route_access(state, location_id, destination)
            if not access.allowed:
                blocked[alias] = access
        return blocked
