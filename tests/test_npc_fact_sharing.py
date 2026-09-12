from __future__ import annotations

from pathlib import Path

from emergent_rpg.domain.events import FactInferred, NPCFactShared
from emergent_rpg.domain.models import NPC, GameSession
from emergent_rpg.domain.npc_actions import NPCMoveIntent, NPCShareFactIntent
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


def _co_locate(state, source_id: str, receiver_id: str, location_id: str = "operations"):
    source = state.entities[source_id]
    receiver = state.entities[receiver_id]
    assert isinstance(source, NPC)
    assert isinstance(receiver, NPC)
    source.state.current_location = location_id
    receiver.state.current_location = location_id
    source.planning_goals.clear()
    receiver.planning_goals.clear()
    source.completed_goal_ids.clear()
    receiver.completed_goal_ids.clear()
    return source, receiver


def test_social_planner_names_receiver_but_not_fact_without_changing_goal_plan() -> None:
    state = build_demo_world()
    arden, sera = _co_locate(state, "npc_arden", "npc_sera")
    arden.knowledge.facts_known = {"fact_blackout_window"}
    sera.knowledge.facts_known.clear()

    context = build_npc_planning_context(state, arden.id)
    planner = DeterministicNPCPlanner()
    ordinary = planner.plan(context)
    social = planner.plan_fact_share(context)

    assert ordinary.intents == []
    assert social == NPCShareFactIntent(receiver_id=sera.id)
    payload = social.model_dump()
    assert "fact_id" not in payload
    assert "fact_blackout_window" in context.known_fact_ids


def test_actionable_structured_goal_remains_in_ordinary_planner() -> None:
    state = build_demo_world()
    dax = state.entities["npc_dax"]
    lio = state.entities["npc_lio"]
    assert isinstance(dax, NPC)
    assert isinstance(lio, NPC)
    lio.state.current_location = "bunkhouse"
    dax.knowledge.mapped_locations = {"bunkhouse", "yard"}

    context = build_npc_planning_context(state, dax.id)
    assert lio.id in context.visible_npc_ids
    planner = DeterministicNPCPlanner()
    plan = planner.plan(context)

    assert len(plan.intents) == 1
    assert isinstance(plan.intents[0], NPCMoveIntent)
    assert plan.intents[0].goal_id == "dax_reach_yard"
    assert plan.intents[0].destination_id == "yard"
    assert planner.plan_fact_share(context) == NPCShareFactIntent(receiver_id=lio.id)


def test_resolver_selects_lexical_new_fact_and_updates_receiver_only() -> None:
    state = build_demo_world()
    arden, sera = _co_locate(state, "npc_arden", "npc_sera")
    arden.knowledge.facts_known = {"fact_schedule", "fact_blackout_window"}
    sera.knowledge.facts_known = {"fact_blackout_window"}
    arden.knowledge.mapped_locations = {"operations"}
    sera.knowledge.mapped_locations = {"archive"}
    arden.knowledge.item_location_beliefs = {"item_maintenance_slate": "operations"}
    sera.knowledge.item_location_beliefs = {"item_archive_token": "archive"}
    player_before = set(state.player_known_facts)

    result = DeterministicNPCResolver().resolve(
        state,
        arden.id,
        NPCShareFactIntent(receiver_id=sera.id),
        turn_number=1,
    )

    assert result.accepted
    shared = [event for event in result.emitted_events if isinstance(event, NPCFactShared)]
    assert len(shared) == 1
    assert shared[0].fact_id == "fact_schedule"
    assert validate_event_preconditions(state, shared[0]).valid
    after = apply_event(state, shared[0])
    after_arden = after.entities[arden.id]
    after_sera = after.entities[sera.id]
    assert isinstance(after_arden, NPC)
    assert isinstance(after_sera, NPC)
    assert after_arden.knowledge.facts_known == arden.knowledge.facts_known
    assert after_sera.knowledge.facts_known == {"fact_blackout_window", "fact_schedule"}
    assert after_arden.knowledge.mapped_locations == {"operations"}
    assert after_sera.knowledge.mapped_locations == {"archive"}
    assert after_arden.knowledge.item_location_beliefs == {
        "item_maintenance_slate": "operations"
    }
    assert after_sera.knowledge.item_location_beliefs == {"item_archive_token": "archive"}
    assert after.player_known_facts == player_before


