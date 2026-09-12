from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from emergent_rpg.domain.events import (
    Event,
    FactDiscovered,
    ItemAcquired,
    NPCFactShared,
    NPCGoalCompleted,
    NPCItemDelivered,
    NPCItemLocationObserved,
    NPCLocationMapped,
    NPCMoved,
    RelationshipChanged,
)
from emergent_rpg.domain.models import NPC, NPCGoal, WorldState
from emergent_rpg.domain.npc_actions import (
    NPCAcquireIntent,
    NPCCompleteGoalIntent,
    NPCDeliverIntent,
    NPCInspectIntent,
    NPCIntent,
    NPCMoveIntent,
    NPCPlan,
    NPCPlanningContext,
    NPCShareFactIntent,
)
from emergent_rpg.engine.dialogue import DialogueRelationshipPolicy
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
    visible_entity_ids = {
        other.id
        for other in state.entities.values()
        if other.id != entity.id
        and other.state.current_location == location.id
        and other.state.alive
        and other.state.conscious
    }
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
        visible_entity_ids=visible_entity_ids,
        visible_npc_ids={
            other_id
            for other_id in visible_entity_ids
            if isinstance(state.entities[other_id], NPC)
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
                and goal.required_fact_ids <= context.known_fact_ids
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

        if goal.kind == "deliver_item":
            receiver_id = goal.receiver_id
            delivery_location_id = goal.delivery_location_id
            if receiver_id is None or delivery_location_id is None:
                return None
            if goal.target_id not in context.inventory_item_ids:
                return None
            if context.current_location_id != delivery_location_id:
                next_hop = deterministic_next_hop(
                    context.current_location_id,
                    delivery_location_id,
                    context.known_routes,
                )
                if next_hop is not None:
                    return NPCMoveIntent(goal_id=goal.id, destination_id=next_hop)
                return None
            if receiver_id in context.visible_entity_ids:
                return NPCDeliverIntent(
                    goal_id=goal.id,
                    item_id=goal.target_id,
                    receiver_id=receiver_id,
                )
            return None

        if goal.kind in {"investigate_item", "acquire_item"}:
            if goal.kind == "investigate_item":
                available = context.visible_item_ids | context.inventory_item_ids
                if goal.target_id in available:
                    return NPCInspectIntent(goal_id=goal.id, item_id=goal.target_id)
            else:
                if goal.target_id in context.inventory_item_ids:
                    return NPCCompleteGoalIntent(goal_id=goal.id)
                if goal.target_id in context.visible_item_ids:
                    return NPCAcquireIntent(goal_id=goal.id, item_id=goal.target_id)

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
            missing_required_facts = goal.required_fact_ids - entity.knowledge.facts_known
            if missing_required_facts:
                return NPCActionResult(
                    accepted=False,
                    reason="NPC goal prerequisites are not known.",
                )

            if isinstance(intent, NPCMoveIntent):
                result = self._resolve_move(state, entity, goal, intent, turn_number)
            elif isinstance(intent, NPCAcquireIntent):
                result = self._resolve_acquire(state, entity, goal, intent, turn_number)
            elif isinstance(intent, NPCDeliverIntent):
                result = self._resolve_deliver(state, entity, goal, intent, turn_number)
            elif isinstance(intent, NPCInspectIntent):
                result = self._resolve_inspect(state, entity, goal, intent, turn_number)
            elif isinstance(intent, NPCCompleteGoalIntent):
                result = self._resolve_completion(state, entity, goal, turn_number)
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
        events: list[Event] = [
            NPCFactShared(
                turn_number=turn_number,
                source_npc_id=source.id,
                receiver_npc_id=receiver.id,
                fact_id=fact_id,
            )
        ]
        relationship_rule = DialogueRelationshipPolicy.next_rule(
            state,
            source.id,
            receiver.id,
            additional_listener_fact_ids={fact_id},
        )
        if relationship_rule is not None:
            events.append(
                RelationshipChanged(
                    turn_number=turn_number,
                    source_id=source.id,
                    target_id=receiver.id,
                    delta=relationship_rule.delta,
                    rule_id=relationship_rule.id,
                )
            )
        return NPCActionResult(
            accepted=True,
            emitted_events=events,
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
            if (
                goal.id in npc.completed_goal_ids
                or goal.kind not in {"investigate_item", "acquire_item"}
                or not goal.required_fact_ids <= npc.knowledge.facts_known
            ):
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
        elif goal.kind == "deliver_item":
            item = state.items.get(goal.target_id)
            if item is None:
                return NPCActionResult(accepted=False, reason="Delivery item does not exist.")
            if item.owner_id != npc.id or goal.target_id not in npc.state.inventory:
                return NPCActionResult(accepted=False, reason="NPC does not own the delivery item.")
            if goal.delivery_location_id is None:
                return NPCActionResult(accepted=False, reason="Delivery location is not configured.")
            target_location = goal.delivery_location_id
        elif goal.kind in {"investigate_item", "acquire_item"}:
            if goal.kind == "investigate_item":
                missing_reason = "Investigation target does not exist."
                local_reason = "Investigation target is already accessible here."
                unknown_reason = "NPC does not know where the investigation target is."
            else:
                missing_reason = "Acquisition target does not exist."
                local_reason = "Acquisition target is already accessible here."
                unknown_reason = "NPC does not know where the acquisition target is."

            item = state.items.get(goal.target_id)
            if item is None:
                return NPCActionResult(accepted=False, reason=missing_reason)
            if item.owner_id == npc.id or item.location_id == location.id:
                return NPCActionResult(accepted=False, reason=local_reason)
            remembered_location = npc.knowledge.item_location_beliefs.get(goal.target_id)
            if remembered_location is None:
                return NPCActionResult(accepted=False, reason=unknown_reason)
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
    def _resolve_acquire(
        cls,
        state: WorldState,
        npc: NPC,
        goal: NPCGoal,
        intent: NPCAcquireIntent,
        turn_number: int,
    ) -> NPCActionResult:
        if goal.kind != "acquire_item" or goal.target_id != intent.item_id:
            return NPCActionResult(
                accepted=False,
                reason="Acquisition does not satisfy the NPC goal.",
            )
        item = state.items.get(intent.item_id)
        if item is None:
            return NPCActionResult(accepted=False, reason="Acquisition target does not exist.")
        if item.owner_id == npc.id:
            return NPCActionResult(
                accepted=False,
                reason="NPC already owns the acquisition target.",
            )
        if item.owner_id is not None:
            return NPCActionResult(
                accepted=False,
                reason="Acquisition target is owned by someone else.",
            )
        if item.location_id != npc.state.current_location:
            return NPCActionResult(accepted=False, reason="Acquisition target is not here.")
        if "portable" not in item.flags:
            return NPCActionResult(accepted=False, reason="Acquisition target is not portable.")

        location_id = npc.state.current_location
        events = cls._map_if_new(npc, location_id, turn_number)
        events.append(
            ItemAcquired(
                turn_number=turn_number,
                item_id=item.id,
                actor_id=npc.id,
                from_location=location_id,
            )
        )
        events.append(
            NPCItemLocationObserved(
                turn_number=turn_number,
                npc_id=npc.id,
                item_id=item.id,
                location_id=location_id,
                present=False,
            )
        )
        events.append(
            NPCGoalCompleted(
                turn_number=turn_number,
                npc_id=npc.id,
                goal_id=goal.id,
                method="acquired_item",
                evidence_id=item.id,
            )
        )
        return NPCActionResult(
            accepted=True,
            emitted_events=events,
            tags={"npc_item", "npc_acquisition"},
        )

    @classmethod
    def _resolve_deliver(
        cls,
        state: WorldState,
        npc: NPC,
        goal: NPCGoal,
        intent: NPCDeliverIntent,
        turn_number: int,
    ) -> NPCActionResult:
        if (
            goal.kind != "deliver_item"
            or goal.target_id != intent.item_id
            or goal.receiver_id != intent.receiver_id
        ):
            return NPCActionResult(
                accepted=False,
                reason="Delivery does not satisfy the NPC goal.",
            )
        item = state.items.get(intent.item_id)
        if item is None:
            return NPCActionResult(accepted=False, reason="Delivery item does not exist.")
        if item.owner_id != npc.id or item.id not in npc.state.inventory:
            return NPCActionResult(accepted=False, reason="NPC does not own the delivery item.")
        receiver = state.entities.get(intent.receiver_id)
        if receiver is None or receiver.id == npc.id:
            return NPCActionResult(accepted=False, reason="Delivery receiver does not exist.")
        if not receiver.state.alive or not receiver.state.conscious:
            return NPCActionResult(accepted=False, reason="Delivery receiver cannot interact.")
        if goal.delivery_location_id != npc.state.current_location:
            return NPCActionResult(accepted=False, reason="NPC is not at the delivery location.")
        if receiver.state.current_location != npc.state.current_location:
            return NPCActionResult(accepted=False, reason="Delivery receiver is not here.")
        if "portable" not in item.flags:
            return NPCActionResult(accepted=False, reason="Delivery item is not portable.")

        events = cls._map_if_new(npc, npc.state.current_location, turn_number)
        events.append(
            NPCItemDelivered(
                turn_number=turn_number,
                source_npc_id=npc.id,
                receiver_id=receiver.id,
                item_id=item.id,
                goal_id=goal.id,
            )
        )
        events.append(
            NPCGoalCompleted(
                turn_number=turn_number,
                npc_id=npc.id,
                goal_id=goal.id,
                method="delivered_item",
                evidence_id=item.id,
            )
        )
        return NPCActionResult(
            accepted=True,
            emitted_events=events,
            tags={"npc_item", "npc_delivery"},
        )

    @classmethod
    def _resolve_inspect(
        cls,
        state: WorldState,
        npc: NPC,
        goal: NPCGoal,
        intent: NPCInspectIntent,
        turn_number: int,
    ) -> NPCActionResult:
        if goal.target_id != intent.item_id or goal.kind not in {
            "investigate_item",
            "acquire_item",
        }:
            return NPCActionResult(
                accepted=False,
                reason="Inspection does not satisfy the NPC goal.",
            )
        item = state.items.get(intent.item_id)
        if item is None:
            return NPCActionResult(accepted=False, reason="Inspection target does not exist.")

        if goal.kind == "acquire_item":
            if item.owner_id == npc.id:
                return NPCActionResult(
                    accepted=False,
                    reason="NPC already owns the acquisition target.",
                )
            if item.location_id == npc.state.current_location:
                return NPCActionResult(
                    accepted=False,
                    reason="Acquisition target is visible and should be acquired.",
                )
            remembered_location = npc.knowledge.item_location_beliefs.get(item.id)
            if remembered_location == npc.state.current_location:
                return NPCActionResult(
                    accepted=True,
                    reason="Item is no longer at the remembered location.",
                    tags={"npc_search"},
                )
            return NPCActionResult(accepted=False, reason="Acquisition target is not accessible.")

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
        state: WorldState,
        npc: NPC,
        goal: NPCGoal,
        turn_number: int,
    ) -> NPCActionResult:
        method: Literal["reached_location", "acquired_item", "delivered_item"]
        if goal.kind == "reach_location" and npc.state.current_location == goal.target_id:
            method = "reached_location"
            evidence_id = goal.target_id
        elif goal.kind == "acquire_item":
            item = state.items.get(goal.target_id)
            if item is None or item.owner_id != npc.id or goal.target_id not in npc.state.inventory:
                return NPCActionResult(accepted=False, reason="NPC goal is not satisfied yet.")
            method = "acquired_item"
            evidence_id = item.id
        elif goal.kind == "deliver_item":
            item = state.items.get(goal.target_id)
            receiver = state.entities.get(goal.receiver_id or "")
            if (
                item is None
                or receiver is None
                or item.owner_id != receiver.id
                or item.id not in receiver.state.inventory
            ):
                return NPCActionResult(accepted=False, reason="NPC goal is not satisfied yet.")
            method = "delivered_item"
            evidence_id = item.id
        else:
            return NPCActionResult(accepted=False, reason="NPC goal is not satisfied yet.")

        events = cls._map_if_new(npc, npc.state.current_location, turn_number)
        events.append(
            NPCGoalCompleted(
                turn_number=turn_number,
                npc_id=npc.id,
                goal_id=goal.id,
                method=method,
                evidence_id=evidence_id,
            )
        )
        return NPCActionResult(accepted=True, emitted_events=events, tags={"npc_goal"})