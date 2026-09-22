from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from typing import Literal

from emergent_rpg.domain.events import (
    CharacterDamaged,
    CharacterHealed,
    Event,
    FactDiscovered,
    FactInferred,
    ItemAcquired,
    NPCFactShared,
    NPCGoalCompleted,
    NPCItemDelivered,
    NPCItemLocationObserved,
    NPCLocationMapped,
    NPCMoved,
    PlayerMoved,
    PlayerObjectiveActivated,
    PlayerObjectiveCompleted,
    PlayerObjectiveFailed,
    ScheduledLocationConditionApplied,
    ScheduledLocationConditionExpired,
    ScheduledLocationConditionQueued,
    SimulationCycleProcessed,
    TimeAdvanced,
)
from emergent_rpg.domain.models import NPC, LocationCondition, PlayerCharacter, WorldState
from emergent_rpg.engine.combat import CombatPolicy
from emergent_rpg.engine.environment import EnvironmentalRules
from emergent_rpg.engine.objective_schedules import ObjectiveOutcomeSchedulePolicy
from emergent_rpg.engine.objectives import PlayerObjectivePolicy
from emergent_rpg.engine.social import SocialDisclosurePolicy
from emergent_rpg.validation.models import ValidationReport


def validate_state(
    state: WorldState,
    previous: WorldState | None = None,
    transition_events: list[Event] | None = None,
) -> ValidationReport:
    report = ValidationReport()

    if state.player_id not in state.entities:
        report.add_error("nonexistent_entity", "player_id references a missing entity")

    for entity_id, entity in state.entities.items():
        if entity.state.current_location not in state.locations:
            report.add_error(
                "impossible_character_location",
                f"{entity_id} is in missing location {entity.state.current_location}",
            )
        for item_id in entity.state.inventory:
            if item_id not in state.items:
                report.add_error(
                    "nonexistent_entity", f"inventory references missing item {item_id}"
                )

    inventory_counts = Counter(
        item_id for entity in state.entities.values() for item_id in entity.state.inventory
    )
    for item_id, item in state.items.items():
        holders = int(item.owner_id is not None) + int(item.location_id is not None)
        if holders != 1:
            report.add_error(
                "impossible_item_ownership",
                f"{item_id} must have exactly one owner or location",
            )
        if item.owner_id is not None:
            if item.owner_id not in state.entities:
                report.add_error("nonexistent_entity", f"{item_id} owner does not exist")
            elif item_id not in state.entities[item.owner_id].state.inventory:
                report.add_error(
                    "impossible_item_ownership",
                    f"{item_id} owner and inventory projection disagree",
                )
        if item.location_id is not None and item.location_id not in state.locations:
            report.add_error("impossible_item_ownership", f"{item_id} location does not exist")
        if item.unique and inventory_counts[item_id] > 1:
            report.add_error(
                "duplicate_unique_item",
                f"unique item {item_id} appears in multiple inventories",
            )

    _validate_scheduled_world_state(state, report)

    for fact_id, fact in state.facts.items():
        missing_prerequisites = fact.discovery_prerequisites - state.facts.keys()
        if missing_prerequisites:
            report.add_error(
                "invalid_mystery_graph",
                f"{fact_id} has missing prerequisites: {sorted(missing_prerequisites)}",
            )
        missing_contradictions = fact.contradicts - state.facts.keys()
        if missing_contradictions:
            report.add_error(
                "invalid_mystery_graph",
                f"{fact_id} contradicts missing facts: {sorted(missing_contradictions)}",
            )
        if fact_id in fact.discovery_prerequisites or fact_id in fact.contradicts:
            report.add_error(
                "invalid_mystery_graph",
                f"{fact_id} cannot depend on or contradict itself",
            )

    for rule_id, rule in state.inference_rules.items():
        if rule.id != rule_id:
            report.add_error("invalid_mystery_graph", f"rule key/id mismatch for {rule_id}")
        missing_premises = rule.premises - state.facts.keys()
        if missing_premises or rule.conclusion not in state.facts:
            report.add_error(
                "invalid_mystery_graph",
                f"rule {rule_id} references missing facts",
            )
        elif state.facts[rule.conclusion].discoverability != "inferred":
            report.add_error(
                "invalid_mystery_graph",
                f"rule {rule_id} conclusion must be marked inferred",
            )
        if rule.conclusion in rule.premises:
            report.add_error(
                "invalid_mystery_graph",
                f"rule {rule_id} conclusion cannot be one of its premises",
            )

    for entity_id, entity in state.entities.items():
        if isinstance(entity, NPC):
            for goal in entity.planning_goals:
                if goal.kind == "reach_location" and goal.target_id not in state.locations:
                    report.add_error(
                        "invalid_npc_goal",
                        f"{entity_id} goal {goal.id} references missing location {goal.target_id}",
                    )
                if (
                    goal.kind in {"investigate_item", "acquire_item", "deliver_item"}
                    and goal.target_id not in state.items
                ):
                    report.add_error(
                        "invalid_npc_goal",
                        f"{entity_id} goal {goal.id} references missing item {goal.target_id}",
                    )
                if goal.kind == "deliver_item":
                    if goal.receiver_id not in state.entities or goal.receiver_id == entity_id:
                        report.add_error(
                            "invalid_npc_goal",
                            f"{entity_id} goal {goal.id} references invalid delivery receiver",
                        )
                    if goal.delivery_location_id not in state.locations:
                        report.add_error(
                            "invalid_npc_goal",
                            f"{entity_id} goal {goal.id} references invalid delivery location",
                        )
            missing = entity.knowledge.facts_known - state.facts.keys()
            if missing:
                report.add_error(
                    "nonexistent_entity_reference",
                    f"{entity_id} knows missing facts: {sorted(missing)}",
                )
            missing_mapped_locations = (
                entity.knowledge.mapped_locations - state.locations.keys()
            )
            if missing_mapped_locations:
                report.add_error(
                    "invalid_npc_map",
                    f"{entity_id} mapped missing locations: {sorted(missing_mapped_locations)}",
                )
            missing_belief_items = (
                entity.knowledge.item_location_beliefs.keys() - state.items.keys()
            )
            if missing_belief_items:
                report.add_error(
                    "invalid_npc_item_belief",
                    f"{entity_id} remembers missing items: {sorted(missing_belief_items)}",
                )
            missing_belief_locations = (
                set(entity.knowledge.item_location_beliefs.values()) - state.locations.keys()
            )
            if missing_belief_locations:
                report.add_error(
                    "invalid_npc_item_belief",
                    f"{entity_id} remembers missing locations: {sorted(missing_belief_locations)}",
                )

    missing_player_facts = state.player_known_facts - state.facts.keys()
    if missing_player_facts:
        report.add_error(
            "nonexistent_entity_reference",
            f"player knows missing facts: {sorted(missing_player_facts)}",
        )

    if previous is not None:
        if state.turn_number < previous.turn_number:
            report.add_error("turn_went_backward", "turn number decreased")
        if state.clock.absolute_minutes < previous.clock.absolute_minutes:
            report.add_error("time_went_backward", "world time decreased")

        expected_health = {
            entity_id: entity.state.health
            for entity_id, entity in previous.entities.items()
        }
        expected_alive = {
            entity_id: entity.state.alive
            for entity_id, entity in previous.entities.items()
        }
        expected_conscious = {
            entity_id: entity.state.conscious
            for entity_id, entity in previous.entities.items()
        }
        for transition_event in transition_events or []:
            if isinstance(transition_event, CharacterDamaged):
                if transition_event.entity_id in expected_health:
                    entity_id = transition_event.entity_id
                    expected_health[entity_id] = max(
                        0,
                        expected_health[entity_id] - transition_event.amount,
                    )
                    if expected_health[entity_id] == 0:
                        expected_alive[entity_id] = False
                        expected_conscious[entity_id] = False
            elif (
                isinstance(transition_event, CharacterHealed)
                and transition_event.entity_id in expected_health
            ):
                expected_health[transition_event.entity_id] = min(
                    10,
                    expected_health[transition_event.entity_id]
                    + transition_event.amount,
                )
        mismatched_health = [
            entity_id
            for entity_id, health in expected_health.items()
            if entity_id in state.entities
            and state.entities[entity_id].state.health != health
        ]
        if mismatched_health:
            report.add_error(
                "character_health_changed_without_event",
                "character health does not match damage/healing event provenance: "
                f"{sorted(mismatched_health)}",
            )
        mismatched_life_state = [
            entity_id
            for entity_id in expected_alive
            if entity_id in state.entities
            and (
                state.entities[entity_id].state.alive != expected_alive[entity_id]
                or state.entities[entity_id].state.conscious
                != expected_conscious[entity_id]
            )
        ]
        if mismatched_life_state:
            report.add_error(
                "character_life_state_changed_without_event",
                "character alive/conscious state does not match damage event provenance: "
                f"{sorted(mismatched_life_state)}",
            )
        if (
            state.simulation.next_due_absolute_minute
            < previous.simulation.next_due_absolute_minute
        ):
            report.add_error("simulation_went_backward", "simulation cursor decreased")
        authorized_expirations = {
            (event.location_id, event.condition_code)
            for event in transition_events or []
            if isinstance(event, ScheduledLocationConditionExpired)
        }
        authorized_mappings = {
            (event.npc_id, event.location_id)
            for event in transition_events or []
            if isinstance(event, NPCLocationMapped)
        }

        expected_active_objectives = set(previous.active_player_objective_ids)
        expected_completed_objectives = set(previous.completed_player_objective_ids)
        expected_failed_objectives = set(previous.failed_player_objective_ids)
        for transition_event in transition_events or []:
            if isinstance(transition_event, PlayerObjectiveActivated):
                expected_active_objectives.add(transition_event.objective_id)
            elif isinstance(transition_event, PlayerObjectiveCompleted):
                expected_active_objectives.discard(transition_event.objective_id)
                expected_completed_objectives.add(transition_event.objective_id)
            elif isinstance(transition_event, PlayerObjectiveFailed):
                expected_active_objectives.discard(transition_event.objective_id)
                expected_failed_objectives.add(transition_event.objective_id)
        if (
            state.active_player_objective_ids != expected_active_objectives
            or state.completed_player_objective_ids != expected_completed_objectives
            or state.failed_player_objective_ids != expected_failed_objectives
        ):
            report.add_error(
                "player_objective_changed_without_event",
                "player objective state does not match lifecycle event provenance",
            )

        queue_events = [
            event
            for event in transition_events or []
            if isinstance(event, ScheduledLocationConditionQueued)
        ]
        queued_schedule_ids = {event.scheduled_event_id for event in queue_events}
        applied_schedule_ids = {
            event.scheduled_event_id
            for event in transition_events or []
            if isinstance(event, ScheduledLocationConditionApplied)
        }
        previous_schedules = {
            scheduled.id: scheduled
            for scheduled in previous.scheduled_location_conditions
        }
        current_schedules = {
            scheduled.id: scheduled
            for scheduled in state.scheduled_location_conditions
        }
        unexpected_schedule_additions = (
            current_schedules.keys()
            - previous_schedules.keys()
            - queued_schedule_ids
        )
        if unexpected_schedule_additions:
            report.add_error(
                "scheduled_world_event_changed_without_queue",
                "scheduled world events were added without queue provenance: "
                f"{sorted(unexpected_schedule_additions)}",
            )
        missing_queued_schedules = (
            queued_schedule_ids
            - current_schedules.keys()
            - applied_schedule_ids
        )
        if missing_queued_schedules:
            report.add_error(
                "scheduled_world_event_queue_not_applied",
                "queued scheduled world events are missing from canonical state: "
                f"{sorted(missing_queued_schedules)}",
            )
        mutated_pending_schedules = [
            schedule_id
            for schedule_id in previous_schedules.keys() & current_schedules.keys()
            if previous_schedules[schedule_id] != current_schedules[schedule_id]
        ]
        if mutated_pending_schedules:
            report.add_error(
                "scheduled_world_event_mutated_in_place",
                "pending scheduled world events changed in place: "
                f"{sorted(mutated_pending_schedules)}",
            )

        expected_applied_schedule_rules = set(
            previous.applied_objective_outcome_scheduled_condition_rule_ids
        )
        expected_applied_schedule_rules.update(event.rule_id for event in queue_events)
        if (
            state.applied_objective_outcome_scheduled_condition_rule_ids
            != expected_applied_schedule_rules
        ):
            report.add_error(
                "objective_schedule_rule_changed_without_event",
                "objective schedule applied-rule state does not match queue provenance",
            )

        for location_id, old_location in previous.locations.items():
            if location_id in state.locations:
                removed_conditions = (
                    old_location.active_conditions.keys()
                    - state.locations[location_id].active_conditions.keys()
                )
                unauthorized = {
                    code
                    for code in removed_conditions
                    if (location_id, code) not in authorized_expirations
                }
                if unauthorized:
                    report.add_error(
                        "environment_went_backward",
                        f"{location_id} lost conditions without expiry: {sorted(unauthorized)}",
                    )
        for entity_id, old_entity in previous.entities.items():
            if entity_id in state.entities:
                new_entity = state.entities[entity_id]
                if not old_entity.state.alive and new_entity.state.alive:
                    report.add_error(
                        "impossible_resurrection",
                        f"{entity_id} changed from dead to alive",
                    )
                if isinstance(old_entity, NPC) and isinstance(new_entity, NPC):
                    removed_mappings = (
                        old_entity.knowledge.mapped_locations
                        - new_entity.knowledge.mapped_locations
                    )
                    if removed_mappings:
                        report.add_error(
                            "npc_map_went_backward",
                            f"{entity_id} forgot mapped locations: {sorted(removed_mappings)}",
                        )
                    added_mappings = (
                        new_entity.knowledge.mapped_locations
                        - old_entity.knowledge.mapped_locations
                    )
                    unauthorized_mappings = {
                        location_id
                        for location_id in added_mappings
                        if (entity_id, location_id) not in authorized_mappings
                    }
                    if unauthorized_mappings:
                        report.add_error(
                            "npc_map_changed_without_observation",
                            f"{entity_id} learned map locations without events: "
                            f"{sorted(unauthorized_mappings)}",
                        )

                    expected_item_beliefs = dict(
                        old_entity.knowledge.item_location_beliefs
                    )
                    for event in transition_events or []:
                        if not isinstance(event, NPCItemLocationObserved):
                            continue
                        if event.npc_id != entity_id:
                            continue
                        if event.present:
                            expected_item_beliefs[event.item_id] = event.location_id
                        elif expected_item_beliefs.get(event.item_id) == event.location_id:
                            del expected_item_beliefs[event.item_id]
                    if new_entity.knowledge.item_location_beliefs != expected_item_beliefs:
                        report.add_error(
                            "npc_item_belief_changed_without_observation",
                            f"{entity_id} item-location memory does not match observation events",
                        )
    return report


