from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter


class ActionModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MoveAction(ActionModel):
    kind: Literal["move"] = "move"
    destination: str = Field(min_length=1)


class InspectAction(ActionModel):
    kind: Literal["inspect"] = "inspect"
    target: str = Field(min_length=1)


class TalkAction(ActionModel):
    kind: Literal["talk"] = "talk"
    target: str = Field(min_length=1)


class TakeAction(ActionModel):
    kind: Literal["take"] = "take"
    target: str = Field(min_length=1)


class GiveAction(ActionModel):
    kind: Literal["give"] = "give"
    item: str = Field(min_length=1)
    receiver: str = Field(min_length=1)


class AttackAction(ActionModel):
    kind: Literal["attack"] = "attack"
    target: str = Field(min_length=1)


class WaitAction(ActionModel):
    kind: Literal["wait"] = "wait"
    minutes: int = Field(default=10, ge=1, le=24 * 60)


class FreeformAction(ActionModel):
    kind: Literal["freeform"] = "freeform"
    text: str


PlayerAction = Annotated[
    MoveAction
    | InspectAction
    | TalkAction
    | TakeAction
    | GiveAction
    | AttackAction
    | WaitAction
    | FreeformAction,
    Field(discriminator="kind"),
]

ACTION_ADAPTER: TypeAdapter[PlayerAction] = TypeAdapter(PlayerAction)


def parse_action(data: object) -> PlayerAction:
    return ACTION_ADAPTER.validate_python(data)
