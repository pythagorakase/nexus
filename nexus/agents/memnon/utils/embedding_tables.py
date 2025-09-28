"""Shared constants and helpers for MEMNON's embedding tables."""

from __future__ import annotations

from typing import Dict, List, Optional

# Mapping of embedding dimensionality to the backing PostgreSQL table.
DIMENSION_TABLE_MAP: Dict[int, str] = {
    1024: "chunk_embeddings_1024d",
    1536: "chunk_embeddings_1536d",
}

# Convenience list of known dimension-specific tables.
DIMENSION_TABLES: List[str] = list(DIMENSION_TABLE_MAP.values())


def resolve_dimension_table(dimensions: int) -> Optional[str]:
    """Return the embedding table that stores vectors for ``dimensions``."""
    return DIMENSION_TABLE_MAP.get(dimensions)

