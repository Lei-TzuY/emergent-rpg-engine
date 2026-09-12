from __future__ import annotations

from pathlib import Path

from emergent_rpg.domain.actions import TakeAction, WaitAction
from emergent_rpg.domain.events import (
    ItemAcquired,
    NPCGoalCompleted,
    NPCItemLocationObserved,
)
from emergent_rpg.domain.models import NPC, GameSession, NPCGoal
from emergent_rpg.domain.npc_actions import (
    NPCAcquireIntent,
    NPCCompleteGoalIntent,
    NPCInspectIntent,
    NPCMoveIntent,
)
from emergent_rpg.engine.npc import (
    DeterministicNPCPlanner,
    DeterministicNPCResolver,
    build_npc_planning_context,
)
from emergent_rpg.engine.reducer import apply_event
from emergent_rpg.engine.resolver import DeterministicResolver
from emergent_rpg.engine.service import GameEngine
from emergent_rpg.persistence.db import SQLiteStore
from emergent_rpg.validation.validator import validate_event_preconditions, validate_state
from emergent_rpg.world.demo import build_demo_world

GOAL_ID = "dax_acquire_brass_key"
ITEM_ID = "item_brass_key"


def _acquisition_state(*, location: str = "yard", remembered: str | None = None):
    state = build_demo_world()
    for entity in state.entities.values():
        if isinstance(entity, NPC):
            entity.planning_goals.clear()
            entity.completed_goal_ids.clear()
    dax = state.entities["npc_dax"]
    assert isinstance(dax, NPC)
    dax.state.current_location = location
    dax.knowledge.mapped_locations = {"bunkhouse", "yard", "operations"}
    dax.knowledge.item_location_beliefs.clear()
    if remembered is not None:
        dax.knowledge.item_location_beliefs[ITEM_ID] = remembered
    dax.planning_goals = [
        NPCGoal(
            id=GOAL_ID,
            kind="acquire_item",
            target_id=ITEM_ID,
            priority=100,
        )
    ]
    return state, dax


def _apply_events(state, events):
    before = state
    candidate = state
    for event in events:
        report = validate_event_preconditions(candidate, event)
        assert report.valid, report.issues
        candidate = apply_event(candidate, event)
    final_report = validate_state(candidate, previous=before, transition_events=list(events))
    assert final_report.valid, final_report.issues
    return candidate


def _persist_engine(tmp_path: Path, state, session_id: str) -> GameEngine:
    store = SQLiteStore(tmp_path / f"{session_id}.db")
    session = GameSession(
        id=session_id,
        name="NPC item acquisition",
        world_pack="test-npc-item-acquisition",
        created_at="2026-09-12T00:00:00+00:00",
    )
    store.create_session(session, state)
    return GameEngine(store)


def test_local_acquisition_uses_existing_item_event_clears_belief_and_completes_goal() -> None:
    state, dax = _acquisition_state(location="yard")
    planner = DeterministicNPCPlanner()
    resolver = DeterministicNPCResolver()

    plan = planner.plan(build_npc_planning_context(state, dax.id))
    assert len(plan.intents) == 1
    intent = plan.intents[0]
    assert isinstance(intent, NPCAcquireIntent)
    assert intent.item_id == ITEM_ID

    result = resolver.resolve(state, dax.id, intent, turn_number=1)
    assert result.accepted
    assert [type(event) for event in result.emitted_events] == [
        NPCItemLocationObserved,
        ItemAcquired,
        NPCItemLocationObserved,
        NPCGoalCompleted,
    ]
    assert result.emitted_events[0].present is True
    assert result.emitted_events[2].present is False

    after = _apply_events(state, result.emitted_events)
    after_dax = after.entities[dax.id]
    assert isinstance(after_dax, NPC)
    assert after.items[ITEM_ID].owner_id == dax.id
    assert after.items[ITEM_ID].location_id is None
    assert ITEM_ID in after_dax.state.inventory
    assert after_dax.knowledge.item_location_beliefs == {}
    assert GOAL_ID in after_dax.completed_goal_ids


