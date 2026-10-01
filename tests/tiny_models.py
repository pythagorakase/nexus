"""Tiny, randomly initialised model artifacts saved to disk for real loads.

Tests that exercise a loader against a real sentence-transformers artifact
use these instead of the multi-gigabyte production models or a monkeypatched
class. Nothing is downloaded: every file is written from a local config.
"""

from __future__ import annotations

import json
from pathlib import Path

import torch
from sentence_transformers import SentenceTransformer, models
from transformers.models.bert.configuration_bert import BertConfig
from transformers.models.bert.modeling_bert import (
    BertForSequenceClassification,
    BertModel,
)
from transformers.models.bert.tokenization_bert_fast import BertTokenizerFast


def write_tiny_sentence_transformer(root: Path) -> Path:
    """Save a tiny randomly initialised BERT SentenceTransformer to ``root``.

    Args:
        root: Directory to create; it must not exist yet

    Returns:
        ``root``, now holding a loadable SentenceTransformer artifact
    """

    source = root.parent / f"{root.name}-transformer"
    source.mkdir(parents=True)
    vocab_file = source / "vocab.txt"
    vocab_file.write_text("[PAD]\n[UNK]\n[CLS]\n[SEP]\n[MASK]\nneedle\nhay\n")
    BertTokenizerFast(vocab_file=str(vocab_file)).save_pretrained(source)
    torch.manual_seed(0)
    config = BertConfig(
        vocab_size=7,
        hidden_size=8,
        num_hidden_layers=1,
        num_attention_heads=1,
        intermediate_size=16,
        max_position_embeddings=32,
    )
    BertModel(config).save_pretrained(source)
    transformer = models.Transformer(
        str(source), max_seq_length=16, model_args={"local_files_only": True}
    )
    pooling = models.Pooling(transformer.get_word_embedding_dimension())
    SentenceTransformer(modules=[transformer, pooling], device="cpu").save(str(root))
    return root


def write_drifted_sentence_transformer(root: Path) -> Path:
    """Save a tiny SentenceTransformer whose sequence limit exceeds its model.

    The folder is ``write_tiny_sentence_transformer(root)`` with
    ``max_seq_length`` raised to 64 in ``sentence_bert_config.json`` while the
    underlying BERT keeps 32 positions. It loads and encodes short text, and
    raises a size-mismatch ``RuntimeError`` on text longer than 32 tokens.

    Args:
        root: Directory to create; it must not exist yet

    Returns:
        ``root``, now holding the drifted SentenceTransformer artifact
    """

    write_tiny_sentence_transformer(root)
    config_path = root / "sentence_bert_config.json"
    config = json.loads(config_path.read_text())
    config["max_seq_length"] = 64
    config_path.write_text(json.dumps(config, indent=2))
    return root


def write_tiny_cross_encoder(root: Path, hidden_size: int = 8) -> Path:
    """Save a tiny randomly initialised BERT cross-encoder to ``root``.

    The model has 32 positions, so a query-passage pair longer than 32 tokens
    raises a size-mismatch ``RuntimeError`` from ``predict``.

    Args:
        root: Directory to create; it must not exist yet
        hidden_size: Hidden size of the BERT model

    Returns:
        ``root``, now holding a loadable cross-encoder artifact
    """

    root.mkdir(parents=True)
    vocab_file = root / "vocab.txt"
    vocab_file.write_text("[PAD]\n[UNK]\n[CLS]\n[SEP]\n[MASK]\nneedle\nhay\n")
    BertTokenizerFast(vocab_file=str(vocab_file)).save_pretrained(root)
    torch.manual_seed(0)
    config = BertConfig(
        vocab_size=7,
        hidden_size=hidden_size,
        num_hidden_layers=1,
        num_attention_heads=1,
        intermediate_size=16,
        max_position_embeddings=32,
        num_labels=1,
    )
    BertForSequenceClassification(config).save_pretrained(root)
    return root
