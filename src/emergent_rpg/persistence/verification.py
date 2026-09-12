from __future__ import annotations

from pydantic import BaseModel, Field

from emergent_rpg.engine.reducer import replay
from emergent_rpg.persistence.archive import (
    SessionArchiveError,
    build_session_archive,
    state_sha256,
)
from emergent_rpg.persistence.db import SQLiteStore
from emergent_rpg.validation.validator import validate_state


class SessionVerificationReport(BaseModel):
    session_id: str
    world_pack: str
    event_count: int = Field(ge=0)
    turn_count: int = Field(ge=0)
    episode_count: int = Field(ge=0)
    replay_equal: bool
    current_state_valid: bool
    archive_consistent: bool
    current_state_sha256: str | None = None
    failures: list[str] = Field(default_factory=list)
    passed: bool


def verify_session(store: SQLiteStore, session_id: str) -> SessionVerificationReport:
    """Read and verify one persisted session without mutating canonical data."""
    session = store.get_session(session_id)
    events = store.load_events(session_id)
    turns = store.list_turns(session_id)
    episodes = store.list_episodes(session_id)
    initial = store.load_initial_state(session_id)
    current = store.load_state(session_id)

    replayed = replay(initial, events)
    replay_equal = replayed == current
    state_report = validate_state(current)
    failures: list[str] = []
    if not replay_equal:
        failures.append("persisted current state does not match event replay")
    if not state_report.valid:
        failures.append(f"persisted current state is invalid: {state_report.issues}")

    archive_consistent = True
    digest: str | None = state_sha256(current)
    try:
        archive = build_session_archive(store, session_id)
    except SessionArchiveError as exc:
        archive_consistent = False
        failures.append(str(exc))
    else:
        digest = archive.current_state_sha256

    passed = replay_equal and state_report.valid and archive_consistent and not failures
    return SessionVerificationReport(
        session_id=session.id,
        world_pack=session.world_pack,
        event_count=len(events),
        turn_count=len(turns),
        episode_count=len(episodes),
        replay_equal=replay_equal,
        current_state_valid=state_report.valid,
        archive_consistent=archive_consistent,
        current_state_sha256=digest,
        failures=failures,
        passed=passed,
    )
