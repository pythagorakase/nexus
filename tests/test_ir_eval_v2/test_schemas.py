"""Unit tests for IR evaluation V2 schemas."""

import pytest

from ir_eval.models.schemas import EvalRunConfig


def test_eval_run_config_accepts_normalized_hybrid_weights() -> None:
    """Run config accepts valid model and hybrid weighting."""
    config = EvalRunConfig(
        name="octen-8b-solo",
        embedding_models=[{"model": "Octen-Embedding-8B", "weight": 1.0}],
        hybrid_search=True,
        vector_weight=0.6,
        text_weight=0.4,
    )

    assert config.name == "octen-8b-solo"
    assert len(config.embedding_models) == 1


def test_eval_run_config_rejects_invalid_hybrid_weight_sum() -> None:
    """Hybrid runs require vector/text weights to sum to 1.0."""
    with pytest.raises(
        ValueError, match=r"vector_weight \+ text_weight must equal 1.0"
    ):
        EvalRunConfig(
            name="invalid-weights",
            embedding_models=[{"model": "bge-large", "weight": 1.0}],
            hybrid_search=True,
            vector_weight=0.7,
            text_weight=0.4,
        )


def test_eval_run_config_requires_positive_model_weight_total() -> None:
    """Run configs must include at least one weighted model."""
    with pytest.raises(
        ValueError, match="At least one embedding model must have weight > 0"
    ):
        EvalRunConfig(
            name="zero-model-weights",
            embedding_models=[
                {"model": "bge-large", "weight": 0.0},
                {"model": "e5-large", "weight": 0.0},
            ],
            hybrid_search=False,
            vector_weight=1.0,
            text_weight=0.0,
        )
