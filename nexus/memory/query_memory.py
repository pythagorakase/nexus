"""Query tracking for LORE's two-pass memory system."""

from __future__ import annotations

import logging
from typing import Dict, Iterable, List, Optional, Set

logger = logging.getLogger("nexus.memory.query_memory")


class QueryMemory:
    """Tracks SQL/text queries executed across passes."""

    def __init__(self, max_iterations: int = 5) -> None:
        self.max_iterations = max(1, int(max_iterations or 5))
        self._queries: Dict[int, List[str]] = {1: [], 2: []}
        self._normalized: Dict[int, Set[str]] = {1: set(), 2: set()}
        self._all_queries: Set[str] = set()

    # ------------------------------------------------------------------
    # Reset operations
    # ------------------------------------------------------------------
    def reset(self) -> None:
        logger.debug("Resetting query memory for all passes")
        for pass_index in (1, 2):
            self.reset_pass(pass_index)
        self._all_queries.clear()

    def reset_pass(self, pass_index: int) -> None:
        logger.debug("Resetting query memory for pass %s", pass_index)
        self._queries[pass_index] = []
        self._normalized[pass_index] = set()
        # Rebuild global cache to avoid stale entries
        self._all_queries = {q for values in self._normalized.values() for q in values}

    # ------------------------------------------------------------------
    # Query recording
    # ------------------------------------------------------------------
    def record_queries(self, pass_index: int, queries: Iterable[str]) -> List[str]:
        recorded: List[str] = []
        for query in queries:
            if self.reserve_query(pass_index, query):
                recorded.append(query)
        return recorded

    def reserve_query(self, pass_index: int, query: Optional[str]) -> bool:
        normalized = self._normalize(query)
        if not normalized:
            return False
        if normalized in self._all_queries:
            logger.debug("Skipping duplicate query '%s'", normalized)
            return False
        if len(self._queries[pass_index]) >= self.max_iterations:
            logger.debug("Query budget exhausted for pass %s", pass_index)
            return False

        self._queries[pass_index].append(query.strip())
        self._normalized[pass_index].add(normalized)
        self._all_queries.add(normalized)
        logger.debug("Recorded query '%s' for pass %s", normalized, pass_index)
        return True

    # ------------------------------------------------------------------
    # Query inspection
    # ------------------------------------------------------------------
    def was_run(self, query: Optional[str]) -> bool:
        normalized = self._normalize(query)
        return bool(normalized and normalized in self._all_queries)

    def remaining_budget(self, pass_index: int) -> int:
        return max(0, self.max_iterations - len(self._queries[pass_index]))

    def get_queries(self, pass_index: Optional[int] = None) -> List[str]:
        if pass_index is None:
            merged: List[str] = []
            for idx in (1, 2):
                merged.extend(self._queries[idx])
            return merged
        return list(self._queries.get(pass_index, []))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _normalize(self, query: Optional[str]) -> Optional[str]:
        if not query:
            return None
        normalized = " ".join(query.split()).strip().lower()
        return normalized or None

