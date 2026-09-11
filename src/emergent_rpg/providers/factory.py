from __future__ import annotations

import os
from collections.abc import Mapping
from enum import StrEnum

from pydantic import ValidationError

from emergent_rpg.providers.base import ActionParser, NarrativeGenerator
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


class ActionParserName(StrEnum):
    DETERMINISTIC = "deterministic"
    OPENAI_COMPATIBLE = "openai-compatible"


def build_narrative_generator(
    name: NarrativeProviderName | str,
    env: Mapping[str, str] | None = None,
    transport: JsonTransport | None = None,
) -> NarrativeGenerator:
    try:
        provider = NarrativeProviderName(name)
    except ValueError as exc:
        raise ProviderConfigurationError(f"unknown narrative provider: {name}") from exc

    if provider is NarrativeProviderName.SCRIPTED:
        return ScriptedNarrativeGenerator()
    return OpenAICompatibleNarrativeGenerator(_provider_config(env), transport=transport)


def build_action_parser(
    name: ActionParserName | str,
    env: Mapping[str, str] | None = None,
    transport: JsonTransport | None = None,
) -> ActionParser:
    try:
        parser_name = ActionParserName(name)
    except ValueError as exc:
        raise ProviderConfigurationError(f"unknown action parser: {name}") from exc

    deterministic = DeterministicActionParser()
    if parser_name is ActionParserName.DETERMINISTIC:
        return deterministic

    primary = OpenAICompatibleActionParser(_provider_config(env), transport=transport)
    return FallbackActionParser(primary, deterministic)


def _provider_config(env: Mapping[str, str] | None) -> OpenAICompatibleConfig:
    source = os.environ if env is None else env
    base_url = source.get("EMERGENT_RPG_LLM_BASE_URL", "").strip()
    model = source.get("EMERGENT_RPG_LLM_MODEL", "").strip()
    if not base_url:
        raise ProviderConfigurationError("EMERGENT_RPG_LLM_BASE_URL is required")
    if not model:
        raise ProviderConfigurationError("EMERGENT_RPG_LLM_MODEL is required")

    try:
        return OpenAICompatibleConfig(
            base_url=base_url,
            model=model,
            api_key=source.get("EMERGENT_RPG_LLM_API_KEY") or None,
            timeout_seconds=_read_float(source, "EMERGENT_RPG_LLM_TIMEOUT", 30.0),
            temperature=_read_float(source, "EMERGENT_RPG_LLM_TEMPERATURE", 0.7),
            max_tokens=_read_int(source, "EMERGENT_RPG_LLM_MAX_TOKENS", 500),
        )
    except ValidationError as exc:
        raise ProviderConfigurationError(f"invalid provider configuration: {exc}") from exc


def _read_float(source: Mapping[str, str], key: str, default: float) -> float:
    raw = source.get(key)
    if raw is None or not raw.strip():
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ProviderConfigurationError(f"{key} must be a number") from exc


def _read_int(source: Mapping[str, str], key: str, default: int) -> int:
    raw = source.get(key)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ProviderConfigurationError(f"{key} must be an integer") from exc
