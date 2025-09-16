"""Context state management for LORE's custom memory system."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Set

logger = logging.getLogger("nexus.memory.context_state")


@dataclass
class ContextPackage:
    """Represents the combined context state across both passes."""

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
    """Stores information that flows from Pass 1 to Pass 2."""

    storyteller_output: str = ""
    expected_user_themes: List[str] = field(default_factory=list)
    assembled_context: Dict[str, Any] = field(default_factory=dict)
    remaining_budget: int = 0


class ContextStateManager:
    """Tracks baseline and incremental context for the two-pass system."""

    def __init__(self) -> None:
        self.context = ContextPackage()
        self.transition: Optional[PassTransition] = None
        self.chunk_store: Dict[int, Dict[str, Any]] = {}
        self.baseline_chunk_order: List[int] = []
        self.additional_chunk_order: List[int] = []
        self.last_user_input: Optional[str] = None
        self.last_analysis: Dict[str, Any] = {}

    # ------------------------------------------------------------------
    # Baseline (Pass 1) state
    # ------------------------------------------------------------------
    def reset(self) -> None:
        """Reset all context state."""

        logger.debug("Resetting context state manager")
        self.context = ContextPackage()
        self.transition = None
        self.chunk_store.clear()
        self.baseline_chunk_order.clear()
        self.additional_chunk_order.clear()
        self.last_user_input = None
        self.last_analysis = {}

    def reset_incremental_state(self) -> None:
        """Clear Pass 2 additions while keeping baseline context intact."""

        logger.debug("Resetting incremental context state")
        self.context.divergence_detected = False
        self.context.divergence_confidence = 0.0
        self.context.additional_chunks.clear()
        self.context.gap_analysis.clear()
        self.additional_chunk_order.clear()

    def store_pass_transition(self, transition: PassTransition) -> None:
        """Persist PassTransition information."""

        logger.debug(
            "Storing pass transition: remaining_budget=%s, themes=%s",
            transition.remaining_budget,
            transition.expected_user_themes,
        )
        self.transition = transition

    def update_remaining_budget(self, remaining_budget: int) -> None:
        """Update the remaining token budget available for Pass 2."""

        if not self.transition:
            self.transition = PassTransition()
        logger.debug("Updating remaining budget to %s", remaining_budget)
        self.transition.remaining_budget = max(0, int(remaining_budget))

    def store_baseline_context(
        self,
        chunk_ids: Iterable[int],
        entities: Dict[str, Any],
        themes: Iterable[str],
        token_usage: Dict[str, int],
        chunk_details: Iterable[Dict[str, Any]],
        storyteller_output: str,
        expected_user_themes: Iterable[str],
        assembled_context: Dict[str, Any],
        remaining_budget: int,
        analysis: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Store baseline context for Pass 1."""

        self.reset_incremental_state()

        normalized_ids = {self._normalize_chunk_id(cid) for cid in chunk_ids if cid is not None}
        normalized_ids.discard(None)
        self.context.baseline_chunks = normalized_ids
        self.context.baseline_entities = entities or {}
        self.context.baseline_themes = list(themes or [])
        self.context.token_usage = token_usage or {}
        self.last_analysis = analysis or {}

        logger.debug(
            "Stored baseline context with %d chunk(s) and %d entity entries",
            len(self.context.baseline_chunks),
            len(self.context.baseline_entities),
        )

        # Store chunk data for baseline access
        self.baseline_chunk_order = []
        for chunk in chunk_details or []:
            chunk_id = self._extract_chunk_id(chunk)
            if chunk_id is None:
                continue
            if chunk_id not in self.context.baseline_chunks:
                self.context.baseline_chunks.add(chunk_id)
            if chunk_id not in self.baseline_chunk_order:
                self.baseline_chunk_order.append(chunk_id)
            self.chunk_store[chunk_id] = chunk

        # Persist pass transition details
        transition = PassTransition(
            storyteller_output=storyteller_output or "",
            expected_user_themes=list(expected_user_themes or []),
            assembled_context=assembled_context or {},
            remaining_budget=int(remaining_budget),
        )
        self.store_pass_transition(transition)

    # ------------------------------------------------------------------
    # Incremental (Pass 2) state
    # ------------------------------------------------------------------
    def mark_divergence(
        self,
        detected: bool,
        confidence: float,
        gap_analysis: Dict[str, str],
    ) -> None:
        """Record divergence information detected in Pass 2."""

        self.context.divergence_detected = bool(detected)
        self.context.divergence_confidence = max(0.0, min(1.0, confidence))
        self.context.gap_analysis = gap_analysis or {}
        logger.debug(
            "Marked divergence detected=%s confidence=%.3f gaps=%s",
            detected,
            confidence,
            list(gap_analysis.keys()),
        )

    def register_additional_chunk(self, chunk: Dict[str, Any]) -> Optional[int]:
        """Register a chunk retrieved during Pass 2."""

        chunk_id = self._extract_chunk_id(chunk)
        if chunk_id is None:
            return None

        if chunk_id in self.context.baseline_chunks or chunk_id in self.context.additional_chunks:
            return None

        self.chunk_store[chunk_id] = chunk
        self.context.additional_chunks.add(chunk_id)
        self.additional_chunk_order.append(chunk_id)
        logger.debug("Registered additional chunk %s", chunk_id)
        return chunk_id

    # ------------------------------------------------------------------
    # Utility helpers
    # ------------------------------------------------------------------
    def record_user_input(self, user_input: str) -> None:
        """Keep track of the most recent user input."""

        self.last_user_input = user_input or ""

    def has_chunk(self, chunk_id: Any) -> bool:
        """Return True if the chunk is already part of the baseline or incremental context."""

        normalized = self._normalize_chunk_id(chunk_id)
        if normalized is None:
            return False
        return normalized in self.context.baseline_chunks or normalized in self.context.additional_chunks

    def get_chunk_data(self, chunk_id: Any) -> Optional[Dict[str, Any]]:
        """Return stored chunk data if available."""

        normalized = self._normalize_chunk_id(chunk_id)
        if normalized is None:
            return None
        return self.chunk_store.get(normalized)

    def get_baseline_chunk_data(self) -> List[Dict[str, Any]]:
        """Return baseline chunk data in insertion order."""

        return [self.chunk_store[cid] for cid in self.baseline_chunk_order if cid in self.chunk_store]

    def get_incremental_chunk_data(self) -> List[Dict[str, Any]]:
        """Return incremental chunk data in retrieval order."""

        return [self.chunk_store[cid] for cid in self.additional_chunk_order if cid in self.chunk_store]

    def get_augmented_warm_slice(self, base_slice: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Combine baseline, base warm slice, and incremental chunks without duplication."""

        combined: List[Dict[str, Any]] = []
        seen: Set[int] = set()

        for chunk in self.get_baseline_chunk_data():
            chunk_id = self._extract_chunk_id(chunk)
            if chunk_id is None or chunk_id in seen:
                continue
            combined.append(chunk)
            seen.add(chunk_id)

        for chunk in base_slice or []:
            chunk_id = self._extract_chunk_id(chunk)
            if chunk_id is None or chunk_id in seen:
                continue
            combined.append(chunk)
            seen.add(chunk_id)

        for chunk in self.get_incremental_chunk_data():
            chunk_id = self._extract_chunk_id(chunk)
            if chunk_id is None or chunk_id in seen:
                continue
            combined.append(chunk)
            seen.add(chunk_id)

        logger.debug("Augmented warm slice to %d chunk(s)", len(combined))
        return combined

    def get_expected_terms(self) -> Set[str]:
        """Derive the set of terms considered covered by baseline context."""

        expected: Set[str] = set()
        for theme in self.context.baseline_themes:
            if theme:
                expected.add(theme.lower())

        if isinstance(self.context.baseline_entities, dict):
            for value in self.context.baseline_entities.values():
                self._collect_terms(value, expected)

        if self.transition and self.transition.expected_user_themes:
            for theme in self.transition.expected_user_themes:
                if theme:
                    expected.add(str(theme).lower())

        if self.last_analysis:
            for key in ("entities", "keywords", "themes"):
                self._collect_terms(self.last_analysis.get(key), expected)

        return expected

    def get_context_summary(self) -> Dict[str, Any]:
        """Return a serializable snapshot of the current context state."""

        return {
            "baseline_chunks": sorted(self.context.baseline_chunks),
            "additional_chunks": sorted(self.context.additional_chunks),
            "divergence_detected": self.context.divergence_detected,
            "divergence_confidence": self.context.divergence_confidence,
            "gap_analysis": self.context.gap_analysis,
            "expected_user_themes": self.transition.expected_user_themes if self.transition else [],
            "remaining_budget": self.transition.remaining_budget if self.transition else 0,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _normalize_chunk_id(self, chunk_id: Any) -> Optional[int]:
        if chunk_id is None:
            return None
        try:
            return int(chunk_id)
        except (TypeError, ValueError):
            return None

    def _extract_chunk_id(self, chunk: Dict[str, Any]) -> Optional[int]:
        if not isinstance(chunk, dict):
            return None
        for key in ("chunk_id", "id"):
            if key in chunk:
                normalized = self._normalize_chunk_id(chunk[key])
                if normalized is not None:
                    return normalized
        return None

    def _collect_terms(self, value: Any, sink: Set[str]) -> None:
        if not value:
            return
        if isinstance(value, str):
            sink.add(value.lower())
        elif isinstance(value, (list, set, tuple)):
            for item in value:
                self._collect_terms(item, sink)
        elif isinstance(value, dict):
            for item in value.values():
                self._collect_terms(item, sink)

