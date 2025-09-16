"""Incremental retrieval logic for Pass 2."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .context_state import ContextStateManager

logger = logging.getLogger("nexus.memory.incremental")


class IncrementalRetriever:
    """Retrieves additional context for divergence handling."""

    def __init__(
        self,
        memnon: Optional[Any] = None,
        context_state: Optional[ContextStateManager] = None,
        settings: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.memnon = memnon
        self.context_state = context_state or ContextStateManager()
        self.settings = settings or {}

    def update_memnon(self, memnon: Any) -> None:
        self.memnon = memnon

    # ------------------------------------------------------------------
    # Retrieval operations
    # ------------------------------------------------------------------
    def retrieve_incremental(
        self,
        query_requests: Sequence[Tuple[str, str]],
        token_budget: int,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Retrieve additional chunks for detected gaps."""

        if not self.memnon or not query_requests or token_budget <= 0:
            return [], 0

        collected: List[Dict[str, Any]] = []
        consumed_tokens = 0

        for query, label in query_requests:
            if token_budget - consumed_tokens <= 0:
                break
            try:
                response = self.memnon.query_memory(query=query, k=8, use_hybrid=True)
            except Exception as exc:
                logger.error("Incremental retrieval failed for '%s': %s", query, exc)
                continue

            for item in response.get("results", []):
                chunk_id = item.get("chunk_id") or item.get("id")
                normalized_id = self.context_state._normalize_chunk_id(chunk_id)  # type: ignore[attr-defined]
                if normalized_id is None or self.context_state.has_chunk(normalized_id):
                    continue

                # Annotate result with retrieval reason
                item = dict(item)
                item.setdefault("metadata", {})
                item["metadata"]["retrieval_reason"] = label
                registered_id = self.context_state.register_additional_chunk(item)
                if registered_id is None:
                    continue

                collected.append(item)
                consumed_tokens += self._estimate_tokens(item.get("text", ""))
                if consumed_tokens >= token_budget:
                    break
            if consumed_tokens >= token_budget:
                break

        return collected, consumed_tokens

    def expand_warm_slice(self, token_budget: int, limit: Optional[int] = None) -> Tuple[List[Dict[str, Any]], int]:
        """Expand context with additional recent chunks when no divergence is detected."""

        if not self.memnon or token_budget <= 0:
            return [], 0

        try:
            if limit is None:
                limit = max(1, min(5, token_budget // 150 or 1))
            recent = self.memnon.get_recent_chunks(limit=limit)
        except Exception as exc:
            logger.error("Failed to expand warm slice: %s", exc)
            return [], 0

        additions: List[Dict[str, Any]] = []
        consumed_tokens = 0
        for chunk in recent.get("results", []):
            chunk_id = chunk.get("chunk_id") or chunk.get("id")
            if self.context_state.has_chunk(chunk_id):
                continue
            registered_id = self.context_state.register_additional_chunk(chunk)
            if registered_id is None:
                continue
            additions.append(chunk)
            consumed_tokens += self._estimate_tokens(chunk.get("text", ""))
            if consumed_tokens >= token_budget:
                break

        return additions, consumed_tokens

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------
    def _estimate_tokens(self, text: str) -> int:
        if not text:
            return 0
        # Approximate 0.75 tokens per word to keep estimates conservative
        words = text.split()
        return int(len(words) / 0.75) if words else 0

