from __future__ import annotations

import logging
import shlex

from emergent_rpg.domain.actions import (
    FreeformAction,
    GiveAction,
    InspectAction,
    MoveAction,
    PlayerAction,
    TakeAction,
    TalkAction,
    WaitAction,
)
from emergent_rpg.domain.models import WorldState
from emergent_rpg.engine.narrative import ScenePlan
from emergent_rpg.providers.base import ActionParser, MemorySummarizer, NarrativeGenerator
from emergent_rpg.providers.errors import ProviderError

logger = logging.getLogger(__name__)


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
        if command == "give" and len(parts) >= 4:
            separators = [index for index, token in enumerate(parts[1:], start=1) if token.casefold() == "to"]
            if separators:
                separator = separators[-1]
                item = " ".join(parts[1:separator]).strip()
                receiver = " ".join(parts[separator + 1 :]).strip()
                if item and receiver:
                    return GiveAction(item=item, receiver=receiver)
        if command == "wait":
            try:
                minutes = int(rest) if rest else 10
            except ValueError:
                minutes = 10
            return WaitAction(minutes=max(1, min(minutes, 24 * 60)))
        return FreeformAction(text=stripped)


class FallbackActionParser(ActionParser):
    def __init__(self, primary: ActionParser, fallback: ActionParser) -> None:
        self.primary = primary
        self.fallback = fallback

    def parse(self, text: str, state: WorldState) -> PlayerAction:
        try:
            return self.primary.parse(text, state)
        except ProviderError as exc:
            logger.warning("action parser provider failed; using deterministic fallback: %s", exc)
            return self.fallback.parse(text, state)


class StubActionParser(ActionParser):
    def __init__(self, action: PlayerAction) -> None:
        self.action = action

    def parse(self, text: str, state: WorldState) -> PlayerAction:
        del text, state
        return self.action


class ScriptedNarrativeGenerator(NarrativeGenerator):
    def generate(self, scene_plan: ScenePlan) -> str:
        if scene_plan.observations:
            return " ".join(scene_plan.observations)
        return "Nothing changes, but the moment passes."


class DeterministicMemorySummarizer(MemorySummarizer):
    def summarize(self, records: list[str]) -> str:
        return " | ".join(records)
