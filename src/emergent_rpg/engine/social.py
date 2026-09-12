from __future__ import annotations

from emergent_rpg.domain.models import NPC, Fact

NEUTRAL_RELATIONSHIP_SCORE = 0


class SocialDisclosurePolicy:
    @staticmethod
    def relationship_score(source: NPC, receiver_id: str) -> int:
        return source.relationships.get(receiver_id, NEUTRAL_RELATIONSHIP_SCORE)

    @classmethod
    def can_disclose(cls, fact: Fact, source: NPC, receiver_id: str) -> bool:
        return cls.relationship_score(source, receiver_id) >= fact.disclosure_min_relationship
