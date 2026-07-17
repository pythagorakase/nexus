"""Reconstruct world state at an arbitrary chunk, or audit ledger sufficiency.

The read half of the reconstruction contract (issue #426): world state at
chunk N = latest checkpoint at or before N + the Orrery and Skald ledgers
in chunk order, with relationships unwound from trigger pre-images.

Usage:
    python scripts/replay_state.py --slot 2 --chunk 1400
    python scripts/replay_state.py --slot 2 --chunk 1400 --output state.json
    python scripts/replay_state.py --slot 2 --verify

``--verify`` replays every consecutive checkpoint pair and diffs the result
against the stored target checkpoint; exits nonzero on drift. Zero drift
proves the ledgers were sufficient across every checkpointed window.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from dataclasses import asdict
from typing import Any

import psycopg2

# Resolve imports against this checkout, not the shared Poetry environment's
# editable-install target. Worktrees can carry a settings model and nexus.toml
# change together, so importing another checkout makes the replay gate lie.
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from nexus.agents.orrery.replay import (  # noqa: E402
    reconstruct_state_at_sync,
    verify_checkpoints_sync,
)
from nexus.api.slot_utils import slot_dbname  # noqa: E402


def _connect(slot: int) -> Any:
    conn = psycopg2.connect(dbname=slot_dbname(slot), host="localhost")
    conn.set_session(readonly=True)
    return conn


def _print_reconstruction(slot: int, chunk_id: int, output: str | None) -> None:
    conn = _connect(slot)
    try:
        with conn.cursor() as cur:
            result = reconstruct_state_at_sync(cur, chunk_id)
    finally:
        conn.close()

    print(
        f"slot {slot}: state at chunk {result.target_chunk_id} "
        f"(base checkpoint {result.base_checkpoint_id} "
        f"at chunk {result.base_checkpoint_chunk_id})"
    )
    for section, rows in result.state.items():
        tier = "approximate" if section in result.approximate_sections else "exact"
        print(f"  {section:<32} {len(rows):>5} rows  [{tier}]")
        for note in result.notes.get(section, []):
            print(f"    - {note}")
    if output:
        document = {
            "target_chunk_id": result.target_chunk_id,
            "base_checkpoint_id": result.base_checkpoint_id,
            "base_checkpoint_chunk_id": result.base_checkpoint_chunk_id,
            "approximate_sections": sorted(result.approximate_sections),
            "notes": result.notes,
            "state": result.state,
        }
        with open(output, "w") as handle:
            json.dump(document, handle, indent=2, default=str)
        print(f"wrote {output}")


def _print_verification(slot: int) -> int:
    conn = _connect(slot)
    try:
        with conn.cursor() as cur:
            verdicts = verify_checkpoints_sync(cur)
    finally:
        conn.close()

    if not verdicts:
        print(
            f"slot {slot}: fewer than two checkpoints at distinct chunks — "
            "nothing to verify"
        )
        return 0
    total_drift = 0
    for verdict in verdicts:
        status = "DRIFT" if verdict.drifts else "ok"
        print(
            f"slot {slot}: checkpoint {verdict.base_checkpoint_id} "
            f"(chunk {verdict.base_chunk_id}) -> "
            f"checkpoint {verdict.target_checkpoint_id} "
            f"(chunk {verdict.target_chunk_id}): {status}"
            + (
                f", {verdict.skipped_unreproducible} unreproducible "
                "column(s) skipped"
                if verdict.skipped_unreproducible
                else ""
            )
        )
        for drift in verdict.drifts:
            total_drift += 1
            print(f"  {json.dumps(asdict(drift), default=str)}")
    if total_drift:
        print(
            f"{total_drift} drift finding(s): a writer mutated checkpointed "
            "state without a replayable ledger record"
        )
        return 1
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--slot", type=int, choices=range(1, 6), required=True)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--chunk", type=int, help="chunk id to reconstruct at")
    group.add_argument(
        "--verify",
        action="store_true",
        help="replay every checkpoint pair and diff against stored documents",
    )
    parser.add_argument("--output", help="write the full state document (JSON)")
    args = parser.parse_args()

    if args.verify:
        sys.exit(_print_verification(args.slot))
    _print_reconstruction(args.slot, args.chunk, args.output)


if __name__ == "__main__":
    main()
