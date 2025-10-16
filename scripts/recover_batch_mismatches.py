#!/usr/bin/env python3
"""
Recover batch_job_id mismatches from bulk async submission.

During bulk batch submissions, batch_job_ids can sometimes be assigned to the
wrong runs in the database due to concurrent updates. This script:

1. Identifies all stuck batch_pending generations
2. Queries provider APIs (OpenAI or Anthropic) to get actual run_ids from batch results
3. Builds a mapping to find correct batch_job_ids
4. Updates the database with correct assignments

Supports both OpenAI and Anthropic batch APIs.
"""

from __future__ import annotations

import argparse
import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Tuple, NamedTuple

from sqlalchemy import text

from nexus.audition import AuditionRepository
from nexus.audition.batch_clients import OpenAIBatchClient, AnthropicBatchClient

LOGGER = logging.getLogger(__name__)


class BatchInfo(NamedTuple):
    """Information about a batch from a provider."""
    batch_id: str
    provider: str  # "openai" or "anthropic"
    status: str
    run_id: str | None  # None if status != completed or results unavailable


def get_stuck_generations(repository: AuditionRepository) -> List[Tuple[str, str, int, int]]:
    """
    Get all stuck batch_pending generations from the database.

    Returns list of (run_id, batch_job_id, prompt_id, replicate_index) tuples.
    """
    query = """
        SELECT DISTINCT run_id, batch_job_id, prompt_id, replicate_index
        FROM apex_audition.generations
        WHERE status = 'batch_pending'
          AND batch_job_id IS NOT NULL
          AND started_at > NOW() - INTERVAL '7 days'
        ORDER BY run_id, prompt_id, replicate_index
    """

    with repository.engine.connect() as conn:
        result = conn.execute(text(query))
        return [(row[0], row[1], row[2], row[3]) for row in result]


def get_all_batches_from_stuck_runs(repository: AuditionRepository, provider: str | None = None) -> List[Tuple[str, str]]:
    """
    Get all batch_job_ids with their providers associated with currently stuck runs.

    This gets batch_job_ids for ALL generations that share a run_id with any
    stuck generation, not just the stuck ones. This ensures we find the correct
    batches even if they're assigned to different runs.

    Args:
        repository: Database repository
        provider: Optional provider filter ("openai" or "anthropic")

    Returns:
        List of (batch_job_id, provider) tuples
    """
    provider_filter = ""
    if provider:
        provider_filter = f"AND c.provider = '{provider.lower()}'"

    query = f"""
        WITH stuck_run_ids AS (
            SELECT DISTINCT run_id
            FROM apex_audition.generations
            WHERE status = 'batch_pending'
              AND batch_job_id IS NOT NULL
              AND started_at > NOW() - INTERVAL '7 days'
        )
        SELECT DISTINCT g.batch_job_id, c.provider
        FROM apex_audition.generations g
        JOIN apex_audition.conditions c ON g.condition_id = c.id
        WHERE g.batch_job_id IS NOT NULL
          AND g.started_at > NOW() - INTERVAL '7 days'
          {provider_filter}
        ORDER BY g.batch_job_id
    """

    with repository.engine.connect() as conn:
        result = conn.execute(text(query))
        return [(row[0], row[1].lower()) for row in result]


def _extract_run_id(custom_id: str) -> str | None:
    """Extract the original run_id from a batch custom_id.

    Works for both OpenAI and Anthropic batch formats, which use the same convention.
    """

    # Multi-lane batches include the condition id before prompt_id/replicate,
    # resulting in "{run_id}_{condition_id}_{prompt_id}_{replicate}". Single-lane
    # batches omit the condition segment and use three parts. rsplit(..., 3)
    # preserves any underscores in the run id while peeling off the tail
    # segments.
    parts = custom_id.rsplit("_", 3)

    if len(parts) == 4:
        run_id, _condition_id, _prompt_id, _replicate = parts
        return run_id

    if len(parts) == 3:
        run_id, _prompt_id, _replicate = parts
        return run_id

    LOGGER.warning("Unexpected custom_id format: %s", custom_id)
    return None


