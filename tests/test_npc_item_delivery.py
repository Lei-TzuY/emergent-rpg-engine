from __future__ import annotations

from pathlib import Path

from emergent_rpg.domain.actions import WaitAction
from emergent_rpg.domain.events import NPCGoalCompleted, NPCItemDelivered
from emergent_rpg.domain.models import NPC, GameSession, NPCGoal
from emergent_rpg.domain.npc_actions import NPCDeliverIntent, NPCMoveIntent
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

GOAL_ID = "dax_deliver_brass_key"
ITEM_ID = "item_brass_key"
SOURCE_ID = "npc_dax"
RECEIVER_ID = "npc_sera"
DELIVERY_LOCATION_ID = "archive"


def _delivery_state(
    *,
    source_location: str = "bunkhouse",
    receiver_location: str = DELIVERY_LOCATION_ID,
):
    state = build_demo_world()
    for entity in state.entities.values():
        if isinstance(entity, NPC):
            entity.planning_goals.clear()
            entity.completed_goal_ids.clear()

    source = state.entities[SOURCE_ID]
    receiver = state.entities[RECEIVER_ID]
    assert isinstance(source, NPC)
    assert isinstance(receiver, NPC)
    source.state.current_location = source_location
    receiver.state.current_location = receiver_location
    source.knowledge.mapped_locations = {
        "bunkhouse",
        "yard",
        "operations",
        "archive",
    }
    source.planning_goals = [
        NPCGoal(
            id=GOAL_ID,
            kind="deliver_item",
            target_id=ITEM_ID,
            receiver_id=RECEIVER_ID,
            delivery_location_id=DELIVERY_LOCATION_ID,
            priority=100,
        )
    ]

    item = state.items[ITEM_ID]
    item.location_id = None
    item.owner_id = SOURCE_ID
    if ITEM_ID not in source.state.inventory:
        source.state.inventory.append(ITEM_ID)
    return state, source, receiver


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
        name="NPC item delivery",
        world_pack="test-npc-item-delivery",
        created_at="2026-09-12T00:00:00+00:00",
    )
    store.create_session(session, state)
    return GameEngine(store)


def test_delivery_routes_to_rendezvous_then_transfers_unique_custody() -> None:
    state, source, receiver = _delivery_state()
    planner = DeterministicNPCPlanner()
    resolver = DeterministicNPCResolver()

    expected_hops = ["yard", "operations", "archive"]
    for turn_number, destination_id in enumerate(expected_hops, start=1):
        plan = planner.plan(build_npc_planning_context(state, source.id))
        assert len(plan.intents) == 1
        intent = plan.intents[0]
        assert isinstance(intent, NPCMoveIntent)
        assert intent.destination_id == destination_id
        result = resolver.resolve(state, source.id, intent, turn_number=turn_number)
        assert result.accepted
        assert not any(isinstance(event, NPCGoalCompleted) for event in result.emitted_events)
        state = _apply_events(state, result.emitted_events)
        source = state.entities[SOURCE_ID]
        assert isinstance(source, NPC)

    plan = planner.plan(build_npc_planning_context(state, source.id))
    assert len(plan.intents) == 1
    delivery_intent = plan.intents[0]
    assert isinstance(delivery_intent, NPCDeliverIntent)
    assert delivery_intent.item_id == ITEM_ID
    assert delivery_intent.receiver_id == RECEIVER_ID

    result = resolver.resolve(state, source.id, delivery_intent, turn_number=4)
    assert result.accepted
    assert [type(event) for event in result.emitted_events] == [
        NPCItemDelivered,
        NPCGoalCompleted,
    ]
    delivery_event = result.emitted_events[0]
    assert isinstance(delivery_event, NPCItemDelivered)
    assert delivery_event.source_npc_id == SOURCE_ID
    assert delivery_event.receiver_id == RECEIVER_ID
    assert delivery_event.item_id == ITEM_ID
    assert delivery_event.goal_id == GOAL_ID

    after = _apply_events(state, result.emitted_events)
    after_source = after.entities[SOURCE_ID]
    after_receiver = after.entities[RECEIVER_ID]
    assert isinstance(after_source, NPC)
    assert isinstance(after_receiver, NPC)
    assert after.items[ITEM_ID].owner_id == RECEIVER_ID
    assert after.items[ITEM_ID].location_id is None
    assert ITEM_ID not in after_source.state.inventory
    assert ITEM_ID in after_receiver.state.inventory
    assert GOAL_ID in after_source.completed_goal_ids


