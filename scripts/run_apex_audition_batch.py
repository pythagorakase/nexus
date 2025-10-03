#!/usr/bin/env python3
"""Run a single Apex audition generation batch."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from nexus.audition import AuditionEngine, ConditionSpec

LOGGER = logging.getLogger("nexus.apex_audition.cli")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--condition-slug", required=True, help="Unique identifier for the model condition")
    parser.add_argument("--provider", choices=["openai", "anthropic"], help="Provider for a new condition")
    parser.add_argument("--model", help="Model name for the condition")
    parser.add_argument("--temperature", type=float, default=0.7, help="Sampling temperature")
    parser.add_argument("--max-tokens", type=int, default=2048, help="Max completion tokens")
    parser.add_argument("--reasoning-effort", choices=["low", "medium", "high"], help="OpenAI reasoning effort")
    parser.add_argument("--top-p", type=float, help="Anthropic / OpenAI nucleus sampling")
    parser.add_argument("--top-k", type=int, help="Anthropic top-k value")
    parser.add_argument("--label", help="Human-readable label for the condition")
    parser.add_argument("--description", help="Optional description for the condition")
    parser.add_argument("--system-prompt", help="System prompt (leave blank to defer)")
    parser.add_argument("--context-dir", type=Path, help="Directory containing audition context packages")
    parser.add_argument("--ingest", action="store_true", help="Re-ingest context packages before running")
    parser.add_argument("--limit", type=int, help="Limit number of prompts processed")
    parser.add_argument("--replicates", type=int, default=1, help="Number of completions per prompt")
    parser.add_argument("--dry-run", action="store_true", help="Skip API calls and log requests only")
    parser.add_argument("--created-by", help="Audit field for run creator")
    parser.add_argument("--notes", help="Optional notes stored with the batch")
    parser.add_argument("--register-only", action="store_true", help="Register the condition and exit")
    parser.add_argument("--no-cache", action="store_true", help="Disable prompt caching")
    parser.add_argument("--no-rate-limiting", action="store_true", help="Disable rate limit enforcement")
    parser.add_argument("--max-retries", type=int, default=3, help="Max retry attempts for failed requests (default 3)")
    parser.add_argument("--batch-mode", action="store_true", help="Use Batch API (async, 50%% discount, 24hr processing)")
    parser.add_argument("--verify-first", action="store_true", help="Send single test request before full batch")
    parser.add_argument("--log-level", default="INFO", help="Python logging level (default INFO)")
    return parser.parse_args()


def maybe_register_condition(engine: AuditionEngine, args: argparse.Namespace) -> None:
    repo = engine.repository
    existing = repo.get_condition_by_slug(args.condition_slug)
    if existing:
        LOGGER.info("Condition %s already registered (id=%s)", existing.slug, existing.id)
        return
    if not args.provider or not args.model:
        raise SystemExit("Provider and model are required to register a new condition")

    parameters = {
        "temperature": args.temperature,
        "max_output_tokens": args.max_tokens,
    }
    if args.reasoning_effort:
        parameters["reasoning_effort"] = args.reasoning_effort
    if args.top_p is not None:
        parameters["top_p"] = args.top_p
    if args.top_k is not None:
        parameters["top_k"] = args.top_k

    spec = ConditionSpec(
        slug=args.condition_slug,
        provider=args.provider,
        model=args.model,
        parameters=parameters,
        label=args.label,
        description=args.description,
        system_prompt=args.system_prompt or None,
    )
    stored = engine.register_conditions([spec])[0]
    LOGGER.info("Registered condition %s (id=%s)", stored.slug, stored.id)


def main() -> None:
    args = parse_args()
    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO), format="%(levelname)s %(message)s")

    engine = AuditionEngine(context_dir=args.context_dir)

    if args.ingest:
        engine.ingest_context_packages(directory=args.context_dir)
    elif not engine.repository.list_prompts():
        LOGGER.info("No prompts found in repository; ingesting from %s", args.context_dir or engine.context_dir)
        engine.ingest_context_packages(directory=args.context_dir)

    maybe_register_condition(engine, args)

    if args.register_only:
        LOGGER.info("Condition registration complete; exiting")
        return

    # Verification mode: send single test request
    if args.verify_first and not args.dry_run:
        LOGGER.info("=== VERIFICATION MODE ===")
        LOGGER.info("Sending single test request to verify setup...")

        verify_run = engine.run_generation_batch(
            condition_slug=args.condition_slug,
            limit=1,
            replicate_count=1,
            dry_run=False,
            enable_cache=not args.no_cache,
            use_rate_limiting=not args.no_rate_limiting,
            max_retries=args.max_retries,
            created_by=args.created_by,
            notes=f"[VERIFICATION] {args.notes or ''}",
        )

        # Check if verification succeeded
        results = engine.repository.list_generations_for_run(verify_run.run_id)
        if not results:
            LOGGER.error("Verification failed: no results recorded")
            return

        result = results[0]
        if result.status != "completed":
            LOGGER.error(f"Verification failed: status={result.status}, error={result.error_message}")
            return

        LOGGER.info("✓ Verification successful!")
        LOGGER.info(f"  Input tokens: {result.input_tokens}")
        LOGGER.info(f"  Output tokens: {result.output_tokens}")
        LOGGER.info(f"  Cache hit: {result.cache_hit}")

        proceed = input("\nVerification passed. Proceed with full batch? [y/N]: ")
        if proceed.lower() != 'y':
            LOGGER.info("Batch cancelled by user")
            return

    # Batch mode: submit async batch job
    if args.batch_mode:
        if args.dry_run:
            LOGGER.error("--batch-mode cannot be used with --dry-run")
            return
        if args.verify_first:
            LOGGER.error("--batch-mode cannot be used with --verify-first")
            return

        condition = engine.repository.get_condition_by_slug(args.condition_slug)
        if not condition:
            LOGGER.error(f"Condition {args.condition_slug} not found")
            return

        run, batch_id = engine.submit_batch_generation(
            condition_slug=args.condition_slug,
            limit=args.limit,
            replicate_count=args.replicates,
            enable_cache=not args.no_cache,
        )

        LOGGER.info("=== BATCH SUBMITTED ===")
        LOGGER.info(f"Run ID: {run.run_id}")
        LOGGER.info(f"Batch ID: {batch_id}")
        LOGGER.info(f"Provider: {condition.provider}")
        LOGGER.info(f"Total requests: {len(engine.repository.list_generations_for_run(run.run_id))}")
        LOGGER.info("")
        LOGGER.info("To poll batch status and retrieve results:")
        LOGGER.info(f"  python scripts/poll_batch.py --batch-id {batch_id} --provider {condition.provider} --auto-retrieve")
        return

    # Run full batch (synchronous)
    run = engine.run_generation_batch(
        condition_slug=args.condition_slug,
        limit=args.limit,
        replicate_count=args.replicates,
        dry_run=args.dry_run,
        enable_cache=not args.no_cache,
        use_rate_limiting=not args.no_rate_limiting,
        max_retries=args.max_retries,
        created_by=args.created_by,
        notes=args.notes,
    )
    LOGGER.info("Run complete: %s", run.run_id)

    # Summary statistics
    if not args.dry_run:
        results = engine.repository.list_generations_for_run(run.run_id)
        cache_hits = sum(1 for r in results if r.cache_hit)
        total_input = sum(r.input_tokens for r in results)
        total_output = sum(r.output_tokens for r in results)

        LOGGER.info("=== BATCH SUMMARY ===")
        LOGGER.info(f"Total generations: {len(results)}")
        LOGGER.info(f"Cache hits: {cache_hits}/{len(results)} ({100 * cache_hits / len(results):.1f}%)")
        LOGGER.info(f"Total input tokens: {total_input:,}")
        LOGGER.info(f"Total output tokens: {total_output:,}")


if __name__ == "__main__":
    main()
