from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from emergent_rpg.api.app import create_app
from emergent_rpg.domain.actions import AttackAction
from emergent_rpg.domain.events import CharacterDamaged, TimeAdvanced, parse_event
from emergent_rpg.domain.models import NPC
from emergent_rpg.engine.combat import CombatPolicy
from emergent_rpg.engine.narrative import ScenePlan
from emergent_rpg.engine.reducer import ReductionError, apply_event
from emergent_rpg.engine.resolver import DeterministicResolver
from emergent_rpg.engine.service import GameEngine
from emergent_rpg.persistence.db import SQLiteStore
from emergent_rpg.providers.base import NarrativeGenerator
from emergent_rpg.providers.errors import ProviderRequestError
from emergent_rpg.providers.openai_compatible import (
    OpenAICompatibleActionParser,
    OpenAICompatibleConfig,
)
from emergent_rpg.providers.scripted import DeterministicActionParser
from emergent_rpg.validation.validator import validate_event_preconditions, validate_state
from emergent_rpg.world.demo import build_demo_world


class RecordingTransport:
    def __init__(self, content: str) -> None:
        self.content = content
        self.payload: dict[str, object] | None = None

    def post_json(
        self,
        url: str,
        headers: Mapping[str, str],
        payload: Mapping[str, object],
        timeout: float,
    ) -> dict[str, object]:
        del url, headers, timeout
        self.payload = dict(payload)
        return {"choices": [{"message": {"content": self.content}}]}


class FailingNarrativeGenerator(NarrativeGenerator):
    def generate(self, scene_plan: ScenePlan) -> str:
        del scene_plan
        raise ProviderRequestError("simulated combat narration outage")


def _lio(state: object) -> NPC:
    assert hasattr(state, "entities")
    entity = state.entities["npc_lio"]  # type: ignore[attr-defined]
    assert isinstance(entity, NPC)
    return entity


def test_deterministic_parser_parses_attack_aliases() -> None:
    parser = DeterministicActionParser()
    state = build_demo_world()

    assert parser.parse("attack Lio Marr", state) == AttackAction(target="Lio Marr")
    assert parser.parse('hit "Lio Marr"', state) == AttackAction(target="Lio Marr")
    assert parser.parse("strike npc_lio", state) == AttackAction(target="npc_lio")


def test_structured_provider_can_propose_attack_from_visible_surface() -> None:
    state = build_demo_world()
    transport = RecordingTransport('{"kind":"attack","target":"Lio Marr"}')
    parser = OpenAICompatibleActionParser(
        OpenAICompatibleConfig(
            base_url="http://localhost:11434/v1",
            model="local-model",
        ),
        transport=transport,
    )

    action = parser.parse("Hit Lio.", state)

    assert action == AttackAction(target="Lio Marr")
    assert transport.payload is not None
    wire = str(transport.payload)
    assert "Lio Marr" in wire
    assert "planning_goals" not in wire
    assert "knowledge" not in wire


def test_resolver_emits_provenance_rich_fixed_unarmed_damage() -> None:
    state = build_demo_world()

    result = DeterministicResolver().resolve(
        state,
        AttackAction(target="Lio Marr"),
    )

    assert result.accepted
    damage = next(
        event
        for event in result.emitted_events
        if isinstance(event, CharacterDamaged)
    )
    advance = next(
        event for event in result.emitted_events if isinstance(event, TimeAdvanced)
    )
    assert damage.entity_id == "npc_lio"
    assert damage.source_id == state.player_id
    assert damage.cause == "unarmed_attack"
    assert damage.amount == CombatPolicy.UNARMED_DAMAGE
    assert advance.minutes == CombatPolicy.UNARMED_MINUTES
    assert result.involved_entities == {"player", "npc_lio"}
    assert {"combat", "attack"} <= result.tags


def test_attack_rejects_remote_inactive_and_incapacitated_targets() -> None:
    state = build_demo_world()
    resolver = DeterministicResolver()

    remote = resolver.resolve(state, AttackAction(target="Arden Vale"))
    assert not remote.accepted
    assert remote.emitted_events == []

    lio = _lio(state)
    lio.state.conscious = False
    inactive = resolver.resolve(state, AttackAction(target="Lio Marr"))
    assert not inactive.accepted
    assert inactive.emitted_events == []

    lio.state.conscious = True
    state.player().state.status_conditions.append(
        state.player().state.status_conditions.__class__.__args__[0](  # type: ignore[attr-defined]
            code="stunned",
            name="Stunned",
            incapacitating=True,
        )
    )
    incapacitated = resolver.resolve(state, AttackAction(target="Lio Marr"))
    assert not incapacitated.accepted
    assert incapacitated.emitted_events == []


