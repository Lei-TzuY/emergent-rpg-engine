from __future__ import annotations

from pathlib import Path

from emergent_rpg.domain.events import FactDiscovered, NPCGoalCompleted, NPCMoved
from emergent_rpg.domain.models import NPC, NPCGoal
from emergent_rpg.domain.npc_actions import NPCMoveIntent
from emergent_rpg.engine.npc import (
    DeterministicNPCPlanner,
    DeterministicNPCResolver,
    build_npc_planning_context,
)
from emergent_rpg.engine.service import GameEngine
from emergent_rpg.persistence.db import SQLiteStore
from emergent_rpg.validation.validator import validate_state
from emergent_rpg.world.demo import build_demo_world


def test_planning_context_exposes_only_npcs_own_knowledge_and_local_surface() -> None:
    state = build_demo_world()
    state.player_known_facts.add("fact_schedule")
    context = build_npc_planning_context(state, "npc_lio")

    assert context.known_fact_ids == {"fact_generator_stable"}
    assert context.beliefs == {}
    assert context.relationships == {}
    assert set(context.known_fact_propositions) == {"fact_generator_stable"}
    assert "fact_schedule" not in context.known_fact_ids
    assert "fact_dax_generator_claim" not in context.known_fact_ids
    assert context.current_location_id == "yard"
    assert "item_brass_key" in context.visible_item_ids
    assert "item_maintenance_slate" not in context.visible_item_ids


def test_planner_is_bounded_and_prioritizes_configured_goal() -> None:
    state = build_demo_world()
    context = build_npc_planning_context(state, "npc_dax")

    plan = DeterministicNPCPlanner().plan(context, max_steps=1)

    assert len(plan.intents) == 1
    intent = plan.intents[0]
    assert isinstance(intent, NPCMoveIntent)
    assert intent.goal_id == "dax_reach_yard"
    assert intent.destination_id == "yard"


def test_npc_resolver_rejects_destination_outside_local_exit() -> None:
    state = build_demo_world()
    resolver = DeterministicNPCResolver()
    intent = NPCMoveIntent(goal_id="dax_reach_yard", destination_id="ridge")

    result = resolver.resolve(state, "npc_dax", intent, turn_number=1)

    assert not result.accepted
    assert result.emitted_events == []


def test_npc_phase_executes_goals_without_leaking_knowledge(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "game.db")
    engine = GameEngine(store)
    session = engine.new_session()

    phase, state = engine.run_npc_phase(session.id, max_actions=2)

    assert phase.actions_attempted == 2
    assert phase.actions_executed == 2
    assert phase.involved_npc_ids == {"npc_dax", "npc_lio"}
    assert any(isinstance(event, NPCMoved) for event in phase.emitted_events)
    assert any(isinstance(event, FactDiscovered) for event in phase.emitted_events)
    assert sum(isinstance(event, NPCGoalCompleted) for event in phase.emitted_events) == 2

    dax = state.entities["npc_dax"]
    lio = state.entities["npc_lio"]
    assert isinstance(dax, NPC)
    assert isinstance(lio, NPC)
    assert dax.state.current_location == "yard"
    assert "dax_reach_yard" in dax.completed_goal_ids
    assert "lio_inspect_brass_key" in lio.completed_goal_ids
    assert "fact_key_mark" in lio.knowledge.facts_known
    assert "fact_key_mark" not in state.player_known_facts
    assert engine.replay_session(session.id) == state


def test_npc_phase_respects_global_action_bound(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "game.db")
    engine = GameEngine(store)
    session = engine.new_session()

    phase, state = engine.run_npc_phase(session.id, max_actions=1)

    assert phase.actions_attempted == 1
    assert phase.actions_executed == 1
    dax = state.entities["npc_dax"]
    lio = state.entities["npc_lio"]
    assert isinstance(dax, NPC)
    assert isinstance(lio, NPC)
    assert "dax_reach_yard" in dax.completed_goal_ids
    assert "lio_inspect_brass_key" not in lio.completed_goal_ids


def test_completed_goals_are_not_replanned(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "game.db")
    engine = GameEngine(store)
    session = engine.new_session()
    engine.run_npc_phase(session.id, max_actions=2)

    second, state = engine.run_npc_phase(session.id, max_actions=2)

    assert second.actions_attempted == 0
    assert second.actions_executed == 0
    assert second.emitted_events == []
    assert engine.replay_session(session.id) == state


def test_world_validation_rejects_dangling_npc_goal_target() -> None:
    state = build_demo_world()
    lio = state.entities["npc_lio"]
    assert isinstance(lio, NPC)
    lio.planning_goals.append(
        NPCGoal(
            id="bad_goal",
            kind="reach_location",
            target_id="missing_location",
            priority=100,
        )
    )

    report = validate_state(state)

    assert not report.valid
    assert any(issue.code == "invalid_npc_goal" for issue in report.issues)
