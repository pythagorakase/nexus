#!/usr/bin/env python3
"""
Check that an ANN index exists on a model's embedding table; this script creates none.
"""

from nexus.database import create_slot_engine

import os
import sys
import argparse
import json
import logging
from sqlalchemy import text

# Set up logging
if __name__ == "__main__":
    # Only a command-line run configures the root logger, never an import.
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
logger = logging.getLogger("nexus.embeddings")

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from nexus.agents.memnon.utils.embedding_tables import (
    PGVECTOR_ANN_INDEX_MAX_DIMENSIONS,
    supports_pgvector_ann_index,
    table_name_for_dimensions,
)
from nexus.config import load_settings  # noqa: E402

# Try to load settings using centralized config loader
try:
    from nexus.config import load_settings_as_dict

    _all_settings = load_settings_as_dict()
    SETTINGS = _all_settings.get("Agent Settings", {}).get("MEMNON", {})
except Exception as e:
    logger.warning(f"Could not load settings via config loader: {e}")
    SETTINGS = {}


def get_model_dimensions(model_name: str) -> int:
    """Get the dimensions for a model name.

    The embedder registry ([memnon.models] or [ir_eval.embedding_candidates])
    answers first.
    """
    registry = load_settings().embedder_registry()
    model_key = model_name.replace("/", "_")
    if model_key in registry:
        dimensions = registry[model_key].get("dimensions")
        if dimensions:
            return dimensions

    # Hard-coded fallbacks
    model_dimensions = {
        "bge-small-custom": 384,
        "bge-small-en": 384,
        "bge-small-en-v1.5": 384,
        "infly/inf-retriever-v1-1.5b": 1536,
        "infly/inf-retriever-v1": 3584,
        "Octen-Embedding-4B": 2560,
        "Octen-Embedding-8B": 4096,
        "bge-large-en-v1.5": 1024,
        "bge-large-en": 1024,
        "e5-large-v2": 1024,
    }

    # Check for exact match
    if model_name in model_dimensions:
        return model_dimensions[model_name]

    # Check for partial match
    for name, dim in model_dimensions.items():
        if name in model_name:
            return dim

    # Default
    logger.warning(
        f"Could not determine dimensions for {model_name}, using default (1024)"
    )
    return 1024


def get_table_name(model_name: str) -> str:
    """Get table name for a model"""
    dimensions = get_model_dimensions(model_name)
    return table_name_for_dimensions(dimensions)


def create_vector_indexes(model_name: str, db_url: str = None):
    """
    Check that an ANN index exists on this model's embedding table.

    Args:
        model_name: Name of the embedding model
        db_url: Database URL (optional)

    Returns:
        True when an ANN index exists or the table is over 2000 dimensions;
        False when the table is missing, or holds no rows for the model.

    Raises:
        RuntimeError: When no ANN index exists.
    """
    # Set default db_url if not provided
    if not db_url:
        db_url = SETTINGS.get("database", {}).get("url", None)

    # Get dimensions and table name
    dimensions = get_model_dimensions(model_name)
    table_name = get_table_name(model_name)

    logger.info(f"Checking ANN indexes for {model_name} ({dimensions}D)")
    logger.info(f"Table: {table_name}")

    # Connect to database
    engine = create_slot_engine(db_url)

    # First check if table exists and has data
    with engine.connect() as conn:
        # Check if table exists
        check_sql = f"""
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_name = '{table_name}'
        );
        """
        table_exists = conn.execute(text(check_sql)).scalar()

        if not table_exists:
            logger.error(f"Table {table_name} does not exist!")
            return False

        # Count embeddings
        count_sql = f"""
        SELECT COUNT(*) FROM {table_name} 
        WHERE model = :model_name;
        """
        count = conn.execute(text(count_sql), {"model_name": model_name}).scalar()

        logger.info(f"Found {count} embeddings for {model_name}")

        if count == 0:
            logger.warning("No embeddings found for this model!")
            return False

        if not supports_pgvector_ann_index(dimensions):
            logger.info(
                "Skipping ANN vector index for %s: pgvector supports HNSW/IVFFlat "
                "indexes up to %sd locally, and exact search remains available",
                table_name,
                PGVECTOR_ANN_INDEX_MAX_DIMENSIONS,
            )
            return True

        ann_indexes = conn.execute(
            text(
                "SELECT indexname FROM pg_indexes WHERE schemaname = 'public' "
                "AND tablename = :table AND indexdef ~ 'USING (hnsw|ivfflat)'"
            ),
            {"table": table_name},
        ).fetchall()

    if ann_indexes:
        for row in ann_indexes:
            logger.info(f"ANN index present: {row[0]}")
        return True
    raise RuntimeError(
        f"No ANN index exists on {table_name}, and this script no longer creates "
        "one: the only ANN path is the explicit 2560d candidate gate "
        "(build_candidate_ann_index, run by scripts/qa_shift/ann_gate.py), and "
        f"#812 owns the legacy {dimensions}d tables and their indexes."
    )


def main():
    """Main entry point for the script"""
    parser = argparse.ArgumentParser(
        description="Check that an ANN index exists on a model's embedding table"
    )
    parser.add_argument("--model", required=True, help="Model name")
    parser.add_argument("--db-url", help="Database URL")
    args = parser.parse_args()

    try:
        success = create_vector_indexes(args.model, args.db_url)
        if success:
            print("\nANN index present.")
            return 0
        else:
            print("\nANN index check failed; see the log.")
            return 1
    except Exception as e:
        logger.error(f"Error creating vector indexes: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
