from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator

EntityId = str
LocationId = str
ItemId = str
FactId = str
SessionId = str


class TruthStatus(StrEnum):
    TRUE = "true"
    FALSE = "false"
    UNCERTAIN = "uncertain"


class WorldClock(BaseModel):
    day: int = Field(default=1, ge=1)
    minute_of_day: int = Field(default=8 * 60, ge=0, lt=24 * 60)

    def advanced(self, minutes: int) -> WorldClock:
        total = (self.day - 1) * 24 * 60 + self.minute_of_day + minutes
        if total < 0:
            raise ValueError("world clock cannot go backward before day 1")
        return WorldClock(day=(total // (24 * 60)) + 1, minute_of_day=total % (24 * 60))

    @property
    def absolute_minutes(self) -> int:
        return (self.day - 1) * 24 * 60 + self.minute_of_day

    def display(self) -> str:
        hour, minute = divmod(self.minute_of_day, 60)
        return f"Day {self.day}, {hour:02d}:{minute:02d}"


class StatusCondition(BaseModel):
    code: str
    name: str
    incapacitating: bool = False


class Relationship(BaseModel):
    target_id: EntityId
    score: int = Field(default=0, ge=-100, le=100)


class NPCKnowledge(BaseModel):
    facts_known: set[FactId] = Field(default_factory=set)
    beliefs: dict[str, str] = Field(default_factory=dict)
    mapped_locations: set[LocationId] = Field(default_factory=set)
    item_location_beliefs: dict[ItemId, LocationId] = Field(default_factory=dict)


class CharacterState(BaseModel):
    health: int = Field(default=10, ge=0, le=10)
    stamina: int = Field(default=10, ge=0, le=10)
    status_conditions: list[StatusCondition] = Field(default_factory=list)
    inventory: list[ItemId] = Field(default_factory=list)
    current_location: LocationId
    alive: bool = True
    conscious: bool = True

    @model_validator(mode="after")
    def life_consistency(self) -> CharacterState:
        if self.health == 0 and self.alive:
            raise ValueError("health 0 cannot be alive")
        if not self.alive and self.conscious:
            raise ValueError("dead character cannot be conscious")
        return self


class Entity(BaseModel):
    id: EntityId
    name: str
    description: str = ""
    faction: str | None = None


class PlayerCharacter(Entity):
    kind: Literal["player"] = "player"
    state: CharacterState


class NPCGoal(BaseModel):
    id: str
    kind: Literal["reach_location", "investigate_item"]
    target_id: str
    priority: int = Field(default=0, ge=-100, le=100)
    required_fact_ids: set[FactId] = Field(default_factory=set)


class NPC(Entity):
    kind: Literal["npc"] = "npc"
    state: CharacterState
    goals: list[str] = Field(default_factory=list)
    planning_goals: list[NPCGoal] = Field(default_factory=list)
    completed_goal_ids: set[str] = Field(default_factory=set)
    relationships: dict[EntityId, int] = Field(default_factory=dict)
    knowledge: NPCKnowledge = Field(default_factory=NPCKnowledge)

    @model_validator(mode="after")
    def planning_goal_consistency(self) -> NPC:
        goal_ids = [goal.id for goal in self.planning_goals]
        if len(goal_ids) != len(set(goal_ids)):
            raise ValueError("NPC planning goal ids must be unique")
        unknown_completed = self.completed_goal_ids - set(goal_ids)
        if unknown_completed:
            raise ValueError("completed NPC goals must reference configured planning goals")
        return self


Character = Annotated[PlayerCharacter | NPC, Field(discriminator="kind")]


class DialogueRelationshipRule(BaseModel):
    id: str = Field(min_length=1)
    speaker_id: EntityId
    listener_id: EntityId
    required_listener_fact_ids: set[FactId] = Field(default_factory=set)
    delta: int = Field(ge=-100, le=100)
    priority: int = Field(default=0, ge=-100, le=100)
    once: bool = True
    observation: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def nonzero_delta(self) -> DialogueRelationshipRule:
        if self.delta == 0:
            raise ValueError("dialogue relationship rule delta must be non-zero")
        return self


class TraversalEffect(BaseModel):
    extra_minutes: int = Field(default=0, ge=0, le=60)


class RouteEffect(BaseModel):
    blocked_destination_ids: set[LocationId] = Field(default_factory=set)


class LocationCondition(BaseModel):
    code: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    traversal: TraversalEffect | None = None
    route: RouteEffect | None = None


class Location(BaseModel):
    id: LocationId
    name: str
    description: str
    exits: dict[str, LocationId] = Field(default_factory=dict)
    active_conditions: dict[str, LocationCondition] = Field(default_factory=dict)


class ScheduledLocationCondition(BaseModel):
    id: str = Field(min_length=1)
    due_absolute_minute: int = Field(ge=0)
    location_id: LocationId
    condition: LocationCondition
    expires_after_minutes: int | None = Field(default=20, ge=1, le=24 * 60)

    @property
    def expiry_event_id(self) -> str:
        return f"{self.id}:expiry"

    @property
    def expiry_absolute_minute(self) -> int | None:
        if self.expires_after_minutes is None:
            return None
        return self.due_absolute_minute + self.expires_after_minutes


class ScheduledLocationConditionExpiry(BaseModel):
    id: str = Field(min_length=1)
    due_absolute_minute: int = Field(ge=0)
    location_id: LocationId
    condition_code: str = Field(min_length=1)


class Item(BaseModel):
    id: ItemId
    name: str
    item_type: str
    description: str = ""
    owner_id: EntityId | None = None
    location_id: LocationId | None = None
    unique: bool = True
    flags: set[str] = Field(default_factory=set)
    reveals_fact_id: FactId | None = None

    @model_validator(mode="after")
    def exactly_one_holder(self) -> Item:
        if (self.owner_id is None) == (self.location_id is None):
            raise ValueError("item must have exactly one owner or location")
        return self


class Fact(BaseModel):
    id: FactId
    proposition: str
    truth_status: TruthStatus = TruthStatus.TRUE
    discoverability: str = "discoverable"
    source: str
    related_entities: set[EntityId] = Field(default_factory=set)
    tags: set[str] = Field(default_factory=set)
    discovery_prerequisites: set[FactId] = Field(default_factory=set)
    contradicts: set[FactId] = Field(default_factory=set)
    disclosure_min_relationship: int = Field(default=-100, ge=-100, le=100)


class FactInferenceRule(BaseModel):
    id: str
    premises: set[FactId] = Field(min_length=1)
    conclusion: FactId


class SimulationState(BaseModel):
    cadence_minutes: int = Field(default=5, ge=1, le=24 * 60)
    next_due_absolute_minute: int = Field(default=8 * 60 + 5, ge=0)
    max_catch_up_cycles: int = Field(default=12, ge=1, le=100)
    max_npc_actions_per_cycle: int = Field(default=3, ge=1, le=20)
    max_social_actions_per_cycle: int = Field(default=1, ge=1, le=20)
    max_scheduled_events_per_turn: int = Field(default=4, ge=1, le=50)


class WorldState(BaseModel):
    turn_number: int = Field(default=0, ge=0)
    clock: WorldClock = Field(default_factory=WorldClock)
    player_id: EntityId
    entities: dict[EntityId, Character]
    locations: dict[LocationId, Location]
    items: dict[ItemId, Item]
    facts: dict[FactId, Fact]
    inference_rules: dict[str, FactInferenceRule] = Field(default_factory=dict)
    dialogue_relationship_rules: list[DialogueRelationshipRule] = Field(default_factory=list)
    applied_dialogue_relationship_rule_ids: set[str] = Field(default_factory=set)
    simulation: SimulationState = Field(default_factory=SimulationState)
    scheduled_location_conditions: list[ScheduledLocationCondition] = Field(default_factory=list)
    scheduled_location_condition_expirations: list[ScheduledLocationConditionExpiry] = Field(
        default_factory=list
    )
    player_known_facts: set[FactId] = Field(default_factory=set)
    factions: set[str] = Field(default_factory=set)

    @model_validator(mode="after")
    def canonical_reference_consistency(self) -> WorldState:
        rule_ids = [rule.id for rule in self.dialogue_relationship_rules]
        if len(rule_ids) != len(set(rule_ids)):
            raise ValueError("dialogue relationship rule ids must be unique")
        unknown_applied = self.applied_dialogue_relationship_rule_ids - set(rule_ids)
        if unknown_applied:
            raise ValueError("applied dialogue relationship rules must reference configured rules")
        for rule in self.dialogue_relationship_rules:
            speaker = self.entities.get(rule.speaker_id)
            if not isinstance(speaker, NPC):
                raise ValueError("dialogue relationship rule speaker must reference an NPC")
            if rule.listener_id not in self.entities:
                raise ValueError("dialogue relationship rule listener must reference an entity")
            missing_facts = rule.required_listener_fact_ids - self.facts.keys()
            if missing_facts:
                raise ValueError("dialogue relationship rule references missing facts")
        for entity in self.entities.values():
            if not isinstance(entity, NPC):
                continue
            for goal in entity.planning_goals:
                missing_goal_facts = goal.required_fact_ids - self.facts.keys()
                if missing_goal_facts:
                    raise ValueError("NPC goal prerequisites must reference configured facts")
        return self

    def player(self) -> PlayerCharacter:
        entity = self.entities[self.player_id]
        if not isinstance(entity, PlayerCharacter):
            raise TypeError("player_id does not reference a PlayerCharacter")
        return entity


class GameSession(BaseModel):
    id: SessionId
    name: str
    world_pack: str
    created_at: str


class Turn(BaseModel):
    session_id: SessionId
    turn_number: int
    raw_input: str
    accepted: bool
    reason: str | None = None
    narration: str
    location_id: LocationId
    involved_entities: set[EntityId] = Field(default_factory=set)
    tags: set[str] = Field(default_factory=set)