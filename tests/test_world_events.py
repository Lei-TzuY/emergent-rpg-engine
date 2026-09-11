from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from emergent_rpg.api.app import create_app
from emergent_rpg.api.models import project_player_state
from emergent_rpg.domain.actions import WaitAction
from emergent_rpg.domain.events import (
    ScheduledLocationConditionApplied,
    SimulationCycleProcessed,
)
from emergent_rpg.domain.models import LocationCondition, ScheduledLocationCondition
from emergent_rpg.engine.narrative import ScenePlan
from emergent_rpg.engine.reducer import apply_event, replay
from emergent_rpg.engine.service import GameEngine
from emergent_rpg.engine.simulation import DeterministicWorldEventScheduler
from emergent_rpg.persistence.db import SQLiteStore
from emergent_rpg.providers.base import NarrativeGenerator
from emergent_rpg.providers.errors import ProviderRequestError
from emergent_rpg.validation.validator import (
    validate_event_preconditions,
    validate_state,
)
from emergent_rpg.world.demo import build_demo_world


class FailingNarrativeGenerator(NarrativeGenerator):
    def generate(self, scene_plan: ScenePlan) -> str:
        del scene_plan
        raise ProviderRequestError("simulated outage before scheduled world events")


def make_engine(tmp_path: Path) -> tuple[GameEngine, str]:
    engine = GameEngine(SQLiteStore(tmp_path / "world-events.db"))
    session = engine.new_session()
    return engine, session.id


def test_demo_world_event_activates_exactly_at_due_time_and_replays(tmp_path: Path) -> None:
    engine, session_id = make_engine(tmp_path)
    initial = engine.store.load_state(session_id)

    assert [event.id for event in initial.scheduled_location_conditions] == [
        "yard_ash_squall"
    ]
    assert initial.locations["yard"].active_conditions == {}

    _, _, before_due = engine.execute_action(
        session_id,
        WaitAction(minutes=19),
        "wait 19",
    )
    assert before_due.clock.absolute_minutes == 8 * 60 + 19
    assert "ash_squall" not in before_due.locations["yard"].active_conditions
    assert [event.id for event in before_due.scheduled_location_conditions] == [
        "yard_ash_squall"
    ]

    _, _, due = engine.execute_action(
        session_id,
        WaitAction(minutes=1),
        "wait 1",
    )
    assert due.clock.absolute_minutes == 8 * 60 + 20
    assert due.scheduled_location_conditions == []
    assert due.locations["yard"].active_conditions["ash_squall"].name == "Ash squall"

    events = engine.store.load_events(session_id)
    world_events = [
        event for event in events if isinstance(event, ScheduledLocationConditionApplied)
    ]
    assert len(world_events) == 1
    assert world_events[0].scheduled_event_id == "yard_ash_squall"
    assert world_events[0].scheduled_absolute_minute == 8 * 60 + 20

    marker_at_same_minute = next(
        event
        for event in events
        if isinstance(event, SimulationCycleProcessed)
        and event.scheduled_absolute_minute == 8 * 60 + 20
    )
    assert events.index(world_events[0]) < events.index(marker_at_same_minute)
    assert engine.replay_session(session_id) == due
    assert SQLiteStore(tmp_path / "world-events.db").load_state(session_id) == due


def test_future_schedule_is_not_player_visible_until_it_fires() -> None:
    state = build_demo_world()

    initial_view = project_player_state(state)
    initial_payload = json.dumps(initial_view.model_dump(mode="json"), sort_keys=True)
    assert initial_view.location_conditions == []
    assert "yard_ash_squall" not in initial_payload
    assert "scheduled_location_conditions" not in initial_payload

    state.clock = state.clock.advanced(20)
    event = ScheduledLocationConditionApplied(
        turn_number=1,
        scheduled_event_id="yard_ash_squall",
        scheduled_absolute_minute=8 * 60 + 20,
    )
    assert validate_event_preconditions(state, event).valid
    after = apply_event(state, event)
    visible = project_player_state(after)

    assert [condition.code for condition in visible.location_conditions] == ["ash_squall"]
    assert visible.location_conditions[0].name == "Ash squall"