def validate_event_preconditions(state: WorldState, event: Event) -> ValidationReport:
    report = ValidationReport()
    if isinstance(event, PlayerMoved):
        _validate_player_moved(state, event, report)
    elif isinstance(event, NPCMoved):
        _validate_npc_moved(state, event, report)
    elif isinstance(event, ItemAcquired):
        _validate_item_acquired(state, event, report)
    elif isinstance(event, NPCLocationMapped):
        _validate_npc_location_mapped(state, event, report)
    elif isinstance(event, NPCItemLocationObserved):
        _validate_npc_item_location_observed(state, event, report)
    elif isinstance(event, NPCItemDelivered):
        _validate_npc_item_delivered(state, event, report)
    elif isinstance(event, NPCFactShared):
        _validate_npc_fact_shared(state, event, report)
    elif isinstance(event, NPCGoalCompleted):
        _validate_npc_goal_completed(state, event, report)
    elif isinstance(event, PlayerObjectiveActivated):
        reason = PlayerObjectivePolicy.validate_activation_event(state, event)
        if reason is not None:
            report.add_error("invalid_player_objective", reason)
    elif isinstance(event, PlayerObjectiveCompleted):
        reason = PlayerObjectivePolicy.validate_completion_event(state, event)
        if reason is not None:
            report.add_error("invalid_player_objective", reason)
    elif isinstance(event, PlayerObjectiveFailed):
        reason = PlayerObjectivePolicy.validate_failure_event(state, event)
        if reason is not None:
            report.add_error("invalid_player_objective", reason)
    elif isinstance(event, CharacterDamaged):
        reason = CombatPolicy.validate_damage_event(state, event)
        if reason is not None:
            report.add_error("invalid_character_damage", reason)
    elif isinstance(event, CharacterHealed):
        if event.entity_id not in state.entities:
            report.add_error("nonexistent_entity", f"missing heal target {event.entity_id}")
        elif not state.entities[event.entity_id].state.alive:
            report.add_error("impossible_resurrection", "cannot heal a dead character back to life")
    elif isinstance(event, FactDiscovered):
        _validate_discovery_event(state, event, report)
    elif isinstance(event, FactInferred):
        _validate_inference_event(state, event, report)
    elif isinstance(event, TimeAdvanced) and event.minutes <= 0:
        report.add_error("time_went_backward", "time advance must be positive")
    elif isinstance(event, SimulationCycleProcessed):
        expected = state.simulation.next_due_absolute_minute
        if event.scheduled_absolute_minute != expected:
            report.add_error(
                "invalid_simulation_cycle",
                f"simulation cycle expected minute {expected}",
            )
        if event.scheduled_absolute_minute > state.clock.absolute_minutes:
            report.add_error(
                "invalid_simulation_cycle",
                "simulation cycle cannot be processed before world time reaches it",
            )
    elif isinstance(event, ScheduledLocationConditionQueued):
        reason = ObjectiveOutcomeSchedulePolicy.validate_queue_event(state, event)
        if reason is not None:
            report.add_error("invalid_objective_schedule", reason)
    elif isinstance(event, ScheduledLocationConditionApplied):
        _validate_scheduled_location_condition(state, event, report)
    elif isinstance(event, ScheduledLocationConditionExpired):
        _validate_scheduled_location_condition_expiry(state, event, report)
    return report


