from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from emergent_rpg.domain.actions import WaitAction
from emergent_rpg.domain.events import NPCFactShared, NPCGoalCompleted, NPCMoved
from emergent_rpg.domain.models import GameSession, NPC, NPCGoal, WorldState
from emergent_rpg.domain.npc_actions import NPCMoveIntent
from emergent_rpg.engine.npc import (
    DeterministicNPCPlanner,
    DeterministicNPCResolver,
    build_npc_planning_context,
)
from emergent_rpg.engine.reducer import ReductionError, apply_event
from emergent_rpg.engine.service import GameEngine
from emergent_rpg.persistence.db import SQLiteStore
from emergent_rpg.world.demo import build_demo_world

REQUIRED_FACT = "fact_blackout_window"
GATED_GOAL_ID = "dax_reach_operations_after_blackout"
STATIC_GOAL_ID = "dax_reach_yard_anyway"


def _reactive_state() -> tuple[WorldState, NPC, NPC]:
    state = build_demo_world()
    arden = state.entities["npc_arden"]
    dax = state.entities["npc_dax"]
    assert isinstance(arden, NPC)
    assert isinstance(dax, NPC)

    for entity in state.entities.values():
        if isinstance(entity, NPC):
            entity.planning_goals.clear()
            entity.completed_goal_ids.clear()
    state.dialogue_relationship_rules.clear()
    state.applied_dialogue_relationship_rule_ids.clear()

    dax.state.current_location = "bunkhouse"
    dax.knowledge.facts_known.discard(REQUIRED_FACT)
    dax.knowledge.mapped_locations = {"bunkhouse", "yard", "operations"}
    dax.planning_goals = [
        NPCGoal(
            id=GATED_GOAL_ID,
            kind="reach_location",
            target_id="operations",
            priority=100,
            required_fact_ids={REQUIRED_FACT},
        ),
        NPCGoal(
            id=STATIC_GOAL_ID,
            kind="reach_location",
            target_id="yard",
            priority=10,
        ),
    ]

    arden.planning_goals.clear()
    arden.knowledge.facts_known = {REQUIRED_FACT}
    return state, arden, dax


def _persist_engine(tmp_path: Path, state: WorldState, session_id: str) -> GameEngine:
    store = SQLiteStore(tmp_path / f"{session_id}.db")
    session = GameSession(
        id=session_id,
        name="Reactive NPC goals",
        world_pack="test-reactive-goals",
        created_at="2026-09-12T00:00:00+00:00",
    )
    store.create_session(session, state)
    return GameEngine(store)


def test_goal_prerequisites_are_backwards_compatible_and_world_references_are_validated() -> None:
    plain = NPCGoal(id="plain", kind="reach_location", target_id="yard")
    assert plain.required_fact_ids == set()

    state, _, dax = _reactive_state()
    invalid = state.model_copy(deep=True)
    invalid_dax = invalid.entities[dax.id]
    assert isinstance(invalid_dax, NPC)
    invalid_dax.planning_goals[0] = invalid_dax.planning_goals[0].model_copy(
        update={"required_fact_ids": {"fact_that_does_not_exist"}}
    )
    with pytest.raises(ValidationError, match="NPC goal prerequisites"):
        WorldState.model_validate(invalid.model_dump(mode="python"))


def test_planner_uses_only_acting_npc_knowledge_and_reprioritizes_after_learning() -> None:
    state, arden, dax = _reactive_state()
    assert REQUIRED_FACT in arden.knowledge.facts_known
    assert REQUIRED_FACT not in dax.knowledge.facts_known

    before = DeterministicNPCPlanner().plan(build_npc_planning_context(state, dax.id))
    assert len(before.intents) == 1
    assert before.intents[0].goal_id == STATIC_GOAL_ID

    learned = state.model_copy(deep=True)
    learned_dax = learned.entities[dax.id]
    assert isinstance(learned_dax, NPC)
    learned_dax.knowledge.facts_known.add(REQUIRED_FACT)
    after = DeterministicNPCPlanner().plan(build_npc_planning_context(learned, dax.id))
    assert len(after.intents) == 1
    assert after.intents[0].goal_id == GATED_GOAL_ID


def test_resolver_and_reducer_reject_forged_dormant_goal_execution() -> None:
    state, _, dax = _reactive_state()
    forged = NPCMoveIntent(goal_id=GATED_GOAL_ID, destination_id="yard")
    result = DeterministicNPCResolver().resolve(state, dax.id, forged, turn_number=1)
    assert not result.accepted
    assert result.reason == "NPC goal prerequisites are not known."
    assert result.emitted_events == []

    at_target = state.model_copy(deep=True)
    at_target_dax = at_target.entities[dax.id]
    assert isinstance(at_target_dax, NPC)
    at_target_dax.state.current_location = "operations"
    completion = NPCGoalCompleted(
        turn_number=1,
        npc_id=dax.id,
        goal_id=GATED_GOAL_ID,
        method="reached_location",
        evidence_id="operations",
    )
    with pytest.raises(ReductionError, match="prerequisites are not known"):
        apply_event(at_target, completion)


