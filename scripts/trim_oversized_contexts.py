#!/usr/bin/env python3
"""
Trim oversized context packages by removing oldest chunks from warm slice.

Target: Get context packages under 110k tokens to leave headroom for API overhead.
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any, Dict, List

from sqlalchemy import create_engine, text

LOGGER = logging.getLogger(__name__)

# Chunks that need trimming based on error log analysis
OVERSIZED_CHUNKS = [615, 620, 754, 898]
TARGET_TOKENS = 110_000  # Target to stay safely under 120k after API overhead
MIN_WARM_CHUNKS = 3  # Keep at least this many chunks for continuity


def load_context_package(chunk_id: int, context_dir: Path) -> tuple[Path, Dict[str, Any]]:
    """Load the most recent context package JSON for a chunk."""
    # Find the most recent file for this chunk
    matching_files = sorted(context_dir.glob(f"chunk_{chunk_id}_*.json"))
    if not matching_files:
        raise FileNotFoundError(f"No context package found for chunk {chunk_id}")

    file_path = matching_files[-1]
    LOGGER.info(f"Loading {file_path.name}")

    with open(file_path) as f:
        data = json.load(f)

    return file_path, data


def calculate_tokens(package: Dict[str, Any]) -> Dict[str, int]:
    """Calculate token counts for each section of the context package."""
    context_payload = package.get("context_payload", {})

    # Warm slice tokens
    warm_chunks = context_payload.get("warm_slice", {}).get("chunks", [])
    warm_tokens = sum(c.get("token_count", 0) for c in warm_chunks)

    # Structured passages tokens
    structured = context_payload.get("structured_passages", [])
    structured_tokens = sum(
        s.get("token_count", 0) for s in structured
    )

    # Retrieved passages tokens
    retrieved = context_payload.get("retrieved_passages", {}).get("results", [])
    retrieved_tokens = sum(
        r.get("token_count", 0) for r in retrieved
    )

    total = warm_tokens + structured_tokens + retrieved_tokens

    return {
        "total": total,
        "warm": warm_tokens,
        "structured": structured_tokens,
        "retrieved": retrieved_tokens,
        "warm_chunk_count": len(warm_chunks),
    }


def trim_warm_slice(
    package: Dict[str, Any],
    target_tokens: int,
    min_chunks: int = MIN_WARM_CHUNKS,
) -> tuple[Dict[str, Any], Dict[str, int]]:
    """
    Trim warm slice by removing oldest chunks until under target token count.

    Returns:
        - Modified package
        - Token counts before and after
    """
    context_payload = package.get("context_payload", {})
    warm_slice = context_payload.get("warm_slice", {})
    warm_chunks = warm_slice.get("chunks", [])

    tokens_before = calculate_tokens(package)

    if tokens_before["total"] <= target_tokens:
        LOGGER.info(f"  Already under target ({tokens_before['total']} <= {target_tokens})")
        return package, {"before": tokens_before["total"], "after": tokens_before["total"]}

    # Sort chunks by chunk_id (oldest first)
    warm_chunks.sort(key=lambda c: c.get("chunk_id", 0))

    LOGGER.info(f"  Before: {tokens_before['total']} tokens, {tokens_before['warm_chunk_count']} warm chunks")
    LOGGER.info(f"  Need to remove ~{tokens_before['total'] - target_tokens} tokens")

    # Remove oldest chunks until we're under target
    removed_chunks = []
    while len(warm_chunks) > min_chunks:
        current_total = calculate_tokens(package)["total"]
        if current_total <= target_tokens:
            break

        # Remove oldest chunk
        removed = warm_chunks.pop(0)
        removed_chunks.append(removed["chunk_id"])
        LOGGER.debug(f"    Removed chunk {removed['chunk_id']}: {removed.get('token_count', 0)} tokens")

    # Update the package
    warm_slice["chunks"] = warm_chunks
    warm_slice["token_count"] = sum(c.get("token_count", 0) for c in warm_chunks)
    context_payload["warm_slice"] = warm_slice
    package["context_payload"] = context_payload

    # Update metadata
    if "metadata" in package and "estimated_payload_tokens" in package["metadata"]:
        tokens_after = calculate_tokens(package)
        package["metadata"]["estimated_payload_tokens"].update({
            "total": tokens_after["total"],
            "warm_slice": tokens_after["warm"],
            "structured": tokens_after["structured"],
            "retrieved": tokens_after["retrieved"],
        })

    tokens_after = calculate_tokens(package)
    LOGGER.info(f"  After: {tokens_after['total']} tokens, {len(warm_chunks)} warm chunks")
    LOGGER.info(f"  Removed {len(removed_chunks)} chunks: {removed_chunks}")

    return package, {"before": tokens_before["total"], "after": tokens_after["total"]}


def update_prompt_context(chunk_id: int, package: Dict[str, Any], engine):
    """Update the prompts table with the trimmed context JSON."""
    context_payload = package.get("context_payload", {})

    update_query = """
    UPDATE apex_audition.prompts
    SET context = CAST(:context AS jsonb)
    WHERE chunk_id = :chunk_id
    RETURNING id
    """

    with engine.begin() as conn:
        result = conn.execute(
            text(update_query),
            {"chunk_id": chunk_id, "context": json.dumps(context_payload)}
        )
        prompt_id = result.fetchone()[0]
        LOGGER.info(f"  Updated prompt {prompt_id} in database")
        return prompt_id


def main():
    parser = argparse.ArgumentParser(description="Trim oversized context packages")
    parser.add_argument(
        "--context-dir",
        type=Path,
        default=Path("/Users/pythagor/nexus/context_packages/apex_audition"),
        help="Directory containing context package JSON files",
    )
    parser.add_argument(
        "--target-tokens",
        type=int,
        default=TARGET_TOKENS,
        help=f"Target token count (default: {TARGET_TOKENS})",
    )
    parser.add_argument(
        "--chunks",
        type=int,
        nargs="+",
        default=OVERSIZED_CHUNKS,
        help="Chunk IDs to trim",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be trimmed without making changes",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging",
    )
    args = parser.parse_args()

    # Setup logging
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(levelname)s: %(message)s"
    )

    # Initialize database connection
    engine = create_engine("postgresql://pythagor@localhost:5432/NEXUS")

    LOGGER.info(f"Trimming {len(args.chunks)} context packages to {args.target_tokens:,} tokens")
    LOGGER.info(f"Target chunks: {args.chunks}")
    print()

    results = []

    for chunk_id in args.chunks:
        LOGGER.info(f"Processing chunk {chunk_id}...")

        try:
            # Load the context package
            file_path, package = load_context_package(chunk_id, args.context_dir)

            # Trim the warm slice
            trimmed_package, token_change = trim_warm_slice(
                package,
                target_tokens=args.target_tokens,
            )

            if not args.dry_run:
                # Save the trimmed package
                with open(file_path, "w") as f:
                    json.dump(trimmed_package, f, indent=2, ensure_ascii=False)
                    f.write("\n")
                LOGGER.info(f"  Saved trimmed package to {file_path.name}")

                # Update database
                prompt_id = update_prompt_context(chunk_id, trimmed_package, engine)

                results.append({
                    "chunk_id": chunk_id,
                    "prompt_id": prompt_id,
                    "tokens_before": token_change["before"],
                    "tokens_after": token_change["after"],
                    "tokens_saved": token_change["before"] - token_change["after"],
                })
            else:
                LOGGER.info("  [DRY RUN] Would save trimmed package")
                results.append({
                    "chunk_id": chunk_id,
                    "tokens_before": token_change["before"],
                    "tokens_after": token_change["after"],
                    "tokens_saved": token_change["before"] - token_change["after"],
                })

            print()

        except Exception as e:
            LOGGER.error(f"  Failed to process chunk {chunk_id}: {e}")
            print()
            continue

    # Summary
    print("=" * 60)
    LOGGER.info("SUMMARY")
    print("=" * 60)

    for result in results:
        chunk_id = result["chunk_id"]
        before = result["tokens_before"]
        after = result["tokens_after"]
        saved = result["tokens_saved"]
        status = "✓" if after <= args.target_tokens else "⚠"

        LOGGER.info(
            f"{status} Chunk {chunk_id:4d}: {before:6,} → {after:6,} tokens "
            f"(saved {saved:,})"
        )

    if args.dry_run:
        LOGGER.info("\n[DRY RUN] No changes were made")
    else:
        LOGGER.info(f"\n✓ Successfully trimmed {len(results)} context packages")


if __name__ == "__main__":
    main()
