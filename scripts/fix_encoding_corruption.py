#!/usr/bin/env python3
"""
Fix encoding corruption in Anthropic batch generations.

This script identifies generations with UTF-8 encoding issues (mojibake)
and re-retrieves the batch results with proper encoding to fix them.

The root cause was using response.text instead of response.content.decode('utf-8')
in batch_clients.py, which caused the requests library to misdetect UTF-8 as another
encoding, corrupting emojis and special characters.

Examples of corruption:
- "—" (em-dash) became "‚Äî"
- "📍" (location emoji) became "üìç"
- "🎬" (clapper emoji) became "üì∫"
"""

from __future__ import annotations

import argparse
import logging
from collections import defaultdict
from typing import Dict, List, Set

from sqlalchemy import text

from nexus.audition import AuditionEngine, AuditionRepository

LOGGER = logging.getLogger(__name__)

# Corruption markers that indicate encoding issues
# These are common UTF-8 mojibake patterns from Windows-1252/ISO-8859-1 misinterpretation
CORRUPTION_MARKERS = [
    # Pattern set 1 (Oct 16 batches)
    "‚Äî",  # Corrupted em-dash
    "üìç",  # Corrupted emoji
    "üì∫",  # Corrupted emoji
    "‚Üí",  # Corrupted arrow
    # Pattern set 2 (Oct 10/14 batches)
    "\u00e2\u0080\u0094",  # Corrupted em-dash (different encoding) - â€"
    "\u011f\u0178",        # Corrupted emoji prefix (catches ğŸ"�, ğŸš¨, ğŸ"Œ, etc.) - ğŸ
    "\u00e2\u009c",        # Corrupted checkmark prefix - âœ
    "\u00ef\u00b8",        # Corrupted emoji modifier - ï¸
]


def find_corrupted_generations(repository: AuditionRepository) -> List[Dict]:
    """
    Find all generations with encoding corruption.

    Returns:
        List of dicts with {id, batch_job_id, condition_id}
    """
    # Build OR conditions for all corruption markers
    or_conditions = " OR ".join(
        f"g.response_payload->>'content' LIKE '%{marker}%'"
        for marker in CORRUPTION_MARKERS
    )

    query = f"""
        SELECT
            g.id,
            g.batch_job_id,
            g.condition_id,
            g.prompt_id,
            g.replicate_index,
            c.provider
        FROM apex_audition.generations g
        JOIN apex_audition.conditions c ON g.condition_id = c.id
        WHERE g.status = 'completed'
          AND ({or_conditions})
        ORDER BY g.batch_job_id, g.id
    """

    with repository.engine.connect() as conn:
        result = conn.execute(text(query))
        return [
            {
                "id": row[0],
                "batch_job_id": row[1],
                "condition_id": row[2],
                "prompt_id": row[3],
                "replicate_index": row[4],
                "provider": row[5],
            }
            for row in result
        ]


def group_by_batch(corrupted: List[Dict]) -> Dict[str, List[Dict]]:
    """Group corrupted generations by batch_job_id."""
    by_batch = defaultdict(list)
    for gen in corrupted:
        if gen["batch_job_id"]:
            by_batch[gen["batch_job_id"]].append(gen)
    return dict(by_batch)


def fix_batch(
    batch_id: str,
    provider: str,
    corrupted_ids: Set[int],
    engine: AuditionEngine,
    repository: AuditionRepository,
    dry_run: bool = False,
) -> tuple[int, int]:
    """
    Re-retrieve batch results and update corrupted generations.

    Returns:
        Tuple of (fixed_count, failed_count)
    """
    LOGGER.info(f"Processing batch {batch_id} ({len(corrupted_ids)} corrupted generations)")

    if dry_run:
        LOGGER.info(f"[DRY RUN] Would re-retrieve batch {batch_id}")
        return len(corrupted_ids), 0

    try:
        # Re-retrieve batch results with fixed encoding
        results = engine.retrieve_batch_results(batch_id, provider)
        LOGGER.info(f"Retrieved {len(results)} results from batch {batch_id}")

        # Count how many corrupted generations were fixed
        fixed_count = 0
        for result in results:
            if result.id in corrupted_ids:
                fixed_count += 1
                LOGGER.debug(f"Fixed generation {result.id}")

        return fixed_count, len(corrupted_ids) - fixed_count

    except Exception as e:
        LOGGER.error(f"Failed to re-retrieve batch {batch_id}: {e}")
        return 0, len(corrupted_ids)


def main():
    parser = argparse.ArgumentParser(
        description="Fix encoding corruption in Anthropic batch generations"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be fixed without making changes",
    )
    parser.add_argument(
        "--batch-id",
        help="Fix only a specific batch ID",
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

    # Find all corrupted generations
    LOGGER.info("Scanning for corrupted generations...")
    corrupted = find_corrupted_generations(repository)

    if not corrupted:
        LOGGER.info("No corrupted generations found!")
        return

    LOGGER.info(f"Found {len(corrupted)} corrupted generations")

    # Group by batch
    by_batch = group_by_batch(corrupted)
    LOGGER.info(f"Corrupted generations span {len(by_batch)} batches")

    # Filter by specific batch if requested
    if args.batch_id:
        if args.batch_id not in by_batch:
            LOGGER.error(f"Batch {args.batch_id} not found in corrupted batches")
            return
        by_batch = {args.batch_id: by_batch[args.batch_id]}
        LOGGER.info(f"Filtering to batch {args.batch_id} only")

    # Show summary
    LOGGER.info("=" * 80)
    LOGGER.info("CORRUPTION SUMMARY")
    LOGGER.info("=" * 80)
    for batch_id, gens in sorted(by_batch.items()):
        providers = {g["provider"] for g in gens}
        LOGGER.info(f"  {batch_id}: {len(gens)} corrupted ({', '.join(providers)})")
    LOGGER.info("=" * 80)

    if args.dry_run:
        LOGGER.info("[DRY RUN] Would fix corrupted generations")
        return

    # Fix each batch
    total_fixed = 0
    total_failed = 0

    for batch_id, gens in by_batch.items():
        provider = gens[0]["provider"]  # All in same batch have same provider
        corrupted_ids = {g["id"] for g in gens}

        fixed, failed = fix_batch(
            batch_id,
            provider,
            corrupted_ids,
            engine,
            repository,
            dry_run=args.dry_run,
        )

        total_fixed += fixed
        total_failed += failed

    # Final summary
    LOGGER.info("=" * 80)
    LOGGER.info("FINAL RESULTS")
    LOGGER.info("=" * 80)
    LOGGER.info(f"Fixed: {total_fixed}")
    LOGGER.info(f"Failed: {total_failed}")
    LOGGER.info("=" * 80)


if __name__ == "__main__":
    main()
