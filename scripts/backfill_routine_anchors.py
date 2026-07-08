"""Backfill routine anchors for characters that have none.

The anchored_routine drive band (ROUTINE_COMMUTE, WORK, and the mundane
band) can only serve characters with `character_routine_anchors` rows;
an unprovisioned character refuses every anchor-gated package. This
script proposes home anchors for the unprovisioned cast.

Derivation ladder (home anchor, best evidence wins):

1. active ``resides_at`` pair tag -> that place, ``fixed_place``
   (high confidence — the fiction has committed to a residence)
2. ``characters.current_location`` -> that place's zone,
   ``zone_resolved`` (medium confidence — coarse on purpose: a wrong
   concrete home contradicts canon, a zone rarely does)
3. no evidence -> reported as unprovisioned for the slot-retrofit pass

Work anchors are NOT derived: profession evidence is currently too
sparse to guess workplaces deterministically; the report lists them so
the retrofit pass can fill them with human review.

Default is a dry-run that writes a review CSV. ``--apply`` takes the
REVIEWED CSV back as its input and inserts exactly the rows it still
contains (source='compiler_backfill') — delete or edit rows during
review and the deletions/edits are honored; the database is never
re-derived behind the reviewer's back.

Usage:
    python scripts/backfill_routine_anchors.py --slot 2 --out review.csv
    # ... review/edit review.csv ...
    python scripts/backfill_routine_anchors.py --slot 2 --apply review.csv
"""

from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import create_engine, text

from nexus.api.slot_utils import get_slot_db_url


@dataclass(frozen=True)
class AnchorProposal:
    character_entity_id: int
    character_name: str
    anchor_type: str
    mobility_policy: str
    place_id: Optional[int]
    zone_id: Optional[int]
    evidence: str
    confidence: str


UNPROVISIONED = "unprovisioned"

# Zone 0 is the "vehicles" zone: a character currently aboard a conveyance
# has no home-zone evidence there (though it may mean they are nomadic —
# a retrofit-review question, not a backfill guess).
VEHICLES_ZONE_ID = 0


def collect_proposals(conn) -> list[AnchorProposal]:
    rows = conn.execute(
        text(
            """
            SELECT
                c.entity_id,
                c.name,
                resides.place_id AS resides_place_id,
                cur.id AS current_place_id,
                cur.zone AS current_zone_id
            FROM characters c
            LEFT JOIN character_routine_anchors cra
                ON cra.character_entity_id = c.entity_id
               AND cra.anchor_type = 'home'
            LEFT JOIN LATERAL (
                SELECT p.id AS place_id
                FROM entity_pair_tags ept
                JOIN pair_tags pt ON pt.id = ept.pair_tag_id
                JOIN places p ON p.entity_id = ept.object_entity_id
                WHERE ept.subject_entity_id = c.entity_id
                  AND pt.tag = 'resides_at'
                  AND ept.cleared_at IS NULL
                ORDER BY ept.applied_at DESC
                LIMIT 1
            ) resides ON TRUE
            LEFT JOIN places cur ON cur.id = c.current_location
            WHERE cra.id IS NULL
            ORDER BY c.entity_id
            """
        )
    ).mappings()

    proposals: list[AnchorProposal] = []
    for row in rows:
        if row["resides_place_id"] is not None:
            proposals.append(
                AnchorProposal(
                    character_entity_id=row["entity_id"],
                    character_name=row["name"],
                    anchor_type="home",
                    mobility_policy="fixed_place",
                    place_id=row["resides_place_id"],
                    zone_id=None,
                    evidence=f"resides_at -> place {row['resides_place_id']}",
                    confidence="high",
                )
            )
        elif row["current_zone_id"] == VEHICLES_ZONE_ID:
            proposals.append(
                AnchorProposal(
                    character_entity_id=row["entity_id"],
                    character_name=row["name"],
                    anchor_type="home",
                    mobility_policy=UNPROVISIONED,
                    place_id=None,
                    zone_id=None,
                    evidence=(
                        f"current location place {row['current_place_id']} is "
                        "in the vehicles zone — aboard a conveyance, not home "
                        "evidence (possibly nomadic; review)"
                    ),
                    confidence="none",
                )
            )
        elif row["current_zone_id"] is not None:
            proposals.append(
                AnchorProposal(
                    character_entity_id=row["entity_id"],
                    character_name=row["name"],
                    anchor_type="home",
                    mobility_policy="zone_resolved",
                    place_id=None,
                    zone_id=row["current_zone_id"],
                    evidence=(
                        f"current_location place {row['current_place_id']} "
                        f"-> zone {row['current_zone_id']}"
                    ),
                    confidence="medium",
                )
            )
        else:
            proposals.append(
                AnchorProposal(
                    character_entity_id=row["entity_id"],
                    character_name=row["name"],
                    anchor_type="home",
                    mobility_policy=UNPROVISIONED,
                    place_id=None,
                    zone_id=None,
                    evidence="no resides_at tag; current location has no zone",
                    confidence="none",
                )
            )
    return proposals


