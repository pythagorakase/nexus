"""Tests for dimension-specific embedding table helpers."""

import pytest

from nexus.agents.memnon.utils.embedding_tables import (
    parse_embedding_table_dimensions,
    resolve_dimension_table,
    table_name_for_dimensions,
)


def test_resolve_octen_dimension_tables() -> None:
    """Octen dimensions resolve to dedicated embedding tables."""
    assert resolve_dimension_table(2560) == "chunk_embeddings_2560d"
    assert resolve_dimension_table(4096) == "chunk_embeddings_4096d"


def test_resolve_unknown_dimension_table() -> None:
    """New embedding dimensions use the same canonical naming convention."""
    assert resolve_dimension_table(3072) == "chunk_embeddings_3072d"


def test_table_name_requires_positive_dimensions() -> None:
    """Invalid dimensions fail before producing unsafe SQL identifiers."""
    with pytest.raises(ValueError):
        table_name_for_dimensions(0)


def test_parse_embedding_table_dimensions() -> None:
    """Dimension parser recognizes canonical embedding table names only."""
    assert parse_embedding_table_dimensions("chunk_embeddings_1536d") == 1536
    assert parse_embedding_table_dimensions("chunk_embeddings_small") is None
