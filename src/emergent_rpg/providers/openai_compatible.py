from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Protocol, cast
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from pydantic import BaseModel, Field, ValidationError, field_validator

from emergent_rpg.domain.actions import PlayerAction, parse_action
from emergent_rpg.domain.models import NPC, WorldState
from emergent_rpg.engine.environment import EnvironmentalRules
from emergent_rpg.engine.narrative import ScenePlan
from emergent_rpg.providers.base import ActionParser, NarrativeGenerator
from emergent_rpg.providers.control import ProviderRuntimeControls, ProviderStage
from emergent_rpg.providers.errors import ProviderRequestError, ProviderResponseError

MAX_RESPONSE_BYTES = 1_000_000

NARRATION_SYSTEM_PROMPT = """You are a narrative renderer inside a persistent RPG engine.
The scene plan is authoritative and immutable. Narrate only what its accepted observations and
world events support. You may use only the explicitly allowed information. Never invent state
changes, inventory transfers, locations, injuries, knowledge, relationships, or time changes.
Never reveal or infer facts identified as forbidden. If the plan is sparse, stay concise instead
of filling gaps with new world facts. Return prose only.
"""

ACTION_SYSTEM_PROMPT = """You are a constrained action parser for a persistent RPG engine.
Convert the player's text into exactly one JSON object and nothing else. You may choose only:
{"kind":"move","destination":"..."}
{"kind":"inspect","target":"..."}
{"kind":"talk","target":"..."}
{"kind":"take","target":"..."}
{"kind":"give","item":"...","receiver":"..."}
{"kind":"wait","minutes":10}
{"kind":"freeform","text":"..."}
Use only the visible interaction surface supplied by the engine. Never claim that an action is
possible; the deterministic resolver decides legality after parsing. Do not add extra fields.
"""


class OpenAICompatibleConfig(BaseModel):
    base_url: str
    model: str = Field(min_length=1)
    api_key: str | None = None
    timeout_seconds: float = Field(default=30.0, gt=0, le=300)
    temperature: float = Field(default=0.7, ge=0, le=2)
    max_tokens: int = Field(default=500, ge=1, le=8192)

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str) -> str:
        normalized = value.strip().rstrip("/")
        if not normalized.startswith(("http://", "https://")):
            raise ValueError("base_url must use http:// or https://")
        return normalized


class JsonTransport(Protocol):
    def post_json(
        self,
        url: str,
        headers: Mapping[str, str],
        payload: Mapping[str, object],
        timeout: float,
    ) -> dict[str, object]: ...


class UrllibJsonTransport:
    def post_json(
        self,
        url: str,
        headers: Mapping[str, str],
        payload: Mapping[str, object],
        timeout: float,
    ) -> dict[str, object]:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        request = Request(url, data=body, headers=dict(headers), method="POST")
        try:
            with urlopen(request, timeout=timeout) as response:
                raw = response.read(MAX_RESPONSE_BYTES + 1)
        except HTTPError as exc:
            raise ProviderRequestError(f"provider returned HTTP {exc.code}") from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise ProviderRequestError(f"provider request failed: {exc}") from exc

        if len(raw) > MAX_RESPONSE_BYTES:
            raise ProviderResponseError("provider response exceeded size limit")
        try:
            parsed: object = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ProviderResponseError("provider returned invalid JSON") from exc
        if not isinstance(parsed, dict):
            raise ProviderResponseError("provider response must be a JSON object")
        return cast(dict[str, object], parsed)


class OpenAICompatibleClient:
    def __init__(
        self,
        config: OpenAICompatibleConfig,
        transport: JsonTransport | None = None,
        controls: ProviderRuntimeControls | None = None,
    ) -> None:
        self.config = config
        self.transport = transport or UrllibJsonTransport()
        self.controls = controls

    def complete(
        self,
        system_prompt: str,
        user_payload: Mapping[str, object],
        *,
        stage: ProviderStage,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        effective_temperature = self.config.temperature if temperature is None else temperature
        effective_max_tokens = self.config.max_tokens if max_tokens is None else max_tokens
        cache_key: str | None = None
        if self.controls is not None:
            cache_key = self.controls.cache_key(
                stage=stage,
                provider_identity=self._cache_identity(),
                system_prompt=system_prompt,
                user_payload=user_payload,
                temperature=effective_temperature,
                max_tokens=effective_max_tokens,
            )
            cached = self.controls.cache.get(cache_key)
            if cached is not None:
                return cached
            self.controls.ledger.reserve(stage, effective_max_tokens)

        response = self.transport.post_json(
            f"{self.config.base_url}/chat/completions",
            self._headers(),
            {
                "model": self.config.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {
                        "role": "user",
                        "content": json.dumps(user_payload, ensure_ascii=False, sort_keys=True),
                    },
                ],
                "temperature": effective_temperature,
                "max_tokens": effective_max_tokens,
            },
            self.config.timeout_seconds,
        )
        text = _extract_message_text(response)
        if self.controls is not None and cache_key is not None:
            self.controls.cache.put(cache_key, text)
        return text

    def _cache_identity(self) -> dict[str, object]:
        credential_scope = None
        if self.config.api_key:
            credential_scope = hashlib.sha256(self.config.api_key.encode("utf-8")).hexdigest()
        return {
            "base_url": self.config.base_url,
            "model": self.config.model,
            "credential_scope": credential_scope,
        }

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "emergent-rpg-engine/0.1",
        }
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        return headers


