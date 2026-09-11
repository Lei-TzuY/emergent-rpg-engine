from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from emergent_rpg.domain.actions import PlayerAction
from emergent_rpg.domain.events import (
    Event,
    ScheduledLocationConditionApplied,
    SimulationCycleProcessed,
)
from emergent_rpg.domain.models import GameSession, Turn, WorldState
from emergent_rpg.engine.mystery import MysteryGraph
from emergent_rpg.engine.narrative import DeterministicNarrativePlanner
from emergent_rpg.engine.npc import (
    DeterministicNPCPlanner,
    DeterministicNPCResolver,
    NPCDecision,
    NPCPhaseResult,
    build_npc_planning_context,
)
from emergent_rpg.engine.reducer import apply_event, replay
from emergent_rpg.engine.resolver import ActionResult, DeterministicResolver
from emergent_rpg.engine.simulation import (
    DeterministicSimulationScheduler,
    DeterministicWorldEventScheduler,
)
from emergent_rpg.memory.models import Episode
from emergent_rpg.persistence.db import SQLiteStore
from emergent_rpg.providers.base import ActionParser, NarrativeGenerator
from emergent_rpg.providers.scripted import DeterministicActionParser, ScriptedNarrativeGenerator
from emergent_rpg.validation.validator import validate_event_preconditions, validate_state
from emergent_rpg.world.demo import build_demo_world


class TransitionRejected(RuntimeError):
    pass