def _pending_world_events(
    state: WorldState,
) -> list[tuple[int, int, str, Literal["activate", "expire"]]]:
    pending: list[tuple[int, int, str, Literal["activate", "expire"]]] = []
    for activation in state.scheduled_location_conditions:
        pending.append((activation.due_absolute_minute, 0, activation.id, "activate"))
        expiry_minute = activation.expiry_absolute_minute
        if expiry_minute is not None:
            pending.append((expiry_minute, 1, activation.expiry_event_id, "expire"))
    pending.extend(
        (expiry.due_absolute_minute, 1, expiry.id, "expire")
        for expiry in state.scheduled_location_condition_expirations
    )
    pending.sort()
    return pending


def _validate_scheduled_world_state(state: WorldState, report: ValidationReport) -> None:
    activation_ids = [activation.id for activation in state.scheduled_location_conditions]
    derived_expiry_ids = [
        activation.expiry_event_id
        for activation in state.scheduled_location_conditions
        if activation.expiry_absolute_minute is not None
    ]
    expiry_ids = [
        expiry.id for expiry in state.scheduled_location_condition_expirations
    ]
    all_ids = [*activation_ids, *derived_expiry_ids, *expiry_ids]
    if len(all_ids) != len(set(all_ids)):
        report.add_error("invalid_scheduled_world_event", "scheduled event ids must be unique")

    activation_targets: list[tuple[str, str]] = []
    for activation in state.scheduled_location_conditions:
        if activation.location_id not in state.locations:
            report.add_error(
                "invalid_scheduled_world_event",
                f"{activation.id} references missing location {activation.location_id}",
            )
            continue
        target = (activation.location_id, activation.condition.code)
        activation_targets.append(target)
        location = state.locations[activation.location_id]
        _validate_condition_route_targets(
            activation.location_id,
            location.exits.values(),
            activation.condition,
            report,
        )
        if activation.condition.code in location.active_conditions:
            report.add_error(
                "invalid_scheduled_world_event",
                f"{activation.id} targets an already-active location condition",
            )

    duplicate_targets = [
        target for target, count in Counter(activation_targets).items() if count > 1
    ]
    if duplicate_targets:
        report.add_error(
            "invalid_scheduled_world_event",
            f"scheduled condition targets must be unique: {sorted(duplicate_targets)}",
        )

    expiry_targets: list[tuple[str, str]] = []
    for expiry in state.scheduled_location_condition_expirations:
        if expiry.location_id not in state.locations:
            report.add_error(
                "invalid_scheduled_world_event",
                f"{expiry.id} references missing location {expiry.location_id}",
            )
            continue
        target = (expiry.location_id, expiry.condition_code)
        expiry_targets.append(target)
        if expiry.condition_code not in state.locations[expiry.location_id].active_conditions:
            report.add_error(
                "invalid_scheduled_world_event",
                f"{expiry.id} expiry target is not active",
            )

    duplicate_expiry_targets = [
        target for target, count in Counter(expiry_targets).items() if count > 1
    ]
    if duplicate_expiry_targets:
        report.add_error(
            "invalid_scheduled_world_event",
            f"scheduled expiry targets must be unique: {sorted(duplicate_expiry_targets)}",
        )

    for location_id, location in state.locations.items():
        for key, condition in location.active_conditions.items():
            if key != condition.code:
                report.add_error(
                    "invalid_location_condition",
                    f"{location_id} condition key/code mismatch for {key}",
                )
            _validate_condition_route_targets(
                location_id,
                location.exits.values(),
                condition,
                report,
            )


