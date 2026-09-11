from __future__ import annotations

from collections import Counter

from emergent_rpg.domain.events import (
    CharacterHealed,
    Event,
    FactDiscovered,
    FactInferred,
    NPCGoalCompleted,
    NPCMoved,
    PlayerMoved,
    SimulationCycleProcessed,
    TimeAdvanced,
)
from emergent_rpg.domain.models import NPC, WorldState
from emergent_rpg.validation.models import ValidationReport


def validate_state(state: WorldState, previous: WorldState | None = None) -> ValidationReport:
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
                if goal.kind == "investigate_item" and goal.target_id not in state.items:
                    report.add_error(
                        "invalid_npc_goal",
                        f"{entity_id} goal {goal.id} references missing item {goal.target_id}",
                    )
            missing = entity.knowledge.facts_known - state.facts.keys()
            if missing:
                report.add_error(
                    "nonexistent_entity_reference",
                    f"{entity_id} knows missing facts: {sorted(missing)}",
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
        if (
            state.simulation.next_due_absolute_minute
            < previous.simulation.next_due_absolute_minute
        ):
            report.add_error("simulation_went_backward", "simulation cursor decreased")
        for entity_id, old_entity in previous.entities.items():
            if entity_id in state.entities:
                new_entity = state.entities[entity_id]
                if not old_entity.state.alive and new_entity.state.alive:
                    report.add_error(
                        "impossible_resurrection",
                        f"{entity_id} changed from dead to alive",
                    )
    return report


def validate_event_preconditions(state: WorldState, event: Event) -> ValidationReport:
    report = ValidationReport()
    if isinstance(event, PlayerMoved):
        if event.entity_id not in state.entities:
            report.add_error("nonexistent_entity", f"missing mover {event.entity_id}")
        if event.from_location not in state.locations or event.to_location not in state.locations:
            report.add_error("impossible_character_location", "move references missing location")
    elif isinstance(event, NPCMoved):
        _validate_npc_moved(state, event, report)
    elif isinstance(event, NPCGoalCompleted):
        _validate_npc_goal_completed(state, event, report)
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
    return report


def _validate_npc_moved(
    state: WorldState,
    event: NPCMoved,
    report: ValidationReport,
) -> None:
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
    if not npc.state.alive or not npc.state.conscious:
        report.add_error("inactive_participant", f"{event.npc_id} cannot move")
    if any(condition.incapacitating for condition in npc.state.status_conditions):
        report.add_error("inactive_participant", f"{event.npc_id} movement is blocked")


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
