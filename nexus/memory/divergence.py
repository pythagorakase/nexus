"""Divergence detection for LORE's Pass 2 processing."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Dict, Iterable, Set

from .context_state import ContextStateManager

logger = logging.getLogger("nexus.memory.divergence")


@dataclass
class DivergenceResult:
    """Outcome of divergence detection."""

    detected: bool = False
    confidence: float = 0.0
    unexpected_terms: Set[str] = field(default_factory=set)
    missing_entities: Set[str] = field(default_factory=set)
    missing_themes: Set[str] = field(default_factory=set)
    gap_analysis: Dict[str, str] = field(default_factory=dict)

    @property
    def has_gaps(self) -> bool:
        return bool(self.gap_analysis)


class DivergenceDetector:
    """Simple heuristic divergence detector."""

    def __init__(self, threshold: float = 0.7) -> None:
        self.threshold = max(0.0, min(1.0, threshold))

    def evaluate(self, user_input: str, state: ContextStateManager) -> DivergenceResult:
        """Compare user input with baseline context and detect divergence."""

        logger.debug("Evaluating user input for divergence")
        result = DivergenceResult()

        if not user_input or not state or not state.transition:
            logger.debug("No baseline context available for divergence detection")
            return result

        expected_terms = state.get_expected_terms()
        logger.debug("Expected terms for comparison: %s", sorted(expected_terms))

        tokens = self._tokenize(user_input)
        unexpected_terms = {tok for tok in tokens if tok not in expected_terms}

        capitalized = self._extract_entities(user_input)
        known_entities = self._normalize_terms(self._flatten_entities(state.context.baseline_entities))
        missing_entities = {ent for ent in capitalized if ent.lower() not in known_entities}

        expected_themes = {theme.lower() for theme in state.context.baseline_themes}
        missing_themes = {tok for tok in unexpected_terms if tok in capitalized or tok in expected_themes}

        confidence = self._calculate_confidence(tokens, unexpected_terms, missing_entities)
        detected = bool(unexpected_terms or missing_entities) and confidence >= self.threshold

        gap_analysis: Dict[str, str] = {}
        if detected:
            for ent in missing_entities:
                gap_analysis[ent] = "Referenced entity not present in baseline context"
            for term in sorted(unexpected_terms):
                if term not in gap_analysis:
                    gap_analysis[term] = "Unexpected reference compared to baseline"

        result.detected = detected
        result.confidence = confidence
        result.unexpected_terms = unexpected_terms
        result.missing_entities = missing_entities
        result.missing_themes = missing_themes
        result.gap_analysis = gap_analysis

        logger.debug(
            "Divergence result: detected=%s confidence=%.3f unexpected=%s",
            detected,
            confidence,
            sorted(unexpected_terms),
        )

        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _tokenize(self, text: str) -> Set[str]:
        words = re.findall(r"[A-Za-z][A-Za-z0-9']+", text)
        return {w.lower() for w in words if len(w) > 2}

    def _extract_entities(self, text: str) -> Set[str]:
        candidates = set()
        for match in re.finditer(r"\b([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+)*)\b", text):
            phrase = match.group(1)
            if phrase in {"You", "The", "And", "But"}:
                continue
            candidates.add(phrase.strip())
        return candidates

    def _flatten_entities(self, entities: Dict[str, Iterable[str]]) -> Set[str]:
        flattened: Set[str] = set()
        if not isinstance(entities, dict):
            return flattened
        for value in entities.values():
            if isinstance(value, str):
                flattened.add(value)
            elif isinstance(value, Iterable):
                for item in value:
                    if isinstance(item, str):
                        flattened.add(item)
        return flattened

    def _normalize_terms(self, terms: Iterable[str]) -> Set[str]:
        return {term.lower() for term in terms if isinstance(term, str)}

    def _calculate_confidence(
        self,
        tokens: Set[str],
        unexpected_terms: Set[str],
        missing_entities: Set[str],
    ) -> float:
        if not tokens:
            return 0.0
        base_ratio = len(unexpected_terms) / max(len(tokens), 1)
        entity_bonus = 0.15 * len(missing_entities)
        confidence = min(1.0, base_ratio + entity_bonus)
        return confidence