def _validate_condition_route_targets(
    location_id: str,
    local_destinations: Iterable[str],
    condition: LocationCondition,
    report: ValidationReport,
) -> None:
    if condition.route is None:
        return
    local = set(local_destinations)
    invalid = condition.route.blocked_destination_ids - local
    if invalid:
        report.add_error(
            "invalid_environment_rule",
            f"{location_id} condition {condition.code} blocks non-local exits: {sorted(invalid)}",
        )


def _validate_expected_world_event(
    state: WorldState,
    event_id: str,
    minute: int,
    kind: Literal["activate", "expire"],
    report: ValidationReport,
) -> bool:
    pending = _pending_world_events(state)
    if not pending:
        report.add_error(
            "invalid_scheduled_world_event",
            f"scheduled event {event_id} is not pending",
        )
        return False
    expected_minute, _, expected_id, expected_kind = pending[0]
    if (event_id, kind) != (expected_id, expected_kind):
        report.add_error(
            "invalid_scheduled_world_event",
            f"scheduled event expected {expected_id} ({expected_kind}) before {event_id}",
        )
        return False
    if minute != expected_minute:
        report.add_error(
            "invalid_scheduled_world_event",
            f"scheduled event {expected_id} minute does not match canonical schedule",
        )
    if expected_minute > state.clock.absolute_minutes:
        report.add_error(
            "invalid_scheduled_world_event",
            f"scheduled event {expected_id} cannot run before its due world time",
        )
    return report.valid


