from __future__ import annotations

from pathlib import Path

import pytest

from emergent_rpg.domain.actions import MoveAction, WaitAction
from emergent_rpg.domain.events import NPCMoved, SimulationCycleProcessed
from emergent_rpg.domain.models import NPC
from emergent_rpg.engine.narrative import ScenePlan
from emergent_rpg.engine.service import GameEngine
from emergent_rpg.engine.simulation import DeterministicSimulationScheduler
from emergent_rpg.persistence.db import SQLiteStore
from emergent_rpg.providers.base import NarrativeGenerator
from emergent_rpg.providers.errors import ProviderRequestError
from emergent_rpg.validation.validator import validate_event_preconditions
from emergent_rpg.world.demo import build_demo_world


class FailingNarrativeGenerator(NarrativeGenerator):
    def generate(self, scene_plan: ScenePlan) -> str:
        del scene_plan
        raise ProviderRequestError("simulated outage before world simulation")


def make_engine(tmp_path: Path) -> tuple[GameEngine, str]:
    engine = GameEngine(SQLiteStore(tmp_path / "game.db"))
    session = engine.new_session()
    return engine, session.id


def test_scheduler_fires_only_when_canonical_cursor_is_due() -> None:
    state = build_demo_world()
    scheduler = DeterministicSimulationScheduler()

    before = scheduler.due_cycles(state)
    assert before.due_absolute_minutes == []

    state.clock = state.clock.advanced(5)
    due = scheduler.due_cycles(state)
    assert due.due_absolute_minutes == [8 * 60 + 5]
    assert not due.backlog_remaining


def test_automatic_cycle_moves_only_offscreen_npc(tmp_path: Path) -> None:
    engine, session_id = make_engine(tmp_path)

    _, _, state = engine.execute_action(
        session_id,
        WaitAction(minutes=5),
        "wait 5",
    )

    dax = state.entities["npc_dax"]
    lio = state.entities["npc_lio"]
    assert isinstance(dax, NPC)
    assert isinstance(lio, NPC)
    assert dax.state.current_location == "yard"
    assert "dax_reach_yard" in dax.completed_goal_ids
    assert "lio_inspect_brass_key" not in lio.completed_goal_ids
    assert "fact_key_mark" not in lio.knowledge.facts_known
    assert state.simulation.next_due_absolute_minute == 8 * 60 + 10

    events = engine.store.load_events(session_id)
    assert any(isinstance(event, NPCMoved) for event in events)
    assert sum(isinstance(event, SimulationCycleProcessed) for event in events) == 1
    assert engine.replay_session(session_id) == state


def test_npc_can_act_after_player_leaves_visibility(tmp_path: Path) -> None:
    engine, session_id = make_engine(tmp_path)
    engine.execute_action(session_id, WaitAction(minutes=5), "wait 5")

    _, _, state = engine.execute_action(
        session_id,
        MoveAction(destination="operations"),
        "move operations",
    )

    lio = state.entities["npc_lio"]
    assert isinstance(lio, NPC)
    assert "lio_inspect_brass_key" in lio.completed_goal_ids
    assert "fact_key_mark" in lio.knowledge.facts_known
    assert "fact_key_mark" not in state.player_known_facts
    assert state.simulation.next_due_absolute_minute == 8 * 60 + 15
    assert engine.replay_session(session_id) == state


def test_simulation_catch_up_is_bounded_per_player_turn(tmp_path: Path) -> None:
    engine, session_id = make_engine(tmp_path)

    _, _, state = engine.execute_action(
        session_id,
        WaitAction(minutes=100),
        "wait 100",
    )

    markers = [
        event
        for event in engine.store.load_events(session_id)
        if isinstance(event, SimulationCycleProcessed)
    ]
    assert len(markers) == state.simulation.max_catch_up_cycles == 12
    assert state.simulation.next_due_absolute_minute == 8 * 60 + 65
    assert state.simulation.next_due_absolute_minute <= state.clock.absolute_minutes
    assert engine.replay_session(session_id) == state


def test_simulation_does_not_create_extra_player_turn_numbers(tmp_path: Path) -> None:
    engine, session_id = make_engine(tmp_path)

    for index in range(20):
        engine.execute_action(session_id, WaitAction(minutes=1), f"wait 1 #{index}")

    state = engine.store.load_state(session_id)
    turns = engine.store.list_turns(session_id, limit=100)
    assert state.turn_number == 20
    assert len(turns) == 20
    assert engine.replay_session(session_id) == state


def test_simulation_marker_must_match_canonical_cursor() -> None:
    state = build_demo_world()
    state.clock = state.clock.advanced(10)
    forged = SimulationCycleProcessed(
        turn_number=1,
        scheduled_absolute_minute=8 * 60 + 10,
    )

    report = validate_event_preconditions(state, forged)

    assert not report.valid
    assert any(issue.code == "invalid_simulation_cycle" for issue in report.issues)


def test_scheduler_reports_bounded_backlog_before_processing_large_jump() -> None:
    state = build_demo_world()
    state.clock = state.clock.advanced(100)

    schedule = DeterministicSimulationScheduler().due_cycles(state)

    assert len(schedule.due_absolute_minutes) == state.simulation.max_catch_up_cycles
    assert schedule.due_absolute_minutes[0] == 8 * 60 + 5
    assert schedule.due_absolute_minutes[-1] == 8 * 60 + 60
    assert schedule.backlog_remaining


def test_provider_failure_prevents_due_simulation_from_committing(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "game.db")
    engine = GameEngine(store, generator=FailingNarrativeGenerator())
    session = engine.new_session()
    before = store.load_state(session.id)

    with pytest.raises(ProviderRequestError, match="before world simulation"):
        engine.execute_action(session.id, WaitAction(minutes=5), "wait 5")

    assert store.load_state(session.id) == before
    assert store.load_events(session.id) == []
    assert store.list_turns(session.id) == []


def test_offscreen_simulation_does_not_leak_into_player_memory_metadata(
    tmp_path: Path,
) -> None:
    engine, session_id = make_engine(tmp_path)
    engine.execute_action(session_id, WaitAction(minutes=5), "wait 5")

    turns = engine.store.list_turns(session_id, limit=10)
    episodes = engine.store.list_episodes(session_id)

    assert len(turns) == 1
    assert turns[0].involved_entities == {"player"}
    assert len(episodes) == 1
    assert episodes[0].involved_entities == {"player"}
    assert "npc_dax" not in episodes[0].involved_entities
