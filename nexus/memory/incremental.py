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
    def retrieve_from_raw_input(
        self,
        user_input: str,
        budget: int,
        k: int = 10,
    ) -> Tuple[List[Dict[str, object]], int]:
        """Retrieve context using raw user input for vector search.

        This method sends the unaltered user input directly to vector search,
        allowing IDF weighting to naturally boost rare/important terms like "karaoke".
        This runs IN ADDITION to any entity-triggered retrieval.

        Args:
            user_input: The raw user input text
            budget: Token budget for retrieved chunks
            k: Number of results to retrieve (default 10)

        Returns:
            Tuple of (chunks, tokens_used)
        """
        if not self.memnon or not user_input or budget <= 0:
            return [], 0

        collected: List[Dict[str, object]] = []
        tokens_used = 0

        # Check if we have query iterations remaining
        if self.query_memory.remaining_iterations("pass2") <= 0:
            logger.debug("Pass 2 query budget exhausted; cannot do raw input retrieval")
            return [], 0

        # Use the raw user input as the query (no modifications)
        query = user_input.strip()

        # Skip if we've already run this exact query
        if self.query_memory.has_run(query):
            logger.debug("Skipping previously executed raw input query")
            return [], 0

        try:
            logger.info("Performing raw user input vector search for enhanced retrieval")
            # Send raw input directly to hybrid search (vector + text)
            result = self.memnon.query_memory(query=query, k=k, use_hybrid=True)
        except Exception as exc:
            logger.error("Raw input retrieval failed: %s", exc)
            return [], 0

        # Record this query
        self.query_memory.record("pass2", query)

        # Process retrieved chunks
        for chunk in result.get("results", []):
            chunk_id = chunk.get("chunk_id") or chunk.get("id")
            try:
                chunk_id = int(chunk_id) if chunk_id is not None else None
            except (TypeError, ValueError):
                chunk_id = None

            if chunk_id is None:
                continue

            # Skip if already in context
            if self.context_state.is_chunk_known(chunk_id):
                continue

            # Check token budget
            estimated_tokens = self._estimate_tokens(chunk.get("text", ""))
            if tokens_used + estimated_tokens > budget:
                logger.debug(
                    "Token budget reached while processing raw input chunk %s", chunk_id
                )
                return collected, tokens_used

            collected.append({"chunk_id": chunk_id, **chunk})
            tokens_used += estimated_tokens

            if tokens_used >= budget:
                return collected, tokens_used

        logger.info(
            "Raw input retrieval collected %d chunks using %d tokens",
            len(collected),
            tokens_used
        )
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
