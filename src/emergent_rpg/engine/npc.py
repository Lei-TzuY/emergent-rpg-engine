from __future__ import annotations

from pydantic import BaseModel, Field

from emergent_rpg.domain.events import (
    Event,
    FactDiscovered,
    NPCFactShared,
    NPCGoalCompleted,
    NPCItemLocationObserved,
    NPCLocationMapped,
    NPCMoved,
)
from emergent_rpg.domain.models import NPC, NPCGoal, WorldState
from emergent_rpg.domain.npc_actions import (
    NPCCompleteGoalIntent,
    NPCInspectIntent,
    NPCIntent,
    NPCMoveIntent,
    NPCPlan,
    NPCPlanningContext,
    NPCShareFactIntent,
)
from emergent_rpg.engine.environment import EnvironmentalRules
from emergent_rpg.engine.mystery import MysteryGraph
from emergent_rpg.engine.navigation import deterministic_next_hop
from emergent_rpg.engine.social import SocialDisclosurePolicy


class NPCActionResult(BaseModel):
    accepted: bool
    reason: str | None = None
    emitted_events: list[Event] = Field(default_factory=list)
    tags: set[str] = Field(default_factory=set)


class NPCDecision(BaseModel):
    npc_id: str
    intent: NPCIntent
    accepted: bool
    reason: str | None = None


class NPCPhaseResult(BaseModel):
    actions_attempted: int = 0
    actions_executed: int = 0
    decisions: list[NPCDecision] = Field(default_factory=list)
    emitted_events: list[Event] = Field(default_factory=list)
    involved_npc_ids: set[str] = Field(default_factory=set)


def build_npc_planning_context(state: WorldState, npc_id: str) -> NPCPlanningContext:
    entity = state.entities.get(npc_id)
    if not isinstance(entity, NPC):
        raise ValueError(f"{npc_id} is not an NPC")
    location = state.locations[entity.state.current_location]
    known_ids = set(entity.knowledge.facts_known)
    accessible_exits = EnvironmentalRules().accessible_exits(state, location.id)
    known_routes = {
        mapped_location_id: set(state.locations[mapped_location_id].exits.values())
        for mapped_location_id in sorted(entity.knowledge.mapped_locations)
        if mapped_location_id in state.locations
    }
    # The NPC can directly observe the exits at its current location. Active
    # closures replace that local adjacency, while remote mapped locations keep
    # only the static topology the NPC already knows.
    known_routes[location.id] = set(accessible_exits.values())
    return NPCPlanningContext(
        npc_id=entity.id,
        npc_name=entity.name,
        current_location_id=location.id,
        exits=accessible_exits,
        known_routes=known_routes,
        known_item_locations=dict(entity.knowledge.item_location_beliefs),
        visible_item_ids={
            item.id for item in state.items.values() if item.location_id == location.id
        },
        inventory_item_ids=set(entity.state.inventory),
        visible_npc_ids={
            other.id
            for other in state.entities.values()
            if isinstance(other, NPC)
            and other.id != entity.id
            and other.state.current_location == location.id
            and other.state.alive
            and other.state.conscious
        },
        goals=list(entity.planning_goals),
        completed_goal_ids=set(entity.completed_goal_ids),
        known_fact_ids=known_ids,
        known_fact_propositions={
            fact_id: state.facts[fact_id].proposition for fact_id in sorted(known_ids)
        },
        beliefs=dict(entity.knowledge.beliefs),
        relationships=dict(entity.relationships),
        movement_blocked=any(
            condition.incapacitating for condition in entity.state.status_conditions
        ),
    )


