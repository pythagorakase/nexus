"""LLM-based relevance judgment for IR evaluation V2."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

from scripts.api_openai import OpenAIProvider


SYSTEM_PROMPT = """You are a specialized evaluator for narrative information retrieval systems. Your task is to determine the relevance of retrieved content to specific queries about a narrative story.

## Task Definition:
1. You will receive query texts and retrieved narrative chunks.
2. For each chunk, assign a relevance score (0-3) based on how well it answers the query.
3. Be consistent in your scoring approach across all judgments.

## Relevance Scale:
0: Irrelevant - Does not match the query at all
1: Marginally relevant - Mentions the topic but not very helpful
2: Relevant - Contains useful information about the query
3: Highly relevant - Perfect match for the query

## Special Considerations:
- For character-related queries, consider both explicit mentions and clearly implied references
- For relationship queries, assess both factual statements and emotional/interpersonal context
- For temporal queries (first, after, etc.), prioritize content that directly addresses the temporal aspect
- For abstract concept queries, look for direct explanations or clear demonstrations of the concept
"""


class RelevanceAssessment(BaseModel):
    """Structured judgment returned by the LLM for a single (query, chunk) pair."""

    relevance_score: Literal[0, 1, 2, 3] = Field(
        description="Relevance score from 0-3 where 0=Irrelevant, 1=Marginally relevant, 2=Relevant, 3=Highly relevant"
    )
    justification: str = Field(
        description="Brief explanation of why this score was assigned"
    )


class JudgmentEngine:
    """Call an LLM to score the relevance of a chunk to a query."""

    def __init__(
        self,
        model: str,
        reasoning_effort: str = "high",
    ):
        """Create a judgment engine backed by an OpenAI structured-output call.

        The OpenAI provider is constructed lazily on first ``judge()`` call so
        that runs which don't trigger any LLM judgments (e.g. retrievals fully
        covered by existing judgments) don't require API credentials.

        Errors from the underlying API call propagate to the caller — this
        engine has no fallback or default-score behavior.
        """
        self.model = model
        self.reasoning_effort = reasoning_effort
        self._provider: Optional[OpenAIProvider] = None

    @property
    def provider(self) -> OpenAIProvider:
        """Lazily construct the OpenAI provider on first access."""
        if self._provider is None:
            self._provider = OpenAIProvider(
                model=self.model,
                reasoning_effort=self.reasoning_effort,
            )
        return self._provider

    def judge(
        self,
        query_text: str,
        chunk_text: str,
        query_category: Optional[str] = None,
    ) -> RelevanceAssessment:
        """Return a structured relevance assessment for one (query, chunk) pair."""
        prompt_parts = [SYSTEM_PROMPT, f"\nQUERY: {query_text}\n"]
        if query_category:
            prompt_parts.append(f"QUERY CATEGORY: {query_category}\n")
        prompt_parts.append(f"\nDOCUMENT TO EVALUATE:\n{chunk_text}\n")
        prompt = "".join(prompt_parts)

        response = self.provider.client.responses.parse(
            model=self.model,
            input=[{"role": "user", "content": prompt}],
            text_format=RelevanceAssessment,
            reasoning={"effort": self.reasoning_effort},
        )
        return response.output_parsed
