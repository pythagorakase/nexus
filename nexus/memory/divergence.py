"""User divergence detection utilities."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, Optional, Set

from .context_state import ContextPackage, PassTransition

logger = logging.getLogger(__name__)


@dataclass
class DivergenceResult:
    """Outcome of the divergence detector."""

    detected: bool
    confidence: float
    gaps: Dict[str, str]
    unmatched_entities: Set[str]
    references_seen: Set[str]

    def to_dict(self) -> Dict[str, object]:
        return {
            "detected": self.detected,
            "confidence": round(self.confidence, 3),
            "gaps": self.gaps,
            "unmatched_entities": sorted(self.unmatched_entities),
            "references_seen": sorted(self.references_seen),
        }


class DivergenceDetector:
    """Placeholder divergence detector - actual detection is done by LLM or entity detector.

    This class remains for backward compatibility but always returns no divergence.
    The real divergence detection is handled by:
    - LLMDivergenceDetector (primary, when LLM available)
    - HighSpecificityEntityDetector (fallback, when LLM unavailable)
    """

    def __init__(self, threshold: float = 0.7) -> None:
        self.threshold = max(0.0, min(1.0, threshold))
        logger.info(
            "DivergenceDetector initialized as placeholder - actual detection via LLM or entity detector"
        )

    def detect(
        self,
        user_input: str,
        context: Optional[ContextPackage],
        transition: Optional[PassTransition],
    ) -> DivergenceResult:
        """Always returns no divergence - actual detection handled elsewhere."""
        # This is now just a placeholder - the manager uses entity detector directly
        return DivergenceResult(False, 0.0, {}, set(), set())