def _validate_scheduled_location_condition(
    state: WorldState,
    event: ScheduledLocationConditionApplied,
    report: ValidationReport,
) -> None:
    if not _validate_expected_world_event(
        state,
        event.scheduled_event_id,
        event.scheduled_absolute_minute,
        "activate",
        report,
    ):
        return
    expected = next(
        item
        for item in state.scheduled_location_conditions
        if item.id == event.scheduled_event_id
    )
    location = state.locations.get(expected.location_id)
    if location is None:
        report.add_error(
            "invalid_scheduled_world_event",
            f"scheduled event {expected.id} references a missing location",
        )
    elif expected.condition.code in location.active_conditions:
        report.add_error(
            "invalid_scheduled_world_event",
            f"scheduled event {expected.id} condition is already active",
        )


def _validate_scheduled_location_condition_expiry(
    state: WorldState,
    event: ScheduledLocationConditionExpired,
    report: ValidationReport,
) -> None:
    if not _validate_expected_world_event(
        state,
        event.scheduled_event_id,
        event.scheduled_absolute_minute,
        "expire",
        report,
    ):
        return
    scheduled_expiry = next(
        (
            item
            for item in state.scheduled_location_condition_expirations
            if item.id == event.scheduled_event_id
        ),
        None,
    )
    if scheduled_expiry is None:
        report.add_error(
            "invalid_scheduled_world_event",
            f"expiry {event.scheduled_event_id} has not been materialized",
        )
        return
    if (event.location_id, event.condition_code) != (
        scheduled_expiry.location_id,
        scheduled_expiry.condition_code,
    ):
        report.add_error(
            "invalid_scheduled_world_event",
            "expiry target does not match canonical schedule",
        )
        return
    location = state.locations.get(scheduled_expiry.location_id)
    if location is None or scheduled_expiry.condition_code not in location.active_conditions:
        report.add_error(
            "invalid_scheduled_world_event",
            f"expiry {scheduled_expiry.id} target is not active",
        )


def _validate_player_moved(
    state: WorldState,
    event: PlayerMoved,
    report: ValidationReport,
) -> None:
    player = state.entities.get(event.entity_id)
    if not isinstance(player, PlayerCharacter) or event.entity_id != state.player_id:
        report.add_error("nonexistent_entity", f"missing player mover {event.entity_id}")
        return
    if event.from_location != player.state.current_location:
        report.add_error("impossible_character_location", "player move origin does not match state")
        return
    if event.to_location not in state.locations:
        report.add_error("impossible_character_location", "player move references missing location")
        return
    location = state.locations[event.from_location]
    if event.to_location not in location.exits.values():
        report.add_error("impossible_character_location", "player destination is not a local exit")
        return
    access = EnvironmentalRules().route_access(state, event.from_location, event.to_location)
    if not access.allowed:
        report.add_error(
            "blocked_environmental_route",
            f"player route is blocked by {access.condition_names}",
        )


