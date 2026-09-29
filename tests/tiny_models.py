"""Tiny, randomly initialised model artifacts saved to disk for real loads.

Tests that exercise a loader against a real sentence-transformers artifact
use these instead of the multi-gigabyte production models or a monkeypatched
class. Nothing is downloaded: every file is written from a local config.
"""

from __future__ import annotations

from pathlib import Path

import torch
from sentence_transformers import SentenceTransformer, models
from transformers.models.bert.configuration_bert import BertConfig
from transformers.models.bert.modeling_bert import BertModel
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
