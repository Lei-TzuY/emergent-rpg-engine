from __future__ import annotations

import math
from collections.abc import Sequence
from pathlib import Path

from emergent_rpg.domain.actions import InspectAction, TakeAction, WaitAction
from emergent_rpg.engine.service import GameEngine
from emergent_rpg.memory.embeddings import HashingEmbeddingBackend, cosine_similarity
from emergent_rpg.memory.retriever import MemoryRetriever
from emergent_rpg.persistence.db import SQLiteStore


class BrokenEmbeddingBackend:
    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        del texts
        return [[math.nan], [1.0]]


class WrongCountEmbeddingBackend:
    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        del texts
        return [[1.0, 0.0]]


class FailingEmbeddingBackend:
    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        del texts
        raise RuntimeError("embedding service unavailable")


def make_engine(tmp_path: Path) -> tuple[GameEngine, str]:
    engine = GameEngine(SQLiteStore(tmp_path / "game.db"))
    session = engine.new_session()
    return engine, session.id


def test_hashing_embeddings_are_deterministic_and_semantically_sensitive() -> None:
    backend = HashingEmbeddingBackend(dimensions=256)
    first, second, unrelated = backend.embed(
        [
            "inspect the brass key and its stamped locker mark",
            "brass key locker mark inspection",
            "wait quietly while the storm passes",
        ]
    )

    assert first == backend.embed(["inspect the brass key and its stamped locker mark"])[0]
    assert math.isclose(sum(value * value for value in first), 1.0, rel_tol=1e-9)
    assert cosine_similarity(first, second) > cosine_similarity(first, unrelated)


def test_semantic_retrieval_promotes_relevant_persisted_episode(tmp_path: Path) -> None:
    engine, session_id = make_engine(tmp_path)
    engine.execute_action(session_id, TakeAction(target="brass key"), "take brass key")
    engine.execute_action(session_id, WaitAction(minutes=1), "wait 1")

    baseline = MemoryRetriever(engine.store).retrieve_context(
        session_id,
        InspectAction(target="brass key"),
        "yard",
        {"player"},
        limit=2,
    )
    semantic = MemoryRetriever(
        engine.store,
        embedding_backend=HashingEmbeddingBackend(dimensions=256),
        semantic_weight=8.0,
    ).retrieve_context(
        session_id,
        InspectAction(target="brass key"),
        "yard",
        {"player"},
        limit=2,
    )

    assert "wait" in baseline.episodes[0].summary.casefold()
    assert "brass key" in semantic.episodes[0].summary.casefold()
    assert {episode.id for episode in semantic.episodes} == {
        episode.id for episode in baseline.episodes
    }


def test_malformed_embedding_output_falls_back_to_deterministic_ranking(
    tmp_path: Path,
) -> None:
    engine, session_id = make_engine(tmp_path)
    engine.execute_action(session_id, WaitAction(minutes=1), "wait 1")
    engine.execute_action(session_id, WaitAction(minutes=2), "wait 2")

    baseline = MemoryRetriever(engine.store).retrieve_context(
        session_id,
        WaitAction(minutes=1),
        "yard",
        {"player"},
        limit=2,
    )
    broken = MemoryRetriever(
        engine.store,
        embedding_backend=BrokenEmbeddingBackend(),
    ).retrieve_context(
        session_id,
        WaitAction(minutes=1),
        "yard",
        {"player"},
        limit=2,
    )
    wrong_count = MemoryRetriever(
        engine.store,
        embedding_backend=WrongCountEmbeddingBackend(),
    ).retrieve_context(
        session_id,
        WaitAction(minutes=1),
        "yard",
        {"player"},
        limit=2,
    )
    failed = MemoryRetriever(
        engine.store,
        embedding_backend=FailingEmbeddingBackend(),
    ).retrieve_context(
        session_id,
        WaitAction(minutes=1),
        "yard",
        {"player"},
        limit=2,
    )

    expected = [episode.id for episode in baseline.episodes]
    assert [episode.id for episode in broken.episodes] == expected
    assert [episode.id for episode in wrong_count.episodes] == expected
    assert [episode.id for episode in failed.episodes] == expected


def test_embedding_backend_cannot_expand_player_fact_visibility(tmp_path: Path) -> None:
    engine, session_id = make_engine(tmp_path)
    state = engine.store.load_state(session_id)
    assert "fact_blackout_window" not in state.player_known_facts
    assert "fact_blackout_window" in state.entities["npc_arden"].knowledge.facts_known

    context = MemoryRetriever(
        engine.store,
        embedding_backend=HashingEmbeddingBackend(),
    ).retrieve_context(
        session_id,
        InspectAction(target="relay"),
        "yard",
        {"player"},
    )

    assert all("02:13" not in fact for fact in context.semantic_facts)
    assert context.semantic_facts == []
    assert engine.store.load_state(session_id) == state
    assert engine.store.load_events(session_id) == []
