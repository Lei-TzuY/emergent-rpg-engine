from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from emergent_rpg.domain.actions import PlayerAction
from emergent_rpg.domain.events import (
    Event,
    NPCFactShared,
    PlayerObjectiveActivated,
    PlayerObjectiveCompleted,
    ScheduledLocationConditionApplied,
    ScheduledLocationConditionExpired,
    SimulationCycleProcessed,
)
from emergent_rpg.domain.models import GameSession, Turn, WorldState
from emergent_rpg.engine.mystery import MysteryGraph
from emergent_rpg.engine.narrative import DeterministicNarrativePlanner
from emergent_rpg.engine.objectives import PlayerObjectivePolicy
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

        objective_events = PlayerObjectivePolicy.progression_events(
            candidate,
            candidate.turn_number,
        )
        if objective_events:
            observations = list(result.observations)
            for event in objective_events:
                candidate = self._apply_validated_event(candidate, event)
                player_events.append(event)
                objective = PlayerObjectivePolicy.objective_by_id(candidate, event.objective_id)
                title = objective.title if objective is not None else event.objective_id
                if isinstance(event, PlayerObjectiveActivated):
                    observations.append(f"Objective started: {title}")
                elif isinstance(event, PlayerObjectiveCompleted):
                    observations.append(f"Objective completed: {title}")
            result = result.model_copy(
                update={
                    "emitted_events": player_events,
                    "observations": observations,
                    "tags": result.tags | {"objective"},
                }
            )

        state_report = validate_state(
            candidate,
            previous=before,
            transition_events=player_events,
        )
        if not state_report.valid:
            raise TransitionRejected(str(state_report.issues))

        plan = self.planner.plan(before, candidate, action, result)
        scene_report = self.planner.validate(candidate, plan)
        if not scene_report.valid:
            raise TransitionRejected(str(scene_report.issues))

        narration = self.generator.generate(plan)

        candidate, simulation_events = self._run_due_simulation(
            candidate,
            turn_number=candidate.turn_number,
        )
        final_report = validate_state(
            candidate,
            previous=before,
            transition_events=[*player_events, *simulation_events],
        )
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

    def _execute_npc_social_phase_on_state(
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
            intent = self.npc_planner.plan_fact_share(context)
            if intent is None:
                continue

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

            receiver_ids: set[str] = set()
            for event in action_result.emitted_events:
                candidate = self._apply_validated_event(candidate, event)
                emitted_events.append(event)
                if isinstance(event, NPCFactShared):
                    receiver_ids.add(event.receiver_npc_id)
                    involved_npc_ids.add(event.receiver_npc_id)

            for receiver_id in sorted(receiver_ids):
                inferred_events = self.mystery.infer_events(
                    candidate,
                    receiver_id,
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
        if not npc_schedule.due_absolute_minutes and not world_schedule.due_events:
            return state, []

        expiry_targets: dict[str, tuple[str, str]] = {
            item.id: (item.location_id, item.condition_code)
            for item in state.scheduled_location_condition_expirations
        }
        for activation in state.scheduled_location_conditions:
            if activation.expiry_absolute_minute is not None:
                expiry_targets[activation.expiry_event_id] = (
                    activation.location_id,
                    activation.condition.code,
                )

        timeline: list[tuple[int, int, str, str]] = []
        for due_event in world_schedule.due_events:
            priority = 0 if due_event.kind == "activate" else 1
            timeline.append(
                (
                    due_event.due_absolute_minute,
                    priority,
                    due_event.kind,
                    due_event.event_id,
                )
            )
        for scheduled_minute in npc_schedule.due_absolute_minutes:
            timeline.append((scheduled_minute, 2, "npc", ""))
        timeline.sort()

        candidate = state.model_copy(deep=True)
        emitted_events: list[Event] = []
        for scheduled_minute, _, kind, scheduled_event_id in timeline:
            if kind == "activate":
                activation_event = ScheduledLocationConditionApplied(
                    turn_number=turn_number,
                    scheduled_event_id=scheduled_event_id,
                    scheduled_absolute_minute=scheduled_minute,
                )
                candidate = self._apply_validated_event(candidate, activation_event)
                emitted_events.append(activation_event)
                continue
            if kind == "expire":
                location_id, condition_code = expiry_targets[scheduled_event_id]
                expiry_event = ScheduledLocationConditionExpired(
                    turn_number=turn_number,
                    scheduled_event_id=scheduled_event_id,
                    scheduled_absolute_minute=scheduled_minute,
                    location_id=location_id,
                    condition_code=condition_code,
                )
                candidate = self._apply_validated_event(candidate, expiry_event)
                emitted_events.append(expiry_event)
                continue

            phase, candidate = self._execute_npc_phase_on_state(
                candidate,
                turn_number=turn_number,
                max_actions=candidate.simulation.max_npc_actions_per_cycle,
                offscreen_only=True,
            )
            emitted_events.extend(phase.emitted_events)

            social_phase, candidate = self._execute_npc_social_phase_on_state(
                candidate,
                turn_number=turn_number,
                max_actions=candidate.simulation.max_social_actions_per_cycle,
                offscreen_only=True,
            )
            emitted_events.extend(social_phase.emitted_events)

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

        state_report = validate_state(
            candidate,
            previous=before,
            transition_events=phase.emitted_events,
        )
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

    def run_npc_social_phase(
        self,
        session_id: str,
        max_actions: int = 3,
    ) -> tuple[NPCPhaseResult, WorldState]:
        before = self.store.load_state(session_id)
        phase, candidate = self._execute_npc_social_phase_on_state(
            before,
            turn_number=before.turn_number + 1,
            max_actions=max_actions,
            offscreen_only=False,
        )
        if not phase.emitted_events:
            return phase, before

        state_report = validate_state(
            candidate,
            previous=before,
            transition_events=phase.emitted_events,
        )
        if not state_report.valid:
            raise TransitionRejected(str(state_report.issues))

        narration = f"NPC social phase executed {phase.actions_executed} action(s)."
        turn = Turn(
            session_id=session_id,
            turn_number=candidate.turn_number,
            raw_input="[npc-social-phase]",
            accepted=True,
            narration=narration,
            location_id=candidate.player().state.current_location,
            involved_entities=phase.involved_npc_ids,
            tags={"npc", "autonomous", "social"},
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
