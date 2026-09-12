from __future__ import annotations

from collections import deque
from collections.abc import Mapping, Set

MAX_NAVIGATION_HOPS = 8


def deterministic_next_hop(
    current_location_id: str,
    target_location_id: str,
    known_routes: Mapping[str, Set[str]],
    *,
    max_hops: int = MAX_NAVIGATION_HOPS,
) -> str | None:
    """Return the first hop on a deterministic bounded shortest path.

    The graph is already epistemically scoped by the caller. Neighbors are
    visited in stable lexical order so equal-length paths are reproducible.
    """
    if max_hops < 1:
        raise ValueError("max_hops must be positive")
    if current_location_id == target_location_id:
        return None

    queue: deque[tuple[str, int]] = deque([(current_location_id, 0)])
    parent: dict[str, str | None] = {current_location_id: None}

    while queue:
        node, depth = queue.popleft()
        if depth >= max_hops:
            continue
        for neighbor in sorted(known_routes.get(node, set())):
            if neighbor in parent:
                continue
            parent[neighbor] = node
            if neighbor == target_location_id:
                cursor = neighbor
                while parent[cursor] != current_location_id:
                    previous = parent[cursor]
                    if previous is None:
                        return None
                    cursor = previous
                return cursor
            queue.append((neighbor, depth + 1))
    return None
