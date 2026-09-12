from __future__ import annotations

from emergent_rpg.domain.events import (
    CharacterDamaged,
    CharacterHealed,
    Event,
    FactDiscovered,
    FactInferred,
    ItemAcquired,
    ItemDropped,
    NPCFactShared,
    NPCGoalCompleted,
    NPCItemLocationObserved,
    NPCLearnedFact,
    NPCLocationMapped,
    NPCMoved,
    PlayerMoved,
    RelationshipChanged,
    ScheduledLocationConditionApplied,
    ScheduledLocationConditionExpired,
    SimulationCycleProcessed,
    StatusApplied,
    TimeAdvanced,
)
from emergent_rpg.domain.models import (
    NPC,
    ScheduledLocationConditionExpiry,
    StatusCondition,
    WorldState,
)
from emergent_rpg.engine.dialogue import DialogueRelationshipPolicy


class ReductionError(ValueError):
    """Raised when an event cannot be reduced against the supplied state."""


def apply_event(state: WorldState, event: Event) -> WorldState:
    new_state = state.model_copy(deep=True)
    new_state.turn_number = max(new_state.turn_number, event.turn_number)

    if isinstance(event, PlayerMoved):
        new_state.entities[event.entity_id].state.current_location = event.to_location
    elif isinstance(event, NPCMoved):
        npc = new_state.entities[event.npc_id]
        if not isinstance(npc, NPC):
            raise ReductionError("NPCMoved target is not an NPC")
        npc.state.current_location = event.to_location
    elif isinstance(event, NPCLocationMapped):
        npc = new_state.entities[event.npc_id]
        if not isinstance(npc, NPC):
            raise ReductionError("NPCLocationMapped target is not an NPC")
        npc.knowledge.mapped_locations.add(event.location_id)
    elif isinstance(event, NPCItemLocationObserved):
        npc = new_state.entities[event.npc_id]
        if not isinstance(npc, NPC):
            raise ReductionError("NPCItemLocationObserved target is not an NPC")
        if event.present:
            npc.knowledge.item_location_beliefs[event.item_id] = event.location_id
        elif npc.knowledge.item_location_beliefs.get(event.item_id) == event.location_id:
            del npc.knowledge.item_location_beliefs[event.item_id]
        else:
            raise ReductionError("negative item observation does not match NPC belief")
    elif isinstance(event, NPCFactShared):
        receiver = new_state.entities[event.receiver_npc_id]
        if not isinstance(receiver, NPC):
            raise ReductionError("NPCFactShared receiver is not an NPC")
        receiver.knowledge.facts_known.add(event.fact_id)
    elif isinstance(event, NPCGoalCompleted):
        npc = new_state.entities[event.npc_id]
        if not isinstance(npc, NPC):
            raise ReductionError("NPCGoalCompleted target is not an NPC")
        npc.completed_goal_ids.add(event.goal_id)
    elif isinstance(event, ItemAcquired):
        item = new_state.items[event.item_id]
        if item.owner_id is not None and item.owner_id in new_state.entities:
            previous = new_state.entities[item.owner_id].state.inventory
            if event.item_id in previous:
                previous.remove(event.item_id)
        item.owner_id = event.actor_id
        item.location_id = None
        inventory = new_state.entities[event.actor_id].state.inventory
        if event.item_id not in inventory:
            inventory.append(event.item_id)
    elif isinstance(event, ItemDropped):
        item = new_state.items[event.item_id]
        inventory = new_state.entities[event.actor_id].state.inventory
        if event.item_id in inventory:
            inventory.remove(event.item_id)
        item.owner_id = None
        item.location_id = event.to_location
    elif isinstance(event, CharacterDamaged):
        char = new_state.entities[event.entity_id].state
        char.health = max(0, char.health - event.amount)
        if char.health == 0:
            char.alive = False
            char.conscious = False
    elif isinstance(event, CharacterHealed):
        char = new_state.entities[event.entity_id].state
        if not char.alive:
            raise ReductionError("healing cannot resurrect a dead character")
        char.health = min(10, char.health + event.amount)
    elif isinstance(event, (FactDiscovered, FactInferred)):
        if event.observer_id == new_state.player_id:
            new_state.player_known_facts.add(event.fact_id)
        else:
            observer = new_state.entities[event.observer_id]
            if not isinstance(observer, NPC):
                raise ReductionError("non-player observer must be an NPC")
            observer.knowledge.facts_known.add(event.fact_id)
    elif isinstance(event, NPCLearnedFact):
        npc = new_state.entities[event.npc_id]
        if not isinstance(npc, NPC):
            raise ReductionError("NPCLearnedFact target is not an NPC")
        npc.knowledge.facts_known.add(event.fact_id)
    elif isinstance(event, RelationshipChanged):
        rule_error = DialogueRelationshipPolicy.validate_rule_event(new_state, event)
        if rule_error is not None:
            raise ReductionError(rule_error)
        source = new_state.entities[event.source_id]
        if not isinstance(source, NPC):
            raise ReductionError("relationship source is not an NPC")
        current = source.relationships.get(event.target_id, 0)
        source.relationships[event.target_id] = max(-100, min(100, current + event.delta))
        if event.rule_id is not None:
            rule = next(
                rule
                for rule in new_state.dialogue_relationship_rules
                if rule.id == event.rule_id
            )
            if rule.once:
                new_state.applied_dialogue_relationship_rule_ids.add(rule.id)
    elif isinstance(event, TimeAdvanced):
        new_state.clock = new_state.clock.advanced(event.minutes)
    elif isinstance(event, SimulationCycleProcessed):
        new_state.simulation.next_due_absolute_minute = (
            event.scheduled_absolute_minute + new_state.simulation.cadence_minutes
        )
    elif isinstance(event, ScheduledLocationConditionApplied):
        activation_index = next(
            (
                idx
                for idx, activation in enumerate(new_state.scheduled_location_conditions)
                if activation.id == event.scheduled_event_id
            ),
            None,
        )
        if activation_index is None:
            raise ReductionError("scheduled location condition no longer exists")
        scheduled_activation = new_state.scheduled_location_conditions[activation_index]
        location = new_state.locations[scheduled_activation.location_id]
        location.active_conditions[scheduled_activation.condition.code] = (
            scheduled_activation.condition.model_copy(deep=True)
        )
        expiry_minute = scheduled_activation.expiry_absolute_minute
        if expiry_minute is not None:
            new_state.scheduled_location_condition_expirations.append(
                ScheduledLocationConditionExpiry(
                    id=scheduled_activation.expiry_event_id,
                    due_absolute_minute=expiry_minute,
                    location_id=scheduled_activation.location_id,
                    condition_code=scheduled_activation.condition.code,
                )
            )
        del new_state.scheduled_location_conditions[activation_index]
    elif isinstance(event, ScheduledLocationConditionExpired):
        expiry_index = next(
            (
                idx
                for idx, expiry in enumerate(
                    new_state.scheduled_location_condition_expirations
                )
                if expiry.id == event.scheduled_event_id
            ),
            None,
        )
        if expiry_index is None:
            raise ReductionError("scheduled location condition expiry no longer exists")
        scheduled_expiry = new_state.scheduled_location_condition_expirations[expiry_index]
        location = new_state.locations[scheduled_expiry.location_id]
        if scheduled_expiry.condition_code not in location.active_conditions:
            raise ReductionError("scheduled location condition is not active")
        del location.active_conditions[scheduled_expiry.condition_code]
        del new_state.scheduled_location_condition_expirations[expiry_index]
    elif isinstance(event, StatusApplied):
        char = new_state.entities[event.entity_id].state
        if all(status.code != event.code for status in char.status_conditions):
            char.status_conditions.append(
                StatusCondition(
                    code=event.code,
                    name=event.name,
                    incapacitating=event.incapacitating,
                )
            )
    else:  # pragma: no cover - exhaustive union guard
        raise ReductionError(f"unsupported event {type(event)!r}")
    return new_state


def replay(initial_state: WorldState, events: list[Event]) -> WorldState:
    state = initial_state.model_copy(deep=True)
    for event in events:
        state = apply_event(state, event)
    return state