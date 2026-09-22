from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, TypeAdapter


class DomainEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    turn_number: int = Field(ge=1)
    occurred_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class PlayerMoved(DomainEvent):
    type: Literal["player_moved"] = "player_moved"
    entity_id: str
    from_location: str
    to_location: str


class NPCMoved(DomainEvent):
    type: Literal["npc_moved"] = "npc_moved"
    npc_id: str
    from_location: str
    to_location: str


class NPCLocationMapped(DomainEvent):
    type: Literal["npc_location_mapped"] = "npc_location_mapped"
    npc_id: str
    location_id: str


class NPCItemLocationObserved(DomainEvent):
    type: Literal["npc_item_location_observed"] = "npc_item_location_observed"
    npc_id: str
    item_id: str
    location_id: str
    present: bool


class NPCItemDelivered(DomainEvent):
    type: Literal["npc_item_delivered"] = "npc_item_delivered"
    source_npc_id: str
    receiver_id: str
    item_id: str
    goal_id: str


class PlayerItemGiven(DomainEvent):
    type: Literal["player_item_given"] = "player_item_given"
    source_player_id: str
    receiver_npc_id: str
    item_id: str


class NPCFactShared(DomainEvent):
    type: Literal["npc_fact_shared"] = "npc_fact_shared"
    source_npc_id: str
    receiver_npc_id: str
    fact_id: str


class NPCGoalCompleted(DomainEvent):
    type: Literal["npc_goal_completed"] = "npc_goal_completed"
    npc_id: str
    goal_id: str
    method: Literal[
        "reached_location",
        "inspected_item",
        "acquired_item",
        "delivered_item",
    ]
    evidence_id: str


class PlayerObjectiveActivated(DomainEvent):
    type: Literal["player_objective_activated"] = "player_objective_activated"
    objective_id: str


class PlayerObjectiveCompleted(DomainEvent):
    type: Literal["player_objective_completed"] = "player_objective_completed"
    objective_id: str


class PlayerObjectiveFailed(DomainEvent):
    type: Literal["player_objective_failed"] = "player_objective_failed"
    objective_id: str


class ItemAcquired(DomainEvent):
    type: Literal["item_acquired"] = "item_acquired"
    item_id: str
    actor_id: str
    from_location: str | None = None
    from_owner: str | None = None


class ItemDropped(DomainEvent):
    type: Literal["item_dropped"] = "item_dropped"
    item_id: str
    actor_id: str
    to_location: str


class CharacterDamaged(DomainEvent):
    type: Literal["character_damaged"] = "character_damaged"
    entity_id: str
    amount: int = Field(gt=0)
    source_id: str | None = None
    cause: Literal["other", "unarmed_attack"] = "other"
    stamina_spend_event_id: str | None = None
    stamina_cost: int | None = Field(default=None, gt=0)
    retaliation_trigger_event_id: str | None = None


class CharacterHealed(DomainEvent):
    type: Literal["character_healed"] = "character_healed"
    entity_id: str
    amount: int = Field(gt=0)


class CharacterStaminaSpent(DomainEvent):
    type: Literal["character_stamina_spent"] = "character_stamina_spent"
    entity_id: str
    amount: int = Field(gt=0)
    reason: Literal["unarmed_attack", "retaliation"]
    target_id: str
    trigger_damage_event_id: str | None = None


class CharacterStaminaRecovered(DomainEvent):
    type: Literal["character_stamina_recovered"] = "character_stamina_recovered"
    entity_id: str
    amount: int = Field(gt=0)
    reason: Literal["wait"]
    wait_minutes: int = Field(ge=1, le=24 * 60)


class FactDiscovered(DomainEvent):
    type: Literal["fact_discovered"] = "fact_discovered"
    fact_id: str
    observer_id: str


class FactInferred(DomainEvent):
    type: Literal["fact_inferred"] = "fact_inferred"
    fact_id: str
    observer_id: str
    rule_id: str
    premise_fact_ids: tuple[str, ...] = Field(min_length=1)


class NPCLearnedFact(DomainEvent):
    type: Literal["npc_learned_fact"] = "npc_learned_fact"
    npc_id: str
    fact_id: str


class RelationshipChanged(DomainEvent):
    type: Literal["relationship_changed"] = "relationship_changed"
    source_id: str
    target_id: str
    delta: int
    rule_id: str | None = None


class TimeAdvanced(DomainEvent):
    type: Literal["time_advanced"] = "time_advanced"
    minutes: int = Field(gt=0)
    cause: Literal["other", "wait", "combat"] = "other"


class SimulationCycleProcessed(DomainEvent):
    type: Literal["simulation_cycle_processed"] = "simulation_cycle_processed"
    scheduled_absolute_minute: int = Field(ge=0)


class ScheduledLocationConditionQueued(DomainEvent):
    type: Literal["scheduled_location_condition_queued"] = (
        "scheduled_location_condition_queued"
    )
    rule_id: str
    objective_id: str
    outcome: Literal["completed", "failed"]
    scheduled_event_id: str
    due_absolute_minute: int = Field(ge=0)


class ScheduledLocationConditionApplied(DomainEvent):
    type: Literal["scheduled_location_condition_applied"] = (
        "scheduled_location_condition_applied"
    )
    scheduled_event_id: str
    scheduled_absolute_minute: int = Field(ge=0)


class ScheduledLocationConditionExpired(DomainEvent):
    type: Literal["scheduled_location_condition_expired"] = (
        "scheduled_location_condition_expired"
    )
    scheduled_event_id: str
    scheduled_absolute_minute: int = Field(ge=0)
    location_id: str
    condition_code: str


class StatusApplied(DomainEvent):
    type: Literal["status_applied"] = "status_applied"
    entity_id: str
    code: str
    name: str
    incapacitating: bool = False


Event = Annotated[
    PlayerMoved
    | NPCMoved
    | NPCLocationMapped
    | NPCItemLocationObserved
    | NPCItemDelivered
    | PlayerItemGiven
    | NPCFactShared
    | NPCGoalCompleted
    | PlayerObjectiveActivated
    | PlayerObjectiveCompleted
    | PlayerObjectiveFailed
    | ItemAcquired
    | ItemDropped
    | CharacterDamaged
    | CharacterHealed
    | CharacterStaminaSpent
    | CharacterStaminaRecovered
    | FactDiscovered
    | FactInferred
    | NPCLearnedFact
    | RelationshipChanged
    | TimeAdvanced
    | SimulationCycleProcessed
    | ScheduledLocationConditionQueued
    | ScheduledLocationConditionApplied
    | ScheduledLocationConditionExpired
    | StatusApplied,
    Field(discriminator="type"),
]

EVENT_ADAPTER: TypeAdapter[Event] = TypeAdapter(Event)


def parse_event(data: dict[str, object]) -> Event:
    return EVENT_ADAPTER.validate_python(data)
