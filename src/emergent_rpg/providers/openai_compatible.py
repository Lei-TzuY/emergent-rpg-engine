from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Protocol, cast
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from pydantic import BaseModel, Field, field_validator

from emergent_rpg.engine.narrative import ScenePlan
from emergent_rpg.providers.base import NarrativeGenerator
from emergent_rpg.providers.errors import ProviderRequestError, ProviderResponseError

MAX_RESPONSE_BYTES = 1_000_000

NARRATION_SYSTEM_PROMPT = """You are a narrative renderer inside a persistent RPG engine.
The scene plan is authoritative and immutable. Narrate only what its accepted observations and
world events support. You may use only the explicitly allowed information. Never invent state
changes, inventory transfers, locations, injuries, knowledge, relationships, or time changes.
Never reveal or infer facts identified as forbidden. If the plan is sparse, stay concise instead
of filling gaps with new world facts. Return prose only.
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


class OpenAICompatibleNarrativeGenerator(NarrativeGenerator):
    def __init__(
        self,
        config: OpenAICompatibleConfig,
        transport: JsonTransport | None = None,
    ) -> None:
        self.config = config
        self.transport = transport or UrllibJsonTransport()

    def generate(self, scene_plan: ScenePlan) -> str:
        response = self.transport.post_json(
            f"{self.config.base_url}/chat/completions",
            self._headers(),
            self._payload(scene_plan),
            self.config.timeout_seconds,
        )
        return self._extract_text(response)

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "emergent-rpg-engine/0.1",
        }
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        return headers

    def _payload(self, scene_plan: ScenePlan) -> dict[str, object]:
        provider_scene: dict[str, object] = {
            "objective": scene_plan.objective,
            "participating_entities": scene_plan.participating_entities,
            "events_that_occurred": scene_plan.events_that_occurred,
            "allowed_information": scene_plan.information_allowed_to_be_revealed,
            "forbidden_fact_ids": scene_plan.information_forbidden_to_reveal,
            "observations": scene_plan.observations,
            "suggested_dramatic_beat": scene_plan.suggested_dramatic_beat,
        }
        return {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": NARRATION_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": json.dumps(provider_scene, ensure_ascii=False, sort_keys=True),
                },
            ],
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
        }

    @staticmethod
    def _extract_text(response: Mapping[str, object]) -> str:
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