def write_csv(proposals: list[AnchorProposal], out) -> None:
    writer = csv.writer(out)
    writer.writerow(
        [
            "character_entity_id",
            "character_name",
            "anchor_type",
            "mobility_policy",
            "place_id",
            "zone_id",
            "evidence",
            "confidence",
        ]
    )
    for p in proposals:
        writer.writerow(
            [
                p.character_entity_id,
                p.character_name,
                p.anchor_type,
                p.mobility_policy,
                p.place_id if p.place_id is not None else "",
                p.zone_id if p.zone_id is not None else "",
                p.evidence,
                p.confidence,
            ]
        )


def read_reviewed_csv(path: str) -> list[AnchorProposal]:
    """Load reviewed proposals; the CSV is the authority after review."""

    proposals: list[AnchorProposal] = []
    with open(path, newline="") as handle:
        reader = csv.DictReader(handle)
        required = {
            "character_entity_id",
            "anchor_type",
            "mobility_policy",
            "place_id",
            "zone_id",
        }
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(
                f"{path}: reviewed CSV is missing columns {sorted(missing)}"
            )
        for row in reader:
            proposals.append(
                AnchorProposal(
                    character_entity_id=int(row["character_entity_id"]),
                    character_name=row.get("character_name", ""),
                    anchor_type=row["anchor_type"],
                    mobility_policy=row["mobility_policy"],
                    place_id=int(row["place_id"]) if row["place_id"] else None,
                    zone_id=int(row["zone_id"]) if row["zone_id"] else None,
                    evidence=row.get("evidence", ""),
                    confidence=row.get("confidence", ""),
                )
            )
    return proposals


def apply_proposals(conn, proposals: list[AnchorProposal]) -> int:
    applied = 0
    for p in proposals:
        if p.mobility_policy == UNPROVISIONED:
            continue
        conn.execute(
            text(
                """
                INSERT INTO character_routine_anchors (
                    character_entity_id, anchor_type, place_id, zone_id,
                    mobility_policy, schedule, source
                ) VALUES (
                    :entity_id, :anchor_type, :place_id, :zone_id,
                    :mobility_policy, '{}'::jsonb, 'compiler_backfill'
                )
                ON CONFLICT (character_entity_id, anchor_type) DO NOTHING
                """
            ),
            {
                "entity_id": p.character_entity_id,
                "anchor_type": p.anchor_type,
                "place_id": p.place_id,
                "zone_id": p.zone_id,
                "mobility_policy": p.mobility_policy,
            },
        )
        applied += 1
    return applied


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--slot", type=int, required=True, help="Save slot (1-5)")
    parser.add_argument(
        "--out",
        type=str,
        default=None,
        help="Review CSV path (default: stdout)",
    )
    parser.add_argument(
        "--apply",
        type=str,
        default=None,
        metavar="REVIEWED_CSV",
        help="Insert exactly the rows in this reviewed CSV (the review is "
        "the authority; the database is not re-derived)",
    )
    args = parser.parse_args()

    engine = create_engine(get_slot_db_url(slot=args.slot))
    with engine.begin() as conn:
        if args.apply:
            reviewed = read_reviewed_csv(args.apply)
            applied = apply_proposals(conn, reviewed)
            skipped = len(reviewed) - applied
            print(
                f"slot {args.slot}: applied {applied} anchors from "
                f"{args.apply}; skipped {skipped} unprovisioned rows"
            )
            return

        proposals = collect_proposals(conn)
        derivable = [p for p in proposals if p.mobility_policy != UNPROVISIONED]
        missing = [p for p in proposals if p.mobility_policy == UNPROVISIONED]

        out = open(args.out, "w", newline="") if args.out else sys.stdout
        try:
            write_csv(proposals, out)
        finally:
            if args.out:
                out.close()
        print(
            f"\nslot {args.slot}: {len(derivable)} derivable "
            f"({sum(1 for p in derivable if p.confidence == 'high')} high, "
            f"{sum(1 for p in derivable if p.confidence == 'medium')} medium), "
            f"{len(missing)} unprovisioned. Dry run — review the CSV, then "
            "re-run with --apply <reviewed.csv>.",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
