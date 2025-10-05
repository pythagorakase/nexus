#!/usr/bin/env python3
"""Run all Apex audition lanes sequentially, chunk by chunk.

This script iterates over the trimmed context packages in ascending
chunk order and fires each lane in a deterministic sequence. OpenAI
lanes run with prompt caching disabled (since cross-parameter cache hits
aren't working yet), while Anthropic lanes keep caching enabled so each
chunk warms once before the extended-thinking variants follow.

Existing completed generations are skipped to avoid double-spend if the
script is resumed. Use --dry-run to preview the execution plan.
"""

from __future__ import annotations

import argparse
import logging
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

from sqlalchemy import text

from nexus.audition import AuditionEngine
from nexus.audition.models import ConditionSpec, PromptSnapshot
from nexus.audition.repository import AuditionRepository
from scripts.api_openai import OpenAIProvider
from scripts.api_anthropic import AnthropicProvider
from nexus.audition.batch_clients import BatchStatus


LOGGER = logging.getLogger("nexus.apex_audition.run_full_sequential")

# Global lock for synchronized output
_output_lock = threading.Lock()


# Lane ordering chosen to favour cache reuse for Anthropic.
OPENAI_LANES = [
    "gpt5.reason-min",
    "gpt5.reason-med",
    "gpt5.reason-high",
    "o3.reason-low",
    "o3.reason-med",
    "o3.reason-high",
    "4o.t0-7",
    "4o.t1-0",
    "4o.t1-3",
]

ANTHROPIC_LANES = [
    "sonnet.t0-7.std",
    "sonnet.t1-0.std",
    "sonnet.t1-0.ext",
    "opus.t0-7.std",
    "opus.t1-0.std",
    "opus.t1-0.ext",
]

TEST_CHUNK_IDS = {4242}  # skip pytest harness fixtures


@dataclass
class LaneGroup:
    slug: str
    provider: str
    enable_cache: bool


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the planned execution without calling the APIs",
    )
    parser.add_argument(
        "--created-by",
        default="sequential-runner",
        help="Audit field recorded with each run",
    )
    parser.add_argument(
        "--notes",
        default="Deterministic sequential rollout",
        help="Notes to attach to each run",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="Logging level (default: INFO)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Limit number of prompts to process",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=7,
        help="Maximum number of concurrent workers (default: 7)",
    )
    return parser.parse_args()


def _fetch_secret(command: List[str], label: str) -> Optional[str]:
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=True)
    except FileNotFoundError:
        LOGGER.warning("1Password CLI not found; unable to prefetch %s", label)
        return None
    except subprocess.CalledProcessError as exc:
        LOGGER.warning("Failed to prefetch %s (exit %s). Will fall back to provider lookup.", label, exc.returncode)
        return None

    value = result.stdout.strip()
    if not value:
        LOGGER.warning("Fetched empty value for %s; provider will attempt runtime retrieval", label)
        return None
    return value


def patch_provider_keys() -> None:
    openai_key = _fetch_secret(
        [
            "op",
            "item",
            "get",
            "tyrupcepa4wluec7sou4e7mkza",
            "--fields",
            "api key",
            "--reveal",
        ],
        "OpenAI API key",
    )
    if openai_key:
        LOGGER.info("Prefetched OpenAI API key via 1Password")

        def _cached_openai_key(self) -> str:  # type: ignore[override]
            return openai_key

        OpenAIProvider._get_api_key = _cached_openai_key  # type: ignore[attr-defined]

    anthropic_key = _fetch_secret(
        ["op", "read", "op://API/Anthropic/api key"],
        "Anthropic API key",
    )
    if anthropic_key:
        LOGGER.info("Prefetched Anthropic API key via 1Password")

        def _cached_anthropic_key(self) -> str:  # type: ignore[override]
            return anthropic_key

        AnthropicProvider._get_api_key = _cached_anthropic_key  # type: ignore[attr-defined]


def load_conditions(repo: AuditionRepository, slugs: Iterable[str]) -> List[ConditionSpec]:
    conditions: List[ConditionSpec] = []
    for slug in slugs:
        condition = repo.get_condition_by_slug(slug)
        if not condition or condition.id is None:
            raise ValueError(f"Unknown or unpersisted condition slug: {slug}")
        conditions.append(condition)
    return conditions


