from __future__ import annotations

from emergent_rpg.domain.events import RelationshipChanged
from emergent_rpg.domain.models import DialogueRelationshipRule, NPC, WorldState


class DialogueRelationshipPolicy:
    @staticmethod
    def _listener_known_facts(state: WorldState, listener_id: str) -> set[str]:
        if listener_id == state.player_id:
            return state.player_known_facts
        listener = state.entities.get(listener_id)
        if isinstance(listener, NPC):
            return listener.knowledge.facts_known
        return set()

    @classmethod
    def eligible_rules(
        cls,
        state: WorldState,
        speaker_id: str,
        listener_id: str,
    ) -> list[DialogueRelationshipRule]:
        listener_facts = cls._listener_known_facts(state, listener_id)
        eligible = [
            rule
            for rule in state.dialogue_relationship_rules
            if rule.speaker_id == speaker_id
            and rule.listener_id == listener_id
            and (not rule.once or rule.id not in state.applied_dialogue_relationship_rule_ids)
            and rule.required_listener_fact_ids <= listener_facts
        ]
        return sorted(eligible, key=lambda rule: (-rule.priority, rule.id))

    @classmethod
    def next_rule(
        cls,
        state: WorldState,
        speaker_id: str,
        listener_id: str,
    ) -> DialogueRelationshipRule | None:
        eligible = cls.eligible_rules(state, speaker_id, listener_id)
        return eligible[0] if eligible else None

    @classmethod
    def validate_rule_event(
        cls,
        state: WorldState,
        event: RelationshipChanged,
    ) -> str | None:
        if event.rule_id is None:
            return None
        expected = cls.next_rule(state, event.source_id, event.target_id)
        if expected is None:
            return "no dialogue relationship rule is eligible"
        if expected.id != event.rule_id:
            return f"expected dialogue relationship rule {expected.id}"
        if event.delta != expected.delta:
            return "relationship delta does not match dialogue relationship rule"
        source = state.entities.get(event.source_id)
        listener = state.entities.get(event.target_id)
        if not isinstance(source, NPC) or listener is None:
            return "dialogue relationship participants are invalid"
        if not source.state.alive or not source.state.conscious:
            return "dialogue relationship source cannot interact"
        if not listener.state.alive or not listener.state.conscious:
            return "dialogue relationship listener cannot interact"
        if source.state.current_location != listener.state.current_location:
            return "dialogue relationship participants must be co-located"
        return None