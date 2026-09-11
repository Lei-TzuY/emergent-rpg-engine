from __future__ import annotations

from emergent_rpg.domain.actions import PlayerAction
from emergent_rpg.domain.models import WorldState
from emergent_rpg.memory.models import Episode, RetrievedContext
from emergent_rpg.persistence.db import SQLiteStore


class MemoryRetriever:
    def __init__(self, store: SQLiteStore, working_turns: int = 8) -> None:
        self.store = store
        self.working_turns = working_turns

    def retrieve_context(
        self,
        session_id: str,
        player_action: PlayerAction,
        location: str,
        involved_entities: set[str],
        limit: int = 6,
    ) -> RetrievedContext:
        state = self.store.load_state(session_id)
        turns = self.store.list_turns(session_id, limit=self.working_turns)
        working = [f"T{turn.turn_number} {turn.raw_input}: {turn.narration}" for turn in turns]
        query_tags = {player_action.kind}
        ranked = sorted(
            self.store.list_episodes(session_id),
            key=lambda episode: self._score(
                episode,
                state,
                location,
                involved_entities,
                query_tags,
            ),
            reverse=True,
        )[:limit]
        semantic = [
            state.facts[fact_id].proposition for fact_id in sorted(state.player_known_facts)
        ]
        return RetrievedContext(
            working_memory=working,
            episodes=ranked,
            semantic_facts=semantic,
            current_location=location,
        )

    @staticmethod
    def _score(
        episode: Episode,
        state: WorldState,
        location: str,
        involved_entities: set[str],
        query_tags: set[str],
    ) -> float:
        recency = 1.0 / (1.0 + max(0, state.turn_number - episode.turn_range[1]))
        entity_overlap = len(episode.involved_entities & involved_entities)
        location_overlap = 1.0 if episode.location == location else 0.0
        tag_overlap = len(episode.tags & query_tags)
        return (
            recency * 3.0
            + entity_overlap * 2.0
            + location_overlap * 1.5
            + tag_overlap
            + episode.importance
        )
