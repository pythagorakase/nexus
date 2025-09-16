"""Incremental context retrieval for LORE's Pass 2."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from nexus.agents.lore.utils.chunk_operations import calculate_chunk_tokens

from .context_state import ContextStateManager
from .divergence import DivergenceResult
from .query_memory import QueryMemory

logger = logging.getLogger("nexus.memory.incremental")


class IncrementalRetriever:
    """Handles Pass 2 augmentation without duplicating baseline chunks."""

    def __init__(
        self,
        *,
        memnon: Optional[Any],
        query_memory: QueryMemory,
        warm_slice_default: bool = True,
    ) -> None:
        self.memnon = memnon
        self.query_memory = query_memory
        self.warm_slice_default = warm_slice_default

    # ------------------------------------------------------------------
    # Divergence handling
    # ------------------------------------------------------------------
    def retrieve_for_divergence(
        self,
        divergence: DivergenceResult,
        state: ContextStateManager,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Retrieve context for detected divergence."""

        if not divergence.detected or not self.memnon:
            return [], 0

        additions: List[Dict[str, Any]] = []
        tokens_used = 0

        gap_terms = divergence.gap_terms
        if not gap_terms:
            return [], 0

        for term in gap_terms:
            if self.query_memory.remaining_iterations(2) <= 0:
                logger.debug("Query budget exhausted for Pass 2; stopping retrieval")
                break
            if self.query_memory.was_executed(term):
                logger.debug("Skipping duplicate query term: %s", term)
                continue

            self.query_memory.record_queries(2, [term])

            try:
                results = self.memnon.query_memory(query=term, k=5, use_hybrid=True)
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("Pass 2 retrieval failed for '%s': %s", term, exc)
                continue

            for chunk in results.get("results", []):
                chunk_id = chunk.get("id")
                if not chunk_id:
                    continue
                package = state.current_package
                if not package:
                    break
                if chunk_id in package.baseline_chunks:
                    continue
                if chunk_id in package.additional_chunks:
                    continue

                chunk_tokens = self._estimate_tokens(chunk)
                if chunk_tokens <= 0:
                    continue

                if state.transition and state.transition.remaining_budget < chunk_tokens:
                    logger.debug(
                        "Budget exhausted before adding chunk %s (tokens=%s)",
                        chunk_id,
                        chunk_tokens,
                    )
                    continue

                additions.append(chunk)
                tokens_used += chunk_tokens
                state.consume_budget(chunk_tokens)

                logger.debug(
                    "Pass 2 added chunk %s (term='%s', tokens=%s)",
                    chunk_id,
                    term,
                    chunk_tokens,
                )

                if state.transition and state.transition.remaining_budget <= 0:
                    logger.debug("Remaining Pass 2 budget depleted after chunk %s", chunk_id)
                    break

            if state.transition and state.transition.remaining_budget <= 0:
                break

        return additions, tokens_used

    # ------------------------------------------------------------------
    # Warm slice expansion
    # ------------------------------------------------------------------
    def expand_warm_slice(
        self,
        state: ContextStateManager,
        desired: int = 3,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Fill remaining budget with recent warm slice chunks."""

        if not self.memnon or not self.warm_slice_default:
            return [], 0

        package = state.current_package
        if not package:
            return [], 0

        existing_ids = set(package.baseline_chunks) | set(package.additional_chunks)

        try:
            recent = self.memnon.get_recent_chunks(limit=desired * 3)
            candidates = recent.get("results", [])
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Failed to expand warm slice: %s", exc)
            return [], 0

        additions: List[Dict[str, Any]] = []
        tokens_used = 0

        for chunk in candidates:
            chunk_id = chunk.get("id")
            if not chunk_id or chunk_id in existing_ids:
                continue

            chunk_tokens = self._estimate_tokens(chunk)
            if chunk_tokens <= 0:
                continue

            if state.transition and state.transition.remaining_budget < chunk_tokens:
                logger.debug(
                    "Skipping warm addition %s due to budget (%s tokens)",
                    chunk_id,
                    chunk_tokens,
                )
                continue

            additions.append(chunk)
            tokens_used += chunk_tokens
            existing_ids.add(chunk_id)
            state.consume_budget(chunk_tokens)

            logger.debug(
                "Warm slice expansion added chunk %s (tokens=%s)",
                chunk_id,
                chunk_tokens,
            )

            if len(additions) >= desired:
                break
            if state.transition and state.transition.remaining_budget <= 0:
                break

        return additions, tokens_used

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------
    def _estimate_tokens(self, chunk: Dict[str, Any]) -> int:
        text = (
            chunk.get("full_text")
            or chunk.get("raw_text")
            or chunk.get("text")
            or ""
        )
        if not text:
            return 0
        try:
            return calculate_chunk_tokens(text)
        except Exception:  # pragma: no cover - fallback to length heuristic
            return max(1, len(text) // 4)
