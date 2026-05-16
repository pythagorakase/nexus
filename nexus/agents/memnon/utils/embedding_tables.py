"""Shared helpers for MEMNON's dimension-specific embedding tables."""

from __future__ import annotations

import re
from typing import List, Optional

from sqlalchemy import text
from sqlalchemy.engine import Connection

EMBEDDING_TABLE_PATTERN = re.compile(r"^chunk_embeddings_(?P<dimensions>\d+)d$")

# Historical dimensions that may exist in older slots. New dimensions should not
# be added here; table names are generated from the model output dimensionality.
LEGACY_EMBEDDING_DIMENSIONS = (1024, 1536, 2560, 4096)
DIMENSION_TABLES: List[str] = [
    f"chunk_embeddings_{dimensions:04d}d" for dimensions in LEGACY_EMBEDDING_DIMENSIONS
]


def table_name_for_dimensions(dimensions: int) -> str:
    """Return the canonical embedding table name for ``dimensions``."""
    if dimensions <= 0:
        raise ValueError(f"Embedding dimensions must be positive, got {dimensions}")
    return f"chunk_embeddings_{dimensions:04d}d"


def resolve_dimension_table(dimensions: int) -> str:
    """Return the embedding table that stores vectors for ``dimensions``."""
    return table_name_for_dimensions(dimensions)


def parse_embedding_table_dimensions(table_name: str) -> Optional[int]:
    """Return dimensions encoded in an embedding table name, if it matches."""
    match = EMBEDDING_TABLE_PATTERN.match(table_name)
    if not match:
        return None
    return int(match.group("dimensions"))


def list_embedding_tables(connection: Connection) -> List[str]:
    """List existing dimension-specific embedding tables in the current schema."""
    rows = connection.execute(
        text(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_type = 'BASE TABLE'
              AND table_name ~ '^chunk_embeddings_[0-9]+d$'
            ORDER BY table_name
            """
        )
    )
    return [row[0] for row in rows]


def embedding_table_exists(connection: Connection, table_name: str) -> bool:
    """Return whether ``table_name`` exists in the current public schema."""
    exists = connection.execute(
        text(
            """
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name = :table_name
            )
            """
        ),
        {"table_name": table_name},
    ).scalar()
    return bool(exists)


def ensure_embedding_table(connection: Connection, dimensions: int) -> str:
    """
    Ensure the embedding table for ``dimensions`` exists.

    Embedding tables are created lazily by write paths. Read/retrieval paths
    should inspect existing tables instead of calling this helper. The pgvector
    extension is a database setup prerequisite and must already exist.
    """
    table_name = table_name_for_dimensions(dimensions)

    connection.execute(
        text(
            f"""
            CREATE TABLE IF NOT EXISTS {table_name} (
                chunk_id BIGINT NOT NULL
                    REFERENCES narrative_chunks(id) ON DELETE CASCADE,
                model TEXT NOT NULL,
                embedding vector({dimensions}) NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (chunk_id, model)
            )
            """
        )
    )
    connection.execute(
        text(
            f"""
            CREATE INDEX IF NOT EXISTS {table_name}_model_idx
            ON {table_name} (model)
            """
        )
    )
    return table_name
