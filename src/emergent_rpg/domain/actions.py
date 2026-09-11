from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field


class MoveAction(BaseModel):
    kind: Literal["move"] = "move"
    destination: str


class InspectAction(BaseModel):
    kind: Literal["inspect"] = "inspect"
    target: str


class TalkAction(BaseModel):
    kind: Literal["talk"] = "talk"
    target: str


class TakeAction(BaseModel):
    kind: Literal["take"] = "take"
    target: str


class WaitAction(BaseModel):
    kind: Literal["wait"] = "wait"
    minutes: int = Field(default=10, ge=1, le=24 * 60)


class FreeformAction(BaseModel):
    kind: Literal["freeform"] = "freeform"
    text: str


PlayerAction = Annotated[
    MoveAction | InspectAction | TalkAction | TakeAction | WaitAction | FreeformAction,
    Field(discriminator="kind"),
]
