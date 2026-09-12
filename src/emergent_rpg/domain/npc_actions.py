from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from emergent_rpg.domain.models import NPCGoal


class NPCIntentModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    goal_id: str


class NPCMoveIntent(NPCIntentModel):
    kind: Literal["move"] = "move"
    destination_id: str


class NPCInspectIntent(NPCIntentModel):
    kind: Literal["inspect"] = "inspect"
    item_id: str


class NPCAcquireIntent(NPCIntentModel):
    kind: Literal["acquire"] = "acquire"
    item_id: str


class NPCCompleteGoalIntent(NPCIntentModel):
    kind: Literal["complete_goal"] = "complete_goal"


class NPCShareFactIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["share_fact"] = "share_fact"
    receiver_id: str


NPCIntent = Annotated[
    NPCMoveIntent
    | NPCInspectIntent
    | NPCAcquireIntent
    | NPCCompleteGoalIntent
    | NPCShareFactIntent,
    Field(discriminator="kind"),
]


class NPCPlan(BaseModel):
    npc_id: str
    intents: list[NPCIntent] = Field(default_factory=list, max_length=3)


class NPCPlanningContext(BaseModel):
    npc_id: str
    npc_name: str
    current_location_id: str
    exits: dict[str, str]
    known_routes: dict[str, set[str]] = Field(default_factory=dict)
    known_item_locations: dict[str, str] = Field(default_factory=dict)
    visible_item_ids: set[str] = Field(default_factory=set)
    inventory_item_ids: set[str] = Field(default_factory=set)
    visible_npc_ids: set[str] = Field(default_factory=set)
    goals: list[NPCGoal] = Field(default_factory=list)
    completed_goal_ids: set[str] = Field(default_factory=set)
    known_fact_ids: set[str] = Field(default_factory=set)
    known_fact_propositions: dict[str, str] = Field(default_factory=dict)
    beliefs: dict[str, str] = Field(default_factory=dict)
    relationships: dict[str, int] = Field(default_factory=dict)
    movement_blocked: bool = False
