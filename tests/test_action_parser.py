from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

import pytest

from emergent_rpg.domain.actions import MoveAction
from emergent_rpg.engine.service import GameEngine
from emergent_rpg.persistence.db import SQLiteStore
from emergent_rpg.providers.errors import ProviderResponseError
from emergent_rpg.providers.openai_compatible import (
    OpenAICompatibleActionParser,
    OpenAICompatibleConfig,
)
from emergent_rpg.providers.scripted import DeterministicActionParser, FallbackActionParser
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


def _parser(content: str) -> tuple[OpenAICompatibleActionParser, RecordingTransport]:
    transport = RecordingTransport(content)
    parser = OpenAICompatibleActionParser(
        OpenAICompatibleConfig(base_url="http://localhost:11434/v1", model="local-model"),
        transport=transport,
    )
    return parser, transport


def test_action_parser_receives_only_visible_interaction_surface() -> None:
    state = build_demo_world()
    parser, transport = _parser('{"kind":"move","destination":"operations"}')

    action = parser.parse("Let's head over to operations.", state)

    assert action == MoveAction(destination="operations")
    assert transport.payload is not None
    wire = json.dumps(transport.payload, sort_keys=True)
    assert state.locations[state.player().state.current_location].name in wire
    assert "Let's head over to operations." in wire
    for fact in state.facts.values():
        assert fact.proposition not in wire
    for entity in state.entities.values():
        knowledge = getattr(entity, "knowledge", None)
        if knowledge is not None:
            for belief in knowledge.beliefs.values():
                assert belief not in wire


def test_action_parser_rejects_extra_model_fields() -> None:
    state = build_demo_world()
    parser, _ = _parser('{"kind":"wait","minutes":1,"damage":999}')

    with pytest.raises(ProviderResponseError, match="invalid action JSON"):
        parser.parse("wait a moment", state)


def test_action_parser_accepts_common_json_code_fence() -> None:
    state = build_demo_world()
    parser, _ = _parser('```json\n{"kind":"move","destination":"operations"}\n```')

    assert parser.parse("go to operations", state) == MoveAction(destination="operations")


def test_provider_parse_failure_uses_deterministic_fallback() -> None:
    state = build_demo_world()
    primary, _ = _parser("not-json")
    parser = FallbackActionParser(primary, DeterministicActionParser())

    assert parser.parse("move operations", state) == MoveAction(destination="operations")


def test_natural_language_action_flows_through_deterministic_resolver(tmp_path: Path) -> None:
    parser, _ = _parser('{"kind":"move","destination":"operations"}')
    engine = GameEngine(SQLiteStore(tmp_path / "game.db"), parser=parser)
    session = engine.new_session()

    result, _, state = engine.process_text(session.id, "Could you take me to operations?")

    assert result.accepted
    assert state.player().state.current_location == "operations"
    assert engine.replay_session(session.id) == state


def test_impossible_model_action_cannot_mutate_canonical_state(tmp_path: Path) -> None:
    parser, _ = _parser('{"kind":"move","destination":"moon"}')
    store = SQLiteStore(tmp_path / "game.db")
    engine = GameEngine(store, parser=parser)
    session = engine.new_session()
    before = store.load_state(session.id)

    result, _, after = engine.process_text(session.id, "Teleport me to the moon.")

    assert not result.accepted
    assert after == before
    assert store.load_state(session.id) == before
    assert store.load_events(session.id) == []
    turns = store.list_turns(session.id)
    assert len(turns) == 1
    assert not turns[0].accepted
