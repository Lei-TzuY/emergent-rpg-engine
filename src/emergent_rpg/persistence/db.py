from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel
from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from emergent_rpg.domain.events import Event, parse_event
from emergent_rpg.domain.models import GameSession, Turn, WorldState
from emergent_rpg.memory.models import Episode
from emergent_rpg.persistence.schema import ensure_schema_compatible


class Base(DeclarativeBase):
    pass


class SessionRow(Base):
    __tablename__ = "game_sessions"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    world_pack: Mapped[str] = mapped_column(String)
    created_at: Mapped[str] = mapped_column(String)
    initial_state_json: Mapped[str] = mapped_column(Text)
    current_state_json: Mapped[str] = mapped_column(Text)


class EventRow(Base):
    __tablename__ = "events"

    sequence_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("game_sessions.id"), index=True)
    event_id: Mapped[str] = mapped_column(String, unique=True, index=True)
    turn_number: Mapped[int] = mapped_column(Integer, index=True)
    event_type: Mapped[str] = mapped_column(String)
    payload_json: Mapped[str] = mapped_column(Text)


class TurnRow(Base):
    __tablename__ = "turns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("game_sessions.id"), index=True)
    turn_number: Mapped[int] = mapped_column(Integer, index=True)
    raw_input: Mapped[str] = mapped_column(Text)
    accepted: Mapped[bool] = mapped_column(Boolean)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    narration: Mapped[str] = mapped_column(Text)
    location_id: Mapped[str] = mapped_column(String)
    involved_json: Mapped[str] = mapped_column(Text)
    tags_json: Mapped[str] = mapped_column(Text)


class EpisodeRow(Base):
    __tablename__ = "episodes"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("game_sessions.id"), index=True)
    turn_start: Mapped[int] = mapped_column(Integer)
    turn_end: Mapped[int] = mapped_column(Integer)
    involved_json: Mapped[str] = mapped_column(Text)
    location_id: Mapped[str] = mapped_column(String)
    tags_json: Mapped[str] = mapped_column(Text)
    summary: Mapped[str] = mapped_column(Text)
    importance: Mapped[float] = mapped_column(Float)


class SQLiteStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.engine = create_engine(f"sqlite:///{self.path}")
        self.schema_version = ensure_schema_compatible(self.engine, Base.metadata)

    @staticmethod
    def _dump_model(model: BaseModel) -> str:
        data = model.model_dump(mode="json")
        return json.dumps(data, sort_keys=True, separators=(",", ":"))

    def create_session(self, session: GameSession, initial_state: WorldState) -> None:
        payload = self._dump_model(initial_state)
        with Session(self.engine) as db:
            db.add(
                SessionRow(
                    id=session.id,
                    name=session.name,
                    world_pack=session.world_pack,
                    created_at=session.created_at,
                    initial_state_json=payload,
                    current_state_json=payload,
                )
            )
            db.commit()

    def get_session(self, session_id: str) -> GameSession:
        with Session(self.engine) as db:
            row = db.get(SessionRow, session_id)
            if row is None:
                raise KeyError(f"unknown session {session_id}")
            return GameSession(
                id=row.id,
                name=row.name,
                world_pack=row.world_pack,
                created_at=row.created_at,
            )

    def latest_session_id(self) -> str | None:
        with Session(self.engine) as db:
            row = db.scalars(select(SessionRow).order_by(SessionRow.created_at.desc())).first()
            return None if row is None else row.id

    def load_initial_state(self, session_id: str) -> WorldState:
        with Session(self.engine) as db:
            row = db.get(SessionRow, session_id)
            if row is None:
                raise KeyError(f"unknown session {session_id}")
            return WorldState.model_validate_json(row.initial_state_json)

    def load_state(self, session_id: str) -> WorldState:
        with Session(self.engine) as db:
            row = db.get(SessionRow, session_id)
            if row is None:
                raise KeyError(f"unknown session {session_id}")
            return WorldState.model_validate_json(row.current_state_json)

    def load_events(self, session_id: str) -> list[Event]:
        with Session(self.engine) as db:
            rows = db.scalars(
                select(EventRow)
                .where(EventRow.session_id == session_id)
                .order_by(EventRow.sequence_id)
            ).all()
            return [parse_event(json.loads(row.payload_json)) for row in rows]

    def commit_turn(
        self,
        session_id: str,
        new_state: WorldState,
        events: list[Event],
        turn: Turn,
        episode: Episode | None,
    ) -> None:
        with Session(self.engine) as db:
            row = db.get(SessionRow, session_id)
            if row is None:
                raise KeyError(f"unknown session {session_id}")
            for event in events:
                db.add(
                    EventRow(
                        session_id=session_id,
                        event_id=event.event_id,
                        turn_number=event.turn_number,
                        event_type=event.type,
                        payload_json=self._dump_model(event),
                    )
                )
            row.current_state_json = self._dump_model(new_state)
            db.add(
                TurnRow(
                    session_id=session_id,
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
            if episode is not None:
                db.add(
                    EpisodeRow(
                        id=episode.id,
                        session_id=session_id,
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

    def list_turns(self, session_id: str, limit: int | None = None) -> list[Turn]:
        with Session(self.engine) as db:
            stmt = (
                select(TurnRow)
                .where(TurnRow.session_id == session_id)
                .order_by(TurnRow.id.desc())
            )
            if limit is not None:
                stmt = stmt.limit(limit)
            rows = list(db.scalars(stmt).all())
            rows.reverse()
            return [
                Turn(
                    session_id=row.session_id,
                    turn_number=row.turn_number,
                    raw_input=row.raw_input,
                    accepted=row.accepted,
                    reason=row.reason,
                    narration=row.narration,
                    location_id=row.location_id,
                    involved_entities=set(json.loads(row.involved_json)),
                    tags=set(json.loads(row.tags_json)),
                )
                for row in rows
            ]

    def list_episodes(self, session_id: str) -> list[Episode]:
        with Session(self.engine) as db:
            rows = db.scalars(
                select(EpisodeRow)
                .where(EpisodeRow.session_id == session_id)
                .order_by(EpisodeRow.turn_end)
            ).all()
            return [
                Episode(
                    id=row.id,
                    turn_range=(row.turn_start, row.turn_end),
                    involved_entities=set(json.loads(row.involved_json)),
                    location=row.location_id,
                    tags=set(json.loads(row.tags_json)),
                    summary=row.summary,
                    importance=row.importance,
                )
                for row in rows
            ]
