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


class CharacterHealed(DomainEvent):
    type: Literal["character_healed"] = "character_healed"
    entity_id: str
    amount: int = Field(gt=0)


class FactDiscovered(DomainEvent):
    type: Literal["fact_discovered"] = "fact_discovered"
    fact_id: str
    observer_id: str


class NPCLearnedFact(DomainEvent):
    type: Literal["npc_learned_fact"] = "npc_learned_fact"
    npc_id: str
    fact_id: str


class RelationshipChanged(DomainEvent):
    type: Literal["relationship_changed"] = "relationship_changed"
    source_id: str
    target_id: str
    delta: int


class TimeAdvanced(DomainEvent):
    type: Literal["time_advanced"] = "time_advanced"
    minutes: int = Field(gt=0)


class StatusApplied(DomainEvent):
    type: Literal["status_applied"] = "status_applied"
    entity_id: str
    code: str
    name: str
    incapacitating: bool = False


Event = Annotated[
    PlayerMoved
    | ItemAcquired
    | ItemDropped
    | CharacterDamaged
    | CharacterHealed
    | FactDiscovered
    | NPCLearnedFact
    | RelationshipChanged
    | TimeAdvanced
    | StatusApplied,
    Field(discriminator="type"),
]

EVENT_ADAPTER = TypeAdapter(Event)


def parse_event(data: dict[str, object]) -> Event:
    return EVENT_ADAPTER.validate_python(data)
