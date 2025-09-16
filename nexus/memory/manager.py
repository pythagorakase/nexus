"""High-level interface to the custom memory system."""

from __future__ import annotations

import logging
from collections import Counter
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .context_state import ContextPackage, ContextStateManager
from .divergence import DivergenceDetector
from .incremental import IncrementalRetriever
from .query_memory import QueryMemory

logger = logging.getLogger("nexus.memory.manager")


class ContextMemoryManager:
    """Coordinates context storage, divergence detection, and incremental retrieval."""

    def __init__(self, settings: Optional[Dict[str, Any]] = None, memnon: Optional[Any] = None) -> None:
        self.settings = settings or {}
        self.memnon = memnon

        self.memory_config = self.settings.get("memory", {})
        self.pass2_reserve = float(self.memory_config.get("pass2_budget_reserve", 0.25))
        self.divergence_threshold = float(self.memory_config.get("divergence_threshold", 0.7))
        self.warm_slice_default = bool(self.memory_config.get("warm_slice_default", True))
        self.max_iterations = int(self.memory_config.get("max_sql_iterations", 5))

        self.context_state = ContextStateManager()
        self.divergence_detector = DivergenceDetector(self.divergence_threshold)
        self.query_memory = QueryMemory(self.max_iterations)
        self.incremental = IncrementalRetriever(memnon=memnon, context_state=self.context_state, settings=self.memory_config)

        self.total_budget = self._resolve_total_budget()
        self.pass2_budget = int(self.total_budget * self.pass2_reserve)

    # ------------------------------------------------------------------
    # Initialization helpers
    # ------------------------------------------------------------------
    def update_memnon(self, memnon: Any) -> None:
        self.memnon = memnon
        self.incremental.update_memnon(memnon)

    def _resolve_total_budget(self) -> int:
        lore_settings = self.settings.get("Agent Settings", {}).get("LORE", {})
        token_settings = lore_settings.get("token_budget", {})
        return int(token_settings.get("apex_context_window", 200000))

    # ------------------------------------------------------------------
    # Pass 1 handling
    # ------------------------------------------------------------------
    def handle_storyteller_response(self, narrative: str, turn_context: Optional[Any]) -> ContextPackage:
        """Store baseline context after Storyteller output (Pass 1)."""

        if not narrative:
            logger.debug("No narrative provided for baseline storage")
            return self.context_state.context

        warm_slice_chunks = []
        retrieved_chunks = []
        token_usage: Dict[str, int] = {}
        baseline_entities: Dict[str, Any] = {}
        assembled_context: Dict[str, Any] = {}

        if turn_context is not None:
            assembled_context = getattr(turn_context, "context_payload", {}) or {}
            token_usage = getattr(turn_context, "token_counts", {}) or {}
            baseline_entities = getattr(turn_context, "entity_data", {}) or {}

            warm_info = assembled_context.get("warm_slice", {}) if isinstance(assembled_context, dict) else {}
            warm_slice_chunks = warm_info.get("chunks", []) or []

            retrieved_info = assembled_context.get("retrieved_passages", {}) if isinstance(assembled_context, dict) else {}
            retrieved_chunks = retrieved_info.get("results", []) or []

        chunk_details = list(warm_slice_chunks) + list(retrieved_chunks)
        chunk_ids = self._collect_chunk_ids(chunk_details)

        analysis = self._basic_analysis(narrative)
        baseline_themes = analysis.get("themes", [])
        expected_user_themes = self._determine_expected_themes(analysis, turn_context)

        baseline_usage = sum(token_usage.values()) if token_usage else 0
        remaining_budget = max(0, self.pass2_budget - baseline_usage)
        self.context_state.store_baseline_context(
            chunk_ids=chunk_ids,
            entities=baseline_entities,
            themes=baseline_themes,
            token_usage=token_usage,
            chunk_details=chunk_details,
            storyteller_output=narrative,
            expected_user_themes=expected_user_themes,
            assembled_context=assembled_context,
            remaining_budget=remaining_budget,
            analysis=analysis,
        )

        # Record pass 1 queries for future duplication checks
        self.query_memory.reset()
        pass1_queries = []
        if turn_context is not None:
            deep_state = getattr(turn_context, "phase_states", {}).get("deep_queries", {})
            pass1_queries = deep_state.get("query_texts", []) if isinstance(deep_state, dict) else []
        if pass1_queries:
            self.query_memory.record_queries(1, pass1_queries)
        self.query_memory.reset_pass(2)

        logger.info(
            "Stored baseline context: %d chunks, %d entities, %d themes",
            len(self.context_state.context.baseline_chunks),
            len(baseline_entities),
            len(baseline_themes),
        )
        return self.context_state.context

    # ------------------------------------------------------------------
    # Pass 2 handling
    # ------------------------------------------------------------------
    def process_user_input(self, user_input: str) -> Dict[str, Any]:
        """Detect divergence and retrieve additional context if needed."""

        self.context_state.record_user_input(user_input)

        if not self.context_state.transition:
            logger.debug("No baseline transition available; skipping divergence handling")
            return {"status": "no_baseline"}

        divergence = self.divergence_detector.evaluate(user_input, self.context_state)
        self.context_state.mark_divergence(divergence.detected, divergence.confidence, divergence.gap_analysis)

        remaining_budget = self.context_state.transition.remaining_budget
        logger.debug("Remaining token budget before Pass 2 retrieval: %s", remaining_budget)

        retrieval_summary: Dict[str, Any] = {
            "divergence_detected": divergence.detected,
            "divergence_confidence": divergence.confidence,
            "gap_terms": list(divergence.gap_analysis.keys()),
            "queries_reserved": [],
            "chunks_added": [],
        }

        if remaining_budget <= 0:
            logger.debug("No token budget available for Pass 2 retrieval")
            retrieval_summary["status"] = "no_budget"
            retrieval_summary["remaining_budget"] = 0
            return retrieval_summary

        query_requests: List[Tuple[str, str]] = []
        if divergence.detected and divergence.gap_analysis:
            for term, reason in divergence.gap_analysis.items():
                if self.query_memory.reserve_query(2, term):
                    query_requests.append((term, reason))
            retrieval_summary["queries_reserved"] = [term for term, _ in query_requests]

        tokens_consumed = 0
        additional_chunks: List[Dict[str, Any]] = []

        if query_requests:
            additional_chunks, tokens_consumed = self.incremental.retrieve_incremental(query_requests, remaining_budget)
            retrieval_summary["status"] = "divergence_handled"
        elif self.warm_slice_default:
            additional_chunks, tokens_consumed = self.incremental.expand_warm_slice(remaining_budget)
            retrieval_summary["queries_reserved"] = []
            retrieval_summary["status"] = "warm_expansion" if additional_chunks else "no_action"
        else:
            retrieval_summary["status"] = "no_action"

        if tokens_consumed:
            self.context_state.update_remaining_budget(max(0, remaining_budget - tokens_consumed))

        if additional_chunks:
            retrieval_summary["chunks_added"] = [
                self.context_state._extract_chunk_id(chunk)  # type: ignore[attr-defined]
                for chunk in additional_chunks
            ]

        retrieval_summary["remaining_budget"] = self.get_remaining_budget()

        logger.debug(
            "Pass 2 retrieval complete: %d chunk(s) added, %d tokens consumed",
            len(additional_chunks),
            tokens_consumed,
        )
        return retrieval_summary

    # ------------------------------------------------------------------
    # Query coordination
    # ------------------------------------------------------------------
    def prepare_queries_for_pass(self, pass_index: int, queries: Sequence[str]) -> List[str]:
        allowed: List[str] = []
        for query in queries:
            if self.query_memory.reserve_query(pass_index, query):
                allowed.append(query)
        return allowed

    # ------------------------------------------------------------------
    # Context accessors
    # ------------------------------------------------------------------
    def augment_warm_slice(self, warm_slice: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return self.context_state.get_augmented_warm_slice(warm_slice)

    def get_context_package(self) -> ContextPackage:
        return self.context_state.context

    def get_context_summary(self) -> Dict[str, Any]:
        return self.context_state.get_context_summary()

    def get_remaining_budget(self) -> int:
        if not self.context_state.transition:
            return 0
        return self.context_state.transition.remaining_budget

    def get_query_history(self, pass_index: Optional[int] = None) -> List[str]:
        return self.query_memory.get_queries(pass_index)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _collect_chunk_ids(self, chunks: Iterable[Dict[str, Any]]) -> List[int]:
        ids: List[int] = []
        for chunk in chunks:
            if not isinstance(chunk, dict):
                continue
            chunk_id = chunk.get("chunk_id") or chunk.get("id")
            try:
                ids.append(int(chunk_id))
            except (TypeError, ValueError):
                continue
        return ids

    def _basic_analysis(self, narrative: str) -> Dict[str, Any]:
        tokens = [tok for tok in narrative.split() if len(tok) > 3]
        cleaned = [tok.strip(".,!?;:").lower() for tok in tokens if tok.strip(".,!?;:")]
        freq = Counter(cleaned)
        top_terms = [term for term, _ in freq.most_common(6)]
        entities = self._extract_entities(narrative)
        return {"themes": top_terms[:5], "entities": list(entities)}

    def _determine_expected_themes(self, analysis: Dict[str, Any], turn_context: Optional[Any]) -> List[str]:
        expected = set(analysis.get("themes", []))
        if turn_context is not None:
            warm_analysis = getattr(turn_context, "phase_states", {}).get("warm_analysis", {})
            if isinstance(warm_analysis, dict):
                analysis_obj = warm_analysis.get("analysis", {})
                if isinstance(analysis_obj, dict):
                    for key in ("themes", "expected_topics", "narrative_goals"):
                        values = analysis_obj.get(key, [])
                        if isinstance(values, str):
                            expected.add(values)
                        elif isinstance(values, Iterable):
                            expected.update(str(v) for v in values)
        return [str(theme).lower() for theme in expected if theme]

    def _extract_entities(self, narrative: str) -> List[str]:
        entities: List[str] = []
        current: List[str] = []
        for token in narrative.split():
            cleaned = token.strip(".,!?;:")
            if cleaned.istitle() and cleaned.lower() not in {"the", "and", "with", "from"}:
                current.append(cleaned)
            else:
                if len(current) == 1:
                    entities.append(current[0])
                elif len(current) > 1:
                    entities.append(" ".join(current))
                current = []
        if current:
            if len(current) == 1:
                entities.append(current[0])
            else:
                entities.append(" ".join(current))
        return entities

