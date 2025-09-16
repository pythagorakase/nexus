"""Pass-aware query tracking for the custom memory system."""

from __future__ import annotations

import logging
from typing import Dict, List

logger = logging.getLogger("nexus.memory.query_memory")


class QueryMemory:
    """Tracks executed queries across Pass 1 and Pass 2."""

    def __init__(self, max_iterations: int = 5) -> None:
        self.max_iterations = max_iterations
        self._queries: Dict[int, List[str]] = {1: [], 2: []}

    # ------------------------------------------------------------------
    # Recording and deduplication
    # ------------------------------------------------------------------
    def record_queries(self, pass_id: int, queries: List[str], replace: bool = False) -> None:
        if pass_id not in self._queries or not queries:
            return

        normalized = [self._normalize(q) for q in queries if q]
        if replace:
            self._queries[pass_id] = []

        for query in normalized:
            if not query:
                continue
            if query in self._queries[pass_id]:
                continue
            if len(self._queries[pass_id]) >= self.max_iterations:
                logger.debug(
                    "Query budget reached for pass %s; skipping '%s'", pass_id, query
                )
                break
            self._queries[pass_id].append(query)

    def was_executed(self, query: str) -> bool:
        normalized = self._normalize(query)
        return any(normalized in queries for queries in self._queries.values())

    def remaining_iterations(self, pass_id: int) -> int:
        if pass_id not in self._queries:
            return 0
        used = len(self._queries[pass_id])
        return max(0, self.max_iterations - used)

    # ------------------------------------------------------------------
    # State management
    # ------------------------------------------------------------------
    def reset_pass(self, pass_id: int) -> None:
        if pass_id in self._queries:
            self._queries[pass_id] = []

    def get_queries(self, pass_id: int) -> List[str]:
        return list(self._queries.get(pass_id, []))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _normalize(query: str) -> str:
        return " ".join(query.lower().split()) if query else ""
