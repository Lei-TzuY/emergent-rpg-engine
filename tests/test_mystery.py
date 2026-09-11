from __future__ import annotations

from pathlib import Path

from emergent_rpg.domain.events import FactDiscovered, FactInferred
from emergent_rpg.domain.models import FactInferenceRule
from emergent_rpg.engine.mystery import MysteryGraph
from emergent_rpg.engine.service import GameEngine
from emergent_rpg.persistence.db import SQLiteStore
from emergent_rpg.validation.validator import validate_event_preconditions, validate_state
from emergent_rpg.world.demo import build_demo_world


def _engine(tmp_path: Path) -> tuple[GameEngine, str]:
    engine = GameEngine(SQLiteStore(tmp_path / "game.db"))
    session = engine.new_session()
    return engine, session.id


def test_inference_rule_emits_provenance_event_and_replays(tmp_path: Path) -> None:
    engine, session_id = _engine(tmp_path)
    engine.process_text(session_id, "move operations")
    engine.process_text(session_id, "inspect console")

    result, _, state = engine.process_text(session_id, "take maintenance slate")

    inferred = [event for event in result.emitted_events if isinstance(event, FactInferred)]
    assert len(inferred) == 1
    event = inferred[0]
    assert event.fact_id == "fact_inside_job"
    assert event.rule_id == "infer_inside_job"
    assert set(event.premise_fact_ids) == {"fact_relay_sabotage", "fact_schedule"}
    assert "fact_inside_job" in state.player_known_facts
    assert engine.replay_session(session_id) == state


def test_chained_inference_reaches_fixpoint_after_later_clue(tmp_path: Path) -> None:
    engine, session_id = _engine(tmp_path)
    engine.process_text(session_id, "move operations")
    engine.process_text(session_id, "inspect console")
    engine.process_text(session_id, "take maintenance slate")
    engine.process_text(session_id, "move yard")
    engine.process_text(session_id, "move ridge")

    result, _, state = engine.process_text(session_id, "take charred fuse")

    inferred = [event for event in result.emitted_events if isinstance(event, FactInferred)]
    assert [event.fact_id for event in inferred] == ["fact_coordinated_sabotage"]
    assert "fact_coordinated_sabotage" in state.player_known_facts
    assert engine.replay_session(session_id) == state


def test_discovery_gate_blocks_and_then_unlocks_archive_clue(tmp_path: Path) -> None:
    engine, session_id = _engine(tmp_path)
    engine.process_text(session_id, "move operations")
    engine.process_text(session_id, "move archive")

    blocked, _, state = engine.process_text(session_id, "inspect locker")
    assert not blocked.accepted
    assert "fact_c7_checkout" not in state.player_known_facts

    # Start a clean path that satisfies both canonical prerequisites.
    engine2 = GameEngine(SQLiteStore(tmp_path / "unlocked.db"))
    session2 = engine2.new_session()
    engine2.process_text(session2.id, "take brass key")
    engine2.process_text(session2.id, "move operations")
    engine2.process_text(session2.id, "inspect console")
    engine2.process_text(session2.id, "take maintenance slate")
    engine2.process_text(session2.id, "move archive")

    unlocked, _, unlocked_state = engine2.process_text(session2.id, "inspect locker")
    assert unlocked.accepted
    assert "fact_inside_job" in unlocked_state.player_known_facts
    assert "fact_c7_checkout" in unlocked_state.player_known_facts


def test_contradiction_tracking_is_observer_scoped(tmp_path: Path) -> None:
    engine, session_id = _engine(tmp_path)
    engine.process_text(session_id, "talk Lio Marr")
    engine.process_text(session_id, "move bunkhouse")
    _, _, state = engine.process_text(session_id, "talk Dax Fen")

    assert MysteryGraph.contradictions(state, state.player_id) == [
        ("fact_dax_generator_claim", "fact_generator_stable")
    ]
    assert MysteryGraph.contradictions(state, "npc_lio") == []
    assert MysteryGraph.contradictions(state, "npc_dax") == []


def test_forged_inference_without_known_premises_is_rejected() -> None:
    state = build_demo_world()
    event = FactInferred(
        turn_number=1,
        fact_id="fact_inside_job",
        observer_id=state.player_id,
        rule_id="infer_inside_job",
        premise_fact_ids=("fact_relay_sabotage", "fact_schedule"),
    )

    report = validate_event_preconditions(state, event)

    assert not report.valid
    assert any(issue.code == "invalid_inference" for issue in report.issues)


def test_state_validation_rejects_dangling_mystery_rule() -> None:
    state = build_demo_world()
    state.inference_rules["bad"] = FactInferenceRule(
        id="bad",
        premises={"fact_missing"},
        conclusion="fact_inside_job",
    )

    report = validate_state(state)

    assert not report.valid
    assert any(issue.code == "invalid_mystery_graph" for issue in report.issues)


def test_forged_gated_discovery_without_prerequisites_is_rejected() -> None:
    state = build_demo_world()
    event = FactDiscovered(
        turn_number=1,
        fact_id="fact_c7_checkout",
        observer_id=state.player_id,
    )

    report = validate_event_preconditions(state, event)

    assert not report.valid
    assert any(issue.code == "invalid_discovery" for issue in report.issues)


def test_derived_fact_cannot_bypass_inference_provenance() -> None:
    state = build_demo_world()
    state.player_known_facts.update({"fact_relay_sabotage", "fact_schedule"})
    event = FactDiscovered(
        turn_number=1,
        fact_id="fact_inside_job",
        observer_id=state.player_id,
    )

    report = validate_event_preconditions(state, event)

    assert not report.valid
    assert any(issue.code == "invalid_discovery" for issue in report.issues)


def test_state_validation_rejects_rule_with_non_inferred_conclusion() -> None:
    state = build_demo_world()
    state.inference_rules["bad_kind"] = FactInferenceRule(
        id="bad_kind",
        premises={"fact_relay_sabotage"},
        conclusion="fact_schedule",
    )

    report = validate_state(state)

    assert not report.valid
    assert any(issue.code == "invalid_mystery_graph" for issue in report.issues)
