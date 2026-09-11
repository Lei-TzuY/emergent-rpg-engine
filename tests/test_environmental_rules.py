from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from emergent_rpg.api.app import create_app
from emergent_rpg.domain.actions import MoveAction, WaitAction
from emergent_rpg.domain.events import TimeAdvanced
from emergent_rpg.domain.models import LocationCondition, TraversalEffect
from emergent_rpg.engine.environment import EnvironmentalRules
from emergent_rpg.engine.narrative import ScenePlan
from emergent_rpg.engine.resolver import ActionResult, DeterministicResolver
from emergent_rpg.engine.service import GameEngine
from emergent_rpg.persistence.db import SQLiteStore
from emergent_rpg.providers.base import NarrativeGenerator
from emergent_rpg.providers.errors import ProviderRequestError
from emergent_rpg.world.demo import build_demo_world


class FailingNarrativeGenerator(NarrativeGenerator):
    def generate(self, scene_plan: ScenePlan) -> str:
        del scene_plan
        raise ProviderRequestError("simulated outage during hazardous movement")


def _time_advanced_minutes(result: ActionResult) -> int:
    events = result.emitted_events
    time_events = [event for event in events if isinstance(event, TimeAdvanced)]
    assert len(time_events) == 1
    return time_events[0].minutes


def test_baseline_travel_remains_five_minutes_without_environmental_modifier() -> None:
    state = build_demo_world()

    result = DeterministicResolver().resolve(state, MoveAction(destination="operations"))

    assert result.accepted
    assert _time_advanced_minutes(result) == 5
    assert "environment" not in result.tags


def test_synthetic_condition_modifies_travel_without_condition_name_branching() -> None:
    state = build_demo_world()
    state.locations["yard"].active_conditions["mud_bank"] = LocationCondition(
        code="mud_bank",
        name="Mud bank",
        description="Rain has turned the yard into deep adhesive mud.",
        traversal=TraversalEffect(extra_minutes=7),
    )

    result = DeterministicResolver().resolve(state, MoveAction(destination="operations"))

    assert result.accepted
    assert _time_advanced_minutes(result) == 12
    assert "environment" in result.tags
    assert any("Mud bank" in observation for observation in result.observations)


def test_multiple_active_conditions_add_deterministic_traversal_cost() -> None:
    state = build_demo_world()
    state.locations["yard"].active_conditions = {
        "crosswind": LocationCondition(
            code="crosswind",
            name="Crosswind",
            description="A hard crosswind slows exposed movement.",
            traversal=TraversalEffect(extra_minutes=2),
        ),
        "loose_scree": LocationCondition(
            code="loose_scree",
            name="Loose scree",
            description="Unstable stones force careful footing.",
            traversal=TraversalEffect(extra_minutes=3),
        ),
    }

    cost = EnvironmentalRules().traversal_cost(state, "yard")

    assert cost.base_minutes == 5
    assert cost.extra_minutes == 5
    assert cost.total_minutes == 10
    assert cost.condition_codes == ["crosswind", "loose_scree"]


def test_traversal_effect_schema_rejects_invalid_extra_time() -> None:
    with pytest.raises(ValidationError):
        TraversalEffect(extra_minutes=-1)
    with pytest.raises(ValidationError):
        TraversalEffect(extra_minutes=61)


def test_demo_ash_squall_changes_executable_movement_and_replays(tmp_path: Path) -> None:
    engine = GameEngine(SQLiteStore(tmp_path / "hazard.db"))
    session = engine.new_session()

    engine.execute_action(session.id, WaitAction(minutes=20), "wait 20")
    before_move = engine.store.load_state(session.id)
    assert before_move.locations["yard"].active_conditions["ash_squall"].traversal is not None

    result, narration, after_move = engine.execute_action(
        session.id,
        MoveAction(destination="operations"),
        "move operations",
    )

    assert result.accepted
    assert _time_advanced_minutes(result) == 10
    assert "environment" in result.tags
    assert "Ash squall" in narration
    assert after_move.clock.absolute_minutes == before_move.clock.absolute_minutes + 10
    assert after_move.player().state.current_location == "operations"
    assert engine.replay_session(session.id) == after_move


def test_provider_failure_does_not_commit_hazard_modified_move(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "atomic-hazard.db")
    setup_engine = GameEngine(store)
    session = setup_engine.new_session()
    setup_engine.execute_action(session.id, WaitAction(minutes=20), "wait 20")
    before = store.load_state(session.id)
    before_events = store.load_events(session.id)
    before_turns = store.list_turns(session.id)

    failing = GameEngine(store, generator=FailingNarrativeGenerator())
    with pytest.raises(ProviderRequestError, match="hazardous movement"):
        failing.execute_action(
            session.id,
            MoveAction(destination="operations"),
            "move operations",
        )

    assert store.load_state(session.id) == before
    assert store.load_events(session.id) == before_events
    assert store.list_turns(session.id) == before_turns


def test_api_and_browser_explain_active_traversal_modifier(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path / "hazard-api.db"))
    created = client.post("/sessions", json={"name": "Hazard UI"})
    session_id = created.json()["session"]["id"]

    activated = client.post(
        f"/sessions/{session_id}/actions",
        json={"text": "wait 20"},
    )
    script = client.get("/ui/app.js")

    assert activated.status_code == 200
    conditions = activated.json()["state"]["location_conditions"]
    assert conditions == [
        {
            "code": "ash_squall",
            "name": "Ash squall",
            "description": (
                "A dense ash squall sweeps across the yard, reducing visibility and "
                "turning the black grit into a stinging horizontal sheet."
            ),
            "traversal_extra_minutes": 5,
        }
    ]
    assert script.status_code == 200
    assert "traversal_extra_minutes" in script.text
    assert "Travel +" in script.text
