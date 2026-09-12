from __future__ import annotations

from pydantic import BaseModel, Field

from emergent_rpg.domain.models import GameSession, WorldState
from emergent_rpg.engine.environment import EnvironmentalRules


class SessionCreateRequest(BaseModel):
    name: str = Field(default="Ashfall Relay", min_length=1, max_length=200)


class ActionRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4_000)


class VisibleItem(BaseModel):
    id: str
    name: str


class VisibleNPC(BaseModel):
    id: str
    name: str


class KnownFact(BaseModel):
    id: str
    proposition: str


class LocationConditionView(BaseModel):
    code: str
    name: str
    description: str
    traversal_extra_minutes: int = 0


class BlockedExitView(BaseModel):
    alias: str
    destination_id: str
    destination_name: str
    blocked_by: list[str] = Field(default_factory=list)


class PlayerStateView(BaseModel):
    turn_number: int
    time: str
    location_id: str
    location_name: str
    exits: dict[str, str]
    blocked_exits: list[BlockedExitView] = Field(default_factory=list)
    location_conditions: list[LocationConditionView] = Field(default_factory=list)
    visible_items: list[VisibleItem] = Field(default_factory=list)
    visible_npcs: list[VisibleNPC] = Field(default_factory=list)
    inventory: list[VisibleItem] = Field(default_factory=list)
    known_facts: list[KnownFact] = Field(default_factory=list)


class SessionView(BaseModel):
    session: GameSession
    state: PlayerStateView


class ActionView(BaseModel):
    accepted: bool
    reason: str | None = None
    narration: str
    state: PlayerStateView


class HistoryTurnView(BaseModel):
    turn_number: int
    raw_input: str
    accepted: bool
    reason: str | None = None
    narration: str
    location_id: str


class HistoryView(BaseModel):
    turns: list[HistoryTurnView] = Field(default_factory=list)


def project_player_state(state: WorldState) -> PlayerStateView:
    player = state.player()
    location = state.locations[player.state.current_location]
    rules = EnvironmentalRules()
    visible_items = sorted(
        (
            VisibleItem(id=item.id, name=item.name)
            for item in state.items.values()
            if item.location_id == location.id
        ),
        key=lambda item: item.name,
    )
    visible_npcs = sorted(
        (
            VisibleNPC(id=entity.id, name=entity.name)
            for entity in state.entities.values()
            if entity.kind == "npc"
            and entity.state.current_location == location.id
            and entity.state.alive
            and entity.state.conscious
        ),
        key=lambda npc: npc.name,
    )
    inventory = sorted(
        (
            VisibleItem(id=item_id, name=state.items[item_id].name)
            for item_id in player.state.inventory
        ),
        key=lambda item: item.name,
    )
    known_facts = [
        KnownFact(id=fact_id, proposition=state.facts[fact_id].proposition)
        for fact_id in sorted(state.player_known_facts)
    ]
    conditions = [
        LocationConditionView(
            code=condition.code,
            name=condition.name,
            description=condition.description,
            traversal_extra_minutes=(
                condition.traversal.extra_minutes if condition.traversal is not None else 0
            ),
        )
        for _, condition in sorted(location.active_conditions.items())
    ]
    accessible_exits = rules.accessible_exits(state, location.id)
    exits = {
        alias: state.locations[destination].name
        for alias, destination in accessible_exits.items()
    }
    blocked_exits = [
        BlockedExitView(
            alias=alias,
            destination_id=destination,
            destination_name=state.locations[destination].name,
            blocked_by=rules.route_access(state, location.id, destination).condition_names,
        )
        for alias, destination in sorted(location.exits.items())
        if not rules.route_access(state, location.id, destination).allowed
    ]
    return PlayerStateView(
        turn_number=state.turn_number,
        time=state.clock.display(),
        location_id=location.id,
        location_name=location.name,
        exits=exits,
        blocked_exits=blocked_exits,
        location_conditions=conditions,
        visible_items=visible_items,
        visible_npcs=visible_npcs,
        inventory=inventory,
        known_facts=known_facts,
    )
