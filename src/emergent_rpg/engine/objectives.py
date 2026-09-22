from __future__ import annotations

from emergent_rpg.domain.events import (
    PlayerObjectiveActivated,
    PlayerObjectiveCompleted,
    PlayerObjectiveFailed,
)
from emergent_rpg.domain.models import PlayerObjective, WorldState

ObjectiveEvent = PlayerObjectiveActivated | PlayerObjectiveCompleted | PlayerObjectiveFailed


class PlayerObjectivePolicy:
    @staticmethod
    def _player_item_ids(state: WorldState) -> set[str]:
        return set(state.player().state.inventory)

    @staticmethod
    def deadline_reached(state: WorldState, objective: PlayerObjective) -> bool:
        return (
            objective.deadline_absolute_minute is not None
            and state.clock.absolute_minutes >= objective.deadline_absolute_minute
        )

    @classmethod
    def activation_ready(
        cls,
        state: WorldState,
        objective: PlayerObjective,
        *,
        completed_ids: set[str] | None = None,
    ) -> bool:
        completed = (
            completed_ids
            if completed_ids is not None
            else state.completed_player_objective_ids
        )
        return (
            objective.activation_required_fact_ids <= state.player_known_facts
            and objective.activation_required_item_ids <= cls._player_item_ids(state)
            and objective.activation_required_turn_in_rule_ids
            <= state.applied_item_turn_in_consequence_rule_ids
            and objective.activation_required_completed_objective_ids <= completed
        )

    @classmethod
    def completion_ready(
        cls,
        state: WorldState,
        objective: PlayerObjective,
        *,
        completed_ids: set[str] | None = None,
    ) -> bool:
        completed = (
            completed_ids
            if completed_ids is not None
            else state.completed_player_objective_ids
        )
        return (
            objective.completion_required_fact_ids <= state.player_known_facts
            and objective.completion_required_item_ids <= cls._player_item_ids(state)
            and objective.completion_required_turn_in_rule_ids
            <= state.applied_item_turn_in_consequence_rule_ids
            and objective.completion_required_completed_objective_ids <= completed
        )

    @classmethod
    def progression_events(cls, state: WorldState, turn_number: int) -> list[ObjectiveEvent]:
        active = set(state.active_player_objective_ids)
        completed = set(state.completed_player_objective_ids)
        failed = set(state.failed_player_objective_ids)
        events: list[ObjectiveEvent] = []
        objectives = sorted(state.player_objectives, key=lambda objective: objective.id)

        # Each objective can transition at most twice:
        # pending -> active -> complete/failed, or pending -> failed.
        for _ in range(max(1, len(objectives) * 2 + 1)):
            changed = False
            for objective in objectives:
                if objective.id in active or objective.id in completed or objective.id in failed:
                    continue
                if not cls.activation_ready(state, objective, completed_ids=completed):
                    continue
                events.append(
                    PlayerObjectiveActivated(
                        turn_number=turn_number,
                        objective_id=objective.id,
                    )
                )
                active.add(objective.id)
                changed = True

            # Completion deliberately precedes deadline failure. If the same canonical
            # state satisfies both outcomes, earned completion wins deterministically.
            for objective in objectives:
                if objective.id not in active or objective.id in completed or objective.id in failed:
                    continue
                if not cls.completion_ready(state, objective, completed_ids=completed):
                    continue
                events.append(
                    PlayerObjectiveCompleted(
                        turn_number=turn_number,
                        objective_id=objective.id,
                    )
                )
                active.remove(objective.id)
                completed.add(objective.id)
                changed = True

            for objective in objectives:
                if objective.id in completed or objective.id in failed:
                    continue
                if not cls.deadline_reached(state, objective):
                    continue
                if objective.id not in active and cls.activation_ready(
                    state,
                    objective,
                    completed_ids=completed,
                ):
                    # A completion earlier in this pass may have just unlocked this
                    # pending objective. Give activation/completion the next fixed-point
                    # pass before deciding failure.
                    continue
                events.append(
                    PlayerObjectiveFailed(
                        turn_number=turn_number,
                        objective_id=objective.id,
                    )
                )
                active.discard(objective.id)
                failed.add(objective.id)
                changed = True

            if not changed:
                break
        return events

    @classmethod
    def validate_activation_event(
        cls,
        state: WorldState,
        event: PlayerObjectiveActivated,
    ) -> str | None:
        objective = cls.objective_by_id(state, event.objective_id)
        if objective is None:
            return f"unknown player objective {event.objective_id}"
        if event.objective_id in state.active_player_objective_ids:
            return f"player objective {event.objective_id} is already active"
        if event.objective_id in state.completed_player_objective_ids:
            return f"player objective {event.objective_id} is already complete"
        if event.objective_id in state.failed_player_objective_ids:
            return f"player objective {event.objective_id} has already failed"
        if not cls.activation_ready(state, objective):
            return f"player objective {event.objective_id} activation requirements are not met"
        return None

    @classmethod
    def validate_completion_event(
        cls,
        state: WorldState,
        event: PlayerObjectiveCompleted,
    ) -> str | None:
        objective = cls.objective_by_id(state, event.objective_id)
        if objective is None:
            return f"unknown player objective {event.objective_id}"
        if event.objective_id not in state.active_player_objective_ids:
            return f"player objective {event.objective_id} is not active"
        if event.objective_id in state.completed_player_objective_ids:
            return f"player objective {event.objective_id} is already complete"
        if event.objective_id in state.failed_player_objective_ids:
            return f"player objective {event.objective_id} has already failed"
        if not cls.completion_ready(state, objective):
            return f"player objective {event.objective_id} completion requirements are not met"
        return None

    @classmethod
    def validate_failure_event(
        cls,
        state: WorldState,
        event: PlayerObjectiveFailed,
    ) -> str | None:
        objective = cls.objective_by_id(state, event.objective_id)
        if objective is None:
            return f"unknown player objective {event.objective_id}"
        if event.objective_id in state.completed_player_objective_ids:
            return f"player objective {event.objective_id} is already complete"
        if event.objective_id in state.failed_player_objective_ids:
            return f"player objective {event.objective_id} has already failed"
        if objective.deadline_absolute_minute is None:
            return f"player objective {event.objective_id} has no deadline"
        if not cls.deadline_reached(state, objective):
            return f"player objective {event.objective_id} deadline has not been reached"
        if event.objective_id in state.active_player_objective_ids:
            if cls.completion_ready(state, objective):
                return (
                    f"player objective {event.objective_id} completion takes precedence "
                    "over deadline failure"
                )
        elif cls.activation_ready(state, objective):
            return (
                f"player objective {event.objective_id} must resolve activation "
                "before deadline failure"
            )
        return None

    @staticmethod
    def objective_by_id(state: WorldState, objective_id: str) -> PlayerObjective | None:
        return next(
            (objective for objective in state.player_objectives if objective.id == objective_id),
            None,
        )
