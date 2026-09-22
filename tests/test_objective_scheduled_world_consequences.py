from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from emergent_rpg.api.models import project_player_state
from emergent_rpg.domain.events import (
    PlayerObjectiveFailed,
    ScheduledLocationConditionQueued,
)
from emergent_rpg.domain.models import (
    GameSession,
    LocationCondition,
    ObjectiveOutcomeScheduledConditionRule,
    PlayerObjective,
    RouteEffect,
    ScheduledLocationCondition,
    TraversalEffect,
    WorldState,
)
from emergent_rpg.engine.narrative import ScenePlan
from emergent_rpg.engine.reducer import ReductionError, apply_event
from emergent_rpg.engine.service import GameEngine
from emergent_rpg.persistence.db import SQLiteStore
from emergent_rpg.providers.base import NarrativeGenerator
from emergent_rpg.providers.errors import ProviderRequestError
from emergent_rpg.validation.validator import validate_event_preconditions, validate_state
from emergent_rpg.world.demo import build_demo_world


class FailingNarrativeGenerator(NarrativeGenerator):
    def generate(self, scene_plan: ScenePlan) -> str:
        del scene_plan
        raise ProviderRequestError("simulated scheduled objective outage")


def _objective(
    objective_id: str,
    *,
    completion_fact: str,
    deadline_absolute_minute: int | None = None,
) -> PlayerObjective:
    return PlayerObjective(
        id=objective_id,
        title=objective_id.replace("_", " ").title(),
        description=f"Objective {objective_id}.",
        deadline_absolute_minute=deadline_absolute_minute,
        completion_required_fact_ids={completion_fact},
    )


def _condition(code: str = "objective_lockdown") -> LocationCondition:
    return LocationCondition(
        code=code,
        name="Objective Lockdown",
        description="The objective outcome temporarily seals the operations route.",
        traversal=TraversalEffect(extra_minutes=3),
        route=RouteEffect(blocked_destination_ids={"operations"}),
    )


def _rule(
    rule_id: str,
    objective_id: str,
    *,
    outcome: str = "completed",
    scheduled_event_id: str = "objective_lockdown_event",
    delay_minutes: int = 3,
    expires_after_minutes: int | None = 2,
    priority: int = 0,
    condition: LocationCondition | None = None,
) -> ObjectiveOutcomeScheduledConditionRule:
    return ObjectiveOutcomeScheduledConditionRule(
        id=rule_id,
        objective_id=objective_id,
        outcome=outcome,
        scheduled_event_id=scheduled_event_id,
        delay_minutes=delay_minutes,
        location_id="yard",
        condition=condition or _condition(),
        expires_after_minutes=expires_after_minutes,
        priority=priority,
    )


def _create_session(store: SQLiteStore, state: WorldState) -> GameSession:
    session = GameSession(
        id="objective-schedule-session",
        name="Objective schedule test",
        world_pack="objective-schedule-test",
        created_at="2026-09-22T00:00:00+00:00",
    )
    store.create_session(session, state)
    return session


def test_completion_queues_then_applies_and_expires_existing_world_condition(
    tmp_path: Path,
) -> None:
    store = SQLiteStore(tmp_path / "scheduled-completion.db")
    state = build_demo_world()
    state.player_objectives = [
        _objective("seal_route", completion_fact="fact_key_mark")
    ]
    state.active_player_objective_ids = {"seal_route"}
    state.player_known_facts.add("fact_key_mark")
    state.objective_outcome_scheduled_condition_rules = [
        _rule("seal_route_schedule", "seal_route")
    ]
    session = _create_session(store, state)
    engine = GameEngine(store)

    first, _, queued_state = engine.process_text(session.id, "wait 1")

    queue_event = next(
        event
        for event in first.emitted_events
        if isinstance(event, ScheduledLocationConditionQueued)
    )
    assert queue_event.scheduled_event_id == "objective_lockdown_event"
    assert queue_event.due_absolute_minute == 8 * 60 + 4
    pending = next(
        scheduled
        for scheduled in queued_state.scheduled_location_conditions
        if scheduled.id == "objective_lockdown_event"
    )
    assert pending.due_absolute_minute == 8 * 60 + 4
    assert "objective_lockdown" not in queued_state.locations["yard"].active_conditions
    assert queued_state.applied_objective_outcome_scheduled_condition_rule_ids == {
        "seal_route_schedule"
    }
    wire = project_player_state(queued_state).model_dump_json()
    assert "objective_lockdown_event" not in wire
    assert "Objective Lockdown" not in wire
    assert engine.replay_session(session.id) == queued_state

    _, _, active_state = engine.process_text(session.id, "wait 3")

    assert "objective_lockdown" in active_state.locations["yard"].active_conditions
    assert not any(
        scheduled.id == "objective_lockdown_event"
        for scheduled in active_state.scheduled_location_conditions
    )
    active_view = project_player_state(active_state)
    assert [item.code for item in active_view.location_conditions] == [
        "objective_lockdown"
    ]
    assert "operations" not in active_view.exits
    assert engine.replay_session(session.id) == active_state

    _, _, expired_state = engine.process_text(session.id, "wait 2")

    assert "objective_lockdown" not in expired_state.locations["yard"].active_conditions
    assert engine.replay_session(session.id) == expired_state


