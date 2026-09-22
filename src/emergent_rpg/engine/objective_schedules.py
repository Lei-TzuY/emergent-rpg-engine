from __future__ import annotations

from typing import Literal

from emergent_rpg.domain.events import (
    PlayerObjectiveCompleted,
    PlayerObjectiveFailed,
    ScheduledLocationConditionQueued,
)
from emergent_rpg.domain.models import (
    ObjectiveOutcomeScheduledConditionRule,
    WorldState,
)

ObjectiveTerminalEvent = PlayerObjectiveCompleted | PlayerObjectiveFailed
ObjectiveOutcome = Literal["completed", "failed"]


class ObjectiveOutcomeSchedulePolicy:
    @staticmethod
    def outcome_for_event(event: ObjectiveTerminalEvent) -> ObjectiveOutcome:
        if isinstance(event, PlayerObjectiveCompleted):
            return "completed"
        return "failed"

    @staticmethod
    def rule_by_id(
        state: WorldState,
        rule_id: str,
    ) -> ObjectiveOutcomeScheduledConditionRule | None:
        return next(
            (
                rule
                for rule in state.objective_outcome_scheduled_condition_rules
                if rule.id == rule_id
            ),
            None,
        )

    @classmethod
    def _outcome_consumed(
        cls,
        state: WorldState,
        objective_id: str,
        outcome: ObjectiveOutcome,
    ) -> bool:
        return any(
            rule.id in state.applied_objective_outcome_scheduled_condition_rule_ids
            for rule in state.objective_outcome_scheduled_condition_rules
            if rule.objective_id == objective_id and rule.outcome == outcome
        )

    @staticmethod
    def _pending_event_ids(state: WorldState) -> set[str]:
        pending = {
            activation.id
            for activation in state.scheduled_location_conditions
        }
        pending.update(
            activation.expiry_event_id
            for activation in state.scheduled_location_conditions
            if activation.expiry_absolute_minute is not None
        )
        pending.update(
            expiry.id for expiry in state.scheduled_location_condition_expirations
        )
        return pending

    @classmethod
    def _queue_block_reason(
        cls,
        state: WorldState,
        rule: ObjectiveOutcomeScheduledConditionRule,
    ) -> str | None:
        location = state.locations.get(rule.location_id)
        if location is None:
            return "objective outcome schedule location does not exist"

        pending_ids = cls._pending_event_ids(state)
        if rule.scheduled_event_id in pending_ids:
            return "objective outcome scheduled event id is already pending"
        if (
            rule.expires_after_minutes is not None
            and f"{rule.scheduled_event_id}:expiry" in pending_ids
        ):
            return "objective outcome scheduled expiry id is already pending"

        if rule.condition.code in location.active_conditions:
            return "objective outcome schedule condition is already active"
        if any(
            activation.location_id == rule.location_id
            and activation.condition.code == rule.condition.code
            for activation in state.scheduled_location_conditions
        ):
            return "objective outcome schedule target is already pending"

        if rule.condition.route is not None:
            invalid_targets = (
                rule.condition.route.blocked_destination_ids
                - set(location.exits.values())
            )
            if invalid_targets:
                return "objective outcome schedule blocks non-local exits"
        return None

    @classmethod
    def eligible_rules(
        cls,
        state: WorldState,
        objective_id: str,
        outcome: ObjectiveOutcome,
    ) -> list[ObjectiveOutcomeScheduledConditionRule]:
        if cls._outcome_consumed(state, objective_id, outcome):
            return []
        eligible = [
            rule
            for rule in state.objective_outcome_scheduled_condition_rules
            if rule.objective_id == objective_id
            and rule.outcome == outcome
            and rule.id not in state.applied_objective_outcome_scheduled_condition_rule_ids
            and cls._queue_block_reason(state, rule) is None
        ]
        return sorted(eligible, key=lambda rule: (-rule.priority, rule.id))

    @classmethod
    def next_rule_for_event(
        cls,
        state: WorldState,
        event: ObjectiveTerminalEvent,
    ) -> ObjectiveOutcomeScheduledConditionRule | None:
        eligible = cls.eligible_rules(
            state,
            event.objective_id,
            cls.outcome_for_event(event),
        )
        return eligible[0] if eligible else None

    @classmethod
    def queue_event(
        cls,
        state: WorldState,
        event: ObjectiveTerminalEvent,
        turn_number: int,
    ) -> tuple[
        ObjectiveOutcomeScheduledConditionRule | None,
        ScheduledLocationConditionQueued | None,
    ]:
        rule = cls.next_rule_for_event(state, event)
        if rule is None:
            return None, None
        return (
            rule,
            ScheduledLocationConditionQueued(
                turn_number=turn_number,
                rule_id=rule.id,
                objective_id=rule.objective_id,
                outcome=rule.outcome,
                scheduled_event_id=rule.scheduled_event_id,
                due_absolute_minute=state.clock.absolute_minutes + rule.delay_minutes,
            ),
        )

    @classmethod
    def validate_queue_event(
        cls,
        state: WorldState,
        event: ScheduledLocationConditionQueued,
    ) -> str | None:
        rule = cls.rule_by_id(state, event.rule_id)
        if rule is None:
            return "objective outcome schedule rule does not exist"
        if rule.id in state.applied_objective_outcome_scheduled_condition_rule_ids:
            return "objective outcome schedule rule is already applied"
        if event.objective_id != rule.objective_id or event.outcome != rule.outcome:
            return "objective outcome schedule provenance does not match rule"
        if event.scheduled_event_id != rule.scheduled_event_id:
            return "scheduled event id does not match objective outcome schedule rule"

        terminal_ids = (
            state.completed_player_objective_ids
            if rule.outcome == "completed"
            else state.failed_player_objective_ids
        )
        if rule.objective_id not in terminal_ids:
            return f"objective {rule.objective_id} is not canonically {rule.outcome}"

        expected_due = state.clock.absolute_minutes + rule.delay_minutes
        if event.due_absolute_minute != expected_due:
            return "scheduled event due minute does not match objective outcome rule"
        if event.due_absolute_minute <= state.clock.absolute_minutes:
            return "objective outcome schedule must be in the future"

        block_reason = cls._queue_block_reason(state, rule)
        if block_reason is not None:
            return block_reason

        eligible = cls.eligible_rules(state, rule.objective_id, rule.outcome)
        if not eligible:
            return "no objective outcome schedule rule is eligible"
        if eligible[0].id != rule.id:
            return f"expected objective outcome schedule rule {eligible[0].id}"
        return None
