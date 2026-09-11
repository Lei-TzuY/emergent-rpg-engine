from __future__ import annotations

from emergent_rpg.domain.events import (
    CharacterDamaged,
    CharacterHealed,
    Event,
    FactDiscovered,
    ItemAcquired,
    ItemDropped,
    NPCLearnedFact,
    PlayerMoved,
    RelationshipChanged,
    StatusApplied,
    TimeAdvanced,
)
from emergent_rpg.domain.models import NPC, StatusCondition, WorldState


class ReductionError(ValueError):
    """Raised when an event cannot be reduced against the supplied state."""


def apply_event(state: WorldState, event: Event) -> WorldState:
    new_state = state.model_copy(deep=True)
    new_state.turn_number = max(new_state.turn_number, event.turn_number)

    if isinstance(event, PlayerMoved):
        new_state.entities[event.entity_id].state.current_location = event.to_location
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
    elif isinstance(event, FactDiscovered):
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
        source = new_state.entities[event.source_id]
        if not isinstance(source, NPC):
            raise ReductionError("relationship source is not an NPC")
        current = source.relationships.get(event.target_id, 0)
        source.relationships[event.target_id] = max(-100, min(100, current + event.delta))
    elif isinstance(event, TimeAdvanced):
        new_state.clock = new_state.clock.advanced(event.minutes)
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
