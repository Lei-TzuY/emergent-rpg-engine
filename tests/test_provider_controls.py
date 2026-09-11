from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import pytest

from emergent_rpg.domain.actions import TakeAction
from emergent_rpg.engine.narrative import ScenePlan
from emergent_rpg.engine.service import GameEngine
from emergent_rpg.persistence.db import SQLiteStore
from emergent_rpg.providers.control import (
    ProviderRuntimeControls,
    ProviderStage,
    StageBudget,
)
from emergent_rpg.providers.errors import ProviderBudgetExceeded
from emergent_rpg.providers.factory import (
    ActionParserName,
    NarrativeProviderName,
    build_action_parser,
    build_narrative_generator,
)
from emergent_rpg.providers.openai_compatible import (
    OpenAICompatibleClient,
    OpenAICompatibleConfig,
    OpenAICompatibleNarrativeGenerator,
)
from emergent_rpg.world.demo import build_demo_world


class RecordingTransport:
    def __init__(self, content: str = "Grounded narration.") -> None:
        self.content = content
        self.calls = 0
        self.payloads: list[dict[str, object]] = []

    def post_json(
        self,
        url: str,
        headers: Mapping[str, str],
        payload: Mapping[str, object],
        timeout: float,
    ) -> dict[str, object]:
        del url, headers, timeout
        self.calls += 1
        self.payloads.append(dict(payload))
        return {"choices": [{"message": {"content": self.content}}]}


def _budgets(
    *,
    action_requests: int = 10,
    action_tokens: int = 10_000,
    narration_requests: int = 10,
    narration_tokens: int = 10_000,
) -> dict[ProviderStage, StageBudget]:
    return {
        ProviderStage.ACTION_PARSER: StageBudget(action_requests, action_tokens),
        ProviderStage.NARRATION: StageBudget(narration_requests, narration_tokens),
    }


def _plan() -> ScenePlan:
    return ScenePlan(
        objective="Render a bounded scene",
        participating_entities=["player"],
        events_that_occurred=["time_advanced"],
        information_allowed_to_be_revealed=["The relay is quiet."],
        information_forbidden_to_reveal=["fact_hidden"],
        observations=["The relay is quiet."],
    )


def _config(model: str = "model-a", api_key: str | None = None) -> OpenAICompatibleConfig:
    return OpenAICompatibleConfig(
        base_url="http://provider.invalid/v1",
        model=model,
        api_key=api_key,
        max_tokens=500,
    )


def test_repeated_completion_hits_cache_without_spending_more_budget() -> None:
    controls = ProviderRuntimeControls(_budgets(), cache_entries=4)
    transport = RecordingTransport()
    generator = OpenAICompatibleNarrativeGenerator(
        _config(),
        transport=transport,
        controls=controls,
    )

    first = generator.generate(_plan())
    second = generator.generate(_plan())

    assert first == second == "Grounded narration."
    assert transport.calls == 1
    snapshot = controls.ledger.snapshot(ProviderStage.NARRATION)
    assert snapshot.requests_used == 1
    assert snapshot.reserved_tokens == 500
    assert len(controls.cache) == 1


def test_cache_key_isolated_across_stage_model_and_credential_scope() -> None:
    controls = ProviderRuntimeControls(_budgets(), cache_entries=8)
    transport = RecordingTransport("same text")
    first = OpenAICompatibleClient(_config("model-a", "key-a"), transport, controls)
    second = OpenAICompatibleClient(_config("model-b", "key-a"), transport, controls)
    third = OpenAICompatibleClient(_config("model-a", "key-b"), transport, controls)
    payload = {"input": "same"}

    assert first.complete("same", payload, stage=ProviderStage.NARRATION) == "same text"
    assert first.complete("same", payload, stage=ProviderStage.ACTION_PARSER) == "same text"
    assert second.complete("same", payload, stage=ProviderStage.NARRATION) == "same text"
    assert third.complete("same", payload, stage=ProviderStage.NARRATION) == "same text"
    assert first.complete("same", payload, stage=ProviderStage.NARRATION) == "same text"

    assert transport.calls == 4
    assert len(controls.cache) == 4