def _validate_npc_moved(state: WorldState, event: NPCMoved, report: ValidationReport) -> None:
    npc = state.entities.get(event.npc_id)
    if not isinstance(npc, NPC):
        report.add_error("nonexistent_entity", f"missing NPC mover {event.npc_id}")
        return
    if event.from_location != npc.state.current_location:
        report.add_error("impossible_character_location", "NPC move origin does not match state")
        return
    if event.to_location not in state.locations:
        report.add_error("impossible_character_location", "NPC move references missing location")
        return
    location = state.locations[event.from_location]
    if event.to_location not in location.exits.values():
        report.add_error("impossible_character_location", "NPC destination is not a local exit")
        return
    access = EnvironmentalRules().route_access(state, event.from_location, event.to_location)
    if not access.allowed:
        report.add_error(
            "blocked_environmental_route",
            f"NPC route is blocked by {access.condition_names}",
        )
    if not npc.state.alive or not npc.state.conscious:
        report.add_error("inactive_participant", f"{event.npc_id} cannot move")
    if any(condition.incapacitating for condition in npc.state.status_conditions):
        report.add_error("inactive_participant", f"{event.npc_id} movement is blocked")


def _validate_item_acquired(
    state: WorldState,
    event: ItemAcquired,
    report: ValidationReport,
) -> None:
    actor = state.entities.get(event.actor_id)
    if actor is None:
        report.add_error("nonexistent_entity", f"missing item-acquisition actor {event.actor_id}")
        return
    item = state.items.get(event.item_id)
    if item is None:
        report.add_error("nonexistent_entity", f"missing acquired item {event.item_id}")
        return
    if not actor.state.alive or not actor.state.conscious:
        report.add_error("inactive_participant", f"{event.actor_id} cannot acquire an item")
    if item.owner_id is not None or event.from_owner is not None:
        report.add_error("invalid_item_acquisition", "owned-item transfer is not supported")
        return
    if item.location_id != actor.state.current_location:
        report.add_error("invalid_item_acquisition", "item is not at the actor's location")
    if event.from_location != item.location_id:
        report.add_error(
            "invalid_item_acquisition",
            "acquisition origin does not match item location",
        )
    if "portable" not in item.flags:
        report.add_error("invalid_item_acquisition", f"item {item.id} is not portable")


def _validate_npc_location_mapped(
    state: WorldState,
    event: NPCLocationMapped,
    report: ValidationReport,
) -> None:
    npc = state.entities.get(event.npc_id)
    if not isinstance(npc, NPC):
        report.add_error("nonexistent_entity", f"missing NPC mapper {event.npc_id}")
        return
    if event.location_id not in state.locations:
        report.add_error("invalid_npc_map", f"mapped location {event.location_id} does not exist")
        return
    if not npc.state.alive or not npc.state.conscious:
        report.add_error("inactive_participant", f"{event.npc_id} cannot observe a location")
        return
    if npc.state.current_location != event.location_id:
        report.add_error(
            "invalid_npc_map",
            f"{event.npc_id} cannot map remote location {event.location_id}",
        )
        return
    if event.location_id in npc.knowledge.mapped_locations:
        report.add_error(
            "invalid_npc_map",
            f"{event.npc_id} already mapped location {event.location_id}",
        )


def _validate_npc_item_location_observed(
    state: WorldState,
    event: NPCItemLocationObserved,
    report: ValidationReport,
) -> None:
    npc = state.entities.get(event.npc_id)
    if not isinstance(npc, NPC):
        report.add_error("nonexistent_entity", f"missing NPC observer {event.npc_id}")
        return
    item = state.items.get(event.item_id)
    if item is None:
        report.add_error("invalid_npc_item_observation", f"missing item {event.item_id}")
        return
    if event.location_id not in state.locations:
        report.add_error(
            "invalid_npc_item_observation",
            f"observation location {event.location_id} does not exist",
        )
        return
    if not npc.state.alive or not npc.state.conscious:
        report.add_error("inactive_participant", f"{event.npc_id} cannot observe an item")
        return
    if npc.state.current_location != event.location_id:
        report.add_error(
            "invalid_npc_item_observation",
            f"{event.npc_id} cannot observe remote location {event.location_id}",
        )
        return

    remembered_location = npc.knowledge.item_location_beliefs.get(event.item_id)
    item_is_present = item.location_id == event.location_id
    if event.present:
        if not item_is_present:
            report.add_error(
                "invalid_npc_item_observation",
                f"{event.item_id} is not present at {event.location_id}",
            )
        elif remembered_location == event.location_id:
            report.add_error(
                "invalid_npc_item_observation",
                f"{event.npc_id} already remembers {event.item_id} at {event.location_id}",
            )
    else:
        if remembered_location != event.location_id:
            report.add_error(
                "invalid_npc_item_observation",
                f"{event.npc_id} has no matching belief to invalidate",
            )
        if item_is_present:
            report.add_error(
                "invalid_npc_item_observation",
                f"{event.item_id} is still present at {event.location_id}",
            )


