"""Context state tracking for LORE's two-pass memory system."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Set


@dataclass
class ContextPackage:
    """State container for baseline and incremental context."""

    baseline_chunks: Set[int] = field(default_factory=set)
    baseline_entities: Dict[str, Any] = field(default_factory=dict)
    baseline_themes: List[str] = field(default_factory=list)
    token_usage: Dict[str, int] = field(default_factory=dict)

    divergence_detected: bool = False
    divergence_confidence: float = 0.0
    additional_chunks: Set[int] = field(default_factory=set)
    gap_analysis: Dict[str, str] = field(default_factory=dict)

    def combined_chunk_ids(self) -> Set[int]:
        """Return the union of baseline and incremental chunk ids."""

        return set(self.baseline_chunks).union(self.additional_chunks)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the context package to a dictionary for logging/debugging."""

        return {
            "baseline_chunks": sorted(self.baseline_chunks),
            "baseline_entities": self.baseline_entities,
            "baseline_themes": list(self.baseline_themes),
            "token_usage": self.token_usage,
            "divergence_detected": self.divergence_detected,
            "divergence_confidence": self.divergence_confidence,
            "additional_chunks": sorted(self.additional_chunks),
            "gap_analysis": self.gap_analysis,
        }


@dataclass
class PassTransition:
    """Metadata captured between Storyteller output and next user turn."""

    storyteller_output: str
    expected_user_themes: List[str]
    assembled_context: Dict[str, Any]
    remaining_budget: int


class ContextStateManager:
    """Manage lifecycle of context packages across LORE passes."""

    def __init__(self) -> None:
        self._context_package: Optional[ContextPackage] = None
        self._pass_transition: Optional[PassTransition] = None

    def reset(self) -> None:
        """Clear any stored state."""

        self._context_package = None
        self._pass_transition = None

    def store_baseline_context(
        self,
        baseline_chunks: Iterable[int],
        baseline_entities: Dict[str, Any],
        baseline_themes: Iterable[str],
        token_usage: Dict[str, int],
    ) -> ContextPackage:
        """Persist baseline state gathered during Pass 1."""

        package = ContextPackage(
            baseline_chunks=set(int(c) for c in baseline_chunks),
            baseline_entities=dict(baseline_entities or {}),
            baseline_themes=list(dict.fromkeys(baseline_themes or [])),
            token_usage=dict(token_usage or {}),
        )
        self._context_package = package
        return package

    def update_pass_transition(self, transition: PassTransition) -> None:
        """Store transition metadata for next user turn."""

        self._pass_transition = transition

    def mark_divergence(
        self,
        detected: bool,
        confidence: float,
        additional_chunks: Iterable[int],
        gap_analysis: Dict[str, str],
    ) -> None:
        """Update context package with divergence results from Pass 2."""

        package = self._ensure_package()
        package.divergence_detected = detected
        package.divergence_confidence = max(0.0, min(1.0, confidence))
        package.additional_chunks.update(int(c) for c in additional_chunks)
        package.gap_analysis = dict(gap_analysis or {})

    def update_remaining_budget(self, remaining_budget: int) -> None:
        """Persist the updated Pass 2 budget."""

        if self._pass_transition:
            self._pass_transition.remaining_budget = max(0, int(remaining_budget))

    def extend_additional_chunks(self, chunk_ids: Iterable[int]) -> None:
        """Ensure the incremental chunk ids are tracked."""

        package = self._ensure_package()
        package.additional_chunks.update(int(c) for c in chunk_ids)

    def get_context_package(self) -> Optional[ContextPackage]:
        return self._context_package

    def get_pass_transition(self) -> Optional[PassTransition]:
        return self._pass_transition

    def get_remaining_budget(self) -> int:
        if self._pass_transition:
            return max(0, int(self._pass_transition.remaining_budget))
        return 0

    def _ensure_package(self) -> ContextPackage:
        if not self._context_package:
            self._context_package = ContextPackage()
        return self._context_package

