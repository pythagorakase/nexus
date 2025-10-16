#!/usr/bin/env python3
"""
Fix empty content in batch generations by re-processing batch results.

This script identifies generations with empty content fields that came from
batch submissions, and re-processes them using the fixed content extraction logic.
"""

from __future__ import annotations

import argparse
import logging
from collections import defaultdict

from sqlalchemy import text

from nexus.audition import AuditionEngine, AuditionRepository

LOGGER = logging.getLogger(__name__)


def get_empty_content_batches(repository: AuditionRepository) -> dict[str, list[tuple[int, str]]]:
    """
    Get all batch_job_ids that have generations with empty content.

    Returns:
        Dict mapping batch_job_id to list of (generation_id, provider) tuples
    """
    query = """
        SELECT DISTINCT
            g.batch_job_id,
            c.provider,
            COUNT(g.id) as empty_count
        FROM apex_audition.generations g
        JOIN apex_audition.conditions c ON c.id = g.condition_id
        WHERE g.status = 'completed'
          AND g.batch_job_id IS NOT NULL
          AND (
              g.response_payload->>'content' IS NULL
              OR LENGTH(COALESCE(g.response_payload->>'content', '')) = 0
          )
        GROUP BY g.batch_job_id, c.provider
        ORDER BY empty_count DESC
    """

    with repository.engine.connect() as conn:
        result = conn.execute(text(query))
        batches = {}
        for row in result:
            batch_id = row[0]
            provider = row[1]
            empty_count = row[2]
            batches[batch_id] = (provider, empty_count)
        return batches


def main():
    parser = argparse.ArgumentParser(
        description="Fix empty content in batch generations"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be fixed without making changes"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging"
    )
    args = parser.parse_args()

    # Setup logging
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(message)s"
    )

    # Initialize engine
    repository = AuditionRepository()
    engine = AuditionEngine(repository=repository)

    # Step 1: Get all batches with empty content
    LOGGER.info("Finding batches with empty content...")
    empty_batches = get_empty_content_batches(repository)

    if not empty_batches:
        LOGGER.info("No batches with empty content found!")
        return

    LOGGER.info(f"Found {len(empty_batches)} batches with empty content")

    # Show summary
    total_empty = sum(count for _, count in empty_batches.values())
    by_provider = defaultdict(int)
    for provider, count in empty_batches.values():
        by_provider[provider] += count

    LOGGER.info(f"Total empty generations: {total_empty}")
    LOGGER.info("By provider:")
    for provider, count in sorted(by_provider.items()):
        LOGGER.info(f"  {provider}: {count} empty")

    if args.dry_run:
        LOGGER.info("\n[DRY RUN] Would re-process the following batches:")
        for batch_id, (provider, count) in empty_batches.items():
            LOGGER.info(f"  {batch_id[:20]}... ({provider}, {count} empty)")
        return

    # Step 2: Re-process each batch
    LOGGER.info("\nRe-processing batches...")
    success_count = 0
    error_count = 0

    for i, (batch_id, (provider, expected_count)) in enumerate(empty_batches.items(), 1):
        LOGGER.info(f"\n[{i}/{len(empty_batches)}] Processing batch {batch_id[:20]}... ({provider})")

        try:
            results = engine.retrieve_batch_results(batch_id, provider)
            LOGGER.info(f"  ✓ Processed {len(results)} results")
            success_count += len(results)
        except Exception as e:
            LOGGER.error(f"  ✗ Failed to process batch: {e}")
            error_count += expected_count

    # Step 3: Verify fix
    LOGGER.info("\n" + "="*60)
    LOGGER.info("Verifying fix...")

    remaining_empty = get_empty_content_batches(repository)

    if remaining_empty:
        LOGGER.warning(f"Still have {len(remaining_empty)} batches with empty content")
        remaining_count = sum(count for _, count in remaining_empty.values())
        LOGGER.warning(f"Total remaining empty: {remaining_count}")
    else:
        LOGGER.info("✓ All batch generations now have content!")

    LOGGER.info("="*60)
    LOGGER.info(f"Successfully fixed: {success_count}")
    LOGGER.info(f"Errors: {error_count}")
    LOGGER.info("="*60)


if __name__ == "__main__":
    main()