class DeterministicNPCPlanner:
    def plan(self, context: NPCPlanningContext, max_steps: int = 1) -> NPCPlan:
        if not 1 <= max_steps <= 3:
            raise ValueError("max_steps must be between 1 and 3")
        if context.movement_blocked:
            return NPCPlan(npc_id=context.npc_id)

        goals = sorted(
            (
                goal
                for goal in context.goals
                if goal.id not in context.completed_goal_ids
            ),
            key=lambda goal: (-goal.priority, goal.id),
        )
        intents: list[NPCIntent] = []
        for goal in goals:
            intent = self._intent_for_goal(context, goal)
            if intent is not None:
                intents.append(intent)
            if len(intents) >= max_steps:
                break
        return NPCPlan(npc_id=context.npc_id, intents=intents)

    @staticmethod
    def plan_fact_share(context: NPCPlanningContext) -> NPCShareFactIntent | None:
        if context.movement_blocked or not context.known_fact_ids:
            return None
        if not context.visible_npc_ids:
            return None
        receiver_id = min(
            context.visible_npc_ids,
            key=lambda npc_id: (-context.relationships.get(npc_id, 0), npc_id),
        )
        return NPCShareFactIntent(receiver_id=receiver_id)

    @staticmethod
    def _intent_for_goal(
        context: NPCPlanningContext,
        goal: NPCGoal,
    ) -> NPCIntent | None:
        if goal.kind == "reach_location":
            if context.current_location_id == goal.target_id:
                return NPCCompleteGoalIntent(goal_id=goal.id)
            next_hop = deterministic_next_hop(
                context.current_location_id,
                goal.target_id,
                context.known_routes,
            )
            if next_hop is not None:
                return NPCMoveIntent(goal_id=goal.id, destination_id=next_hop)
            return None

        if goal.kind == "investigate_item":
            available = context.visible_item_ids | context.inventory_item_ids
            if goal.target_id in available:
                return NPCInspectIntent(goal_id=goal.id, item_id=goal.target_id)
            remembered_location = context.known_item_locations.get(goal.target_id)
            if remembered_location is None:
                return None
            if remembered_location == context.current_location_id:
                # The item is not visible but this is where the NPC remembers it.
                # Inspect becomes an explicit local search that can invalidate the
                # stale belief through a typed observation event.
                return NPCInspectIntent(goal_id=goal.id, item_id=goal.target_id)
            next_hop = deterministic_next_hop(
                context.current_location_id,
                remembered_location,
                context.known_routes,
            )
            if next_hop is not None:
                return NPCMoveIntent(goal_id=goal.id, destination_id=next_hop)
        return None


