from __future__ import annotations

from collections import Counter
from pathlib import Path

from pydantic import BaseModel, Field

from emergent_rpg.domain.actions import GiveAction, TakeAction, WaitAction
from emergent_rpg.domain.models import (
    DialogueRelationshipRule,
    GameSession,
    ItemTurnInConsequenceRule,
    NPC,
    NPCGoal,
    WorldState,
)
from emergent_rpg.engine.service import GameEngine
from emergent_rpg.persistence.db import SQLiteStore
from emergent_rpg.validation.validator import validate_state
from emergent_rpg.world.demo import build_demo_world

AUTONOMY_SCENARIO = "autonomy-custody-social-v1"


class AutonomyIntegrationReport(BaseModel):
    scenario: str = AUTONOMY_SCENARIO
    rounds: int
    event_count: int
    persisted_turn_count: int
    event_type_counts: dict[str, int] = Field(default_factory=dict)
    replay_equal: bool
    state_valid: bool
    unique_event_ids: bool
    item_ownership_valid: bool
    private_fact_isolated: bool
    milestones: dict[str, bool] = Field(default_factory=dict)
    failures: list[str] = Field(default_factory=list)
    passed: bool


def run_autonomy_integration_evaluation(
    db_path: str | Path,
    *,
    rounds: int = 20,
) -> AutonomyIntegrationReport:
    if rounds < 1:
        raise ValueError("rounds must be positive")

    path = Path(db_path)
    if path.exists():
        raise FileExistsError(f"evaluation database already exists: {path}")

    state = _build_evaluation_world()
    initial_report = validate_state(state)
    if not initial_report.valid:
        raise ValueError(f"invalid evaluation world: {initial_report.issues}")

    store = SQLiteStore(path)
    engine = GameEngine(store)
    session = GameSession(
        id="autonomy-integration-evaluation",
        name="Autonomy integration evaluation",
        world_pack="ashfall-relay-evaluation",
        created_at="2026-09-12T00:00:00+00:00",
    )
    store.create_session(session, state)

    _execute_required_action(
        engine,
        session.id,
        TakeAction(target="brass key"),
        "[autonomy-eval] take brass key",
    )
    _execute_required_action(
        engine,
        session.id,
        GiveAction(item="brass key", receiver="Lio Marr"),
        "[autonomy-eval] give brass key to Lio Marr",
    )

    social_phase, _ = engine.run_npc_social_phase(session.id, max_actions=2)
    if social_phase.actions_executed < 2:
        raise RuntimeError("autonomy evaluation expected two initial social actions")

    for _ in range(6):
        engine.run_npc_phase(session.id, max_actions=5)
        current = store.load_state(session.id)
        if _workflow_goals_complete(current):
            break

    for index in range(rounds):
        _execute_required_action(
            engine,
            session.id,
            WaitAction(minutes=5),
            f"[autonomy-eval:{index}] wait 5",
        )

    final_state = store.load_state(session.id)
    events = store.load_events(session.id)
    event_ids = [event.event_id for event in events]
    event_type_counts = dict(Counter(event.type for event in events))
    milestones = _milestone_checks(final_state, event_type_counts)
    failures = [name for name, passed in milestones.items() if not passed]

    replay_equal = engine.replay_session(session.id) == final_state
    state_valid = validate_state(final_state).valid
    unique_event_ids = len(event_ids) == len(set(event_ids))
    item_ownership_valid = _item_ownership_valid(final_state)
    private_fact_isolated = "fact_generator_stable" not in final_state.player_known_facts

    if not replay_equal:
        failures.append("replay_mismatch")
    if not state_valid:
        failures.append("state_validation_failed")
    if not unique_event_ids:
        failures.append("duplicate_event_id")
    if not item_ownership_valid:
        failures.append("item_ownership_invalid")
    if not private_fact_isolated:
        failures.append("npc_private_fact_leaked_to_player")

    return AutonomyIntegrationReport(
        rounds=rounds,
        event_count=len(events),
        persisted_turn_count=len(store.list_turns(session.id)),
        event_type_counts=event_type_counts,
        replay_equal=replay_equal,
        state_valid=state_valid,
        unique_event_ids=unique_event_ids,
        item_ownership_valid=item_ownership_valid,
        private_fact_isolated=private_fact_isolated,
        milestones=milestones,
        failures=failures,
        passed=not failures,
    )