def build_batch_to_run_mapping(
    batches_with_providers: List[Tuple[str, str]],
    openai_client: OpenAIBatchClient | None = None,
    anthropic_client: AnthropicBatchClient | None = None,
) -> Tuple[Dict[str, str], Dict[str, List[BatchInfo]]]:
    """
    Query provider APIs for each batch and extract run_id from custom_ids.

    Args:
        batches_with_providers: List of (batch_id, provider) tuples
        openai_client: OpenAI batch client (created if needed)
        anthropic_client: Anthropic batch client (created if needed)

    Returns:
        - completed_mapping: {batch_id: run_id} for completed batches only
        - status_groups: {status: [BatchInfo]} grouped by batch status
    """
    completed_mapping = {}
    status_groups = defaultdict(list)

    # Group batches by provider for efficient processing
    openai_batches = [batch_id for batch_id, provider in batches_with_providers if provider == "openai"]
    anthropic_batches = [batch_id for batch_id, provider in batches_with_providers if provider == "anthropic"]

    # Process OpenAI batches
    if openai_batches:
        if openai_client is None:
            openai_client = OpenAIBatchClient()
        LOGGER.info(f"Processing {len(openai_batches)} OpenAI batches...")

        for i, batch_id in enumerate(openai_batches, 1):
            try:
                if i % 10 == 0:
                    LOGGER.info(f"  Processed {i}/{len(openai_batches)} OpenAI batches...")

                batch_job = openai_client.get_status(batch_id)
                status = batch_job.status.value

                # Try to extract run_id for completed batches
                run_id = None
                if status == "completed":
                    try:
                        results = openai_client.retrieve_results(batch_job)
                        if results:
                            custom_id = results[0].custom_id
                            run_id = _extract_run_id(custom_id)
                            if run_id is None:
                                LOGGER.warning(
                                    "OpenAI batch %s completed but run_id could not be parsed from %s",
                                    batch_id,
                                    custom_id,
                                )
                            else:
                                completed_mapping[batch_id] = run_id
                                LOGGER.debug(f"Batch {batch_id} (OpenAI) → run {run_id}")
                        else:
                            LOGGER.warning(f"OpenAI batch {batch_id} completed but has no results")
                    except Exception as e:
                        LOGGER.error(f"Failed to retrieve OpenAI results for batch {batch_id}: {e}")

                # Track all batches by status
                batch_info = BatchInfo(batch_id=batch_id, provider="openai", status=status, run_id=run_id)
                status_groups[status].append(batch_info)

            except Exception as e:
                LOGGER.error(f"Failed to get OpenAI status for batch {batch_id}: {e}")
                continue

    # Process Anthropic batches
    if anthropic_batches:
        if anthropic_client is None:
            anthropic_client = AnthropicBatchClient()
        LOGGER.info(f"Processing {len(anthropic_batches)} Anthropic batches...")

        for i, batch_id in enumerate(anthropic_batches, 1):
            try:
                if i % 10 == 0:
                    LOGGER.info(f"  Processed {i}/{len(anthropic_batches)} Anthropic batches...")

                batch_job = anthropic_client.get_status(batch_id)
                status = batch_job.status.value

                # Try to extract run_id for completed batches
                run_id = None
                if status == "completed":
                    try:
                        results = anthropic_client.retrieve_results(batch_job)
                        if results:
                            custom_id = results[0].custom_id
                            run_id = _extract_run_id(custom_id)
                            if run_id is None:
                                LOGGER.warning(
                                    "Anthropic batch %s completed but run_id could not be parsed from %s",
                                    batch_id,
                                    custom_id,
                                )
                            else:
                                completed_mapping[batch_id] = run_id
                                LOGGER.debug(f"Batch {batch_id} (Anthropic) → run {run_id}")
                        else:
                            LOGGER.warning(f"Anthropic batch {batch_id} completed but has no results")
                    except Exception as e:
                        LOGGER.error(f"Failed to retrieve Anthropic results for batch {batch_id}: {e}")

                # Track all batches by status
                batch_info = BatchInfo(batch_id=batch_id, provider="anthropic", status=status, run_id=run_id)
                status_groups[status].append(batch_info)

            except Exception as e:
                LOGGER.error(f"Failed to get Anthropic status for batch {batch_id}: {e}")
                continue

    return completed_mapping, dict(status_groups)


