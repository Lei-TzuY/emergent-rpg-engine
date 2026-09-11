from __future__ import annotations

import shlex

from emergent_rpg.domain.actions import (
    FreeformAction,
    InspectAction,
    MoveAction,
    PlayerAction,
    TakeAction,
    TalkAction,
    WaitAction,
)
from emergent_rpg.domain.models import WorldState
from emergent_rpg.providers.base import ActionParser, MemorySummarizer, NarrativeGenerator


class DeterministicActionParser(ActionParser):
    def parse(self, text: str, state: WorldState) -> PlayerAction:
        del state
        stripped = text.strip()
        if not stripped:
            return FreeformAction(text="")
        try:
            parts = shlex.split(stripped)
        except ValueError:
            parts = stripped.split()
        command = parts[0].casefold()
        rest = " ".join(parts[1:]).strip()
        if command in {"move", "go", "walk"} and rest:
            return MoveAction(destination=rest)
        if command in {"inspect", "look", "examine"} and rest:
            return InspectAction(target=rest)
        if command in {"talk", "speak"} and rest:
            return TalkAction(target=rest)
        if command in {"take", "get", "pick"} and rest:
            return TakeAction(target=rest)
        if command == "wait":
            try:
                minutes = int(rest) if rest else 10
            except ValueError:
                minutes = 10
            return WaitAction(minutes=max(1, min(minutes, 24 * 60)))
        return FreeformAction(text=stripped)


class StubActionParser(ActionParser):
    def __init__(self, action: PlayerAction) -> None:
        self.action = action

    def parse(self, text: str, state: WorldState) -> PlayerAction:
        del text, state
        return self.action


class ScriptedNarrativeGenerator(NarrativeGenerator):
    def generate(self, scene_plan: object) -> str:
        from emergent_rpg.engine.narrative import ScenePlan

        if not isinstance(scene_plan, ScenePlan):
            raise TypeError("ScriptedNarrativeGenerator requires ScenePlan")
        if scene_plan.observations:
            return " ".join(scene_plan.observations)
        return "Nothing changes, but the moment passes."


class DeterministicMemorySummarizer(MemorySummarizer):
    def summarize(self, records: list[str]) -> str:
        return " | ".join(records)
