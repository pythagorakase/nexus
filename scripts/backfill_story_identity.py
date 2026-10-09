#!/usr/bin/env python3
"""Mint story identities for slots that predate migration 146 (issue #822).

Migration 146 creates ``story_identity`` and ``story_lineage`` and writes no
row. This one-time, rerunnable backfill gives each target slot database an
origin ``backfill`` identity row when it has none, then records the fork
lineage that evidence supports: ``save_02`` was cloned from ``save_01``
(822-Q4). ``save_03`` and ``save_04`` stay independent unless the owner names
the copy with ``--fork``.

Usage:
    python scripts/backfill_story_identity.py --all --write-locked-slot
    python scripts/backfill_story_identity.py --slot 3
    python scripts/backfill_story_identity.py --all --fork 4:3

A rerun changes nothing. ``NEXUS_template`` is never a target: it carries the
tables and no row (822-Q13).
"""

from __future__ import annotations

import argparse
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Any, Optional, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nexus.api.story_identity import record_fork  # noqa: E402
from nexus.database import maintenance_connection, transaction  # noqa: E402
from scripts.migrate import SLOT_DBS, is_db_locked  # noqa: E402
import nexus.maintenance.migrate as migrate  # noqa: E402

OPERATION = "story_identity_backfill"


@dataclass(frozen=True)
class ForkSpec:
    """The database ``child`` holds a fork of the story in ``parent``."""

    child: str
    parent: str
    evidence: str


HISTORICAL_FORKS = (
    ForkSpec(
        "save_02",
        "save_01",
        "save_02 was cloned from save_01 by the 2026-07-17 order; both held "
        "1,425 chunks and slot_created_at 2026-01-14 18:22:29.574584-05 when "
        "this backfill ran (822-Q4).",
    ),
)


def _require_table(cur: Any, dbname: str) -> None:
    """Raise unless ``dbname`` has both tables from migration 146."""
    for table in ("story_identity", "story_lineage"):
        cur.execute("SELECT to_regclass(%s) IS NULL", (f"public.{table}",))
        if cur.fetchone()[0]:
            raise RuntimeError(
                f"{dbname} has no public.{table} table; apply migration 146 "
                "first with python scripts/migrate.py"
            )


def _read_identity(cur: Any, dbname: str) -> tuple[str, str]:
    """Return ``(story_uuid, origin)`` of the single row, raising otherwise."""
    cur.execute("SELECT story_uuid::text, origin FROM public.story_identity")
    rows = cur.fetchall()
    if len(rows) != 1:
        raise RuntimeError(
            f"{dbname} holds {len(rows)} story_identity rows; exactly one is required"
        )
    return rows[0][0], rows[0][1]


def _preflight_databases(targets: Sequence[str], forks: Sequence[ForkSpec]) -> None:
    """Check every target and fork parent read-only before minting any UUID."""
    identities: dict[str, Optional[tuple[str, str]]] = {}
    lineage: dict[str, list[str]] = {}
    databases = dict.fromkeys([*targets, *(fork.parent for fork in forks)])
    for dbname in databases:
        with closing(maintenance_connection(dbname, operation=OPERATION)) as conn:
            conn.set_session(readonly=True)
            with transaction(conn), conn.cursor() as cur:
                _require_table(cur, dbname)
                cur.execute(
                    "SELECT story_uuid::text, origin FROM public.story_identity"
                )
                rows = cur.fetchall()
                if len(rows) > 1 or (not rows and dbname not in targets):
                    raise RuntimeError(
                        f"{dbname} holds {len(rows)} story_identity rows; "
                        "exactly one is required for an existing fork parent"
                    )
                identities[dbname] = rows[0] if rows else None
                cur.execute("SELECT parent_uuid::text FROM public.story_lineage")
                lineage[dbname] = [row[0] for row in cur.fetchall()]

    requested_parents: dict[str, str] = {}
    for fork in forks:
        child = identities[fork.child]
        parent = identities[fork.parent]
        child_origin = child[1] if child else "backfill"
        parent_origin = parent[1] if parent else "backfill"
        if (child_origin, parent_origin) != ("backfill", "backfill"):
            raise ValueError(
                f"fork {fork.child} <- {fork.parent} needs two backfill "
                f"identities; found {child_origin} and {parent_origin}"
            )
        if fork.child == fork.parent or (child and parent and child[0] == parent[0]):
            raise ValueError(
                f"fork {fork.child} <- {fork.parent} would be self-parentage"
            )
        previous = requested_parents.setdefault(fork.child, fork.parent)
        if previous != fork.parent:
            raise ValueError(
                f"fork child {fork.child} has conflicting requested parents"
            )
        parents = lineage[fork.child]
        if parents and (parent is None or parents != [parent[0]]):
            raise RuntimeError(
                f"{fork.child} already forks {', '.join(parents)}, not {fork.parent}"
            )


