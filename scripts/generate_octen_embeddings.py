#!/usr/bin/env python3
"""Generate Octen embeddings using the existing regeneration pipeline.

This wrapper standardizes model names and options for issue #175 so Octen-4B
and Octen-8B can be generated with one command.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import List

OCTEN_MODELS = ["Octen-Embedding-4B", "Octen-Embedding-8B"]


def build_command(
    model_name: str,
    regenerate_script: Path,
    batch_size: int,
    db_url: str | None,
    create_indexes: bool,
    dry_run: bool,
) -> List[str]:
    """Build the subprocess command for one model regeneration run."""
    command = [
        sys.executable,
        str(regenerate_script),
        "--model",
        model_name,
        "--batch-size",
        str(batch_size),
    ]

    if db_url:
        command.extend(["--db-url", db_url])
    if create_indexes:
        command.append("--create-indexes")
    if dry_run:
        command.append("--dry-run")

    return command


def run_model(command: List[str]) -> int:
    """Run a single model generation command and return the exit code."""
    process = subprocess.run(command, check=False)
    return process.returncode


def main() -> int:
    """Parse CLI arguments and dispatch Octen embedding generation."""
    parser = argparse.ArgumentParser(description="Generate Octen embeddings for MEMNON")
    parser.add_argument(
        "--model",
        default="all",
        choices=["all", *OCTEN_MODELS],
        help="Which Octen model to generate",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=8,
        help="Chunk batch size passed through to scripts/regenerate_embeddings.py",
    )
    parser.add_argument(
        "--db-url", type=str, default=None, help="PostgreSQL connection URL"
    )
    parser.add_argument(
        "--create-indexes",
        action="store_true",
        help="Create vector indexes after generation",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Pass through dry-run mode"
    )
    parser.add_argument(
        "--parallel",
        action="store_true",
        help="Run both Octen models in parallel (only valid with --model all)",
    )

    args = parser.parse_args()

    if args.batch_size <= 0:
        raise ValueError("--batch-size must be greater than 0")

    script_path = Path(__file__).resolve().parent / "regenerate_embeddings.py"
    if not script_path.exists():
        raise FileNotFoundError(f"Missing script: {script_path}")

    if args.parallel and args.model != "all":
        raise ValueError("--parallel is only valid when --model all")

    target_models = OCTEN_MODELS if args.model == "all" else [args.model]

    if args.parallel:
        processes = []
        for model_name in target_models:
            command = build_command(
                model_name=model_name,
                regenerate_script=script_path,
                batch_size=args.batch_size,
                db_url=args.db_url,
                create_indexes=args.create_indexes,
                dry_run=args.dry_run,
            )
            processes.append(subprocess.Popen(command))

        exit_codes = [process.wait() for process in processes]
        if any(code != 0 for code in exit_codes):
            return 1
        return 0

    for model_name in target_models:
        command = build_command(
            model_name=model_name,
            regenerate_script=script_path,
            batch_size=args.batch_size,
            db_url=args.db_url,
            create_indexes=args.create_indexes,
            dry_run=args.dry_run,
        )
        exit_code = run_model(command)
        if exit_code != 0:
            return exit_code

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
