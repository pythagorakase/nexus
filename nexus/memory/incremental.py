"""Incremental retrieval helpers for Pass 2."""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple

from .context_state import ContextStateManager
from .query_memory import QueryMemory

logger = logging.getLogger(__name__)


class IncrementalRetriever:
    """Retrieve additional context without duplicating Pass 1 content."""

    def __init__(
        self,
        memnon: Optional[object],
        context_state: ContextStateManager,
        query_memory: QueryMemory,
        warm_slice_default: bool = True,
    ) -> None:
        self.memnon = memnon
        self.context_state = context_state
        self.query_memory = query_memory
        self.warm_slice_default = warm_slice_default

    # ------------------------------------------------------------------
    def retrieve_gap_context(
        self,
        gaps: Dict[str, str],
        budget: int,
    ) -> Tuple[List[Dict[str, object]], int]:
        if not self.memnon or not gaps or budget <= 0:
            return [], 0

        collected: List[Dict[str, object]] = []
        tokens_used = 0

        for reference, reason in gaps.items():
            if self.query_memory.remaining_iterations("pass2") <= 0:
                logger.debug("Pass 2 query budget exhausted; stopping incremental retrieval")
                break

            query = f"{reference} {reason}".strip()
            if self.query_memory.has_run(query):
                logger.debug("Skipping previously executed query: %s", query)
                continue

            try:
                result = self.memnon.query_memory(query=query, k=5, use_hybrid=True)
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.error("Incremental retrieval failed for query '%s': %s", query, exc)
                continue

            self.query_memory.record("pass2", query)

            for chunk in result.get("results", []):
                chunk_id = chunk.get("chunk_id") or chunk.get("id")
                try:
                    chunk_id = int(chunk_id) if chunk_id is not None else None
                except (TypeError, ValueError):
                    chunk_id = None
                if chunk_id is None:
                    continue
                if self.context_state.is_chunk_known(chunk_id):
                    continue

                estimated_tokens = self._estimate_tokens(chunk.get("text", ""))
                if tokens_used + estimated_tokens > budget:
                    logger.debug(
                        "Token budget reached while processing chunk %s", chunk_id
                    )
                    return collected, tokens_used

                collected.append({"chunk_id": chunk_id, **chunk})
                tokens_used += estimated_tokens

                if tokens_used >= budget:
                    return collected, tokens_used

        return collected, tokens_used

    # ------------------------------------------------------------------
    def expand_warm_slice(self, budget: int) -> Tuple[List[Dict[str, object]], int]:
        if not self.memnon or not self.warm_slice_default or budget <= 0:
            return [], 0

        try:
            recent = self.memnon.get_recent_chunks(limit=5) or {}
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error("Warm slice expansion failed: %s", exc)
            return [], 0

        additions: List[Dict[str, object]] = []
        tokens_used = 0

        for chunk in recent.get("results", []):
            chunk_id = chunk.get("chunk_id") or chunk.get("id")
            try:
                chunk_id = int(chunk_id) if chunk_id is not None else None
            except (TypeError, ValueError):
                chunk_id = None
            if chunk_id is None or self.context_state.is_chunk_known(chunk_id):
                continue

            estimated_tokens = self._estimate_tokens(chunk.get("text", ""))
            if tokens_used + estimated_tokens > budget:
                break

            additions.append({"chunk_id": chunk_id, **chunk})
            tokens_used += estimated_tokens

            if tokens_used >= budget:
                break

        return additions, tokens_used

    # ------------------------------------------------------------------
    def _estimate_tokens(self, text: str) -> int:
        # Fallback heuristic: words * 1.25 ≈ tokens
        words = len(text.split())
        return int(words * 1.25)
