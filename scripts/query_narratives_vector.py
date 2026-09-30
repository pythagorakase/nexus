#!/usr/bin/env python3
"""
Query Narratives Script for NEXUS with vector search support

This script provides semantic search functionality across the stored narrative chunks
using pgvector for similarity search. It supports both 1024D (BGE-Large, E5-Large)
and 384D (BGE-Small) embeddings stored in separate tables.

Usage:
    python query_narratives_vector.py "your search query" --model bge-large --limit 5

Example:
    python query_narratives_vector.py "Alex discovers the secret" --model bge-large
"""

from nexus.database import create_slot_engine

import os
import sys
import argparse
import logging
import json
from typing import List, Dict, Any, Mapping, Tuple, Optional

# Add parent directory to sys.path to import from nexus package
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Import embedding utilities
try:
    from scripts.utils.embedding_utils import (
        get_model_dimensions,
        get_table_for_model,
        construct_vector_search_sql,
        normalize_vector,
    )
except ImportError:
    print(
        "Embedding utilities not found. Please ensure scripts/utils/embedding_utils.py exists."
    )
    EMBEDDING_UTILS_AVAILABLE = False
else:
    EMBEDDING_UTILS_AVAILABLE = True

# Try to load settings using centralized config loader
try:
    from nexus.config import load_settings_as_dict

    _all_settings = load_settings_as_dict()
    SETTINGS = _all_settings.get("Agent Settings", {}).get("MEMNON", {})
except Exception as e:
    print(f"Warning: Could not load settings via config loader: {e}")
    SETTINGS = {}

# Configure logging from settings
if __name__ == "__main__":
    # Only a command-line run configures the root logger, never an import.
    log_file = SETTINGS.get("logging", {}).get("file", "memnon.log")
    log_level_str = SETTINGS.get("logging", {}).get("level", "INFO")
    log_console = SETTINGS.get("logging", {}).get("console", True)

    # Convert string log level to logging constant
    log_level = getattr(logging, log_level_str.upper(), logging.INFO)

    # Set up handlers
    handlers: list[logging.Handler] = []
    if log_file:
        handlers.append(logging.FileHandler(log_file))
    if log_console:
        handlers.append(logging.StreamHandler())

    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=handlers,
    )
logger = logging.getLogger("nexus.query")

from nexus.agents.memnon.utils.embedding_manager import load_local_model  # noqa: E402


# The registered [memnon.models] entries this import-era script can query
# with. A query loads only the one ``--model`` it names, from its local_path
# (issue #812): no Hugging Face download, no hardcoded default path, and a
# missing folder raises with the restore command instead of being skipped.
SCRIPT_EMBEDDERS = ("bge-large", "e5-large", "bge-small-custom")


def load_embedding_model(
    models_config: Mapping[str, Mapping[str, Any]], model_key: str
) -> Any:
    """Load the one queried embedder from its ``[memnon.models]`` local_path.

    Args:
        models_config: The ``[memnon.models]`` registry, keyed by entry name
        model_key: The entry the query embeds with

    Returns:
        The loaded SentenceTransformer

    Raises:
        RuntimeError: When the entry is not registered, or its local artifact
            is missing or fails to load.
    """
    if model_key not in models_config:
        raise RuntimeError(
            f"Embedding model '{model_key}' is not registered in "
            "[memnon.models]; register it with its local_path."
        )
    model = load_local_model(model_key, models_config[model_key])
    logger.info(f"Loaded embedding model: {model_key}")
    return model


# Try to import SQLAlchemy
try:
    import sqlalchemy as sa
    from sqlalchemy import text
    from sqlalchemy.orm import sessionmaker
except ImportError:
    logger.error("SQLAlchemy not found. Please install with: pip install sqlalchemy")
    sys.exit(1)

# Try to import pgvector
try:
    import pgvector
    from pgvector.sqlalchemy import Vector

    HAS_PGVECTOR = True
except ImportError:
    logger.error("pgvector not found. Please install with: pip install pgvector")
    sys.exit(1)

# Try to import numpy for vector operations
try:
    import numpy as np

    HAS_NUMPY = True
except ImportError:
    logger.error("numpy not found. Please install with: pip install numpy")
    HAS_NUMPY = False


