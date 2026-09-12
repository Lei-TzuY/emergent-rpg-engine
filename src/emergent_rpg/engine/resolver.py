from __future__ import annotations

from pydantic import BaseModel, Field

from emergent_rpg.domain.actions import (
    FreeformAction,
    GiveAction,
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
    NPCGoalCompleted,
    PlayerItemGiven,
    PlayerMoved,
    RelationshipChanged,
    TimeAdvanced,
)
from emergent_rpg.domain.models import NPC, Fact, Item, WorldState
from emergent_rpg.engine.dialogue import DialogueRelationshipPolicy
from emergent_rpg.engine.environment import EnvironmentalRules
from emergent_rpg.engine.mystery import MysteryGraph
from emergent_rpg.engine.social import SocialDisclosurePolicy


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
            access = self.environmental_rules.route_access(state, location_id, destination)
            if not access.allowed:
                blockers = ", ".join(access.condition_names)
                destination_name = state.locations[destination].name
                return ActionResult(
                    accepted=False,
                    reason=f"The route to {destination_name} is blocked by: {blockers}.",
                )
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
            if "portable" not in item.flags:
                return ActionResult(accepted=False, reason="That item cannot be carried.")
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

        if isinstance(action, GiveAction):
            item = self._find_owned_item(state, action.item, player.id)
            if item is None:
                return ActionResult(accepted=False, reason="You do not have that item to give.")
            if "portable" not in item.flags:
                return ActionResult(accepted=False, reason="That item cannot be handed over.")
            receiver = self._find_npc(state, action.receiver, location_id)
            if receiver is None:
                return ActionResult(accepted=False, reason="That person is not here to receive it.")
            if not receiver.state.alive or not receiver.state.conscious:
                return ActionResult(
                    accepted=False,
                    reason="They cannot receive anything right now.",
                )
            events: list[Event] = [
                PlayerItemGiven(
                    turn_number=turn,
                    source_player_id=player.id,
                    receiver_npc_id=receiver.id,
                    item_id=item.id,
                )
            ]
            matching_goals = sorted(
                (
                    goal
                    for goal in receiver.planning_goals
                    if goal.kind == "acquire_item"
                    and goal.target_id == item.id
                    and goal.id not in receiver.completed_goal_ids
                    and goal.required_fact_ids <= receiver.knowledge.facts_known
                ),
                key=lambda goal: goal.id,
            )
            events.extend(
                NPCGoalCompleted(
                    turn_number=turn,
                    npc_id=receiver.id,
                    goal_id=goal.id,
                    method="acquired_item",
                    evidence_id=item.id,
                )
                for goal in matching_goals
            )
            events.append(TimeAdvanced(turn_number=turn, minutes=1))
            return ActionResult(
                accepted=True,
                emitted_events=events,
                observations=[f"You give {item.name} to {receiver.name}."],
                involved_entities={player.id, receiver.id},
                tags={"item", "handoff"},
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
                and SocialDisclosurePolicy.can_disclose(
                    state.facts[fact_id],
                    npc,
                    player.id,
                )
            )
            newly_revealed: set[str] = set()
            if revealable:
                fact_id = revealable[0]
                newly_revealed.add(fact_id)
                events.append(
                    FactDiscovered(turn_number=turn, fact_id=fact_id, observer_id=player.id)
                )
                observations.append(f'"{state.facts[fact_id].proposition}"')
            relationship_rule = DialogueRelationshipPolicy.next_rule(
                state,
                npc.id,
                player.id,
                additional_listener_fact_ids=newly_revealed,
            )
            if relationship_rule is not None:
                events.append(
                    RelationshipChanged(
                        turn_number=turn,
                        source_id=npc.id,
                        target_id=player.id,
                        delta=relationship_rule.delta,
                        rule_id=relationship_rule.id,
                    )
                )
                if relationship_rule.observation:
                    observations.append(relationship_rule.observation)
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
                    "talk, take, give, or wait in the deterministic demo."
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
    def _find_owned_item(state: WorldState, target: str, owner_id: str) -> Item | None:
        key = target.casefold().strip()
        for item in state.items.values():
            if item.owner_id == owner_id and key in {item.id.casefold(), item.name.casefold()}:
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
        tag = f"inspect:{location_id}:{target}"
        for fact in state.facts.values():
            if tag in fact.tags and MysteryGraph.can_discover_fact(state, fact.id, state.player_id):
                return fact
        return None