def test_failed_objective_can_queue_scheduled_world_consequence(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "scheduled-failure.db")
    state = build_demo_world()
    state.player_objectives = [
        _objective(
            "missed_window",
            completion_fact="fact_inside_job",
            deadline_absolute_minute=state.clock.absolute_minutes + 1,
        )
    ]
    state.active_player_objective_ids = {"missed_window"}
    state.objective_outcome_scheduled_condition_rules = [
        _rule(
            "failure_schedule",
            "missed_window",
            outcome="failed",
            scheduled_event_id="failure_weather",
        )
    ]
    session = _create_session(store, state)
    engine = GameEngine(store)

    result, _, final_state = engine.process_text(session.id, "wait 1")

    assert any(isinstance(event, PlayerObjectiveFailed) for event in result.emitted_events)
    assert any(
        isinstance(event, ScheduledLocationConditionQueued)
        and event.scheduled_event_id == "failure_weather"
        for event in result.emitted_events
    )
    assert final_state.failed_player_objective_ids == {"missed_window"}
    assert final_state.applied_objective_outcome_scheduled_condition_rule_ids == {
        "failure_schedule"
    }
    assert engine.replay_session(session.id) == final_state


def test_forged_queue_before_terminal_outcome_is_rejected() -> None:
    state = build_demo_world()
    state.player_objectives = [
        _objective("still_open", completion_fact="fact_key_mark")
    ]
    state.active_player_objective_ids = {"still_open"}
    state.objective_outcome_scheduled_condition_rules = [
        _rule("premature_schedule", "still_open")
    ]
    forged = ScheduledLocationConditionQueued(
        turn_number=1,
        rule_id="premature_schedule",
        objective_id="still_open",
        outcome="completed",
        scheduled_event_id="objective_lockdown_event",
        due_absolute_minute=state.clock.absolute_minutes + 3,
    )

    precheck = validate_event_preconditions(state, forged)
    assert not precheck.valid
    assert "not canonically completed" in str(precheck.issues)
    with pytest.raises(ReductionError, match="not canonically completed"):
        apply_event(state, forged)


def test_schedule_queue_rejects_wrong_due_minute_and_duplicate_id() -> None:
    state = build_demo_world()
    state.player_objectives = [
        _objective("terminal", completion_fact="fact_key_mark")
    ]
    state.completed_player_objective_ids = {"terminal"}
    state.objective_outcome_scheduled_condition_rules = [
        _rule("schedule_rule", "terminal")
    ]

    wrong_due = ScheduledLocationConditionQueued(
        turn_number=1,
        rule_id="schedule_rule",
        objective_id="terminal",
        outcome="completed",
        scheduled_event_id="objective_lockdown_event",
        due_absolute_minute=state.clock.absolute_minutes,
    )
    report = validate_event_preconditions(state, wrong_due)
    assert not report.valid
    assert "due minute does not match" in str(report.issues)

    state.scheduled_location_conditions.append(
        ScheduledLocationCondition(
            id="objective_lockdown_event",
            due_absolute_minute=state.clock.absolute_minutes + 20,
            location_id="ridge",
            condition=LocationCondition(
                code="existing_event",
                name="Existing Event",
                description="Existing scheduled condition.",
            ),
        )
    )
    duplicate = wrong_due.model_copy(
        update={"due_absolute_minute": state.clock.absolute_minutes + 3}
    )
    duplicate_report = validate_event_preconditions(state, duplicate)
    assert not duplicate_report.valid
    assert "scheduled event id is already pending" in str(duplicate_report.issues)


