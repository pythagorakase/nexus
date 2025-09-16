"""Public interface for LORE's custom two-pass memory system."""

from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, List, Optional, Sequence

from nexus.agents.lore.utils.chunk_operations import calculate_chunk_tokens

from .context_state import ContextPackage, ContextStateManager, PassTransition
from .divergence import DivergenceDetector
from .incremental import IncrementalRetriever
from .query_memory import QueryMemory

logger = logging.getLogger("nexus.memory.manager")


class ContextMemoryManager:
    """Coordinates Pass 1 baseline storage and Pass 2 augmentation."""

    def __init__(
        self,
        settings: Optional[Dict[str, Any]] = None,
        *,
        memnon: Optional[Any] = None,
        token_manager: Optional[Any] = None,
        llm_manager: Optional[Any] = None,
    ) -> None:
        self.settings = settings or {}
        memory_cfg = self.settings.get("memory", {})

        self.pass2_reserve = float(memory_cfg.get("pass2_budget_reserve", 0.25))
        self.divergence_threshold = float(memory_cfg.get("divergence_threshold", 0.7))
        self.warm_slice_default = bool(memory_cfg.get("warm_slice_default", True))
        self.max_sql_iterations = int(memory_cfg.get("max_sql_iterations", 5))

        self.memnon = memnon
        self.token_manager = token_manager
        self.llm_manager = llm_manager

        self.state = ContextStateManager()
        self.query_memory = QueryMemory(self.max_sql_iterations)
        self.divergence_detector = DivergenceDetector(self.divergence_threshold)
        self.incremental = IncrementalRetriever(
            memnon=self.memnon,
            query_memory=self.query_memory,
            warm_slice_default=self.warm_slice_default,
        )

    # ------------------------------------------------------------------
    # Dependency updates
    # ------------------------------------------------------------------
    def refresh_memnon(self, memnon: Any) -> None:
        self.memnon = memnon
        self.incremental.memnon = memnon

    # ------------------------------------------------------------------
    # Pass 1 handling
    # ------------------------------------------------------------------
    def handle_storyteller_response(self, storyteller_output: str, turn_context: Any) -> None:
        """Store Pass 1 baseline context after Storyteller completes."""

        if not storyteller_output:
            logger.debug("No storyteller output provided; skipping baseline storage")
            self.state.reset()
            return

        warm_slice = getattr(turn_context, "warm_slice", []) or []
        retrieved_passages = getattr(turn_context, "retrieved_passages", []) or []
        entity_data = getattr(turn_context, "entity_data", {}) or {}
        phase_states = getattr(turn_context, "phase_states", {}) or {}
        analysis = phase_states.get("warm_analysis", {}).get("analysis", {})
        token_counts = getattr(turn_context, "token_counts", {}) or {}
        context_payload = getattr(turn_context, "context_payload", {}) or {}

        baseline_entities = self._extract_entities(entity_data, analysis)
        baseline_themes = self._extract_themes(analysis, storyteller_output)
        baseline_chunks = self._collect_chunk_ids(warm_slice, retrieved_passages)
        token_usage = self._estimate_token_usage(warm_slice, retrieved_passages, storyteller_output)
        expected_themes = self._derive_expected_themes(
            analysis,
            storyteller_output,
            baseline_entities,
            baseline_themes,
        )
        remaining_budget = self._calculate_remaining_budget(token_counts, token_usage)

        package = ContextPackage(
            baseline_chunks=baseline_chunks,
            baseline_entities=baseline_entities,
            baseline_themes=baseline_themes,
            token_usage={**token_usage, "remaining_budget": remaining_budget},
        )
        transition = PassTransition(
            storyteller_output=storyteller_output,
            expected_user_themes=expected_themes,
            assembled_context=context_payload,
            remaining_budget=remaining_budget,
        )

        self.state.initialize_pass1(package, transition, warm_slice, retrieved_passages, analysis)
        self.query_memory.reset_pass(2)

        logger.debug(
            "Stored baseline context: %s baseline chunks, reserve=%s",
            len(baseline_chunks),
            remaining_budget,
        )

    # ------------------------------------------------------------------
    # Pass 2 handling
    # ------------------------------------------------------------------
    def handle_user_input(self, turn_context: Any) -> Dict[str, Any]:
        """Evaluate user input for divergence and retrieve incremental context."""

        baseline = self.state.get_baseline_context()
        summary: Dict[str, Any] = {}

        if not baseline:
            logger.debug("No Pass 1 baseline available; using default warm slice workflow")
            return summary

        divergence = self.divergence_detector.detect(
            turn_context.user_input,
            baseline,
            self.state.get_transition_state(),
        )
        self.state.update_divergence(divergence.detected, divergence.confidence)
        self.state.update_gap_analysis(divergence.gap_analysis)

        additions: List[Dict[str, Any]] = []
        warm_additions: List[Dict[str, Any]] = []
        aug_tokens = 0
        warm_tokens = 0

        if divergence.detected:
            additions, aug_tokens = self.incremental.retrieve_for_divergence(divergence, self.state)
            self.state.register_additional_chunks(
                additions,
                component="augmentation",
                token_usage=aug_tokens,
                as_warm_slice=False,
            )
        elif self.warm_slice_default:
            warm_additions, warm_tokens = self.incremental.expand_warm_slice(self.state)
            self.state.register_additional_chunks(
                warm_additions,
                component="warm_slice",
                token_usage=warm_tokens,
                as_warm_slice=True,
            )

        # Update turn context state
        combined_warm = self.state.get_warm_slice()
        turn_context.warm_slice = combined_warm
        turn_context.memory_state = self.state.get_memory_summary()

        if aug_tokens:
            turn_context.token_counts["augmentation"] = (
                turn_context.token_counts.get("augmentation", 0) + aug_tokens
            )
        if warm_tokens:
            turn_context.token_counts["warm_slice"] = (
                turn_context.token_counts.get("warm_slice", 0) + warm_tokens
            )
        if self.state.transition:
            turn_context.token_counts["remaining_pass2_budget"] = self.state.transition.remaining_budget

        summary.update(
            {
                "divergence_detected": divergence.detected,
                "confidence": divergence.confidence,
                "gap_analysis": divergence.gap_analysis,
                "added_chunk_ids": [chunk.get("id") for chunk in additions],
                "warm_slice_added": [chunk.get("id") for chunk in warm_additions],
                "remaining_budget": self.state.transition.remaining_budget if self.state.transition else 0,
            }
        )

        logger.debug(
            "Pass 2 summary: detected=%s confidence=%.2f additions=%s warm_additions=%s",
            divergence.detected,
            divergence.confidence,
            summary["added_chunk_ids"],
            summary["warm_slice_added"],
        )

        return summary

    def merge_incremental_results(self, turn_context: Any) -> None:
        """Inject divergence retrievals into the aggregated retrieval set."""

        incremental_chunks = self.state.get_incremental_chunks()
        if not incremental_chunks:
            return

        existing_ids = {chunk.get("id") for chunk in turn_context.retrieved_passages}
        merged = list(turn_context.retrieved_passages)

        for chunk in incremental_chunks:
            chunk_id = chunk.get("id")
            if not chunk_id or chunk_id in existing_ids:
                continue
            merged.append(chunk)
            existing_ids.add(chunk_id)

        turn_context.retrieved_passages = merged

    # ------------------------------------------------------------------
    # Query tracking utilities
    # ------------------------------------------------------------------
    def record_queries(self, pass_id: int, queries: Sequence[str], *, replace: bool = False) -> None:
        self.query_memory.record_queries(pass_id, list(queries), replace=replace)

    def get_memory_summary(self) -> Dict[str, Any]:
        return self.state.get_memory_summary()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _extract_entities(
        self,
        entity_data: Dict[str, Any],
        analysis: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        entities: Dict[str, Any] = {}
        for character in entity_data.get("characters", []):
            name = character.get("name")
            if name:
                entities[name] = character
        for location in entity_data.get("locations", []):
            name = location.get("name")
            if name:
                enriched = dict(location)
                enriched.setdefault("type", "location")
                entities[name] = enriched

        if analysis:
            for name in analysis.get("characters", []) or []:
                if name and name not in entities:
                    entities[name] = {"name": name, "type": "character"}
            for name in analysis.get("locations", []) or []:
                if name and name not in entities:
                    entities[name] = {"name": name, "type": "location"}
            for name in analysis.get("entities_for_retrieval", []) or []:
                if name and name not in entities:
                    entities[name] = {"name": name, "type": "entity"}

        return entities

    def _extract_themes(
        self,
        analysis: Optional[Dict[str, Any]],
        storyteller_output: str,
    ) -> List[str]:
        themes: List[str] = []
        if analysis:
            themes.extend(analysis.get("entities_for_retrieval", []) or [])
            if analysis.get("context_type"):
                themes.append(str(analysis.get("context_type")))
            themes.extend(analysis.get("locations", []) or [])
        keywords = list(self.divergence_detector._extract_keywords(storyteller_output).values())
        for keyword in keywords:
            if keyword not in themes:
                themes.append(keyword)
        return themes[:20]

    def _derive_expected_themes(
        self,
        analysis: Optional[Dict[str, Any]],
        storyteller_output: str,
        entities: Dict[str, Any],
        baseline_themes: Iterable[str],
    ) -> List[str]:
        expected: List[str] = []
        if analysis:
            expected.extend(analysis.get("entities_for_retrieval", []) or [])
            if analysis.get("context_type"):
                expected.append(str(analysis.get("context_type")))
        expected.extend(list(entities.keys()))
        expected.extend(list(baseline_themes))
        keywords = list(self.divergence_detector._extract_keywords(storyteller_output).values())
        for keyword in keywords[:8]:
            if keyword not in expected:
                expected.append(keyword)
        return expected[:25]

    def _collect_chunk_ids(
        self,
        warm_slice: List[Dict[str, Any]],
        retrieved: List[Dict[str, Any]],
    ) -> set:
        chunk_ids = {chunk.get("id") for chunk in warm_slice if chunk.get("id")}
        chunk_ids.update({chunk.get("id") for chunk in retrieved if chunk.get("id")})
        return chunk_ids

    def _estimate_token_usage(
        self,
        warm_slice: List[Dict[str, Any]],
        retrieved: List[Dict[str, Any]],
        storyteller_output: str,
    ) -> Dict[str, int]:
        warm_tokens = sum(self._estimate_tokens_from_text(self._chunk_text(chunk)) for chunk in warm_slice)
        retrieval_tokens = sum(self._estimate_tokens_from_text(self._chunk_text(chunk)) for chunk in retrieved)
        storyteller_tokens = self._estimate_tokens_from_text(storyteller_output)
        return {
            "warm_slice": warm_tokens,
            "retrieval": retrieval_tokens,
            "storyteller_output": storyteller_tokens,
            "baseline_total": warm_tokens + retrieval_tokens,
        }

    def _chunk_text(self, chunk: Dict[str, Any]) -> str:
        return (
            chunk.get("full_text")
            or chunk.get("raw_text")
            or chunk.get("text")
            or ""
        )

    def _estimate_tokens_from_text(self, text: str) -> int:
        if not text:
            return 0
        try:
            return calculate_chunk_tokens(text)
        except Exception:  # pragma: no cover - fallback
            return max(1, len(text) // 4)

    def _calculate_remaining_budget(
        self,
        token_counts: Dict[str, int],
        token_usage: Dict[str, int],
    ) -> int:
        total_available = int(token_counts.get("total_available", 0))
        baseline_used = token_usage.get("baseline_total", 0)
        remaining = max(0, total_available - baseline_used)
        reserve = int(total_available * self.pass2_reserve)
        return min(total_available, max(reserve, remaining))
