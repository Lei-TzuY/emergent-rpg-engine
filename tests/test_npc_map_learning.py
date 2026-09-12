from __future__ import annotations

from pathlib import Path

import pytest

from emergent_rpg.domain.actions import WaitAction
from emergent_rpg.domain.events import (
    NPCGoalCompleted,
    NPCLocationMapped,
    NPCMoved,
)
from emergent_rpg.domain.models import NPC
from emergent_rpg.domain.npc_actions import NPCInspectIntent, NPCMoveIntent
from emergent_rpg.engine.narrative import ScenePlan
from emergent_rpg.engine.npc import DeterministicNPCResolver
from emergent_rpg.engine.reducer import apply_event
from emergent_rpg.engine.service import GameEngine
from emergent_rpg.persistence.db import SQLiteStore
from emergent_rpg.providers.errors import ProviderRequestError
from emergent_rpg.validation.validator import validate_event_preconditions, validate_state
from emergent_rpg.world.demo import build_demo_world


def _apply_events(state, events):
    candidate = state
    for event in events:
        report = validate_event_preconditions(candidate, event)
        assert report.valid, report.issues
        candidate = apply_event(candidate, event)
    return candidate


class FailingNarrativeGenerator:
    def generate(self, scene_plan: ScenePlan) -> str:
        del scene_plan
        raise ProviderRequestError("narration unavailable")


def test_mapping_event_requires_physical_presence_and_fresh_location() -> None:
    state = build_demo_world()
    remote = NPCLocationMapped(
        turn_number=1,
        npc_id="npc_dax",
        location_id="archive",
    )

    remote_report = validate_event_preconditions(state, remote)

    assert not remote_report.valid
    assert any(issue.code == "invalid_npc_map" for issue in remote_report.issues)

    local = NPCLocationMapped(
        turn_number=1,
        npc_id="npc_dax",
        location_id="bunkhouse",
    )
    assert validate_event_preconditions(state, local).valid
    mapped = apply_event(state, local)

    duplicate_report = validate_event_preconditions(mapped, local.model_copy())
    assert not duplicate_report.valid
    assert any(issue.code == "invalid_npc_map" for issue in duplicate_report.issues)


def test_state_validation_requires_mapping_provenance_and_monotonicity() -> None:
    before = build_demo_world()
    after = before.model_copy(deep=True)
    dax = after.entities["npc_dax"]
    assert isinstance(dax, NPC)
    dax.knowledge.mapped_locations.add("bunkhouse")

    unauthorized = validate_state(after, previous=before)

    assert not unauthorized.valid
    assert any(
        issue.code == "npc_map_changed_without_observation"
        for issue in unauthorized.issues
    )

    mapping = NPCLocationMapped(
        turn_number=1,
        npc_id="npc_dax",
        location_id="bunkhouse",
    )
    authorized = validate_state(after, previous=before, transition_events=[mapping])
    assert authorized.valid

    forgotten = after.model_copy(deep=True)
    forgotten_dax = forgotten.entities["npc_dax"]
    assert isinstance(forgotten_dax, NPC)
    forgotten_dax.knowledge.mapped_locations.clear()
    regression = validate_state(forgotten, previous=after)

    assert not regression.valid
    assert any(issue.code == "npc_map_went_backward" for issue in regression.issues)


def test_world_validation_rejects_missing_mapped_location() -> None:
    state = build_demo_world()
    dax = state.entities["npc_dax"]
    assert isinstance(dax, NPC)
    dax.knowledge.mapped_locations.add("missing_location")

    report = validate_state(state)

    assert not report.valid
    assert any(issue.code == "invalid_npc_map" for issue in report.issues)


def test_move_maps_current_and_arrival_locations_before_goal_completion() -> None:
    state = build_demo_world()
    intent = NPCMoveIntent(goal_id="dax_reach_yard", destination_id="yard")

    result = DeterministicNPCResolver().resolve(
        state,
        "npc_dax",
        intent,
        turn_number=1,
    )

    assert result.accepted
    assert [type(event) for event in result.emitted_events] == [
        NPCLocationMapped,
        NPCMoved,
        NPCLocationMapped,
        NPCGoalCompleted,
    ]

    candidate = _apply_events(state, result.emitted_events)
    dax = candidate.entities["npc_dax"]
    assert isinstance(dax, NPC)
    assert dax.knowledge.mapped_locations == {"bunkhouse", "yard"}
    assert "dax_reach_yard" in dax.completed_goal_ids


