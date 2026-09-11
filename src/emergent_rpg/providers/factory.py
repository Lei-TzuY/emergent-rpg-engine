from __future__ import annotations

import os
from collections.abc import Mapping
from enum import StrEnum

from pydantic import ValidationError

from emergent_rpg.providers.base import ActionParser, NarrativeGenerator
from emergent_rpg.providers.control import ProviderRuntimeControls, ProviderStage, StageBudget
from emergent_rpg.providers.errors import ProviderConfigurationError
from emergent_rpg.providers.openai_compatible import (
    JsonTransport,
    OpenAICompatibleActionParser,
    OpenAICompatibleConfig,
    OpenAICompatibleNarrativeGenerator,
)
from emergent_rpg.providers.scripted import (
    DeterministicActionParser,
    FallbackActionParser,
    ScriptedNarrativeGenerator,
)


class NarrativeProviderName(StrEnum):
    SCRIPTED = "scripted"
    OPENAI_COMPATIBLE = "openai-compatible"
    OLLAMA = "ollama"


class ActionParserName(StrEnum):
    DETERMINISTIC = "deterministic"
    OPENAI_COMPATIBLE = "openai-compatible"
    OLLAMA = "ollama"


def build_narrative_generator(
    name: NarrativeProviderName | str,
    env: Mapping[str, str] | None = None,
    transport: JsonTransport | None = None,
    controls: ProviderRuntimeControls | None = None,
) -> NarrativeGenerator:
    try:
        provider = NarrativeProviderName(name)
    except ValueError as exc:
        raise ProviderConfigurationError(f"unknown narrative provider: {name}") from exc

    if provider is NarrativeProviderName.SCRIPTED:
        return ScriptedNarrativeGenerator()
    config = (
        _ollama_config(env, ProviderStage.NARRATION)
        if provider is NarrativeProviderName.OLLAMA
        else _provider_config(env, ProviderStage.NARRATION)
    )
    runtime_controls = controls or build_provider_controls(env)
    return OpenAICompatibleNarrativeGenerator(
        config,
        transport=transport,
        controls=runtime_controls,
    )


def build_action_parser(
    name: ActionParserName | str,
    env: Mapping[str, str] | None = None,
    transport: JsonTransport | None = None,
    controls: ProviderRuntimeControls | None = None,
) -> ActionParser:
    try:
        parser_name = ActionParserName(name)
    except ValueError as exc:
        raise ProviderConfigurationError(f"unknown action parser: {name}") from exc

    deterministic = DeterministicActionParser()
    if parser_name is ActionParserName.DETERMINISTIC:
        return deterministic

    config = (
        _ollama_config(env, ProviderStage.ACTION_PARSER)
        if parser_name is ActionParserName.OLLAMA
        else _provider_config(env, ProviderStage.ACTION_PARSER)
    )
    runtime_controls = controls or build_provider_controls(env)
    primary = OpenAICompatibleActionParser(
        config,
        transport=transport,
        controls=runtime_controls,
    )
    return FallbackActionParser(primary, deterministic)


def build_provider_controls(
    env: Mapping[str, str] | None = None,
) -> ProviderRuntimeControls:
    source = os.environ if env is None else env
    budgets = {
        ProviderStage.ACTION_PARSER: StageBudget(
            max_requests=_read_non_negative_int(
                source,
                "EMERGENT_RPG_ACTION_BUDGET_REQUESTS",
                10_000,
            ),
            max_reserved_tokens=_read_non_negative_int(
                source,
                "EMERGENT_RPG_ACTION_BUDGET_RESERVED_TOKENS",
                2_000_000,
            ),
        ),
        ProviderStage.NARRATION: StageBudget(
            max_requests=_read_non_negative_int(
                source,
                "EMERGENT_RPG_NARRATION_BUDGET_REQUESTS",
                10_000,
            ),
            max_reserved_tokens=_read_non_negative_int(
                source,
                "EMERGENT_RPG_NARRATION_BUDGET_RESERVED_TOKENS",
                5_000_000,
            ),
        ),
    }
    cache_entries = _read_non_negative_int(source, "EMERGENT_RPG_LLM_CACHE_ENTRIES", 256)
    return ProviderRuntimeControls(budgets, cache_entries=cache_entries)


