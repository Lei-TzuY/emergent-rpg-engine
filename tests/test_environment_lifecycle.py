from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from emergent_rpg.api.app import create_app
from emergent_rpg.domain.actions import MoveAction, WaitAction
from emergent_rpg.domain.events import (
    ScheduledLocationConditionApplied,
    ScheduledLocationConditionExpired,
    TimeAdvanced,
)
from emergent_rpg.engine.narrative import ScenePlan
from emergent_rpg.engine.reducer import apply_event
from emergent_rpg.engine.resolver import ActionResult, DeterministicResolver
from emergent_rpg.engine.service import GameEngine
from emergent_rpg.engine.simulation import DeterministicWorldEventScheduler
from emergent_rpg.persistence.db import SQLiteStore
from emergent_rpg.providers.base import NarrativeGenerator
from emergent_rpg.providers.errors import ProviderRequestError
from emergent_rpg.validation.validator import validate_event_preconditions, validate_state
from emergent_rpg.world.demo import build_demo_world


class FailingNarrativeGenerator(NarrativeGenerator):
    def generate(self, scene_plan: ScenePlan) -> str:
        del scene_plan
        raise ProviderRequestError("simulated outage at expiry boundary")


def _travel_minutes(result: ActionResult) -> int:
    events = [event for event in result.emitted_events if isinstance(event, TimeAdvanced)]
    assert len(events) == 1
    return events[0].minutes


def test_demo_condition_activates_then_expires_and_restores_baseline(tmp_path: Path) -> None:
    engine = GameEngine(SQLiteStore(tmp_path / "lifecycle.db"))
    session = engine.new_session()

    engine.execute_action(session.id, WaitAction(minutes=20), "wait 20")
    active = engine.store.load_state(session.id)
    assert "ash_squall" in active.locations["yard"].active_conditions
    assert active.scheduled_location_condition_expirations[0].due_absolute_minute == 520
    assert _travel_minutes(
        DeterministicResolver().resolve(active, MoveAction(destination="operations"))
    ) == 10

    engine.execute_action(session.id, WaitAction(minutes=19), "wait 19")
    almost_expired = engine.store.load_state(session.id)
    assert almost_expired.clock.absolute_minutes == 519
    assert "ash_squall" in almost_expired.locations["yard"].active_conditions

    engine.execute_action(session.id, WaitAction(minutes=1), "wait 1")
    expired = engine.store.load_state(session.id)
    assert expired.clock.absolute_minutes == 520
    assert "ash_squall" not in expired.locations["yard"].active_conditions
    assert expired.scheduled_location_condition_expirations == []
    assert _travel_minutes(
        DeterministicResolver().resolve(expired, MoveAction(destination="operations"))
    ) == 5
    assert engine.replay_session(session.id) == expired


def test_large_jump_orders_activation_then_expiry_in_same_turn(tmp_path: Path) -> None:
    engine = GameEngine(SQLiteStore(tmp_path / "jump.db"))
    session = engine.new_session()

    engine.execute_action(session.id, WaitAction(minutes=40), "wait 40")
    state = engine.store.load_state(session.id)
    world_events = [
        event
        for event in engine.store.load_events(session.id)
        if isinstance(
            event,
            (ScheduledLocationConditionApplied, ScheduledLocationConditionExpired),
        )
    ]

    assert [type(event) for event in world_events] == [
        ScheduledLocationConditionApplied,
        ScheduledLocationConditionExpired,
    ]
    assert [event.scheduled_absolute_minute for event in world_events] == [500, 520]
    assert "ash_squall" not in state.locations["yard"].active_conditions
    assert engine.replay_session(session.id) == state


def test_world_event_budget_leaves_expiry_as_explicit_backlog() -> None:
    state = build_demo_world()
    state.clock = state.clock.advanced(40)
    state.simulation.max_scheduled_events_per_turn = 1
    scheduler = DeterministicWorldEventScheduler()

    first = scheduler.due_events(state)
    assert [(event.kind, event.event_id) for event in first.due_events] == [
        ("activate", "yard_ash_squall")
    ]
    assert first.backlog_remaining

    activation = ScheduledLocationConditionApplied(
        turn_number=1,
        scheduled_event_id="yard_ash_squall",
        scheduled_absolute_minute=500,
    )
    assert validate_event_preconditions(state, activation).valid
    activated = apply_event(state, activation)
    second = scheduler.due_events(activated)
    assert [(event.kind, event.event_id) for event in second.due_events] == [
        ("expire", "yard_ash_squall:expiry")
    ]


def test_expiry_cannot_run_early_or_twice(tmp_path: Path) -> None:
    engine = GameEngine(SQLiteStore(tmp_path / "guards.db"))
    session = engine.new_session()
    engine.execute_action(session.id, WaitAction(minutes=20), "wait 20")
    active = engine.store.load_state(session.id)
    forged = ScheduledLocationConditionExpired(
        turn_number=active.turn_number + 1,
        scheduled_event_id="yard_ash_squall:expiry",
        scheduled_absolute_minute=520,
        location_id="yard",
        condition_code="ash_squall",
    )
    assert not validate_event_preconditions(active, forged).valid

    engine.execute_action(session.id, WaitAction(minutes=20), "wait 20")
    expired = engine.store.load_state(session.id)
    assert not validate_event_preconditions(expired, forged).valid


def test_manual_condition_deletion_still_requires_typed_expiry_provenance(
    tmp_path: Path,
) -> None:
    engine = GameEngine(SQLiteStore(tmp_path / "provenance.db"))
    session = engine.new_session()
    engine.execute_action(session.id, WaitAction(minutes=20), "wait 20")
    before = engine.store.load_state(session.id)
    forged_state = before.model_copy(deep=True)
    del forged_state.locations["yard"].active_conditions["ash_squall"]

    report = validate_state(forged_state, previous=before)

    assert not report.valid
    assert any(issue.code == "environment_went_backward" for issue in report.issues)


def test_provider_failure_at_expiry_boundary_is_zero_commit(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "provider-expiry.db")
    setup = GameEngine(store)
    session = setup.new_session()
    setup.execute_action(session.id, WaitAction(minutes=20), "wait 20")
    before = store.load_state(session.id)
    before_events = store.load_events(session.id)
    before_turns = store.list_turns(session.id)

    failing = GameEngine(store, generator=FailingNarrativeGenerator())
    with pytest.raises(ProviderRequestError, match="expiry boundary"):
        failing.execute_action(session.id, WaitAction(minutes=20), "wait 20")

    assert store.load_state(session.id) == before
    assert store.load_events(session.id) == before_events
    assert store.list_turns(session.id) == before_turns
    assert "ash_squall" in before.locations["yard"].active_conditions


def test_api_projection_removes_condition_after_expiry(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path / "api-expiry.db"))
    created = client.post("/sessions", json={"name": "Lifecycle API"})
    session_id = created.json()["session"]["id"]

    active = client.post(
        f"/sessions/{session_id}/actions",
        json={"text": "wait 20"},
    )
    expired = client.post(
        f"/sessions/{session_id}/actions",
        json={"text": "wait 20"},
    )

    assert active.status_code == 200
    assert active.json()["state"]["location_conditions"][0]["code"] == "ash_squall"
    assert expired.status_code == 200
    assert expired.json()["state"]["location_conditions"] == []
