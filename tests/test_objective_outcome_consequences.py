from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from emergent_rpg.domain.events import (
    FactDiscovered,
    PlayerObjectiveCompleted,
    PlayerObjectiveFailed,
    RelationshipChanged,
)
from emergent_rpg.domain.models import (
    GameSession,
    NPC,
    ObjectiveOutcomeConsequenceRule,
    PlayerObjective,
    WorldState,
)
from emergent_rpg.engine.narrative import ScenePlan
from emergent_rpg.engine.reducer import ReductionError, apply_event
from emergent_rpg.engine.service import GameEngine
from emergent_rpg.persistence.db import SQLiteStore
from emergent_rpg.providers.base import NarrativeGenerator
from emergent_rpg.providers.errors import ProviderRequestError
from emergent_rpg.world.demo import build_demo_world


class FailingNarrativeGenerator(NarrativeGenerator):
    def generate(self, scene_plan: ScenePlan) -> str:
        del scene_plan
        raise ProviderRequestError("simulated objective outcome outage")


def _objective(
    objective_id: str,
    *,
    completion_fact: str,
    activation_facts: set[str] | None = None,
    deadline_absolute_minute: int | None = None,
) -> PlayerObjective:
    return PlayerObjective(
        id=objective_id,
        title=objective_id.replace("_", " ").title(),
        description=f"Objective {objective_id}.",
        deadline_absolute_minute=deadline_absolute_minute,
        activation_required_fact_ids=activation_facts or set(),
        completion_required_fact_ids={completion_fact},
    )


def _rule(
    rule_id: str,
    objective_id: str,
    *,
    outcome: str = "completed",
    delta: int = 5,
    reward_fact_id: str | None = None,
    priority: int = 0,
) -> ObjectiveOutcomeConsequenceRule:
    return ObjectiveOutcomeConsequenceRule(
        id=rule_id,
        objective_id=objective_id,
        outcome=outcome,
        source_npc_id="npc_lio",
        relationship_delta=delta,
        reward_fact_id=reward_fact_id,
        priority=priority,
    )


def _create_session(store: SQLiteStore, state: WorldState) -> GameSession:
    session = GameSession(
        id="objective-outcome-session",
        name="Objective outcome test",
        world_pack="objective-outcome-test",
        created_at="2026-09-22T00:00:00+00:00",
    )
    store.create_session(session, state)
    return session


def _lio(state: WorldState) -> NPC:
    entity = state.entities["npc_lio"]
    assert isinstance(entity, NPC)
    return entity


def test_completion_outcome_applies_fact_relationship_and_replays(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "completion-outcome.db")
    state = build_demo_world()
    state.player_objectives = [
        _objective("case_closed", completion_fact="fact_key_mark")
    ]
    state.active_player_objective_ids = {"case_closed"}
    state.player_known_facts.add("fact_key_mark")
    state.objective_outcome_consequence_rules = [
        _rule(
            "case_reward",
            "case_closed",
            delta=7,
            reward_fact_id="fact_generator_stable",
        )
    ]
    session = _create_session(store, state)
    engine = GameEngine(store)

    result, _, final_state = engine.process_text(session.id, "wait 1")

    relevant = [
        event
        for event in result.emitted_events
        if isinstance(
            event,
            (PlayerObjectiveCompleted, FactDiscovered, RelationshipChanged),
        )
    ]
    assert [event.type for event in relevant] == [
        "player_objective_completed",
        "fact_discovered",
        "relationship_changed",
    ]
    assert final_state.completed_player_objective_ids == {"case_closed"}
    assert "fact_generator_stable" in final_state.player_known_facts
    assert _lio(final_state).relationships[final_state.player_id] == 7
    assert final_state.applied_objective_outcome_consequence_rule_ids == {
        "case_reward"
    }
    assert engine.replay_session(session.id) == final_state


def test_failed_outcome_applies_relationship_after_deadline(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "failed-outcome.db")
    state = build_demo_world()
    state.player_objectives = [
        _objective(
            "missed_window",
            completion_fact="fact_inside_job",
            deadline_absolute_minute=state.clock.absolute_minutes + 1,
        )
    ]
    state.active_player_objective_ids = {"missed_window"}
    state.objective_outcome_consequence_rules = [
        _rule(
            "failure_consequence",
            "missed_window",
            outcome="failed",
            delta=-4,
        )
    ]
    session = _create_session(store, state)
    engine = GameEngine(store)

    result, _, final_state = engine.process_text(session.id, "wait 1")

    assert any(isinstance(event, PlayerObjectiveFailed) for event in result.emitted_events)
    assert final_state.failed_player_objective_ids == {"missed_window"}
    assert _lio(final_state).relationships[final_state.player_id] == -4
    assert final_state.applied_objective_outcome_consequence_rule_ids == {
        "failure_consequence"
    }
    assert engine.replay_session(session.id) == final_state