def test_delivery_planner_uses_configured_rendezvous_not_remote_receiver_location() -> None:
    state, source, receiver = _delivery_state(receiver_location="infirmary")
    planner = DeterministicNPCPlanner()

    plan = planner.plan(build_npc_planning_context(state, source.id))

    assert len(plan.intents) == 1
    intent = plan.intents[0]
    assert isinstance(intent, NPCMoveIntent)
    assert intent.destination_id == "yard"
    assert receiver.id not in build_npc_planning_context(state, source.id).visible_entity_ids

    source.state.current_location = DELIVERY_LOCATION_ID
    at_rendezvous = planner.plan(build_npc_planning_context(state, source.id))
    assert at_rendezvous.intents == []


def test_delivery_resolver_rejects_wrong_remote_inactive_and_nonportable_handoffs() -> None:
    state, source, receiver = _delivery_state(
        source_location=DELIVERY_LOCATION_ID,
        receiver_location=DELIVERY_LOCATION_ID,
    )
    resolver = DeterministicNPCResolver()

    wrong_receiver = NPCDeliverIntent(
        goal_id=GOAL_ID,
        item_id=ITEM_ID,
        receiver_id="npc_mina",
    )
    wrong = resolver.resolve(state, source.id, wrong_receiver, turn_number=1)
    assert not wrong.accepted
    assert wrong.emitted_events == []

    receiver.state.current_location = "infirmary"
    remote_intent = NPCDeliverIntent(
        goal_id=GOAL_ID,
        item_id=ITEM_ID,
        receiver_id=RECEIVER_ID,
    )
    remote = resolver.resolve(state, source.id, remote_intent, turn_number=1)
    assert not remote.accepted
    assert remote.reason == "Delivery receiver is not here."
    assert remote.emitted_events == []

    receiver.state.current_location = DELIVERY_LOCATION_ID
    receiver.state.conscious = False
    inactive = resolver.resolve(state, source.id, remote_intent, turn_number=1)
    assert not inactive.accepted
    assert inactive.reason == "Delivery receiver cannot interact."

    receiver.state.conscious = True
    state.items[ITEM_ID].flags.discard("portable")
    nonportable = resolver.resolve(state, source.id, remote_intent, turn_number=1)
    assert not nonportable.accepted
    assert nonportable.reason == "Delivery item is not portable."


def test_delivery_requires_source_custody_and_configured_location() -> None:
    state, source, receiver = _delivery_state(
        source_location="operations",
        receiver_location="operations",
    )
    intent = NPCDeliverIntent(
        goal_id=GOAL_ID,
        item_id=ITEM_ID,
        receiver_id=receiver.id,
    )
    resolver = DeterministicNPCResolver()

    wrong_location = resolver.resolve(state, source.id, intent, turn_number=1)
    assert not wrong_location.accepted
    assert wrong_location.reason == "NPC is not at the delivery location."

    source.state.current_location = DELIVERY_LOCATION_ID
    receiver.state.current_location = DELIVERY_LOCATION_ID
    source.state.inventory.remove(ITEM_ID)
    state.items[ITEM_ID].owner_id = receiver.id
    receiver.state.inventory.append(ITEM_ID)
    no_custody = resolver.resolve(state, source.id, intent, turn_number=1)
    assert not no_custody.accepted
    assert no_custody.reason == "NPC does not own the delivery item."


def test_generic_delivery_validator_rejects_forged_provenance_and_duplicate_inventory() -> None:
    state, source, receiver = _delivery_state(
        source_location=DELIVERY_LOCATION_ID,
        receiver_location=DELIVERY_LOCATION_ID,
    )

    wrong_goal = NPCItemDelivered(
        turn_number=1,
        source_npc_id=source.id,
        receiver_id=receiver.id,
        item_id=ITEM_ID,
        goal_id="missing_goal",
    )
    wrong_goal_report = validate_event_preconditions(state, wrong_goal)
    assert not wrong_goal_report.valid
    assert any(
        issue.code == "invalid_npc_item_delivery" for issue in wrong_goal_report.issues
    )

    remote = NPCItemDelivered(
        turn_number=1,
        source_npc_id=source.id,
        receiver_id=receiver.id,
        item_id=ITEM_ID,
        goal_id=GOAL_ID,
    )
    receiver.state.current_location = "infirmary"
    remote_report = validate_event_preconditions(state, remote)
    assert not remote_report.valid
    assert any(
        issue.code == "invalid_npc_item_delivery" for issue in remote_report.issues
    )

    receiver.state.current_location = DELIVERY_LOCATION_ID
    receiver.state.inventory.append(ITEM_ID)
    duplicate_report = validate_event_preconditions(state, remote)
    assert not duplicate_report.valid
    assert any(
        issue.code == "invalid_npc_item_delivery" for issue in duplicate_report.issues
    )


def test_forged_delivery_goal_completion_requires_receiver_custody() -> None:
    state, source, _ = _delivery_state(
        source_location=DELIVERY_LOCATION_ID,
        receiver_location=DELIVERY_LOCATION_ID,
    )
    forged = NPCGoalCompleted(
        turn_number=1,
        npc_id=source.id,
        goal_id=GOAL_ID,
        method="delivered_item",
        evidence_id=ITEM_ID,
    )

    report = validate_event_preconditions(state, forged)

    assert not report.valid
    assert any(issue.code == "invalid_npc_goal" for issue in report.issues)