def _ollama_config(
    env: Mapping[str, str] | None,
    stage: ProviderStage,
) -> OpenAICompatibleConfig:
    source = os.environ if env is None else env
    prefix = _stage_prefix(stage, "OLLAMA")
    model = _stage_value(source, prefix, "MODEL", "EMERGENT_RPG_OLLAMA_MODEL")
    if not model:
        raise ProviderConfigurationError(
            f"{prefix}_MODEL or EMERGENT_RPG_OLLAMA_MODEL is required"
        )
    base_url = _stage_value(
        source,
        prefix,
        "BASE_URL",
        "EMERGENT_RPG_OLLAMA_BASE_URL",
        "http://127.0.0.1:11434/v1",
    )
    api_key = _stage_value(
        source,
        prefix,
        "API_KEY",
        "EMERGENT_RPG_OLLAMA_API_KEY",
    )

    try:
        return OpenAICompatibleConfig(
            base_url=base_url,
            model=model,
            api_key=api_key or None,
            timeout_seconds=_stage_float(
                source,
                prefix,
                "TIMEOUT",
                "EMERGENT_RPG_OLLAMA_TIMEOUT",
                30.0,
            ),
            temperature=_stage_float(
                source,
                prefix,
                "TEMPERATURE",
                "EMERGENT_RPG_OLLAMA_TEMPERATURE",
                0.7,
            ),
            max_tokens=_stage_int(
                source,
                prefix,
                "MAX_TOKENS",
                "EMERGENT_RPG_OLLAMA_MAX_TOKENS",
                500,
            ),
        )
    except ValidationError as exc:
        raise ProviderConfigurationError(f"invalid Ollama configuration: {exc}") from exc


def _provider_config(
    env: Mapping[str, str] | None,
    stage: ProviderStage,
) -> OpenAICompatibleConfig:
    source = os.environ if env is None else env
    prefix = _stage_prefix(stage, "LLM")
    base_url = _stage_value(source, prefix, "BASE_URL", "EMERGENT_RPG_LLM_BASE_URL")
    model = _stage_value(source, prefix, "MODEL", "EMERGENT_RPG_LLM_MODEL")
    if not base_url:
        raise ProviderConfigurationError(
            f"{prefix}_BASE_URL or EMERGENT_RPG_LLM_BASE_URL is required"
        )
    if not model:
        raise ProviderConfigurationError(f"{prefix}_MODEL or EMERGENT_RPG_LLM_MODEL is required")

    try:
        return OpenAICompatibleConfig(
            base_url=base_url,
            model=model,
            api_key=_stage_value(
                source,
                prefix,
                "API_KEY",
                "EMERGENT_RPG_LLM_API_KEY",
            )
            or None,
            timeout_seconds=_stage_float(
                source,
                prefix,
                "TIMEOUT",
                "EMERGENT_RPG_LLM_TIMEOUT",
                30.0,
            ),
            temperature=_stage_float(
                source,
                prefix,
                "TEMPERATURE",
                "EMERGENT_RPG_LLM_TEMPERATURE",
                0.7,
            ),
            max_tokens=_stage_int(
                source,
                prefix,
                "MAX_TOKENS",
                "EMERGENT_RPG_LLM_MAX_TOKENS",
                500,
            ),
        )
    except ValidationError as exc:
        raise ProviderConfigurationError(f"invalid provider configuration: {exc}") from exc


def _stage_prefix(stage: ProviderStage, namespace: str) -> str:
    stage_name = "ACTION" if stage is ProviderStage.ACTION_PARSER else "NARRATION"
    return f"EMERGENT_RPG_{stage_name}_{namespace}"


def _stage_value(
    source: Mapping[str, str],
    prefix: str,
    suffix: str,
    generic_key: str,
    default: str = "",
) -> str:
    stage_value = source.get(f"{prefix}_{suffix}")
    if stage_value is not None and stage_value.strip():
        return stage_value.strip()
    generic_value = source.get(generic_key)
    if generic_value is not None and generic_value.strip():
        return generic_value.strip()
    return default


def _stage_float(
    source: Mapping[str, str],
    prefix: str,
    suffix: str,
    generic_key: str,
    default: float,
) -> float:
    key = f"{prefix}_{suffix}"
    raw = source.get(key)
    if raw is None or not raw.strip():
        key = generic_key
        raw = source.get(generic_key)
    return _parse_float(raw, key, default)


def _stage_int(
    source: Mapping[str, str],
    prefix: str,
    suffix: str,
    generic_key: str,
    default: int,
) -> int:
    key = f"{prefix}_{suffix}"
    raw = source.get(key)
    if raw is None or not raw.strip():
        key = generic_key
        raw = source.get(generic_key)
    return _parse_int(raw, key, default)


def _parse_float(raw: str | None, key: str, default: float) -> float:
    if raw is None or not raw.strip():
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ProviderConfigurationError(f"{key} must be a number") from exc


def _parse_int(raw: str | None, key: str, default: int) -> int:
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ProviderConfigurationError(f"{key} must be an integer") from exc


def _read_non_negative_int(source: Mapping[str, str], key: str, default: int) -> int:
    value = _parse_int(source.get(key), key, default)
    if value < 0:
        raise ProviderConfigurationError(f"{key} must be non-negative")
    return value