def compute_summary(
    repo: AuditionRepository,
    prompts: List[PromptSnapshot],
    conditions: List[ConditionSpec],
) -> Dict[str, int]:
    prompt_ids = [p.id for p in prompts if p.id is not None]
    condition_ids = [c.id for c in conditions if c.id is not None]

    combos: Dict[Tuple[int, int], Dict[str, Optional[str]]] = {}
    for cond_id in condition_ids:
        for prompt_id in prompt_ids:
            combos[(cond_id, prompt_id)] = {
                "seen": False,
                "has_completed": False,
                "last_status": None,
            }

    if combos:
        cond_csv = ",".join(str(i) for i in condition_ids)
        prompt_csv = ",".join(str(i) for i in prompt_ids)
        query = text(
            f"""
            SELECT condition_id, prompt_id, status
            FROM apex_audition.generations
            WHERE condition_id IN ({cond_csv})
              AND prompt_id IN ({prompt_csv})
            ORDER BY created_at
            """
        )
        with repo.engine.connect() as connection:
            rows = connection.execute(query).fetchall()

        for condition_id, prompt_id, status in rows:
            key = (condition_id, prompt_id)
            if key not in combos:
                continue
            entry = combos[key]
            entry["seen"] = True
            entry["last_status"] = status
            if status == "completed":
                entry["has_completed"] = True

    summary = {
        "total": len(combos),
        "unsent": 0,
        "completed": 0,
        "processing": 0,
        "failed": 0,
    }

    for entry in combos.values():
        if not entry["seen"]:
            summary["unsent"] += 1
            continue
        if entry["has_completed"]:
            summary["completed"] += 1
            continue

        last_status = (entry["last_status"] or "").lower()
        if last_status in {"pending", "in_progress", "queued", "submitted"}:
            summary["processing"] += 1
        elif last_status == "error":
            summary["failed"] += 1
        else:
            summary["processing"] += 1

    summary["sent"] = summary["total"] - summary["unsent"]
    return summary


def display_summary(summary: Dict[str, int]) -> None:
    with _output_lock:
        remaining = summary['total'] - summary['completed'] - summary['failed']
        line = (
            f"Total: {summary['total']} | "
            f"Remaining: {remaining} | "
            f"Completed: {summary['completed']} | "
            f"Failed: {summary['failed']}"
        )
        sys.stdout.write("\r" + line.ljust(120))
        sys.stdout.flush()


def has_completed_generation(repo: AuditionRepository, condition_id: int, prompt_id: int) -> bool:
    query = text(
        """
        SELECT 1
        FROM apex_audition.generations
        WHERE condition_id = :condition_id
          AND prompt_id = :prompt_id
          AND replicate_index = 0
          AND status = 'completed'
        LIMIT 1
        """
    )
    with repo.engine.connect() as connection:
        row = connection.execute(query, {"condition_id": condition_id, "prompt_id": prompt_id}).scalar()
    return row is not None


def run_lane(
    engine: AuditionEngine,
    condition: ConditionSpec,
    prompt: PromptSnapshot,
    *,
    enable_cache: bool,
    dry_run: bool,
    created_by: str,
    notes: str,
    repo: AuditionRepository,
    prompts: List[PromptSnapshot],
    all_conditions: List[ConditionSpec],
) -> None:
    if dry_run:
        with _output_lock:
            LOGGER.info(
                "[DRY-RUN] %s on chunk %s (prompt %s) cache=%s",
                condition.slug,
                prompt.chunk_id,
                prompt.id,
                enable_cache,
            )
        return

    run = engine.run_generation_batch(
        condition_slug=condition.slug,
        prompt_ids=[prompt.id],
        replicate_count=1,
        dry_run=False,
        enable_cache=enable_cache,
        use_rate_limiting=True,
        max_retries=3,
        created_by=created_by,
        notes=notes,
    )
    with _output_lock:
        LOGGER.info(
            "Completed %s chunk %s -> run %s",
            condition.slug,
            prompt.chunk_id,
            run.run_id,
        )


