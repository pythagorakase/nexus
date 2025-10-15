#!/usr/bin/env python3
"""Automatically poll and retrieve results from pending batch jobs."""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

from sqlalchemy import text

from nexus.audition import (
    AuditionEngine,
    AuditionRepository,
    AnthropicBatchClient,
    OpenAIBatchClient,
    BatchStatus,
)

LOGGER = logging.getLogger("nexus.apex_audition.auto_poll")
STATUS_PATH = Path("logs/auto_poll_status.json")


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description="Poll provider batches and ingest results.")
    parser.add_argument(
        "--loop",
        action="store_true",
        help="Run continuously, polling every INTERVAL seconds instead of exiting after one pass.",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=60,
        help="Seconds between polls when --loop is enabled (default: 60).",
    )
    return parser.parse_args()


def get_active_batches(repository: AuditionRepository) -> List[Tuple[str, str]]:
    """Query database for active batch jobs.

    Returns list of (batch_job_id, provider) tuples for batches that are:
    - status = 'batch_pending'
    - batch_job_id IS NOT NULL
    - started_at within last 24 hours
    """
    query = """
        SELECT DISTINCT g.batch_job_id, c.provider
        FROM apex_audition.generations g
        JOIN apex_audition.conditions c ON g.condition_id = c.id
        WHERE g.status = 'batch_pending'
          AND g.batch_job_id IS NOT NULL
          AND g.started_at > NOW() - INTERVAL '24 hours'
        ORDER BY g.batch_job_id
    """

    with repository.engine.connect() as conn:
        result = conn.execute(text(query))
        return [(row[0], row[1]) for row in result]


def poll_and_retrieve_batch(
    batch_id: str, provider: str, engine: AuditionEngine, client_cache: Dict[str, Any]
) -> bool:
    """Poll a single batch and retrieve results if completed.

    Returns True if batch is still in progress, False if terminal state reached.
    """
    provider_key = provider.lower()
    if provider_key not in client_cache:
        if provider_key == "anthropic":
            client_cache[provider_key] = AnthropicBatchClient()
        elif provider_key == "openai":
            client_cache[provider_key] = OpenAIBatchClient()
        else:
            LOGGER.warning("Unknown provider '%s' for batch %s, skipping", provider, batch_id)
            return False

    client = client_cache.get(provider_key)
    if client is None:
        LOGGER.warning("No client available for provider '%s'; skipping batch %s", provider, batch_id)
        return False

    try:
        batch_job = client.get_status(batch_id)
    except Exception as e:
        LOGGER.error(f"Failed to get status for batch {batch_id} ({provider}): {e}")
        return False

    LOGGER.info(f"Batch {batch_id} ({provider}): {batch_job.status.value}")

    if batch_job.request_counts:
        LOGGER.info(f"  Request counts: {batch_job.request_counts}")

    # Handle completed batch
    if batch_job.status == BatchStatus.COMPLETED:
        LOGGER.info(f"✓ Batch {batch_id} completed, retrieving results...")
        try:
            results = engine.retrieve_batch_results(batch_id, provider.lower())
            succeeded = sum(1 for r in results if r.status == "completed")
            failed = sum(1 for r in results if r.status == "error")
            LOGGER.info(f"  Retrieved: {succeeded} succeeded, {failed} failed")
            if results:
                LOGGER.info(f"  Run ID: {results[0].run_id}")
        except Exception as e:
            LOGGER.error(f"Failed to retrieve results for batch {batch_id}: {e}")
        return False

    # Handle failed states
    if batch_job.status in [BatchStatus.FAILED, BatchStatus.CANCELLED, BatchStatus.EXPIRED]:
        LOGGER.error(f"✗ Batch {batch_id} ended with status: {batch_job.status.value}")
        return False

    # Still in progress
    return True


def process_batches(
    repository: AuditionRepository, engine: AuditionEngine, client_cache: Dict[str, Any]
) -> Tuple[int, int]:
    """Run a single polling pass and return (still_pending, total_active)."""
    active_batches = get_active_batches(repository)

    if not active_batches:
        LOGGER.debug("No active batches found")
        return 0, 0

    LOGGER.info("Found %d active batch(es)", len(active_batches))

    still_pending = 0
    for batch_id, provider in active_batches:
        if poll_and_retrieve_batch(batch_id, provider, engine, client_cache):
            still_pending += 1

    return still_pending, len(active_batches)


def write_status(still_pending: int, total_active: int, poll_interval: int | None, duration: float) -> None:
    """Persist the latest polling heartbeat for UI and operators."""
    timestamp = datetime.now(timezone.utc)
    payload = {
        "last_poll_at": timestamp.isoformat(),
        "active_batches": total_active,
        "still_pending": still_pending,
        "last_duration_seconds": round(duration, 2),
    }

    if poll_interval:
        payload["polling_interval_seconds"] = poll_interval
        payload["next_poll_at"] = (timestamp + timedelta(seconds=poll_interval)).isoformat()

    try:
        STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
        STATUS_PATH.write_text(json.dumps(payload))
    except OSError as exc:  # pragma: no cover - best effort telemetry
        LOGGER.debug("Failed to write auto-poll status file: %s", exc)


def main() -> None:
    """Main entry point for auto-polling script."""
    args = parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.FileHandler("auto_poll_batches.log"),
            logging.StreamHandler()
        ]
    )

    # Initialize repository and engine
    repository = AuditionRepository()
    engine = AuditionEngine(repository=repository)
    client_cache: Dict[str, Any] = {}
    poll_interval: int | None = None

    def run_once() -> Tuple[int, int, float]:
        """Execute a single polling pass, returning still_pending, total_active, elapsed."""
        pass_start = time.time()
        try:
            still_pending, total_active = process_batches(repository, engine, client_cache)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            LOGGER.exception("Auto-poll run failed: %s", exc)
            still_pending, total_active = 0, 0
        elapsed = time.time() - pass_start
        if total_active:
            LOGGER.info(
                "Polling cycle complete in %.2fs (%d still pending)",
                elapsed,
                still_pending,
            )
        write_status(still_pending, total_active, poll_interval, elapsed)
        return still_pending, total_active, elapsed

    if not args.loop:
        poll_interval = None
        _, total_active, elapsed = run_once()
        if total_active == 0:
            LOGGER.debug("No active batches found (query took %.2fs)", elapsed)
        sys.exit(0)

    poll_interval = max(args.interval, 5)
    LOGGER.info("Starting auto-poll loop with %ds interval", poll_interval)

    try:
        while True:
            _, _, _ = run_once()
            time.sleep(poll_interval)
    except KeyboardInterrupt:
        LOGGER.info("Auto-poll loop interrupted by user")


if __name__ == "__main__":
    main()