def test_highest_priority_outcome_rule_wins_and_consumes_outcome(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "priority-outcome.db")
    state = build_demo_world()
    state.player_objectives = [
        _objective("priority_case", completion_fact="fact_key_mark")
    ]
    state.active_player_objective_ids = {"priority_case"}
    state.player_known_facts.add("fact_key_mark")
    state.objective_outcome_consequence_rules = [
        _rule("low_rule", "priority_case", delta=2, priority=1),
        _rule("high_rule", "priority_case", delta=9, priority=10),
    ]
    session = _create_session(store, state)
    engine = GameEngine(store)

    _, _, final_state = engine.process_text(session.id, "wait 1")

    assert _lio(final_state).relationships[final_state.player_id] == 9
    assert final_state.applied_objective_outcome_consequence_rule_ids == {
        "high_rule"
    }

    forged_lower_priority = RelationshipChanged(
        turn_number=final_state.turn_number,
        source_id="npc_lio",
        target_id=final_state.player_id,
        delta=2,
        rule_id="low_rule",
    )
    with pytest.raises(
        ReductionError,
        match="no objective outcome consequence rule is eligible",
    ):
        apply_event(final_state, forged_lower_priority)


def test_forged_outcome_relationship_before_terminal_state_is_rejected() -> None:
    state = build_demo_world()
    state.player_objectives = [
        _objective("still_open", completion_fact="fact_key_mark")
    ]
    state.active_player_objective_ids = {"still_open"}
    state.objective_outcome_consequence_rules = [
        _rule("premature_reward", "still_open", delta=6)
    ]
    forged = RelationshipChanged(
        turn_number=1,
        source_id="npc_lio",
        target_id=state.player_id,
        delta=6,
        rule_id="premature_reward",
    )

    with pytest.raises(ReductionError, match="not canonically completed"):
        apply_event(state, forged)


def test_reward_fact_reconverges_downstream_objective_in_same_turn(
    tmp_path: Path,
) -> None:
    store = SQLiteStore(tmp_path / "reconverge-outcome.db")
    state = build_demo_world()
    state.player_objectives = [
        _objective("objective_a", completion_fact="fact_key_mark"),
        _objective(
            "objective_b",
            activation_facts={"fact_generator_stable"},
            completion_fact="fact_generator_stable",
        ),
    ]
    state.active_player_objective_ids = {"objective_a"}
    state.player_known_facts.add("fact_key_mark")
    state.objective_outcome_consequence_rules = [
        _rule(
            "unlock_b",
            "objective_a",
            reward_fact_id="fact_generator_stable",
        )
    ]
    session = _create_session(store, state)
    engine = GameEngine(store)

    result, _, final_state = engine.process_text(session.id, "wait 1")

    lifecycle = [
        (event.type, getattr(event, "objective_id", None))
        for event in result.emitted_events
        if event.type.startswith("player_objective_")
    ]
    assert lifecycle == [
        ("player_objective_completed", "objective_a"),
        ("player_objective_activated", "objective_b"),
        ("player_objective_completed", "objective_b"),
    ]
    assert final_state.completed_player_objective_ids == {
        "objective_a",
        "objective_b",
    }
    assert final_state.turn_number == 1
    assert engine.replay_session(session.id) == final_state


def test_provider_failure_keeps_outcome_consequences_zero_commit(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "provider-outcome.db")
    state = build_demo_world()
    state.player_objectives = [
        _objective("atomic_case", completion_fact="fact_key_mark")
    ]
    state.active_player_objective_ids = {"atomic_case"}
    state.player_known_facts.add("fact_key_mark")
    state.objective_outcome_consequence_rules = [
        _rule(
            "atomic_reward",
            "atomic_case",
            delta=8,
            reward_fact_id="fact_generator_stable",
        )
    ]
    session = _create_session(store, state)
    before = store.load_state(session.id)
    engine = GameEngine(store, generator=FailingNarrativeGenerator())

    with pytest.raises(ProviderRequestError, match="objective outcome outage"):
        engine.process_text(session.id, "wait 1")

    assert store.load_state(session.id) == before
    assert store.load_events(session.id) == []
    assert store.list_turns(session.id) == []


def test_world_rejects_invalid_or_overlapping_outcome_rules() -> None:
    state = build_demo_world()
    objective_id = state.player_objectives[0].id
    duplicate_rule_id = state.dialogue_relationship_rules[0].id
    state.objective_outcome_consequence_rules = [
        _rule(duplicate_rule_id, objective_id)
    ]

    with pytest.raises(
        ValidationError,
        match="relationship consequence rule ids must not overlap",
    ):
        WorldState.model_validate(state.model_dump())

    payload = build_demo_world().model_dump(mode="json")
    payload["objective_outcome_consequence_rules"] = [
        {
            "id": "bad_outcome_rule",
            "objective_id": "missing_objective",
            "outcome": "completed",
            "source_npc_id": "npc_lio",
            "relationship_delta": 5,
        }
    ]
    with pytest.raises(
        ValidationError,
        match="objective outcome rule references missing objective",
    ):
        WorldState.model_validate(payload)