def test_explicit_social_learning_activates_goal_on_later_goal_phase_and_replays(
    tmp_path: Path,
) -> None:
    state, arden, dax = _reactive_state()
    arden.state.current_location = "bunkhouse"
    engine = _persist_engine(tmp_path, state, "explicit-reactive-goal")

    before_phase, before = engine.run_npc_phase("explicit-reactive-goal", max_actions=1)
    assert before_phase.actions_executed == 1
    before_move = next(
        event for event in before_phase.emitted_events if isinstance(event, NPCMoved)
    )
    assert before_move.npc_id == dax.id
    assert before_move.to_location == "yard"
    before_dax = before.entities[dax.id]
    assert isinstance(before_dax, NPC)
    assert STATIC_GOAL_ID in before_dax.completed_goal_ids
    assert GATED_GOAL_ID not in before_dax.completed_goal_ids

    # Return Dax to the social source location through a fresh deterministic test state
    # so the social phase itself, rather than direct knowledge mutation, unlocks M26.
    reset = state.model_copy(deep=True)
    reset_dax = reset.entities[dax.id]
    reset_arden = reset.entities[arden.id]
    assert isinstance(reset_dax, NPC)
    assert isinstance(reset_arden, NPC)
    reset_dax.planning_goals = [reset_dax.planning_goals[0]]
    reset_arden.state.current_location = "bunkhouse"
    reset_dax.state.current_location = "bunkhouse"
    reset_dax.knowledge.facts_known.discard(REQUIRED_FACT)
    engine = _persist_engine(tmp_path, reset, "explicit-reactive-social")

    dormant_phase, _ = engine.run_npc_phase("explicit-reactive-social", max_actions=1)
    assert dormant_phase.actions_executed == 0

    social_phase, shared = engine.run_npc_social_phase(
        "explicit-reactive-social",
        max_actions=1,
    )
    share = next(event for event in social_phase.emitted_events if isinstance(event, NPCFactShared))
    assert share.source_npc_id == arden.id
    assert share.receiver_npc_id == dax.id
    assert share.fact_id == REQUIRED_FACT
    shared_dax = shared.entities[dax.id]
    assert isinstance(shared_dax, NPC)
    assert REQUIRED_FACT in shared_dax.knowledge.facts_known
    assert shared_dax.state.current_location == "bunkhouse"

    activated_phase, after = engine.run_npc_phase("explicit-reactive-social", max_actions=1)
    activated_move = next(
        event for event in activated_phase.emitted_events if isinstance(event, NPCMoved)
    )
    assert activated_move.npc_id == dax.id
    assert activated_move.from_location == "bunkhouse"
    assert activated_move.to_location == "yard"
    assert activated_phase.decisions[0].intent.goal_id == GATED_GOAL_ID
    assert engine.replay_session("explicit-reactive-social") == after

    restarted = GameEngine(SQLiteStore(tmp_path / "explicit-reactive-social.db"))
    assert restarted.store.load_state("explicit-reactive-social") == after
    assert restarted.replay_session("explicit-reactive-social") == after


def test_offscreen_social_learning_activates_only_on_next_simulation_goal_phase(
    tmp_path: Path,
) -> None:
    state, arden, dax = _reactive_state()
    dax.planning_goals = [dax.planning_goals[0]]
    arden.state.current_location = "bunkhouse"
    state.player().state.current_location = "operations"
    state.simulation.max_npc_actions_per_cycle = 1
    state.simulation.max_social_actions_per_cycle = 1
    engine = _persist_engine(tmp_path, state, "offscreen-reactive-goal")

    _, _, after_first = engine.execute_action(
        "offscreen-reactive-goal",
        WaitAction(minutes=5),
        "wait 5",
    )
    first_dax = after_first.entities[dax.id]
    assert isinstance(first_dax, NPC)
    assert REQUIRED_FACT in first_dax.knowledge.facts_known
    assert first_dax.state.current_location == "bunkhouse"

    first_events = engine.store.load_events("offscreen-reactive-goal")
    first_share = next(event for event in first_events if isinstance(event, NPCFactShared))
    assert first_share.receiver_npc_id == dax.id
    assert not any(
        isinstance(event, NPCMoved) and event.npc_id == dax.id for event in first_events
    )

    _, _, after_second = engine.execute_action(
        "offscreen-reactive-goal",
        WaitAction(minutes=5),
        "wait 5",
    )
    second_dax = after_second.entities[dax.id]
    assert isinstance(second_dax, NPC)
    assert second_dax.state.current_location == "yard"
    second_events = engine.store.load_events("offscreen-reactive-goal")
    dax_moves = [
        event
        for event in second_events
        if isinstance(event, NPCMoved) and event.npc_id == dax.id
    ]
    assert len(dax_moves) == 1
    assert dax_moves[0].from_location == "bunkhouse"
    assert dax_moves[0].to_location == "yard"
    assert engine.replay_session("offscreen-reactive-goal") == after_second
