from __future__ import annotations

from pathlib import Path

from emergent_rpg.domain.events import (
    NPCGoalCompleted,
    NPCItemLocationObserved,
    NPCMoved,
)
from emergent_rpg.domain.models import GameSession, NPC, NPCGoal
from emergent_rpg.domain.npc_actions import NPCInspectIntent, NPCMoveIntent
from emergent_rpg.engine.npc import (
    DeterministicNPCPlanner,
    DeterministicNPCResolver,
    build_npc_planning_context,
)
from emergent_rpg.engine.reducer import apply_event
from emergent_rpg.engine.service import GameEngine
from emergent_rpg.persistence.db import SQLiteStore
from emergent_rpg.validation.validator import validate_event_preconditions, validate_state
from emergent_rpg.world.demo import build_demo_world


def _apply_events(state, events):
    candidate = state
    for event in events:
        report = validate_event_preconditions(candidate, event)
        assert report.valid, report.issues
        candidate = apply_event(candidate, event)
    return candidate


def _dax_item_pursuit_state():
    state = build_demo_world()
    dax = state.entities["npc_dax"]
    assert isinstance(dax, NPC)
    dax.state.current_location = "operations"
    dax.planning_goals = [
        NPCGoal(
            id="dax_find_key",
            kind="investigate_item",
            target_id="item_brass_key",
            priority=100,
        )
    ]
    dax.completed_goal_ids.clear()
    dax.knowledge.mapped_locations = {"operations", "yard"}
    dax.knowledge.item_location_beliefs = {"item_brass_key": "yard"}
    return state, dax


def test_planning_context_exposes_own_belief_not_global_item_truth() -> None:
    state = build_demo_world()
    lio = state.entities["npc_lio"]
    assert isinstance(lio, NPC)

    context = build_npc_planning_context(state, lio.id)

    assert "item_brass_key" in context.visible_item_ids
    assert context.known_item_locations == {}

    lio.knowledge.item_location_beliefs["item_brass_key"] = "operations"
    remembered = build_npc_planning_context(state, lio.id)

    assert remembered.known_item_locations == {"item_brass_key": "operations"}
    assert state.items["item_brass_key"].location_id == "yard"


def test_item_observation_requires_local_truth_and_can_clear_stale_belief() -> None:
    state = build_demo_world()
    remote = NPCItemLocationObserved(
        turn_number=1,
        npc_id="npc_dax",
        item_id="item_brass_key",
        location_id="yard",
        present=True,
    )
    remote_report = validate_event_preconditions(state, remote)
    assert not remote_report.valid
    assert any(
        issue.code == "invalid_npc_item_observation" for issue in remote_report.issues
    )

    positive = NPCItemLocationObserved(
        turn_number=1,
        npc_id="npc_lio",
        item_id="item_brass_key",
        location_id="yard",
        present=True,
    )
    assert validate_event_preconditions(state, positive).valid
    learned = apply_event(state, positive)
    lio = learned.entities["npc_lio"]
    assert isinstance(lio, NPC)
    assert lio.knowledge.item_location_beliefs == {"item_brass_key": "yard"}

    learned.items["item_brass_key"].location_id = "archive"
    negative = NPCItemLocationObserved(
        turn_number=2,
        npc_id="npc_lio",
        item_id="item_brass_key",
        location_id="yard",
        present=False,
    )
    assert validate_event_preconditions(learned, negative).valid
    cleared = apply_event(learned, negative)
    cleared_lio = cleared.entities["npc_lio"]
    assert isinstance(cleared_lio, NPC)
    assert cleared_lio.knowledge.item_location_beliefs == {}


def test_state_validation_requires_item_belief_observation_provenance() -> None:
    before = build_demo_world()
    after = before.model_copy(deep=True)
    lio = after.entities["npc_lio"]
    assert isinstance(lio, NPC)
    lio.knowledge.item_location_beliefs["item_brass_key"] = "yard"

    unauthorized = validate_state(after, previous=before)

    assert not unauthorized.valid
    assert any(
        issue.code == "npc_item_belief_changed_without_observation"
        for issue in unauthorized.issues
    )

    observation = NPCItemLocationObserved(
        turn_number=1,
        npc_id="npc_lio",
        item_id="item_brass_key",
        location_id="yard",
        present=True,
    )
    authorized = validate_state(
        after,
        previous=before,
        transition_events=[observation],
    )
    assert authorized.valid


def test_accepted_action_observes_secondary_item_without_cross_npc_leak() -> None:
    state = build_demo_world()
    dax = state.entities["npc_dax"]
    lio = state.entities["npc_lio"]
    assert isinstance(dax, NPC)
    assert isinstance(lio, NPC)
    dax.state.current_location = "yard"
    dax.planning_goals = [
        NPCGoal(
            id="dax_reach_operations",
            kind="reach_location",
            target_id="operations",
            priority=100,
        ),
        NPCGoal(
            id="dax_find_key",
            kind="investigate_item",
            target_id="item_brass_key",
            priority=50,
        ),
    ]
    dax.completed_goal_ids.clear()
    dax.knowledge.mapped_locations = {"yard", "operations"}

    plan = DeterministicNPCPlanner().plan(build_npc_planning_context(state, dax.id))
    assert len(plan.intents) == 1
    intent = plan.intents[0]
    assert isinstance(intent, NPCMoveIntent)
    assert intent.destination_id == "operations"

    result = DeterministicNPCResolver().resolve(state, dax.id, intent, turn_number=1)
    assert result.accepted
    assert isinstance(result.emitted_events[0], NPCItemLocationObserved)
    candidate = _apply_events(state, result.emitted_events)

    moved_dax = candidate.entities["npc_dax"]
    unchanged_lio = candidate.entities["npc_lio"]
    assert isinstance(moved_dax, NPC)
    assert isinstance(unchanged_lio, NPC)
    assert moved_dax.state.current_location == "operations"
    assert moved_dax.knowledge.item_location_beliefs == {"item_brass_key": "yard"}
    assert unchanged_lio.knowledge.item_location_beliefs == {}
    assert "dax_reach_operations" in moved_dax.completed_goal_ids


