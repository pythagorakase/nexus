"""Pydantic schemas for the IR evaluation V2 engine."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, model_validator


class EvalModelConfig(BaseModel):
    """Embedding model selection for an evaluation run."""

    model: str = Field(..., min_length=1)
    weight: float = Field(..., ge=0.0, le=1.0)


class EvalRunConfig(BaseModel):
    """Immutable run configuration persisted in the database."""

    name: str = Field(..., min_length=1)
    description: str = ""
    embedding_models: List[EvalModelConfig] = Field(..., min_length=1)
    hybrid_search: bool = True
    vector_weight: float = Field(default=0.6, ge=0.0, le=1.0)
    text_weight: float = Field(default=0.4, ge=0.0, le=1.0)
    cross_encoder_enabled: bool = True
    top_k: int = Field(default=10, ge=1)
    query_ids: Optional[List[int]] = None
    query_categories: Optional[List[str]] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    settings_snapshot: Dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_weights(self) -> "EvalRunConfig":
        """Validate weight sums for deterministic scoring behavior."""
        if self.hybrid_search:
            total = self.vector_weight + self.text_weight
            if abs(total - 1.0) > 1e-6:
                raise ValueError("vector_weight + text_weight must equal 1.0")

        model_weight_total = sum(model.weight for model in self.embedding_models)
        if model_weight_total <= 0:
            raise ValueError("At least one embedding model must have weight > 0")

        return self


class EvalQuery(BaseModel):
    """Query payload used by the run executor."""

    id: int
    text: str
    category: str = "unknown"
    name: str = ""


class RetrievedDocument(BaseModel):
    """Single retrieved document with full score breakdown."""

    chunk_id: int
    rank: int
    final_score: float = 0.0
    vector_score: float = 0.0
    text_score: float = 0.0
    reranker_score: Optional[float] = None
    model_scores: Dict[str, float] = Field(default_factory=dict)
    source: str = "unknown"
    metadata: Dict[str, Any] = Field(default_factory=dict)


class QueryExecutionResult(BaseModel):
    """Execution output for one query in a run."""

    query_id: int
    query_text: str
    query_category: str
    elapsed_seconds: float
    results: List[RetrievedDocument] = Field(default_factory=list)


class RunExecutionSummary(BaseModel):
    """Top-level execution summary returned after a run completes."""

    run_id: int
    status: str
    query_count: int
    total_elapsed_seconds: float
    overall_metrics: Dict[str, float] = Field(default_factory=dict)
    category_metrics: Dict[str, Dict[str, float]] = Field(default_factory=dict)
