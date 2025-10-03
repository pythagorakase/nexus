#!/usr/bin/env python3
"""Submit a multi-lane batch generation job.

Combines multiple lanes (conditions) into a single batch submission,
enabling cross-lane caching and simplified batch management.

All lanes must use the same provider (OpenAI or Anthropic).
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from nexus.audition import AuditionEngine

LOGGER = logging.getLogger("nexus.apex_audition.multi_lane_batch")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--lanes",
        required=True,
        help="Comma-separated list of lane IDs (e.g., 'gpt5.reason-min,o3.reason-low,4o.t0-8')"
    )
    parser.add_argument(
        "--context-dir",
        type=Path,
        help="Directory containing audition context packages"
    )
    parser.add_argument(
        "--ingest",
        action="store_true",
        help="Re-ingest context packages before running"
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Limit number of prompts processed"
    )
    parser.add_argument(
        "--replicates",
        type=int,
        default=1,
        help="Number of completions per prompt per lane (default: 1)"
    )
    parser.add_argument(
        "--created-by",
        help="Audit field for run creator"
    )
    parser.add_argument(
        "--notes",
        help="Optional notes stored with the batch"
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Disable prompt caching"
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="Python logging level (default: INFO)"
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(levelname)s %(message)s"
    )

    engine = AuditionEngine(context_dir=args.context_dir)

    if args.ingest:
        engine.ingest_context_packages(directory=args.context_dir)
    elif not engine.repository.list_prompts():
        LOGGER.info("No prompts found in repository; ingesting from %s", args.context_dir or engine.context_dir)
        engine.ingest_context_packages(directory=args.context_dir)

    # Parse lane IDs
    lane_ids = [lane.strip() for lane in args.lanes.split(',')]

    LOGGER.info(f"Submitting multi-lane batch with {len(lane_ids)} lanes:")
    for lane_id in lane_ids:
        LOGGER.info(f"  - {lane_id}")

    # Submit multi-lane batch
    run, batch_id = engine.submit_multi_lane_batch(
        condition_slugs=lane_ids,
        limit=args.limit,
        replicate_count=args.replicates,
        enable_cache=not args.no_cache,
        created_by=args.created_by,
        notes=args.notes,
    )

    # Get provider from first lane
    first_condition = engine.repository.get_condition_by_slug(lane_ids[0])
    provider = first_condition.provider if first_condition else "unknown"

    LOGGER.info("=== MULTI-LANE BATCH SUBMITTED ===")
    LOGGER.info(f"Run ID: {run.run_id}")
    LOGGER.info(f"Batch ID: {batch_id}")
    LOGGER.info(f"Provider: {provider}")
    LOGGER.info(f"Lanes: {len(lane_ids)}")
    LOGGER.info(f"Prompts: {args.limit if args.limit else 'all'}")
    LOGGER.info(f"Replicates per lane: {args.replicates}")
    LOGGER.info("")
    LOGGER.info("To poll batch status and retrieve results:")
    LOGGER.info(f"  python scripts/poll_batch.py --batch-id {batch_id} --provider {provider} --auto-retrieve")


if __name__ == "__main__":
    main()
