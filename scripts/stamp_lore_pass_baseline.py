"""Stamp a migration boundary or refresh an existing Pass-2 fingerprint.

Usage:
    python scripts/stamp_lore_pass_baseline.py --slot 2
    python scripts/stamp_lore_pass_baseline.py --dbname ref_corpus
    python scripts/stamp_lore_pass_baseline.py --refresh-fingerprint --slot 2

Run this once after migration 107 for an existing save whose accepted tail
predates durable LORE baselines. It never infers a historical retrieval set.
"""

from __future__ import annotations

import argparse
from contextlib import closing
import json
from pathlib import Path
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from nexus.api.slot_utils import get_slot_db_url  # noqa: E402
from nexus.config import load_settings_as_dict  # noqa: E402
from nexus.database import maintenance_connection  # noqa: E402
from nexus.memory.context_state import (
    Pass2BaselineV1,
    bind_pass2_baseline,
)  # noqa: E402
from nexus.memory.manager import (
    empty_pass2_baseline,
    pass2_baseline_config_fingerprint,
)  # noqa: E402
from scripts.database_targets import evaluation_dbname  # noqa: E402


def stamp_slot_tail(
    slot: int | None = None,
    *,
    dbname: str | None = None,
    write_locked_slot: bool = False,
) -> tuple[int, bool, bool]:
    """Stamp the slot's migration boundary.

    Stamps the accepted tail's canonical baseline row when missing, and
    backfills the staged (deliberately unbound) baseline onto a pre-migration
    provisional incubator draft whose lore_pass_baseline is NULL. Returns
    (tail_chunk_id, tail_stamped, incubator_stamped); raises when the slot has
    no accepted tail or nothing needed stamping.
    """

    if (slot is None) == (dbname is None):
        raise ValueError("Select exactly one slot or evaluation database")
    if dbname is not None:
        evaluation_dbname(dbname)
    target = dbname if dbname is not None else f"slot {slot}"
    from nexus.api.slot_utils import slot_dbname
    from nexus.config.story_model import read_story_settings, story_context_settings

    settings = story_context_settings(
        load_settings_as_dict(), read_story_settings(dbname or slot_dbname(slot))
    )
    staged = empty_pass2_baseline(settings)
    connection = maintenance_connection(
        dbname,
        db_url=get_slot_db_url(slot=slot) if dbname is None else None,
        write_locked_slot=write_locked_slot,
        operation="stamp Pass-2 baseline",
    )
    with closing(connection), connection as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM narrative_chunks ORDER BY id DESC LIMIT 1")
            row = cur.fetchone()
            if row is None:
                raise RuntimeError(f"{target} has no accepted narrative tail")
            chunk_id = int(row[0])

            cur.execute(
                "SELECT 1 FROM lore_pass_baselines WHERE chunk_id = %s",
                (chunk_id,),
            )
            tail_stamped = cur.fetchone() is None
            if tail_stamped:
                bound = bind_pass2_baseline(staged, chunk_id)
                cur.execute(
                    """
                    INSERT INTO lore_pass_baselines (chunk_id, schema_version, payload)
                    VALUES (%s, %s, %s::jsonb)
                    """,
                    (
                        chunk_id,
                        bound.schema_version,
                        json.dumps(bound.model_dump(mode="json")),
                    ),
                )

            cur.execute(
                """
                UPDATE incubator
                SET lore_pass_baseline = %s::jsonb
                WHERE lore_pass_baseline IS NULL
                """,
                (json.dumps(staged.model_dump(mode="json")),),
            )
            incubator_stamped = cur.rowcount > 0

            if not tail_stamped and not incubator_stamped:
                raise RuntimeError(
                    f"{target} tail chunk {chunk_id} already has a Pass-2 "
                    "baseline and no provisional draft needed stamping"
                )
    return chunk_id, tail_stamped, incubator_stamped


