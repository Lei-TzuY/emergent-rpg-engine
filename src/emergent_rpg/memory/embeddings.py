from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Sequence
from typing import Protocol

_TOKEN_RE = re.compile(r"[a-z0-9]+", re.IGNORECASE)


class EmbeddingBackend(Protocol):
    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Return one finite fixed-width vector for each input text."""


class HashingEmbeddingBackend:
    """Offline deterministic feature-hashing embeddings for semantic reranking.

    This is deliberately local and dependency-free. It provides a real vector/cosine
    retrieval path while keeping CI independent from an embedding service. A neural
    backend can implement the same protocol later without changing retrieval authority.
    """

    def __init__(self, dimensions: int = 128) -> None:
        if dimensions < 8:
            raise ValueError("dimensions must be at least 8")
        self.dimensions = dimensions

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]

    def _embed_one(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        for token in _TOKEN_RE.findall(text.casefold()):
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            bucket = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if digest[4] & 1 else -1.0
            vector[bucket] += sign
        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0.0:
            return vector
        return [value / norm for value in vector]


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right) or not left:
        raise ValueError("embedding vectors must have the same non-zero width")
    if not all(math.isfinite(value) for value in (*left, *right)):
        raise ValueError("embedding vectors must contain only finite values")
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    return dot / (left_norm * right_norm)
