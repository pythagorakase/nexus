"""Divergence detection heuristics for LORE's Pass 2."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Set, Tuple

from .context_state import ContextPackage, PassTransition

logger = logging.getLogger("nexus.memory.divergence")

_STOPWORDS = {
    "the",
    "and",
    "with",
    "that",
    "this",
    "from",
    "into",
    "your",
    "have",
    "what",
    "when",
    "where",
    "who",
    "about",
    "just",
    "like",
    "into",
    "then",
    "them",
    "they",
    "their",
    "been",
    "were",
    "will",
    "would",
    "could",
    "should",
    "might",
    "again",
    "still",
    "even",
}


@dataclass
class DivergenceResult:
    """Structured result describing divergence detection outcome."""

    detected: bool
    confidence: float
    gap_terms: List[str] = field(default_factory=list)
    missing_entities: Set[str] = field(default_factory=set)
    missing_themes: Set[str] = field(default_factory=set)
    gap_analysis: Dict[str, str] = field(default_factory=dict)


class DivergenceDetector:
    """Simple heuristic-based divergence detector."""

    def __init__(self, threshold: float = 0.7) -> None:
        self.threshold = threshold

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def detect(
        self,
        user_input: str,
        baseline: Optional[ContextPackage],
        transition: Optional[PassTransition],
    ) -> DivergenceResult:
        """Compare user input against Pass 1 baseline context."""

        if not user_input or not baseline:
            return DivergenceResult(False, 0.0)

        normalized_entities = {
            self._normalize(name): name for name in baseline.baseline_entities.keys()
        }
        baseline_themes = {self._normalize(theme) for theme in baseline.baseline_themes}
        expected = {
            self._normalize(theme)
            for theme in (transition.expected_user_themes if transition else [])
            if theme
        }

        entity_tokens = self._extract_named_tokens(user_input)
        keyword_tokens = self._extract_keywords(user_input)

        missing_entities, entity_gap_terms = self._compute_missing_tokens(
            entity_tokens, normalized_entities, baseline_themes, expected
        )
        missing_themes, theme_gap_terms = self._compute_missing_tokens(
            keyword_tokens, None, baseline_themes, expected
        )

        gap_terms = sorted({*entity_gap_terms, *theme_gap_terms})

        gap_analysis = {}
        for term in gap_terms:
            if term in entity_gap_terms:
                gap_analysis[term] = (
                    "Entity or reference not present in Pass 1 baseline context"
                )
            else:
                gap_analysis[term] = (
                    "Theme or topic absent from Pass 1 baseline context"
                )

        confidence = self._calculate_confidence(
            entity_tokens,
            keyword_tokens,
            missing_entities,
            missing_themes,
        )
        detected = bool(gap_terms) and confidence >= self.threshold

        logger.debug(
            "Divergence detection completed: detected=%s confidence=%.2f gaps=%s",
            detected,
            confidence,
            gap_terms,
        )

        return DivergenceResult(
            detected=detected,
            confidence=confidence,
            gap_terms=gap_terms,
            missing_entities=missing_entities,
            missing_themes=missing_themes,
            gap_analysis=gap_analysis,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _normalize(text: str) -> str:
        return re.sub(r"\s+", " ", text.strip().lower()) if text else ""

    def _extract_named_tokens(self, text: str) -> Dict[str, str]:
        """Return capitalized entities and quoted strings."""

        tokens: Dict[str, str] = {}
        for match in re.finditer(r"([A-Z][\w']+(?:\s+[A-Z][\w']+)*)", text):
            original = match.group(1).strip()
            normalized = self._normalize(original)
            if normalized and normalized not in tokens:
                tokens[normalized] = original

        # Capture quoted terms (for things like "Pete's Silo")
        for match in re.finditer(r"['\"]([^'\"]{2,})['\"]", text):
            original = match.group(1).strip()
            normalized = self._normalize(original)
            if normalized and normalized not in tokens:
                tokens[normalized] = original

        return tokens

    def _extract_keywords(self, text: str) -> Dict[str, str]:
        tokens: Dict[str, str] = {}
        for raw in re.findall(r"\b[\w'][\w'-]{3,}\b", text):
            normalized = self._normalize(raw)
            if (
                normalized
                and normalized not in _STOPWORDS
                and not normalized.isdigit()
            ):
                tokens.setdefault(normalized, raw)
        return tokens

    def _compute_missing_tokens(
        self,
        tokens: Dict[str, str],
        baseline_entities: Optional[Dict[str, str]],
        baseline_themes: Set[str],
        expected: Set[str],
    ) -> Tuple[Set[str], Set[str]]:
        missing: Set[str] = set()
        gap_terms: Set[str] = set()

        for normalized, original in tokens.items():
            if normalized in expected:
                continue
            if baseline_entities is not None and normalized in baseline_entities:
                continue
            if normalized in baseline_themes:
                continue
            missing.add(original)
            gap_terms.add(original)
        return missing, gap_terms

    def _calculate_confidence(
        self,
        entity_tokens: Dict[str, str],
        keyword_tokens: Dict[str, str],
        missing_entities: Iterable[str],
        missing_themes: Iterable[str],
    ) -> float:
        entity_count = len(entity_tokens)
        keyword_count = len(keyword_tokens)

        max_score = entity_count * 1.0 + keyword_count * 0.5
        if max_score <= 0:
            return 0.0

        score = len(set(missing_entities)) * 1.0 + len(set(missing_themes)) * 0.5
        return min(1.0, score / max_score)
