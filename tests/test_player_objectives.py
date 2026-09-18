from __future__ import annotations

from pathlib import Path

import pytest

from emergent_rpg.api.models import project_player_state
from emergent_rpg.domain.actions import TakeAction
from emergent_rpg.domain.events import PlayerObjectiveActivated, PlayerObjectiveCompleted
from emergent_rpg.domain.models import GameSession, PlayerObjective, WorldState
from emergent_rpg.engine.narrative import ScenePlan
from emergent_rpg.engine.objectives import PlayerObjectivePolicy
from emergent_rpg.engine.reducer import apply_event
from emergent_rpg.engine.service import GameEngine
from emergent_rpg.persistence.db import SQLiteStore
from emergent_rpg.providers.base import NarrativeGenerator
from emergent_rpg.providers.errors import ProviderRequestError
from emergent_rpg.validation.validator import validate_event_preconditions, validate_state
from emergent_rpg.world.demo import build_demo_world


class FailingNarrativeGenerator(NarrativeGenerator):
    def generate(self, scene_plan: ScenePlan) -> str:
        del scene_plan
        raise ProviderRequestError("simulated outage during objective progression")


def _objective(
    objective_id: str,
    *,
    activation_facts: set[str] | None = None,
    activation_items: set[str] | None = None,
    activation_objectives: set[str] | None = None,
    completion_facts: set[str] | None = None,
) -> PlayerObjective:
    return PlayerObjective(
        id=objective_id,
        title=objective_id.replace("_", " ").title(),
        description=f"Public description for {objective_id}.",
        activation_required_fact_ids=activation_facts or set(),
        activation_required_item_ids=activation_items or set(),
        activation_required_completed_objective_ids=activation_objectives or set(),
        completion_required_fact_ids=completion_facts or {"fact_relay_sabotage"},
    )


def _create_session(store: SQLiteStore, state: WorldState) -> GameSession:
    session = GameSession(
        id="objective-session",
        name="Objective test",
        world_pack="objective-test",
        created_at="2026-09-18T00:00:00+00:00",
    )
    store.create_session(session, state)
    return session


def test_objective_policy_deterministically_cascades_dependencies() -> None:
    state = build_demo_world()
    state.player_objectives = [
        _objective("objective_a", completion_facts={"fact_key_mark"}),
        _objective(
            "objective_b",
            activation_objectives={"objective_a"},
            completion_facts={"fact_relay_sabotage"},
        ),
    ]
    state.player_known_facts.update({"fact_key_mark", "fact_relay_sabotage"})

    events = PlayerObjectivePolicy.progression_events(state, turn_number=1)

    assert [
        (event.type, event.objective_id)
        for event in events
    ] == [
        ("player_objective_activated", "objective_a"),
        ("player_objective_completed", "objective_a"),
        ("player_objective_activated", "objective_b"),
        ("player_objective_completed", "objective_b"),
    ]


def test_forged_objective_events_fail_preconditions() -> None:
    state = build_demo_world()
    state.player_objectives = [
        _objective(
            "locked",
            activation_facts={"fact_key_mark"},
            completion_facts={"fact_relay_sabotage"},
        )
    ]

    activation = PlayerObjectiveActivated(turn_number=1, objective_id="locked")
    activation_report = validate_event_preconditions(state, activation)
    assert not activation_report.valid
    assert "activation requirements are not met" in str(activation_report.issues)

    completion = PlayerObjectiveCompleted(turn_number=1, objective_id="locked")
    completion_report = validate_event_preconditions(state, completion)
    assert not completion_report.valid
    assert "is not active" in str(completion_report.issues)


def test_direct_objective_state_mutation_requires_event_provenance() -> None:
    before = build_demo_world()
    before.player_objectives = [_objective("tracked")]
    after = before.model_copy(deep=True)
    after.active_player_objective_ids.add("tracked")

    report = validate_state(after, previous=before, transition_events=[])

    assert not report.valid
    assert "player objective state does not match lifecycle event provenance" in str(
        report.issues
    )