def find_correct_batch_ids(
    stuck_runs: List[Tuple[str, str, int, int]],
    batch_to_run: Dict[str, str],
    status_groups: Dict[str, List[BatchInfo]]
) -> Tuple[Dict[str, str], List[str]]:
    """
    Find the correct batch_job_id for each stuck run.

    Args:
        stuck_runs: List of (run_id, wrong_batch_id, prompt_id, replicate_index)
        batch_to_run: Mapping of batch_id -> actual_run_id from completed batches
        status_groups: Batch status information grouped by status

    Returns:
        - corrections: {run_id: correct_batch_id} for fixable runs
        - unfixable_runs: List of run_ids that can't be fixed (batches failed/expired)
    """
    # Build reverse mapping: run_id -> batch_id (from OpenAI completed batches)
    run_to_batch = {run_id: batch_id for batch_id, run_id in batch_to_run.items()}

    # Build mapping of wrong_batch_id -> actual_run_id to detect misassignments
    wrong_batch_to_actual_run = {}
    for batch_id, run_id in batch_to_run.items():
        wrong_batch_to_actual_run[batch_id] = run_id

    corrections = {}
    unfixable_runs = []
    stuck_runs_set = set(run_id for run_id, _, _, _ in stuck_runs)

    LOGGER.info(f"\nAnalyzing {len(stuck_runs_set)} unique stuck runs...")
    LOGGER.info(f"Have batch results for {len(run_to_batch)} runs from OpenAI")

    # Show batch status breakdown
    LOGGER.info("\nBatch status breakdown:")
    for status, batches in sorted(status_groups.items()):
        LOGGER.info(f"  {status}: {len(batches)} batches")

    matched = 0
    misassigned = 0
    not_found = 0

    for run_id, wrong_batch_id, _, _ in stuck_runs:
        if run_id in corrections or run_id in unfixable_runs:
            continue

        # Check if this run has a completed batch in OpenAI
        if run_id in run_to_batch:
            correct_batch_id = run_to_batch[run_id]

            if correct_batch_id == wrong_batch_id:
                matched += 1
                LOGGER.debug(f"Run {run_id}: batch_job_id already correct ({correct_batch_id})")
            else:
                misassigned += 1
                corrections[run_id] = correct_batch_id

                # Show what the wrong batch actually contains
                actual_run = wrong_batch_to_actual_run.get(wrong_batch_id, "unknown")
                LOGGER.info(
                    f"Run {run_id}: {wrong_batch_id[:20]}... (contains run {actual_run[:8]}...) "
                    f"→ {correct_batch_id[:20]}... (correct)"
                )
        else:
            not_found += 1
            unfixable_runs.append(run_id)
            LOGGER.warning(f"Run {run_id}: No completed batch found in OpenAI")

    LOGGER.info(f"\nMatching summary:")
    LOGGER.info(f"  ✓ Already correct: {matched}")
    LOGGER.info(f"  ⚠ Misassigned (fixable): {misassigned}")
    LOGGER.info(f"  ✗ Not found (unfixable): {not_found}")

    return corrections, unfixable_runs


def apply_corrections(
    repository: AuditionRepository,
    corrections: Dict[str, str],
    dry_run: bool = False
) -> int:
    """
    Update database with correct batch_job_ids.

    Returns number of generations updated.
    """
    count = 0

    for run_id, correct_batch_id in corrections.items():
        update_query = """
            UPDATE apex_audition.generations
            SET batch_job_id = :correct_batch_id
            WHERE run_id = :run_id
              AND status = 'batch_pending'
            RETURNING id
        """

        if dry_run:
            LOGGER.info(f"[DRY RUN] Would update run {run_id} to batch {correct_batch_id}")
        else:
            with repository.engine.begin() as conn:
                result = conn.execute(
                    text(update_query),
                    {"run_id": run_id, "correct_batch_id": correct_batch_id}
                )
                updated_ids = [row[0] for row in result]
                count += len(updated_ids)
                LOGGER.info(f"Updated {len(updated_ids)} generations for run {run_id}")

    return count


def mark_unfixable_as_errors(
    repository: AuditionRepository,
    unfixable_runs: List[str],
    dry_run: bool = False
) -> int:
    """
    Mark unfixable runs as errors (batches failed/expired on OpenAI side).

    Returns number of generations marked as errors.
    """
    if not unfixable_runs:
        return 0

    count = 0
    for run_id in unfixable_runs:
        update_query = """
            UPDATE apex_audition.generations
            SET status = 'error',
                error_message = 'Batch job failed or expired on provider side'
            WHERE run_id = :run_id
              AND status = 'batch_pending'
            RETURNING id
        """

        if dry_run:
            LOGGER.info(f"[DRY RUN] Would mark run {run_id} as error")
        else:
            with repository.engine.begin() as conn:
                result = conn.execute(text(update_query), {"run_id": run_id})
                updated_ids = [row[0] for row in result]
                count += len(updated_ids)
                LOGGER.info(f"Marked {len(updated_ids)} generations as error for run {run_id}")

    return count


