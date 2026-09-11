from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

import pytest

from emergent_rpg.domain.actions import TakeAction, TalkAction
from emergent_rpg.domain.events import TimeAdvanced
from emergent_rpg.engine.narrative import DeterministicNarrativePlanner, ScenePlan
from emergent_rpg.engine.reducer import apply_event
from emergent_rpg.engine.resolver import ActionResult
from emergent_rpg.engine.service import GameEngine
from emergent_rpg.persistence.db import SQLiteStore
from emergent_rpg.providers.base import NarrativeGenerator
from emergent_rpg.providers.errors import (
    ProviderConfigurationError,
    ProviderRequestError,
    ProviderResponseError,
)
from emergent_rpg.providers.factory import NarrativeProviderName, build_narrative_generator
from emergent_rpg.providers.openai_compatible import (
    OpenAICompatibleConfig,
    OpenAICompatibleNarrativeGenerator,
)
from emergent_rpg.world.demo import build_demo_world


class RecordingTransport:
    def __init__(self, response: dict[str, object]) -> None:
        self.response = response
        self.url: str | None = None
        self.headers: dict[str, str] | None = None
        self.payload: dict[str, object] | None = None
        self.timeout: float | None = None

    def post_json(
        self,
        url: str,
        headers: Mapping[str, str],
        payload: Mapping[str, object],
        timeout: float,
    ) -> dict[str, object]:
        self.url = url
        self.headers = dict(headers)
        self.payload = dict(payload)
        self.timeout = timeout
        return self.response


class FailingNarrativeGenerator(NarrativeGenerator):
    def generate(self, scene_plan: ScenePlan) -> str:
        del scene_plan
        raise ProviderRequestError("simulated outage")


def _plan() -> ScenePlan:
    return ScenePlan(
        objective="Render an accepted inspection",
        participating_entities=["player"],
        events_that_occurred=["time_advanced"],
        information_allowed_to_be_revealed=["The console is dark."],
        information_forbidden_to_reveal=["fact_hidden_switch"],
        observations=["The console is dark."],
    )


def test_openai_compatible_generator_builds_constrained_request() -> None:
    transport = RecordingTransport(
        {"choices": [{"message": {"content": "The console sits dark beneath your hand."}}]}
    )
    generator = OpenAICompatibleNarrativeGenerator(
        OpenAICompatibleConfig(
            base_url="http://localhost:11434/v1/",
            model="local-model",
            api_key="test-token",
            temperature=0.2,
            max_tokens=120,
        ),
        transport=transport,
    )

    narration = generator.generate(_plan())

    assert narration == "The console sits dark beneath your hand."
    assert transport.url == "http://localhost:11434/v1/chat/completions"
    assert transport.headers is not None
    assert transport.headers["Authorization"] == "Bearer test-token"
    assert transport.payload is not None
    wire = json.dumps(transport.payload, sort_keys=True)
    assert "The console is dark." in wire
    assert "fact_hidden_switch" in wire
    assert "Never invent state" in wire


def test_openai_compatible_generator_rejects_malformed_response() -> None:
    generator = OpenAICompatibleNarrativeGenerator(
        OpenAICompatibleConfig(base_url="http://localhost:9999/v1", model="test"),
        transport=RecordingTransport({"choices": []}),
    )
    with pytest.raises(ProviderResponseError, match="no choices"):
        generator.generate(_plan())


def test_provider_factory_requires_explicit_endpoint_and_model() -> None:
    with pytest.raises(ProviderConfigurationError, match="BASE_URL"):
        build_narrative_generator(NarrativeProviderName.OPENAI_COMPATIBLE, env={})

    transport = RecordingTransport(
        {"choices": [{"message": {"content": "A grounded line."}}]}
    )
    generator = build_narrative_generator(
        NarrativeProviderName.OPENAI_COMPATIBLE,
        env={
            "EMERGENT_RPG_LLM_BASE_URL": "http://127.0.0.1:11434/v1",
            "EMERGENT_RPG_LLM_MODEL": "qwen-local",
            "EMERGENT_RPG_LLM_MAX_TOKENS": "250",
        },
        transport=transport,
    )
    assert isinstance(generator, OpenAICompatibleNarrativeGenerator)
    assert generator.config.max_tokens == 250


def test_npc_participation_does_not_grant_player_secret_knowledge() -> None:
    before = build_demo_world()
    event = TimeAdvanced(turn_number=1, minutes=1)
    after = apply_event(before, event)
    result = ActionResult(
        accepted=True,
        emitted_events=[event],
        observations=["Lio watches you without volunteering an explanation."],
        involved_entities={"player", "npc_lio"},
        tags={"dialogue"},
    )

    plan = DeterministicNarrativePlanner().plan(
        before,
        after,
        TalkAction(target="Lio Marr"),
        result,
    )

    hidden = before.facts["fact_generator_stable"].proposition
    assert hidden not in plan.relevant_facts
    assert hidden not in plan.information_allowed_to_be_revealed
    assert "fact_generator_stable" in plan.information_forbidden_to_reveal


def test_provider_failure_is_transactionally_atomic(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "game.db")
    engine = GameEngine(store, generator=FailingNarrativeGenerator())
    session = engine.new_session()
    before = store.load_state(session.id)

    with pytest.raises(ProviderRequestError, match="simulated outage"):
        engine.execute_action(
            session.id,
            TakeAction(target="brass key"),
            "take brass key",
        )

    assert store.load_state(session.id) == before
    assert store.load_events(session.id) == []
    assert store.list_turns(session.id) == []


def test_ollama_provider_uses_local_defaults_without_generic_credentials() -> None:
    transport = RecordingTransport(
        {"choices": [{"message": {"content": "A local grounded line."}}]}
    )
    generator = build_narrative_generator(
        NarrativeProviderName.OLLAMA,
        env={
            "EMERGENT_RPG_OLLAMA_MODEL": "qwen-local:latest",
            "EMERGENT_RPG_LLM_API_KEY": "must-not-leak",
        },
        transport=transport,
    )

    assert generator.generate(_plan()) == "A local grounded line."
    assert transport.url == "http://127.0.0.1:11434/v1/chat/completions"
    assert transport.headers is not None
    assert "Authorization" not in transport.headers
    assert transport.payload is not None
    assert transport.payload["model"] == "qwen-local:latest"


def test_ollama_provider_supports_namespaced_overrides() -> None:
    transport = RecordingTransport(
        {"choices": [{"message": {"content": "Local override works."}}]}
    )
    generator = build_narrative_generator(
        NarrativeProviderName.OLLAMA,
        env={
            "EMERGENT_RPG_OLLAMA_MODEL": "local-model",
            "EMERGENT_RPG_OLLAMA_BASE_URL": "http://localhost:22434/v1/",
            "EMERGENT_RPG_OLLAMA_API_KEY": "local-proxy-token",
            "EMERGENT_RPG_OLLAMA_TIMEOUT": "12",
            "EMERGENT_RPG_OLLAMA_MAX_TOKENS": "321",
        },
        transport=transport,
    )

    generator.generate(_plan())
    assert transport.url == "http://localhost:22434/v1/chat/completions"
    assert transport.headers is not None
    assert transport.headers["Authorization"] == "Bearer local-proxy-token"
    assert transport.timeout == 12.0
    assert transport.payload is not None
    assert transport.payload["max_tokens"] == 321


def test_ollama_provider_requires_only_explicit_model() -> None:
    with pytest.raises(ProviderConfigurationError, match="OLLAMA_MODEL"):
        build_narrative_generator(NarrativeProviderName.OLLAMA, env={})