def refresh_tail_fingerprint(
    slot: int | None = None,
    *,
    dbname: str | None = None,
    write_locked_slot: bool = False,
) -> tuple[int, str, str]:
    """Refresh only the accepted tail fingerprint after a compatible config change.

    The operator must establish that Pass-2 semantics are unchanged. This does
    not reconstruct missing baselines or update historical/provisional payloads.
    """
    if (slot is None) == (dbname is None):
        raise ValueError("Select exactly one slot or evaluation database")
    if dbname is not None:
        evaluation_dbname(dbname)
    from nexus.api.slot_utils import slot_dbname
    from nexus.config.story_model import read_story_settings, story_context_settings

    target = dbname or slot_dbname(slot)
    settings = story_context_settings(
        load_settings_as_dict(), read_story_settings(target)
    )
    new_fingerprint = pass2_baseline_config_fingerprint(settings)
    connection = maintenance_connection(
        dbname,
        db_url=get_slot_db_url(slot=slot) if dbname is None else None,
        write_locked_slot=write_locked_slot,
        operation="refresh Pass-2 fingerprint",
    )
    with closing(connection), connection as conn, conn.cursor() as cur:
        cur.execute("SELECT id FROM narrative_chunks ORDER BY id DESC LIMIT 1")
        row = cur.fetchone()
        if row is None:
            raise RuntimeError(f"{target} has no accepted narrative tail")
        chunk_id = int(row[0])
        cur.execute(
            "SELECT schema_version, payload FROM lore_pass_baselines "
            "WHERE chunk_id = %s FOR UPDATE",
            (chunk_id,),
        )
        row = cur.fetchone()
        if row is None:
            raise RuntimeError(
                f"{target} tail chunk {chunk_id} has no Pass-2 baseline; "
                "cannot refresh its fingerprint"
            )
        baseline = Pass2BaselineV1.model_validate(row[1])
        if baseline.parent_chunk_id != chunk_id or baseline.schema_version != row[0]:
            raise RuntimeError(f"{target} tail baseline identity or schema mismatch")
        old_fingerprint = baseline.config_fingerprint
        cur.execute(
            "UPDATE lore_pass_baselines SET payload = "
            "jsonb_set(payload, '{config_fingerprint}', %s::jsonb, false) "
            "WHERE chunk_id = %s",
            (json.dumps(new_fingerprint), chunk_id),
        )
    return chunk_id, old_fingerprint, new_fingerprint


def main(argv: Any = None) -> int:
    """Parse CLI arguments and update one explicitly selected baseline."""

    parser = argparse.ArgumentParser(description=__doc__)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--slot", type=int, choices=range(1, 6))
    target.add_argument("--dbname", type=evaluation_dbname)
    parser.add_argument(
        "--refresh-fingerprint",
        action="store_true",
        help="Refresh an existing tail fingerprint after a compatible config change",
    )
    parser.add_argument(
        "--write-locked-slot",
        action="store_true",
        help="Override read-only policy only for this maintenance session",
    )
    args = parser.parse_args(argv)
    if args.refresh_fingerprint:
        chunk_id, old, new = refresh_tail_fingerprint(
            args.slot, dbname=args.dbname, write_locked_slot=args.write_locked_slot
        )
        print(
            f"Refreshed {args.dbname or f'slot {args.slot}'} tail chunk {chunk_id} "
            f"Pass-2 fingerprint: {old} -> {new}"
        )
        return 0
    chunk_id, tail_stamped, incubator_stamped = stamp_slot_tail(
        args.slot, dbname=args.dbname, write_locked_slot=args.write_locked_slot
    )
    actions = []
    if tail_stamped:
        actions.append(f"tail chunk {chunk_id}")
    if incubator_stamped:
        actions.append("provisional incubator draft")
    print(
        f"Stamped {args.dbname or f'slot {args.slot}'} {' and '.join(actions)} with an explicit "
        "empty Pass-2 migration-boundary baseline."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