def test_scheduled_event_rejects_too_early_out_of_order_and_duplicate_execution() -> None:
    state = build_demo_world()
    too_early = ScheduledLocationConditionApplied(
        turn_number=1,
        scheduled_event_id="yard_ash_squall",
        scheduled_absolute_minute=8 * 60 + 20,
    )
    early_report = validate_event_preconditions(state, too_early)
    assert not early_report.valid
    assert any(issue.code == "invalid_scheduled_world_event" for issue in early_report.issues)

    state.scheduled_location_conditions.append(
        ScheduledLocationCondition(
            id="later_ridge_gust",
            due_absolute_minute=8 * 60 + 21,
            location_id="ridge",
            condition=LocationCondition(
                code="ridge_gust",
                name="Ridge gust",
                description="A hard crosswind tears across Glass Ridge.",
            ),
        )
    )
    state.clock = state.clock.advanced(21)
    out_of_order = ScheduledLocationConditionApplied(
        turn_number=1,
        scheduled_event_id="later_ridge_gust",
        scheduled_absolute_minute=8 * 60 + 21,
    )
    order_report = validate_event_preconditions(state, out_of_order)
    assert not order_report.valid
    assert any(issue.code == "invalid_scheduled_world_event" for issue in order_report.issues)

    first = ScheduledLocationConditionApplied(
        turn_number=1,
        scheduled_event_id="yard_ash_squall",
        scheduled_absolute_minute=8 * 60 + 20,
    )
    assert validate_event_preconditions(state, first).valid
    after_first = apply_event(state, first)
    duplicate_report = validate_event_preconditions(after_first, first)
    assert not duplicate_report.valid
    assert any(
        issue.code == "invalid_scheduled_world_event" for issue in duplicate_report.issues
    )


def test_world_event_scheduler_bounds_backlog_and_events_replay(tmp_path: Path) -> None:
    state = build_demo_world()
    state.simulation.max_scheduled_events_per_turn = 2
    state.scheduled_location_conditions = [
        ScheduledLocationCondition(
            id=f"yard_condition_{index}",
            due_absolute_minute=8 * 60 + index,
            location_id="yard",
            condition=LocationCondition(
                code=f"condition_{index}",
                name=f"Condition {index}",
                description=f"Deterministic environmental condition {index}.",
            ),
        )
        for index in range(1, 6)
    ]
    state.clock = state.clock.advanced(30)
    assert validate_state(state).valid

    schedule = DeterministicWorldEventScheduler().due_events(state)
    assert schedule.due_event_ids == ["yard_condition_1", "yard_condition_2"]
    assert schedule.backlog_remaining

    engine = GameEngine(SQLiteStore(tmp_path / "bounded.db"))
    candidate, emitted = engine._run_due_simulation(state, turn_number=1)

    assert sorted(candidate.locations["yard"].active_conditions) == [
        "condition_1",
        "condition_2",
    ]
    assert [event.id for event in candidate.scheduled_location_conditions] == [
        "yard_condition_3",
        "yard_condition_4",
        "yard_condition_5",
    ]
    assert sum(isinstance(event, ScheduledLocationConditionApplied) for event in emitted) == 2
    assert replay(state, emitted) == candidate


def test_invalid_schedule_state_is_rejected() -> None:
    state = build_demo_world()
    duplicate = state.scheduled_location_conditions[0].model_copy(deep=True)
    state.scheduled_location_conditions.append(duplicate)

    report = validate_state(state)

    assert not report.valid
    assert any(issue.code == "invalid_scheduled_world_event" for issue in report.issues)


def test_provider_failure_prevents_due_world_event_from_committing(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "atomic.db")
    engine = GameEngine(store, generator=FailingNarrativeGenerator())
    session = engine.new_session()
    before = store.load_state(session.id)

    with pytest.raises(ProviderRequestError, match="before scheduled world events"):
        engine.execute_action(session.id, WaitAction(minutes=20), "wait 20")

    assert store.load_state(session.id) == before
    assert store.load_events(session.id) == []
    assert store.list_turns(session.id) == []


def test_api_and_browser_reveal_only_active_environmental_conditions(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path / "api-world-events.db"))
    page = client.get("/ui/")
    script = client.get("/ui/app.js")
    created = client.post("/sessions", json={"name": "World event API"})

    assert page.status_code == 200
    assert script.status_code == 200
    assert 'id="location-conditions"' in page.text
    assert "view.location_conditions" in script.text
    assert created.status_code == 201
    initial_state = created.json()["state"]
    assert initial_state["location_conditions"] == []
    assert "yard_ash_squall" not in json.dumps(created.json(), sort_keys=True)

    session_id = created.json()["session"]["id"]
    action = client.post(
        f"/sessions/{session_id}/actions",
        json={"text": "wait 20"},
    )

    assert action.status_code == 200
    assert action.json()["accepted"] is True
    assert action.json()["state"]["location_conditions"][0]["code"] == "ash_squall"
