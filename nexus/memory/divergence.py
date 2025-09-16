"""Divergence detection utilities for LORE Pass 2."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, Iterable, List, Sequence, Set

from .context_state import ContextPackage


@dataclass
class DivergenceResult:
    """Result from divergence detection."""

    detected: bool
    confidence: float
    gaps: Dict[str, str]
    missing_terms: List[str]
    covered_terms: List[str]


class DivergenceDetector:
    """Simple lexical divergence detector.

    The detector compares salient tokens from the user input against the
    baseline themes and entities captured in :class:`ContextPackage`.
    """

    def __init__(self, threshold: float = 0.7) -> None:
        self.threshold = threshold

    def detect(
        self,
        user_input: str,
        context: ContextPackage,
        expected_themes: Sequence[str] | None = None,
    ) -> DivergenceResult:
        """Return a :class:`DivergenceResult` describing divergence.

        Args:
            user_input: Raw user utterance for the new turn.
            context: Baseline context assembled during Pass 1.
            expected_themes: Themes Pass 1 predicted might appear.
        """

        if not user_input:
            return DivergenceResult(False, 0.0, {}, [], [])

        expected_themes = expected_themes or []
        baseline_terms = self._build_baseline_terms(context, expected_themes)
        user_terms = self._extract_terms(user_input)

        missing_terms = [term for term in user_terms if term not in baseline_terms]
        covered_terms = [term for term in user_terms if term in baseline_terms]

        # Penalize when expected themes are absent from the user input.
        missing_expected = [theme for theme in expected_themes if theme and theme.lower() not in user_input.lower()]

        denominator = max(1, len(user_terms) + len(expected_themes))
        confidence = min(1.0, (len(missing_terms) + len(missing_expected)) / denominator)
        detected = bool(missing_terms or missing_expected) and confidence >= self.threshold

        gaps = {
            term: "Not present in Pass 1 baseline context"
            for term in missing_terms
        }
        for theme in missing_expected:
            gaps.setdefault(theme, "Expected theme not referenced by user input")

        return DivergenceResult(detected, confidence, gaps, missing_terms, covered_terms)

    # Internal helpers -------------------------------------------------

    def _build_baseline_terms(
        self,
        context: ContextPackage,
        expected_themes: Sequence[str],
    ) -> Set[str]:
        terms: Set[str] = set()
        if context:
            for name, value in (context.baseline_entities or {}).items():
                terms.add(name.lower())
                if isinstance(value, dict):
                    for sub_val in value.values():
                        if isinstance(sub_val, str):
                            terms.update(self._extract_terms(sub_val))
                        elif isinstance(sub_val, Iterable):
                            for item in sub_val:
                                if isinstance(item, str):
                                    terms.update(self._extract_terms(item))
                elif isinstance(value, str):
                    terms.update(self._extract_terms(value))
            for theme in context.baseline_themes:
                terms.add(theme.lower())
            # Include simple numeric chunk ids for lexical coverage.
            terms.update(str(chunk_id) for chunk_id in context.baseline_chunks)
        for theme in expected_themes or []:
            terms.add(theme.lower())
        return terms

    def _extract_terms(self, text: str) -> List[str]:
        """Extract salient tokens from text."""

        tokens = re.findall(r"[A-Za-z][A-Za-z0-9'_]{2,}", text or "")
        normalized = {token.lower() for token in tokens}
        # Filter out very common stop-like words.
        stop_words = {"the", "this", "that", "with", "have", "from", "into", "about", "your", "their"}
        return [token for token in normalized if token not in stop_words]

