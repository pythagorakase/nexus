"""Take a state checkpoint for one save slot (or all slots).

Usage:
    python scripts/checkpoint_state.py --slot 2 --label manual
    python scripts/checkpoint_state.py --all --label genesis

Genesis checkpoints retro-fit the instrumentation-era boundary for slots
older than migration 065: state is exact from this checkpoint forward,
approximate before (docs/orrery_audit_dashboard_notes.md, issue #426).
"""

from __future__ import annotations

import argparse

import psycopg2

from nexus.agents.orrery.reconstruction import capture_state_checkpoint_sync
from nexus.api.slot_utils import slot_dbname


def checkpoint_slot(slot: int, label: str) -> None:
    conn = psycopg2.connect(dbname=slot_dbname(slot), host="localhost")
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT max(id) FROM narrative_chunks")
            chunk_id = cur.fetchone()[0]
            checkpoint_id = capture_state_checkpoint_sync(
                cur, chunk_id=chunk_id, label=label
            )
        conn.commit()
        if checkpoint_id is None:
            print(f"slot {slot}: checkpoint ({chunk_id}, {label}) already exists")
        else:
            print(f"slot {slot}: checkpoint {checkpoint_id} at chunk {chunk_id}")
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--slot", type=int, choices=range(1, 6))
    group.add_argument("--all", action="store_true")
    parser.add_argument(
        "--label", choices=("genesis", "interval", "manual"), default="manual"
    )
    args = parser.parse_args()

    slots = range(1, 6) if args.all else [args.slot]
    for slot in slots:
        checkpoint_slot(slot, args.label)


if __name__ == "__main__":
    main()