def test_already_owned_acquisition_target_completes_without_second_item_transfer() -> None:
    state, dax = _acquisition_state(location="yard")
    item = state.items[ITEM_ID]
    item.location_id = None
    item.owner_id = dax.id
    dax.state.inventory.append(ITEM_ID)

    plan = DeterministicNPCPlanner().plan(build_npc_planning_context(state, dax.id))
    assert len(plan.intents) == 1
    intent = plan.intents[0]
    assert isinstance(intent, NPCCompleteGoalIntent)

    result = DeterministicNPCResolver().resolve(state, dax.id, intent, turn_number=1)
    assert result.accepted
    assert not any(isinstance(event, ItemAcquired) for event in result.emitted_events)
    assert any(
        isinstance(event, NPCGoalCompleted) and event.method == "acquired_item"
        for event in result.emitted_events
    )
    after = _apply_events(state, result.emitted_events)
    after_dax = after.entities[dax.id]
    assert isinstance(after_dax, NPC)
    assert GOAL_ID in after_dax.completed_goal_ids


def test_remembered_remote_item_is_pursued_stepwise_then_acquired() -> None:
    state, dax = _acquisition_state(location="bunkhouse", remembered="yard")
    planner = DeterministicNPCPlanner()
    resolver = DeterministicNPCResolver()

    first_plan = planner.plan(build_npc_planning_context(state, dax.id))
    first_intent = first_plan.intents[0]
    assert isinstance(first_intent, NPCMoveIntent)
    assert first_intent.destination_id == "yard"
    first_result = resolver.resolve(state, dax.id, first_intent, turn_number=1)
    assert first_result.accepted
    state = _apply_events(state, first_result.emitted_events)

    moved_dax = state.entities[dax.id]
    assert isinstance(moved_dax, NPC)
    assert moved_dax.state.current_location == "yard"
    assert GOAL_ID not in moved_dax.completed_goal_ids

    second_plan = planner.plan(build_npc_planning_context(state, dax.id))
    second_intent = second_plan.intents[0]
    assert isinstance(second_intent, NPCAcquireIntent)
    second_result = resolver.resolve(state, dax.id, second_intent, turn_number=2)
    assert second_result.accepted
    state = _apply_events(state, second_result.emitted_events)

    final_dax = state.entities[dax.id]
    assert isinstance(final_dax, NPC)
    assert state.items[ITEM_ID].owner_id == dax.id
    assert ITEM_ID in final_dax.state.inventory
    assert GOAL_ID in final_dax.completed_goal_ids


def test_stale_acquisition_belief_drives_local_search_and_is_cleared() -> None:
    state, dax = _acquisition_state(location="yard", remembered="yard")
    state.items[ITEM_ID].location_id = "archive"

    plan = DeterministicNPCPlanner().plan(build_npc_planning_context(state, dax.id))
    intent = plan.intents[0]
    assert isinstance(intent, NPCInspectIntent)

    result = DeterministicNPCResolver().resolve(state, dax.id, intent, turn_number=1)
    assert result.accepted
    assert result.reason == "Item is no longer at the remembered location."
    assert len(result.emitted_events) == 1
    observation = result.emitted_events[0]
    assert isinstance(observation, NPCItemLocationObserved)
    assert observation.present is False

    after = _apply_events(state, result.emitted_events)
    after_dax = after.entities[dax.id]
    assert isinstance(after_dax, NPC)
    assert after_dax.knowledge.item_location_beliefs == {}
    assert GOAL_ID not in after_dax.completed_goal_ids
    assert DeterministicNPCPlanner().plan(
        build_npc_planning_context(after, dax.id)
    ).intents == []


def test_acquisition_resolver_rejects_nonportable_and_owned_targets() -> None:
    state, dax = _acquisition_state(location="yard")
    state.items[ITEM_ID].flags.discard("portable")
    intent = NPCAcquireIntent(goal_id=GOAL_ID, item_id=ITEM_ID)

    nonportable = DeterministicNPCResolver().resolve(state, dax.id, intent, turn_number=1)
    assert not nonportable.accepted
    assert nonportable.reason == "Acquisition target is not portable."
    assert nonportable.emitted_events == []

    state, dax = _acquisition_state(location="yard")
    lio = state.entities["npc_lio"]
    assert isinstance(lio, NPC)
    state.items[ITEM_ID].location_id = None
    state.items[ITEM_ID].owner_id = lio.id
    lio.state.inventory.append(ITEM_ID)
    owned = DeterministicNPCResolver().resolve(state, dax.id, intent, turn_number=1)
    assert not owned.accepted
    assert owned.reason == "Acquisition target is owned by someone else."
    assert owned.emitted_events == []