def test_direct_pending_schedule_mutation_requires_queue_provenance() -> None:
    before = build_demo_world()
    after = before.model_copy(deep=True)
    after.scheduled_location_conditions.append(
        ScheduledLocationCondition(
            id="forged_queue",
            due_absolute_minute=before.clock.absolute_minutes + 5,
            location_id="yard",
            condition=_condition("forged_condition"),
        )
    )

    report = validate_state(after, previous=before, transition_events=[])

    assert not report.valid
    assert "added without queue provenance" in str(report.issues)


def test_high_priority_schedule_rule_consumes_outcome_once(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "scheduled-priority.db")
    state = build_demo_world()
    state.player_objectives = [
        _objective("priority_case", completion_fact="fact_key_mark")
    ]
    state.active_player_objective_ids = {"priority_case"}
    state.player_known_facts.add("fact_key_mark")
    state.objective_outcome_scheduled_condition_rules = [
        _rule(
            "low_schedule",
            "priority_case",
            scheduled_event_id="low_event",
            priority=1,
            condition=_condition("low_condition"),
        ),
        _rule(
            "high_schedule",
            "priority_case",
            scheduled_event_id="high_event",
            priority=10,
            condition=_condition("high_condition"),
        ),
    ]
    session = _create_session(store, state)
    engine = GameEngine(store)

    _, _, final_state = engine.process_text(session.id, "wait 1")

    assert final_state.applied_objective_outcome_scheduled_condition_rule_ids == {
        "high_schedule"
    }
    assert any(
        scheduled.id == "high_event"
        for scheduled in final_state.scheduled_location_conditions
    )
    assert not any(
        scheduled.id == "low_event"
        for scheduled in final_state.scheduled_location_conditions
    )

    forged_low = ScheduledLocationConditionQueued(
        turn_number=final_state.turn_number,
        rule_id="low_schedule",
        objective_id="priority_case",
        outcome="completed",
        scheduled_event_id="low_event",
        due_absolute_minute=final_state.clock.absolute_minutes + 3,
    )
    with pytest.raises(
        ReductionError,
        match="no objective outcome schedule rule is eligible",
    ):
        apply_event(final_state, forged_low)


def test_provider_failure_keeps_queued_world_consequence_zero_commit(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "scheduled-provider.db")
    state = build_demo_world()
    state.player_objectives = [
        _objective("atomic_schedule", completion_fact="fact_key_mark")
    ]
    state.active_player_objective_ids = {"atomic_schedule"}
    state.player_known_facts.add("fact_key_mark")
    state.objective_outcome_scheduled_condition_rules = [
        _rule("atomic_schedule_rule", "atomic_schedule")
    ]
    session = _create_session(store, state)
    before = store.load_state(session.id)
    engine = GameEngine(store, generator=FailingNarrativeGenerator())

    with pytest.raises(ProviderRequestError, match="scheduled objective outage"):
        engine.process_text(session.id, "wait 1")

    assert store.load_state(session.id) == before
    assert store.load_events(session.id) == []
    assert store.list_turns(session.id) == []


def test_world_rejects_invalid_objective_schedule_rule_targets() -> None:
    state = build_demo_world()
    objective_id = state.player_objectives[0].id
    state.objective_outcome_scheduled_condition_rules = [
        _rule(
            "bad_route_rule",
            objective_id,
            condition=LocationCondition(
                code="bad_route",
                name="Bad Route",
                description="Invalid route target.",
                route=RouteEffect(blocked_destination_ids={"archive"}),
            ),
        )
    ]
    with pytest.raises(
        ValidationError,
        match="objective outcome schedule rule blocks non-local exits",
    ):
        WorldState.model_validate(state.model_dump())

    payload = build_demo_world().model_dump(mode="json")
    payload["objective_outcome_scheduled_condition_rules"] = [
        {
            "id": "missing_location_rule",
            "objective_id": objective_id,
            "outcome": "completed",
            "scheduled_event_id": "missing_location_event",
            "delay_minutes": 3,
            "location_id": "missing",
            "condition": {
                "code": "missing",
                "name": "Missing",
                "description": "Missing location.",
            },
        }
    ]
    with pytest.raises(
        ValidationError,
        match="objective outcome schedule rule references missing location",
    ):
        WorldState.model_validate(payload)
