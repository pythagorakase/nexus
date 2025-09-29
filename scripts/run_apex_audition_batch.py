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

    run = engine.run_generation_batch(
        condition_slug=args.condition_slug,
        limit=args.limit,
        replicate_count=args.replicates,
        dry_run=args.dry_run,
        created_by=args.created_by,
        notes=args.notes,
    )
    LOGGER.info("Run complete: %s", run.run_id)


if __name__ == "__main__":
    main()
