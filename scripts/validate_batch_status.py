#!/usr/bin/env python3
"""
Validate batch job status before performing database resets.

This script checks the actual status of batch jobs on provider APIs (OpenAI/Anthropic)
and helps determine whether generations should be:
- Reset to batch_pending (if batch is still processing)
- Retrieved (if batch is complete)
- Marked as error (if batch failed/expired)

Use this before manually resetting generation statuses to avoid creating orphaned records.
"""

from __future__ import annotations

import argparse
import logging
from collections import defaultdict
from typing import Dict, List

from sqlalchemy import text

from nexus.audition import AuditionRepository
from nexus.audition.batch_clients import (
    AnthropicBatchClient,
    BatchStatus,
    OpenAIBatchClient,
)

LOGGER = logging.getLogger(__name__)


def validate_batch_ids(
    batch_ids: List[str],
    provider: str,
) -> Dict[str, Dict[str, any]]:
    """
    Validate batch IDs against provider API.

    Args:
        batch_ids: List of batch job IDs to validate
        provider: Provider name ("openai" or "anthropic")

    Returns:
        Dictionary mapping batch_id -> {status, valid, recommendation}
    """
    if provider.lower() == "openai":
        client = OpenAIBatchClient()
    elif provider.lower() == "anthropic":
        client = AnthropicBatchClient()
    else:
        raise ValueError(f"Unsupported provider: {provider}")

    results = {}

    for i, batch_id in enumerate(batch_ids, 1):
        if i % 10 == 0:
            LOGGER.info(f"Validated {i}/{len(batch_ids)} batches...")

        try:
            batch_job = client.get_status(batch_id)
            status = batch_job.status

            # Determine recommendation based on status
            if status == BatchStatus.COMPLETED:
                recommendation = "RETRIEVE_RESULTS"
                message = "Batch completed - results should be retrieved"
            elif status in [BatchStatus.IN_PROGRESS, BatchStatus.PENDING]:
                recommendation = "KEEP_PENDING"
                message = "Batch still processing - keep as batch_pending"
            elif status in [BatchStatus.FAILED, BatchStatus.EXPIRED, BatchStatus.CANCELLED]:
                recommendation = "MARK_ERROR"
                message = f"Batch {status.value} - mark generations as error"
            else:
                recommendation = "UNKNOWN"
                message = f"Unknown status: {status.value}"

            results[batch_id] = {
                "status": status.value,
                "valid": True,
                "recommendation": recommendation,
                "message": message,
                "request_counts": batch_job.request_counts if hasattr(batch_job, "request_counts") else None,
            }

        except Exception as e:
            results[batch_id] = {
                "status": "ERROR",
                "valid": False,
                "recommendation": "MARK_ERROR",
                "message": f"Failed to query provider: {str(e)}",
                "request_counts": None,
            }
            LOGGER.error(f"Failed to validate batch {batch_id}: {e}")

    return results


def get_batches_by_provider(repository: AuditionRepository) -> Dict[str, List[str]]:
    """
    Get all batch_pending batch_job_ids grouped by provider.

    Returns:
        Dictionary mapping provider -> [batch_ids]
    """
    query = """
        SELECT DISTINCT g.batch_job_id, c.provider
        FROM apex_audition.generations g
        JOIN apex_audition.conditions c ON g.condition_id = c.id
        WHERE g.status = 'batch_pending'
          AND g.batch_job_id IS NOT NULL
        ORDER BY c.provider, g.batch_job_id
    """

    batches_by_provider = defaultdict(list)

    with repository.engine.connect() as conn:
        result = conn.execute(text(query))
        for row in result:
            batch_id = row[0]
            provider = row[1].lower()
            batches_by_provider[provider].append(batch_id)

    return dict(batches_by_provider)


