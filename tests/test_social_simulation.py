from __future__ import annotations

from pathlib import Path

import pytest

from emergent_rpg.domain.actions import WaitAction
from emergent_rpg.domain.events import NPCFactShared, NPCMoved, SimulationCycleProcessed
from emergent_rpg.domain.models import NPC, GameSession
from emergent_rpg.engine.narrative import ScenePlan
from emergent_rpg.engine.service import GameEngine
from emergent_rpg.persistence.db import SQLiteStore
from emergent_rpg.providers.base import NarrativeGenerator
from emergent_rpg.providers.errors import ProviderRequestError
from emergent_rpg.world.demo import build_demo_world


class FailingNarrativeGenerator(NarrativeGenerator):
    def generate(self, scene_plan: ScenePlan) -> str:
        del scene_plan
        raise ProviderRequestError("simulated outage before social simulation")


def _persist_engine(
    tmp_path: Path,
    state,
    *,
    generator: NarrativeGenerator | None = None,
) -> tuple[GameEngine, str]:
    store = SQLiteStore(tmp_path / "social-simulation.db")
    session = GameSession(
        id="social-simulation",
        name="Social simulation",
        world_pack="test-social-simulation",
        created_at="2026-09-12T00:00:00+00:00",
    )
    store.create_session(session, state)
    return GameEngine(store, generator=generator), session.id


def _prepare_offscreen_pair(state) -> tuple[NPC, NPC]:
    for entity in state.entities.values():
        if isinstance(entity, NPC):
            entity.planning_goals.clear()
            entity.completed_goal_ids.clear()
            entity.state.current_location = "yard"
    arden = state.entities["npc_arden"]
    sera = state.entities["npc_sera"]
    assert isinstance(arden, NPC)
    assert isinstance(sera, NPC)
    arden.state.current_location = "operations"
    sera.state.current_location = "operations"
    arden.knowledge.facts_known = {"fact_blackout_window"}
    sera.knowledge.facts_known.clear()
    state.simulation.max_social_actions_per_cycle = 1
    return arden, sera


def test_due_cycle_automatically_runs_bounded_offscreen_social_phase(tmp_path: Path) -> None:
    state = build_demo_world()
    arden, sera = _prepare_offscreen_pair(state)
    engine, session_id = _persist_engine(tmp_path, state)

    _, _, after = engine.execute_action(session_id, WaitAction(minutes=5), "wait 5")

    persisted_sera = after.entities[sera.id]
    assert isinstance(persisted_sera, NPC)
    assert "fact_blackout_window" in persisted_sera.knowledge.facts_known

    events = engine.store.load_events(session_id)
    shares = [event for event in events if isinstance(event, NPCFactShared)]
    markers = [event for event in events if isinstance(event, SimulationCycleProcessed)]
    assert len(shares) == state.simulation.max_social_actions_per_cycle == 1
    assert shares[0].source_npc_id == arden.id
    assert shares[0].receiver_npc_id == sera.id
    assert len(markers) == 1
    assert events.index(shares[0]) < events.index(markers[0])
    assert engine.replay_session(session_id) == after


def test_automatic_social_phase_skips_npcs_at_player_location(tmp_path: Path) -> None:
    state = build_demo_world()
    arden, sera = _prepare_offscreen_pair(state)
    arden.state.current_location = state.player().state.current_location
    sera.state.current_location = state.player().state.current_location
    engine, session_id = _persist_engine(tmp_path, state)

    _, _, after = engine.execute_action(session_id, WaitAction(minutes=5), "wait 5")

    events = engine.store.load_events(session_id)
    assert not any(isinstance(event, NPCFactShared) for event in events)
    assert sum(isinstance(event, SimulationCycleProcessed) for event in events) == 1
    persisted_sera = after.entities[sera.id]
    assert isinstance(persisted_sera, NPC)
    assert "fact_blackout_window" not in persisted_sera.knowledge.facts_known
    assert engine.replay_session(session_id) == after


def test_goal_and_social_budgets_are_independent_in_same_cycle(tmp_path: Path) -> None:
    state = build_demo_world()
    player = state.player()
    player.state.current_location = "operations"

    arden = state.entities["npc_arden"]
    sera = state.entities["npc_sera"]
    lio = state.entities["npc_lio"]
    dax = state.entities["npc_dax"]
    assert isinstance(arden, NPC)
    assert isinstance(sera, NPC)
    assert isinstance(lio, NPC)
    assert isinstance(dax, NPC)

    arden.state.current_location = "archive"
    sera.state.current_location = "archive"
    arden.knowledge.facts_known = {"fact_blackout_window"}
    sera.knowledge.facts_known.clear()
    lio.state.current_location = "operations"
    lio.planning_goals.clear()
    state.simulation.max_npc_actions_per_cycle = 1
    state.simulation.max_social_actions_per_cycle = 1

    engine, session_id = _persist_engine(tmp_path, state)
    _, _, after = engine.execute_action(session_id, WaitAction(minutes=5), "wait 5")

    events = engine.store.load_events(session_id)
    moves = [event for event in events if isinstance(event, NPCMoved)]
    shares = [event for event in events if isinstance(event, NPCFactShared)]
    markers = [event for event in events if isinstance(event, SimulationCycleProcessed)]
    assert len(moves) == state.simulation.max_npc_actions_per_cycle == 1
    assert moves[0].npc_id == dax.id
    assert len(shares) == state.simulation.max_social_actions_per_cycle == 1
    assert shares[0].source_npc_id == arden.id
    assert shares[0].receiver_npc_id == sera.id
    assert len(markers) == 1
    assert events.index(moves[0]) < events.index(shares[0]) < events.index(markers[0])

    turns = engine.store.list_turns(session_id)
    episodes = engine.store.list_episodes(session_id)
    assert len(turns) == 1
    assert turns[0].involved_entities == {"player"}
    assert len(episodes) == 1
    assert episodes[0].involved_entities == {"player"}
    assert engine.replay_session(session_id) == after


def test_provider_failure_prevents_automatic_social_diffusion_commit(tmp_path: Path) -> None:
    state = build_demo_world()
    _prepare_offscreen_pair(state)
    engine, session_id = _persist_engine(
        tmp_path,
        state,
        generator=FailingNarrativeGenerator(),
    )
    before = engine.store.load_state(session_id)

    with pytest.raises(ProviderRequestError, match="before social simulation"):
        engine.execute_action(session_id, WaitAction(minutes=5), "wait 5")

    assert engine.store.load_state(session_id) == before
    assert engine.store.load_events(session_id) == []
    assert engine.store.list_turns(session_id) == []
