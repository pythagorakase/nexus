#!/usr/bin/env python3
"""
Fix remaining encoding corruptions by re-retrieving specific batches.

Uses SQL LIKE patterns directly to find all corrupted content.
"""

from __future__ import annotations

import argparse
import logging
from typing import List

from sqlalchemy import text

from nexus.audition import AuditionEngine, AuditionRepository

LOGGER = logging.getLogger(__name__)


def get_corrupted_batches(repository: AuditionRepository) -> List[tuple[str, str]]:
    """
    Get all batches with encoding corruption using direct SQL patterns.

    Returns:
        List of (batch_id, provider) tuples
    """
    # Use raw SQL with LIKE patterns for corruption detection
    query = """
        SELECT DISTINCT g.batch_job_id, c.provider
        FROM apex_audition.generations g
        JOIN apex_audition.conditions c ON g.condition_id = c.id
        WHERE g.status = 'completed'
          AND g.batch_job_id IS NOT NULL
          AND (
              g.response_payload->>'content' LIKE '%â€%'
              OR g.response_payload->>'content' LIKE '%ğŸ%'
              OR g.response_payload->>'content' LIKE '%‚Äî%'
              OR g.response_payload->>'content' LIKE '%üì%'
          )
        ORDER BY g.batch_job_id
    """

    with repository.engine.connect() as conn:
        result = conn.execute(text(query))
        return [(row[0], row[1]) for row in result]


def main():
    parser = argparse.ArgumentParser(
        description="Fix all remaining encoding corruptions"
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

    # Get corrupted batches
    LOGGER.info("Finding all batches with encoding corruption...")
    batches = get_corrupted_batches(repository)

    if not batches:
        LOGGER.info("No corrupted batches found!")
        return

    LOGGER.info(f"Found {len(batches)} batches with encoding corruption")
    for batch_id, provider in batches:
        LOGGER.info(f"  {batch_id} ({provider})")

    if args.dry_run:
        LOGGER.info("[DRY RUN] Would re-retrieve these batches")
        return

    # Re-retrieve each batch
    fixed = 0
    failed = 0

    for batch_id, provider in batches:
        LOGGER.info(f"Re-retrieving batch {batch_id}...")
        try:
            results = engine.retrieve_batch_results(batch_id, provider)
            LOGGER.info(f"  Fixed {len(results)} generations")
            fixed += len(results)
        except Exception as e:
            LOGGER.error(f"  Failed: {e}")
            failed += 1

    LOGGER.info("=" * 80)
    LOGGER.info(f"Fixed {fixed} generations")
    LOGGER.info(f"Failed {failed} batches")
    LOGGER.info("=" * 80)


if __name__ == "__main__":
    main()