def test_stage_specific_model_routes_override_generic_provider_model() -> None:
    narration_transport = RecordingTransport()
    generator = build_narrative_generator(
        NarrativeProviderName.OPENAI_COMPATIBLE,
        env={
            "EMERGENT_RPG_LLM_BASE_URL": "http://provider.invalid/v1",
            "EMERGENT_RPG_LLM_MODEL": "generic-model",
            "EMERGENT_RPG_NARRATION_LLM_MODEL": "narration-model",
        },
        transport=narration_transport,
    )
    generator.generate(_plan())
    assert narration_transport.payloads[-1]["model"] == "narration-model"

    action_transport = RecordingTransport('{"kind":"wait","minutes":1}')
    parser = build_action_parser(
        ActionParserName.OPENAI_COMPATIBLE,
        env={
            "EMERGENT_RPG_LLM_BASE_URL": "http://provider.invalid/v1",
            "EMERGENT_RPG_LLM_MODEL": "generic-model",
            "EMERGENT_RPG_ACTION_LLM_MODEL": "parser-model",
        },
        transport=action_transport,
    )
    action = parser.parse("pause briefly", build_demo_world())
    assert action.kind == "wait"
    assert action_transport.payloads[-1]["model"] == "parser-model"


def test_reserved_output_token_budget_blocks_request_before_transport() -> None:
    controls = ProviderRuntimeControls(
        _budgets(narration_requests=3, narration_tokens=499),
        cache_entries=4,
    )
    transport = RecordingTransport()
    generator = OpenAICompatibleNarrativeGenerator(
        _config(),
        transport=transport,
        controls=controls,
    )

    with pytest.raises(ProviderBudgetExceeded, match="reserved-output-token"):
        generator.generate(_plan())

    assert transport.calls == 0
    snapshot = controls.ledger.snapshot(ProviderStage.NARRATION)
    assert snapshot.requests_used == 0
    assert snapshot.reserved_tokens == 0


def test_action_parser_budget_exhaustion_uses_deterministic_fallback() -> None:
    controls = ProviderRuntimeControls(
        _budgets(action_requests=0),
        cache_entries=4,
    )
    transport = RecordingTransport('{"kind":"move","destination":"moon"}')
    parser = build_action_parser(
        ActionParserName.OPENAI_COMPATIBLE,
        env={
            "EMERGENT_RPG_LLM_BASE_URL": "http://provider.invalid/v1",
            "EMERGENT_RPG_LLM_MODEL": "parser-model",
        },
        transport=transport,
        controls=controls,
    )

    action = parser.parse("take brass key", build_demo_world())

    assert isinstance(action, TakeAction)
    assert transport.calls == 0


def test_narration_budget_exhaustion_keeps_turn_transaction_atomic(tmp_path: Path) -> None:
    controls = ProviderRuntimeControls(
        _budgets(narration_requests=0),
        cache_entries=4,
    )
    transport = RecordingTransport()
    generator = OpenAICompatibleNarrativeGenerator(
        _config(),
        transport=transport,
        controls=controls,
    )
    store = SQLiteStore(tmp_path / "budget.db")
    engine = GameEngine(store, generator=generator)
    session = engine.new_session()
    before = store.load_state(session.id)

    with pytest.raises(ProviderBudgetExceeded, match="request budget exhausted"):
        engine.execute_action(session.id, TakeAction(target="brass key"), "take brass key")

    assert transport.calls == 0
    assert store.load_state(session.id) == before
    assert store.load_events(session.id) == []
    assert store.list_turns(session.id) == []


def test_cache_is_bounded_lru() -> None:
    controls = ProviderRuntimeControls(_budgets(), cache_entries=2)
    transport = RecordingTransport()
    client = OpenAICompatibleClient(_config(), transport, controls)

    for value in ("one", "two", "three"):
        client.complete(
            "prompt",
            {"value": value},
            stage=ProviderStage.NARRATION,
            max_tokens=10,
        )

    assert transport.calls == 3
    assert len(controls.cache) == 2
