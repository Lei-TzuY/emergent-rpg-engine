from __future__ import annotations

from pathlib import Path

from emergent_rpg.domain.events import NPCGoalCompleted, NPCMoved
from emergent_rpg.domain.models import (
    NPC,
    GameSession,
    LocationCondition,
    NPCGoal,
    RouteEffect,
)
from emergent_rpg.domain.npc_actions import NPCMoveIntent
from emergent_rpg.engine.navigation import deterministic_next_hop
from emergent_rpg.engine.npc import (
    DeterministicNPCPlanner,
    DeterministicNPCResolver,
    build_npc_planning_context,
)
from emergent_rpg.engine.reducer import apply_event
from emergent_rpg.engine.service import GameEngine
from emergent_rpg.persistence.db import SQLiteStore
from emergent_rpg.validation.validator import validate_event_preconditions
from emergent_rpg.world.demo import build_demo_world


def _navigation_state():
    state = build_demo_world()
    dax = state.entities["npc_dax"]
    assert isinstance(dax, NPC)
    dax.state.current_location = "bunkhouse"
    dax.planning_goals = [
        NPCGoal(
            id="dax_reach_archive",
            kind="reach_location",
            target_id="archive",
            priority=100,
        )
    ]
    dax.completed_goal_ids.clear()
    dax.knowledge.mapped_locations = {
        "bunkhouse",
        "yard",
        "operations",
        "archive",
    }
    return state, dax


def _apply_npc_result(state, result):
    candidate = state
    for event in result.emitted_events:
        report = validate_event_preconditions(candidate, event)
        assert report.valid, report.issues
        candidate = apply_event(candidate, event)
    return candidate


def test_bounded_path_selection_has_stable_tie_breaking() -> None:
    routes = {
        "start": {"c", "b"},
        "b": {"target"},
        "c": {"target"},
    }

    assert deterministic_next_hop("start", "target", routes) == "b"

    long_routes = {f"n{index}": {f"n{index + 1}"} for index in range(9)}
    assert deterministic_next_hop("n0", "n9", long_routes, max_hops=8) is None


def test_planner_does_not_route_through_unmapped_global_topology() -> None:
    state, dax = _navigation_state()
    dax.knowledge.mapped_locations = {"bunkhouse"}

    context = build_npc_planning_context(state, dax.id)
    plan = DeterministicNPCPlanner().plan(context)

    assert context.known_routes == {"bunkhouse": {"yard"}}
    assert plan.intents == []


def test_resolver_accepts_intermediate_steps_and_completes_only_final_hop() -> None:
    state, dax = _navigation_state()
    planner = DeterministicNPCPlanner()
    resolver = DeterministicNPCResolver()

    expected_locations = ["yard", "operations", "archive"]
    for turn_number, expected_location in enumerate(expected_locations, start=1):
        context = build_npc_planning_context(state, dax.id)
        plan = planner.plan(context)
        assert len(plan.intents) == 1
        intent = plan.intents[0]
        assert isinstance(intent, NPCMoveIntent)
        assert intent.destination_id == expected_location

        result = resolver.resolve(state, dax.id, intent, turn_number=turn_number)
        assert result.accepted
        completion_events = [
            event for event in result.emitted_events if isinstance(event, NPCGoalCompleted)
        ]
        if expected_location == "archive":
            assert len(completion_events) == 1
        else:
            assert completion_events == []
        state = _apply_npc_result(state, result)

    dax = state.entities["npc_dax"]
    assert isinstance(dax, NPC)
    assert dax.state.current_location == "archive"
    assert "dax_reach_archive" in dax.completed_goal_ids


def test_resolver_rejects_accessible_but_wrong_known_route_step() -> None:
    state, dax = _navigation_state()
    dax.state.current_location = "yard"
    forged = NPCMoveIntent(
        goal_id="dax_reach_archive",
        destination_id="ridge",
    )

    result = DeterministicNPCResolver().resolve(
        state,
        dax.id,
        forged,
        turn_number=1,
    )

    assert not result.accepted
    assert result.reason is not None and "deterministic known route" in result.reason


def test_remote_closure_is_not_omniscient_then_causes_local_reroute() -> None:
    state, dax = _navigation_state()
    state.locations["ridge"].exits["archive"] = "archive"
    dax.knowledge.mapped_locations.add("ridge")
    state.locations["yard"].active_conditions["sealed_operations"] = LocationCondition(
        code="sealed_operations",
        name="Sealed operations door",
        description="A pressure shutter seals the operations route.",
        route=RouteEffect(blocked_destination_ids={"operations"}),
    )

    before = build_npc_planning_context(state, dax.id)
    assert "operations" in before.known_routes["yard"]
    first_plan = DeterministicNPCPlanner().plan(before)
    first_intent = first_plan.intents[0]
    assert isinstance(first_intent, NPCMoveIntent)
    assert first_intent.destination_id == "yard"

    first_result = DeterministicNPCResolver().resolve(
        state,
        dax.id,
        first_intent,
        turn_number=1,
    )
    assert first_result.accepted
    state = _apply_npc_result(state, first_result)

    at_yard = build_npc_planning_context(state, dax.id)
    assert "operations" not in at_yard.known_routes["yard"]
    second_plan = DeterministicNPCPlanner().plan(at_yard)
    second_intent = second_plan.intents[0]
    assert isinstance(second_intent, NPCMoveIntent)
    assert second_intent.destination_id == "ridge"


def test_multi_hop_npc_phase_persists_and_replays_each_step(tmp_path: Path) -> None:
    state, _ = _navigation_state()
    store = SQLiteStore(tmp_path / "npc-navigation.db")
    session = GameSession(
        id="navigation-session",
        name="Navigation integration",
        world_pack="test-navigation",
        created_at="2026-09-12T00:00:00+00:00",
    )
    store.create_session(session, state)
    engine = GameEngine(store)

    destinations: list[str] = []
    for _ in range(3):
        phase, current = engine.run_npc_phase(session.id, max_actions=1)
        assert phase.actions_executed == 1
        moved = [event for event in phase.emitted_events if isinstance(event, NPCMoved)]
        assert len(moved) == 1
        destinations.append(moved[0].to_location)
        assert engine.replay_session(session.id) == current

    final_state = store.load_state(session.id)
    dax = final_state.entities["npc_dax"]
    assert isinstance(dax, NPC)
    assert destinations == ["yard", "operations", "archive"]
    assert dax.state.current_location == "archive"
    assert "dax_reach_archive" in dax.completed_goal_ids
    assert len(store.list_turns(session.id)) == 3
