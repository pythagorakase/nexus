"""LLM-based divergence detection for intelligent entity and event analysis."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set

from pydantic import BaseModel, Field

from .context_state import ContextPackage, PassTransition
from .divergence import DivergenceResult

logger = logging.getLogger(__name__)


class DivergenceAnalysis(BaseModel):
    """Structured output from LLM divergence analysis."""

    entity_ids_to_feature: List[int] = Field(
        default_factory=list,
        description="Entity IDs that should be upgraded from baseline to featured"
    )
    requires_search: bool = Field(
        default=False,
        description="Whether user input references obscure/remote events requiring search"
    )
    search_reason: Optional[str] = Field(
        default=None,
        description="Explanation of why additional search is needed"
    )
    search_terms: List[str] = Field(
        default_factory=list,
        description="Specific terms to search for if requires_search=True"
    )
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Confidence in the divergence detection (0.0-1.0)"
    )


class LLMDivergenceDetector:
    """LLM-based intelligent divergence detector.

    Uses local LLM inference to determine:
    - Which baseline entities need upgrading to featured
    - Whether user input references obscure events requiring additional retrieval
    """

    def __init__(
        self,
        llm_manager: Any,
        threshold: float = 0.7,
        use_local_llm: bool = True,
    ) -> None:
        """Initialize LLM divergence detector.

        Args:
            llm_manager: LLMManager instance for inference
            threshold: Confidence threshold for divergence detection (0.0-1.0)
            use_local_llm: Whether to use local LLM (faster, cheaper)
        """
        self.llm_manager = llm_manager
        self.threshold = max(0.0, min(1.0, threshold))
        self.use_local_llm = use_local_llm

    def detect(
        self,
        user_input: str,
        context: Optional[ContextPackage],
        transition: Optional[PassTransition],
    ) -> DivergenceResult:
        """Detect divergence using LLM inference.

        Args:
            user_input: New user input text to analyze
            context: Baseline context package (if available)
            transition: Pass transition metadata (if available)

        Returns:
            DivergenceResult with detection status and metadata
        """
        import time

        # If no baseline or input, no divergence to detect
        if not user_input or not context or not transition:
            logger.debug("No baseline context or user input; skipping divergence detection")
            return DivergenceResult(False, 0.0, {}, set(), set())

        # Build prompt for LLM analysis
        prompt = self._build_divergence_prompt(user_input, context, transition)

        # Get LLM analysis with timing
        start_time = time.time()
        try:
            analysis = self._get_llm_analysis(prompt)
            elapsed = time.time() - start_time
            logger.info(f"LLM divergence analysis completed in {elapsed:.2f}s")
        except Exception as e:
            elapsed = time.time() - start_time
            logger.warning(f"LLM divergence analysis failed after {elapsed:.2f}s: {e}")
            # Fallback to no-divergence on error
            return DivergenceResult(False, 0.0, {}, set(), set())

        # Convert LLM analysis to DivergenceResult
        result = self._convert_to_result(analysis, user_input)
        logger.debug(f"Divergence detection: {result.detected} (confidence={result.confidence:.2f})")
        return result

    def _build_divergence_prompt(
        self,
        user_input: str,
        context: ContextPackage,
        transition: PassTransition,
    ) -> str:
        """Build prompt for LLM divergence analysis."""

        sections = []

        # System context
        sections.append("# DIVERGENCE ANALYSIS TASK")
        sections.append("")
        sections.append("You are analyzing user input for an interactive narrative system.")
        sections.append("Your task is to identify:")
        sections.append("1. Which baseline entities (characters/places) the user directly references")
        sections.append("2. Whether the user mentions events/details not in recent narrative or retrieved context")
        sections.append("")

        # Baseline entities (characters)
        baseline_entities = context.baseline_entities or {}
        characters = baseline_entities.get("characters", {})

        if isinstance(characters, dict):
            # Handle hierarchical format
            baseline_chars = characters.get("baseline", [])
            if baseline_chars:
                sections.append("## ALL CHARACTERS (Baseline Awareness)")
                sections.append("These characters exist in the world. The system has minimal info about them.")
                for char in baseline_chars[:30]:  # Limit to 30 to avoid token bloat
                    char_id = char.get("id")
                    name = char.get("name", "Unknown")
                    summary = char.get("summary", "")[:100]  # Truncate long summaries
                    sections.append(f"- ID {char_id}: {name} - {summary}")
                sections.append("")

        # Locations
        locations = baseline_entities.get("locations", {})
        if isinstance(locations, dict):
            baseline_locs = locations.get("baseline", [])
            if baseline_locs:
                sections.append("## ALL LOCATIONS (Baseline Awareness)")
                for loc in baseline_locs[:20]:  # Limit to 20
                    loc_id = loc.get("id")
                    name = loc.get("name", "Unknown")
                    summary = loc.get("summary", "")[:80]
                    sections.append(f"- ID {loc_id}: {name} - {summary}")
                sections.append("")

        # Recent narrative chunks
        if context.baseline_chunks:
            chunk_list = sorted(context.baseline_chunks)
            sections.append("## RECENT NARRATIVE")
            sections.append(f"Chunks {chunk_list[0]}-{chunk_list[-1]} ({len(chunk_list)} total)")
            sections.append("")

        # Storyteller output (what just happened)
        if transition.storyteller_output:
            preview = transition.storyteller_output[:500]  # First 500 chars
            sections.append("## MOST RECENT SCENE")
            sections.append(preview)
            sections.append("")

        # User input to analyze
        sections.append("## USER INPUT TO ANALYZE")
        sections.append(user_input)
        sections.append("")

        # Instructions
        sections.append("## ANALYSIS QUESTIONS")
        sections.append("")
        sections.append("1. **Entity References**: Which character/location IDs (if any) does the user")
        sections.append("   directly reference, interact with, or mention? These need 'featured' details.")
        sections.append("   - Only include entities explicitly referenced")
        sections.append("   - Use entity IDs from the lists above")
        sections.append("")
        sections.append("2. **Event References**: Does the user mention events, details, or knowledge that")
        sections.append("   aren't explained in the recent narrative or most recent scene?")
        sections.append("   - Examples: obscure past events, time gaps, unexplained knowledge")
        sections.append("   - If yes, provide search terms to find relevant context")
        sections.append("")
        sections.append("3. **Confidence**: How confident are you in this analysis? (0.0-1.0)")
        sections.append("")
        sections.append("Respond with structured JSON output.")

        return "\n".join(sections)

    def _get_llm_analysis(self, prompt: str) -> DivergenceAnalysis:
        """Get LLM analysis using structured output."""

        # Use local LLM for fast, cheap inference
        if not self.llm_manager:
            raise ValueError("LLMManager not available for divergence detection")

        try:
            # Check if using LM Studio SDK (supports structured output)
            import lmstudio as lms

            # Create chat with system context
            chat = lms.Chat(
                "You are LORE's divergence detection system. "
                "Analyze user input to identify entity references and event gaps."
            )
            chat.add_user_message(prompt)

            # Get structured response
            result = self.llm_manager.model.respond(
                chat,
                response_format=DivergenceAnalysis,
                config={
                    "temperature": 0.3,  # Low temperature for consistent analysis
                    "maxTokens": 500,    # Short response sufficient
                    "contextLength": self.llm_manager.llm_config.get("context_window", 65536),
                }
            )

            logger.debug(
                "LLM divergence analysis complete: entities=%s, search=%s, confidence=%.2f",
                len(result.entity_ids_to_feature),
                result.requires_search,
                result.confidence,
            )

            return result

        except ImportError:
            # Use HTTP requests if LM Studio SDK not available
            logger.warning("LM Studio SDK not available, using HTTP-based LLM inference")
            # Parse manually from string response
            response_text = self.llm_manager.query(
                prompt,
                temperature=0.3,
                max_tokens=500,
                system_prompt=(
                    "You are LORE's divergence detection system. "
                    "Respond in JSON format with keys: "
                    "entity_ids_to_feature (list of ints), "
                    "requires_search (bool), "
                    "search_reason (string or null), "
                    "search_terms (list of strings), "
                    "confidence (float 0-1)"
                )
            )

            # Try to parse JSON response
            try:
                import json
                data = json.loads(response_text)
                return DivergenceAnalysis(**data)
            except Exception as e:
                logger.warning(f"Failed to parse divergence analysis JSON: {e}")
                # Return safe default
                return DivergenceAnalysis(
                    entity_ids_to_feature=[],
                    requires_search=False,
                    confidence=0.0,
                )

    def _convert_to_result(
        self,
        analysis: DivergenceAnalysis,
        user_input: str,
    ) -> DivergenceResult:
        """Convert LLM analysis to DivergenceResult format."""

        # Build gaps dict from analysis
        gaps: Dict[str, str] = {}

        # Add entity gaps
        for entity_id in analysis.entity_ids_to_feature:
            gaps[f"entity_{entity_id}"] = f"Entity ID {entity_id} referenced, needs featured details"

        # Add search gap if needed
        if analysis.requires_search and analysis.search_reason:
            for term in analysis.search_terms:
                gaps[term] = f"Obscure reference requiring search: {analysis.search_reason}"

        # Determine detection status
        detected = (
            (bool(analysis.entity_ids_to_feature) or analysis.requires_search)
            and analysis.confidence >= self.threshold
        )

        # Build unmatched_entities set (for compatibility)
        unmatched = set(gaps.keys())

        # References seen (user input tokens)
        # For LLM-based detection, we don't tokenize - just mark as "user_input"
        references_seen = {"user_input"} if user_input else set()

        logger.debug(
            "LLM divergence result: detected=%s, confidence=%.2f, entities=%s, search=%s",
            detected,
            analysis.confidence,
            len(analysis.entity_ids_to_feature),
            analysis.requires_search,
        )

        return DivergenceResult(
            detected=detected,
            confidence=analysis.confidence,
            gaps=gaps,
            unmatched_entities=unmatched,
            references_seen=references_seen,
        )
