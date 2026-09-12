from __future__ import annotations

from pathlib import Path

from emergent_rpg.domain.events import NPCFactShared, RelationshipChanged
from emergent_rpg.domain.models import NPC, GameSession
from emergent_rpg.domain.npc_actions import NPCShareFactIntent
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


def _co_locate_pair(location_id: str = "operations"):
    state = build_demo_world()
    source = state.entities["npc_arden"]
    receiver = state.entities["npc_sera"]
    assert isinstance(source, NPC)
    assert isinstance(receiver, NPC)
    source.state.current_location = location_id
    receiver.state.current_location = location_id
    source.planning_goals.clear()
    receiver.planning_goals.clear()
    source.completed_goal_ids.clear()
    receiver.completed_goal_ids.clear()
    return state, source, receiver


def test_public_fact_remains_shareable_at_neutral_relationship() -> None:
    state, source, receiver = _co_locate_pair()
    source.relationships.clear()
    source.knowledge.facts_known = {"fact_schedule"}
    receiver.knowledge.facts_known.clear()

    result = DeterministicNPCResolver().resolve(
        state,
        source.id,
        NPCShareFactIntent(receiver_id=receiver.id),
        turn_number=1,
    )

    assert result.accepted
    shared = [event for event in result.emitted_events if isinstance(event, NPCFactShared)]
    assert len(shared) == 1
    assert shared[0].fact_id == "fact_schedule"
    assert validate_event_preconditions(state, shared[0]).valid


def test_restricted_fact_requires_source_directed_relationship_threshold() -> None:
    state, source, receiver = _co_locate_pair()
    restricted = state.facts["fact_relay_sabotage"]
    assert restricted.disclosure_min_relationship == 20
    source.knowledge.facts_known = {restricted.id}
    receiver.knowledge.facts_known.clear()
    source.relationships.clear()
    receiver.relationships[source.id] = 100

    result = DeterministicNPCResolver().resolve(
        state,
        source.id,
        NPCShareFactIntent(receiver_id=receiver.id),
        turn_number=1,
    )

    assert not result.accepted
    assert result.reason == "NPC relationship is below disclosure requirements."

    forged = NPCFactShared(
        turn_number=1,
        source_npc_id=source.id,
        receiver_npc_id=receiver.id,
        fact_id=restricted.id,
    )
    report = validate_event_preconditions(state, forged)
    assert not report.valid
    assert any(issue.code == "npc_disclosure_blocked" for issue in report.issues)


def test_relationship_change_unlocks_restricted_fact_in_source_direction() -> None:
    state, source, receiver = _co_locate_pair()
    source.knowledge.facts_known = {"fact_relay_sabotage"}
    receiver.knowledge.facts_known.clear()
    source.relationships.clear()

    relationship_event = RelationshipChanged(
        turn_number=1,
        source_id=source.id,
        target_id=receiver.id,
        delta=20,
    )
    changed = apply_event(state, relationship_event)
    changed_source = changed.entities[source.id]
    changed_receiver = changed.entities[receiver.id]
    assert isinstance(changed_source, NPC)
    assert isinstance(changed_receiver, NPC)
    assert changed_source.relationships[receiver.id] == 20
    assert changed_receiver.relationships.get(source.id, 0) == 0

    result = DeterministicNPCResolver().resolve(
        changed,
        source.id,
        NPCShareFactIntent(receiver_id=receiver.id),
        turn_number=2,
    )

    assert result.accepted
    shared = [event for event in result.emitted_events if isinstance(event, NPCFactShared)]
    assert len(shared) == 1
    assert shared[0].fact_id == "fact_relay_sabotage"
    assert validate_event_preconditions(changed, shared[0]).valid


def test_social_planner_ranks_visible_receivers_by_source_relationship_then_id() -> None:
    state = build_demo_world()
    source = state.entities["npc_arden"]
    lio = state.entities["npc_lio"]
    sera = state.entities["npc_sera"]
    assert isinstance(source, NPC)
    assert isinstance(lio, NPC)
    assert isinstance(sera, NPC)
    lio.state.current_location = source.state.current_location
    sera.state.current_location = source.state.current_location
    source.knowledge.facts_known = {"fact_schedule"}
    source.relationships = {lio.id: 10, sera.id: 40}
    lio.relationships[source.id] = 100

    planner = DeterministicNPCPlanner()
    context = build_npc_planning_context(state, source.id)
    intent = planner.plan_fact_share(context)

    assert intent == NPCShareFactIntent(receiver_id=sera.id)

    source.relationships = {lio.id: 40, sera.id: 40}
    tied = planner.plan_fact_share(build_npc_planning_context(state, source.id))
    assert tied == NPCShareFactIntent(receiver_id=min(lio.id, sera.id))


def test_resolver_skips_restricted_fact_when_public_new_fact_is_available() -> None:
    state, source, receiver = _co_locate_pair()
    source.relationships.clear()
    source.knowledge.facts_known = {"fact_relay_sabotage", "fact_schedule"}
    receiver.knowledge.facts_known.clear()

    result = DeterministicNPCResolver().resolve(
        state,
        source.id,
        NPCShareFactIntent(receiver_id=receiver.id),
        turn_number=1,
    )

    assert result.accepted
    shared = [event for event in result.emitted_events if isinstance(event, NPCFactShared)]
    assert len(shared) == 1
    assert shared[0].fact_id == "fact_schedule"


def test_relationship_gated_social_phase_persists_and_replays(tmp_path: Path) -> None:
    state, source, receiver = _co_locate_pair()
    source.knowledge.facts_known = {"fact_relay_sabotage"}
    receiver.knowledge.facts_known.clear()
    source.relationships = {receiver.id: 20}

    db_path = tmp_path / "social-disclosure.db"
    store = SQLiteStore(db_path)
    session = GameSession(
        id="social-disclosure",
        name="Social disclosure",
        world_pack="test-social-disclosure",
        created_at="2026-09-12T00:00:00+00:00",
    )
    store.create_session(session, state)
    engine = GameEngine(store)

    phase, after = engine.run_npc_social_phase(session.id, max_actions=1)

    shared = [event for event in phase.emitted_events if isinstance(event, NPCFactShared)]
    assert len(shared) == 1
    assert shared[0].fact_id == "fact_relay_sabotage"
    assert phase.actions_attempted == 1
    assert phase.actions_executed == 1
    after_receiver = after.entities[receiver.id]
    assert isinstance(after_receiver, NPC)
    assert "fact_relay_sabotage" in after_receiver.knowledge.facts_known
    assert engine.replay_session(session.id) == after

    restarted = GameEngine(SQLiteStore(db_path))
    assert restarted.store.load_state(session.id) == after
    assert restarted.replay_session(session.id) == after
