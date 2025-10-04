#!/usr/bin/env python3
"""Regenerate generations that have null/empty content.

This script finds all completed generations where the content field is null
or empty (despite successful API calls that returned metadata), and regenerates
them in parallel without caching to get fast results.

Uses ThreadPoolExecutor for parallel processing (default 50 workers) to take
advantage of high API rate limits. Progress is displayed with a live countdown,
and any persistent failures are logged to temp/regeneration_errors.log.
"""

from __future__ import annotations

import argparse
import logging
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

from sqlalchemy import text

from nexus.audition import AuditionEngine
from nexus.audition.repository import AuditionRepository
from scripts.api_anthropic import AnthropicProvider
from scripts.api_openai import OpenAIProvider

LOGGER = logging.getLogger("nexus.apex_audition.regenerate_missing_content")

# Error log file
ERROR_LOG = Path(__file__).parent.parent / "temp" / "regeneration_errors.log"


@dataclass
class MissingGeneration:
    """A generation that needs to be regenerated."""
    id: int
    lane_id: str
    condition_id: int
    prompt_id: int
    retry_count: int = 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the generations to regenerate without calling APIs",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=50,
        help="Maximum parallel workers (default: 50)",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="Logging level (default: INFO)",
    )
    return parser.parse_args()


def find_missing_generations(repo: AuditionRepository) -> List[MissingGeneration]:
    """Query database for generations with null/empty content."""
    query = text("""
        SELECT id, lane_id, condition_id, prompt_id
        FROM apex_audition.generations
        WHERE status = 'completed'
          AND (response_payload->>'content' IS NULL
               OR LENGTH(response_payload->>'content') = 0)
        ORDER BY id
    """)

    with repo.engine.connect() as connection:
        rows = connection.execute(query).fetchall()

    return [
        MissingGeneration(
            id=row[0],
            lane_id=row[1],
            condition_id=row[2],
            prompt_id=row[3]
        )
        for row in rows
    ]


def update_generation(
    repo: AuditionRepository,
    generation_id: int,
    response_payload: Dict,
    input_tokens: int,
    output_tokens: int,
    cache_hit: bool,
) -> None:
    """Update an existing generation row with new content."""
    query = text("""
        UPDATE apex_audition.generations
        SET response_payload = :response_payload,
            input_tokens = :input_tokens,
            output_tokens = :output_tokens,
            cache_hit = :cache_hit,
            completed_at = :completed_at
        WHERE id = :id
    """)

    with repo.engine.begin() as connection:
        connection.execute(
            query,
            {
                "id": generation_id,
                "response_payload": response_payload,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cache_hit": cache_hit,
                "completed_at": datetime.now(timezone.utc),
            }
        )


def log_error(generation: MissingGeneration, error: str) -> None:
    """Log a persistent error to the error log file."""
    ERROR_LOG.parent.mkdir(parents=True, exist_ok=True)

    with open(ERROR_LOG, "a") as f:
        f.write(f"{generation.id},{generation.lane_id},{generation.prompt_id},{error}\n")

    LOGGER.error(
        "Generation %s (lane=%s, prompt=%s) failed after retries: %s",
        generation.id,
        generation.lane_id,
        generation.prompt_id,
        error,
    )


def display_progress(total: int, remaining: int, completed: int, failed: int) -> None:
    """Display live progress with countdown."""
    line = f"Total: {total} | Remaining: {remaining} | Completed: {completed} | Failed: {failed}"
    sys.stdout.write("\r" + line.ljust(100))
    sys.stdout.flush()


