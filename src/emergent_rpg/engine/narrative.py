from __future__ import annotations

from pydantic import BaseModel, Field

from emergent_rpg.domain.actions import PlayerAction
from emergent_rpg.domain.events import FactDiscovered
from emergent_rpg.domain.models import WorldState
from emergent_rpg.engine.resolver import ActionResult
from emergent_rpg.validation.models import ValidationReport
from emergent_rpg.validation.validator import validate_scene_participation


class ScenePlan(BaseModel):
    objective: str
    participating_entities: list[str]
    relevant_facts: list[str] = Field(default_factory=list)
    events_that_occurred: list[str] = Field(default_factory=list)
    information_allowed_to_be_revealed: list[str] = Field(default_factory=list)
    information_forbidden_to_reveal: list[str] = Field(default_factory=list)
    suggested_dramatic_beat: str = "grounded consequence"
    observations: list[str] = Field(default_factory=list)
    fact_reveals: dict[str, list[str]] = Field(default_factory=dict)


class DeterministicNarrativePlanner:
    def plan(
        self,
        state_before: WorldState,
        state_after: WorldState,
        action: PlayerAction,
        result: ActionResult,
    ) -> ScenePlan:
        participants = sorted(result.involved_entities)
        fact_reveals: dict[str, list[str]] = {}

        # Player-facing narration may only contain facts the player actually knows after
        # accepted events. Merely placing a knowledgeable NPC in the scene is not a transfer
        # of knowledge.
        allowed_ids = set(state_after.player_known_facts)
        allowed_propositions = [
            state_after.facts[fact_id].proposition for fact_id in sorted(allowed_ids)
        ]

        discovered = [
            event.fact_id
            for event in result.emitted_events
            if isinstance(event, FactDiscovered) and event.observer_id == state_after.player_id
        ]
        if discovered:
            fact_reveals[state_after.player_id] = discovered

        forbidden = sorted(set(state_after.facts) - allowed_ids)
        return ScenePlan(
            objective=f"Resolve {action.kind} without inventing state changes",
            participating_entities=participants,
            relevant_facts=allowed_propositions,
            events_that_occurred=[event.type for event in result.emitted_events],
            information_allowed_to_be_revealed=allowed_propositions,
            information_forbidden_to_reveal=forbidden,
            observations=result.observations,
            fact_reveals=fact_reveals,
        )

    def validate(
        self,
        state_before: WorldState,
        state_after: WorldState,
        plan: ScenePlan,
    ) -> ValidationReport:
        newly_inactive = {
            entity_id
            for entity_id in plan.participating_entities
            if entity_id in state_before.entities
            and entity_id in state_after.entities
            and state_before.entities[entity_id].state.alive
            and state_before.entities[entity_id].state.conscious
            and (
                not state_after.entities[entity_id].state.alive
                or not state_after.entities[entity_id].state.conscious
            )
        }
        return validate_scene_participation(
            state_after,
            plan.participating_entities,
            plan.fact_reveals,
            allow_inactive_participants=newly_inactive,
        )
