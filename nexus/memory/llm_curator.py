"""LLM-based context curator for Phase 2 retrieval."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class CurationDecision(BaseModel):
    """Structured output from LLM curator."""

    kept_chunk_ids: List[int] = Field(
        default_factory=list,
        description="Chunk IDs to keep from the raw search results"
    )
    additional_queries: List[Dict[str, str]] = Field(
        default_factory=list,
        description="Additional targeted queries to execute (type: 'vector' or 'sql', query: text)"
    )
    reasoning: Optional[str] = Field(
        default=None,
        description="Brief explanation of curation decisions"
    )
    estimated_tokens: Optional[int] = Field(
        default=None,
        description="Estimated tokens used by kept chunks"
    )


class LLMContextCurator:
    """Curate Phase 2 context using local LLM intelligence.

    This curator:
    1. Reviews raw search results
    2. Decides which chunks to keep/discard
    3. Identifies gaps needing targeted retrieval
    4. Generates specific queries to fill gaps
    5. Manages the Phase 2 token budget (typically 7,500 tokens)
    """

    def __init__(
        self,
        llm_manager: Any,
        phase2_budget: int = 7500,
        use_local_llm: bool = True,
    ) -> None:
        """Initialize the LLM context curator.

        Args:
            llm_manager: LLMManager instance for inference
            phase2_budget: Token budget for Phase 2 (default 7,500)
            use_local_llm: Whether to use local LLM (faster, cheaper)
        """
        self.llm_manager = llm_manager
        self.phase2_budget = phase2_budget
        self.use_local_llm = use_local_llm

    def curate(
        self,
        user_input: str,
        raw_search_results: List[Dict[str, Any]],
        storyteller_context: Optional[str] = None,
    ) -> CurationDecision:
        """Curate Phase 2 context intelligently.

        Args:
            user_input: The user's input text
            raw_search_results: Results from raw vector search
            storyteller_context: Recent storyteller output for context

        Returns:
            CurationDecision with chunks to keep and queries to execute
        """
        import time

        if not raw_search_results:
            logger.info("No raw search results to curate")
            return CurationDecision()

        # Build prompt for LLM curation
        prompt = self._build_curation_prompt(
            user_input, raw_search_results, storyteller_context
        )

        # Get LLM decision with timing
        start_time = time.time()
        try:
            decision = self._get_llm_decision(prompt)
            elapsed = time.time() - start_time
            logger.info(f"LLM curation completed in {elapsed:.2f}s")

            # Log the curation decision
            logger.info(
                f"Curation decision: keeping {len(decision.kept_chunk_ids)} chunks, "
                f"requesting {len(decision.additional_queries)} additional queries"
            )
            if decision.reasoning:
                logger.debug(f"Reasoning: {decision.reasoning}")

            return decision

        except Exception as e:
            elapsed = time.time() - start_time
            logger.warning(f"LLM curation failed after {elapsed:.2f}s: {e}")
            # Fallback: keep first few chunks that fit in budget
            return self._fallback_curation(raw_search_results)

    def _build_curation_prompt(
        self,
        user_input: str,
        raw_search_results: List[Dict[str, Any]],
        storyteller_context: Optional[str],
    ) -> str:
        """Build prompt for LLM curation."""

        sections = []

        # System context
        sections.append("# PHASE 2 CONTEXT CURATION")
        sections.append("")
        sections.append(f"You have {self.phase2_budget} tokens for Phase 2 context enrichment.")
        sections.append("Your goal is to intelligently manage this budget by:")
        sections.append("1. Reviewing raw search results and keeping only relevant chunks")
        sections.append("2. Identifying gaps that need targeted retrieval")
        sections.append("3. Generating specific queries to fill those gaps")
        sections.append("")

        # Recent storyteller output (for context)
        if storyteller_context:
            preview = storyteller_context[:500]
            sections.append("## RECENT NARRATIVE CONTEXT")
            sections.append(preview)
            sections.append("")

        # User input
        sections.append("## USER INPUT")
        sections.append(user_input)
        sections.append("")

        # Raw search results
        sections.append(f"## RAW SEARCH RESULTS ({len(raw_search_results)} chunks)")
        sections.append("")
        for i, chunk in enumerate(raw_search_results[:30]):  # Limit to 30 for prompt size
            chunk_id = chunk.get("chunk_id") or chunk.get("id")
            text_preview = chunk.get("text", "")[:200]
            score = chunk.get("score", 0.0)
            tokens = self._estimate_tokens(chunk.get("text", ""))

            sections.append(f"### Chunk {chunk_id} (score: {score:.3f}, ~{tokens} tokens)")
            sections.append(text_preview)
            sections.append("")

        # Instructions
        sections.append("## CURATION TASK")
        sections.append("")
        sections.append("Review the chunks above and decide:")
        sections.append("1. Which chunks are relevant to the user's input and should be kept?")
        sections.append("2. What narrative elements or entities are missing that need retrieval?")
        sections.append("3. What specific queries would fill those gaps?")
        sections.append("")
        sections.append("REMEMBER:")
        sections.append(f"- You have {self.phase2_budget} tokens total for Phase 2")
        sections.append("- Each chunk uses roughly (word_count * 1.25) tokens")
        sections.append("- Leave room for results from your additional queries")
        sections.append("- Prioritize chunks with high relevance to the user input")
        sections.append("- Consider narrative callbacks and entity references")
        sections.append("")
        sections.append("Respond with structured JSON output.")

        return "\n".join(sections)

    def _get_llm_decision(self, prompt: str) -> CurationDecision:
        """Get LLM curation decision using structured output."""

        if not self.llm_manager:
            raise ValueError("LLMManager not available for curation")

        try:
            # Check if using LM Studio SDK
            import lmstudio as lms

            # Create chat with system context
            chat = lms.Chat(
                "You are LORE's Phase 2 context curator. "
                "Intelligently manage the token budget by selecting relevant chunks "
                "and identifying gaps that need targeted retrieval."
            )
            chat.add_user_message(prompt)

            # Get model identifier for special handling
            model_identifier = ""
            if hasattr(self.llm_manager, "model"):
                model = self.llm_manager.model
                model_identifier = (
                    getattr(model, "identifier", "")
                    or getattr(model, "model_id", "")
                )
            if not model_identifier:
                model_identifier = getattr(self.llm_manager, "loaded_model_id", "")

            # Use structured output
            result = self.llm_manager.model.respond(
                chat,
                response_format=CurationDecision,
                config={
                    "temperature": 0.3,
                    "maxTokens": 1000,
                    "contextLength": self.llm_manager.llm_config.get("context_window", 65536),
                }
            )

            # Extract parsed content
            if not hasattr(result, "parsed") or result.parsed is None:
                raise RuntimeError("LM Studio SDK returned result without parsed content")

            parsed_data = result.parsed

            # Convert to model if needed
            if isinstance(parsed_data, dict):
                decision = CurationDecision(**parsed_data)
            else:
                decision = parsed_data

            return decision

        except ImportError:
            # Fallback without LM Studio SDK
            logger.warning("LM Studio SDK not available, using fallback curation")
            return self._fallback_curation([])

    def _fallback_curation(self, raw_search_results: List[Dict[str, Any]]) -> CurationDecision:
        """Simple fallback curation when LLM unavailable."""

        kept_chunks = []
        total_tokens = 0

        # Keep chunks that fit in budget (first 60% of budget for safety)
        budget_limit = int(self.phase2_budget * 0.6)

        for chunk in raw_search_results:
            chunk_id = chunk.get("chunk_id") or chunk.get("id")
            if chunk_id is None:
                continue

            tokens = self._estimate_tokens(chunk.get("text", ""))
            if total_tokens + tokens > budget_limit:
                break

            kept_chunks.append(int(chunk_id))
            total_tokens += tokens

        logger.info(
            f"Fallback curation: keeping {len(kept_chunks)} chunks "
            f"(~{total_tokens} tokens of {self.phase2_budget} budget)"
        )

        return CurationDecision(
            kept_chunk_ids=kept_chunks,
            additional_queries=[],
            reasoning="Fallback curation - kept chunks that fit in budget",
            estimated_tokens=total_tokens
        )

    def _estimate_tokens(self, text: str) -> int:
        """Estimate token count for text."""
        # Simple heuristic: words * 1.25 ≈ tokens
        words = len(text.split())
        return int(words * 1.25)