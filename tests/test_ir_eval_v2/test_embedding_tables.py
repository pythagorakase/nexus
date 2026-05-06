"""Tests for dimension-specific embedding table resolution."""

from nexus.agents.memnon.utils.embedding_tables import resolve_dimension_table


def test_resolve_octen_dimension_tables() -> None:
    """Octen dimensions resolve to dedicated embedding tables."""
    assert resolve_dimension_table(2560) == "chunk_embeddings_2560d"
    assert resolve_dimension_table(4096) == "chunk_embeddings_4096d"
