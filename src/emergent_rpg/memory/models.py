from __future__ import annotations

from pydantic import BaseModel, Field


class Episode(BaseModel):
    id: str
    turn_range: tuple[int, int]
    involved_entities: set[str] = Field(default_factory=set)
    location: str
    tags: set[str] = Field(default_factory=set)
    summary: str
    importance: float = Field(default=0.5, ge=0.0, le=1.0)


class RetrievedContext(BaseModel):
    working_memory: list[str] = Field(default_factory=list)
    episodes: list[Episode] = Field(default_factory=list)
    semantic_facts: list[str] = Field(default_factory=list)
    current_location: str
