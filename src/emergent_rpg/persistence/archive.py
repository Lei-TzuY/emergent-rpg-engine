from __future__ import annotations

import json
from datetime import UTC, datetime
from enum import Enum
from hashlib import sha256
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from emergent_rpg.domain.events import Event
from emergent_rpg.domain.models import GameSession, Turn, WorldState
from emergent_rpg.engine.reducer import apply_event, replay
from emergent_rpg.memory.models import Episode
from emergent_rpg.persistence.db import (
    EpisodeRow,
    EventRow,
    SessionRow,
    SQLiteStore,
    TurnRow,
)
from emergent_rpg.validation.validator import validate_event_preconditions, validate_state


class SessionArchiveError(ValueError):
    pass


class SessionArchive(BaseModel):
    model_config = ConfigDict(extra="forbid")

    format_version: Literal[1] = 1
    source_session_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    world_pack: str = Field(min_length=1)
    source_created_at: str = Field(min_length=1)
    initial_state: WorldState
    current_state_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    events: list[Event] = Field(default_factory=list)
    turns: list[Turn] = Field(default_factory=list)
    episodes: list[Episode] = Field(default_factory=list)


def _canonical_value(value: object) -> object:
    if isinstance(value, BaseModel):
        return _canonical_value(value.model_dump(mode="python"))
    if isinstance(value, Enum):
        return _canonical_value(value.value)
    if isinstance(value, dict):
        return {
            str(key): _canonical_value(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (set, frozenset)):
        items = [_canonical_value(item) for item in value]
        items.sort(
            key=lambda item: json.dumps(
                item,
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return {"__set__": items}
    if isinstance(value, (list, tuple)):
        return [_canonical_value(item) for item in value]
    return value


def _canonical_state_json(state: WorldState) -> str:
    return json.dumps(
        _canonical_value(state),
        sort_keys=True,
        separators=(",", ":"),
    )


def state_sha256(state: WorldState) -> str:
    return sha256(_canonical_state_json(state).encode("utf-8")).hexdigest()


def _verified_replay(archive: SessionArchive) -> WorldState:
    initial_report = validate_state(archive.initial_state)
    if not initial_report.valid:
        raise SessionArchiveError(f"invalid archive initial state: {initial_report.issues}")

    if archive.initial_state.turn_number != 0:
        raise SessionArchiveError("archive initial state must start at turn 0")

    event_ids = [event.event_id for event in archive.events]
    if len(event_ids) != len(set(event_ids)):
        raise SessionArchiveError("archive event ids must be unique")

    episode_ids = [episode.id for episode in archive.episodes]
    if len(episode_ids) != len(set(episode_ids)):
        raise SessionArchiveError("archive episode ids must be unique")

    event_turns = [event.turn_number for event in archive.events]
    if event_turns != sorted(event_turns):
        raise SessionArchiveError("archive events must be ordered by nondecreasing turn number")

    turn_numbers = [turn.turn_number for turn in archive.turns]
    if turn_numbers != sorted(turn_numbers):
        raise SessionArchiveError("archive turns must be ordered by nondecreasing turn number")
    if any(turn.session_id != archive.source_session_id for turn in archive.turns):
        raise SessionArchiveError("archive turn session ids do not match source_session_id")

    state = archive.initial_state.model_copy(deep=True)
    for event in archive.events:
        precheck = validate_event_preconditions(state, event)
        if not precheck.valid:
            raise SessionArchiveError(
                f"archive event {event.event_id} violates preconditions: {precheck.issues}"
            )
        previous = state
        state = apply_event(state, event)
        state_report = validate_state(
            state,
            previous=previous,
            transition_events=[event],
        )
        if not state_report.valid:
            raise SessionArchiveError(
                f"archive event {event.event_id} produces invalid state: {state_report.issues}"
            )

    final_report = validate_state(state)
    if not final_report.valid:
        raise SessionArchiveError(f"archive replay state is invalid: {final_report.issues}")
    if state_sha256(state) != archive.current_state_sha256:
        raise SessionArchiveError("archive current-state digest does not match replay")

    max_turn = state.turn_number
    for turn in archive.turns:
        if turn.turn_number > max_turn:
            raise SessionArchiveError("archive turn history extends beyond replayed state")
        if turn.location_id not in state.locations:
            raise SessionArchiveError("archive turn references a missing location")
    for episode in archive.episodes:
        start, end = episode.turn_range
        if start > end or end > max_turn:
            raise SessionArchiveError("archive episode range extends beyond replayed state")
        if episode.location not in state.locations:
            raise SessionArchiveError("archive episode references a missing location")
    return state


def build_session_archive(store: SQLiteStore, session_id: str) -> SessionArchive:
    session = store.get_session(session_id)
    initial = store.load_initial_state(session_id)
    events = store.load_events(session_id)
    current = store.load_state(session_id)
    replayed = replay(initial, events)
    if replayed != current:
        raise SessionArchiveError("source session current state does not match event replay")
    current_report = validate_state(current)
    if not current_report.valid:
        raise SessionArchiveError(
            f"source session current state is invalid: {current_report.issues}"
        )

    archive = SessionArchive(
        source_session_id=session.id,
        name=session.name,
        world_pack=session.world_pack,
        source_created_at=session.created_at,
        initial_state=initial,
        current_state_sha256=state_sha256(current),
        events=events,
        turns=store.list_turns(session_id),
        episodes=store.list_episodes(session_id),
    )
    _verified_replay(archive)
    return archive


def write_session_archive(
    path: str | Path,
    archive: SessionArchive,
    *,
    overwrite: bool = False,
) -> None:
    destination = Path(path)
    if destination.exists() and not overwrite:
        raise SessionArchiveError(f"archive already exists: {destination}")
    destination.write_text(
        json.dumps(archive.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def load_session_archive(path: str | Path) -> SessionArchive:
    source = Path(path)
    try:
        raw = source.read_text(encoding="utf-8")
    except OSError as exc:
        raise SessionArchiveError(f"cannot read session archive {source}: {exc}") from exc
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SessionArchiveError(
            f"invalid JSON in session archive {source}: line {exc.lineno}, column {exc.colno}"
        ) from exc
    try:
        archive = SessionArchive.model_validate(payload)
    except ValidationError as exc:
        raise SessionArchiveError(f"invalid session archive schema: {exc}") from exc
    _verified_replay(archive)
    return archive


def import_session_archive(
    store: SQLiteStore,
    archive: SessionArchive,
    *,
    name: str | None = None,
) -> GameSession:
    current = _verified_replay(archive)
    session = GameSession(
        id=str(uuid4()),
        name=name or archive.name,
        world_pack=archive.world_pack,
        created_at=datetime.now(UTC).isoformat(),
    )
    turns = [turn.model_copy(update={"session_id": session.id}) for turn in archive.turns]

    try:
        with Session(store.engine) as db:
            db.add(
                SessionRow(
                    id=session.id,
                    name=session.name,
                    world_pack=session.world_pack,
                    created_at=session.created_at,
                    initial_state_json=SQLiteStore._dump_model(archive.initial_state),
                    current_state_json=SQLiteStore._dump_model(current),
                )
            )
            for event in archive.events:
                db.add(
                    EventRow(
                        session_id=session.id,
                        event_id=event.event_id,
                        turn_number=event.turn_number,
                        event_type=event.type,
                        payload_json=SQLiteStore._dump_model(event),
                    )
                )
            for turn in turns:
                db.add(
                    TurnRow(
                        session_id=session.id,
                        turn_number=turn.turn_number,
                        raw_input=turn.raw_input,
                        accepted=turn.accepted,
                        reason=turn.reason,
                        narration=turn.narration,
                        location_id=turn.location_id,
                        involved_json=json.dumps(sorted(turn.involved_entities)),
                        tags_json=json.dumps(sorted(turn.tags)),
                    )
                )
            for episode in archive.episodes:
                db.add(
                    EpisodeRow(
                        id=episode.id,
                        session_id=session.id,
                        turn_start=episode.turn_range[0],
                        turn_end=episode.turn_range[1],
                        involved_json=json.dumps(sorted(episode.involved_entities)),
                        location_id=episode.location,
                        tags_json=json.dumps(sorted(episode.tags)),
                        summary=episode.summary,
                        importance=episode.importance,
                    )
                )
            db.commit()
    except IntegrityError as exc:
        raise SessionArchiveError(
            "archive conflicts with existing event or episode provenance"
        ) from exc
    return session
