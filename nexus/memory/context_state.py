"""State tracking for LORE's two-pass memory system."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set


@dataclass
class ContextPackage:
    """Represents the combined state of Pass 1 and Pass 2 context."""

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
    """Holds information needed to bridge Storyteller and user passes."""

    storyteller_output: str
    expected_user_themes: List[str]
    assembled_context: Dict[str, Any]
    remaining_budget: int


class ContextStateManager:
    """Maintains Pass 1 baseline and Pass 2 incremental state."""

    def __init__(self) -> None:
        self._current_package: Optional[ContextPackage] = None
        self._transition: Optional[PassTransition] = None
        self._baseline_warm_slice: List[Dict[str, Any]] = []
        self._baseline_retrievals: List[Dict[str, Any]] = []
        self._incremental_chunks: List[Dict[str, Any]] = []
        self._warm_expansions: List[Dict[str, Any]] = []
        self._analysis: Dict[str, Any] = {}

    # ------------------------------------------------------------------
    # Pass 1 lifecycle
    # ------------------------------------------------------------------
    def initialize_pass1(
        self,
        package: ContextPackage,
        transition: PassTransition,
        warm_slice: Optional[List[Dict[str, Any]]],
        retrieved_passages: Optional[List[Dict[str, Any]]],
        analysis: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Store the baseline context generated during Pass 1."""

        self._current_package = package
        self._transition = transition
        self._baseline_warm_slice = list(warm_slice or [])
        self._baseline_retrievals = list(retrieved_passages or [])
        self._incremental_chunks = []
        self._warm_expansions = []
        self._analysis = analysis or {}

    def reset(self) -> None:
        """Completely clear all state (used when Storyteller fails)."""

        self._current_package = None
        self._transition = None
        self._baseline_warm_slice = []
        self._baseline_retrievals = []
        self._incremental_chunks = []
        self._warm_expansions = []
        self._analysis = {}

    # ------------------------------------------------------------------
    # Pass 2 updates
    # ------------------------------------------------------------------
    def update_divergence(self, detected: bool, confidence: float) -> None:
        if not self._current_package:
            return
        self._current_package.divergence_detected = detected
        self._current_package.divergence_confidence = confidence

    def update_gap_analysis(self, analysis: Dict[str, str]) -> None:
        if not self._current_package:
            return
        self._current_package.gap_analysis = analysis

    def register_additional_chunks(
        self,
        chunks: List[Dict[str, Any]],
        *,
        component: str,
        token_usage: int = 0,
        as_warm_slice: bool = False,
    ) -> None:
        """Track newly retrieved chunks from Pass 2."""

        if not self._current_package or not chunks:
            return

        for chunk in chunks:
            chunk_id = chunk.get("id")
            if not chunk_id:
                continue
            if chunk_id in self._current_package.baseline_chunks:
                continue
            if chunk_id in self._current_package.additional_chunks:
                continue

            self._current_package.additional_chunks.add(chunk_id)
            if as_warm_slice:
                self._warm_expansions.append(chunk)
            else:
                self._incremental_chunks.append(chunk)

        if token_usage:
            current = self._current_package.token_usage.get(component, 0)
            self._current_package.token_usage[component] = current + token_usage
            total = self._current_package.token_usage.get("pass2", 0)
            self._current_package.token_usage["pass2"] = total + token_usage

    def consume_budget(self, amount: int) -> int:
        """Decrease the remaining Pass 2 token budget."""

        if not self._transition or amount <= 0:
            return 0

        remaining = max(self._transition.remaining_budget, 0)
        consumed = min(amount, remaining)
        self._transition.remaining_budget = remaining - consumed
        return consumed

    # ------------------------------------------------------------------
    # Accessors
    # ------------------------------------------------------------------
    @property
    def current_package(self) -> Optional[ContextPackage]:
        return self._current_package

    @property
    def transition(self) -> Optional[PassTransition]:
        return self._transition

    @property
    def baseline_analysis(self) -> Dict[str, Any]:
        return self._analysis

    def get_baseline_context(self) -> Optional[ContextPackage]:
        return self._current_package

    def get_transition_state(self) -> Optional[PassTransition]:
        return self._transition

    def get_warm_slice(self) -> List[Dict[str, Any]]:
        return list(self._baseline_warm_slice) + list(self._warm_expansions)

    def get_incremental_chunks(self) -> List[Dict[str, Any]]:
        return list(self._incremental_chunks)

    def get_all_chunks(self) -> List[Dict[str, Any]]:
        return self.get_warm_slice() + list(self._baseline_retrievals) + list(self._incremental_chunks)

    def get_complete_context(self) -> Dict[str, Any]:
        if not self._current_package:
            return {}

        return {
            "baseline_warm_slice": list(self._baseline_warm_slice),
            "baseline_retrievals": list(self._baseline_retrievals),
            "warm_expansions": list(self._warm_expansions),
            "incremental_chunks": list(self._incremental_chunks),
            "package": self._current_package,
            "transition": self._transition,
            "analysis": self._analysis,
        }

    def get_memory_summary(self) -> Dict[str, Any]:
        if not self._current_package:
            return {}

        summary = {
            "baseline_chunks": len(self._current_package.baseline_chunks),
            "additional_chunks": len(self._current_package.additional_chunks),
            "divergence_detected": self._current_package.divergence_detected,
            "divergence_confidence": round(self._current_package.divergence_confidence, 3),
            "remaining_budget": self._transition.remaining_budget if self._transition else 0,
        }
        if self._current_package.gap_analysis:
            summary["gap_analysis"] = self._current_package.gap_analysis
        return summary
