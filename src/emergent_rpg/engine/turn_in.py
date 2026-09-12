from __future__ import annotations

from emergent_rpg.domain.events import RelationshipChanged
from emergent_rpg.domain.models import NPC, ItemTurnInConsequenceRule, WorldState


class ItemTurnInConsequencePolicy:
    @staticmethod
    def _rule_by_id(state: WorldState, rule_id: str) -> ItemTurnInConsequenceRule | None:
        return next(
            (rule for rule in state.item_turn_in_consequence_rules if rule.id == rule_id),
            None,
        )

    @classmethod
    def eligible_rules(
        cls,
        state: WorldState,
        receiver_npc_id: str,
        item_id: str,
        *,
        completed_goal_ids: set[str] | None = None,
    ) -> list[ItemTurnInConsequenceRule]:
        receiver = state.entities.get(receiver_npc_id)
        if not isinstance(receiver, NPC):
            return []
        completed = completed_goal_ids or set()
        eligible = [
            rule
            for rule in state.item_turn_in_consequence_rules
            if rule.receiver_npc_id == receiver_npc_id
            and rule.item_id == item_id
            and rule.id not in state.applied_item_turn_in_consequence_rule_ids
            and (rule.required_goal_id is None or rule.required_goal_id in completed)
            and rule.required_player_fact_ids <= state.player_known_facts
            and rule.required_receiver_fact_ids <= receiver.knowledge.facts_known
        ]
        return sorted(eligible, key=lambda rule: (-rule.priority, rule.id))

    @classmethod
    def next_rule(
        cls,
        state: WorldState,
        receiver_npc_id: str,
        item_id: str,
        *,
        completed_goal_ids: set[str] | None = None,
    ) -> ItemTurnInConsequenceRule | None:
        eligible = cls.eligible_rules(
            state,
            receiver_npc_id,
            item_id,
            completed_goal_ids=completed_goal_ids,
        )
        return eligible[0] if eligible else None

    @classmethod
    def validate_relationship_event(
        cls,
        state: WorldState,
        event: RelationshipChanged,
    ) -> str | None:
        if event.rule_id is None:
            return "item turn-in relationship event requires rule provenance"
        rule = cls._rule_by_id(state, event.rule_id)
        if rule is None:
            return "item turn-in consequence rule does not exist"
        if rule.id in state.applied_item_turn_in_consequence_rule_ids:
            return "item turn-in consequence rule is already applied"
        if event.source_id != rule.receiver_npc_id or event.target_id != state.player_id:
            return "item turn-in relationship participants do not match rule"
        if event.delta != rule.relationship_delta:
            return "relationship delta does not match item turn-in rule"

        player = state.player()
        receiver = state.entities.get(rule.receiver_npc_id)
        item = state.items.get(rule.item_id)
        if not isinstance(receiver, NPC) or item is None:
            return "item turn-in consequence rule references invalid canonical state"
        if not player.state.alive or not player.state.conscious:
            return "player cannot complete an item turn-in"
        if not receiver.state.alive or not receiver.state.conscious:
            return "item turn-in receiver cannot interact"
        if player.state.current_location != receiver.state.current_location:
            return "item turn-in participants must be co-located"
        if item.owner_id != receiver.id or item.id not in receiver.state.inventory:
            return "item turn-in reward requires completed receiver custody"
        if not rule.required_player_fact_ids <= state.player_known_facts:
            return "player lacks item turn-in rule prerequisites"
        if not rule.required_receiver_fact_ids <= receiver.knowledge.facts_known:
            return "receiver lacks item turn-in rule prerequisites"
        if rule.required_goal_id is not None and rule.required_goal_id not in receiver.completed_goal_ids:
            return "required item turn-in goal is not complete"
        return None
