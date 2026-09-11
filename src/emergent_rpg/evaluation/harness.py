from __future__ import annotations

import random
from pathlib import Path

from pydantic import BaseModel, Field

from emergent_rpg.domain.actions import (
    InspectAction,
    MoveAction,
    PlayerAction,
    TakeAction,
    WaitAction,
)
from emergent_rpg.domain.models import WorldState
from emergent_rpg.engine.service import GameEngine
from emergent_rpg.persistence.db import SQLiteStore
from emergent_rpg.validation.validator import validate_state

DEFAULT_SEED = 20_260_911


class EvaluationReport(BaseModel):
    scenario: str = "seeded-mixed-actions-v1"
    seed: int
    target_accepted_turns: int
    submitted_actions: int
    accepted_turns: int
    rejected_actions: int
    event_count: int
    persisted_turn_count: int
    episode_count: int
    checkpoint_turns: list[int] = Field(default_factory=list)
    action_counts: dict[str, int] = Field(default_factory=dict)
    final_clock_absolute_minutes: int
    replay_equal: bool
    state_valid: bool
    clock_monotonic: bool
    player_knowledge_monotonic: bool
    event_log_monotonic: bool
    item_ownership_valid: bool
    unique_event_ids: bool
    failures: list[str] = Field(default_factory=list)
    passed: bool


def run_consistency_evaluation(
    db_path: str | Path,
    *,
    turns: int = 1_000,
    seed: int = DEFAULT_SEED,
    checkpoint_interval: int = 100,
) -> EvaluationReport:
    if turns < 1:
        raise ValueError("turns must be positive")
    if checkpoint_interval < 1:
        raise ValueError("checkpoint_interval must be positive")

    path = Path(db_path)
    if path.exists():
        raise FileExistsError(f"evaluation database already exists: {path}")

    rng = random.Random(seed)
    store = SQLiteStore(path)
    engine = GameEngine(store)
    session = engine.new_session("Long-run consistency evaluation")
    state = store.load_state(session.id)

    submitted_actions = 0
    rejected_actions = 0
    action_counts: dict[str, int] = {}
    checkpoint_turns: list[int] = []
    failures: list[str] = []
    clock_monotonic = True
    knowledge_monotonic = True
    event_log_monotonic = True
    state_valid = True
    replay_equal = True
    item_ownership_valid = True
    unique_event_ids = True
    last_clock = state.clock.absolute_minutes
    previous_known = set(state.player_known_facts)
    last_event_count = 0
    last_checkpoint_turn = -1
    max_submissions = turns * 10 + 100

    while state.turn_number < turns:
        if submitted_actions >= max_submissions:
            _record_failure(failures, "submission_guard_exhausted")
            break

        before = state
        action = _choose_action(rng, state, submitted_actions)
        action_kind = str(action.kind)
        action_counts[action_kind] = action_counts.get(action_kind, 0) + 1
        result, _, state = engine.execute_action(
            session.id,
            action,
            f"[eval:{submitted_actions}] {action.model_dump_json()}",
        )
        submitted_actions += 1
        if not result.accepted:
            rejected_actions += 1

        if state.clock.absolute_minutes < last_clock:
            clock_monotonic = False
            _record_failure(failures, "clock_regressed")
        last_clock = state.clock.absolute_minutes

        if not previous_known.issubset(state.player_known_facts):
            knowledge_monotonic = False
            _record_failure(failures, "player_knowledge_regressed")
        previous_known = set(state.player_known_facts)

        if result.accepted and state.turn_number == before.turn_number:
            _record_failure(failures, "accepted_action_did_not_advance_turn")
        if not result.accepted and state != before:
            _record_failure(failures, "rejected_action_mutated_state")

        should_checkpoint = (
            result.accepted
            and state.turn_number % checkpoint_interval == 0
            and state.turn_number != last_checkpoint_turn
        )
        if should_checkpoint:
            checkpoint_turns.append(state.turn_number)
            last_checkpoint_turn = state.turn_number
            checkpoint = _check_checkpoint(engine, session.id, state, last_event_count)
            last_event_count = checkpoint.event_count
            if not checkpoint.state_valid:
                state_valid = False
                _record_failure(failures, "state_validation_failed")
            if not checkpoint.replay_equal:
                replay_equal = False
                _record_failure(failures, "checkpoint_replay_mismatch")
            if not checkpoint.event_log_monotonic:
                event_log_monotonic = False
                _record_failure(failures, "event_log_shrank")
            if not checkpoint.item_ownership_valid:
                item_ownership_valid = False
                _record_failure(failures, "item_ownership_invalid")
            if not checkpoint.unique_event_ids:
                unique_event_ids = False
                _record_failure(failures, "duplicate_event_id")

    if state.turn_number != last_checkpoint_turn:
        checkpoint_turns.append(state.turn_number)
        checkpoint = _check_checkpoint(engine, session.id, state, last_event_count)
        last_event_count = checkpoint.event_count
        state_valid = state_valid and checkpoint.state_valid
        replay_equal = replay_equal and checkpoint.replay_equal
        event_log_monotonic = event_log_monotonic and checkpoint.event_log_monotonic
        item_ownership_valid = item_ownership_valid and checkpoint.item_ownership_valid
        unique_event_ids = unique_event_ids and checkpoint.unique_event_ids

    events = store.load_events(session.id)
    turns_rows = store.list_turns(session.id)
    episodes = store.list_episodes(session.id)
    if state.turn_number != turns:
        _record_failure(failures, "target_turn_count_not_reached")
    if len(turns_rows) != submitted_actions:
        _record_failure(failures, "persisted_turn_count_mismatch")
    if len(episodes) != state.turn_number:
        _record_failure(failures, "episode_count_mismatch")
    if not state_valid:
        _record_failure(failures, "final_state_invalid")
    if not replay_equal:
        _record_failure(failures, "final_replay_mismatch")

    return EvaluationReport(
        seed=seed,
        target_accepted_turns=turns,
        submitted_actions=submitted_actions,
        accepted_turns=state.turn_number,
        rejected_actions=rejected_actions,
        event_count=len(events),
        persisted_turn_count=len(turns_rows),
        episode_count=len(episodes),
        checkpoint_turns=checkpoint_turns,
        action_counts=action_counts,
        final_clock_absolute_minutes=state.clock.absolute_minutes,
        replay_equal=replay_equal,
        state_valid=state_valid,
        clock_monotonic=clock_monotonic,
        player_knowledge_monotonic=knowledge_monotonic,
        event_log_monotonic=event_log_monotonic,
        item_ownership_valid=item_ownership_valid,
        unique_event_ids=unique_event_ids,
        failures=failures,
        passed=not failures,
    )


