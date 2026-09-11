from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from emergent_rpg.domain.actions import PlayerAction
from emergent_rpg.domain.models import GameSession, Turn, WorldState
from emergent_rpg.engine.mystery import MysteryGraph
from emergent_rpg.engine.narrative import DeterministicNarrativePlanner
from emergent_rpg.engine.reducer import apply_event, replay
from emergent_rpg.engine.resolver import ActionResult, DeterministicResolver
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
        emitted_events = list(result.emitted_events)
        for event in result.emitted_events:
            precheck = validate_event_preconditions(candidate, event)
            if not precheck.valid:
                raise TransitionRejected(str(precheck.issues))
            candidate = apply_event(candidate, event)

        inferred_events = self.mystery.infer_events(
            candidate,
            candidate.player_id,
            candidate.turn_number,
        )
        if inferred_events:
            observations = list(result.observations)
            for event in inferred_events:
                precheck = validate_event_preconditions(candidate, event)
                if not precheck.valid:
                    raise TransitionRejected(str(precheck.issues))
                candidate = apply_event(candidate, event)
                emitted_events.append(event)
                observations.append(f"Inference: {candidate.facts[event.fact_id].proposition}")
            result = result.model_copy(
                update={
                    "emitted_events": emitted_events,
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

        # Narrative generation happens before the transactional commit. A provider outage can
        # therefore fail the turn without leaving canonical state or the event log half-applied.
        narration = self.generator.generate(plan)

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
        self.store.commit_turn(session_id, candidate, result.emitted_events, turn, episode)
        return result, narration, candidate

    def replay_session(self, session_id: str) -> WorldState:
        return replay(self.store.load_initial_state(session_id), self.store.load_events(session_id))