class NarrativeSearcher:
    """
    Performs semantic search over narrative chunks using vector embeddings.
    """

    def __init__(self, db_url: str = None, model_key: Optional[str] = None):
        """
        Initialize the searcher with database connection.

        Args:
            db_url: PostgreSQL database URL
            model_key: The ``[memnon.models]`` entry semantic search embeds
                with; the only embedder loaded. None loads no embedder (text
                search only).
        """
        # Set default database URL if not provided
        default_db_url = SETTINGS.get("database", {}).get("url", None)
        self.db_url = db_url or os.environ.get("NEXUS_DB_URL", default_db_url)

        # Initialize database connection
        self.engine = create_slot_engine(self.db_url)
        self.Session = sessionmaker(bind=self.engine)

        # Load only the embedder this search uses.
        self.embedding_models: Dict[str, Any] = {}
        if model_key is not None:
            self.embedding_models[model_key] = load_embedding_model(
                SETTINGS.get("models", {}), model_key
            )

        # Check pgvector extension
        self._check_pgvector()

        logger.info("Connected to the configured database")
        logger.info(
            f"Available embedding models: {', '.join(self.embedding_models.keys())}"
        )

    def _check_pgvector(self):
        """Check if pgvector extension is properly installed."""
        try:
            with self.engine.connect() as connection:
                result = connection.execute(
                    text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
                ).scalar()
                if not result:
                    logger.error(
                        "pgvector extension not found in database. Please install it first."
                    )
                    sys.exit(1)
                logger.info("pgvector extension found in database.")
        except Exception as e:
            logger.error(f"Error checking pgvector extension: {e}")
            sys.exit(1)

    def generate_embedding(self, query: str, model_key: str) -> List[float]:
        """
        Generate an embedding for the query using the specified model.

        Args:
            query: Search query to embed
            model_key: Key of the model to use

        Returns:
            Embedding as a list of floats
        """
        if model_key not in self.embedding_models:
            logger.error(f"Model {model_key} not found in available embedding models")
            raise ValueError(
                f"Model {model_key} not found in available embedding models"
            )

        model = self.embedding_models[model_key]
        embedding = model.encode(query)

        return embedding.tolist()

    def semantic_search(
        self, query: str, model: str = "bge-large", limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Perform semantic search using vector similarity.

        Args:
            query: The search query
            model: The embedding model to use
            limit: Maximum number of results to return

        Returns:
            List of matching chunks with scores
        """
        # Generate embedding for the query
        try:
            query_embedding = self.generate_embedding(query, model)
        except Exception as e:
            logger.error(f"Error generating embedding: {e}")
            return []

        # Create a session
        session = self.Session()

        try:
            # Use the embedding utilities if available
            if EMBEDDING_UTILS_AVAILABLE:
                # Normalize the embedding for better results
                if HAS_NUMPY:
                    query_embedding = normalize_vector(query_embedding).tolist()

                # Get the correct table for this model
                embedding_table = get_table_for_model(model)

                # Get the vector dimensions for this model
                dimensions = get_model_dimensions(model)

                # Construct the SQL query using our utility function
                sql_query, table_used = construct_vector_search_sql(
                    model_name=model, filter_conditions=None, limit=limit
                )

                logger.info(
                    f"Using table {table_used} for model {model} ({dimensions}D)"
                )
            else:
                # Fall back to the original logic if utilities aren't available
                logger.warning(
                    "Embedding utilities not available, using fallback table selection"
                )

                # Determine the table and dimensions based on the model name
                if model.startswith("bge-small"):
                    dimensions = 384
                else:
                    dimensions = 1024
                embedding_table = f"chunk_embeddings_{dimensions:04d}d"

            # Create the query vector string representation directly in SQL
            query_vector_str = f"[{','.join(str(x) for x in query_embedding)}]"

            # Construct the SQL query
            raw_sql = f"""
                SELECT 
                    nc.id, 
                    nc.raw_text,
                    cm.season,
                    cm.episode,
                    cm.characters,
                    1 - (ce.embedding <=> '{query_vector_str}'::vector) AS similarity
                FROM 
                    narrative_chunks nc
                JOIN 
                    {embedding_table} ce ON nc.id = ce.chunk_id
                LEFT JOIN
                    chunk_metadata cm ON nc.id = cm.chunk_id
                WHERE
                    ce.model = '{model}'
                ORDER BY 
                    ce.embedding <=> '{query_vector_str}'::vector
                LIMIT {limit}
            """

            # Execute the raw SQL query
            result = session.execute(text(raw_sql))

            # Process results
            search_results = []
            for row in result:
                # Extract context from the raw text (truncate if too long)
                raw_text = row.raw_text
                if len(raw_text) > 500:
                    raw_text = raw_text[:497] + "..."

                # Extract characters if available
                characters = []
                if row.characters:
                    try:
                        characters = list(set(eval(row.characters)))
                    except:
                        pass

                # Format the result
                search_results.append(
                    {
                        "id": str(row.id),
                        "similarity": float(row.similarity),
                        "season": row.season or 0,
                        "episode": row.episode or 0,
                        "characters": characters,
                        "text": raw_text,
                    }
                )

            return search_results

        except Exception as e:
            logger.error(f"Error in semantic search: {e}")
            return []

        finally:
            session.close()

    def text_search(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Perform text-based search using PostgreSQL ILIKE.

        Args:
            query: The search query
            limit: Maximum number of results to return

        Returns:
            List of matching chunks
        """
        # Create a session
        session = self.Session()

        try:
            # Construct the SQL query with ILIKE for text matching
            sql_query = text(
                """
                SELECT 
                    nc.id, 
                    nc.raw_text,
                    cm.season,
                    cm.episode,
                    cm.characters
                FROM 
                    narrative_chunks nc
                LEFT JOIN
                    chunk_metadata cm ON nc.id = cm.chunk_id
                WHERE
                    nc.raw_text ILIKE :query_pattern
                LIMIT :limit
            """
            )

            # Execute the query with parameters
            result = session.execute(
                sql_query, {"query_pattern": f"%{query}%", "limit": limit}
            )

            # Process results
            search_results = []
            for row in result:
                # Extract context from the raw text (truncate if too long)
                raw_text = row.raw_text
                if len(raw_text) > 500:
                    raw_text = raw_text[:497] + "..."

                # Extract characters if available
                characters = []
                if row.characters:
                    try:
                        characters = list(set(eval(row.characters)))
                    except:
                        pass

                # Format the result
                search_results.append(
                    {
                        "id": str(row.id),
                        "season": row.season or 0,
                        "episode": row.episode or 0,
                        "characters": characters,
                        "text": raw_text,
                    }
                )

            return search_results

        except Exception as e:
            logger.error(f"Error in text search: {e}")
            return []

        finally:
            session.close()


def main():
    """
    Main entry point for the query script
    """
    parser = argparse.ArgumentParser(description="Query narrative chunks in NEXUS")
    parser.add_argument("query", help="Search query")

    # Get default values from settings
    default_model = SETTINGS.get("query", {}).get("default_model", "bge-large")
    default_limit = SETTINGS.get("query", {}).get("default_limit", 5)

    parser.add_argument(
        "--model",
        choices=list(SCRIPT_EMBEDDERS),
        default=default_model,
        help="Embedding model to use for semantic search",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=default_limit,
        help="Maximum number of results to return",
    )
    parser.add_argument(
        "--text-only",
        action="store_true",
        help="Use text search instead of vector search",
    )
    parser.add_argument("--db-url", dest="db_url", help="PostgreSQL database URL")
    args = parser.parse_args()

    # Initialize searcher
    searcher = NarrativeSearcher(
        db_url=args.db_url, model_key=None if args.text_only else args.model
    )

    # Perform search
    if args.text_only:
        print(f"Performing text search for: '{args.query}'")
        results = searcher.text_search(args.query, limit=args.limit)
    else:
        print(
            f"Performing semantic search for: '{args.query}' using model: {args.model}"
        )
        results = searcher.semantic_search(
            args.query, model=args.model, limit=args.limit
        )

    # Print results
    if not results:
        print("No results found.")
    else:
        print(f"\nFound {len(results)} results:")
        print("-" * 80)

        for i, result in enumerate(results):
            print(f"Result {i+1}:")
            if "similarity" in result:
                print(f"Similarity: {result['similarity']:.4f}")
            print(f"S{result['season']:02d}E{result['episode']:02d}")

            if result["characters"]:
                print(f"Characters: {', '.join(result['characters'])}")

            print(f"\n{result['text']}\n")
            print("-" * 80)


if __name__ == "__main__":
    main()