class _CheckpointResult(BaseModel):
    event_count: int
    replay_equal: bool
    state_valid: bool
    event_log_monotonic: bool
    item_ownership_valid: bool
    unique_event_ids: bool


def _check_checkpoint(
    engine: GameEngine,
    session_id: str,
    state: WorldState,
    previous_event_count: int,
) -> _CheckpointResult:
    events = engine.store.load_events(session_id)
    event_ids = [event.event_id for event in events]
    return _CheckpointResult(
        event_count=len(events),
        replay_equal=engine.replay_session(session_id) == state,
        state_valid=validate_state(state).valid,
        event_log_monotonic=len(events) >= previous_event_count,
        item_ownership_valid=_item_ownership_valid(state),
        unique_event_ids=len(event_ids) == len(set(event_ids)),
    )


def _item_ownership_valid(state: WorldState) -> bool:
    inventory_holders: dict[str, str] = {}
    for entity_id, entity in state.entities.items():
        if len(entity.state.inventory) != len(set(entity.state.inventory)):
            return False
        for item_id in entity.state.inventory:
            if item_id in inventory_holders:
                return False
            inventory_holders[item_id] = entity_id

    for item_id, item in state.items.items():
        if item.owner_id is not None:
            if inventory_holders.get(item_id) != item.owner_id:
                return False
        elif item_id in inventory_holders:
            return False
    return True


def _choose_action(
    rng: random.Random,
    state: WorldState,
    submission_index: int,
) -> PlayerAction:
    if submission_index > 0 and submission_index % 29 == 0:
        return MoveAction(destination="__missing_exit__")
    if submission_index > 0 and submission_index % 47 == 0:
        return TakeAction(target="__missing_item__")

    player = state.player()
    location = state.locations[player.state.current_location]
    visible_items = sorted(
        item.name for item in state.items.values() if item.location_id == location.id
    )
    exits = sorted(location.exits)
    roll = rng.random()

    if visible_items and roll < 0.18:
        return TakeAction(target=rng.choice(visible_items))
    if exits and roll < 0.48:
        return MoveAction(destination=rng.choice(exits))
    if roll < 0.72:
        return InspectAction(target="room")
    return WaitAction(minutes=rng.choice((1, 2, 5, 10)))


def _record_failure(failures: list[str], code: str) -> None:
    if code not in failures:
        failures.append(code)
