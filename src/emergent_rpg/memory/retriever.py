from __future__ import annotations

import logging
from collections.abc import Sequence

from emergent_rpg.domain.actions import PlayerAction
from emergent_rpg.domain.models import WorldState
from emergent_rpg.memory.embeddings import EmbeddingBackend, cosine_similarity
from emergent_rpg.memory.models import Episode, RetrievedContext
from emergent_rpg.persistence.db import SQLiteStore

logger = logging.getLogger(__name__)


class MemoryRetriever:
    def __init__(
        self,
        store: SQLiteStore,
        working_turns: int = 8,
        embedding_backend: EmbeddingBackend | None = None,
        semantic_weight: float = 2.0,
    ) -> None:
        if semantic_weight < 0.0:
            raise ValueError("semantic_weight cannot be negative")
        self.store = store
        self.working_turns = working_turns
        self.embedding_backend = embedding_backend
        self.semantic_weight = semantic_weight

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
        query_tags: set[str] = {player_action.kind}
        episodes = self.store.list_episodes(session_id)
        semantic_scores = self._semantic_episode_scores(
            episodes,
            self._query_text(player_action, location, involved_entities),
        )
        ranked = sorted(
            episodes,
            key=lambda episode: (
                self._score(
                    episode,
                    state,
                    location,
                    involved_entities,
                    query_tags,
                )
                + self.semantic_weight * semantic_scores.get(episode.id, 0.0)
            ),
            reverse=True,
        )[:limit]
        # Canonical semantic facts are filtered before any optional embedding work and are
        # never supplied by the backend. Vector retrieval can only rerank persisted episodes.
        semantic = [
            state.facts[fact_id].proposition for fact_id in sorted(state.player_known_facts)
        ]
        return RetrievedContext(
            working_memory=working,
            episodes=ranked,
            semantic_facts=semantic,
            current_location=location,
        )

    def _semantic_episode_scores(
        self,
        episodes: Sequence[Episode],
        query_text: str,
    ) -> dict[str, float]:
        if self.embedding_backend is None or not episodes or self.semantic_weight == 0.0:
            return {}
        texts = [query_text, *(episode.summary for episode in episodes)]
        try:
            vectors = self.embedding_backend.embed(texts)
            self._validate_embedding_batch(vectors, expected_count=len(texts))
            query_vector = vectors[0]
            return {
                episode.id: cosine_similarity(query_vector, vector)
                for episode, vector in zip(episodes, vectors[1:], strict=True)
            }
        except Exception as exc:
            logger.warning("semantic retrieval unavailable; using deterministic ranking: %s", exc)
            return {}

    @staticmethod
    def _validate_embedding_batch(
        vectors: Sequence[Sequence[float]],
        expected_count: int,
    ) -> None:
        if len(vectors) != expected_count:
            raise ValueError("embedding backend returned the wrong vector count")
        if not vectors or not vectors[0]:
            raise ValueError("embedding backend returned an empty vector")
        width = len(vectors[0])
        if any(len(vector) != width for vector in vectors):
            raise ValueError("embedding backend returned inconsistent vector widths")
        # cosine_similarity performs the finite-value validation for each candidate. Validate
        # the query eagerly too so an empty episode list can never hide malformed output.
        cosine_similarity(vectors[0], vectors[0])

    @staticmethod
    def _query_text(
        player_action: PlayerAction,
        location: str,
        involved_entities: set[str],
    ) -> str:
        fields = " ".join(
            str(value)
            for key, value in player_action.model_dump(mode="json").items()
            if key != "kind"
        )
        entities = " ".join(sorted(involved_entities))
        return f"{player_action.kind} {fields} location {location} entities {entities}".strip()

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
