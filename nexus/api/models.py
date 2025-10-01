"""
Pydantic models for FastAPI endpoints.

These match the TypeScript interfaces expected by the iris2 frontend.
"""
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime


class Condition(BaseModel):
    """Model configuration for generation."""
    id: int
    slug: str
    provider: str
    model: str = Field(alias="model_name")
    label: Optional[str] = None
    parameters: Dict[str, Any]
    is_active: bool

    class Config:
        populate_by_name = True


class Generation(BaseModel):
    """A single generation result."""
    id: int
    condition_id: int
    prompt_id: int
    replicate_index: int
    status: str
    response_payload: Optional[Dict[str, Any]] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    cost_usd: Optional[float] = None
    completed_at: Optional[datetime] = None


class Prompt(BaseModel):
    """Context package for generation."""
    id: int
    chunk_id: int
    category: Optional[str] = None
    label: Optional[str] = None
    context: Dict[str, Any]
    metadata: Dict[str, Any]


class Comparison(BaseModel):
    """A comparison between two generations."""
    id: int
    prompt_id: int
    condition_a: Condition
    condition_b: Condition
    generation_a: Generation
    generation_b: Generation
    winner_condition_id: Optional[int] = None
    evaluator: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime


class ComparisonCreate(BaseModel):
    """Request to create a new comparison judgment."""
    prompt_id: int
    condition_a_id: int
    condition_b_id: int
    winner_condition_id: Optional[int] = None
    evaluator: str
    notes: Optional[str] = None


class ELORating(BaseModel):
    """ELO rating for a condition."""
    condition_id: int
    condition: Condition
    rating: float
    games_played: int
    last_updated: datetime


class ComparisonQueueItem(BaseModel):
    """Single item in comparison queue."""
    prompt: Prompt
    condition_a: Condition
    condition_b: Condition
    generation_a: Generation
    generation_b: Generation


class ComparisonQueue(BaseModel):
    """Queue of pending comparisons."""
    total: int
    current: int
    comparisons: List[ComparisonQueueItem]


class GenerationRun(BaseModel):
    """A batch generation run."""
    id: str  # UUID
    label: Optional[str] = None
    started_at: datetime
    completed_at: Optional[datetime] = None
    total_generations: int
    completed_generations: int
    failed_generations: int