def poll_pending_batches(
    engine: AuditionEngine,
    pending_batches: List[Dict[str, str]],
    repo: AuditionRepository,
    prompts: List[PromptSnapshot],
    all_conditions: List[ConditionSpec],
) -> None:
    if not pending_batches:
        return

    remaining: List[Dict[str, str]] = []
    for entry in pending_batches:
        batch_id = entry["batch_id"]
        provider = entry["provider"]
        condition = entry["condition"]

        try:
            if provider == "openai":
                client = engine._get_openai_batch_client()
            else:
                client = engine._get_anthropic_batch_client()

            job = client.get_status(batch_id)

            if job.status == BatchStatus.COMPLETED:
                LOGGER.info("Batch %s (%s/%s) completed; retrieving results", batch_id, provider, condition)
                results = engine.retrieve_batch_results(batch_id, provider)
                LOGGER.info("Processed %s results from batch %s", len(results), batch_id)
                display_summary(compute_summary(repo, prompts, all_conditions))
                continue

            if job.status in {BatchStatus.FAILED, BatchStatus.CANCELLED, BatchStatus.EXPIRED}:
                LOGGER.error(
                    "Batch %s (%s/%s) ended with status %s; inspect manually",
                    batch_id,
                    provider,
                    condition,
                    job.status.value,
                )
                display_summary(compute_summary(repo, prompts, all_conditions))
                continue

            remaining.append(entry)
        except Exception as exc:  # pragma: no cover - defensive
            LOGGER.warning("Failed to poll batch %s (%s): %s", batch_id, provider, exc)
            remaining.append(entry)

    pending_batches[:] = remaining


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(message)s",
    )

    patch_provider_keys()

    engine = AuditionEngine()
    repo = engine.repository

    openai_conditions = load_conditions(repo, OPENAI_LANES)
    anthropic_conditions = load_conditions(repo, ANTHROPIC_LANES)
    all_conditions = openai_conditions + anthropic_conditions

    prompts = [
        prompt
        for prompt in sorted(repo.list_prompts(), key=lambda p: (p.chunk_id, p.id))
        if prompt.id is not None and prompt.chunk_id not in TEST_CHUNK_IDS
    ]

    if args.limit is not None and args.limit > 0:
        prompts = prompts[:args.limit]
        LOGGER.info("Limiting to first %s prompts", args.limit)

    LOGGER.info(
        "Starting rollout across %s prompts (%s OpenAI lanes, %s Anthropic lanes)",
        len(prompts),
        len(openai_conditions),
        len(anthropic_conditions),
    )

    display_summary(compute_summary(repo, prompts, all_conditions))

    LOGGER.info("=== Processing all prompts across all lanes (max %d concurrent) ===", args.max_workers)

    # Build list of tasks to execute
    tasks = []
    for prompt in prompts:
        for condition in all_conditions:
            if has_completed_generation(repo, condition.id, prompt.id):
                continue
            tasks.append((condition, prompt))

    LOGGER.info("Total tasks to execute: %s", len(tasks))

    # Execute tasks with configured number of workers
    completed_count = 0
    with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
        futures = []
        for condition, prompt in tasks:
            # Disable caching for all providers since parallel execution prevents cache reuse
            # (Anthropic charges +25% to write cache, OpenAI provides no cross-parameter cache hits)
            enable_cache = False

            future = executor.submit(
                run_lane,
                engine,
                condition,
                prompt,
                enable_cache=enable_cache,
                dry_run=args.dry_run,
                created_by=args.created_by,
                notes=args.notes,
                repo=repo,
                prompts=prompts,
                all_conditions=all_conditions,
            )
            futures.append(future)

        # Wait for all to complete and show progress
        for future in as_completed(futures):
            try:
                future.result()
                completed_count += 1
                # Show progress after each completion
                summary = compute_summary(repo, prompts, all_conditions)
                display_summary(summary)
            except Exception as exc:
                LOGGER.error("Task generated exception: %s", exc)
                completed_count += 1

    LOGGER.info("Sequential rollout complete")
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
