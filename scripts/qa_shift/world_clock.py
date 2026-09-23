"""Read-only world_clock QA family: canonical identity and the seed's face."""

from __future__ import annotations

import argparse
import json
from typing import Any

from nexus.api.db_pool import get_connection
from nexus.api.slot_utils import slot_dbname
from nexus.util.clock_face import clock_face


def measure_connection(conn: Any) -> dict[str, Any]:
    """Measure one database in a caller-owned read-only transaction."""
    with conn.cursor() as cur:
        cur.execute("SELECT current_setting('transaction_read_only')")
        if cur.fetchone()[0] != "on":
            raise RuntimeError("world_clock requires a read-only transaction")
        cur.execute(
            """
            SELECT count(*), count(*) FILTER (
                WHERE nv.world_time IS DISTINCT FROM cm.world_time
            )
            FROM chunk_metadata cm
            JOIN narrative_view nv ON nv.id = cm.chunk_id
            """
        )
        chunks, disagreements = cur.fetchone()
        cur.execute("SELECT base_timestamp FROM global_variables WHERE id = true")
        row = cur.fetchone()
        if row is None:
            raise RuntimeError("Missing global_variables singleton")
        base = row[0]
    return {
        "chunks": chunks,
        "disagreements": disagreements,
        "base_timestamp_face": clock_face(base) if base is not None else None,
    }


def measure_slot(slot: int) -> dict[str, Any]:
    """Report a slot without changing data, schema, or pool configuration."""
    with get_connection(slot_dbname(slot)) as conn:
        with conn.cursor() as cur:
            cur.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        return {"slot": slot, **measure_connection(conn)}


def main() -> int:
    """Print one report per selected slot; disagreements produce exit code 1."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--slot", type=int, choices=range(1, 6), action="append")
    args = parser.parse_args()
    reports = [measure_slot(slot) for slot in (args.slot or range(1, 6))]
    print(json.dumps({"family": "world_clock", "slots": reports}, indent=2))
    return int(any(row["disagreements"] for row in reports))


if __name__ == "__main__":
    raise SystemExit(main())
