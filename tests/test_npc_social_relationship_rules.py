from __future__ import annotations

from pathlib import Path

import pytest

from emergent_rpg.domain.actions import WaitAction
from emergent_rpg.domain.events import (
    NPCFactShared,
    RelationshipChanged,
    SimulationCycleProcessed,
)
from emergent_rpg.domain.models import NPC, DialogueRelationshipRule, GameSession, WorldState
from emergent_rpg.domain.npc_actions import NPCShareFactIntent
from emergent_rpg.engine.npc import DeterministicNPCResolver
from emergent_rpg.engine.reducer import ReductionError, apply_event
from emergent_rpg.engine.service import GameEngine
from emergent_rpg.persistence.db import SQLiteStore
from emergent_rpg.world.demo import build_demo_world

RULE_ID = "arden_respects_sera_after_blackout_share"


def _relationship_state() -> tuple[WorldState, NPC, NPC]:
    state = build_demo_world()
    arden = state.entities["npc_arden"]
    sera = state.entities["npc_sera"]
    assert isinstance(arden, NPC)
    assert isinstance(sera, NPC)

    arden.state.current_location = "operations"
    sera.state.current_location = "operations"
    arden.planning_goals.clear()
    sera.planning_goals.clear()
    arden.completed_goal_ids.clear()
    sera.completed_goal_ids.clear()
    arden.knowledge.facts_known = {"fact_blackout_window", "fact_schedule"}
    sera.knowledge.facts_known.clear()
    arden.relationships.pop(sera.id, None)
    sera.relationships.pop(arden.id, None)
    state.dialogue_relationship_rules = [
        DialogueRelationshipRule(
            id=RULE_ID,
            speaker_id=arden.id,
            listener_id=sera.id,
            required_listener_fact_ids={"fact_blackout_window"},
            delta=7,
            priority=10,
            once=True,
        )
    ]
    state.applied_dialogue_relationship_rule_ids.clear()
    return state, arden, sera


def _persist_engine(tmp_path: Path, state: WorldState, session_id: str) -> GameEngine:
    store = SQLiteStore(tmp_path / f"{session_id}.db")
    session = GameSession(
        id=session_id,
        name="NPC social relationship rules",
        world_pack="test-social-relationship-rules",
        created_at="2026-09-12T00:00:00+00:00",
    )
    store.create_session(session, state)
    return GameEngine(store)


def test_share_precedes_relationship_rule_and_reducer_revalidates_provenance() -> None:
    state, arden, sera = _relationship_state()
    result = DeterministicNPCResolver().resolve(
        state,
        arden.id,
        NPCShareFactIntent(receiver_id=sera.id),
        turn_number=1,
    )

    assert result.accepted
    share = next(event for event in result.emitted_events if isinstance(event, NPCFactShared))
    relationship = next(
        event for event in result.emitted_events if isinstance(event, RelationshipChanged)
    )
    assert result.emitted_events.index(share) < result.emitted_events.index(relationship)
    assert share.fact_id == "fact_blackout_window"
    assert relationship.rule_id == RULE_ID
    assert relationship.source_id == arden.id
    assert relationship.target_id == sera.id
    assert relationship.delta == 7

    with pytest.raises(ReductionError, match="no dialogue relationship rule is eligible"):
        apply_event(state, relationship)

    after_share = apply_event(state, share)
    after = apply_event(after_share, relationship)
    after_arden = after.entities[arden.id]
    after_sera = after.entities[sera.id]
    assert isinstance(after_arden, NPC)
    assert isinstance(after_sera, NPC)
    assert "fact_blackout_window" in after_sera.knowledge.facts_known
    assert after_arden.relationships[sera.id] == 7
    assert after_sera.relationships.get(arden.id, 0) == 0
    assert after.applied_dialogue_relationship_rule_ids == {RULE_ID}


def test_explicit_social_phase_is_one_action_one_shot_and_replayable(tmp_path: Path) -> None:
    state, arden, sera = _relationship_state()
    engine = _persist_engine(tmp_path, state, "explicit-social-relationship")

    first_phase, first = engine.run_npc_social_phase(
        "explicit-social-relationship",
        max_actions=1,
    )

    first_shares = [
        event for event in first_phase.emitted_events if isinstance(event, NPCFactShared)
    ]
    first_relationships = [
        event for event in first_phase.emitted_events if isinstance(event, RelationshipChanged)
    ]
    assert first_phase.actions_attempted == 1
    assert first_phase.actions_executed == 1
    assert len(first_shares) == 1
    assert len(first_relationships) == 1
    assert first_phase.emitted_events.index(first_shares[0]) < first_phase.emitted_events.index(
        first_relationships[0]
    )
    first_arden = first.entities[arden.id]
    assert isinstance(first_arden, NPC)
    assert first_arden.relationships[sera.id] == 7
    assert first.applied_dialogue_relationship_rule_ids == {RULE_ID}
    assert engine.replay_session("explicit-social-relationship") == first

    second_phase, second = engine.run_npc_social_phase(
        "explicit-social-relationship",
        max_actions=1,
    )
    second_shares = [
        event for event in second_phase.emitted_events if isinstance(event, NPCFactShared)
    ]
    second_relationships = [
        event for event in second_phase.emitted_events if isinstance(event, RelationshipChanged)
    ]
    assert second_phase.actions_attempted == 1
    assert second_phase.actions_executed == 1
    assert len(second_shares) == 1
    assert second_shares[0].fact_id == "fact_schedule"
    assert second_relationships == []
    second_arden = second.entities[arden.id]
    assert isinstance(second_arden, NPC)
    assert second_arden.relationships[sera.id] == 7
    assert second.applied_dialogue_relationship_rule_ids == {RULE_ID}
    assert engine.replay_session("explicit-social-relationship") == second

    restarted = GameEngine(SQLiteStore(tmp_path / "explicit-social-relationship.db"))
    assert restarted.store.load_state("explicit-social-relationship") == second
    assert restarted.replay_session("explicit-social-relationship") == second


def test_automatic_offscreen_social_phase_applies_same_relationship_rule(tmp_path: Path) -> None:
    state, arden, sera = _relationship_state()
    state.player().state.current_location = "yard"
    state.simulation.max_social_actions_per_cycle = 1
    engine = _persist_engine(tmp_path, state, "automatic-social-relationship")

    _, _, after = engine.execute_action(
        "automatic-social-relationship",
        WaitAction(minutes=5),
        "wait 5",
    )

    events = engine.store.load_events("automatic-social-relationship")
    share = next(event for event in events if isinstance(event, NPCFactShared))
    relationship = next(event for event in events if isinstance(event, RelationshipChanged))
    marker = next(event for event in events if isinstance(event, SimulationCycleProcessed))
    assert share.source_npc_id == arden.id
    assert share.receiver_npc_id == sera.id
    assert relationship.rule_id == RULE_ID
    assert events.index(share) < events.index(relationship) < events.index(marker)

    after_arden = after.entities[arden.id]
    after_sera = after.entities[sera.id]
    assert isinstance(after_arden, NPC)
    assert isinstance(after_sera, NPC)
    assert after_arden.relationships[sera.id] == 7
    assert after_sera.relationships.get(arden.id, 0) == 0
    assert after.applied_dialogue_relationship_rule_ids == {RULE_ID}
    assert engine.replay_session("automatic-social-relationship") == after
