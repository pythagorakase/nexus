"""Dependency checks for MEMNON cross-encoder reranking."""

import importlib


def test_cross_encoder_tokenizer_runtime_dependencies_available() -> None:
    """DeBERTa/SentencePiece rerankers need these non-core transformers extras."""

    assert importlib.import_module("google.protobuf")
    assert importlib.import_module("sentencepiece")