def test_stale_belief_drives_pursuit_then_local_search_invalidates_it() -> None:
    state, dax = _dax_item_pursuit_state()
    state.items["item_brass_key"].location_id = "archive"
    planner = DeterministicNPCPlanner()
    resolver = DeterministicNPCResolver()

    first_plan = planner.plan(build_npc_planning_context(state, dax.id))
    first_intent = first_plan.intents[0]
    assert isinstance(first_intent, NPCMoveIntent)
    assert first_intent.destination_id == "yard"

    first_result = resolver.resolve(state, dax.id, first_intent, turn_number=1)
    assert first_result.accepted
    state = _apply_events(state, first_result.emitted_events)
    dax = state.entities["npc_dax"]
    assert isinstance(dax, NPC)
    assert dax.state.current_location == "yard"
    assert dax.knowledge.item_location_beliefs == {"item_brass_key": "yard"}
    assert "dax_find_key" not in dax.completed_goal_ids

    second_plan = planner.plan(build_npc_planning_context(state, dax.id))
    second_intent = second_plan.intents[0]
    assert isinstance(second_intent, NPCInspectIntent)

    second_result = resolver.resolve(state, dax.id, second_intent, turn_number=2)
    assert second_result.accepted
    assert second_result.reason == "Item is no longer at the remembered location."
    assert sum(
        isinstance(event, NPCItemLocationObserved)
        and not event.present
        for event in second_result.emitted_events
    ) == 1
    state = _apply_events(state, second_result.emitted_events)
    dax = state.entities["npc_dax"]
    assert isinstance(dax, NPC)
    assert dax.knowledge.item_location_beliefs == {}
    assert "dax_find_key" not in dax.completed_goal_ids
    assert planner.plan(build_npc_planning_context(state, dax.id)).intents == []


def test_resolver_rejects_forged_item_pursuit_move_when_item_is_local() -> None:
    state, dax = _dax_item_pursuit_state()
    state.items["item_brass_key"].location_id = "operations"
    forged = NPCMoveIntent(goal_id="dax_find_key", destination_id="yard")

    result = DeterministicNPCResolver().resolve(
        state,
        dax.id,
        forged,
        turn_number=1,
    )

    assert not result.accepted
    assert result.reason == "Investigation target is already accessible here."
    assert result.emitted_events == []


def test_item_observation_and_pursuit_persist_across_restart_and_replay(
    tmp_path: Path,
) -> None:
    state = build_demo_world()
    dax = state.entities["npc_dax"]
    assert isinstance(dax, NPC)
    dax.state.current_location = "yard"
    dax.planning_goals = [
        NPCGoal(
            id="dax_reach_operations",
            kind="reach_location",
            target_id="operations",
            priority=100,
        ),
        NPCGoal(
            id="dax_find_key",
            kind="investigate_item",
            target_id="item_brass_key",
            priority=50,
        ),
    ]
    dax.completed_goal_ids.clear()
    dax.knowledge.mapped_locations = {"yard", "operations"}

    db_path = tmp_path / "npc-item-pursuit.db"
    store = SQLiteStore(db_path)
    session = GameSession(
        id="npc-item-pursuit",
        name="NPC item pursuit",
        world_pack="test-item-pursuit",
        created_at="2026-09-12T00:00:00+00:00",
    )
    store.create_session(session, state)
    engine = GameEngine(store)

    phase, after = engine.run_npc_phase(session.id, max_actions=1)

    observations = [
        event
        for event in phase.emitted_events
        if isinstance(event, NPCItemLocationObserved)
    ]
    assert len(observations) == 1
    assert observations[0].item_id == "item_brass_key"
    assert observations[0].location_id == "yard"
    assert observations[0].present
    after_dax = after.entities["npc_dax"]
    assert isinstance(after_dax, NPC)
    assert after_dax.knowledge.item_location_beliefs == {"item_brass_key": "yard"}
    assert engine.replay_session(session.id) == after

    restarted = GameEngine(SQLiteStore(db_path))
    assert restarted.store.load_state(session.id) == after
    assert restarted.replay_session(session.id) == after


def test_successful_local_inspection_still_completes_goal() -> None:
    state = build_demo_world()
    resolver = DeterministicNPCResolver()
    intent = NPCInspectIntent(
        goal_id="lio_inspect_brass_key",
        item_id="item_brass_key",
    )

    result = resolver.resolve(state, "npc_lio", intent, turn_number=1)

    assert result.accepted
    assert any(
        isinstance(event, NPCItemLocationObserved) and event.present
        for event in result.emitted_events
    )
    assert any(isinstance(event, NPCGoalCompleted) for event in result.emitted_events)
    candidate = _apply_events(state, result.emitted_events)
    lio = candidate.entities["npc_lio"]
    assert isinstance(lio, NPC)
    assert "lio_inspect_brass_key" in lio.completed_goal_ids
    assert lio.knowledge.item_location_beliefs == {"item_brass_key": "yard"}