class OpenAICompatibleNarrativeGenerator(NarrativeGenerator):
    def __init__(
        self,
        config: OpenAICompatibleConfig,
        transport: JsonTransport | None = None,
        controls: ProviderRuntimeControls | None = None,
    ) -> None:
        self.client = OpenAICompatibleClient(config, transport, controls)
        self.config = config

    def generate(self, scene_plan: ScenePlan) -> str:
        provider_scene: dict[str, object] = {
            "objective": scene_plan.objective,
            "participating_entities": scene_plan.participating_entities,
            "events_that_occurred": scene_plan.events_that_occurred,
            "allowed_information": scene_plan.information_allowed_to_be_revealed,
            "forbidden_fact_ids": scene_plan.information_forbidden_to_reveal,
            "observations": scene_plan.observations,
            "suggested_dramatic_beat": scene_plan.suggested_dramatic_beat,
        }
        return self.client.complete(
            NARRATION_SYSTEM_PROMPT,
            provider_scene,
            stage=ProviderStage.NARRATION,
        )


class OpenAICompatibleActionParser(ActionParser):
    def __init__(
        self,
        config: OpenAICompatibleConfig,
        transport: JsonTransport | None = None,
        controls: ProviderRuntimeControls | None = None,
    ) -> None:
        self.client = OpenAICompatibleClient(config, transport, controls)

    def parse(self, text: str, state: WorldState) -> PlayerAction:
        content = self.client.complete(
            ACTION_SYSTEM_PROMPT,
            {
                "player_text": text,
                "visible_state": _visible_action_surface(state),
            },
            stage=ProviderStage.ACTION_PARSER,
            temperature=0.0,
            max_tokens=200,
        )
        try:
            decoded: object = json.loads(_strip_code_fence(content))
            return parse_action(decoded)
        except (json.JSONDecodeError, ValidationError) as exc:
            raise ProviderResponseError("provider returned invalid action JSON") from exc


def _visible_action_surface(state: WorldState) -> dict[str, object]:
    player = state.player()
    location = state.locations[player.state.current_location]
    rules = EnvironmentalRules()
    visible_items = sorted(
        item.name for item in state.items.values() if item.location_id == location.id
    )
    visible_npcs = sorted(
        entity.name
        for entity in state.entities.values()
        if isinstance(entity, NPC)
        and entity.state.current_location == location.id
        and entity.state.alive
        and entity.state.conscious
    )
    accessible = rules.accessible_exits(state, location.id)
    exits = sorted(
        {exit_name for exit_name in accessible}
        | {state.locations[destination].name for destination in accessible.values()}
    )
    blocked_exits = [
        {
            "alias": alias,
            "destination": state.locations[destination].name,
            "blocked_by": rules.route_access(state, location.id, destination).condition_names,
        }
        for alias, destination in sorted(location.exits.items())
        if not rules.route_access(state, location.id, destination).allowed
    ]
    inventory = sorted(state.items[item_id].name for item_id in player.state.inventory)
    movement_blocked = any(status.incapacitating for status in player.state.status_conditions)
    return {
        "location": location.name,
        "exits": exits,
        "blocked_exits": blocked_exits,
        "visible_items": visible_items,
        "visible_npcs": visible_npcs,
        "inventory": inventory,
        "movement_blocked": movement_blocked,
    }


def _strip_code_fence(content: str) -> str:
    stripped = content.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()
    if len(lines) < 3 or lines[-1].strip() != "```":
        return stripped
    return "\n".join(lines[1:-1]).strip()


def _extract_message_text(response: Mapping[str, object]) -> str:
    choices_value = response.get("choices")
    if not isinstance(choices_value, list) or not choices_value:
        raise ProviderResponseError("provider response has no choices")
    choices = cast(list[object], choices_value)
    first = choices[0]
    if not isinstance(first, dict):
        raise ProviderResponseError("provider choice is not an object")
    choice = cast(dict[str, object], first)
    message_value = choice.get("message")
    if not isinstance(message_value, dict):
        raise ProviderResponseError("provider choice has no message object")
    message = cast(dict[str, object], message_value)
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise ProviderResponseError("provider message content is empty")
    return content.strip()