def test_generic_item_acquisition_validator_blocks_remote_and_nonportable_forgery() -> None:
    state, dax = _acquisition_state(location="bunkhouse", remembered="yard")
    remote = ItemAcquired(
        turn_number=1,
        item_id=ITEM_ID,
        actor_id=dax.id,
        from_location="yard",
    )
    remote_report = validate_event_preconditions(state, remote)
    assert not remote_report.valid
    assert any(issue.code == "invalid_item_acquisition" for issue in remote_report.issues)

    local, local_dax = _acquisition_state(location="yard")
    local.items[ITEM_ID].flags.discard("portable")
    forged_nonportable = ItemAcquired(
        turn_number=1,
        item_id=ITEM_ID,
        actor_id=local_dax.id,
        from_location="yard",
    )
    nonportable_report = validate_event_preconditions(local, forged_nonportable)
    assert not nonportable_report.valid
    assert any(issue.code == "invalid_item_acquisition" for issue in nonportable_report.issues)


def test_forged_acquisition_goal_completion_requires_canonical_custody() -> None:
    state, dax = _acquisition_state(location="yard")
    forged = NPCGoalCompleted(
        turn_number=1,
        npc_id=dax.id,
        goal_id=GOAL_ID,
        method="acquired_item",
        evidence_id=ITEM_ID,
    )

    report = validate_event_preconditions(state, forged)

    assert not report.valid
    assert any(issue.code == "invalid_npc_goal" for issue in report.issues)


def test_acquisition_goal_respects_knowledge_prerequisites() -> None:
    state, dax = _acquisition_state(location="yard")
    required_fact = "fact_blackout_window"
    dax.knowledge.facts_known.discard(required_fact)
    dax.planning_goals[0] = dax.planning_goals[0].model_copy(
        update={"required_fact_ids": {required_fact}}
    )

    dormant = DeterministicNPCPlanner().plan(build_npc_planning_context(state, dax.id))
    assert dormant.intents == []

    dax.knowledge.facts_known.add(required_fact)
    active = DeterministicNPCPlanner().plan(build_npc_planning_context(state, dax.id))
    assert len(active.intents) == 1
    assert isinstance(active.intents[0], NPCAcquireIntent)


def test_player_take_cleanly_rejects_nonportable_item() -> None:
    state = build_demo_world()
    state.items[ITEM_ID].flags.discard("portable")

    result = DeterministicResolver().resolve(state, TakeAction(target="brass key"))

    assert not result.accepted
    assert result.reason == "That item cannot be carried."
    assert result.emitted_events == []


def test_explicit_acquisition_persists_restarts_and_replays(tmp_path: Path) -> None:
    state, dax = _acquisition_state(location="yard")
    engine = _persist_engine(tmp_path, state, "explicit-acquisition")

    phase, after = engine.run_npc_phase("explicit-acquisition", max_actions=1)

    assert phase.actions_executed == 1
    assert any(isinstance(event, ItemAcquired) for event in phase.emitted_events)
    after_dax = after.entities[dax.id]
    assert isinstance(after_dax, NPC)
    assert after.items[ITEM_ID].owner_id == dax.id
    assert ITEM_ID in after_dax.state.inventory
    assert GOAL_ID in after_dax.completed_goal_ids
    assert engine.replay_session("explicit-acquisition") == after

    restarted = GameEngine(SQLiteStore(tmp_path / "explicit-acquisition.db"))
    assert restarted.store.load_state("explicit-acquisition") == after
    assert restarted.replay_session("explicit-acquisition") == after


def test_offscreen_simulation_can_acquire_item_under_existing_npc_budget(tmp_path: Path) -> None:
    state, dax = _acquisition_state(location="yard")
    state.player().state.current_location = "operations"
    state.simulation.max_npc_actions_per_cycle = 1
    state.simulation.max_social_actions_per_cycle = 1
    engine = _persist_engine(tmp_path, state, "offscreen-acquisition")

    _, _, after = engine.execute_action(
        "offscreen-acquisition",
        WaitAction(minutes=5),
        "wait 5",
    )

    after_dax = after.entities[dax.id]
    assert isinstance(after_dax, NPC)
    assert after.items[ITEM_ID].owner_id == dax.id
    assert ITEM_ID in after_dax.state.inventory
    assert GOAL_ID in after_dax.completed_goal_ids
    events = engine.store.load_events("offscreen-acquisition")
    assert any(
        isinstance(event, ItemAcquired) and event.actor_id == dax.id for event in events
    )
    assert engine.replay_session("offscreen-acquisition") == after
