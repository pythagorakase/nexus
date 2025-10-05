#!/usr/bin/env python3
"""Register lane-based conditions from YAML configuration.

Reads the creative_benchmark.yaml config and registers all 15 lane
conditions in the database for the Apex Audition system.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import yaml

from nexus.audition import AuditionEngine, ConditionSpec

LOGGER = logging.getLogger("nexus.apex_audition.register_lanes")


def validate_lane(model_id: str, lane: dict) -> None:
    """Validate lane configuration against rules."""
    params = lane.get("params", {})

    # Rule: GPT-5 and o3 must not have temperature
    if model_id in ("gpt-5", "o3"):
        if "temperature" in params:
            raise ValueError(
                f"Invalid config: {model_id} lane '{lane['lane_id']}' "
                f"must not include 'temperature' parameter"
            )

    # Rule: Anthropic extended thinking requires proper token budget
    if "thinking" in params:
        thinking = params["thinking"]
        if thinking.get("enabled"):
            budget = thinking.get("budget_tokens")
            if budget != 32000:
                raise ValueError(
                    f"Invalid config: Lane '{lane['lane_id']}' has extended thinking "
                    f"but budget_tokens={budget}, expected 32000"
                )

            max_tokens = params.get("max_tokens", 0)
            if max_tokens < 38000:
                LOGGER.warning(
                    "Lane '%s' has extended thinking (32k budget) but max_tokens=%d. "
                    "Should be at least 38000 (6k base + 32k thinking).",
                    lane["lane_id"], max_tokens
                )

    # Rule: Reasoning models should have high output budget
    if model_id in ("gpt-5", "o3"):
        max_output = params.get("max_output_tokens", 0)
        if max_output < 30000:
            LOGGER.warning(
                "Lane '%s' is a reasoning model but max_output_tokens=%d. "
                "Consider increasing to at least 30000.",
                lane["lane_id"], max_output
            )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config/creative_benchmark.yaml"),
        help="Path to YAML configuration file (default: config/creative_benchmark.yaml)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate config and show what would be registered without actually registering"
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

    # Load YAML config
    if not args.config.exists():
        LOGGER.error(f"Config file not found: {args.config}")
        sys.exit(1)

    with open(args.config) as f:
        config = yaml.safe_load(f)

    experiment = config.get("experiment", {})
    models = experiment.get("models", [])

    if not models:
        LOGGER.error("No models defined in config")
        sys.exit(1)

    LOGGER.info(f"Loaded config: {experiment.get('name')}")
    LOGGER.info(f"Description: {experiment.get('description')}")
    LOGGER.info(f"Models defined: {len(models)}")

    # Build condition specs
    conditions = []
    total_lanes = 0

    for model_def in models:
        model_id = model_def["id"]
        provider = model_def["provider"]
        model_name = model_def["model_name"]
        lanes = model_def.get("lanes", [])

        LOGGER.info(f"\n{model_name} ({provider}):")
        LOGGER.info(f"  Lanes: {len(lanes)}")

        for lane in lanes:
            lane_id = lane["lane_id"]
            label = lane.get("label", lane_id)
            description = lane.get("description", "")
            params = lane.get("params", {})

            # Validate lane
            try:
                validate_lane(model_id, lane)
            except ValueError as e:
                LOGGER.error(str(e))
                sys.exit(1)

            # Extract individual parameters
            temperature = params.get("temperature")
            max_output_tokens = params.get("max_output_tokens") or params.get("max_tokens")
            reasoning_effort = params.get("reasoning_effort")

            # For Anthropic, extract thinking config from nested structure
            thinking_enabled = False
            thinking_budget_tokens = None
            if "thinking" in params:
                thinking = params["thinking"]
                thinking_enabled = thinking.get("enabled", False)
                if thinking_enabled:
                    thinking_budget_tokens = thinking.get("budget_tokens")

            condition = ConditionSpec(
                slug=lane_id,
                provider=provider,
                model=model_name,
                temperature=temperature,
                reasoning_effort=reasoning_effort,
                thinking_enabled=thinking_enabled,
                max_output_tokens=max_output_tokens,
                thinking_budget_tokens=thinking_budget_tokens,
                label=label,
                description=description,
                system_prompt=None,  # Using default storyteller prompt from engine
                is_active=True
            )

            conditions.append(condition)
            total_lanes += 1

            LOGGER.info(f"    [{lane_id}] {label}")
            LOGGER.info(f"        Params: {params}")

    LOGGER.info(f"\n{'=' * 60}")
    LOGGER.info(f"Total lanes to register: {total_lanes}")
    LOGGER.info(f"Expected generations: {total_lanes} × {experiment.get('total_prompts', '?')} prompts")

    if args.dry_run:
        LOGGER.info("\n[DRY RUN] Would register these conditions, but --dry-run was specified")
        return

    # Register conditions
    LOGGER.info("\nRegistering conditions in database...")
    engine = AuditionEngine()
    registered = engine.register_conditions(conditions)

    LOGGER.info(f"\n✓ Successfully registered {len(registered)} lane conditions!")
    LOGGER.info("\nTo run a full production batch:")
    LOGGER.info("  python scripts/run_apex_audition_batch.py \\")
    LOGGER.info("    --condition-slug <lane-id> \\")
    LOGGER.info("    --created-by <your-name> \\")
    LOGGER.info("    --notes 'Production run' \\")
    LOGGER.info("    --batch-mode")


if __name__ == "__main__":
    main()
