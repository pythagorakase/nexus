"""High-level memory manager coordinating Pass 1 and Pass 2."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from .context_state import ContextPackage, ContextStateManager, PassTransition
from .divergence import DivergenceDetector, DivergenceResult
from .incremental import IncrementalRetriever
from .query_memory import QueryMemory


class ContextMemoryManager:
    """Main interface used by LORE to coordinate memory operations."""

    def __init__(
        self,
        settings: Optional[Dict[str, Any]] = None,
        memnon: Optional[object] = None,
        token_manager: Optional[object] = None,
    ) -> None:
        self.settings = settings or {}
        memory_settings = self.settings.get("memory", {})

        self.reserve_ratio = float(memory_settings.get("pass2_budget_reserve", 0.25))
        divergence_threshold = float(memory_settings.get("divergence_threshold", 0.7))
        warm_slice_default = bool(memory_settings.get("warm_slice_default", True))
        max_iterations = int(memory_settings.get("max_sql_iterations", 5))

        self.state_manager = ContextStateManager()
        self.divergence_detector = DivergenceDetector(threshold=divergence_threshold)
        self.incremental_retriever = IncrementalRetriever(memnon, warm_slice_default=warm_slice_default)
        self.query_memory = QueryMemory(max_iterations=max_iterations)

        self.memnon = memnon
        self.token_manager = token_manager

        self.latest_divergence: Optional[DivergenceResult] = None
        self.latest_gap_feedback: Dict[str, str] = {}

    # Wiring -----------------------------------------------------------

    def attach_memnon(self, memnon: object) -> None:
        self.memnon = memnon
        self.incremental_retriever.memnon = memnon

    # Pass 1 -----------------------------------------------------------

    def handle_storyteller_response(self, narrative: str, turn_context: Any) -> Optional[ContextPackage]:
        """Process Storyteller output and capture Pass 1 baseline state."""

        if turn_context is None:
            return None

        baseline_chunks = self._gather_baseline_chunks(
            getattr(turn_context, "warm_slice", []),
            getattr(turn_context, "retrieved_passages", []),
        )

        analysis = {}
        if getattr(turn_context, "phase_states", None):
            analysis = turn_context.phase_states.get("warm_analysis", {}).get("analysis", {})

        baseline_entities = self._gather_entities(analysis, getattr(turn_context, "entity_data", {}))
        baseline_themes = self._gather_themes(analysis, narrative)
        token_usage = dict(getattr(turn_context, "token_counts", {}))

        context_package = self.state_manager.store_baseline_context(
            baseline_chunks=baseline_chunks,
            baseline_entities=baseline_entities,
            baseline_themes=baseline_themes,
            token_usage=token_usage,
        )

        remaining_budget = self._calculate_remaining_budget(token_usage)
        expected_user_themes = self._infer_expected_themes(analysis, narrative, baseline_themes)

        transition = PassTransition(
            storyteller_output=narrative or "",
            expected_user_themes=expected_user_themes,
            assembled_context=getattr(turn_context, "context_payload", {}) or {},
            remaining_budget=remaining_budget,
        )
        self.state_manager.update_pass_transition(transition)
        self.state_manager.update_remaining_budget(remaining_budget)

        # Reset pass2 state for the upcoming turn.
        self.query_memory.reset_pass2()
        self.latest_divergence = None
        self.latest_gap_feedback = {}

        # Persist pass1 query history if the turn captured it.
        deep_phase = {}
        if getattr(turn_context, "phase_states", None):
            deep_phase = turn_context.phase_states.get("deep_queries", {})
        self.query_memory.register_pass1_queries(deep_phase.get("queries", []))

        return context_package

    # Pass 2 -----------------------------------------------------------

    def prepare_warm_slice_for_user(
        self,
        user_input: str,
        warm_slice: Sequence[Dict[str, Any]],
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """Augment warm slice for Pass 2 if divergence requires it."""

        baseline = self.state_manager.get_context_package()
        transition = self.state_manager.get_pass_transition()

        if not baseline or not transition:
            metadata = {
                "divergence_detected": False,
                "confidence": 0.0,
                "missing_terms": [],
                "covered_terms": [],
                "gap_feedback": {},
                "additional_chunks": 0,
                "remaining_budget": 0,
            }
            self.latest_divergence = None
            self.latest_gap_feedback = {}
            return list(warm_slice or []), metadata

        detection = self.divergence_detector.detect(
            user_input,
            baseline,
            transition.expected_user_themes,
        )

        remaining_budget = self.state_manager.get_remaining_budget()
        gap_feedback: Dict[str, str] = dict(detection.gaps)
        additions: List[Dict[str, Any]] = []
        added_chunk_ids: Set[int] = set()

        if detection.detected:
            additions, added_chunk_ids, remaining_budget, gap_feedback = self.incremental_retriever.retrieve_gap_context(
                gap_feedback,
                baseline,
                remaining_budget,
                self.query_memory,
            )
        else:
            # No divergence detected; optionally expand warm slice.
            warm_additions, warm_ids, remaining_budget = self.incremental_retriever.expand_warm_slice(
                remaining_budget,
                baseline,
            )
            additions.extend(warm_additions)
            added_chunk_ids.update(warm_ids)

        merged_warm_slice = self.incremental_retriever.merge_warm_slice(warm_slice, additions)

        self.state_manager.mark_divergence(
            detected=detection.detected,
            confidence=detection.confidence,
            additional_chunks=added_chunk_ids,
            gap_analysis=gap_feedback,
        )
        self.state_manager.update_remaining_budget(remaining_budget)

        self.latest_divergence = detection
        self.latest_gap_feedback = gap_feedback

        metadata = {
            "divergence_detected": detection.detected,
            "confidence": detection.confidence,
            "missing_terms": detection.missing_terms,
            "covered_terms": detection.covered_terms,
            "gap_feedback": gap_feedback,
            "additional_chunks": len(added_chunk_ids),
            "remaining_budget": remaining_budget,
        }
        return merged_warm_slice, metadata

    # Accessors --------------------------------------------------------

    def get_baseline_context(self) -> Optional[ContextPackage]:
        return self.state_manager.get_context_package()

    def get_complete_context(self) -> Optional[Dict[str, Any]]:
        package = self.state_manager.get_context_package()
        transition = self.state_manager.get_pass_transition()
        if not package:
            return None
        return {
            "package": package.to_dict(),
            "pass_transition": {
                "storyteller_output": transition.storyteller_output if transition else "",
                "expected_user_themes": transition.expected_user_themes if transition else [],
                "remaining_budget": transition.remaining_budget if transition else 0,
            },
            "query_history": self.query_memory.get_history(),
        }

    def get_divergence_summary(self) -> Dict[str, Any]:
        detection = self.latest_divergence
        return {
            "detected": bool(detection and detection.detected),
            "confidence": getattr(detection, "confidence", 0.0),
            "missing_terms": getattr(detection, "missing_terms", []),
            "covered_terms": getattr(detection, "covered_terms", []),
            "gap_feedback": self.latest_gap_feedback,
        }

    # Helpers ----------------------------------------------------------

    def _gather_baseline_chunks(
        self,
        warm_slice: Sequence[Dict[str, Any]],
        retrieved_passages: Sequence[Dict[str, Any]],
    ) -> Set[int]:
        chunk_ids: Set[int] = set()
        for collection in (warm_slice or [], retrieved_passages or []):
            for item in collection:
                chunk_id = self._extract_chunk_id(item)
                if chunk_id is not None:
                    chunk_ids.add(chunk_id)
        return chunk_ids

    def _gather_entities(self, analysis: Any, entity_data: Dict[str, Any]) -> Dict[str, Any]:
        entities: Dict[str, Any] = {}
        if isinstance(entity_data, dict):
            for key, value in entity_data.items():
                entities[key] = value
        if isinstance(analysis, dict):
            for key in ("characters", "locations", "factions", "objects"):
                if key not in analysis:
                    continue
                values = analysis.get(key)
                if isinstance(values, list):
                    entities.setdefault(key, [])
                    for value in values:
                        if value not in entities[key]:
                            entities[key].append(value)
        return entities

    def _gather_themes(self, analysis: Any, narrative: str) -> List[str]:
        themes: List[str] = []
        if isinstance(analysis, dict):
            for key in ("themes", "topics", "motifs"):
                values = analysis.get(key)
                if isinstance(values, list):
                    for value in values:
                        if value not in themes:
                            themes.append(value)
        if narrative:
            inferred = self._infer_keywords_from_text(narrative)
            for keyword in inferred:
                if keyword not in themes:
                    themes.append(keyword)
        return themes

    def _infer_expected_themes(
        self,
        analysis: Any,
        narrative: str,
        baseline_themes: Sequence[str],
    ) -> List[str]:
        if isinstance(analysis, dict):
            expected = analysis.get("expected_user_themes")
            if isinstance(expected, list) and expected:
                return list(dict.fromkeys(expected))
        # Fall back to baseline themes inferred from narrative.
        if baseline_themes:
            return list(dict.fromkeys(baseline_themes))
        return self._infer_keywords_from_text(narrative)

    def _calculate_remaining_budget(self, token_usage: Dict[str, int]) -> int:
        total_available = int(token_usage.get("total_available", 0))
        used = sum(int(token_usage.get(key, 0)) for key in ("warm_slice", "structured", "augmentation"))
        reserve = int(total_available * self.reserve_ratio)
        remaining = max(reserve, total_available - used)
        return max(0, remaining)

    def _infer_keywords_from_text(self, text: str) -> List[str]:
        if not text:
            return []
        import re

        tokens = re.findall(r"[A-Z][a-zA-Z]+", text)
        normalized = []
        for token in tokens[:15]:
            token_lower = token.lower()
            if token_lower not in normalized:
                normalized.append(token_lower)
        return normalized

    def _extract_chunk_id(self, item: Dict[str, Any]) -> Optional[int]:
        chunk_id = item.get("chunk_id") or item.get("id")
        if chunk_id is None:
            return None
        try:
            return int(chunk_id)
        except (TypeError, ValueError):  # pragma: no cover - defensive
            return None

