from __future__ import annotations

from emergent_rpg.domain.actions import MoveAction, TakeAction, TalkAction
from emergent_rpg.engine.resolver import DeterministicResolver
from emergent_rpg.providers.scripted import DeterministicActionParser
from emergent_rpg.world.demo import build_demo_world


def test_parser_supports_required_commands() -> None:
    state = build_demo_world()
    parser = DeterministicActionParser()
    assert parser.parse("move ridge", state).kind == "move"
    assert parser.parse("inspect room", state).kind == "inspect"
    assert parser.parse("talk Lio Marr", state).kind == "talk"
    assert parser.parse("take brass key", state).kind == "take"
    assert parser.parse("wait 12", state).kind == "wait"
    assert parser.parse("I pry open the hatch", state).kind == "freeform"


def test_impossible_actions_are_structured_failures() -> None:
    state = build_demo_world()
    resolver = DeterministicResolver()
    assert not resolver.resolve(state, MoveAction(destination="moon")).accepted
    assert not resolver.resolve(state, TakeAction(target="charred fuse")).accepted
    assert not resolver.resolve(state, TalkAction(target="Arden Vale")).accepted
