"""User divergence detection utilities."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Dict, Iterable, Optional, Set

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
    """Simple heuristic divergence detector comparing user input to baseline context."""

    def __init__(self, threshold: float = 0.7) -> None:
        self.threshold = max(0.0, min(1.0, threshold))

    # ------------------------------------------------------------------
    def detect(
        self,
        user_input: str,
        context: Optional[ContextPackage],
        transition: Optional[PassTransition],
    ) -> DivergenceResult:
        if not user_input or not context or not transition:
            return DivergenceResult(False, 0.0, {}, set(), set())

        normalized_refs = self._extract_references(user_input)
        if not normalized_refs:
            return DivergenceResult(False, 0.0, {}, set(), set())

        baseline_terms = self._collect_baseline_terms(context, transition)
        unmatched = normalized_refs - baseline_terms

        gaps: Dict[str, str] = {}
        if unmatched:
            for ref in sorted(unmatched):
                gaps[ref] = "Reference not present in baseline context"

        confidence = len(unmatched) / max(1, len(normalized_refs))
        detected = confidence >= self.threshold and bool(gaps)

        logger.debug(
            "Divergence detection: %s unmatched references (confidence=%.2f, threshold=%.2f)",
            len(unmatched),
            confidence,
            self.threshold,
        )

        return DivergenceResult(detected, confidence, gaps, unmatched, normalized_refs)

    # ------------------------------------------------------------------
    def _extract_references(self, text: str) -> Set[str]:
        tokens = re.findall(r"[A-Za-z][A-Za-z0-9'\-]+", text)
        normalized: Set[str] = set()
        for token in tokens:
            cleaned = token.strip("-'")
            if len(cleaned) < 4:
                continue
            if cleaned.lower() in {"this", "that", "what", "when", "where", "your", "have", "with"}:
                continue
            # Keep both lower-case and title-case variants for matching
            normalized.add(cleaned.lower())
        # Capture multi-word proper nouns (very simple heuristic)
        proper_nouns = re.findall(r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)", text)
        for noun in proper_nouns:
            normalized.add(noun.strip())
        return normalized

    def _collect_baseline_terms(
        self,
        context: ContextPackage,
        transition: PassTransition,
    ) -> Set[str]:
        terms: Set[str] = set()

        def _flatten(values: Iterable) -> Iterable[str]:
            for value in values:
                if isinstance(value, str):
                    yield value
                elif isinstance(value, Iterable):
                    for sub in _flatten(value):
                        yield sub
                elif isinstance(value, dict):
                    for sub in _flatten(value.values()):
                        yield sub

        baseline_entities = context.baseline_entities or {}
        for key, value in baseline_entities.items():
            for item in _flatten(value if isinstance(value, Iterable) else [value]):
                if isinstance(item, str) and item:
                    terms.add(item.lower())
                    terms.add(item)

        for theme in context.baseline_themes:
            if theme:
                terms.add(theme.lower())
                terms.add(theme)

        for expected in transition.expected_user_themes:
            if expected:
                terms.add(expected.lower())
                terms.add(expected)

        # Include words from the storyteller output itself
        for ref in self._extract_references(transition.storyteller_output):
            terms.add(ref)
            terms.add(ref.lower())

        return terms