def test_already_known_locations_do_not_emit_duplicate_mapping_events() -> None:
    state = build_demo_world()
    dax = state.entities["npc_dax"]
    assert isinstance(dax, NPC)
    dax.knowledge.mapped_locations = {"bunkhouse", "yard"}
    intent = NPCMoveIntent(goal_id="dax_reach_yard", destination_id="yard")

    result = DeterministicNPCResolver().resolve(
        state,
        dax.id,
        intent,
        turn_number=1,
    )

    assert result.accepted
    assert all(not isinstance(event, NPCLocationMapped) for event in result.emitted_events)
    assert sum(isinstance(event, NPCMoved) for event in result.emitted_events) == 1


def test_inspection_maps_only_acting_npc_current_location() -> None:
    state = build_demo_world()
    intent = NPCInspectIntent(
        goal_id="lio_inspect_brass_key",
        item_id="item_brass_key",
    )

    result = DeterministicNPCResolver().resolve(
        state,
        "npc_lio",
        intent,
        turn_number=1,
    )
    assert result.accepted
    candidate = _apply_events(state, result.emitted_events)

    lio = candidate.entities["npc_lio"]
    dax = candidate.entities["npc_dax"]
    assert isinstance(lio, NPC)
    assert isinstance(dax, NPC)
    assert lio.knowledge.mapped_locations == {"yard"}
    assert dax.knowledge.mapped_locations == set()


def test_npc_phase_persists_map_learning_across_restart_and_replay(tmp_path: Path) -> None:
    db_path = tmp_path / "npc-map.db"
    engine = GameEngine(SQLiteStore(db_path))
    session = engine.new_session()

    phase, state = engine.run_npc_phase(session.id, max_actions=2)

    mapping_events = [
        event for event in phase.emitted_events if isinstance(event, NPCLocationMapped)
    ]
    assert {(event.npc_id, event.location_id) for event in mapping_events} == {
        ("npc_dax", "bunkhouse"),
        ("npc_dax", "yard"),
        ("npc_lio", "yard"),
    }
    assert engine.replay_session(session.id) == state

    restarted = GameEngine(SQLiteStore(db_path))
    reloaded = restarted.store.load_state(session.id)
    assert reloaded == state
    assert restarted.replay_session(session.id) == state


def test_offscreen_simulation_maps_acting_npc_without_player_knowledge_leak(
    tmp_path: Path,
) -> None:
    engine = GameEngine(SQLiteStore(tmp_path / "offscreen-map.db"))
    session = engine.new_session()
    before = engine.store.load_state(session.id)
    assert before.player_known_facts == set()

    _, _, after = engine.execute_action(
        session.id,
        WaitAction(minutes=5),
        "wait 5",
    )

    dax = after.entities["npc_dax"]
    lio = after.entities["npc_lio"]
    assert isinstance(dax, NPC)
    assert isinstance(lio, NPC)
    assert dax.knowledge.mapped_locations == {"bunkhouse", "yard"}
    assert lio.knowledge.mapped_locations == set()
    assert after.player_known_facts == set()
    map_events = [
        event
        for event in engine.store.load_events(session.id)
        if isinstance(event, NPCLocationMapped)
    ]
    assert {(event.npc_id, event.location_id) for event in map_events} == {
        ("npc_dax", "bunkhouse"),
        ("npc_dax", "yard"),
    }
    assert engine.replay_session(session.id) == after


def test_provider_failure_before_simulation_does_not_commit_map_learning(
    tmp_path: Path,
) -> None:
    store = SQLiteStore(tmp_path / "failed-map.db")
    engine = GameEngine(store, generator=FailingNarrativeGenerator())
    session = engine.new_session()
    before = store.load_state(session.id)
    events_before = store.load_events(session.id)

    with pytest.raises(ProviderRequestError):
        engine.execute_action(session.id, WaitAction(minutes=5), "wait 5")

    assert store.load_state(session.id) == before
    assert store.load_events(session.id) == events_before
    assert all(
        not isinstance(event, NPCLocationMapped)
        for event in store.load_events(session.id)
    )
