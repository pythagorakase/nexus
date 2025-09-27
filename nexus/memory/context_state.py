"""Context state tracking for LORE's custom memory subsystem."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Set

logger = logging.getLogger(__name__)


@dataclass
class ContextPackage:
    """State container for baseline and incremental context across passes."""

    baseline_chunks: Set[int] = field(default_factory=set)
    baseline_entities: Dict[str, Any] = field(default_factory=dict)
    baseline_themes: List[str] = field(default_factory=list)
    token_usage: Dict[str, int] = field(default_factory=dict)
    divergence_detected: bool = False
    divergence_confidence: float = 0.0
    additional_chunks: Set[int] = field(default_factory=set)
    gap_analysis: Dict[str, str] = field(default_factory=dict)


@dataclass
class PassTransition:
    """Information needed to transition from Pass 1 (baseline) to Pass 2."""

    storyteller_output: str
    expected_user_themes: List[str] = field(default_factory=list)
    assembled_context: Dict[str, Any] = field(default_factory=dict)
    remaining_budget: int = 0


class ContextStateManager:
    """Manage shared state between Pass 1 and Pass 2."""

    def __init__(self) -> None:
        self._context: Optional[ContextPackage] = None
        self._transition: Optional[PassTransition] = None
        self._chunk_cache: Dict[int, Dict[str, Any]] = {}

    # ------------------------------------------------------------------
    # Baseline context management
    # ------------------------------------------------------------------
    def store_baseline(
        self,
        package: ContextPackage,
        transition: PassTransition,
        chunk_details: Optional[Iterable[Dict[str, Any]]] = None,
    ) -> None:
        """Persist a new baseline package and associated transition metadata."""

        logger.debug(
            "Storing new baseline context: %s chunks, remaining budget=%s",
            len(package.baseline_chunks),
            transition.remaining_budget,
        )

        package.additional_chunks.clear()
        package.gap_analysis.clear()
        package.divergence_detected = False
        package.divergence_confidence = 0.0

        self._context = package
        self._transition = transition
        self._chunk_cache = {}

        if chunk_details:
            self.register_chunks(chunk_details)

    def register_chunks(self, chunks: Iterable[Dict[str, Any]]) -> None:
        """Register chunk payloads for quick lookup and deduplication."""

        for chunk in chunks:
            chunk_id = self._extract_chunk_id(chunk)
            if chunk_id is None:
                continue
            if self._context:
                if chunk_id in self._context.baseline_chunks or chunk_id in self._context.additional_chunks:
                    self._chunk_cache[chunk_id] = chunk
            else:
                self._chunk_cache[chunk_id] = chunk

    # ------------------------------------------------------------------
    # Accessors
    # ------------------------------------------------------------------
    @property
    def context(self) -> Optional[ContextPackage]:
        return self._context

    @property
    def transition(self) -> Optional[PassTransition]:
        return self._transition

    def get_current_context(self) -> Optional[ContextPackage]:
        """Convenience accessor used by status reporting."""
        return self._context

    # ------------------------------------------------------------------
    # Chunk helpers
    # ------------------------------------------------------------------
    def is_chunk_known(self, chunk_id: int) -> bool:
        if not self._context:
            return False
        return chunk_id in self._context.baseline_chunks or chunk_id in self._context.additional_chunks

    def register_additional_chunks(self, chunks: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Register additional chunks and return only the truly new entries."""

        if not self._context:
            logger.debug("No baseline context loaded; skipping additional chunk registration")
            return []

        new_chunks: List[Dict[str, Any]] = []
        for chunk in chunks:
            chunk_id = self._extract_chunk_id(chunk)
            if chunk_id is None or self.is_chunk_known(chunk_id):
                continue
            self._context.additional_chunks.add(chunk_id)
            self._chunk_cache[chunk_id] = chunk
            new_chunks.append(chunk)
        return new_chunks

    def get_all_chunks(self) -> List[Dict[str, Any]]:
        if not self._context:
            return []
        # Return chunks in a deterministic order: baseline first, then additional
        ordered_ids = list(self._context.baseline_chunks) + list(self._context.additional_chunks)
        seen: Set[int] = set()
        result: List[Dict[str, Any]] = []
        for chunk_id in ordered_ids:
            if chunk_id in seen:
                continue
            chunk = self._chunk_cache.get(chunk_id)
            if chunk:
                result.append(chunk)
                seen.add(chunk_id)
        return result

    def get_additional_chunk_details(self) -> List[Dict[str, Any]]:
        if not self._context:
            return []
        details: List[Dict[str, Any]] = []
        for chunk_id in self._context.additional_chunks:
            chunk = self._chunk_cache.get(chunk_id)
            if chunk:
                details.append(chunk)
        return details

    # ------------------------------------------------------------------
    # Budget helpers
    # ------------------------------------------------------------------
    def get_remaining_budget(self) -> int:
        if not self._transition:
            return 0
        return max(0, int(self._transition.remaining_budget))

    def consume_budget(self, amount: int) -> int:
        if not self._transition or amount <= 0:
            return 0
        available = self.get_remaining_budget()
        to_consume = min(available, amount)
        self._transition.remaining_budget = max(0, available - to_consume)
        logger.debug("Consumed %s tokens from remaining budget (now %s)", to_consume, self._transition.remaining_budget)
        return to_consume

    def adjust_budget(self, remaining_budget: int) -> None:
        if not self._transition:
            return
        self._transition.remaining_budget = max(0, remaining_budget)

    # ------------------------------------------------------------------
    # Divergence tracking
    # ------------------------------------------------------------------
    def update_divergence(self, detected: bool, confidence: float, gaps: Dict[str, str]) -> None:
        if not self._context:
            return
        self._context.divergence_detected = detected
        self._context.divergence_confidence = confidence
        self._context.gap_analysis = gaps

    # ------------------------------------------------------------------
    # Utility helpers
    # ------------------------------------------------------------------
    def _extract_chunk_id(self, chunk: Dict[str, Any]) -> Optional[int]:
        chunk_id = chunk.get("id") or chunk.get("chunk_id")
        if chunk_id is None:
            return None
        try:
            return int(chunk_id)
        except (TypeError, ValueError):
            logger.debug("Could not coerce chunk id '%s' to int", chunk_id)
            return None
