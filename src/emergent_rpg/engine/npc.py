from __future__ import annotations

from pydantic import BaseModel, Field

from emergent_rpg.domain.events import (
    Event,
    FactDiscovered,
    NPCGoalCompleted,
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
)
from emergent_rpg.engine.environment import EnvironmentalRules
from emergent_rpg.engine.mystery import MysteryGraph
from emergent_rpg.engine.navigation import deterministic_next_hop


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

        goal = self._goal(entity, intent.goal_id)
        if goal is None:
            return NPCActionResult(accepted=False, reason="NPC goal does not exist.")
        if goal.id in entity.completed_goal_ids:
            return NPCActionResult(accepted=False, reason="NPC goal is already complete.")

        if isinstance(intent, NPCMoveIntent):
            return self._resolve_move(state, entity, goal, intent, turn_number)
        if isinstance(intent, NPCInspectIntent):
            return self._resolve_inspect(state, entity, goal, intent, turn_number)
        if isinstance(intent, NPCCompleteGoalIntent):
            return self._resolve_completion(entity, goal, turn_number)
        return NPCActionResult(accepted=False, reason="Unsupported NPC intent.")

    @staticmethod
    def _goal(npc: NPC, goal_id: str) -> NPCGoal | None:
        return next((goal for goal in npc.planning_goals if goal.id == goal_id), None)

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

    @classmethod
    def _resolve_move(
        cls,
        state: WorldState,
        npc: NPC,
        goal: NPCGoal,
        intent: NPCMoveIntent,
        turn_number: int,
    ) -> NPCActionResult:
        if goal.kind != "reach_location":
            return NPCActionResult(accepted=False, reason="Move does not satisfy the NPC goal.")
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

        context = build_npc_planning_context(state, npc.id)
        expected_next_hop = deterministic_next_hop(
            context.current_location_id,
            goal.target_id,
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
        if intent.destination_id == goal.target_id:
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