def test_delivery_goal_respects_source_knowledge_prerequisites() -> None:
    state, source, _ = _delivery_state(
        source_location=DELIVERY_LOCATION_ID,
        receiver_location=DELIVERY_LOCATION_ID,
    )
    required_fact = "fact_blackout_window"
    source.knowledge.facts_known.discard(required_fact)
    source.planning_goals[0] = source.planning_goals[0].model_copy(
        update={"required_fact_ids": {required_fact}}
    )

    dormant = DeterministicNPCPlanner().plan(build_npc_planning_context(state, source.id))
    assert dormant.intents == []

    source.knowledge.facts_known.add(required_fact)
    active = DeterministicNPCPlanner().plan(build_npc_planning_context(state, source.id))
    assert len(active.intents) == 1
    assert isinstance(active.intents[0], NPCDeliverIntent)


def test_delivery_does_not_globally_synchronize_item_location_beliefs() -> None:
    state, source, receiver = _delivery_state(
        source_location=DELIVERY_LOCATION_ID,
        receiver_location=DELIVERY_LOCATION_ID,
    )
    lio = state.entities["npc_lio"]
    assert isinstance(lio, NPC)
    lio.knowledge.item_location_beliefs[ITEM_ID] = "yard"
    receiver.knowledge.item_location_beliefs[ITEM_ID] = "operations"
    intent = NPCDeliverIntent(
        goal_id=GOAL_ID,
        item_id=ITEM_ID,
        receiver_id=receiver.id,
    )

    result = DeterministicNPCResolver().resolve(state, source.id, intent, turn_number=1)
    assert result.accepted
    after = _apply_events(state, result.emitted_events)

    after_lio = after.entities[lio.id]
    after_receiver = after.entities[receiver.id]
    assert isinstance(after_lio, NPC)
    assert isinstance(after_receiver, NPC)
    assert after_lio.knowledge.item_location_beliefs[ITEM_ID] == "yard"
    assert after_receiver.knowledge.item_location_beliefs[ITEM_ID] == "operations"


def test_explicit_delivery_persists_restarts_and_replays(tmp_path: Path) -> None:
    state, source, receiver = _delivery_state(
        source_location=DELIVERY_LOCATION_ID,
        receiver_location=DELIVERY_LOCATION_ID,
    )
    engine = _persist_engine(tmp_path, state, "explicit-delivery")

    phase, after = engine.run_npc_phase("explicit-delivery", max_actions=1)

    assert phase.actions_executed == 1
    assert any(isinstance(event, NPCItemDelivered) for event in phase.emitted_events)
    after_source = after.entities[source.id]
    after_receiver = after.entities[receiver.id]
    assert isinstance(after_source, NPC)
    assert isinstance(after_receiver, NPC)
    assert after.items[ITEM_ID].owner_id == receiver.id
    assert ITEM_ID not in after_source.state.inventory
    assert ITEM_ID in after_receiver.state.inventory
    assert GOAL_ID in after_source.completed_goal_ids
    assert engine.replay_session("explicit-delivery") == after

    restarted = GameEngine(SQLiteStore(tmp_path / "explicit-delivery.db"))
    assert restarted.store.load_state("explicit-delivery") == after
    assert restarted.replay_session("explicit-delivery") == after


def test_offscreen_simulation_can_deliver_under_existing_npc_budget(tmp_path: Path) -> None:
    state, source, receiver = _delivery_state(
        source_location=DELIVERY_LOCATION_ID,
        receiver_location=DELIVERY_LOCATION_ID,
    )
    state.player().state.current_location = "yard"
    state.simulation.max_npc_actions_per_cycle = 1
    engine = _persist_engine(tmp_path, state, "offscreen-delivery")

    _, _, after = engine.execute_action(
        "offscreen-delivery",
        WaitAction(minutes=5),
        "wait 5",
    )

    after_source = after.entities[source.id]
    after_receiver = after.entities[receiver.id]
    assert isinstance(after_source, NPC)
    assert isinstance(after_receiver, NPC)
    assert after.items[ITEM_ID].owner_id == receiver.id
    assert ITEM_ID not in after_source.state.inventory
    assert ITEM_ID in after_receiver.state.inventory
    assert GOAL_ID in after_source.completed_goal_ids
    events = engine.store.load_events("offscreen-delivery")
    assert any(
        isinstance(event, NPCItemDelivered)
        and event.source_npc_id == source.id
        and event.receiver_id == receiver.id
        for event in events
    )
    assert engine.replay_session("offscreen-delivery") == after