class DeterministicNPCResolver:
    def resolve(
        self,
        state: WorldState,
        npc_id: str,
        intent: NPCIntent,
        turn_number: int,
    ) -> NPCActionResult:
        entity = state.entities.get(npc_id)
        if not isinstance(entity, NPC):
            return NPCActionResult(accepted=False, reason="NPC does not exist.")
        if not entity.state.alive or not entity.state.conscious:
            return NPCActionResult(accepted=False, reason="NPC cannot act right now.")

        if isinstance(intent, NPCShareFactIntent):
            result = self._resolve_share(state, entity, intent, turn_number)
        else:
            goal = self._goal(entity, intent.goal_id)
            if goal is None:
                return NPCActionResult(accepted=False, reason="NPC goal does not exist.")
            if goal.id in entity.completed_goal_ids:
                return NPCActionResult(accepted=False, reason="NPC goal is already complete.")

            if isinstance(intent, NPCMoveIntent):
                result = self._resolve_move(state, entity, goal, intent, turn_number)
            elif isinstance(intent, NPCInspectIntent):
                result = self._resolve_inspect(state, entity, goal, intent, turn_number)
            elif isinstance(intent, NPCCompleteGoalIntent):
                result = self._resolve_completion(entity, goal, turn_number)
            else:
                return NPCActionResult(accepted=False, reason="Unsupported NPC intent.")

        if not result.accepted:
            return result
        observation_events = self._tracked_item_observations(state, entity, turn_number)
        if not observation_events:
            return result
        return result.model_copy(
            update={
                "emitted_events": [*observation_events, *result.emitted_events],
                "tags": result.tags | {"npc_observation"},
            }
        )

    @staticmethod
    def _goal(npc: NPC, goal_id: str) -> NPCGoal | None:
        return next((goal for goal in npc.planning_goals if goal.id == goal_id), None)

    @staticmethod
    def _resolve_share(
        state: WorldState,
        source: NPC,
        intent: NPCShareFactIntent,
        turn_number: int,
    ) -> NPCActionResult:
        receiver = state.entities.get(intent.receiver_id)
        if not isinstance(receiver, NPC) or receiver.id == source.id:
            return NPCActionResult(accepted=False, reason="Fact-sharing receiver is not an NPC.")
        if not receiver.state.alive or not receiver.state.conscious:
            return NPCActionResult(accepted=False, reason="Fact-sharing receiver cannot interact.")
        if receiver.state.current_location != source.state.current_location:
            return NPCActionResult(accepted=False, reason="Fact-sharing receiver is not here.")

        new_fact_ids = sorted(
            fact_id
            for fact_id in source.knowledge.facts_known - receiver.knowledge.facts_known
            if fact_id in state.facts
        )
        if not new_fact_ids:
            return NPCActionResult(accepted=False, reason="NPC has no new fact to share.")
        shareable = [
            fact_id
            for fact_id in new_fact_ids
            if SocialDisclosurePolicy.can_disclose(
                state.facts[fact_id],
                source,
                receiver.id,
            )
        ]
        if not shareable:
            return NPCActionResult(
                accepted=False,
                reason="NPC relationship is below disclosure requirements.",
            )
        fact_id = shareable[0]
        return NPCActionResult(
            accepted=True,
            emitted_events=[
                NPCFactShared(
                    turn_number=turn_number,
                    source_npc_id=source.id,
                    receiver_npc_id=receiver.id,
                    fact_id=fact_id,
                )
            ],
            tags={"npc_dialogue", "npc_fact_share"},
        )

    @staticmethod
    def _map_if_new(npc: NPC, location_id: str, turn_number: int) -> list[Event]:
        if location_id in npc.knowledge.mapped_locations:
            return []
        return [
            NPCLocationMapped(
                turn_number=turn_number,
                npc_id=npc.id,
                location_id=location_id,
            )
        ]

    @staticmethod
    def _tracked_item_observations(
        state: WorldState,
        npc: NPC,
        turn_number: int,
    ) -> list[Event]:
        location_id = npc.state.current_location
        observations: list[Event] = []
        seen_item_ids: set[str] = set()
        goals = sorted(npc.planning_goals, key=lambda goal: goal.id)
        for goal in goals:
            if goal.id in npc.completed_goal_ids or goal.kind != "investigate_item":
                continue
            item_id = goal.target_id
            if item_id in seen_item_ids:
                continue
            seen_item_ids.add(item_id)
            item = state.items.get(item_id)
            if item is None:
                continue
            remembered_location = npc.knowledge.item_location_beliefs.get(item_id)
            if item.location_id == location_id:
                if remembered_location != location_id:
                    observations.append(
                        NPCItemLocationObserved(
                            turn_number=turn_number,
                            npc_id=npc.id,
                            item_id=item_id,
                            location_id=location_id,
                            present=True,
                        )
                    )
            elif remembered_location == location_id:
                observations.append(
                    NPCItemLocationObserved(
                        turn_number=turn_number,
                        npc_id=npc.id,
                        item_id=item_id,
                        location_id=location_id,
                        present=False,
                    )
                )
        return observations

    @classmethod
    def _resolve_move(
        cls,
        state: WorldState,
        npc: NPC,
        goal: NPCGoal,
        intent: NPCMoveIntent,
        turn_number: int,
    ) -> NPCActionResult:
        if any(condition.incapacitating for condition in npc.state.status_conditions):
            return NPCActionResult(accepted=False, reason="NPC movement is blocked.")
        location = state.locations[npc.state.current_location]
        if intent.destination_id not in location.exits.values():
            return NPCActionResult(accepted=False, reason="Destination is not a local exit.")
        access = EnvironmentalRules().route_access(state, location.id, intent.destination_id)
        if not access.allowed:
            blockers = ", ".join(access.condition_names)
            return NPCActionResult(
                accepted=False,
                reason=f"NPC route is blocked by: {blockers}.",
            )

        if goal.kind == "reach_location":
            target_location = goal.target_id
        elif goal.kind == "investigate_item":
            item = state.items.get(goal.target_id)
            if item is None:
                return NPCActionResult(
                    accepted=False,
                    reason="Investigation target does not exist.",
                )
            if item.owner_id == npc.id or item.location_id == location.id:
                return NPCActionResult(
                    accepted=False,
                    reason="Investigation target is already accessible here.",
                )
            remembered_location = npc.knowledge.item_location_beliefs.get(goal.target_id)
            if remembered_location is None:
                return NPCActionResult(
                    accepted=False,
                    reason="NPC does not know where the investigation target is.",
                )
            target_location = remembered_location
        else:
            return NPCActionResult(accepted=False, reason="Move does not satisfy the NPC goal.")

        context = build_npc_planning_context(state, npc.id)
        expected_next_hop = deterministic_next_hop(
            context.current_location_id,
            target_location,
            context.known_routes,
        )
        if expected_next_hop != intent.destination_id:
            return NPCActionResult(
                accepted=False,
                reason="Move does not match the NPC's deterministic known route.",
            )

        events = cls._map_if_new(npc, location.id, turn_number)
        events.append(
            NPCMoved(
                turn_number=turn_number,
                npc_id=npc.id,
                from_location=location.id,
                to_location=intent.destination_id,
            )
        )
        events.extend(cls._map_if_new(npc, intent.destination_id, turn_number))
        if goal.kind == "reach_location" and intent.destination_id == target_location:
            events.append(
                NPCGoalCompleted(
                    turn_number=turn_number,
                    npc_id=npc.id,
                    goal_id=goal.id,
                    method="reached_location",
                    evidence_id=intent.destination_id,
                )
            )
        return NPCActionResult(accepted=True, emitted_events=events, tags={"npc_movement"})

    @classmethod
    def _resolve_inspect(
        cls,
        state: WorldState,
        npc: NPC,
        goal: NPCGoal,
        intent: NPCInspectIntent,
        turn_number: int,
    ) -> NPCActionResult:
        if goal.kind != "investigate_item" or goal.target_id != intent.item_id:
            return NPCActionResult(
                accepted=False,
                reason="Inspection does not satisfy the NPC goal.",
            )
        item = state.items.get(intent.item_id)
        if item is None:
            return NPCActionResult(accepted=False, reason="Inspection target does not exist.")
        available = item.owner_id == npc.id or item.location_id == npc.state.current_location
        if not available:
            remembered_location = npc.knowledge.item_location_beliefs.get(item.id)
            if remembered_location == npc.state.current_location:
                return NPCActionResult(
                    accepted=True,
                    reason="Item is no longer at the remembered location.",
                    tags={"npc_search"},
                )
            return NPCActionResult(accepted=False, reason="Inspection target is not accessible.")

        events = cls._map_if_new(npc, npc.state.current_location, turn_number)
        if (
            item.reveals_fact_id
            and item.reveals_fact_id not in npc.knowledge.facts_known
            and MysteryGraph.can_discover_fact(state, item.reveals_fact_id, npc.id)
        ):
            events.append(
                FactDiscovered(
                    turn_number=turn_number,
                    fact_id=item.reveals_fact_id,
                    observer_id=npc.id,
                )
            )
        events.append(
            NPCGoalCompleted(
                turn_number=turn_number,
                npc_id=npc.id,
                goal_id=goal.id,
                method="inspected_item",
                evidence_id=item.id,
            )
        )
        return NPCActionResult(accepted=True, emitted_events=events, tags={"npc_inspection"})

    @classmethod
    def _resolve_completion(
        cls,
        npc: NPC,
        goal: NPCGoal,
        turn_number: int,
    ) -> NPCActionResult:
        if goal.kind != "reach_location" or npc.state.current_location != goal.target_id:
            return NPCActionResult(accepted=False, reason="NPC goal is not satisfied yet.")
        events = cls._map_if_new(npc, npc.state.current_location, turn_number)
        events.append(
            NPCGoalCompleted(
                turn_number=turn_number,
                npc_id=npc.id,
                goal_id=goal.id,
                method="reached_location",
                evidence_id=goal.target_id,
            )
        )
        return NPCActionResult(accepted=True, emitted_events=events, tags={"npc_goal"})
