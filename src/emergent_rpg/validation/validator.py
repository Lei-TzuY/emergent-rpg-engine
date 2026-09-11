from __future__ import annotations

from collections import Counter

from emergent_rpg.domain.events import CharacterHealed, Event, PlayerMoved, TimeAdvanced
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

    for entity_id, entity in state.entities.items():
        if isinstance(entity, NPC):
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
    elif isinstance(event, CharacterHealed):
        if event.entity_id not in state.entities:
            report.add_error("nonexistent_entity", f"missing heal target {event.entity_id}")
        elif not state.entities[event.entity_id].state.alive:
            report.add_error("impossible_resurrection", "cannot heal a dead character back to life")
    elif isinstance(event, TimeAdvanced) and event.minutes <= 0:
        report.add_error("time_went_backward", "time advance must be positive")
    return report


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
