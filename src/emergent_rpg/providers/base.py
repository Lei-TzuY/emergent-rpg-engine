from __future__ import annotations

from abc import ABC, abstractmethod

from emergent_rpg.domain.actions import PlayerAction
from emergent_rpg.domain.models import WorldState


class ActionParser(ABC):
    @abstractmethod
    def parse(self, text: str, state: WorldState) -> PlayerAction: ...


class NarrativePlanner(ABC):
    @abstractmethod
    def plan(self, state: WorldState, action: PlayerAction, result: object) -> object: ...


class NarrativeGenerator(ABC):
    @abstractmethod
    def generate(self, scene_plan: object) -> str: ...


class MemorySummarizer(ABC):
    @abstractmethod
    def summarize(self, records: list[str]) -> str: ...