class GameEngine:
    def __init__(
        self,
        store: SQLiteStore,
        generator: NarrativeGenerator | None = None,
        parser: ActionParser | None = None,
    ) -> None:
        self.store = store
        self.parser = parser or DeterministicActionParser()
        self.resolver = DeterministicResolver()
        self.planner = DeterministicNarrativePlanner()
        self.mystery = MysteryGraph()
        self.npc_planner = DeterministicNPCPlanner()
        self.npc_resolver = DeterministicNPCResolver()
        self.simulation_scheduler = DeterministicSimulationScheduler()
        self.world_event_scheduler = DeterministicWorldEventScheduler()
        self.generator = generator or ScriptedNarrativeGenerator()

    def new_session(self, name: str = "Ashfall Relay") -> GameSession:
        session = GameSession(
            id=str(uuid4()),
            name=name,
            world_pack="ashfall-relay",
            created_at=datetime.now(UTC).isoformat(),
        )
        state = build_demo_world()
        report = validate_state(state)
        if not report.valid:
            raise TransitionRejected(str(report.issues))
        self.store.create_session(session, state)
        return session

    def process_text(self, session_id: str, text: str) -> tuple[ActionResult, str, WorldState]:
        state = self.store.load_state(session_id)
        action = self.parser.parse(text, state)
        return self.execute_action(session_id, action, text)

    def execute_action(
        self, session_id: str, action: PlayerAction, raw_input: str
    ) -> tuple[ActionResult, str, WorldState]:
        before = self.store.load_state(session_id)
        result = self.resolver.resolve(before, action)
        if not result.accepted:
            narration = result.reason or "That action is rejected."
            turn = Turn(
                session_id=session_id,
                turn_number=before.turn_number,
                raw_input=raw_input,
                accepted=False,
                reason=result.reason,
                narration=narration,
                location_id=before.player().state.current_location,
            )
            self.store.commit_turn(session_id, before, [], turn, None)
            return result, narration, before

        candidate = before.model_copy(deep=True)
        player_events = list(result.emitted_events)
        for event in result.emitted_events:
            candidate = self._apply_validated_event(candidate, event)

        inferred_events = self.mystery.infer_events(
            candidate,
            candidate.player_id,
            candidate.turn_number,
        )
        if inferred_events:
            observations = list(result.observations)
            for event in inferred_events:
                candidate = self._apply_validated_event(candidate, event)
                player_events.append(event)
                observations.append(f"Inference: {candidate.facts[event.fact_id].proposition}")
            result = result.model_copy(
                update={
                    "emitted_events": player_events,
                    "observations": observations,
                    "tags": result.tags | {"inference"},
                }
            )

        state_report = validate_state(candidate, previous=before)
        if not state_report.valid:
            raise TransitionRejected(str(state_report.issues))

        plan = self.planner.plan(before, candidate, action, result)
        scene_report = self.planner.validate(candidate, plan)
        if not scene_report.valid:
            raise TransitionRejected(str(scene_report.issues))

        # Narrative generation happens before simulation and before the transactional commit.
        # A provider outage therefore cannot leave either the player's action or off-screen
        # consequences half-applied.
        narration = self.generator.generate(plan)

        candidate, simulation_events = self._run_due_simulation(
            candidate,
            turn_number=candidate.turn_number,
        )
        final_report = validate_state(candidate, previous=before)
        if not final_report.valid:
            raise TransitionRejected(str(final_report.issues))

        location_id = candidate.player().state.current_location
        turn = Turn(
            session_id=session_id,
            turn_number=candidate.turn_number,
            raw_input=raw_input,
            accepted=True,
            narration=narration,
            location_id=location_id,
            involved_entities=result.involved_entities,
            tags=result.tags | {action.kind},
        )
        importance = min(1.0, 0.35 + 0.1 * len(result.emitted_events))
        episode = Episode(
            id=str(uuid4()),
            turn_range=(candidate.turn_number, candidate.turn_number),
            involved_entities=result.involved_entities,
            location=location_id,
            tags=result.tags | {action.kind},
            summary=narration,
            importance=importance,
        )
        all_events = [*result.emitted_events, *simulation_events]
        self.store.commit_turn(session_id, candidate, all_events, turn, episode)
        return result, narration, candidate

    def _apply_validated_event(self, state: WorldState, event: Event) -> WorldState:
        precheck = validate_event_preconditions(state, event)
        if not precheck.valid:
            raise TransitionRejected(str(precheck.issues))
        return apply_event(state, event)

    def _execute_npc_phase_on_state(
        self,
        state: WorldState,
        *,
        turn_number: int,
        max_actions: int,
        offscreen_only: bool,
    ) -> tuple[NPCPhaseResult, WorldState]:
        if not 1 <= max_actions <= 20:
            raise ValueError("max_actions must be between 1 and 20")

        candidate = state.model_copy(deep=True)
        decisions: list[NPCDecision] = []
        emitted_events: list[Event] = []
        involved_npc_ids: set[str] = set()
        actions_attempted = 0
        actions_executed = 0
        player_location = candidate.player().state.current_location

        npc_ids = sorted(
            entity_id
            for entity_id, entity in candidate.entities.items()
            if entity.kind == "npc"
            and (not offscreen_only or entity.state.current_location != player_location)
        )
        for npc_id in npc_ids:
            if actions_attempted >= max_actions:
                break
            context = build_npc_planning_context(candidate, npc_id)
            plan = self.npc_planner.plan(context, max_steps=1)
            for intent in plan.intents:
                if actions_attempted >= max_actions:
                    break
                actions_attempted += 1
                action_result = self.npc_resolver.resolve(
                    candidate,
                    npc_id,
                    intent,
                    turn_number,
                )
                decisions.append(
                    NPCDecision(
                        npc_id=npc_id,
                        intent=intent,
                        accepted=action_result.accepted,
                        reason=action_result.reason,
                    )
                )
                if not action_result.accepted:
                    continue

                for event in action_result.emitted_events:
                    candidate = self._apply_validated_event(candidate, event)
                    emitted_events.append(event)

                inferred_events = self.mystery.infer_events(
                    candidate,
                    npc_id,
                    turn_number,
                )
                for event in inferred_events:
                    candidate = self._apply_validated_event(candidate, event)
                    emitted_events.append(event)

                actions_executed += 1
                involved_npc_ids.add(npc_id)

        return (
            NPCPhaseResult(
                actions_attempted=actions_attempted,
                actions_executed=actions_executed,
                decisions=decisions,
                emitted_events=emitted_events,
                involved_npc_ids=involved_npc_ids,
            ),
            candidate,
        )

    def _run_due_simulation(
        self,
        state: WorldState,
        *,
        turn_number: int,
    ) -> tuple[WorldState, list[Event]]:
        npc_schedule = self.simulation_scheduler.due_cycles(state)
        world_schedule = self.world_event_scheduler.due_events(state)
        if not npc_schedule.due_absolute_minutes and not world_schedule.due_event_ids:
            return state, []

        scheduled_by_id = {
            item.id: item for item in state.scheduled_location_conditions
        }
        timeline: list[tuple[int, int, str, str]] = []
        for scheduled_event_id in world_schedule.due_event_ids:
            scheduled = scheduled_by_id[scheduled_event_id]
            timeline.append(
                (
                    scheduled.due_absolute_minute,
                    0,
                    "world",
                    scheduled_event_id,
                )
            )
        for scheduled_minute in npc_schedule.due_absolute_minutes:
            timeline.append((scheduled_minute, 1, "npc", ""))
        timeline.sort()

        candidate = state.model_copy(deep=True)
        emitted_events: list[Event] = []
        for scheduled_minute, _, kind, scheduled_event_id in timeline:
            if kind == "world":
                event = ScheduledLocationConditionApplied(
                    turn_number=turn_number,
                    scheduled_event_id=scheduled_event_id,
                    scheduled_absolute_minute=scheduled_minute,
                )
                candidate = self._apply_validated_event(candidate, event)
                emitted_events.append(event)
                continue

            phase, candidate = self._execute_npc_phase_on_state(
                candidate,
                turn_number=turn_number,
                max_actions=candidate.simulation.max_npc_actions_per_cycle,
                offscreen_only=True,
            )
            emitted_events.extend(phase.emitted_events)
            marker = SimulationCycleProcessed(
                turn_number=turn_number,
                scheduled_absolute_minute=scheduled_minute,
            )
            candidate = self._apply_validated_event(candidate, marker)
            emitted_events.append(marker)
        return candidate, emitted_events

    def run_npc_phase(
        self,
        session_id: str,
        max_actions: int = 3,
    ) -> tuple[NPCPhaseResult, WorldState]:
        before = self.store.load_state(session_id)
        phase, candidate = self._execute_npc_phase_on_state(
            before,
            turn_number=before.turn_number + 1,
            max_actions=max_actions,
            offscreen_only=False,
        )
        if not phase.emitted_events:
            return phase, before

        state_report = validate_state(candidate, previous=before)
        if not state_report.valid:
            raise TransitionRejected(str(state_report.issues))

        narration = f"Autonomous NPC phase executed {phase.actions_executed} action(s)."
        turn = Turn(
            session_id=session_id,
            turn_number=candidate.turn_number,
            raw_input="[npc-phase]",
            accepted=True,
            narration=narration,
            location_id=candidate.player().state.current_location,
            involved_entities=phase.involved_npc_ids,
            tags={"npc", "autonomous"},
        )
        self.store.commit_turn(
            session_id,
            candidate,
            phase.emitted_events,
            turn,
            None,
        )
        return phase, candidate

    def replay_session(self, session_id: str) -> WorldState:
        return replay(self.store.load_initial_state(session_id), self.store.load_events(session_id))
