"""High level manager orchestrating LORE's custom memory flows."""

from __future__ import annotations

import logging
import re
from collections import Counter
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional

from .context_state import ContextPackage, ContextStateManager, PassTransition
from .divergence import DivergenceDetector, DivergenceResult
from .incremental import IncrementalRetriever
from .query_memory import QueryMemory

logger = logging.getLogger(__name__)


@dataclass
class Pass2Update:
    """Information returned after handling user input (Pass 2)."""

    divergence: DivergenceResult
    retrieved_chunks: List[Dict[str, Any]]
    tokens_used: int
    baseline_available: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "divergence": self.divergence.to_dict(),
            "retrieved_chunk_ids": [chunk.get("chunk_id") or chunk.get("id") for chunk in self.retrieved_chunks],
            "tokens_used": self.tokens_used,
            "baseline_available": self.baseline_available,
        }


class ContextMemoryManager:
    """Coordinate Pass 1 baseline storage and Pass 2 incremental retrieval."""

    def __init__(
        self,
        settings: Dict[str, Any],
        memnon: Optional[object] = None,
        llm_manager: Optional[object] = None,
        token_manager: Optional[object] = None,
    ) -> None:
        self.settings = settings
        memory_settings = settings.get("memory", {})
        self.pass2_reserve = float(memory_settings.get("pass2_budget_reserve", 0.25))
        self.divergence_threshold = float(memory_settings.get("divergence_threshold", 0.7))
        self.warm_slice_default = bool(memory_settings.get("warm_slice_default", True))
        self.max_sql_iterations = int(memory_settings.get("max_sql_iterations", 5))

        self.context_state = ContextStateManager()
        self.query_memory = QueryMemory(max_iterations=self.max_sql_iterations)
        self.divergence_detector = DivergenceDetector(threshold=self.divergence_threshold)
        self.incremental = IncrementalRetriever(
            memnon=memnon,
            context_state=self.context_state,
            query_memory=self.query_memory,
            warm_slice_default=self.warm_slice_default,
        )

        self.llm_manager = llm_manager
        self.token_manager = token_manager

    def get_memory_summary(self) -> Dict[str, Any]:
        """Get a summary of the current memory state for status reporting."""
        current_package = self.context_state.get_current_context()
        query_snapshot = self.query_memory.snapshot()
        pass1_usage = {}
        pass2_usage = {}

        if current_package:
            pass1_usage = {
                "baseline_tokens": current_package.token_usage.get("baseline_tokens", 0),
                "reserved_for_pass2": current_package.token_usage.get("reserved_for_pass2", 0),
            }
            pass2_usage = {
                "reserve_shortfall": current_package.token_usage.get("reserve_shortfall", 0),
                "remaining_budget": self.context_state.get_remaining_budget(),
            }
        return {
            "pass1": {
                "baseline_chunks": len(current_package.baseline_chunks) if current_package else 0,
                "baseline_themes": current_package.baseline_themes if current_package else [],
                "token_usage": pass1_usage,
            },
            "pass2": {
                "divergence_detected": current_package.divergence_detected if current_package else False,
                "divergence_confidence": current_package.divergence_confidence if current_package else 0.0,
                "additional_chunks": len(current_package.additional_chunks) if current_package else 0,
                "token_reserve_percent": int(self.pass2_reserve * 100),
                "usage": pass2_usage,
            },
            "query_memory": {
                "history": query_snapshot,
                "max_iterations": self.query_memory.max_iterations,
            },
            "settings": {
                "divergence_threshold": self.divergence_threshold,
                "warm_slice_default": self.warm_slice_default
            }
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def handle_storyteller_response(
        self,
        narrative: str,
        warm_slice: Optional[Iterable[Dict[str, Any]]] = None,
        retrieved_passages: Optional[Iterable[Dict[str, Any]]] = None,
        token_usage: Optional[Dict[str, int]] = None,
        assembled_context: Optional[Dict[str, Any]] = None,
    ) -> ContextPackage:
        """Run Pass 1 analysis and store baseline context for the next turn."""

        analysis = self._analyze_storyteller_output(narrative)
        baseline_entities = {
            "characters": analysis.get("characters", []),
            "locations": analysis.get("locations", []),
            "keywords": analysis.get("keywords", []),
        }
        baseline_themes = analysis.get("themes", [])
        expected_user_themes = analysis.get("expected", [])

        baseline_chunks: set[int] = set()
        chunk_details: List[Dict[str, Any]] = []

        for collection in (warm_slice or []):
            chunk_id = self._extract_chunk_id(collection)
            if chunk_id is not None:
                baseline_chunks.add(chunk_id)
                chunk_details.append({"chunk_id": chunk_id, **collection})

        for passage in (retrieved_passages or []):
            chunk_id = self._extract_chunk_id(passage)
            if chunk_id is not None:
                baseline_chunks.add(chunk_id)
                chunk_details.append({"chunk_id": chunk_id, **passage})

        token_usage = token_usage or {}
        baseline_tokens = sum(
            token_usage.get(key, 0) for key in ("warm_slice", "structured", "augmentation")
        )
        total_available = token_usage.get("total_available", 0)
        reserved_for_pass2 = max(0, int(total_available * self.pass2_reserve))
        remaining_budget = max(0, total_available - baseline_tokens)
        reserve_shortfall = max(0, reserved_for_pass2 - remaining_budget)

        package = ContextPackage(
            baseline_chunks=baseline_chunks,
            baseline_entities=baseline_entities,
            baseline_themes=baseline_themes,
            token_usage={
                **token_usage,
                "baseline_tokens": baseline_tokens,
                "reserved_for_pass2": reserved_for_pass2,
                "reserve_shortfall": reserve_shortfall,
            },
        )

        transition = PassTransition(
            storyteller_output=narrative,
            expected_user_themes=expected_user_themes,
            assembled_context=assembled_context or {},
            remaining_budget=remaining_budget,
        )

        self.context_state.store_baseline(package, transition, chunk_details)
        # Pass 2 queries are always reset when a new baseline is stored
        self.query_memory.reset_pass("pass2")
        logger.debug(
            "Pass 1 baseline stored: %s baseline chunks, %s expected themes, remaining budget=%s",
            len(baseline_chunks),
            len(expected_user_themes),
            remaining_budget,
        )
        return package

    # ------------------------------------------------------------------
    # Pass 2: User Input Handling
    # ------------------------------------------------------------------
    def handle_user_input(
        self,
        user_input: str,
        token_counts: Optional[Dict[str, int]] = None,
    ) -> Pass2Update:
        """Run Pass 2 divergence analysis and retrieve incremental context if needed."""

        context = self.context_state.context
        transition = self.context_state.transition
        divergence = self.divergence_detector.detect(user_input, context, transition)
        self.context_state.update_divergence(divergence.detected, divergence.confidence, divergence.gaps)

        if not context or not transition:
            logger.debug("No baseline context available; skipping incremental retrieval")
            return Pass2Update(divergence, [], 0, baseline_available=False)

        if token_counts and "total_available" in token_counts:
            # Adjust remaining budget if calculation changed significantly for this turn
            total_available = token_counts.get("total_available", transition.remaining_budget)
            baseline_tokens = context.token_usage.get("baseline_tokens", 0)
            reserve = int(total_available * self.pass2_reserve)
            new_budget = max(0, total_available - baseline_tokens)
            self.context_state.adjust_budget(new_budget)
            context.token_usage["reserved_for_pass2"] = reserve
            context.token_usage["reserve_shortfall"] = max(0, reserve - new_budget)

        budget = self.context_state.get_remaining_budget()
        retrieved: List[Dict[str, Any]] = []
        tokens_used = 0

        if divergence.detected and budget > 0:
            retrieved, tokens_used = self.incremental.retrieve_gap_context(divergence.gaps, budget)
        elif not divergence.detected and budget > 0:
            retrieved, tokens_used = self.incremental.expand_warm_slice(budget)

        if retrieved:
            new_chunks = self.context_state.register_additional_chunks(retrieved)
            tokens_consumed = self.context_state.consume_budget(tokens_used)
            logger.debug(
                "Pass 2 retrieved %s new chunks (tokens used=%s, consumed=%s)",
                len(new_chunks),
                tokens_used,
                tokens_consumed,
            )
        else:
            tokens_consumed = 0

        if context:
            reserve = context.token_usage.get("reserved_for_pass2", 0)
            context.token_usage["reserve_shortfall"] = max(
                0, reserve - self.context_state.get_remaining_budget()
            )

        return Pass2Update(divergence, retrieved, tokens_consumed, baseline_available=True)

    # ------------------------------------------------------------------
    # Helper Methods
    # ------------------------------------------------------------------
    def augment_warm_slice(self, warm_slice: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Merge existing warm slice chunks with any incremental additions."""

        if not warm_slice:
            warm_slice = []

        # Register baseline warm slice for deduplication in future passes
        self.context_state.register_chunks(warm_slice)

        additions = self.context_state.get_additional_chunk_details()
        if not additions:
            return warm_slice

        known_ids = {self._extract_chunk_id(chunk) for chunk in warm_slice}
        for chunk in additions:
            chunk_id = self._extract_chunk_id(chunk)
            if chunk_id is None or chunk_id in known_ids:
                continue
            warm_slice.append(chunk)
            known_ids.add(chunk_id)

        return warm_slice

    def record_pass1_query(self, query: str) -> None:
        """Record a query executed during Pass 1 for future deduplication."""
        self.query_memory.record("pass1", query)

    def reset_pass1_queries(self) -> None:
        self.query_memory.reset_pass("pass1")

    def get_state(self) -> Dict[str, Any]:
        """Return a snapshot of the current memory state (for logging/debug)."""
        package = self.context_state.context
        transition = self.context_state.transition
        return {
            "context": package,
            "transition": transition,
            "queries": self.query_memory.snapshot(),
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _analyze_storyteller_output(self, narrative: str) -> Dict[str, Any]:
        """Lightweight heuristic analysis of storyteller output."""
        text = narrative or ""
        if not text.strip():
            return {"characters": [], "locations": [], "keywords": [], "themes": [], "expected": []}

        character_candidates = re.findall(r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)", text)
        characters: List[str] = []
        locations: List[str] = []

        for candidate in character_candidates:
            candidate = candidate.strip()
            if candidate.lower() in {"you", "the", "she", "he", "they"}:
                continue
            if any(token in {"Street", "District", "Bay", "Zone", "Tower", "Market"} for token in candidate.split()):
                locations.append(candidate)
            else:
                characters.append(candidate)

        tokens = [token.lower() for token in re.findall(r"[a-zA-Z']+", text)]
        token_counts = Counter(token for token in tokens if len(token) > 4)
        keywords = [word for word, count in token_counts.most_common(8)]

        # Themes: top keywords filtered for variety
        themes = keywords[:5]

        expected = list(dict.fromkeys(characters + themes))[:10]

        return {
            "characters": sorted(set(characters)),
            "locations": sorted(set(locations)),
            "keywords": keywords,
            "themes": themes,
            "expected": expected,
        }

    def _extract_chunk_id(self, chunk: Dict[str, Any]) -> Optional[int]:
        chunk_id = chunk.get("chunk_id") or chunk.get("id")
        if chunk_id is None:
            return None
        try:
            return int(chunk_id)
        except (TypeError, ValueError):
            return None