def print_summary(results_by_provider: Dict[str, Dict[str, Dict]]) -> None:
    """Print a summary of validation results."""
    LOGGER.info("\n" + "=" * 80)
    LOGGER.info("BATCH VALIDATION SUMMARY")
    LOGGER.info("=" * 80)

    for provider, results in results_by_provider.items():
        LOGGER.info(f"\n{provider.upper()} Batches ({len(results)} total):")

        # Group by recommendation
        by_recommendation = defaultdict(list)
        for batch_id, info in results.items():
            by_recommendation[info["recommendation"]].append((batch_id, info))

        for recommendation, batch_infos in sorted(by_recommendation.items()):
            LOGGER.info(f"\n  {recommendation}: {len(batch_infos)} batches")
            for batch_id, info in batch_infos[:5]:  # Show first 5
                LOGGER.info(f"    {batch_id}: {info['message']}")
            if len(batch_infos) > 5:
                LOGGER.info(f"    ... and {len(batch_infos) - 5} more")

    LOGGER.info("\n" + "=" * 80)
    LOGGER.info("RECOMMENDATIONS:")
    LOGGER.info("=" * 80)

    total_retrieve = sum(
        sum(1 for info in results.values() if info["recommendation"] == "RETRIEVE_RESULTS")
        for results in results_by_provider.values()
    )
    total_keep = sum(
        sum(1 for info in results.values() if info["recommendation"] == "KEEP_PENDING")
        for results in results_by_provider.values()
    )
    total_error = sum(
        sum(1 for info in results.values() if info["recommendation"] == "MARK_ERROR")
        for results in results_by_provider.values()
    )

    if total_retrieve > 0:
        LOGGER.info(f"\n1. RETRIEVE {total_retrieve} completed batches:")
        LOGGER.info("   poetry run python scripts/auto_poll_batches.py")

    if total_error > 0:
        LOGGER.info(f"\n2. MARK {total_error} failed/expired batches as errors:")
        LOGGER.info("   Use recover_batch_mismatches.py with --mark-unfixable-as-errors")

    if total_keep > 0:
        LOGGER.info(f"\n3. KEEP {total_keep} in-progress batches as batch_pending:")
        LOGGER.info("   No action needed - poller will check them automatically")

    LOGGER.info("\n" + "=" * 80)


def main():
    parser = argparse.ArgumentParser(
        description="Validate batch job status before database operations"
    )
    parser.add_argument(
        "--provider",
        choices=["openai", "anthropic", "both"],
        default="both",
        help="Provider to validate (default: both)",
    )
    parser.add_argument(
        "--batch-ids",
        nargs="+",
        help="Specific batch IDs to validate (optional)",
    )
    parser.add_argument(
        "--verbose", action="store_true", help="Enable debug logging"
    )
    args = parser.parse_args()

    # Setup logging
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(message)s")

    repository = AuditionRepository()

    if args.batch_ids:
        # Validate specific batch IDs
        LOGGER.info(f"Validating {len(args.batch_ids)} specific batch IDs...")
        results = validate_batch_ids(args.batch_ids, args.provider)
        results_by_provider = {args.provider: results}
    else:
        # Validate all batch_pending batches
        LOGGER.info("Fetching all batch_pending batch IDs from database...")
        batches_by_provider = get_batches_by_provider(repository)

        if not batches_by_provider:
            LOGGER.info("No batch_pending generations found!")
            return

        # Filter by provider if specified
        if args.provider != "both":
            batches_by_provider = {
                k: v for k, v in batches_by_provider.items() if k == args.provider.lower()
            }

        LOGGER.info(f"Found batches: {', '.join(f'{p.upper()}: {len(b)}' for p, b in batches_by_provider.items())}")

        # Validate all batches
        results_by_provider = {}
        for provider, batch_ids in batches_by_provider.items():
            LOGGER.info(f"\nValidating {len(batch_ids)} {provider.upper()} batches...")
            results_by_provider[provider] = validate_batch_ids(batch_ids, provider)

    # Print summary
    print_summary(results_by_provider)


if __name__ == "__main__":
    main()
