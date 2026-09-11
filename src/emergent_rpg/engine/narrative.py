from __future__ import annotations

from pydantic import BaseModel, Field

from emergent_rpg.domain.actions import PlayerAction
from emergent_rpg.domain.events import FactDiscovered
from emergent_rpg.domain.models import NPC, WorldState
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
        allowed: set[str] = set(state_after.player_known_facts)
        for entity_id in participants:
            entity = state_after.entities.get(entity_id)
            if isinstance(entity, NPC):
                allowed.update(entity.knowledge.facts_known)

        discovered = [
            event.fact_id
            for event in result.emitted_events
            if isinstance(event, FactDiscovered) and event.observer_id == state_after.player_id
        ]
        if discovered:
            # Facts newly learned by the player were supported by resolver observations/events,
            # not invented by narration.
            fact_reveals[state_after.player_id] = discovered

        forbidden = sorted(set(state_after.facts) - allowed)
        return ScenePlan(
            objective=f"Resolve {action.kind} without inventing state changes",
            participating_entities=participants,
            relevant_facts=sorted(allowed),
            events_that_occurred=[event.type for event in result.emitted_events],
            information_allowed_to_be_revealed=sorted(allowed),
            information_forbidden_to_reveal=forbidden,
            observations=result.observations,
            fact_reveals=fact_reveals,
        )

    def validate(self, state: WorldState, plan: ScenePlan) -> ValidationReport:
        return validate_scene_participation(
            state,
            plan.participating_entities,
            plan.fact_reveals,
        )
