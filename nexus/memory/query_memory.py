"""Query tracking between LORE memory passes."""

from __future__ import annotations

from typing import Dict, List


class QueryMemory:
    """Track SQL/text queries executed during Pass 1 and Pass 2."""

    def __init__(self, max_iterations: int = 5) -> None:
        self.max_iterations = max_iterations
        self._history: Dict[int, List[str]] = {1: [], 2: []}
        self._normalized: Dict[int, set[str]] = {1: set(), 2: set()}

    # Recording --------------------------------------------------------

    def record_pass1_query(self, query: str) -> None:
        self._record(query, pass_id=1)

    def record_pass2_query(self, query: str) -> None:
        self._record(query, pass_id=2)

    def _record(self, query: str, pass_id: int) -> None:
        if not query:
            return
        normalized = query.strip().lower()
        if not normalized:
            return
        if normalized in self._normalized[pass_id]:
            return
        self._history[pass_id].append(query)
        self._normalized[pass_id].add(normalized)

    # Budget management ------------------------------------------------

    def remaining_iterations(self, pass_id: int) -> int:
        executed = len(self._history.get(pass_id, []))
        return max(0, self.max_iterations - executed)

    def was_executed(self, query: str) -> bool:
        normalized = (query or "").strip().lower()
        if not normalized:
            return False
        return normalized in self._normalized[1] or normalized in self._normalized[2]

    def register_pass1_queries(self, queries: List[str]) -> None:
        for query in queries or []:
            self.record_pass1_query(query)

    def reset_pass2(self) -> None:
        self._history[2].clear()
        self._normalized[2].clear()

    # Introspection ----------------------------------------------------

    def get_history(self) -> Dict[str, List[str]]:
        return {
            "pass1": list(self._history.get(1, [])),
            "pass2": list(self._history.get(2, [])),
        }

