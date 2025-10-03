#!/usr/bin/env python3
"""Poll and retrieve results from a batch job."""

import argparse
import logging
import time
from pathlib import Path

from nexus.audition import (
    AuditionEngine,
    AnthropicBatchClient,
    OpenAIBatchClient,
    BatchStatus,
)

LOGGER = logging.getLogger("nexus.apex_audition.poll")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-id", required=True, help="Batch job ID")
    parser.add_argument(
        "--provider",
        required=True,
        choices=["openai", "anthropic"],
        help="Provider that created the batch"
    )
    parser.add_argument(
        "--poll-interval",
        type=int,
        default=60,
        help="Polling interval in seconds (default: 60)"
    )
    parser.add_argument(
        "--max-wait",
        type=int,
        default=3600,
        help="Maximum time to wait in seconds (default: 3600 = 1 hour)"
    )
    parser.add_argument(
        "--auto-retrieve",
        action="store_true",
        help="Automatically retrieve results when batch completes"
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="Python logging level (default INFO)"
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(levelname)s %(message)s"
    )

    # Get batch client
    if args.provider == "anthropic":
        client = AnthropicBatchClient()
    else:
        client = OpenAIBatchClient()

    LOGGER.info(f"Polling batch {args.batch_id} on {args.provider}")

    start_time = time.time()
    while True:
        # Get current status
        batch_job = client.get_status(args.batch_id)

        elapsed = int(time.time() - start_time)
        LOGGER.info(f"Status: {batch_job.status.value} (elapsed: {elapsed}s)")

        if batch_job.request_counts:
            LOGGER.info(f"  Request counts: {batch_job.request_counts}")

        # Check if completed
        if batch_job.status == BatchStatus.COMPLETED:
            LOGGER.info("✓ Batch completed successfully!")

            if args.auto_retrieve:
                LOGGER.info("Retrieving results...")
                engine = AuditionEngine()
                results = engine.retrieve_batch_results(args.batch_id, args.provider)

                succeeded = sum(1 for r in results if r.status == "completed")
                failed = sum(1 for r in results if r.status == "error")

                LOGGER.info(f"Results retrieved: {succeeded} succeeded, {failed} failed")
                LOGGER.info(f"Run ID: {results[0].run_id if results else 'N/A'}")

            break

        if batch_job.status in [BatchStatus.FAILED, BatchStatus.CANCELLED, BatchStatus.EXPIRED]:
            LOGGER.error(f"Batch ended with status: {batch_job.status.value}")
            break

        # Check timeout
        if elapsed >= args.max_wait:
            LOGGER.warning(f"Max wait time ({args.max_wait}s) exceeded. Batch still {batch_job.status.value}")
            break

        # Wait before next poll
        LOGGER.info(f"Waiting {args.poll_interval}s before next poll...")
        time.sleep(args.poll_interval)


if __name__ == "__main__":
    main()
