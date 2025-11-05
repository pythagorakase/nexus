"""LLM-based divergence detection for intelligent entity and event analysis."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set

from pydantic import BaseModel, Field

from .context_state import ContextPackage, PassTransition
from .divergence import DivergenceResult

logger = logging.getLogger(__name__)


class EnrichmentAnalysis(BaseModel):
    """Structured output identifying narrative enrichment opportunities."""

    enrichment_searches: List[str] = Field(
        default_factory=list,
        description="Search terms for narrative callbacks, events, or references worth retrieving"
    )
    entity_ids_to_feature: List[int] = Field(
        default_factory=list,
        description="Entity IDs (if any) that should be upgraded from baseline to featured"
    )
    enrichment_reason: Optional[str] = Field(
        default=None,
        description="Brief explanation of what narrative elements could be enriched"
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

        # Debug: Log user input
        logger.info(f"Analyzing user input: {user_input[:100]}...")

        # Log the prompt being sent (first 1000 chars for debugging)
        logger.debug(f"Sending prompt to LLM (first 1000 chars): {prompt[:1000]}...")

        # Get LLM analysis with timing
        start_time = time.time()
        try:
            analysis = self._get_llm_analysis(prompt)
            elapsed = time.time() - start_time
            logger.info(f"LLM divergence analysis completed in {elapsed:.2f}s")

            # Log the raw analysis result
            logger.debug(f"LLM analysis result: searches={analysis.enrichment_searches}, entities={analysis.entity_ids_to_feature}, reason={analysis.enrichment_reason}")
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
        sections.append("# NARRATIVE ENRICHMENT ANALYSIS")
        sections.append("")
        sections.append("You are analyzing user input to identify opportunities for narrative enrichment.")
        sections.append("Your goal is to find:")
        sections.append("1. Entities that would benefit from richer context")
        sections.append("2. References and callbacks that could be enhanced with additional retrieval")
        sections.append("3. Narrative threads worth exploring more deeply")
        sections.append("")
        sections.append("Remember: Casual mentions and throwaway lines often carry the most narrative weight.")
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
        sections.append("## ENRICHMENT OPPORTUNITIES")
        sections.append("")
        sections.append("1. **Narrative References**: What events, callbacks, or allusions could be enriched?")
        sections.append("   - Past events mentioned (even jokingly) like 'karaoke' or 'that time when...'")
        sections.append("   - Shared history or inside references")
        sections.append("   - Any knowledge that implies deeper context")
        sections.append("   - List search terms to retrieve the full context (PRIMARY OUTPUT)")
        sections.append("")
        sections.append("2. **Entity Upgrades** (if applicable): Which character/location IDs need fuller context?")
        sections.append("   - Only if specific entities are directly referenced")
        sections.append("   - List entity IDs that deserve 'featured' treatment")
        sections.append("   - Leave empty if no specific entities need upgrading")
        sections.append("")
        sections.append("3. **Enrichment Reason**: Brief explanation of what would be enriched")
        sections.append("")
        sections.append("Respond with structured JSON output.")

        return "\n".join(sections)

    def _get_llm_analysis(self, prompt: str) -> EnrichmentAnalysis:
        """Get LLM analysis using structured output."""

        # Use local LLM for fast, cheap inference
        if not self.llm_manager:
            raise ValueError("LLMManager not available for divergence detection")

        try:
            # Check if using LM Studio SDK (supports structured output)
            import lmstudio as lms

            # Create chat with system context
            chat = lms.Chat(
                "You are LORE's narrative enrichment analyzer. "
                "Identify opportunities to enhance the narrative with deeper context. "
                "Remember: casual references often signal the richest retrieval opportunities."
            )
            chat.add_user_message(prompt)

            # For GPT-OSS models, first get reasoning with regular response
            if "gpt-oss" in self.llm_manager.model.identifier.lower():
                # First, get the reasoning without structured output
                reasoning_config = {
                    "temperature": 0.3,
                    "maxTokens": 2000,
                    "contextLength": self.llm_manager.llm_config.get("context_window", 65536),
                    "reasoning": {"effort": "high"}
                }

                # Add instruction to output JSON at the end
                reasoning_chat = lms.Chat(
                    "You are LORE's narrative enrichment analyzer. "
                    "Think step-by-step about enrichment opportunities, then output JSON. "
                    "Remember: casual references often signal the richest retrieval opportunities."
                )
                reasoning_chat.add_user_message(
                    prompt + "\n\nFirst explain your reasoning about what enrichment opportunities exist. "
                    "Then output a JSON object on a new line with exactly these keys:\n"
                    "{\n"
                    '  "enrichment_searches": ["search term 1", "search term 2", ...],\n'
                    '  "entity_ids_to_feature": [1, 2, 3],\n'
                    '  "enrichment_reason": "Brief reason why these enrichments would help"\n'
                    "}\n\n"
                    "The JSON must be valid and complete. Include empty arrays [] if no items needed."
                )

                reasoning_result = self.llm_manager.model.respond(
                    reasoning_chat,
                    config=reasoning_config
                )

                # Log the full reasoning response
                if hasattr(reasoning_result, "content"):
                    logger.info("=== FULL LLM RESPONSE WITH REASONING ===")
                    logger.info(reasoning_result.content)
                    logger.info("=== END FULL RESPONSE ===")

                    # Parse JSON from the response
                    import json
                    import re

                    # Try to find JSON block - look for opening { and matching closing }
                    content = reasoning_result.content

                    # First try to find a clean JSON object
                    json_match = re.search(r'\{[^}]*"enrichment_searches"[^}]*\}', content, re.DOTALL)

                    if not json_match:
                        # Try more permissive pattern
                        json_match = re.search(r'\{.*?\}(?=\s*$|\s*\n)', content, re.DOTALL)

                    if json_match:
                        try:
                            json_str = json_match.group()
                            # Clean up any trailing commas before closing brackets
                            json_str = re.sub(r',(\s*[}\]])', r'\1', json_str)
                            data = json.loads(json_str)
                            analysis = EnrichmentAnalysis(**data)
                            logger.debug(f"Successfully parsed JSON: {data}")
                        except (json.JSONDecodeError, Exception) as e:
                            logger.warning(f"Failed to parse JSON: {e}. Content was: {json_match.group()[:200]}")
                            analysis = EnrichmentAnalysis()
                    else:
                        # Fallback to empty response if no JSON found
                        analysis = EnrichmentAnalysis()
                else:
                    # Fallback to structured output
                    result = self.llm_manager.model.respond(
                        chat,
                        response_format=EnrichmentAnalysis,
                        config={"temperature": 0.3, "maxTokens": 500, "contextLength": 65536}
                    )
                    if hasattr(result, "parsed"):
                        analysis = result.parsed
                    else:
                        analysis = EnrichmentAnalysis()
            else:
                # Non-GPT-OSS models: use structured output directly
                result = self.llm_manager.model.respond(
                    chat,
                    response_format=EnrichmentAnalysis,
                    config={
                        "temperature": 0.3,
                        "maxTokens": 500,
                        "contextLength": self.llm_manager.llm_config.get("context_window", 65536),
                    }
                )

                # Extract parsed content from PredictionResult wrapper
                if not hasattr(result, "parsed") or result.parsed is None:
                    raise RuntimeError("LM Studio SDK returned result without parsed content")

                parsed_data = result.parsed

                # result.parsed may be a dict or Pydantic model - convert to model for consistency
                if isinstance(parsed_data, dict):
                    analysis = EnrichmentAnalysis(**parsed_data)
                else:
                    analysis = parsed_data

            logger.info(
                "LLM enrichment analysis complete: searches=%s, entities=%s",
                analysis.enrichment_searches,
                analysis.entity_ids_to_feature if analysis.entity_ids_to_feature else "none",
            )

            # Log enrichment reason if provided
            if analysis.enrichment_reason:
                logger.info("Enrichment reason: %s", analysis.enrichment_reason)

            return analysis

        except ImportError:
            # Use HTTP requests if LM Studio SDK not available
            logger.warning("LM Studio SDK not available, using HTTP-based LLM inference")
            # Parse manually from string response
            response_text = self.llm_manager.query(
                prompt,
                temperature=0.3,
                max_tokens=500,
                system_prompt=(
                    "You are LORE's narrative enrichment analyzer. "
                    "Respond in JSON format with keys: "
                    "enrichment_searches (list of strings), "
                    "entity_ids_to_feature (list of ints or empty), "
                    "enrichment_reason (string or null)"
                )
            )

            # Parse JSON response - FAIL HARD if parsing fails
            import json
            data = json.loads(response_text)
            return EnrichmentAnalysis(**data)

    def _convert_to_result(
        self,
        analysis: EnrichmentAnalysis,
        user_input: str,
    ) -> DivergenceResult:
        """Convert LLM analysis to DivergenceResult format."""

        # Build enrichment opportunities from analysis
        gaps: Dict[str, str] = {}

        # Add search terms as primary enrichment opportunities
        for search_term in analysis.enrichment_searches:
            gaps[search_term] = f"Narrative enrichment: {analysis.enrichment_reason or 'callback/reference'}"

        # Add entity enrichment opportunities if any
        for entity_id in analysis.entity_ids_to_feature:
            gaps[f"entity_{entity_id}"] = f"Entity ID {entity_id} could benefit from featured context"

        # Detect enrichment opportunities (no confidence threshold)
        detected = bool(analysis.enrichment_searches) or bool(analysis.entity_ids_to_feature)

        # Build unmatched_entities set (for compatibility)
        unmatched = set(gaps.keys())

        # References seen (user input tokens)
        # For LLM-based detection, we don't tokenize - just mark as "user_input"
        references_seen = {"user_input"} if user_input else set()

        logger.debug(
            "LLM enrichment result: detected=%s, searches=%s, entities=%s",
            detected,
            len(analysis.enrichment_searches),
            len(analysis.entity_ids_to_feature),
        )

        return DivergenceResult(
            detected=detected,
            confidence=1.0 if detected else 0.0,  # Simple binary for backwards compatibility
            gaps=gaps,
            unmatched_entities=unmatched,
            references_seen=references_seen,
        )
