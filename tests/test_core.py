from __future__ import annotations

from pathlib import Path

from emergent_rpg.domain.actions import (
    InspectAction,
    MoveAction,
    TakeAction,
    TalkAction,
    WaitAction,
)
from emergent_rpg.domain.events import NPCLearnedFact
from emergent_rpg.engine.reducer import apply_event, replay
from emergent_rpg.engine.service import GameEngine
from emergent_rpg.memory.retriever import MemoryRetriever
from emergent_rpg.persistence.db import SQLiteStore
from emergent_rpg.validation.validator import validate_scene_participation, validate_state
from emergent_rpg.world.demo import build_demo_world


def make_engine(tmp_path: Path) -> tuple[GameEngine, str]:
    engine = GameEngine(SQLiteStore(tmp_path / "game.db"))
    session = engine.new_session()
    return engine, session.id


def test_persistence_round_trip(tmp_path: Path) -> None:
    engine, session_id = make_engine(tmp_path)
    _, _, expected = engine.execute_action(
        session_id, TakeAction(target="brass key"), "take brass key"
    )
    reloaded = SQLiteStore(tmp_path / "game.db").load_state(session_id)
    assert reloaded == expected


def test_event_replay_matches_projection(tmp_path: Path) -> None:
    engine, session_id = make_engine(tmp_path)
    engine.execute_action(session_id, TakeAction(target="brass key"), "take brass key")
    engine.execute_action(session_id, MoveAction(destination="operations"), "move operations")
    engine.execute_action(session_id, InspectAction(target="console"), "inspect console")
    store = engine.store
    replayed = replay(store.load_initial_state(session_id), store.load_events(session_id))
    assert replayed == store.load_state(session_id)


def test_item_conservation_validator_detects_double_location() -> None:
    state = build_demo_world()
    item = state.items["item_brass_key"]
    item.owner_id = "player"
    state.entities["player"].state.inventory.append(item.id)
    report = validate_state(state)
    assert not report.valid
    assert any(issue.code == "impossible_item_ownership" for issue in report.issues)


def test_npc_epistemic_isolation() -> None:
    state = build_demo_world()
    fact_id = "fact_blackout_window"
    report = validate_scene_participation(state, ["npc_lio"], {"npc_lio": [fact_id]})
    assert not report.valid
    assert any(issue.code == "npc_fact_not_known" for issue in report.issues)

    learned = apply_event(
        state,
        NPCLearnedFact(turn_number=1, npc_id="npc_lio", fact_id=fact_id),
    )
    report_after = validate_scene_participation(
        learned, ["npc_lio"], {"npc_lio": [fact_id]}
    )
    assert report_after.valid


def test_remote_npc_cannot_participate() -> None:
    state = build_demo_world()
    report = validate_scene_participation(state, ["npc_arden"], {})
    assert not report.valid
    assert any(issue.code == "impossible_character_location" for issue in report.issues)


def test_memory_retrieval_does_not_require_full_transcript(tmp_path: Path) -> None:
    engine, session_id = make_engine(tmp_path)
    engine.execute_action(session_id, MoveAction(destination="operations"), "move operations")
    engine.execute_action(session_id, InspectAction(target="console"), "inspect console")
    for i in range(20):
        engine.execute_action(session_id, WaitAction(minutes=1), f"wait 1 #{i}")

    state = engine.store.load_state(session_id)
    retriever = MemoryRetriever(engine.store, working_turns=5)
    context = retriever.retrieve_context(
        session_id,
        WaitAction(minutes=1),
        state.player().state.current_location,
        {state.player_id},
        limit=4,
    )
    assert len(context.working_memory) == 5
    assert any("shutdown command" in fact for fact in context.semantic_facts)
    assert len(context.episodes) <= 4


def test_mystery_item_persists_until_late_interaction(tmp_path: Path) -> None:
    engine, session_id = make_engine(tmp_path)
    for i in range(100):
        engine.execute_action(session_id, WaitAction(minutes=1), f"wait 1 #{i}")
    state = engine.store.load_state(session_id)
    assert state.items["item_charred_fuse"].location_id == "ridge"

    engine.execute_action(session_id, MoveAction(destination="ridge"), "move ridge")
    _, _, state = engine.execute_action(
        session_id, TakeAction(target="charred fuse"), "take charred fuse"
    )
    assert state.items["item_charred_fuse"].owner_id == "player"
    assert "fact_fuse_cut" in state.player_known_facts


def test_long_run_200_turn_consistency(tmp_path: Path) -> None:
    engine, session_id = make_engine(tmp_path)
    engine.execute_action(session_id, TakeAction(target="brass key"), "take brass key")
    engine.execute_action(session_id, MoveAction(destination="operations"), "move operations")
    engine.execute_action(session_id, InspectAction(target="console"), "inspect console")
    engine.execute_action(session_id, TalkAction(target="Arden Vale"), "talk Arden Vale")

    for i in range(196):
        engine.execute_action(session_id, WaitAction(minutes=1), f"wait 1 #{i}")

    state = engine.store.load_state(session_id)
    assert state.turn_number == 200
    assert validate_state(state).valid

    owner_counts: dict[str, int] = {}
    for entity in state.entities.values():
        for item_id in entity.state.inventory:
            owner_counts[item_id] = owner_counts.get(item_id, 0) + 1
    assert all(count == 1 for count in owner_counts.values())

    initial = engine.store.load_initial_state(session_id)
    events = engine.store.load_events(session_id)
    cursor = initial
    last_time = cursor.clock.absolute_minutes
    for event in events:
        cursor = apply_event(cursor, event)
        assert cursor.clock.absolute_minutes >= last_time
        last_time = cursor.clock.absolute_minutes
    assert cursor == state
    assert engine.replay_session(session_id) == state
