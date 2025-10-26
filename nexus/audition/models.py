"""Dataclasses used by the Apex audition engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID, uuid4


@dataclass(slots=True)
class ConditionSpec:
    """Model condition (provider + parameters) tracked in the repository."""

    slug: str
    provider: str
    model: str
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    min_p: Optional[float] = None
    frequency_penalty: Optional[float] = None
    presence_penalty: Optional[float] = None
    repetition_penalty: Optional[float] = None
    reasoning_effort: Optional[str] = None
    thinking_enabled: Optional[bool] = None
    max_output_tokens: Optional[int] = None
    thinking_budget_tokens: Optional[int] = None
    label: Optional[str] = None
    description: Optional[str] = None
    system_prompt: Optional[str] = None
    is_active: bool = True
    is_visible: bool = True
    id: Optional[int] = None
    created_at: Optional[datetime] = None

    def __post_init__(self) -> None:
        # Normalize provider identifiers for storage/lookup consistency
        normalized_provider = (
            self.provider.strip().lower().replace(" ", "").replace("-", "")
        )
        provider_canonical_map = {
            "openai": "OpenAI",
            "anthropic": "Anthropic",
            "deepseek": "DeepSeek",
            "moonshot": "Moonshot",
            "moonshotai": "Moonshot",
            "nousresearch": "NousResearch",
            "openrouter": "OpenRouter",
        }
        self.provider = provider_canonical_map.get(normalized_provider, self.provider.strip())
        self.model = self.model.strip()

    def with_id(self, identifier: int, created_at: datetime) -> "ConditionSpec":
        """Return a copy that includes database identifiers."""
        clone = ConditionSpec(
            slug=self.slug,
            provider=self.provider,
            model=self.model,
            temperature=self.temperature,
            top_p=self.top_p,
            min_p=self.min_p,
            frequency_penalty=self.frequency_penalty,
            presence_penalty=self.presence_penalty,
            repetition_penalty=self.repetition_penalty,
            reasoning_effort=self.reasoning_effort,
            thinking_enabled=self.thinking_enabled,
            max_output_tokens=self.max_output_tokens,
            thinking_budget_tokens=self.thinking_budget_tokens,
            label=self.label,
            description=self.description,
            system_prompt=self.system_prompt,
            is_active=self.is_active,
            is_visible=self.is_visible,
        )
        clone.id = identifier
        clone.created_at = created_at
        return clone


@dataclass(slots=True)
class PromptSnapshot:
    """Frozen context package used by the audition pipeline."""

    chunk_id: int
    context_sha: str
    context: Dict[str, Any]
    category: Optional[str] = None
    label: Optional[str] = None
    source_path: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    id: Optional[int] = None
    created_at: Optional[datetime] = None

    def with_id(self, identifier: int, created_at: datetime) -> "PromptSnapshot":
        clone = PromptSnapshot(
            chunk_id=self.chunk_id,
            context_sha=self.context_sha,
            context=self.context,
            category=self.category,
            label=self.label,
            source_path=self.source_path,
            metadata=dict(self.metadata),
        )
        clone.id = identifier
        clone.created_at = created_at
        return clone


@dataclass(slots=True)
class GenerationRun:
    """Logical grouping of generations executed in a batch."""

    provider: str
    storyteller_prompt: Optional[str] = None
    created_by: Optional[str] = None
    notes: Optional[str] = None
    run_id: UUID = field(default_factory=uuid4)
    description: Optional[str] = None
    created_at: Optional[datetime] = None


@dataclass(slots=True)
class GenerationResult:
    """Result of a single model completion for a prompt/condition pair."""

    run_id: UUID
    condition_id: int
    prompt_id: int
    replicate_index: int
    lane_id: Optional[str]
    status: str
    prompt_text: str
    request_payload: Dict[str, Any]
    response_payload: Optional[Dict[str, Any]] = None
    input_tokens: int = 0
    output_tokens: int = 0
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    batch_job_id: Optional[str] = None
    cache_hit: bool = False
    id: Optional[int] = None


__all__ = [
    "ConditionSpec",
    "PromptSnapshot",
    "GenerationRun",
    "GenerationResult",
]
