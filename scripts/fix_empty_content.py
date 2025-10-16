#!/usr/bin/env python3
"""
Fix generations with empty content by re-retrieving their batches.

Some extended thinking generations ended up with empty content fields
due to extraction issues. This script re-retrieves those batches.
"""

from __future__ import annotations

import argparse
import logging
from typing import List

from sqlalchemy import text

from nexus.audition import AuditionEngine, AuditionRepository

LOGGER = logging.getLogger(__name__)


def get_empty_content_batches(repository: AuditionRepository) -> List[tuple[str, str]]:
    """
    Get batch IDs and providers for generations with empty content.

    Returns:
        List of (batch_id, provider) tuples
    """
    query = """
        SELECT DISTINCT g.batch_job_id, c.provider
        FROM apex_audition.generations g
        JOIN apex_audition.conditions c ON g.condition_id = c.id
        WHERE g.status = 'completed'
          AND g.response_payload->>'content' = ''
          AND g.batch_job_id IS NOT NULL
        ORDER BY g.batch_job_id
    """

    with repository.engine.connect() as conn:
        result = conn.execute(text(query))
        return [(row[0], row[1]) for row in result]


def main():
    parser = argparse.ArgumentParser(
        description="Fix generations with empty content by re-retrieving batches"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be fixed without making changes",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging",
    )
    args = parser.parse_args()

    # Setup logging
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    repository = AuditionRepository()
    engine = AuditionEngine(repository=repository)

    # Get empty content batches
    LOGGER.info("Finding batches with empty content...")
    batches = get_empty_content_batches(repository)

    if not batches:
        LOGGER.info("No batches with empty content found!")
        return

    LOGGER.info(f"Found {len(batches)} batches with empty content")

    for batch_id, provider in batches:
        LOGGER.info(f"  {batch_id} ({provider})")

    if args.dry_run:
        LOGGER.info("[DRY RUN] Would re-retrieve these batches")
        return

    # Re-retrieve each batch
    fixed = 0
    failed = 0

    for batch_id, provider in batches:
        LOGGER.info(f"Re-retrieving batch {batch_id} ({provider})...")
        try:
            results = engine.retrieve_batch_results(batch_id, provider)
            LOGGER.info(f"  Fixed {len(results)} generations")
            fixed += len(results)
        except Exception as e:
            LOGGER.error(f"  Failed to retrieve batch {batch_id}: {e}")
            failed += 1

    LOGGER.info("=" * 80)
    LOGGER.info(f"Fixed {fixed} generations")
    LOGGER.info(f"Failed {failed} batches")
    LOGGER.info("=" * 80)


if __name__ == "__main__":
    main()
