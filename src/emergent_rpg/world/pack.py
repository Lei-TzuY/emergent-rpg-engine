from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from emergent_rpg.domain.models import GameSession, WorldState
from emergent_rpg.validation.validator import validate_state


class WorldPackLoadError(ValueError):
    pass


class WorldPack(BaseModel):
    model_config = ConfigDict(extra="forbid")

    format_version: Literal[1] = 1
    id: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9][a-z0-9._-]*$")
    name: str = Field(min_length=1, max_length=120)
    initial_state: WorldState

    def instantiate(self, session_name: str | None = None) -> tuple[GameSession, WorldState]:
        session = GameSession(
            id=str(uuid4()),
            name=session_name or self.name,
            world_pack=self.id,
            created_at=datetime.now(UTC).isoformat(),
        )
        return session, self.initial_state.model_copy(deep=True)


def load_world_pack(path: str | Path) -> WorldPack:
    source = Path(path)
    try:
        raw = source.read_text(encoding="utf-8")
    except OSError as exc:
        raise WorldPackLoadError(f"cannot read world pack {source}: {exc}") from exc

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise WorldPackLoadError(
            f"invalid JSON in world pack {source}: line {exc.lineno}, column {exc.colno}"
        ) from exc

    try:
        pack = WorldPack.model_validate(payload)
    except ValidationError as exc:
        raise WorldPackLoadError(f"invalid world pack schema: {exc}") from exc

    if pack.initial_state.turn_number != 0:
        raise WorldPackLoadError("world pack initial_state.turn_number must be 0")

    report = validate_state(pack.initial_state)
    if not report.valid:
        raise WorldPackLoadError(f"invalid world pack state: {report.issues}")
    return pack
