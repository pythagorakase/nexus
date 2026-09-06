"""Shared result value for active entity-based divergence detection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Set


@dataclass
class DivergenceResult:
    """Outcome of the active entity-based divergence detector."""

    detected: bool
    confidence: float
    gaps: Dict[str, str]
    unmatched_entities: Set[str]
    references_seen: Set[str]

    def to_dict(self) -> Dict[str, object]:
        """Return the stable, JSON-serializable Pass-2 result shape."""

        return {
            "detected": self.detected,
            "confidence": round(self.confidence, 3),
            "gaps": self.gaps,
            "unmatched_entities": sorted(self.unmatched_entities),
            "references_seen": sorted(self.references_seen),
        }
