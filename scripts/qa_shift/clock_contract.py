"""Read-only primary chunk-clock contract QA family (issue 778)."""

from __future__ import annotations

import argparse
import json
from typing import Any

from nexus.agents.orrery.replay import chunk_clock_report_sync
from nexus.api.db_pool import get_connection
from nexus.api.slot_utils import slot_dbname

SUMMARY_FIELDS = (
    "chunks",
    "disagreements",
    "primary_regressions",
    "missing_base",
    "nonprimary_contributions",
    "bootstrap_nonzero",
)


def measure_connection(conn: Any) -> dict[str, Any]:
    """Measure a caller-owned read-only transaction without repairing anything."""
    with conn.cursor() as cur:
        cur.execute("SELECT current_setting('transaction_read_only')")
        if cur.fetchone()[0] != "on":
            raise RuntimeError("clock_contract requires a read-only transaction")
        report = chunk_clock_report_sync(cur)
    return {name: report[name] for name in SUMMARY_FIELDS}


def measure_slot(slot: int) -> dict[str, Any]:
    """Read one slot under repeatable-read isolation and enforced read-only access."""
    with get_connection(slot_dbname(slot)) as conn:
        with conn.cursor() as cur:
            cur.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        return {"slot": slot, **measure_connection(conn)}


def main() -> int:
    """Print selected slots (all five by default); any violation exits 1."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--slot", type=int, choices=range(1, 6), action="append")
    args = parser.parse_args()
    reports = [measure_slot(slot) for slot in (args.slot or range(1, 6))]
    print(json.dumps({"family": "clock_contract", "slots": reports}, indent=2))
    return int(any(row[name] for row in reports for name in SUMMARY_FIELDS[1:]))


if __name__ == "__main__":
    raise SystemExit(main())
