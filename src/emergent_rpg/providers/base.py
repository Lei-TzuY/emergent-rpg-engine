from __future__ import annotations

from abc import ABC, abstractmethod

from emergent_rpg.domain.actions import PlayerAction
from emergent_rpg.domain.models import WorldState
from emergent_rpg.engine.narrative import ScenePlan
from emergent_rpg.engine.resolver import ActionResult


class ActionParser(ABC):
    @abstractmethod
    def parse(self, text: str, state: WorldState) -> PlayerAction: ...


class NarrativePlanner(ABC):
    @abstractmethod
    def plan(
        self,
        state_before: WorldState,
        state_after: WorldState,
        action: PlayerAction,
        result: ActionResult,
    ) -> ScenePlan: ...


class NarrativeGenerator(ABC):
    @abstractmethod
    def generate(self, scene_plan: ScenePlan) -> str: ...


class MemorySummarizer(ABC):
    @abstractmethod
    def summarize(self, records: list[str]) -> str: ...