def test_reducer_applies_objective_activation_and_completion() -> None:
    state = build_demo_world()
    state.player_objectives = [_objective("tracked")]
    activated = apply_event(
        state,
        PlayerObjectiveActivated(turn_number=1, objective_id="tracked"),
    )
    completed = apply_event(
        activated,
        PlayerObjectiveCompleted(turn_number=1, objective_id="tracked"),
    )

    assert activated.active_player_objective_ids == {"tracked"}
    assert activated.completed_player_objective_ids == set()
    assert completed.active_player_objective_ids == set()
    assert completed.completed_player_objective_ids == {"tracked"}


def test_engine_persists_objective_lifecycle_and_replays_exactly(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "objectives.db")
    state = build_demo_world()
    state.player_objectives = [
        _objective(
            "investigate_blackout",
            activation_facts={"fact_key_mark"},
            completion_facts={"fact_relay_sabotage"},
        )
    ]
    session = _create_session(store, state)
    engine = GameEngine(store)

    take, _, after_take = engine.process_text(session.id, "take brass key")
    assert take.accepted
    assert after_take.active_player_objective_ids == {"investigate_blackout"}
    assert any(isinstance(event, PlayerObjectiveActivated) for event in take.emitted_events)

    moved, _, _ = engine.process_text(session.id, "move operations")
    assert moved.accepted
    inspected, _, final_state = engine.process_text(session.id, "inspect console")
    assert inspected.accepted
    assert final_state.active_player_objective_ids == set()
    assert final_state.completed_player_objective_ids == {"investigate_blackout"}
    assert any(isinstance(event, PlayerObjectiveCompleted) for event in inspected.emitted_events)

    assert engine.replay_session(session.id) == final_state
    persisted = store.load_events(session.id)
    assert sum(isinstance(event, PlayerObjectiveActivated) for event in persisted) == 1
    assert sum(isinstance(event, PlayerObjectiveCompleted) for event in persisted) == 1


def test_provider_failure_does_not_commit_objective_progression(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "objective-provider.db")
    state = build_demo_world()
    state.player_objectives = [
        _objective(
            "take_key",
            activation_facts={"fact_key_mark"},
            completion_facts={"fact_relay_sabotage"},
        )
    ]
    session = _create_session(store, state)
    before = store.load_state(session.id)
    engine = GameEngine(store, generator=FailingNarrativeGenerator())

    with pytest.raises(ProviderRequestError, match="simulated outage"):
        engine.execute_action(
            session.id,
            TakeAction(target="brass key"),
            "take brass key",
        )

    assert store.load_state(session.id) == before
    assert store.load_events(session.id) == []
    assert store.list_turns(session.id) == []


def test_player_projection_hides_pending_objectives_and_prerequisites() -> None:
    state = build_demo_world()
    state.player_objectives = [
        _objective(
            "pending_secret",
            activation_facts={"fact_blackout_window"},
            completion_facts={"fact_relay_sabotage"},
        ),
        _objective("visible_active"),
        _objective("visible_done"),
    ]
    state.active_player_objective_ids = {"visible_active"}
    state.completed_player_objective_ids = {"visible_done"}

    view = project_player_state(state)
    wire = view.model_dump_json()

    assert [item.id for item in view.active_objectives] == ["visible_active"]
    assert [item.id for item in view.completed_objectives] == ["visible_done"]
    assert "pending_secret" not in wire
    assert "fact_blackout_window" not in wire
    assert "fact_relay_sabotage" not in wire


def test_demo_objectives_are_pending_until_player_earns_prerequisites() -> None:
    state = build_demo_world()
    view = project_player_state(state)

    assert {objective.id for objective in state.player_objectives} == {
        "objective_trace_blackout",
        "objective_expose_sabotage",
    }
    assert view.active_objectives == []
    assert view.completed_objectives == []
