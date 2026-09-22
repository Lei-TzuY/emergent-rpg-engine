from __future__ import annotations

from typing import Literal

from emergent_rpg.domain.events import (
    Event,
    FactDiscovered,
    PlayerObjectiveCompleted,
    PlayerObjectiveFailed,
    RelationshipChanged,
)
from emergent_rpg.domain.models import ObjectiveOutcomeConsequenceRule, WorldState
from emergent_rpg.engine.mystery import MysteryGraph

ObjectiveTerminalEvent = PlayerObjectiveCompleted | PlayerObjectiveFailed
ObjectiveOutcome = Literal["completed", "failed"]


class ObjectiveOutcomeConsequencePolicy:
    @staticmethod
    def outcome_for_event(event: ObjectiveTerminalEvent) -> ObjectiveOutcome:
        if isinstance(event, PlayerObjectiveCompleted):
            return "completed"
        return "failed"

    @staticmethod
    def _rule_by_id(
        state: WorldState,
        rule_id: str,
    ) -> ObjectiveOutcomeConsequenceRule | None:
        return next(
            (
                rule
                for rule in state.objective_outcome_consequence_rules
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
            rule.id in state.applied_objective_outcome_consequence_rule_ids
            for rule in state.objective_outcome_consequence_rules
            if rule.objective_id == objective_id and rule.outcome == outcome
        )

    @classmethod
    def eligible_rules(
        cls,
        state: WorldState,
        objective_id: str,
        outcome: ObjectiveOutcome,
    ) -> list[ObjectiveOutcomeConsequenceRule]:
        if cls._outcome_consumed(state, objective_id, outcome):
            return []
        eligible = [
            rule
            for rule in state.objective_outcome_consequence_rules
            if rule.objective_id == objective_id
            and rule.outcome == outcome
            and rule.id not in state.applied_objective_outcome_consequence_rule_ids
        ]
        return sorted(eligible, key=lambda rule: (-rule.priority, rule.id))

    @classmethod
    def next_rule_for_event(
        cls,
        state: WorldState,
        event: ObjectiveTerminalEvent,
    ) -> ObjectiveOutcomeConsequenceRule | None:
        eligible = cls.eligible_rules(
            state,
            event.objective_id,
            cls.outcome_for_event(event),
        )
        return eligible[0] if eligible else None

    @classmethod
    def consequence_events(
        cls,
        state: WorldState,
        event: ObjectiveTerminalEvent,
        turn_number: int,
    ) -> tuple[ObjectiveOutcomeConsequenceRule | None, list[Event]]:
        rule = cls.next_rule_for_event(state, event)
        if rule is None:
            return None, []

        events: list[Event] = []
        if (
            rule.reward_fact_id is not None
            and rule.reward_fact_id not in state.player_known_facts
            and MysteryGraph.can_discover_fact(
                state,
                rule.reward_fact_id,
                state.player_id,
            )
        ):
            events.append(
                FactDiscovered(
                    turn_number=turn_number,
                    fact_id=rule.reward_fact_id,
                    observer_id=state.player_id,
                )
            )
        events.append(
            RelationshipChanged(
                turn_number=turn_number,
                source_id=rule.source_npc_id,
                target_id=state.player_id,
                delta=rule.relationship_delta,
                rule_id=rule.id,
            )
        )
        return rule, events

    @classmethod
    def validate_relationship_event(
        cls,
        state: WorldState,
        event: RelationshipChanged,
    ) -> str | None:
        if event.rule_id is None:
            return "objective outcome relationship event requires rule provenance"
        rule = cls._rule_by_id(state, event.rule_id)
        if rule is None:
            return "objective outcome consequence rule does not exist"
        if rule.id in state.applied_objective_outcome_consequence_rule_ids:
            return "objective outcome consequence rule is already applied"
        if event.source_id != rule.source_npc_id or event.target_id != state.player_id:
            return "objective outcome relationship participants do not match rule"
        if event.delta != rule.relationship_delta:
            return "relationship delta does not match objective outcome rule"

        terminal_ids = (
            state.completed_player_objective_ids
            if rule.outcome == "completed"
            else state.failed_player_objective_ids
        )
        if rule.objective_id not in terminal_ids:
            return f"objective {rule.objective_id} is not canonically {rule.outcome}"

        eligible = cls.eligible_rules(state, rule.objective_id, rule.outcome)
        if not eligible:
            return "no objective outcome consequence rule is eligible"
        if eligible[0].id != rule.id:
            return f"expected objective outcome consequence rule {eligible[0].id}"
        return None