def test_share_event_rejects_remote_unknown_duplicate_and_inactive_participants() -> None:
    state = build_demo_world()
    arden = state.entities["npc_arden"]
    sera = state.entities["npc_sera"]
    assert isinstance(arden, NPC)
    assert isinstance(sera, NPC)

    remote = NPCFactShared(
        turn_number=1,
        source_npc_id=arden.id,
        receiver_npc_id=sera.id,
        fact_id="fact_blackout_window",
    )
    remote_report = validate_event_preconditions(state, remote)
    assert not remote_report.valid
    assert any(issue.code == "invalid_npc_fact_share" for issue in remote_report.issues)

    sera.state.current_location = arden.state.current_location
    unknown = remote.model_copy(update={"fact_id": "fact_schedule"})
    unknown_report = validate_event_preconditions(state, unknown)
    assert not unknown_report.valid
    assert any(issue.code == "npc_fact_not_known" for issue in unknown_report.issues)

    sera.knowledge.facts_known.add("fact_blackout_window")
    duplicate_report = validate_event_preconditions(state, remote)
    assert not duplicate_report.valid
    assert any(issue.code == "invalid_npc_fact_share" for issue in duplicate_report.issues)

    sera.knowledge.facts_known.clear()
    sera.state.conscious = False
    inactive_report = validate_event_preconditions(state, remote)
    assert not inactive_report.valid
    assert any(issue.code == "inactive_participant" for issue in inactive_report.issues)


def test_resolver_rejects_self_remote_and_no_new_fact_share_intents() -> None:
    state = build_demo_world()
    arden, sera = _co_locate(state, "npc_arden", "npc_sera")
    resolver = DeterministicNPCResolver()

    self_result = resolver.resolve(
        state,
        arden.id,
        NPCShareFactIntent(receiver_id=arden.id),
        turn_number=1,
    )
    assert not self_result.accepted

    sera.state.current_location = "archive"
    remote_result = resolver.resolve(
        state,
        arden.id,
        NPCShareFactIntent(receiver_id=sera.id),
        turn_number=1,
    )
    assert not remote_result.accepted

    sera.state.current_location = arden.state.current_location
    sera.knowledge.facts_known = set(arden.knowledge.facts_known)
    duplicate_result = resolver.resolve(
        state,
        arden.id,
        NPCShareFactIntent(receiver_id=sera.id),
        turn_number=1,
    )
    assert not duplicate_result.accepted
    assert duplicate_result.reason == "NPC has no new fact to share."


def test_social_phase_persists_replays_and_triggers_receiver_inference(tmp_path: Path) -> None:
    state = build_demo_world()
    arden, sera = _co_locate(state, "npc_arden", "npc_sera")
    arden.knowledge.facts_known = {"fact_schedule"}
    sera.knowledge.facts_known = {"fact_relay_sabotage"}
    before_player_facts = set(state.player_known_facts)

    db_path = tmp_path / "npc-fact-sharing.db"
    store = SQLiteStore(db_path)
    session = GameSession(
        id="npc-fact-sharing",
        name="NPC fact sharing",
        world_pack="test-fact-sharing",
        created_at="2026-09-12T00:00:00+00:00",
    )
    store.create_session(session, state)
    engine = GameEngine(store)

    phase, after = engine.run_npc_social_phase(session.id, max_actions=1)

    share_events = [event for event in phase.emitted_events if isinstance(event, NPCFactShared)]
    inference_events = [event for event in phase.emitted_events if isinstance(event, FactInferred)]
    assert len(share_events) == 1
    assert share_events[0].source_npc_id == arden.id
    assert share_events[0].receiver_npc_id == sera.id
    assert share_events[0].fact_id == "fact_schedule"
    assert any(
        event.observer_id == sera.id and event.fact_id == "fact_inside_job"
        for event in inference_events
    )
    assert phase.actions_attempted == 1
    assert phase.actions_executed == 1
    assert phase.involved_npc_ids == {arden.id, sera.id}

    after_arden = after.entities[arden.id]
    after_sera = after.entities[sera.id]
    assert isinstance(after_arden, NPC)
    assert isinstance(after_sera, NPC)
    assert after_arden.knowledge.facts_known == {"fact_schedule"}
    assert {
        "fact_relay_sabotage",
        "fact_schedule",
        "fact_inside_job",
    }.issubset(after_sera.knowledge.facts_known)
    assert after.player_known_facts == before_player_facts
    assert engine.replay_session(session.id) == after

    turns = store.list_turns(session.id)
    assert len(turns) == 1
    assert turns[0].raw_input == "[npc-social-phase]"
    assert {"npc", "autonomous", "social"}.issubset(turns[0].tags)

    restarted = GameEngine(SQLiteStore(db_path))
    assert restarted.store.load_state(session.id) == after
    assert restarted.replay_session(session.id) == after
