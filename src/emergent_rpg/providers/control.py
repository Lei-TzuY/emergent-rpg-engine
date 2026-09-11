from __future__ import annotations

import hashlib
import json
from collections import OrderedDict
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from threading import Lock

from emergent_rpg.providers.errors import ProviderBudgetExceeded


class ProviderStage(StrEnum):
    ACTION_PARSER = "action-parser"
    NARRATION = "narration"


@dataclass(frozen=True, slots=True)
class StageBudget:
    max_requests: int
    max_reserved_tokens: int

    def __post_init__(self) -> None:
        if self.max_requests < 0:
            raise ValueError("max_requests must be non-negative")
        if self.max_reserved_tokens < 0:
            raise ValueError("max_reserved_tokens must be non-negative")


@dataclass(frozen=True, slots=True)
class BudgetSnapshot:
    max_requests: int
    max_reserved_tokens: int
    requests_used: int
    reserved_tokens: int


class BudgetLedger:
    def __init__(self, budgets: Mapping[ProviderStage, StageBudget]) -> None:
        self._budgets = dict(budgets)
        self._usage = {stage: (0, 0) for stage in self._budgets}
        self._lock = Lock()

    def reserve(self, stage: ProviderStage, reserved_tokens: int) -> None:
        if reserved_tokens < 0:
            raise ValueError("reserved_tokens must be non-negative")
        with self._lock:
            budget = self._budgets.get(stage)
            if budget is None:
                raise ValueError(f"no budget configured for {stage.value}")
            requests_used, tokens_used = self._usage[stage]
            if requests_used + 1 > budget.max_requests:
                raise ProviderBudgetExceeded(f"{stage.value} request budget exhausted")
            if tokens_used + reserved_tokens > budget.max_reserved_tokens:
                raise ProviderBudgetExceeded(
                    f"{stage.value} reserved-output-token budget exhausted"
                )
            self._usage[stage] = (requests_used + 1, tokens_used + reserved_tokens)

    def snapshot(self, stage: ProviderStage) -> BudgetSnapshot:
        with self._lock:
            budget = self._budgets.get(stage)
            if budget is None:
                raise ValueError(f"no budget configured for {stage.value}")
            requests_used, tokens_used = self._usage[stage]
            return BudgetSnapshot(
                max_requests=budget.max_requests,
                max_reserved_tokens=budget.max_reserved_tokens,
                requests_used=requests_used,
                reserved_tokens=tokens_used,
            )


class CompletionCache:
    def __init__(self, capacity: int) -> None:
        if capacity < 0:
            raise ValueError("cache capacity must be non-negative")
        self.capacity = capacity
        self._entries: OrderedDict[str, str] = OrderedDict()
        self._lock = Lock()

    def get(self, key: str) -> str | None:
        if self.capacity == 0:
            return None
        with self._lock:
            value = self._entries.get(key)
            if value is None:
                return None
            self._entries.move_to_end(key)
            return value

    def put(self, key: str, value: str) -> None:
        if self.capacity == 0:
            return
        with self._lock:
            self._entries[key] = value
            self._entries.move_to_end(key)
            while len(self._entries) > self.capacity:
                self._entries.popitem(last=False)

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)


class ProviderRuntimeControls:
    def __init__(
        self,
        budgets: Mapping[ProviderStage, StageBudget],
        cache_entries: int = 256,
    ) -> None:
        self.ledger = BudgetLedger(budgets)
        self.cache = CompletionCache(cache_entries)

    def cache_key(
        self,
        *,
        stage: ProviderStage,
        provider_identity: Mapping[str, object],
        system_prompt: str,
        user_payload: Mapping[str, object],
        temperature: float,
        max_tokens: int,
    ) -> str:
        material = {
            "stage": stage.value,
            "provider": dict(provider_identity),
            "system_prompt": system_prompt,
            "user_payload": dict(user_payload),
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        encoded = json.dumps(
            material,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()
