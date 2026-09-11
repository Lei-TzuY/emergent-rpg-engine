from __future__ import annotations

from pydantic import BaseModel, Field

from emergent_rpg.domain.actions import (
    FreeformAction,
    InspectAction,
    MoveAction,
    PlayerAction,
    TakeAction,
    TalkAction,
    WaitAction,
)
from emergent_rpg.domain.events import (
    Event,
    FactDiscovered,
    ItemAcquired,
    PlayerMoved,
    RelationshipChanged,
    TimeAdvanced,
)
from emergent_rpg.domain.models import NPC, Fact, Item, WorldState
from emergent_rpg.engine.environment import EnvironmentalRules
from emergent_rpg.engine.mystery import MysteryGraph


class ActionResult(BaseModel):
    accepted: bool
    reason: str | None = None
    emitted_events: list[Event] = Field(default_factory=list)
    observations: list[str] = Field(default_factory=list)
    involved_entities: set[str] = Field(default_factory=set)
    tags: set[str] = Field(default_factory=set)


class DeterministicResolver:
    def __init__(self, environmental_rules: EnvironmentalRules | None = None) -> None:
        self.environmental_rules = environmental_rules or EnvironmentalRules()

    def resolve(self, state: WorldState, action: PlayerAction) -> ActionResult:
        turn = state.turn_number + 1
        player = state.player()
        location_id = player.state.current_location
        location = state.locations[location_id]
        incapacitated = any(s.incapacitating for s in player.state.status_conditions)

        if isinstance(action, MoveAction):
            if incapacitated:
                return ActionResult(accepted=False, reason="You cannot move while incapacitated.")
            destination = self._resolve_destination(state, location_id, action.destination)
            if destination is None:
                return ActionResult(accepted=False, reason="There is no such exit from here.")
            traversal = self.environmental_rules.traversal_cost(state, location_id)
            observations = [f"You travel to {state.locations[destination].name}."]
            tags = {"movement"}
            if traversal.extra_minutes:
                names = ", ".join(traversal.condition_names)
                observations.append(
                    f"Environmental conditions add {traversal.extra_minutes} minute(s) "
                    f"to the trip: {names}."
                )
                tags.add("environment")
            return ActionResult(
                accepted=True,
                emitted_events=[
                    PlayerMoved(
                        turn_number=turn,
                        entity_id=player.id,
                        from_location=location_id,
                        to_location=destination,
                    ),
                    TimeAdvanced(turn_number=turn, minutes=traversal.total_minutes),
                ],
                observations=observations,
                involved_entities={player.id},
                tags=tags,
            )

        if isinstance(action, TakeAction):
            item = self._find_item(state, action.target, location_id)
            if item is None or item.location_id != location_id:
                return ActionResult(accepted=False, reason="That item is not here to take.")
            events: list[Event] = [
                ItemAcquired(
                    turn_number=turn,
                    item_id=item.id,
                    actor_id=player.id,
                    from_location=location_id,
                ),
                TimeAdvanced(turn_number=turn, minutes=1),
            ]
            observations = [f"You take {item.name}."]
            if (
                item.reveals_fact_id
                and item.reveals_fact_id not in state.player_known_facts
                and MysteryGraph.can_discover_fact(state, item.reveals_fact_id, player.id)
            ):
                events.append(
                    FactDiscovered(
                        turn_number=turn,
                        fact_id=item.reveals_fact_id,
                        observer_id=player.id,
                    )
                )
                observations.append(state.facts[item.reveals_fact_id].proposition)
            return ActionResult(
                accepted=True,
                emitted_events=events,
                observations=observations,
                involved_entities={player.id},
                tags={"item"},
            )

        if isinstance(action, InspectAction):
            target = action.target.casefold().strip()
            observations: list[str] = []
            events: list[Event] = [TimeAdvanced(turn_number=turn, minutes=1)]
            item = self._find_item(state, action.target, location_id, include_owned=True)
            if item is not None:
                observations.append(item.description or f"You inspect {item.name}.")
                if (
                    item.reveals_fact_id
                    and item.reveals_fact_id not in state.player_known_facts
                    and MysteryGraph.can_discover_fact(state, item.reveals_fact_id, player.id)
                ):
                    events.append(
                        FactDiscovered(
                            turn_number=turn,
                            fact_id=item.reveals_fact_id,
                            observer_id=player.id,
                        )
                    )
                    observations.append(state.facts[item.reveals_fact_id].proposition)
            elif target in {"room", "area", "around", "here", location.name.casefold()}:
                observations.append(location.description)
            else:
                hidden_fact = self._inspection_fact(state, location_id, target)
                if hidden_fact is not None:
                    observations.append(hidden_fact.proposition)
                    if hidden_fact.id not in state.player_known_facts:
                        events.append(
                            FactDiscovered(
                                turn_number=turn,
                                fact_id=hidden_fact.id,
                                observer_id=player.id,
                            )
                        )
                else:
                    return ActionResult(accepted=False, reason="You find nothing actionable there.")
            return ActionResult(
                accepted=True,
                emitted_events=events,
                observations=observations,
                involved_entities={player.id},
                tags={"inspection"},
            )

        if isinstance(action, TalkAction):
            npc = self._find_npc(state, action.target, location_id)
            if npc is None:
                return ActionResult(accepted=False, reason="That person is not here to talk to.")
            if not npc.state.alive or not npc.state.conscious:
                return ActionResult(accepted=False, reason="They cannot respond right now.")
            observations = [f"{npc.name} considers your question carefully."]
            events: list[Event] = [TimeAdvanced(turn_number=turn, minutes=2)]
            revealable = sorted(
                fact_id
                for fact_id in npc.knowledge.facts_known - state.player_known_facts
                if MysteryGraph.can_discover_fact(state, fact_id, player.id)
            )
            if revealable:
                fact_id = revealable[0]
                events.append(
                    FactDiscovered(turn_number=turn, fact_id=fact_id, observer_id=player.id)
                )
                observations.append(f'"{state.facts[fact_id].proposition}"')
            if "fact_relay_sabotage" in state.player_known_facts and npc.id == "npc_arden":
                events.append(
                    RelationshipChanged(
                        turn_number=turn,
                        source_id=npc.id,
                        target_id=player.id,
                        delta=5,
                    )
                )
                observations.append(
                    "Arden's guarded posture eases; you have earned a little trust."
                )
            return ActionResult(
                accepted=True,
                emitted_events=events,
                observations=observations,
                involved_entities={player.id, npc.id},
                tags={"dialogue"},
            )

        if isinstance(action, WaitAction):
            return ActionResult(
                accepted=True,
                emitted_events=[TimeAdvanced(turn_number=turn, minutes=action.minutes)],
                observations=[f"You wait for {action.minutes} minutes."],
                involved_entities={player.id},
                tags={"waiting"},
            )

        if isinstance(action, FreeformAction):
            return ActionResult(
                accepted=False,
                reason=(
                    "Freeform language is preserved for a pluggable parser; use move, inspect, "
                    "talk, take, or wait in the deterministic demo."
                ),
            )
        return ActionResult(accepted=False, reason="Unsupported action.")

    @staticmethod
    def _resolve_destination(state: WorldState, location_id: str, target: str) -> str | None:
        location = state.locations[location_id]
        key = target.casefold().strip()
        for exit_name, destination in location.exits.items():
            names = {
                exit_name.casefold(),
                destination.casefold(),
                state.locations[destination].name.casefold(),
            }
            if key in names:
                return destination
        return None

    @staticmethod
    def _find_item(
        state: WorldState, target: str, location_id: str, *, include_owned: bool = False
    ) -> Item | None:
        key = target.casefold().strip()
        for item in state.items.values():
            if key not in {item.id.casefold(), item.name.casefold()}:
                continue
            if item.location_id == location_id:
                return item
            if include_owned and item.owner_id == state.player_id:
                return item
        return None

    @staticmethod
    def _find_npc(state: WorldState, target: str, location_id: str) -> NPC | None:
        key = target.casefold().strip()
        for entity in state.entities.values():
            if (
                isinstance(entity, NPC)
                and entity.state.current_location == location_id
                and key in {entity.id.casefold(), entity.name.casefold()}
            ):
                return entity
        return None

    @staticmethod
    def _inspection_fact(state: WorldState, location_id: str, target: str) -> Fact | None:
        for fact in state.facts.values():
            if (
                f"inspect:{location_id}:{target}" in fact.tags
                and MysteryGraph.can_discover_fact(state, fact.id, state.player_id)
            ):
                return fact
        return None
