#!/usr/bin/env python3
"""
Test script for the IDF Dictionary implementation
"""

import sys
import os
import logging
from pathlib import Path

# Setup basic logging
if __name__ == "__main__":
    # Only a command-line run configures the root logger, never an import.
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
logger = logging.getLogger("idf_test")

# Make sure parent directory is in path
sys.path.append(str(Path(__file__).parent.parent.parent))

# Import our modules
from agents.memnon.utils.idf_dictionary import IDFDictionary
import argparse


def load_database_url() -> str:
    """Return the MEMNON database URL configured in nexus.toml."""
    from nexus.config import load_settings

    return load_settings().memnon.database.url


def main():
    parser = argparse.ArgumentParser(description="Test IDF Dictionary functionality")
    parser.add_argument(
        "--rebuild", action="store_true", help="Force rebuild of IDF dictionary"
    )
    parser.add_argument("--db-url", help="PostgreSQL database URL")
    parser.add_argument("--terms", nargs="+", help="Terms to check IDF values for")
    parser.add_argument("--query", help="Test query to generate weighted format")
    args = parser.parse_args()

    # Get database URL
    db_url = args.db_url or load_database_url()
    if not db_url:
        logger.error(
            "No database URL provided. Use --db-url or configure in settings.json"
        )
        return 1

    try:
        # Initialize and build IDF dictionary
        logger.info("Initializing IDF dictionary with the configured database")
        idf_dict = IDFDictionary(db_url)

        # Build or load
        idf_dict.build_dictionary(force_rebuild=args.rebuild)
        logger.info(f"IDF dictionary contains {len(idf_dict.idf_dict)} terms")

        # Print some stats
        logger.info(f"Total document count: {idf_dict.total_docs}")

        # Calculate some statistics
        all_idf_values = list(idf_dict.idf_dict.values())
        if all_idf_values:
            avg_idf = sum(all_idf_values) / len(all_idf_values)
            max_idf = max(all_idf_values)
            min_idf = min(all_idf_values)
            logger.info(
                f"IDF statistics: avg={avg_idf:.4f}, min={min_idf:.4f}, max={max_idf:.4f}"
            )
        else:
            logger.warning("No IDF values available for statistics")

        # Check specific terms
        if args.terms:
            logger.info("--- Term IDF values ---")
            for term in args.terms:
                idf_value = idf_dict.get_idf(term)
                weight_class = idf_dict.get_weight_class(term)
                logger.info(
                    f"Term '{term}': IDF={idf_value:.4f}, Weight Class={weight_class}"
                )

        # Test query weighting
        if args.query:
            weighted_query = idf_dict.generate_weighted_query(args.query)
            logger.info(f"Original query: '{args.query}'")
            logger.info(f"Weighted query: '{weighted_query}'")

            # Show weights for each term
            for term in args.query.lower().split():
                idf = idf_dict.get_idf(term)
                weight = idf_dict.get_weight_class(term)
                logger.info(f"  - '{term}': IDF={idf:.4f}, Weight={weight}")

        return 0

    except Exception as e:
        logger.error(f"Error in IDF test: {e}")
        import traceback

        logger.error(traceback.format_exc())
        return 1


if __name__ == "__main__":
    sys.exit(main())