def main():
    parser = argparse.ArgumentParser(description="Recover batch_job_id mismatches for OpenAI and/or Anthropic batches")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be updated without making changes"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging"
    )
    parser.add_argument(
        "--mark-unfixable-as-errors",
        action="store_true",
        help="Mark unfixable runs as errors (batches that failed/expired)"
    )
    parser.add_argument(
        "--provider",
        choices=["openai", "anthropic", "both"],
        default="both",
        help="Provider to check (default: both)"
    )
    args = parser.parse_args()

    # Setup logging
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(message)s"
    )

    # Initialize repository
    repository = AuditionRepository()

    # Step 1: Get all stuck generations
    LOGGER.info("Step 1: Fetching stuck generations from database...")
    stuck_runs = get_stuck_generations(repository)

    if not stuck_runs:
        LOGGER.info("No stuck generations found!")
        return

    stuck_run_ids = list(set(run_id for run_id, _, _, _ in stuck_runs))
    LOGGER.info(f"Found {len(stuck_runs)} stuck generations for {len(stuck_run_ids)} runs")

    # Step 2: Get ALL batch_job_ids from recent submissions (last 7 days)
    LOGGER.info("\nStep 2: Fetching all batches from recent submissions...")
    provider_filter = None if args.provider == "both" else args.provider
    all_batches_with_providers = get_all_batches_from_stuck_runs(repository, provider=provider_filter)

    if provider_filter:
        LOGGER.info(f"Found {len(all_batches_with_providers)} {args.provider.upper()} batches from last 7 days")
    else:
        openai_count = sum(1 for _, p in all_batches_with_providers if p == "openai")
        anthropic_count = sum(1 for _, p in all_batches_with_providers if p == "anthropic")
        LOGGER.info(f"Found {len(all_batches_with_providers)} total batches from last 7 days")
        LOGGER.info(f"  OpenAI: {openai_count}, Anthropic: {anthropic_count}")

    # Step 3: Query providers for actual run_ids and batch statuses
    LOGGER.info("\nStep 3: Querying provider APIs for all batches (this may take a few minutes)...")
    batch_to_run, status_groups = build_batch_to_run_mapping(all_batches_with_providers)

    LOGGER.info(f"Retrieved {len(batch_to_run)} completed batch mappings from providers")

    # Step 4: Find correct batch_ids for stuck runs
    LOGGER.info("\nStep 4: Finding correct batch_job_ids for stuck runs...")
    corrections, unfixable_runs = find_correct_batch_ids(stuck_runs, batch_to_run, status_groups)

    # Step 5: Apply corrections
    LOGGER.info("\nStep 5: Applying corrections to database...")
    count = apply_corrections(repository, corrections, dry_run=args.dry_run)

    if args.dry_run:
        LOGGER.info(f"\n[DRY RUN] Would have updated {count} generations for {len(corrections)} runs")
    else:
        LOGGER.info(f"\n✓ Successfully updated {count} generations for {len(corrections)} runs")

    # Step 6: Handle unfixable runs
    if unfixable_runs:
        LOGGER.info(f"\nStep 6: Handling {len(unfixable_runs)} unfixable runs...")
        if args.mark_unfixable_as_errors:
            error_count = mark_unfixable_as_errors(repository, unfixable_runs, dry_run=args.dry_run)
            if args.dry_run:
                LOGGER.info(f"[DRY RUN] Would have marked {error_count} generations as errors")
            else:
                LOGGER.info(f"✓ Marked {error_count} generations as errors")
        else:
            LOGGER.info("To mark these as errors, run with --mark-unfixable-as-errors")

    # Final summary
    LOGGER.info("\n" + "="*60)
    LOGGER.info("SUMMARY:")
    LOGGER.info(f"  Corrected: {len(corrections)} runs ({count} generations)")
    LOGGER.info(f"  Unfixable: {len(unfixable_runs)} runs")
    if not args.dry_run and corrections:
        LOGGER.info("\nNext steps:")
        LOGGER.info("  1. Run the poller to retrieve corrected batches:")
        LOGGER.info("     poetry run python scripts/auto_poll_batches.py")
        if unfixable_runs and not args.mark_unfixable_as_errors:
            LOGGER.info("  2. Mark unfixable runs as errors:")
            LOGGER.info("     poetry run python scripts/recover_batch_mismatches.py --mark-unfixable-as-errors")
    LOGGER.info("="*60)


if __name__ == "__main__":
    main()