def test_forged_unarmed_damage_is_rejected_by_validator_and_reducer() -> None:
    state = build_demo_world()
    forged_high_damage = CharacterDamaged(
        turn_number=1,
        entity_id="npc_lio",
        source_id=state.player_id,
        cause="unarmed_attack",
        amount=99,
    )

    report = validate_event_preconditions(state, forged_high_damage)
    assert not report.valid
    assert "unarmed attack damage must equal" in str(report.issues)
    with pytest.raises(ReductionError, match="unarmed attack damage must equal"):
        apply_event(state, forged_high_damage)

    _lio(state).state.current_location = "operations"
    forged_remote = CharacterDamaged(
        turn_number=1,
        entity_id="npc_lio",
        source_id=state.player_id,
        cause="unarmed_attack",
        amount=CombatPolicy.UNARMED_DAMAGE,
    )
    remote_report = validate_event_preconditions(state, forged_remote)
    assert not remote_report.valid
    assert "co-located" in str(remote_report.issues)
    with pytest.raises(ReductionError, match="co-located"):
        apply_event(state, forged_remote)


def test_direct_health_mutation_requires_damage_or_healing_event() -> None:
    before = build_demo_world()
    after = before.model_copy(deep=True)
    _lio(after).state.health = 1

    report = validate_state(after, previous=before, transition_events=[])

    assert not report.valid
    assert "character health does not match damage/healing event provenance" in str(
        report.issues
    )


def test_legacy_damage_event_shape_remains_replayable() -> None:
    state = build_demo_world()
    event = parse_event(
        {
            "type": "character_damaged",
            "turn_number": 1,
            "entity_id": "npc_lio",
            "amount": 1,
        }
    )

    assert isinstance(event, CharacterDamaged)
    assert event.source_id is None
    assert event.cause == "other"
    assert validate_event_preconditions(state, event).valid

    damaged = apply_event(state, event)

    assert _lio(damaged).state.health == 9


def test_engine_attack_persists_replays_and_eventually_kills_target(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "combat.db")
    engine = GameEngine(store)
    session = engine.new_session()

    for _ in range(5):
        result, _, state = engine.process_text(session.id, "attack Lio Marr")
        assert result.accepted

    lio = _lio(state)
    assert lio.state.health == 0
    assert not lio.state.alive
    assert not lio.state.conscious
    assert engine.replay_session(session.id) == state

    rejected, _, unchanged = engine.process_text(session.id, "attack Lio Marr")
    assert not rejected.accepted
    assert unchanged == state


def test_browser_api_raw_text_attack_uses_same_combat_authority(tmp_path: Path) -> None:
    db_path = tmp_path / "api-combat.db"
    client = TestClient(create_app(db_path))
    created = client.post("/sessions", json={"name": "Combat parity"})
    assert created.status_code == 201
    session_id = str(created.json()["session"]["id"])

    response = client.post(
        f"/sessions/{session_id}/actions",
        json={"text": "attack Lio Marr"},
    )

    assert response.status_code == 200
    assert response.json()["accepted"] is True
    store = SQLiteStore(db_path)
    state = store.load_state(session_id)
    assert _lio(state).state.health == 10 - CombatPolicy.UNARMED_DAMAGE
    persisted = store.load_events(session_id)
    damage = next(event for event in persisted if isinstance(event, CharacterDamaged))
    assert damage.source_id == state.player_id
    assert damage.cause == "unarmed_attack"
    assert GameEngine(store).replay_session(session_id) == state


def test_provider_failure_keeps_combat_zero_commit(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "combat-provider.db")
    engine = GameEngine(store, generator=FailingNarrativeGenerator())
    session = engine.new_session()
    before = store.load_state(session.id)

    with pytest.raises(ProviderRequestError, match="combat narration outage"):
        engine.process_text(session.id, "attack Lio Marr")

    assert store.load_state(session.id) == before
    assert store.load_events(session.id) == []
    assert store.list_turns(session.id) == []
