from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from emergent_rpg.api.app import create_app
from emergent_rpg.domain.actions import MoveAction, WaitAction
from emergent_rpg.domain.events import (
    NPCMoved,
    PlayerMoved,
    ScheduledLocationConditionApplied,
)
from emergent_rpg.domain.models import (
    NPC,
    LocationCondition,
    NPCGoal,
    RouteEffect,
)
from emergent_rpg.domain.npc_actions import NPCMoveIntent
from emergent_rpg.engine.npc import (
    DeterministicNPCPlanner,
    DeterministicNPCResolver,
    build_npc_planning_context,
)
from emergent_rpg.engine.reducer import apply_event
from emergent_rpg.engine.resolver import DeterministicResolver
from emergent_rpg.engine.service import GameEngine
from emergent_rpg.persistence.db import SQLiteStore
from emergent_rpg.providers.openai_compatible import _visible_action_surface
from emergent_rpg.validation.validator import validate_event_preconditions, validate_state
from emergent_rpg.world.demo import build_demo_world


def _active_squall_state():
    state = build_demo_world()
    state.clock = state.clock.advanced(20)
    event = ScheduledLocationConditionApplied(
        turn_number=1,
        scheduled_event_id="yard_ash_squall",
        scheduled_absolute_minute=500,
    )
    assert validate_event_preconditions(state, event).valid
    return apply_event(state, event)


def test_route_closure_rejects_player_move_and_expiry_restores_it(tmp_path: Path) -> None:
    engine = GameEngine(SQLiteStore(tmp_path / "route-lifecycle.db"))
    session = engine.new_session()
    initial = engine.store.load_state(session.id)

    before = DeterministicResolver().resolve(initial, MoveAction(destination="ridge"))
    assert before.accepted

    engine.execute_action(session.id, WaitAction(minutes=20), "wait 20")
    active = engine.store.load_state(session.id)
    events_before_rejection = engine.store.load_events(session.id)
    rejected, _, rejected_state = engine.execute_action(
        session.id,
        MoveAction(destination="ridge"),
        "move ridge",
    )

    assert not rejected.accepted
    assert rejected.emitted_events == []
    assert rejected.reason is not None and "Ash squall" in rejected.reason
    assert rejected_state == active
    assert engine.store.load_state(session.id) == active
    assert engine.store.load_events(session.id) == events_before_rejection

    engine.execute_action(session.id, WaitAction(minutes=20), "wait 20")
    expired = engine.store.load_state(session.id)
    after = DeterministicResolver().resolve(expired, MoveAction(destination="ridge"))

    assert "ash_squall" not in expired.locations["yard"].active_conditions
    assert after.accepted


def test_route_effect_is_data_driven_not_condition_name_specific() -> None:
    state = build_demo_world()
    state.locations["yard"].active_conditions["dust_wall"] = LocationCondition(
        code="dust_wall",
        name="Dust wall",
        description="A dense curtain of dust seals the operations doorway.",
        route=RouteEffect(blocked_destination_ids={"operations"}),
    )

    blocked = DeterministicResolver().resolve(state, MoveAction(destination="operations"))
    ridge = DeterministicResolver().resolve(state, MoveAction(destination="ridge"))

    assert not blocked.accepted
    assert blocked.reason is not None and "Dust wall" in blocked.reason
    assert ridge.accepted


def test_invalid_route_effect_cannot_reference_non_local_destination() -> None:
    state = build_demo_world()
    state.scheduled_location_conditions[0].condition.route = RouteEffect(
        blocked_destination_ids={"archive"}
    )

    report = validate_state(state)

    assert not report.valid
    assert any(issue.code == "invalid_environment_rule" for issue in report.issues)


def test_forged_player_move_across_closed_route_is_rejected() -> None:
    state = _active_squall_state()
    forged = PlayerMoved(
        turn_number=state.turn_number + 1,
        entity_id=state.player_id,
        from_location="yard",
        to_location="ridge",
    )

    report = validate_event_preconditions(state, forged)

    assert not report.valid
    assert any(issue.code == "blocked_environmental_route" for issue in report.issues)


def test_npc_planning_and_resolution_both_respect_route_closure() -> None:
    state = _active_squall_state()
    dax = state.entities["npc_dax"]
    assert isinstance(dax, NPC)
    dax.state.current_location = "yard"
    dax.planning_goals = [
        NPCGoal(
            id="dax_reach_ridge",
            kind="reach_location",
            target_id="ridge",
            priority=100,
        )
    ]
    dax.completed_goal_ids.clear()

    context = build_npc_planning_context(state, dax.id)
    plan = DeterministicNPCPlanner().plan(context)
    forged_intent = NPCMoveIntent(
        goal_id="dax_reach_ridge",
        destination_id="ridge",
    )
    resolved = DeterministicNPCResolver().resolve(
        state,
        dax.id,
        forged_intent,
        turn_number=state.turn_number + 1,
    )
    forged_event = NPCMoved(
        turn_number=state.turn_number + 1,
        npc_id=dax.id,
        from_location="yard",
        to_location="ridge",
    )
    event_report = validate_event_preconditions(state, forged_event)

    assert "ridge" not in context.exits.values()
    assert plan.intents == []
    assert not resolved.accepted
    assert resolved.reason is not None and "Ash squall" in resolved.reason
    assert not event_report.valid
    assert any(
        issue.code == "blocked_environmental_route" for issue in event_report.issues
    )


def test_parser_surface_lists_only_current_route_access() -> None:
    initial = build_demo_world()
    active = _active_squall_state()

    initial_surface = _visible_action_surface(initial)
    active_surface = _visible_action_surface(active)

    assert "ridge" in initial_surface["exits"]
    assert "Glass Ridge" in initial_surface["exits"]
    assert "ridge" not in active_surface["exits"]
    assert "Glass Ridge" not in active_surface["exits"]
    assert active_surface["blocked_exits"] == [
        {
            "alias": "ridge",
            "destination": "Glass Ridge",
            "blocked_by": ["Ash squall"],
        }
    ]


def test_api_and_browser_show_current_closure_without_future_schedule(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path / "route-api.db"))
    page = client.get("/ui/")
    script = client.get("/ui/app.js")
    created = client.post("/sessions", json={"name": "Route closure API"})
    session_id = created.json()["session"]["id"]

    assert page.status_code == 200
    assert script.status_code == 200
    assert 'id="blocked-exits"' in page.text
    assert "view.blocked_exits" in script.text
    assert created.json()["state"]["blocked_exits"] == []
    assert "yard_ash_squall" not in json.dumps(created.json(), sort_keys=True)

    active = client.post(
        f"/sessions/{session_id}/actions",
        json={"text": "wait 20"},
    )
    active_state = active.json()["state"]

    assert active.status_code == 200
    assert "ridge" not in active_state["exits"]
    assert active_state["blocked_exits"] == [
        {
            "alias": "ridge",
            "destination_id": "ridge",
            "destination_name": "Glass Ridge",
            "blocked_by": ["Ash squall"],
        }
    ]
    assert "yard_ash_squall" not in json.dumps(active.json(), sort_keys=True)

    expired = client.post(
        f"/sessions/{session_id}/actions",
        json={"text": "wait 20"},
    )
    expired_state = expired.json()["state"]

    assert expired.status_code == 200
    assert expired_state["exits"]["ridge"] == "Glass Ridge"
    assert expired_state["blocked_exits"] == []