def _validate_npc_item_delivered(
    state: WorldState,
    event: NPCItemDelivered,
    report: ValidationReport,
) -> None:
    source = state.entities.get(event.source_npc_id)
    if not isinstance(source, NPC):
        report.add_error("nonexistent_entity", f"missing delivery source {event.source_npc_id}")
        return
    receiver = state.entities.get(event.receiver_id)
    if receiver is None or receiver.id == source.id:
        report.add_error("invalid_npc_item_delivery", "delivery receiver is invalid")
        return
    item = state.items.get(event.item_id)
    if item is None:
        report.add_error("invalid_npc_item_delivery", f"missing delivery item {event.item_id}")
        return
    goal = next((goal for goal in source.planning_goals if goal.id == event.goal_id), None)
    if goal is None:
        report.add_error("invalid_npc_item_delivery", f"missing delivery goal {event.goal_id}")
        return
    if (
        goal.kind != "deliver_item"
        or goal.target_id != item.id
        or goal.receiver_id != receiver.id
    ):
        report.add_error(
            "invalid_npc_item_delivery",
            "delivery event does not match configured goal",
        )
        return
    if event.goal_id in source.completed_goal_ids:
        report.add_error("invalid_npc_item_delivery", "delivery goal is already complete")
    missing_required_facts = goal.required_fact_ids - source.knowledge.facts_known
    if missing_required_facts:
        report.add_error(
            "invalid_npc_item_delivery",
            f"delivery source lacks goal prerequisites: {sorted(missing_required_facts)}",
        )
    if not source.state.alive or not source.state.conscious:
        report.add_error("inactive_participant", f"{source.id} cannot deliver an item")
    if not receiver.state.alive or not receiver.state.conscious:
        report.add_error("inactive_participant", f"{receiver.id} cannot receive an item")
    if source.state.current_location != receiver.state.current_location:
        report.add_error(
            "invalid_npc_item_delivery",
            "delivery participants must be physically co-located",
        )
    if goal.delivery_location_id != source.state.current_location:
        report.add_error(
            "invalid_npc_item_delivery",
            "delivery does not occur at the configured location",
        )
    if item.owner_id != source.id or item.id not in source.state.inventory:
        report.add_error(
            "invalid_npc_item_delivery",
            "delivery source does not canonically own the item",
        )
    if item.id in receiver.state.inventory:
        report.add_error(
            "invalid_npc_item_delivery",
            "delivery receiver already has the item",
        )
    if "portable" not in item.flags:
        report.add_error("invalid_npc_item_delivery", f"item {item.id} is not portable")


def _validate_npc_fact_shared(
    state: WorldState,
    event: NPCFactShared,
    report: ValidationReport,
) -> None:
    source = state.entities.get(event.source_npc_id)
    receiver = state.entities.get(event.receiver_npc_id)
    if not isinstance(source, NPC):
        report.add_error("nonexistent_entity", f"missing fact-sharing source {event.source_npc_id}")
        return
    if not isinstance(receiver, NPC) or receiver.id == source.id:
        report.add_error(
            "invalid_npc_fact_share",
            f"invalid fact-sharing receiver {event.receiver_npc_id}",
        )
        return
    fact = state.facts.get(event.fact_id)
    if fact is None:
        report.add_error("invalid_npc_fact_share", f"missing shared fact {event.fact_id}")
        return
    if not source.state.alive or not source.state.conscious:
        report.add_error("inactive_participant", f"{source.id} cannot share facts")
    if not receiver.state.alive or not receiver.state.conscious:
        report.add_error("inactive_participant", f"{receiver.id} cannot receive facts")
    if source.state.current_location != receiver.state.current_location:
        report.add_error(
            "invalid_npc_fact_share",
            "fact-sharing NPCs must be physically co-located",
        )
    if event.fact_id not in source.knowledge.facts_known:
        report.add_error(
            "npc_fact_not_known",
            f"{source.id} attempted to share unknown fact {event.fact_id}",
        )
    if event.fact_id in receiver.knowledge.facts_known:
        report.add_error(
            "invalid_npc_fact_share",
            f"{receiver.id} already knows fact {event.fact_id}",
        )
    if (
        event.fact_id in source.knowledge.facts_known
        and event.fact_id not in receiver.knowledge.facts_known
        and not SocialDisclosurePolicy.can_disclose(fact, source, receiver.id)
    ):
        score = SocialDisclosurePolicy.relationship_score(source, receiver.id)
        report.add_error(
            "npc_disclosure_blocked",
            f"{source.id} relationship {score} with {receiver.id} is below "
            f"fact {event.fact_id} disclosure requirement {fact.disclosure_min_relationship}",
        )


