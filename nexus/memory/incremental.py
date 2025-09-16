"""Incremental retrieval helpers for LORE Pass 2."""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from .context_state import ContextPackage
from .query_memory import QueryMemory


class IncrementalRetriever:
    """Retrieve additional context without duplicating Pass 1 content."""

    def __init__(self, memnon: Optional[object], warm_slice_default: bool = True) -> None:
        self.memnon = memnon
        self.warm_slice_default = warm_slice_default
        self.estimated_tokens_per_chunk = 180

    # Public API -------------------------------------------------------

    def retrieve_gap_context(
        self,
        gaps: Dict[str, str],
        context_package: ContextPackage,
        remaining_budget: int,
        query_memory: QueryMemory,
    ) -> Tuple[List[Dict], Set[int], int, Dict[str, str]]:
        """Fetch additional chunks covering detected gaps."""

        if not gaps or not self.memnon:
            return [], set(), remaining_budget, {}

        additions: List[Dict] = []
        added_chunk_ids: Set[int] = set()
        gap_feedback: Dict[str, str] = {}

        for term, reason in gaps.items():
            if remaining_budget <= 0:
                break
            if query_memory.remaining_iterations(pass_id=2) <= 0:
                gap_feedback.setdefault(term, "Query budget exhausted")
                break

            query = term.strip()
            if not query:
                continue
            if query_memory.was_executed(query):
                gap_feedback.setdefault(term, "Query already executed in Pass 1")
                continue

            try:
                results = self.memnon.query_memory(query=query, k=8, use_hybrid=True)
                query_memory.record_pass2_query(query)
            except Exception as exc:  # pragma: no cover - defensive logging
                gap_feedback[term] = f"Query failed: {exc}"
                continue

            result_chunks = results.get("results", [])
            if not result_chunks:
                gap_feedback.setdefault(term, "No results returned")
                continue

            for chunk in result_chunks:
                chunk_id = self._extract_chunk_id(chunk)
                if chunk_id is None:
                    continue
                if chunk_id in context_package.combined_chunk_ids() or chunk_id in added_chunk_ids:
                    continue

                chunk.setdefault("source", "pass2_gap")
                chunk.setdefault("query", query)
                additions.append(chunk)
                added_chunk_ids.add(chunk_id)
                remaining_budget -= self.estimated_tokens_per_chunk

                if remaining_budget <= 0:
                    break

            if term not in gap_feedback:
                gap_feedback[term] = reason

            if remaining_budget <= 0:
                break

        return additions, added_chunk_ids, max(0, remaining_budget), gap_feedback

    def expand_warm_slice(
        self,
        remaining_budget: int,
        context_package: ContextPackage,
    ) -> Tuple[List[Dict], Set[int], int]:
        """Provide a warm slice expansion when no divergence is detected."""

        if not self.warm_slice_default or not self.memnon or remaining_budget <= 0:
            return [], set(), remaining_budget

        # Estimate how many additional chunks we can afford.
        chunk_allowance = max(1, remaining_budget // self.estimated_tokens_per_chunk)
        chunk_allowance = min(chunk_allowance, 10)

        try:
            recent = self.memnon.get_recent_chunks(limit=chunk_allowance)
            candidate_chunks = recent.get("results", []) if isinstance(recent, dict) else recent
        except Exception:  # pragma: no cover - defensive logging
            return [], set(), remaining_budget

        additions: List[Dict] = []
        added_ids: Set[int] = set()

        for chunk in candidate_chunks:
            chunk_id = self._extract_chunk_id(chunk)
            if chunk_id is None:
                continue
            if chunk_id in context_package.combined_chunk_ids() or chunk_id in added_ids:
                continue

            chunk.setdefault("source", "pass2_warm")
            additions.append(chunk)
            added_ids.add(chunk_id)
            remaining_budget -= self.estimated_tokens_per_chunk
            if remaining_budget <= 0:
                break

        return additions, added_ids, max(0, remaining_budget)

    def merge_warm_slice(self, warm_slice: Sequence[Dict], additions: Sequence[Dict]) -> List[Dict]:
        """Merge additional chunks into warm slice without duplication."""

        merged = list(warm_slice or [])
        seen_ids = {self._extract_chunk_id(chunk) for chunk in merged if self._extract_chunk_id(chunk) is not None}

        for addition in additions:
            chunk_id = self._extract_chunk_id(addition)
            if chunk_id is None or chunk_id in seen_ids:
                continue
            merged.append(addition)
            seen_ids.add(chunk_id)

        return merged

    # Helpers ----------------------------------------------------------

    def _extract_chunk_id(self, chunk: Dict) -> Optional[int]:
        chunk_id = chunk.get("chunk_id") or chunk.get("id")
        if chunk_id is None:
            return None
        try:
            return int(chunk_id)
        except (TypeError, ValueError):  # pragma: no cover - defensive
            return None

