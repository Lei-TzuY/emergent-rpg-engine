from __future__ import annotations

from emergent_rpg.domain.events import FactInferred
from emergent_rpg.domain.models import NPC, FactId, WorldState


class MysteryGraph:
    """Deterministic clue dependencies, inference, gates, and contradictions."""

    @staticmethod
    def known_facts(state: WorldState, observer_id: str) -> set[FactId]:
        if observer_id == state.player_id:
            return set(state.player_known_facts)
        observer = state.entities.get(observer_id)
        if not isinstance(observer, NPC):
            raise ValueError(f"observer {observer_id} is not a player or NPC")
        return set(observer.knowledge.facts_known)

    @classmethod
    def can_discover_fact(cls, state: WorldState, fact_id: FactId, observer_id: str) -> bool:
        fact = state.facts[fact_id]
        known = cls.known_facts(state, observer_id)
        return fact.discovery_prerequisites <= known

    @classmethod
    def infer_events(
        cls,
        state: WorldState,
        observer_id: str,
        turn_number: int,
    ) -> list[FactInferred]:
        known = cls.known_facts(state, observer_id)
        inferred: list[FactInferred] = []
        while True:
            progress = False
            for rule_id in sorted(state.inference_rules):
                rule = state.inference_rules[rule_id]
                if rule.conclusion in known or not rule.premises <= known:
                    continue
                inferred.append(
                    FactInferred(
                        turn_number=turn_number,
                        fact_id=rule.conclusion,
                        observer_id=observer_id,
                        rule_id=rule.id,
                        premise_fact_ids=tuple(sorted(rule.premises)),
                    )
                )
                known.add(rule.conclusion)
                progress = True
            if not progress:
                return inferred

    @classmethod
    def contradictions(cls, state: WorldState, observer_id: str) -> list[tuple[FactId, FactId]]:
        known = cls.known_facts(state, observer_id)
        pairs: set[tuple[FactId, FactId]] = set()
        for fact_id in known:
            for other_id in state.facts[fact_id].contradicts:
                if other_id in known:
                    pair = (fact_id, other_id) if fact_id < other_id else (other_id, fact_id)
                    pairs.add(pair)
        return sorted(pairs)
