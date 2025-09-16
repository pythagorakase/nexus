"""Track executed memory queries across passes."""

from __future__ import annotations

import logging
from typing import Dict, List

logger = logging.getLogger(__name__)


class QueryMemory:
    """Simple pass-aware query history with budget tracking."""

    def __init__(self, max_iterations: int = 5) -> None:
        self.max_iterations = max(1, int(max_iterations))
        self._history: Dict[str, List[str]] = {"pass1": [], "pass2": []}

    # ------------------------------------------------------------------
    def reset_pass(self, pass_label: str) -> None:
        if pass_label not in self._history:
            raise ValueError(f"Unknown pass label: {pass_label}")
        logger.debug("Resetting query history for %s", pass_label)
        self._history[pass_label] = []

    def has_run(self, query: str) -> bool:
        query_normalized = query.strip().lower()
        return any(query_normalized == existing.strip().lower() for existing in self.all_queries)

    def record(self, pass_label: str, query: str) -> None:
        if pass_label not in self._history:
            raise ValueError(f"Unknown pass label: {pass_label}")
        if self.remaining_iterations(pass_label) <= 0:
            logger.debug("Query budget exhausted for %s; skipping record", pass_label)
            return
        query_normalized = query.strip()
        if not query_normalized:
            return
        self._history[pass_label].append(query_normalized)
        logger.debug("Recorded %s query: %s", pass_label, query_normalized)

    # ------------------------------------------------------------------
    @property
    def all_queries(self) -> List[str]:
        return [q for history in self._history.values() for q in history]

    def remaining_iterations(self, pass_label: str) -> int:
        if pass_label not in self._history:
            raise ValueError(f"Unknown pass label: {pass_label}")
        used = len(self._history[pass_label])
        return max(0, self.max_iterations - used)

    def snapshot(self) -> Dict[str, List[str]]:
        return {label: history.copy() for label, history in self._history.items()}