def regenerate_generation(
    engine: AuditionEngine,
    repo: AuditionRepository,
    generation: MissingGeneration,
    dry_run: bool,
) -> bool:
    """
    Regenerate a single generation synchronously.

    Returns True if successful, False if failed.
    """
    if dry_run:
        LOGGER.info(
            "[DRY-RUN] Would regenerate generation %s (lane=%s, prompt=%s)",
            generation.id,
            generation.lane_id,
            generation.prompt_id,
        )
        return True

    try:
        # Run synchronous generation with caching disabled
        # lane_id is the condition slug
        run = engine.run_generation_batch(
            condition_slug=generation.lane_id,
            prompt_ids=[generation.prompt_id],
            replicate_count=1,
            dry_run=False,
            enable_cache=False,  # No caching for fast results
            use_rate_limiting=True,
            max_retries=2,
            created_by="regeneration-script",
            notes=f"Regenerating generation {generation.id} (missing content)",
        )

        # The generation was created with a new ID, but we want to update the old one
        # Query for the newly created generation to extract its response
        new_gen_query = text("""
            SELECT response_payload, input_tokens, output_tokens, cache_hit
            FROM apex_audition.generations
            WHERE run_id = :run_id
              AND condition_id = :condition_id
              AND prompt_id = :prompt_id
              AND replicate_index = 0
            LIMIT 1
        """)

        with repo.engine.connect() as connection:
            result = connection.execute(
                new_gen_query,
                {
                    "run_id": str(run.run_id),
                    "condition_id": generation.condition_id,
                    "prompt_id": generation.prompt_id,
                }
            ).fetchone()

        if not result:
            raise ValueError(f"Could not find newly created generation for run {run.run_id}")

        # Update the original generation with the new content
        update_generation(
            repo,
            generation.id,
            response_payload=result[0],
            input_tokens=result[1],
            output_tokens=result[2],
            cache_hit=result[3],
        )

        # Delete the duplicate generation
        delete_query = text("""
            DELETE FROM apex_audition.generations
            WHERE run_id = :run_id
              AND condition_id = :condition_id
              AND prompt_id = :prompt_id
              AND replicate_index = 0
              AND id != :original_id
        """)

        with repo.engine.begin() as connection:
            connection.execute(
                delete_query,
                {
                    "run_id": str(run.run_id),
                    "condition_id": generation.condition_id,
                    "prompt_id": generation.prompt_id,
                    "original_id": generation.id,
                }
            )

        LOGGER.info(
            "Regenerated generation %s (lane=%s, prompt=%s)",
            generation.id,
            generation.lane_id,
            generation.prompt_id,
        )
        return True

    except Exception as e:
        LOGGER.warning(
            "Failed to regenerate generation %s (attempt %s): %s",
            generation.id,
            generation.retry_count + 1,
            str(e),
        )
        return False


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(message)s",
    )

    engine = AuditionEngine()
    repo = engine.repository

    # Find all generations with missing content
    missing = find_missing_generations(repo)

    if not missing:
        LOGGER.info("No generations with missing content found!")
        return

    LOGGER.info(
        "Found %s generation(s) with missing content%s",
        len(missing),
        " (DRY RUN)" if args.dry_run else "",
    )

    if args.dry_run:
        for gen in missing:
            LOGGER.info(
                "  - Generation %s: lane=%s, prompt=%s",
                gen.id,
                gen.lane_id,
                gen.prompt_id,
            )
        return

    # Initialize progress tracking (thread-safe)
    total = len(missing)
    completed = 0
    failed = 0
    remaining = total
    progress_lock = threading.Lock()

    # Clear error log
    if ERROR_LOG.exists():
        ERROR_LOG.unlink()

    display_progress(total, remaining, completed, failed)

    LOGGER.info("Processing with %s parallel workers...", args.max_workers)

    # Process generations in parallel
    def process_with_retry(generation: MissingGeneration) -> bool:
        """Process a generation with retry logic."""
        nonlocal completed, failed, remaining

        success = False
        for attempt in range(2):
            generation.retry_count = attempt
            success = regenerate_generation(engine, repo, generation, args.dry_run)
            if success:
                break

        # Update progress (thread-safe)
        with progress_lock:
            if success:
                completed += 1
            else:
                failed += 1
                log_error(generation, "Failed after 2 attempts")
            remaining -= 1
            display_progress(total, remaining, completed, failed)

        return success

    # Use ThreadPoolExecutor for parallel processing
    with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
        # Submit all tasks
        futures = {executor.submit(process_with_retry, gen): gen for gen in missing}

        # Wait for completion (progress is updated in process_with_retry)
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as e:
                gen = futures[future]
                LOGGER.error("Unexpected error processing generation %s: %s", gen.id, e)

    sys.stdout.write("\n")
    LOGGER.info("Regeneration complete!")
    LOGGER.info("  Total: %s", total)
    LOGGER.info("  Completed: %s", completed)
    LOGGER.info("  Failed: %s", failed)

    if failed > 0:
        LOGGER.info("  Errors logged to: %s", ERROR_LOG)


if __name__ == "__main__":
    main()
