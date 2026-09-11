from __future__ import annotations

from pydantic import BaseModel, Field

from emergent_rpg.domain.models import WorldState


class SimulationSchedule(BaseModel):
    due_absolute_minutes: list[int] = Field(default_factory=list)
    backlog_remaining: bool = False


class DeterministicSimulationScheduler:
    def due_cycles(self, state: WorldState) -> SimulationSchedule:
        simulation = state.simulation
        due: list[int] = []
        cursor = simulation.next_due_absolute_minute
        now = state.clock.absolute_minutes
        while cursor <= now and len(due) < simulation.max_catch_up_cycles:
            due.append(cursor)
            cursor += simulation.cadence_minutes
        return SimulationSchedule(
            due_absolute_minutes=due,
            backlog_remaining=cursor <= now,
        )