def _build_evaluation_world() -> WorldState:
    state = build_demo_world()
    state.dialogue_relationship_rules = [
        DialogueRelationshipRule(
            id="eval_lio_dax_trust",
            speaker_id="npc_lio",
            listener_id="npc_dax",
            required_listener_fact_ids={"fact_generator_stable"},
            delta=5,
            priority=100,
            once=True,
        )
    ]
    state.applied_dialogue_relationship_rule_ids.clear()
    state.item_turn_in_consequence_rules = [
        ItemTurnInConsequenceRule(
            id="eval_key_turn_in",
            receiver_npc_id="npc_lio",
            item_id="item_brass_key",
            required_goal_id="eval_lio_receive_key",
            relationship_delta=7,
            reward_fact_id="fact_schedule",
            priority=100,
            observation="Lio accepts the key as useful evidence.",
        )
    ]
    state.applied_item_turn_in_consequence_rule_ids.clear()

    lio = _npc(state, "npc_lio")
    lio.planning_goals = [
        NPCGoal(
            id="eval_lio_receive_key",
            kind="acquire_item",
            target_id="item_brass_key",
            priority=100,
        )
    ]
    lio.completed_goal_ids.clear()

    dax = _npc(state, "npc_dax")
    dax.state.current_location = "yard"
    dax.planning_goals = [
        NPCGoal(
            id="eval_dax_reach_operations",
            kind="reach_location",
            target_id="operations",
            priority=100,
            required_fact_ids={"fact_generator_stable"},
        )
    ]
    dax.completed_goal_ids.clear()
    dax.knowledge.mapped_locations = {"yard", "operations"}

    sera = _npc(state, "npc_sera")
    sera.planning_goals = [
        NPCGoal(
            id="eval_sera_acquire_token",
            kind="acquire_item",
            target_id="item_archive_token",
            priority=100,
        ),
        NPCGoal(
            id="eval_sera_deliver_token",
            kind="deliver_item",
            target_id="item_archive_token",
            receiver_id="npc_mina",
            delivery_location_id="infirmary",
            priority=90,
        ),
    ]
    sera.completed_goal_ids.clear()
    sera.knowledge.mapped_locations = {"archive", "operations", "infirmary"}
    sera.knowledge.item_location_beliefs["item_archive_token"] = "archive"

    return state


def _execute_required_action(
    engine: GameEngine,
    session_id: str,
    action: GiveAction | TakeAction | WaitAction,
    raw_input: str,
) -> WorldState:
    result, _, state = engine.execute_action(session_id, action, raw_input)
    if not result.accepted:
        raise RuntimeError(f"required evaluation action rejected: {result.reason}")
    return state


def _workflow_goals_complete(state: WorldState) -> bool:
    lio = _npc(state, "npc_lio")
    dax = _npc(state, "npc_dax")
    sera = _npc(state, "npc_sera")
    return (
        "eval_lio_receive_key" in lio.completed_goal_ids
        and "eval_dax_reach_operations" in dax.completed_goal_ids
        and "eval_sera_acquire_token" in sera.completed_goal_ids
        and "eval_sera_deliver_token" in sera.completed_goal_ids
    )


def _milestone_checks(state: WorldState, counts: dict[str, int]) -> dict[str, bool]:
    lio = _npc(state, "npc_lio")
    dax = _npc(state, "npc_dax")
    sera = _npc(state, "npc_sera")
    token = state.items["item_archive_token"]
    return {
        "player_handoff": counts.get("player_item_given", 0) >= 1,
        "turn_in_reward": (
            "eval_key_turn_in" in state.applied_item_turn_in_consequence_rule_ids
            and "fact_schedule" in state.player_known_facts
            and lio.relationships.get(state.player_id, 0) >= 7
        ),
        "social_fact_diffusion": (
            counts.get("npc_fact_shared", 0) >= 2
            and "fact_generator_stable" in dax.knowledge.facts_known
        ),
        "social_relationship_progression": (
            "eval_lio_dax_trust" in state.applied_dialogue_relationship_rule_ids
            and lio.relationships.get(dax.id, 0) >= 5
        ),
        "knowledge_gated_reactive_goal": (
            "eval_dax_reach_operations" in dax.completed_goal_ids
        ),
        "npc_item_acquisition": "eval_sera_acquire_token" in sera.completed_goal_ids,
        "npc_item_delivery": (
            "eval_sera_deliver_token" in sera.completed_goal_ids
            and token.owner_id == "npc_mina"
        ),
        "automatic_simulation": counts.get("simulation_cycle_processed", 0) >= 1,
        "goal_event_provenance": counts.get("npc_goal_completed", 0) >= 4,
        "custody_event_provenance": counts.get("item_acquired", 0) >= 2,
    }


def _npc(state: WorldState, npc_id: str) -> NPC:
    entity = state.entities[npc_id]
    if not isinstance(entity, NPC):
        raise TypeError(f"{npc_id} is not an NPC")
    return entity


def _item_ownership_valid(state: WorldState) -> bool:
    inventory_holders: dict[str, str] = {}
    for entity_id, entity in state.entities.items():
        if len(entity.state.inventory) != len(set(entity.state.inventory)):
            return False
        for item_id in entity.state.inventory:
            if item_id in inventory_holders:
                return False
            inventory_holders[item_id] = entity_id

    for item_id, item in state.items.items():
        if item.owner_id is not None:
            if inventory_holders.get(item_id) != item.owner_id:
                return False
        elif item_id in inventory_holders:
            return False
    return True
