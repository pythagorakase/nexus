#!/usr/bin/env python3
"""Audit NEXUS save slots for GIS hygiene violations."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import Any, Iterable, Sequence

import psycopg2
from psycopg2.extras import RealDictCursor

from nexus.api.slot_utils import all_slots, get_slot_db_url


@dataclass(frozen=True)
class AuditCategory:
    """One named GIS audit result set."""

    name: str
    columns: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]


def audit_slot(conn: Any) -> list[AuditCategory]:
    """Run every read-only GIS audit against one slot connection."""

    queries = (
        (
            "Placeless characters",
            ("name", "provenance"),
            """
            SELECT name,
                   COALESCE(extra_data ->> 'source', '') AS provenance
            FROM characters
            WHERE current_location IS NULL
            ORDER BY id
            """,
        ),
        (
            "Unlocated non-virtual places",
            ("name", "type"),
            """
            SELECT name, type::text AS type
            FROM places
            WHERE type::text <> 'virtual'
              AND coordinates IS NULL
            ORDER BY id
            """,
        ),
        (
            "Zone-less places",
            ("name", "type"),
            """
            SELECT name, type::text AS type
            FROM places
            WHERE zone IS NULL
            ORDER BY id
            """,
        ),
        (
            "Boundary-less zones",
            ("id", "name"),
            """
            SELECT id::text AS id, name
            FROM zones
            WHERE boundary IS NULL
            ORDER BY id
            """,
        ),
    )
    categories = []
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        for name, columns, sql in queries:
            cur.execute(sql)
            rows = tuple(
                tuple(str(row[column] or "") for column in columns)
                for row in cur.fetchall()
            )
            categories.append(AuditCategory(name, columns, rows))
    return categories


def _table(columns: Sequence[str], rows: Iterable[Sequence[str]]) -> list[str]:
    materialized = [tuple(row) for row in rows]
    widths = [len(column) for column in columns]
    for row in materialized:
        widths = [max(width, len(value)) for width, value in zip(widths, row)]
    header = " | ".join(column.ljust(width) for column, width in zip(columns, widths))
    divider = "-+-".join("-" * width for width in widths)
    lines = [header, divider]
    lines.extend(
        " | ".join(value.ljust(width) for value, width in zip(row, widths))
        for row in materialized
    )
    return lines


def format_slot_report(slot: int, categories: Sequence[AuditCategory]) -> str:
    """Render one slot's audit as plain tables."""

    lines = [f"GIS HYGIENE — slot {slot}"]
    for category in categories:
        lines.extend(["", f"{category.name} ({len(category.rows)})"])
        lines.extend(_table(category.columns, category.rows))
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""

    parser = argparse.ArgumentParser(description=__doc__)
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--slot", type=int, choices=all_slots())
    selection.add_argument("--all", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Audit requested slots and return nonzero for any finding."""

    args = build_parser().parse_args(argv)
    slots = all_slots() if args.all else [args.slot]
    reports = []
    finding_count = 0
    for slot in slots:
        conn = psycopg2.connect(get_slot_db_url(slot=slot))
        try:
            categories = audit_slot(conn)
        finally:
            conn.close()
        finding_count += sum(len(category.rows) for category in categories)
        reports.append(format_slot_report(slot, categories))
    print("\n\n".join(reports))
    return 1 if finding_count else 0


if __name__ == "__main__":
    raise SystemExit(main())