def backfill_story_identity(
    targets: Sequence[str],
    forks: Sequence[ForkSpec],
    *,
    write_locked_slot: bool = False,
) -> dict[str, str]:
    """Mint a ``backfill`` identity on each target lacking one; record forks.

    Before any write, validate every target and fork parent: template/lock
    policy, both identity tables, row counts, fork origins and existing
    lineage. Each target is then written in its own transaction, so a later
    connection failure or concurrent change can still leave a partial run.
    A rerun preserves already-committed identities. A fork is recorded only
    between two ``backfill`` identities (its evidence describes those stories),
    and only once; a child already linked to another parent raises.

    Returns:
        Each target database's ``story_uuid``.
    """
    template = migrate.TEMPLATE_DB
    for dbname in targets:
        if dbname == template:
            raise ValueError(f"{template} carries no story identity (822-Q13)")
    for fork in forks:
        if template in (fork.child, fork.parent):
            raise ValueError(f"{template} is never a fork's child or parent")
        if fork.child not in targets:
            raise ValueError(f"fork child {fork.child} is not a backfill target")
    locked = {dbname for dbname in targets if is_db_locked(dbname)}
    if locked and not write_locked_slot:
        raise ValueError(
            f"{', '.join(sorted(locked))} locked; pass --write-locked-slot "
            "(write_locked_slot=True) to backfill a locked slot"
        )
    _preflight_databases(targets, forks)

    identities: dict[str, str] = {}
    for dbname in targets:
        with closing(
            maintenance_connection(
                dbname, write_locked_slot=dbname in locked, operation=OPERATION
            )
        ) as conn:
            with transaction(conn), conn.cursor() as cur:
                _require_table(cur, dbname)
                cur.execute(
                    "INSERT INTO public.story_identity (origin) "
                    "SELECT 'backfill' "
                    "WHERE NOT EXISTS (SELECT 1 FROM public.story_identity)"
                )
                story_uuid, origin = _read_identity(cur, dbname)
        identities[dbname] = story_uuid
        print(f"{dbname} {story_uuid} {origin}")

    for fork in forks:
        with closing(maintenance_connection(fork.parent, operation=OPERATION)) as conn:
            conn.set_session(readonly=True)
            with transaction(conn), conn.cursor() as cur:
                _require_table(cur, fork.parent)
                parent_uuid, parent_origin = _read_identity(cur, fork.parent)
        with closing(
            maintenance_connection(
                fork.child,
                write_locked_slot=fork.child in locked,
                operation=OPERATION,
            )
        ) as conn:
            with transaction(conn), conn.cursor() as cur:
                child_uuid, child_origin = _read_identity(cur, fork.child)
                if (child_origin, parent_origin) != ("backfill", "backfill"):
                    raise ValueError(
                        f"fork {fork.child} <- {fork.parent} needs two backfill "
                        f"identities; found {child_origin} and {parent_origin}"
                    )
                cur.execute(
                    "SELECT parent_uuid::text FROM public.story_lineage "
                    "WHERE child_uuid = %s",
                    (child_uuid,),
                )
                parents = [row[0] for row in cur.fetchall()]
                if parents == [parent_uuid]:
                    status = "present"
                elif parents:
                    raise RuntimeError(
                        f"{fork.child} already forks {', '.join(parents)}, not "
                        f"{fork.parent} ({parent_uuid})"
                    )
                else:
                    record_fork(
                        cur,
                        child_uuid=child_uuid,
                        parent_uuid=parent_uuid,
                        source_dbname=fork.parent,
                        evidence=fork.evidence,
                    )
                    status = "recorded"
        print(
            f"{fork.child} fork of {fork.parent} {child_uuid} <- {parent_uuid} "
            f"{status}"
        )
    return identities


def _owner_fork(value: str) -> ForkSpec:
    """Build the fork the owner named as ``child:parent``."""
    if value not in ("3:4", "4:3"):
        raise ValueError("An owner fork must be 3:4 or 4:3")
    child, parent = value.split(":")
    return ForkSpec(
        f"save_0{child}",
        f"save_0{parent}",
        f"The owner named save_0{child} a copy of save_0{parent} (822-Q4).",
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Run the backfill from the command line."""
    parser = argparse.ArgumentParser(
        description="Mint story identities for slots that predate migration 146."
    )
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--all", action="store_true", help="every save slot")
    target.add_argument("--slot", type=int, choices=range(1, 6), help="one slot")
    parser.add_argument(
        "--write-locked-slot",
        action="store_true",
        help="Override read-only policy only for this maintenance session",
    )
    parser.add_argument(
        "--fork",
        choices=("3:4", "4:3"),
        help="child:parent copy the owner named (822-Q4)",
    )
    args = parser.parse_args(argv)
    targets = list(SLOT_DBS) if args.all else [f"save_0{args.slot}"]
    forks = list(HISTORICAL_FORKS)
    if args.fork:
        forks.append(_owner_fork(args.fork))
    backfill_story_identity(
        targets,
        [fork for fork in forks if fork.child in targets],
        write_locked_slot=args.write_locked_slot,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
