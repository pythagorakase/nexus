"""Dependency checks for MEMNON cross-encoder reranking."""

import importlib
from pathlib import Path

import pytest


LOCAL_CROSS_ENCODER_MODEL = (
    Path(__file__).resolve().parents[1]
    / "models"
    / "naver-trecdl22-crossencoder-debertav3"
)


def test_protobuf_runtime_dependency_available() -> None:
    """DeBERTa tokenizers need protobuf available at runtime."""

    importlib.import_module("google.protobuf")


def test_sentencepiece_runtime_dependency_available() -> None:
    """DeBERTa/SentencePiece tokenizers need sentencepiece at runtime."""

    importlib.import_module("sentencepiece")


@pytest.mark.skipif(
    not LOCAL_CROSS_ENCODER_MODEL.exists(),
    reason="Local DeBERTa cross-encoder model is not available",
)
def test_local_deberta_cross_encoder_reranks_minimal_pair() -> None:
    """Exercise the local cross-encoder load and scoring path when available."""

    from nexus.agents.memnon.utils.cross_encoder import rerank_results

    ranked = rerank_results(
        query="Pontchartrain transfer yard infiltration",
        results=[
            {
                "id": "irrelevant",
                "text": "Mara packed coffee and biscuits for a quiet morning indoors.",
                "score": 0.92,
            },
            {
                "id": "relevant",
                "text": (
                    "The crew infiltrated the Pontchartrain transfer yard "
                    "under cover of rain."
                ),
                "score": 0.41,
            },
        ],
        top_k=2,
        alpha=0.3,
        batch_size=2,
        use_sliding_window=False,
        model_path=str(LOCAL_CROSS_ENCODER_MODEL),
        api_type="cross_encoder",
        device="cpu",
    )

    assert ranked[0]["id"] == "relevant"
    assert ranked[0]["reranker_score"] > ranked[1]["reranker_score"]