def _validate_npc_goal_completed(
    state: WorldState,
    event: NPCGoalCompleted,
    report: ValidationReport,
) -> None:
    npc = state.entities.get(event.npc_id)
    if not isinstance(npc, NPC):
        report.add_error("nonexistent_entity", f"missing NPC {event.npc_id}")
        return
    goal = next((item for item in npc.planning_goals if item.id == event.goal_id), None)
    if goal is None:
        report.add_error("invalid_npc_goal", f"missing NPC goal {event.goal_id}")
        return
    if event.goal_id in npc.completed_goal_ids:
        report.add_error("invalid_npc_goal", f"NPC goal {event.goal_id} is already complete")
        return
    if event.method == "reached_location":
        if goal.kind != "reach_location" or goal.target_id != event.evidence_id:
            report.add_error("invalid_npc_goal", "goal completion does not match reach goal")
        elif npc.state.current_location != goal.target_id:
            report.add_error("invalid_npc_goal", "NPC has not reached the goal location")
    elif event.method == "inspected_item":
        if goal.kind != "investigate_item" or goal.target_id != event.evidence_id:
            report.add_error("invalid_npc_goal", "goal completion does not match inspection goal")
            return
        item = state.items.get(event.evidence_id)
        if item is None:
            report.add_error("invalid_npc_goal", "inspection evidence item does not exist")
        elif item.owner_id != npc.id and item.location_id != npc.state.current_location:
            report.add_error("invalid_npc_goal", "inspection evidence is not accessible to NPC")
    elif event.method == "acquired_item":
        if goal.kind != "acquire_item" or goal.target_id != event.evidence_id:
            report.add_error("invalid_npc_goal", "goal completion does not match acquisition goal")
            return
        item = state.items.get(event.evidence_id)
        if item is None:
            report.add_error("invalid_npc_goal", "acquisition evidence item does not exist")
        elif item.owner_id != npc.id or item.id not in npc.state.inventory:
            report.add_error("invalid_npc_goal", "NPC does not own acquisition evidence")
    elif event.method == "delivered_item":
        if goal.kind != "deliver_item" or goal.target_id != event.evidence_id:
            report.add_error("invalid_npc_goal", "goal completion does not match delivery goal")
            return
        item = state.items.get(event.evidence_id)
        receiver = state.entities.get(goal.receiver_id or "")
        if item is None or receiver is None:
            report.add_error("invalid_npc_goal", "delivery evidence does not exist")
        elif item.owner_id != receiver.id or item.id not in receiver.state.inventory:
            report.add_error("invalid_npc_goal", "delivery receiver does not own evidence item")
        elif item.id in npc.state.inventory:
            report.add_error("invalid_npc_goal", "delivery source still owns evidence item")


def _known_facts_for_observer(
    state: WorldState,
    observer_id: str,
    report: ValidationReport,
) -> set[str] | None:
    if observer_id == state.player_id:
        return state.player_known_facts
    observer = state.entities.get(observer_id)
    if not isinstance(observer, NPC):
        report.add_error("nonexistent_entity", f"missing fact observer {observer_id}")
        return None
    return observer.knowledge.facts_known


def _validate_discovery_event(
    state: WorldState,
    event: FactDiscovered,
    report: ValidationReport,
) -> None:
    fact = state.facts.get(event.fact_id)
    if fact is None:
        report.add_error("nonexistent_entity", f"missing discovered fact {event.fact_id}")
        return
    known = _known_facts_for_observer(state, event.observer_id, report)
    if known is None:
        return
    if fact.discoverability == "inferred":
        report.add_error(
            "invalid_discovery",
            f"fact {event.fact_id} requires inference provenance",
        )
    missing = fact.discovery_prerequisites - known
    if missing:
        report.add_error(
            "invalid_discovery",
            f"observer lacks discovery prerequisites: {sorted(missing)}",
        )


def _validate_inference_event(
    state: WorldState,
    event: FactInferred,
    report: ValidationReport,
) -> None:
    rule = state.inference_rules.get(event.rule_id)
    if rule is None:
        report.add_error("invalid_inference", f"missing inference rule {event.rule_id}")
        return
    if rule.conclusion != event.fact_id:
        report.add_error("invalid_inference", "inference conclusion does not match rule")
    if set(event.premise_fact_ids) != rule.premises:
        report.add_error("invalid_inference", "inference provenance does not match rule premises")

    fact = state.facts.get(event.fact_id)
    if fact is None:
        report.add_error("nonexistent_entity", f"missing inferred fact {event.fact_id}")
        return
    if fact.discoverability != "inferred":
        report.add_error(
            "invalid_inference",
            f"fact {event.fact_id} is not marked as inferred",
        )

    known = _known_facts_for_observer(state, event.observer_id, report)
    if known is None:
        return
    missing = rule.premises - known
    if missing:
        report.add_error(
            "invalid_inference",
            f"observer lacks inference premises: {sorted(missing)}",
        )
    if event.fact_id in known:
        report.add_error("invalid_inference", f"fact {event.fact_id} is already known")


def validate_scene_participation(
    state: WorldState, participants: list[str], fact_reveals: dict[str, list[str]]
) -> ValidationReport:
    report = ValidationReport()
    player_location = state.player().state.current_location
    for entity_id in participants:
        if entity_id not in state.entities:
            report.add_error("nonexistent_entity_reference", f"scene references {entity_id}")
            continue
        entity = state.entities[entity_id]
        if entity.state.current_location != player_location:
            report.add_error(
                "impossible_character_location",
                f"{entity_id} cannot participate from {entity.state.current_location}",
            )
        if not entity.state.alive or not entity.state.conscious:
            report.add_error("inactive_participant", f"{entity_id} cannot participate in scene")

    for entity_id, fact_ids in fact_reveals.items():
        if entity_id == state.player_id:
            allowed = state.player_known_facts
        elif entity_id in state.entities and isinstance(state.entities[entity_id], NPC):
            npc = state.entities[entity_id]
            assert isinstance(npc, NPC)
            allowed = npc.knowledge.facts_known
        else:
            report.add_error("nonexistent_entity_reference", f"fact speaker {entity_id} missing")
            continue
        for fact_id in fact_ids:
            if fact_id not in allowed:
                report.add_error(
                    "npc_fact_not_known",
                    f"{entity_id} attempted to reveal unknown fact {fact_id}",
                )
    return report