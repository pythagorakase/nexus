"""Read-only boundary_catchup QA family: crossed world-clock boundaries (issue 780).

For one primary-layer parent chunk, the family enumerates every scheduled
boundary that a child turn would cross for each configured skip length, and
for an optional explicit target. It reads through one session whose
transactions are read-only (``default_transaction_read_only=on``) and
repeatable read, so every window sees one snapshot. It materializes nothing,
simulates no rearm, and coalesces nothing.
"""

from __future__ import annotations

import argparse
from collections import Counter
from contextlib import closing
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
import json
import logging
from pathlib import Path
import tomllib
from typing import Any, Mapping, Optional, Sequence

import psycopg2
from psycopg2.extras import RealDictCursor

from nexus.agents.orrery.boundaries import (
    BoundaryEnumeration,
    BoundaryWindow,
    CrossedBoundary,
    enumerate_crossed_boundaries,
    parent_world_time,
)
from nexus.agents.orrery.db_rows import row_get
from nexus.api.slot_utils import slot_dbname
from nexus.config import load_settings
from nexus.config.settings_models import BoundaryCatchupSettings, OrrerySettings
from nexus.database import connection_kwargs
from scripts.database_targets import metrics_dbname

ROOT = Path(__file__).resolve().parent
FAMILY = "boundary_catchup"
READ_ONLY_ERROR = "boundary_catchup requires a read-only transaction"

logger = logging.getLogger(__name__)


def load_config(path: Path = ROOT / "qa_shift.toml") -> BoundaryCatchupSettings:
    """Validate the family's skip lengths from the QA kit's configuration."""
    return BoundaryCatchupSettings.model_validate(
        tomllib.loads(path.read_text())["boundary_catchup"]
    )


def open_read_only_connection(dbname: str) -> Any:
    """Open a session whose transactions are read-only and repeatable read."""
    metrics_dbname(dbname)
    return psycopg2.connect(
        **connection_kwargs(
            dbname,
            options=(
                "-c default_transaction_read_only=on "
                "-c default_transaction_isolation=repeatable\\ read"
            ),
        ),
        cursor_factory=RealDictCursor,
    )


def _json_value(value: Any) -> Any:
    """Render one crossing detail value as JSON-safe data."""
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def _crossing_report(crossing: CrossedBoundary) -> dict[str, Any]:
    return {
        "occurs_at_world_time": crossing.occurs_at_world_time.isoformat(),
        "producer": crossing.producer,
        "subject_key": list(crossing.subject_key),
        "boundary_class": crossing.boundary_class.value,
        "precedence": crossing.precedence,
        "owner_issue": crossing.owner_issue,
        "detail": _json_value(crossing.detail),
    }


def _window_report(
    enumeration: BoundaryEnumeration, *, skip_minutes: Optional[int]
) -> dict[str, Any]:
    window = enumeration.window
    report: dict[str, Any] = {"source": window.source}
    if skip_minutes is not None:
        report["skip_minutes"] = skip_minutes
    else:
        report["target_world_time"] = window.target_world_time.isoformat()
    per_subject = Counter(crossing.subject_key for crossing in enumeration.crossings)
    report.update(
        {
            "counts": dict(enumeration.counts),
            "at_or_before_previous": dict(enumeration.at_or_before_previous),
            "total": enumeration.total,
            "max_crossings_per_subject": max(per_subject.values(), default=0),
            "crossings": [
                _crossing_report(crossing) for crossing in enumeration.crossings
            ],
        }
    )
    return report


def _newest_primary_chunk(cur: Any) -> int:
    cur.execute(
        """
        SELECT chunk_id
        FROM chunk_metadata
        WHERE world_layer::text = 'primary' AND world_time IS NOT NULL
        ORDER BY chunk_id DESC
        LIMIT 1
        """
    )
    row = cur.fetchone()
    if row is None:
        raise ValueError("No primary-layer chunk with a world_time to anchor on")
    return int(row_get(row, "chunk_id", 0))


def measure_connection(
    conn: Any,
    *,
    parent_chunk_id: int | None,
    skip_minutes: Sequence[int],
    target_world_time: datetime | None,
    settings: OrrerySettings,
) -> dict[str, Any]:
    """Enumerate crossed boundaries in a caller-owned read-only transaction.

    One ``projected_child_clock`` window per skip and, when a target is given,
    one ``target_horizon`` window all read the same snapshot. Without a parent
    the newest primary-layer chunk with a world clock anchors the windows.
    """
    with conn.cursor() as cur:
        cur.execute("SELECT current_setting('transaction_read_only') AS read_only")
        read_only = row_get(cur.fetchone(), "read_only", 0)
        if read_only != "on":
            raise RuntimeError(READ_ONLY_ERROR)
        cur.execute(
            "SELECT current_database() AS database, "
            "(SELECT max(version) FROM schema_migrations) AS schema_level"
        )
        identity = cur.fetchone()
        database = str(row_get(identity, "database", 0))
        schema_level = row_get(identity, "schema_level", 1)
        anchor = (
            parent_chunk_id
            if parent_chunk_id is not None
            else _newest_primary_chunk(cur)
        )
        previous = parent_world_time(cur, anchor)
        windows: list[tuple[BoundaryWindow, Optional[int]]] = [
            (
                BoundaryWindow.projected_child_clock(
                    previous, timedelta(minutes=minutes)
                ),
                minutes,
            )
            for minutes in skip_minutes
        ]
        if target_world_time is not None:
            windows.append(
                (BoundaryWindow.target_horizon(previous, target_world_time), None)
            )
        reports = [
            _window_report(
                enumerate_crossed_boundaries(cur, window, settings=settings),
                skip_minutes=minutes,
            )
            for window, minutes in windows
        ]
    return {
        "family": FAMILY,
        "database": database,
        "schema_level": schema_level,
        "transaction_read_only": read_only,
        "parent_chunk_id": anchor,
        "previous_world_time": previous.isoformat(),
        "windows": reports,
    }


def _aware_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(
            f"--target-world-time needs an ISO 8601 offset; {value!r} is naive"
        )
    return parsed


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Measure one database and print one JSON report to stdout."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--dbname", type=metrics_dbname)
    target.add_argument("--slot", type=int, choices=range(1, 6))
    parser.add_argument("--parent-chunk", type=int)
    parser.add_argument("--target-world-time")
    args = parser.parse_args(argv)
    target_world_time = (
        _aware_datetime(args.target_world_time)
        if args.target_world_time is not None
        else None
    )
    dbname = args.dbname if args.dbname is not None else slot_dbname(args.slot)
    orrery = load_settings().orrery
    if orrery is None:
        raise RuntimeError("nexus.toml has no [orrery] settings")
    config = load_config()
    logger.info("boundary_catchup: measuring %s read-only", dbname)
    with closing(open_read_only_connection(dbname)) as conn:
        report = measure_connection(
            conn,
            parent_chunk_id=args.parent_chunk,
            skip_minutes=config.skip_minutes,
            target_world_time=target_world_time,
            settings=orrery,
        )
        conn.rollback()
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
